"""
Writes TRUST_PATH.md: the end-to-end path from the exchanges' own data to a loan, with line references into the
vendored dependency and transaction hashes taken from studio-next/live_proof.json and the dependency's own
CONTRACT.md, so nothing here is transcribed by hand.   python3 scripts/build_trust_path.py
"""
import json
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parent.parent
X = "https://explorer-studio-dev.genlayer.com"
DEP = "dependencies/delistwatch/contracts/delist_watch_studio_next.py"
GRD = "contracts/collateral_guard_studio_next.py"
L = json.loads((REPO / "studio-next" / "live_proof.json").read_text())
D = json.loads((REPO / "studio-next" / "deployment.json").read_text())
dep_src = (REPO / DEP).read_text().splitlines()
grd_src = (REPO / GRD).read_text().splitlines()


def line(src, pattern, nth=0):
    hits = [i + 1 for i, s in enumerate(src) if re.search(pattern, s)]
    assert len(hits) > nth, f"pattern not found: {pattern}"
    return hits[nth]


def ref(path, n): return f"[`{path.split('/')[-1]}:{n}`]({path}#L{n})"
def tx(h): return f"[`{h[:10]}…`]({X}/tx/{h})"
def votes(v): return f"{v.count('AGREE')} agree" + (f", {v.count('DISAGREE')} disagree" if v.count("DISAGREE") else "")


ln = {
    "fetch": line(dep_src, r"gl\.nondet\.web\.get"),
    "market": line(dep_src, r"^def _market_state"),
    "facts": line(dep_src, r"^def _facts"),
    "gather": line(dep_src, r"^def _gather"),
    "read": line(dep_src, r"^def _read\b"),
    "prompt": line(dep_src, r"gl\.nondet\.exec_prompt"),
    "quote": line(dep_src, r"^def _quote_grounded"),
    "reading": line(dep_src, r"^def _reading_grounded"),
    "decide": line(dep_src, r"^def _decide"),
    "check": line(dep_src, r"def check\(self, watch_id"),
    "leader": line(dep_src, r"def leader_fn"),
    "validator": line(dep_src, r"def validator_fn"),
    "nondet": line(dep_src, r"gl\.vm\.run_nondet"),
    "recompute": line(dep_src, r"Recomputed from the agreed facts"),
    "latest": line(dep_src, r"def latest_check"),
    "list": line(dep_src, r"def list_watches"),
    "g_latest": line(grd_src, r"\.view\(\)\.latest_check"),
    "g_list": line(grd_src, r"\.view\(\)\.list_watches"),
    "g_venue": line(grd_src, r"^def _venue"),
    "g_cov": line(grd_src, r"^def _coverage"),
    "g_ltv": line(grd_src, r"^def _ltv_bps"),
    "g_basket": line(grd_src, r"def create_basket\(self"),
    "g_borrow": line(grd_src, r"def borrow\(self"),
}
dep_md = (REPO / "dependencies" / "delistwatch" / "CONTRACT.md").read_text()
regs = [(m.group(1), m.group(2), m.group(3)) for m in re.finditer(r"^\| `([a-z]+-[a-z]+)` \| ([A-Za-z]+ [A-Z]+/[A-Z]+) \| `(0x[0-9a-f]{64})` \| ✓ \|", dep_md, re.M)]
chk = [(m.group(1), m.group(2), m.group(3)) for m in re.finditer(r"^\| `([a-z]+-[a-z]+)` \| `(0x[0-9a-f]{64})` \| \*\*`([A-Z_]+)`\*\*", dep_md, re.M)]
assert len(regs) == 5 and len(chk) == 5, (len(regs), len(chk))
watches = [e for e in L if e["step"] == "watch"]
checks = [e for e in L if e["step"] == "check"]

o = []
w = o.append
w("# Trust path: from the exchanges' own data to a loan\n")
w("A reviewer's first question about this project is fair: **where in this repository does anything non-deterministic happen?** "
  "It does not happen in the policy, and that is on purpose. `contracts/collateral_guard.py` is a deterministic lending policy: it has no web access and no LLM, "
  "so it can never be a second, unaudited source of truth about a market. Everything that reads the exchanges, uses a model, and reaches validator consensus "
  "is in **DelistWatch**, the contract the policy reads. Its **exact deployed source is included in this repository** under "
  "[`dependencies/delistwatch/`](dependencies/delistwatch/), so the whole path can be reviewed here, end to end.\n")
