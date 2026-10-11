"""
Writes CONTRACT.md from studio-next/live_proof.json (the log prove.ts wrote as it ran), so no transaction
hash, verdict or percentage in it is ever transcribed by hand.   python3 scripts/build_contract_md.py
Deployment facts come from studio-next/deployment.json (written by hand once, from the deploy logs).
"""
import json
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent
L = json.loads((REPO / "studio-next" / "live_proof.json").read_text())
D = json.loads((REPO / "studio-next" / "deployment.json").read_text())
X = "https://explorer-studio-dev.genlayer.com"


def tx(h): return f"[`{h[:10]}…`]({X}/tx/{h})"
def votes(v):
    a, d = v.count("AGREE"), v.count("DISAGREE")
    return f"{a} agree" + (f", {d} disagree" if d else "")
def money(s): return f"{int(s):,}"
def pct(bps): return f"{bps / 100:g}%"


watches = [e for e in L if e["step"] == "watch"]
baskets = [e for e in L if e["step"] == "basket"]
refusals = [e for e in L if e["step"] == "refuse-basket"]
checks = [e for e in L if e["step"] == "check"]
borrows = [e for e in L if e["step"] == "borrow"]
read = next(e for e in L if e["step"] == "read")
assert all(e["result"] in ("FINISHED_WITH_RETURN", "FINISHED_WITH_ERROR") for e in L if "result" in e)
assert not any(v == "DISAGREE" for e in L for v in e.get("votes", [])), "a disagreement belongs in the text"
decided = [e for e in L if "tx" in e]

o = []
w = o.append
w("# CollateralGuard: deployment and live proof\n")
w("## Deployment\n")
w("| | |\n|---|---|")
w("| Network | GenLayer Studio Next, chain 61997 (`chains.studioDevnet`, genlayer-js 2.0.0-rc.1) |")
w(f"| CollateralGuard | [`{D['guard']['address']}`]({X}/address/{D['guard']['address']}) - deploy tx {tx(D['guard']['deploy_tx'])}; constructed with DelistWatch's address, `max_age_seconds` 86400, `base_ltv_bps` 6000 (60%) and the ladder `[[100,100],[66,70],[33,40]]` |")
w(f"| DelistWatch (the oracle it reads) | [`{D['delistwatch']['address']}`]({X}/address/{D['delistwatch']['address']}) - deploy tx {tx(D['delistwatch']['deploy_tx'])}, the contract behind the published DelistWatch project |")
w("| Runner | `py-genlayer:5jycge4q8k23462jtb0b9fyey1s9qz928sz2nbrd9mg4sxqg2qng` (v0.3.0) |")
w("| Deployer and owner | `0x5cdb5699bc1038e115A973bb91A646f7E98C075b` |\n")
w("CollateralGuard passed the live runner's `getContractSchemaForCode` check before deploying, and **the code on-chain is byte-identical to this repo**: `cd studio-next && npx tsx verify_code.ts <address> collateral_guard_studio_next.py` fetches it with `gen_getContractCode` and compares.\n")
w("| Contract | SHA-256 on-chain = SHA-256 of the repo file |\n|---|---|")
w(f"| CollateralGuard / `contracts/collateral_guard_studio_next.py` | `{D['guard']['sha256']}` |\n")
w(f"## Live proof ({D['date']})\n")
w(f"Reproduce with `cd studio-next && npx tsx prove.ts <collateralguard> <delistwatch> <watches|baskets|check|borrow|read>`. Every row is from [`studio-next/live_proof.json`](studio-next/live_proof.json), written as it ran (it resumes where it stopped). \"Agree\" counts the validators that actively voted (Studio Next leaves the rest of the 5-seat committee idle). **All {len(decided)} transactions reached consensus with every voting validator agreeing**, including the ones the contract refused: a refusal is a decided outcome.\n")

w("### 1. The markets: DelistWatch reads each exchange\n")
w("DelistWatch already watched Bitcoin and STORJ on the exchanges it supports. This proof adds Ether on three of them (registration is permissionless and immutable), then asks DelistWatch for a fresh check of all eight markets, because the policy wants a check no older than a day. Each check is DelistWatch's validators reading the exchange's own market data and delisting announcements.\n")
w("| Market | DelistWatch check | Verdict | What the exchange said |\n|---|---|---|---|")
for e in watches:
    a = e["args"]
    w(f"| `{a[0]}` | registered: {tx(e['tx'])} {votes(e['votes'])} | | {a[4]} |")
