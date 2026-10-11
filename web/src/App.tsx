import { useCallback, useEffect, useMemo, useState } from "react";
import { AccountPanel, Pill, Section, TxPanel } from "./components/ui";
import { addressLink, errorText, onThrottle, short, type Signer } from "./lib/genlayer";
import { duration, fmtTime } from "./lib/format";
import {
  DELISTWATCH, DESK_ARGS, GUARD, GUARD_SOURCE, STATE_NAME, STATE_RULE, STATE_TONE, amountProblem, askMaxBorrow, basketProblem, boundBasket,
  boundCheck, boundLoan, cachedGuard, delistCheckCount, deployedAddress, isOwner, loadDelistCheck, loadGuard, maxBorrowFor, same, saveDesk,
  savedDesk, toUnits, type BasketStatus, type DelistCheck, type GuardData, type Venue,
} from "./lib/guard";
import { useTransaction } from "./lib/useTransaction";

const n = (s: string | number | bigint) => Number(s).toLocaleString();
const pct = (bps: number) => `${(bps / 100).toFixed(bps % 100 === 0 ? 0 : 1)}%`;
const tone = (state: string) => STATE_TONE[state] ?? "none";

function VenueChip({ v }: { v?: Venue }) {
  if (!v) return <span className="sm">·</span>;
  return <Pill tone={tone(v.state)}>{STATE_NAME[v.state] ?? v.state} · {v.weight_pct}%</Pill>;
}

function Coverage({ b }: { b: BasketStatus }) {
  return (
    <div>
      <div className="bar" aria-hidden="true"><i className="limit" style={{ width: `${b.coverage_pct}%` }} /></div>
      <div className="barlab"><span>coverage {b.coverage_pct}%</span><span>loan-to-value {pct(b.ltv_bps)} (base {pct(b.base_ltv_bps)})</span><span>{n(b.borrowed)} borrowed so far</span></div>
    </div>
  );
}