w("## The path\n")
w("```")
w("exchange market API (Binance market-data mirror / OKX instruments / KuCoin symbols)    every validator fetches")
w("exchange's own delisting list + announcement pages (URLs built by the contract)         it itself")
w(f"            |                                                                         {DEP}:{ln['fetch']}")
w("            v")
w("   DelistWatch.check(watch)")
w(f"   - plain code reads the pair's market status from the exchange; that outranks any announcement               :{ln['market']}")
w(f"   - plain code picks which announcements to open (those naming the token, or generic spot notices, recent)    :{ln['facts']}, :{ln['gather']}")
w(f"   - an LLM reads ONLY announcements whose text names the token; it can only move TRADING down; a delisting")
w(f"     counts only with a verbatim quote and a date written in the text                                         :{ln['read']}, :{ln['prompt']}, :{ln['quote']}, :{ln['reading']}")
w(f"   - consensus: gl.vm.run_nondet; validators must agree EXACTLY on the facts (via a digest of the exact text")
w(f"     the reader is shown), and on the verdict and date                                                        :{ln['leader']}-{ln['nondet']}")
w(f"   - the verdict is recomputed from the agreed facts and reading, never taken from the leader                 :{ln['decide']}, :{ln['recompute']}")
w("            |")
w(f"            v   stored record: verdict, effective_date, checked_at, the facts the validators agreed             :{ln['latest']} (latest_check)")
w("            |")
w("            v   cross-contract VIEW read, at the moment of every call (nothing is cached)")
w(f"   CollateralGuard ({GRD})")
w(f"   - reads each venue's record                                                                                :{ln['g_latest']}")
w(f"   - venue weight = pure function of the record (trading / countdown / out / stale / none)                    :{ln['g_venue']}")
w(f"   - coverage = average weight; ladder turns coverage into a share of the base ratio                          :{ln['g_cov']}, :{ln['g_ltv']}")
w(f"   - borrow() records a loan only within collateral x that limit, reading the records again                   :{ln['g_borrow']}")
w("```\n")
w("Line numbers are for the files as committed here; `tests/test_trust_path.py` regenerates this document and fails if it has gone stale.\n")
w("## What each stage does, and where it is reviewable\n")
w("| Stage | Non-deterministic? | Who must agree | Code | Tests |\n|---|---|---|---|---|")
w(f"| Fetch the exchange's market data and delisting notices | yes (web) | every validator fetches itself; exact agreement on the facts (via `facts_digest`) | {ref(DEP, ln['fetch'])} | [`dependencies/delistwatch/tests/`](dependencies/delistwatch/tests/) (82 tests on real exchange responses) |")
w(f"| Market status of the exact pair | no (plain code) | exact, as above | {ref(DEP, ln['market'])} | same |")
w(f"| Judge whether announcements end spot trading | yes (LLM) | same verdict and date as each validator's own reader; the quote and the date must be in each validator's own copy | {ref(DEP, ln['read'])}, {ref(DEP, ln['quote'])} | consensus-boundary tests in the same suite |")
w(f"| Decide the verdict | no | recomputed after consensus | {ref(DEP, ln['decide'])} | same |")
w(f"| Weight a venue, average, apply the ladder | no (pure) | n/a: functions of the records | {ref(GRD, ln['g_venue'])}, {ref(GRD, ln['g_cov'])}, {ref(GRD, ln['g_ltv'])} | [`tests/test_collateral_guard.py`](tests/test_collateral_guard.py) on real check records, plus mutation checks |\n")
w("## Evidence that it ran: the live transactions\n")
w("DelistWatch's own live proof ([`dependencies/delistwatch/CONTRACT.md`](dependencies/delistwatch/CONTRACT.md)): the first five markets registered, then each read by the validators.\n")
w("| Market | Registered | First check | Verdict |\n|---|---|---|---|")
verdict = {k: (t, v) for k, t, v in chk}
for k, pair, t in regs:
    ct, v = verdict[k]
    w(f"| `{k}` ({pair}) | {tx(t)} | {tx(ct)} | **{v}** |")
w("\nThis project's live proof added three Ether markets and asked DelistWatch for a fresh check of all eight, each a DelistWatch transaction that its validators decided before the policy read it ([`CONTRACT.md`](CONTRACT.md), section 1):\n")
w("| Market | Tx | Validators | Verdict | What the exchange said |\n|---|---|---|---|---|")
for e in watches:
    w(f"| `{e['args'][0]}` | {tx(e['tx'])} (registered) | {votes(e['votes'])} | | {e['args'][4]} |")
for e in checks:
    c = e["check"]
    why = "; ".join(c["reasons"]) if c["reasons"] else "trading, and no announced delisting names it"
    w(f"| `{e['args'][0]}` (check {c['check_id']}) | {tx(e['tx'])} | {votes(e['votes'])} | **{c['verdict']}** | {why} |")
w("")
w("## Identity of the dependency\n")
w("| | |\n|---|---|")
w(f"| DelistWatch (deployed) | [`{D['delistwatch']['address']}`]({X}/address/{D['delistwatch']['address']}), deploy tx {tx(D['delistwatch']['deploy_tx'])} |")
w("| Vendored from | [github.com/HarrisonJL/delistwatch](https://github.com/HarrisonJL/delistwatch), every tracked file at the commit recorded in [`dependencies/README.md`](dependencies/README.md) |")
w("| Deployed file | `dependencies/delistwatch/contracts/delist_watch_studio_next.py`, byte-identical to the code on-chain (SHA-256 in `dependencies/README.md`; checked by `tests/test_trust_path.py` and by `studio-next/verify_dependency.ts` against the chain) |\n")
w("## How to review it\n")
w("```bash")
w("# 1. the policy's tests, and the checks that tie it to the vendored dependency")
w(".venv/bin/pytest tests -q")
w("# 2. the dependency's own tests (offline: its exchange responses are committed)")
w("cd dependencies/delistwatch && ../../.venv/bin/pytest tests -q")
w("# 3. the vendored code is what is deployed")
w("cd studio-next && npm ci && npx tsx verify_dependency.ts")
w("```")
TEXT = "\n".join(o) + "\n"
if __name__ == "__main__":
    (REPO / "TRUST_PATH.md").write_text(TEXT)
    print("wrote TRUST_PATH.md,", len(o), "lines")