for e in checks:
    c = e["check"]
    why = "; ".join(c["reasons"]) if c["reasons"] else "trading, and no announced delisting names it"
    w(f"| `{e['args'][0]}` | check {c['check_id']}: {tx(e['tx'])} {votes(e['votes'])} | **{c['verdict']}**{(' (effective ' + c['effective_date'] + ')') if c['effective_date'] else ''} | {why} |")

w("\n### 2. Baskets, and what the policy refuses to create\n")
w("A basket is one token across up to five of DelistWatch's markets. Creating one is owner-only; the policy checks each market against DelistWatch's own list.\n")
w("| What it does | Call | Tx | Outcome |\n|---|---|---|---|")
for e in baskets:
    a = e["args"]
    w(f"| {e['note']} | `create_basket({a[0]}, {a[1]}, [{', '.join(a[2])}])` | {tx(e['tx'])} {votes(e['votes'])} | created |")
for e in refusals:
    a = e["args"]
    w(f"| {e['note']} | `create_basket({a[0]}, {a[1]}, [{', '.join(a[2])}])` | {tx(e['tx'])} {votes(e['votes'])} | refused: `{e['revert']}` |")

w("\n### 3. What each basket allows, read from the markets above\n")
w("| Basket | Venues now | Coverage | Loan-to-value |\n|---|---|---|---|")
for bid, b in read["baskets"].items():
    venues = ", ".join(f"{v['exchange']} {v['state'].lower()} ({v['weight_pct']}%)" for v in b["venues"])
    w(f"| `{bid}` ({b['token']}) | {venues} | {b['coverage_pct']}% | **{pct(b['ltv_bps'])}** of {pct(b['base_ltv_bps'])} base |")

w("\n### 4. Loans: at the limit, over it, and against nothing\n")
w("Anyone can borrow; the limit is read from DelistWatch at the moment of the call. `max_borrow` is the same sum as a read.\n")
w("| What it shows | Call | Outcome | Tx |\n|---|---|---|---|")
for e in borrows:
    b, c, a = e["args"]
    mb = f" (`max_borrow` said {money(e['max_borrow']['max_borrow'])})" if e.get("max_borrow") else ""
    out_ = "**recorded**" if e["result"] == "FINISHED_WITH_RETURN" else f"refused: `{e['revert']}`"
    w(f"| {e['note']} | `borrow({b}, {money(c)}, {money(a)})` | {out_}{mb} | {tx(e['tx'])} {votes(e['votes'])} |")
cfg = read["config"]
w(f"\nAfter the run `get_config()` reports {cfg['basket_count']} baskets and {cfg['loan_count']} loans; each loan record keeps the loan-to-value and coverage it was made under (`get_loans()`).\n")

w("## What the live run found\n")
for t in D.get("found_live", []):
    w("- " + t)
w("")
if D.get("superseded"):
    w("## Superseded deployments\n")
    w("| Contract | Address | Why it is superseded |\n|---|---|---|")
    for s in D["superseded"]:
        w(f"| {s['contract']} | `{s['address']}` | {s['why']} |")
    w("")
w("## Proven in tests, not live\n")
w("Direct Mode proves these on DelistWatch's real check records (captured from the live contract, `tests/fixtures/`) and on edited copies of them; none has a live transaction:\n")
w("- **The countdown.** A delisting announced for a known date counts 75% with 30 or more days to go, 50% from 14, 25% from 7 and 0 inside a week, in calendar days in UTC; an announced delisting whose date is unreadable counts 0. No exchange had announced a future spot delisting of a watched token on the day of the proof (their notices give days, not weeks), so a live row would have reached only the 25% or 0% step.")
w("- **A stale check** (older than the limit, or dated in the future) and **no check at all** count 0, as does an `UNDETERMINED` check or an unknown verdict.")
w("- **Coverage and the ladder**: the average rounds down, the ladder rounds down, a ladder can end in a rung that allows something at any coverage, and an invalid ladder or configuration is refused at deployment.")
w("- Every owner-only check, an invalid basket id or token, a zero loan, and an unknown basket, which are decided before any cross-contract call. The calls that read DelistWatch (`create_basket`, `borrow`, `get_status`, `max_borrow`) cannot be simulated in Direct Mode and are proven by the live tables above.")
(REPO / "CONTRACT.md").write_text("\n".join(o) + "\n")
print("wrote CONTRACT.md,", len(o), "lines;", len(decided), "transactions")