export default function App() {
  const [signer, setSigner] = useState<Signer | null>(null);
  const [desk, setDesk] = useState(savedDesk);
  const [target, setTarget] = useState<"official" | "desk">("official");
  const address = target === "desk" && desk ? desk.address : GUARD;
  const [data, setData] = useState<GuardData | null>(() => cachedGuard(GUARD));
  const [stale, setStale] = useState(() => cachedGuard(GUARD) !== null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [waitSec, setWaitSec] = useState(0);
  useEffect(() => onThrottle(setWaitSec), []);
  const tx = useTransaction();
  const busy = tx.state.stage === "submitting" || tx.state.stage === "waiting";

  const refresh = useCallback(async () => {
    setLoading(true); setError("");
    try { setData(await loadGuard(address)); setStale(false); } catch (e) { setError(errorText(e)); } finally { setLoading(false); }
  }, [address]);
  useEffect(() => { setData(cachedGuard(address)); setStale(cachedGuard(address) !== null); void refresh(); }, [address, refresh]);
  const [, tick] = useState(0);
  useEffect(() => { const t = setInterval(() => tick((x) => x + 1), 30000); return () => clearInterval(t); }, []);

  const owner = isOwner(signer, data);
  const baskets = data?.baskets ?? [];
  const [selected, setSelected] = useState("");
  const sel = baskets.find((b) => b.basket_id === selected) ?? baskets[0] ?? null;
  const exchanges = useMemo(() => [...new Set(baskets.flatMap((b) => b.venues.map((v) => v.exchange)))].sort(), [baskets]);

  // The market whose DelistWatch record is shown under the venue table.
  const [venueId, setVenueId] = useState("");
  const venue = sel?.venues.find((v) => v.watch_id === venueId) ?? sel?.venues[0] ?? null;
  const [dcheck, setDcheck] = useState<DelistCheck | null>(null);
  useEffect(() => {
    setDcheck(null);
    if (!venue || venue.check_id === null) return;
    let live = true;
    loadDelistCheck(venue.watch_id).then((c) => { if (live) setDcheck(c); }).catch(() => { /* optional detail */ });
    return () => { live = false; };
  }, [venue?.watch_id, venue?.check_id]); // eslint-disable-line react-hooks/exhaustive-deps

  // --- Writes ---------------------------------------------------------------------------
  async function runCheck(watchId: string) {
    if (!signer) return;
    const label = `Check ${watchId}`;
    tx.starting(label);
    let before: number;
    try { before = await delistCheckCount(); } catch (e) { return tx.fail(label, e); }
    const ok = await tx.run(signer, DELISTWATCH, "check", [watchId], label, "DelistWatch refused the check.", () => boundCheck(before, signer, watchId));
    if (ok) { setVenueId(watchId); setDcheck(ok); void refresh(); }
  }

  const [collateral, setCollateral] = useState("1000000");
  const [amount, setAmount] = useState("");
  const collateralBad = amountProblem(collateral);
  const limit = sel && !collateralBad ? maxBorrowFor(toUnits(collateral), sel.ltv_bps) : null;
  const [asked, setAsked] = useState<{ basket: string; collateral: string; max: string; ltv_bps: number; coverage_pct: number } | null>(null);
  const [askError, setAskError] = useState("");
  async function ask() {
    if (!sel || collateralBad) return;
    setAsked(null); setAskError("");
    try {
      const r = await askMaxBorrow(address, sel.basket_id, toUnits(collateral));
      setAsked({ basket: sel.basket_id, collateral, max: r.max_borrow, ltv_bps: r.ltv_bps, coverage_pct: r.coverage_pct });
    } catch (e) { setAskError(errorText(e)); }
  }
  async function borrow() {
    if (!signer || !data || !sel || collateralBad || amountProblem(amount)) return;
    const label = `Borrow against ${sel.basket_id}`;
    const before = data.config.loan_count;
    const ok = await tx.run(signer, address, "borrow", [sel.basket_id, toUnits(collateral), toUnits(amount)], label,
      "the policy refuses this loan.", () => boundLoan(address, before, signer, sel.basket_id));
    if (ok) { setAmount(""); setAsked(null); void refresh(); }
  }

  const [newId, setNewId] = useState("");
  const [newToken, setNewToken] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const tokens = [...new Set((data?.watches ?? []).map((w) => w.base))].sort();
  const token = newToken || tokens[0] || "";
  const candidates = (data?.watches ?? []).filter((w) => w.base === token);
  const chosen = picked.filter((id) => candidates.some((w) => w.watch_id === id));
  const problem = basketProblem(newId.trim(), token, chosen, baskets.map((b) => b.basket_id));
  async function createBasket() {
    if (!signer || problem) return;
    const id = newId.trim();
    const ok = await tx.run(signer, address, "create_basket", [id, token, chosen], `Create basket ${id}`,
      "the basket id is used, or a market does not match the token.", () => boundBasket(address, id));
    if (ok) { setNewId(""); setPicked([]); setSelected(id); void refresh(); }
  }

  async function createDesk() {
    if (!signer) return;
    const ok = await tx.deploy(signer, GUARD_SOURCE, [...DESK_ARGS], "Create my desk", "the deployment was rejected.",
      async (t) => ({ address: deployedAddress(t) }));
    if (ok) { const d = { address: ok.address as string, owner: signer.address }; saveDesk(d); setDesk(d); setTarget("desk"); }
  }
  function forgetDesk() { saveDesk(null); setDesk(null); setTarget("official"); }

  const cfg = data?.config;
  const maxAge = cfg ? Number(cfg.max_age_seconds) : 86400;
  const unchecked = sel ? sel.venues.filter((v) => v.state === "STALE" || v.state === "NO_CHECK") : [];

  return (
    <main>
      <div className="top">
        <div>
          <h1>CollateralGuard</h1>
          <p className="sub">A lending policy over exchange liquidity. A lender that takes a token as collateral depends on being able to sell it, and one exchange's delisting is not the same risk as the token being unsellable everywhere. Each venue is weighted by what DelistWatch's validators read from the exchange itself, and the loan-to-value limit follows the average.</p>
        </div>
        <div className="meta">GenLayer Studio Next (chain 61997)<br />
          Policy <a className="mono" href={addressLink(address)} target="_blank" rel="noreferrer">{short(address)}</a>{" "}
          · reads DelistWatch <a className="mono" href={addressLink(DELISTWATCH)} target="_blank" rel="noreferrer">{short(DELISTWATCH)}</a><br />
          {data
            ? stale
              ? `Showing the last read, from ${data.loadedAt.toLocaleString()}${loading ? " · reading the chain now…" : ""}`
              : `Read live from the chain at ${data.loadedAt.toLocaleTimeString()}`
            : loading ? "Reading the chain…" : ""}{" "}
          <button className="link" onClick={() => void refresh()} disabled={loading}>Refresh</button>
          {loading && waitSec > 0 && <><br />Pacing reads to the public RPC's 30-a-minute limit (about {waitSec}s)…</>}</div>
      </div>

      <AccountPanel signer={signer} onSigner={setSigner} />

      <div className="panel desk">
        <div>
          <b>Which policy</b>
          <div className="sm">
            {target === "official"
              ? <>The official policy, owned by <a className="mono" href={addressLink(data?.config.owner ?? GUARD)} target="_blank" rel="noreferrer">{short(data?.config.owner ?? GUARD)}</a>. Anyone can read it, ask DelistWatch for a fresh check of any market, and borrow against a basket. Creating baskets is owner-only.</>
              : <>Your own desk: the same audited contract, deployed from your account{desk && !same(desk.owner, signer?.address ?? "") ? <>, which belongs to <span className="mono">{short(desk.owner)}</span> (sign in with that account to act as its owner)</> : ""}. You are its owner, so you can create baskets of your own.</>}
          </div>
        </div>
        <div className="actions">
          <button className={target === "official" ? "" : "secondary"} aria-pressed={target === "official"} onClick={() => setTarget("official")}>Official policy</button>
          {desk
            ? <>
                <button className={target === "desk" ? "" : "secondary"} aria-pressed={target === "desk"} onClick={() => setTarget("desk")}>My desk</button>
                <button className="secondary" onClick={forgetDesk}>Forget my desk</button>
              </>
            : <button className="secondary" disabled={!signer || busy} onClick={() => void createDesk()}
                      title={signer ? "" : "Sign in above to deploy"}>Create my desk</button>}
        </div>
      </div>

      <TxPanel state={tx.state} onReset={tx.reset}>
        {(b) =>
          b?.address ? <div className="result">Your desk is live at <a className="mono" href={addressLink(b.address)} target="_blank" rel="noreferrer">{short(b.address)}</a>. Create a basket below from DelistWatch's markets, then borrow against it.</div>
          : b?.loan_id !== undefined ? <div className="result"><b>Loan #{b.loan_id}</b> recorded: <b>{n(b.amount)}</b> against collateral worth {n(b.collateral_value)} in <span className="mono">{b.basket_id}</span>, at {pct(b.ltv_bps)} loan-to-value ({b.coverage_pct}% coverage).</div>
          : b?.verdict ? <div className="result"><b>DelistWatch check {b.check_id}</b> recorded for <span className="mono">{b.watch_id}</span>: <Pill tone={b.verdict === "TRADING" ? "ok" : b.verdict === "DELISTING_ANNOUNCED" ? "warn" : b.verdict === "NOT_TRADING" ? "bad" : "none"}>{b.verdict}</Pill> The policy now reads this check.</div>
          : <div className="result">Basket <span className="mono">{b?.basket_id}</span> created for {b?.token}.</div>}
      </TxPanel>

      {cfg && (
        <div className="stats">
          <div className="stat"><b>{cfg.basket_count}</b><span>baskets</span></div>
          <div className="stat"><b>{cfg.loan_count}</b><span>loans recorded</span></div>
          <div className="stat"><b>{pct(cfg.base_ltv_bps)}</b><span>base loan-to-value</span></div>
          <div className="stat"><b>{duration(maxAge * 1000)}</b><span>oldest check the policy accepts</span></div>
        </div>
      )}

      <Section title="How the limit is decided">
        <div className="rules">
          <div><b>1 · Each venue</b><span>Weighted by DelistWatch's latest check of that market: <b>Trading 100%</b>; <b>Delisting announced</b> {data ? data.rules.countdown.map((c) => `${c.venue_share_pct}% with ${c.days_at_least}+ days to go`).join(", ") : "…"}, 0% inside {data ? Math.min(...data.rules.countdown.map((c) => c.days_at_least)) : 7} days; <b>Not trading, stale or unchecked 0%</b>.</span></div>
          <div><b>2 · Coverage</b><span>The average weight of the basket's venues, in whole percent. Two of three venues trading is 66%.</span></div>
          <div><b>3 · The ladder</b><span>Coverage turns into a share of the base ratio ({cfg ? pct(cfg.base_ltv_bps) : "…"}): {data ? data.rules.coverage_ladder.map(([m, s]) => `${m}%+ coverage → ${s}%`).join(", ") : "…"}, below that nothing.</span></div>
          <div><b>4 · The loan</b><span>Collateral value × that ratio, read from DelistWatch at the moment of the loan, so a venue that stopped trading since lowers it.</span></div>
        </div>
      </Section>

      <Section title="Baskets · tokens × exchanges" aside={<span className="sm">live from the policy, which reads DelistWatch's latest check of every market now</span>}>
        {error && <div className="err">Couldn't read the chain: {error}</div>}
        {!data && !error && <p className="sub">Reading the chain…</p>}
        {data && baskets.length === 0 && <p className="sub">No baskets yet. {owner ? "Create one below." : target === "desk" ? "Sign in as this desk's owner to create one." : ""}</p>}
        {baskets.length > 0 && (
          <div className="panel">
            <div className="scroll">
              <table className="matrix">
                <thead><tr><th className="firm">Basket · token</th>{exchanges.map((e) => <th key={e}>{e}</th>)}<th>Coverage</th><th>Loan-to-value</th></tr></thead>
                <tbody>
                  {baskets.map((b) => (
                    <tr key={b.basket_id} className={b.basket_id === sel?.basket_id ? "on" : ""}>
                      <td className="firm"><button aria-pressed={b.basket_id === sel?.basket_id} onClick={() => { setSelected(b.basket_id); setVenueId(""); setAsked(null); }}>{b.basket_id}</button> <span className="sm">· {b.token}</span></td>
                      {exchanges.map((e) => <td key={e}><VenueChip v={b.venues.find((v) => v.exchange === e)} /></td>)}
                      <td className="num">{b.coverage_pct}%</td>
                      <td><b>{pct(b.ltv_bps)}</b></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </Section>

      {sel && (
        <Section title="One basket in detail">
          <div className="panel">
            <div className="row">
              <div>
                <div className="name">{sel.basket_id} <span className="sm">· {sel.token}</span></div>
                <div className="sm">Created {fmtTime(sel.created_at)}. Each row below is one market, read by DelistWatch's validators from the exchange's own data.</div>
              </div>
              <Pill tone={sel.ltv_bps > 0 ? "ok" : "bad"}>{sel.ltv_bps > 0 ? `up to ${pct(sel.ltv_bps)} loan-to-value` : "no loans"}</Pill>
            </div>
            <Coverage b={sel} />
            {unchecked.length > 0 && (
              <div className="notice">{unchecked.length === 1 ? "One market has" : `${unchecked.length} markets have`} no check fresher than {duration(maxAge * 1000)}, so {unchecked.length === 1 ? "it counts" : "they count"} as 0%. Ask DelistWatch for a fresh check below ({unchecked.map((v) => `${v.exchange}`).join(", ")}); it takes about a minute and anyone can do it.</div>
            )}
            <div className="tablewrap" style={{ marginTop: 12 }}>
              <table className="list venues">
                <thead><tr><th>Market</th><th>State</th><th>Counted</th><th>DelistWatch said</th><th>Checked</th><th /></tr></thead>
                <tbody>
                  {sel.venues.map((v) => (
                    <tr key={v.watch_id} className={v.watch_id === venue?.watch_id ? "on" : ""}>
                      <td><button className="link" onClick={() => setVenueId(v.watch_id)}>{v.exchange}</button> <span className="sm">{sel.token}/{v.quote}</span></td>
                      <td><Pill tone={tone(v.state)}>{STATE_NAME[v.state] ?? v.state}</Pill>{v.days_left !== null && <div className="sm">{v.days_left} days left</div>}</td>
                      <td><b>{v.weight_pct}%</b></td>
                      <td className="sm">{v.verdict}</td>
                      <td className="sm">{v.checked_at ? `${duration((v.age_seconds ?? 0) * 1000)} ago` : "never"}</td>
                      <td><button className="secondary" disabled={!signer || busy} onClick={() => void runCheck(v.watch_id)} title={signer ? "" : "Sign in above to send a transaction"}>Fresh check</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {venue && (
              <div className="detail">
                <b>{venue.exchange}</b> <Pill tone={tone(venue.state)}>{STATE_NAME[venue.state] ?? venue.state}</Pill>
                <div className="why">{STATE_RULE[venue.state]}</div>
                <div className="why">The policy's reading of the latest check: {venue.reason}.</div>
                {dcheck && dcheck.verdict !== "NONE" && (
                  <div className="why">
                    DelistWatch check {dcheck.check_id} by <a className="mono" href={addressLink(dcheck.submitted_by)} target="_blank" rel="noreferrer">{short(dcheck.submitted_by)}</a>, {fmtTime(dcheck.checked_at)}: <b>{dcheck.verdict}</b>
                    {dcheck.effective_date ? ` · effective ${dcheck.effective_date}` : ""}{dcheck.reasons?.length ? ` · ${dcheck.reasons.join("; ")}` : ""}
                    {dcheck.reading?.evidence && <> · the exchange's words: <q>{dcheck.reading.evidence}</q></>}
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="two">
            <div className="panel form">
              <b>What could I borrow?</b>
              <div className="sm">Collateral value × the loan-to-value above. The contract does the same sum when you borrow.</div>
              <label>Collateral value<input inputMode="numeric" value={collateral} onChange={(e) => { setCollateral(e.target.value); setAsked(null); }} /></label>
              <div className="result">{collateralBad ? <span className="sm">{collateralBad}</span> : limit !== null && <>Up to <b>{n(limit)}</b> at {pct(sel.ltv_bps)}.</>}</div>
              <div className="actions">
                <button className="secondary" disabled={!!collateralBad} onClick={() => void ask()}>Ask the contract</button>
                <span className="sm">a read, no transaction</span>
              </div>
              {askError && <div className="err">{askError}</div>}
              {asked && asked.basket === sel.basket_id && <div className="sm">The contract says: up to <b>{n(asked.max)}</b> ({pct(asked.ltv_bps)} at {asked.coverage_pct}% coverage).</div>}
            </div>
            <div className="panel form">
              <b>Borrow</b>
              <div className="sm">Records a loan if it is within the limit the policy reads from DelistWatch right now. Anyone can borrow; nothing is moved, the policy keeps the record.</div>
              <label>Amount<input inputMode="numeric" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="500000" /></label>
              <div className="actions">
                <button disabled={!signer || busy || !!collateralBad || !!amountProblem(amount)} onClick={() => void borrow()}>Borrow</button>
                {amount && amountProblem(amount) && <span className="sm">{amountProblem(amount)}</span>}
                {amount && !amountProblem(amount) && limit !== null && toUnits(amount) > limit && <span className="sm">More than {n(limit)}: the contract will refuse it, and the refusal is a recorded outcome.</span>}
                {!signer && <span className="sm">Sign in above to send a transaction.</span>}
              </div>
            </div>
          </div>
        </Section>
      )}

      {owner && (
        <Section title="Create a basket">
          <div className="panel form">
            <div className="sm">A basket is one token across up to five markets that DelistWatch watches. Pick the token, then its markets.</div>
            <div className="formrow">
              <label>Basket id<input value={newId} onChange={(e) => setNewId(e.target.value)} placeholder="my-basket" maxLength={32} /></label>
              <label>Token<select value={token} onChange={(e) => { setNewToken(e.target.value); setPicked([]); }}>{tokens.map((t) => <option key={t} value={t}>{t}</option>)}</select></label>
            </div>
            <div className="picks">
              {candidates.map((w) => (
                <label key={w.watch_id} className={`pick ${chosen.includes(w.watch_id) ? "on" : ""}`}>
                  <input type="checkbox" checked={chosen.includes(w.watch_id)} onChange={(e) => setPicked(e.target.checked ? [...chosen, w.watch_id] : chosen.filter((x) => x !== w.watch_id))} />
                  {w.exchange} <span className="sm">{w.base}/{w.quote}</span>
                </label>
              ))}
            </div>
            <div className="actions">
              <button disabled={!signer || busy || !!problem} onClick={() => void createBasket()}>Create basket</button>
              {problem && (newId || chosen.length > 0) && <span className="sm">{problem}</span>}
            </div>
          </div>
        </Section>
      )}

      <Section title="Loans" aside={<span className="sm">newest first</span>}>
        {data && (
          <div className="tablewrap">
            <table className="list">
              <thead><tr><th>Loan</th><th>Basket</th><th>Borrower</th><th>Collateral</th><th>Amount</th><th>Loan-to-value</th><th>Coverage</th><th>When</th></tr></thead>
              <tbody>
                {data.loans.map((l) => (
                  <tr key={l.loan_id}>
                    <td className="num">#{l.loan_id}</td><td className="mono">{l.basket_id}</td>
                    <td><a className="mono" href={addressLink(l.borrower)} target="_blank" rel="noreferrer">{short(l.borrower)}</a></td>
                    <td>{n(l.collateral_value)}</td><td>{n(l.amount)}</td><td>{pct(l.ltv_bps)}</td><td>{l.coverage_pct}%</td><td>{fmtTime(l.recorded_at)}</td>
                  </tr>
                ))}
                {data.loans.length === 0 && <tr><td colSpan={8}>No loans yet.</td></tr>}
              </tbody>
            </table>
          </div>
        )}
        <p className="sm">A refused loan (above the limit, or against a basket with no coverage) is a decided transaction that records nothing; every refusal with the policy's reason is in the repository's CONTRACT.md.</p>
      </Section>

      <footer>
        <p>The limit reflects what the exchanges' own market data and delisting announcements said when DelistWatch's validators last read them. It is not investment advice, and it says nothing about how deep a market is: a pair can trade and still be thin. Source, tests and every transaction: <a href="https://github.com/HarrisonJL/collateralguard" target="_blank" rel="noreferrer">github.com/HarrisonJL/collateralguard</a>.</p>
      </footer>
    </main>
  );
}
