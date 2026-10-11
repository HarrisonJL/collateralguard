// Reproducible live proof for CollateralGuard. Every step's tx hash, result, votes and the
// contract's recorded output are appended to live_proof.json - the source for CONTRACT.md's
// tables. Steps already in live_proof.json are skipped and each run stops at a time budget,
// so a stall costs nothing: run the same command again.
//
//   npx tsx prove.ts <collateralguard> <delistwatch> <phase>
//   phases: watches | baskets | check | borrow | read
import * as fs from "fs";
import { client, readClient, write, safeJson } from "./lib";

// DelistWatch watches this proof adds (the five existing ones - BTC and STORJ - were registered with DelistWatch itself).
const NEW_WATCHES: [string, string, string, string, string][] = [
  ["binance-eth", "binance", "ETH", "USDT", "ETH/USDT on Binance"],
  ["okx-eth", "okx", "ETH", "USDT", "ETH/USDT on OKX"],
  ["kucoin-eth", "kucoin", "ETH", "USDT", "ETH/USDT on KuCoin"],
];
const ALL_WATCHES = ["binance-btc", "okx-btc", "binance-eth", "okx-eth", "kucoin-eth", "binance-storj", "okx-storj", "kucoin-storj"];

// [basket id, token, venues, what it shows]
const BASKETS: [string, string, string[], string][] = [
  ["btc-core", "BTC", ["binance-btc", "okx-btc"], "Bitcoin on two exchanges, both trading"],
  ["eth-core", "ETH", ["binance-eth", "okx-eth", "kucoin-eth"], "Ether on three exchanges, all trading"],
  ["storj-mixed", "STORJ", ["binance-storj", "okx-storj", "kucoin-storj"], "STORJ delisted on Binance and OKX, still trading on KuCoin: one venue in three"],
  ["storj-gone", "STORJ", ["binance-storj", "okx-storj"], "STORJ on the two exchanges that delisted it: nothing left"],
];
// Baskets the contract must refuse before any loan is involved.
const REFUSE_BASKETS: [string, [string, string, string[]], string][] = [
  ["refuse-basket-twice", ["btc-core", "BTC", ["binance-btc"]], "a basket id used twice"],
  ["refuse-wrong-token", ["x-wrong", "BTC", ["binance-btc", "binance-storj"]], "a STORJ market inside a BTC basket"],
  ["refuse-unknown-watch", ["x-unknown", "BTC", ["binance-doge"]], "a market DelistWatch has never heard of"],
  ["refuse-duplicate-venue", ["x-dup", "BTC", ["binance-btc", "binance-btc"]], "the same market listed twice"],
];
// [id, basket, collateral value, amount, what it shows]
const BORROWS: [string, string, string, string, string][] = [
  ["b-btc-ok", "btc-core", "1000000", "500000", "full coverage: 60% loan-to-value, so up to 600,000 against 1,000,000"],
  ["b-btc-over", "btc-core", "1000000", "700000", "more than the limit: refused, with the limit stated"],
  ["b-eth-ok", "eth-core", "2000000", "1200000", "exactly at the limit (60% of 2,000,000): allowed"],
  ["b-storj-ok", "storj-mixed", "1000000", "200000", "one venue in three trades: coverage 33%, so 40% of the 60%: up to 240,000"],
  ["b-storj-over", "storj-mixed", "1000000", "300000", "above that reduced limit: refused"],
  ["b-gone", "storj-gone", "1000000", "1", "coverage 0%: no loans at all"],
  ["b-unknown", "no-such-basket", "1000000", "1", "a basket that does not exist"],
];

function load(): any[] {
  return fs.existsSync("live_proof.json") ? JSON.parse(fs.readFileSync("live_proof.json", "utf-8")) : [];
}
function log(entry: Record<string, unknown>) {
  const all = load();
  all.push(entry);
  fs.writeFileSync("live_proof.json", JSON.stringify(all, null, 1));
}
const done = (id: string) => load().some((e) => e.id === id);

function revertMessage(tx: any): string {
  const found: string[] = [];
  const walk = (o: any) => {
    if (typeof o === "string") {
      const m = o.match(/(basket_id already exists|unknown basket_id|watch_id already registered|[^\n"]*refused: [^\n"]*|a basket holds[^\n"]*|a venue can only be[^\n"]*|only the owner[^\n"]*|amount must[^\n"]*|token must[^\n"]*|basket_id must[^\n"]*)/);
      if (m) found.push(m[0]);
    } else if (o && typeof o === "object") Object.values(o).forEach(walk);
  };
  walk(tx);
  return found[0] ?? "";
}

async function main() {
  const [guard, dw, phase] = process.argv.slice(2);
  const c = client();
  const r = readClient();
  const votes = (tx: any) => tx.last_round?.validator_votes_name ?? [];
  const started = Date.now();
  const outOfTime = () => Date.now() - started > 330_000;
  const view = async (address: string, fn: string, args: unknown[] = []) => {
    await new Promise((res) => setTimeout(res, 2200));
    return JSON.parse(safeJson(await r.readContract({ address, functionName: fn, args })));
  };
  const stop = () => console.log("  (time budget reached - run this phase again to continue)");
  const state = async (basket: string) => {
    const s = await view(guard, "get_status", [basket]);
    console.log(`     ${basket}: coverage ${s.coverage_pct}% -> ${s.ltv_bps / 100}% loan-to-value; venues ${s.venues.map((v: any) => v.exchange + ":" + v.state).join(", ")}`);
    return s;
  };

  if (phase === "watches") {
    const known = (await view(dw, "list_watches")).map((w: any) => w.watch_id);
    for (const [id, exchange, base, quote, label] of NEW_WATCHES) {
      if (done("watch-" + id) || known.includes(id)) continue;
      if (outOfTime()) return stop();
      const { hash, tx } = await write(c, dw, "register_watch", [id, exchange, base, quote, label]);
      log({ id: "watch-" + id, step: "watch", args: [id, exchange, base, quote, label], note: `DelistWatch learns ${label}`, tx: hash, result: tx.txExecutionResultName, votes: votes(tx) });
    }
    return process.exit(0);
  }
  if (phase === "baskets") {
    for (const [id, token, venues, note] of BASKETS) {
      if (done("basket-" + id)) continue;
      if (outOfTime()) return stop();
      const { hash, tx } = await write(c, guard, "create_basket", [id, token, venues]);
      log({ id: "basket-" + id, step: "basket", args: [id, token, venues], note, tx: hash, result: tx.txExecutionResultName, votes: votes(tx), revert: revertMessage(tx) });
    }
    for (const [id, args, note] of REFUSE_BASKETS) {
      if (done(id)) continue;
      if (outOfTime()) return stop();
      const { hash, tx } = await write(c, guard, "create_basket", args);
      const message = tx.txExecutionResultName === "FINISHED_WITH_ERROR" ? revertMessage(tx) : "";
      log({ id, step: "refuse-basket", args, note, tx: hash, result: tx.txExecutionResultName, votes: votes(tx), revert: message });
      console.log(`  ${id}: ${tx.txExecutionResultName} ${message}`);
    }
    return process.exit(0);
  }
  if (phase === "check") {
    for (const w of ALL_WATCHES) {
      if (done("check-" + w)) continue;
      if (outOfTime()) return stop();
      const { hash, tx } = await write(c, dw, "check", [w]);
      const chk = await view(dw, "latest_check", [w]);
      log({ id: "check-" + w, step: "check", args: [w], note: `DelistWatch reads ${w} on the exchange`, tx: hash, result: tx.txExecutionResultName, votes: votes(tx),
            check: { check_id: chk.check_id, verdict: chk.verdict, checked_at: chk.checked_at, effective_date: chk.effective_date ?? "", reasons: chk.reasons } });
      console.log(`     ${w}: ${chk.verdict} ${chk.effective_date ?? ""}`);
    }
    return process.exit(0);
  }
  if (phase === "borrow") {
    for (const [id, basket, collateral, amount, note] of BORROWS) {
      if (done(id)) continue;
      if (outOfTime()) return stop();
      const { hash, tx } = await write(c, guard, "borrow", [basket, BigInt(collateral), BigInt(amount)]);
      const message = tx.txExecutionResultName === "FINISHED_WITH_ERROR" ? revertMessage(tx) : "";
      const mb = basket === "no-such-basket" ? null : await view(guard, "max_borrow", [basket, collateral]);
      log({ id, step: "borrow", args: [basket, collateral, amount], note, tx: hash, result: tx.txExecutionResultName, votes: votes(tx), revert: message, max_borrow: mb });
      console.log(`  borrow(${basket}, ${collateral}, ${amount}) -> ${tx.txExecutionResultName} ${message}`);
    }
    return process.exit(0);
  }
  if (phase === "read") {
    const out: Record<string, any> = {};
    for (const [id] of BASKETS) out[id] = await state(id);
    const loans = await view(guard, "get_loans", [0, 20]);
    const config = await view(guard, "get_config");
    const rules = await view(guard, "get_rules");
    if (!done("read")) log({ id: "read", step: "read", baskets: out, loans, config, rules });
    return process.exit(0);
  }
  console.log("phases: watches | baskets | check | borrow | read");
  process.exit(1);
}

main().catch((e) => {
  console.error(e?.shortMessage ?? e?.message ?? e);
  process.exit(1);
});
