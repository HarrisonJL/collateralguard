# CollateralGuard

**How much may a lender lend against this token, given where it can still be sold?** A GenLayer Intelligent Contract that turns [DelistWatch](https://github.com/HarrisonJL/delistwatch)'s verdicts about exchange markets into a loan-to-value limit. A lender that accepts a token as collateral depends on being able to sell it, and one exchange's delisting is not the same risk as the token being unsellable anywhere. CollateralGuard groups the same token across exchanges into a **basket**, weights each exchange by what DelistWatch's validators read from the exchange itself, and lends less as coverage falls: full limit when every venue trades, a reduced one when some have gone, **none when nothing is left**.

| | |
|---|---|
| Network | GenLayer Studio Next (chain 61997) |
| CollateralGuard | [`0x1b0C8D779D58DFD67CF491840A8b081094d53e8C`](https://explorer-studio-dev.genlayer.com/address/0x1b0C8D779D58DFD67CF491840A8b081094d53e8C) |
| Reads | [DelistWatch `0x1AFffBad…85DAFc`](https://explorer-studio-dev.genlayer.com/address/0x1AFffBad8fCfBEFD9494fd8994118f586B85DAFc), the contract whose validators read Binance's, OKX's and KuCoin's own market data and delisting notices. **Its exact deployed source is included in this repository:** [`dependencies/delistwatch/`](dependencies/delistwatch/) |
| Live app | [collateralguard.vercel.app](https://collateralguard.vercel.app) (source in [`web/`](web/)) |
| Live proof | [CONTRACT.md](CONTRACT.md): eight real markets read, four baskets (full, mixed and zero coverage), loans at the limit and over it, every refusal, every transaction linked |
| Trust path | [TRUST_PATH.md](TRUST_PATH.md): from the exchanges' own data, through DelistWatch's validators, to a loan, with line references, tests and live transactions |
| Tests | 82 Direct Mode tests on DelistWatch's real check records; 42 safety mutations, all killed; 8 tests tying the policy to the included DelistWatch (whose own 82 tests run in place); 30 web-app tests |

> **A policy, not a lender.** CollateralGuard records loans and limits; it does not hold or move tokens, and it does **not price the collateral**: the collateral value is what the caller states (a real lender feeds it from its own price source). What the policy adds is the liquidity side of the limit.

## Where the non-deterministic part is

**Not in the policy, and on purpose.** `contracts/collateral_guard.py` is a deterministic lending policy: no web access, no LLM. It cannot be a second, unaudited source of truth about a market; it turns agreed records into a loan limit. Everything that reads the exchanges, uses a model and reaches validator consensus happens in **DelistWatch**, which the policy reads, and DelistWatch's **exact deployed source is in this repository** ([`dependencies/delistwatch/`](dependencies/delistwatch/), byte-identical to the code on-chain). [TRUST_PATH.md](TRUST_PATH.md) walks the whole path with line references, the tests that keep it honest (`tests/test_trust_path.py`) and the live transactions that ran it.

## Why this exists

[DelistWatch](https://github.com/HarrisonJL/delistwatch) answers a factual question about one market: is BASE/QUOTE on this exchange trading, has the exchange announced its end, or is it not trading? Its own consumer, CollateralPolicy, is a switch for a single market. Lending against a token is rarely that simple. STORJ is delisted on Binance and OKX and still trades on KuCoin: the token is not unsellable, but it is much less liquid than it was, and a lender should know and lend less, not refuse or ignore it.

## How it decides

The policy reads DelistWatch's **latest check for every venue in the basket at the moment of the call**:

| Venue state | Counted | When |
|---|---|---|
| `TRADING` | 100% | The exchange's own data says the pair trades, and no announcement ends it |
| `DELISTING` | 75% with 30+ days to the announced date, 50% from 14, 25% from 7, **0% inside a week** | Still trading, but the exchange announced an end date (calendar days, UTC) |
| `OUT` | 0% | The exchange's own data says the pair is halted, suspended or not listed |
| `STALE` | 0% | The latest check is older than the policy allows (a day here), or dated in the future |
| `NO_CHECK` / `UNKNOWN` | 0% | DelistWatch never checked the market, could not settle it, or gave a verdict this policy does not know |

**Coverage** is the average weight of the basket's venues, in whole percent. A **ladder** set at deployment turns coverage into a share of the base loan-to-value ratio. The proof instance uses a 60% base and `[[100,100],[66,70],[33,40]]`: full coverage 60%, two thirds 42%, one third 24%, less than that nothing. The loan limit is collateral value × that ratio, rounded down, read at the moment of the loan.

Why an average and not "the worst venue": a token that trades on two of three exchanges is genuinely less exposed than one that trades on one. The ladder is where the lender's caution lives, and it is a constructor argument, not a constant.

## The calls

| Call | Who | What it does |
|---|---|---|
| `create_basket(basket_id, token, watch_ids)` | owner | One token across up to five of DelistWatch's markets. Refused if the id exists, a market is unknown to DelistWatch, or a market watches a different token. |
| `borrow(basket_id, collateral_value, amount)` | **anyone** | Records a loan if the amount is within collateral × the limit the policy reads from DelistWatch right now. Refused with the limit in the message otherwise. |

Views: `get_status(basket_id)` (every venue's state, weight, check age and days left, coverage, the limit), `max_borrow(basket_id, collateral_value)` (the same sum as a read), `list_baskets`, `get_loans`, `get_config`, `get_rules` (the weights, countdown and ladder themselves, so an app can show the contract's own numbers).

## Using it from another contract

```python
guard = gl.contract.get_at(GUARD_ADDRESS)        # Studio Next syntax
limit = guard.view().max_borrow("btc-core", collateral_value)
if int(limit["max_borrow"]) < amount:
    raise gl.vm.UserError(f"loan refused: {limit['coverage_pct']}% coverage allows {limit['max_borrow']}")
```

`max_borrow` is computed at the moment of the call from DelistWatch's latest checks, so a consumer inherits the freshness rule without implementing it.

## The web app

[`web/`](web/) is a Vite + React app that reads the policy live and sends real transactions through the whole consensus lifecycle (genlayer-js 2.0.0-rc.1, Studio Next). Reading needs no account; writing uses a wallet (MetaMask) or a throwaway in-browser account funded from Studio Next's faucet.

- **The matrix** shows every basket against every exchange: each venue's state and weight, the basket's coverage and its loan-to-value. The rules above are read from the contract and shown on the page.
- **One basket in detail** lists each market with the age of DelistWatch's check, and DelistWatch's own record (including the exchange's quoted words when a delisting is announced).
- **Fresh check** is a real transaction anyone can send: every validator reads the exchange's market data and delisting announcements. The result shown is the check **this** transaction created (compared before and after, and by sender), never "the latest one".
- **What could I borrow?** is the contract's own `max_borrow` read; **Borrow** records a loan. Both work for any account, on the official policy.
- **Create a basket** is owner-only. So the app lets you **create your own desk**: it deploys this exact contract from your account (the code the app carries is byte-identical to the deployed one; a test checks its SHA-256 against the code on-chain), and you are its owner.

### Try it in five minutes

1. Open the app. **Use a temporary account**, then **Get 100 test GEN**.
2. In the matrix, compare `eth-core` (three exchanges, all trading: 60% loan-to-value) with `storj-mixed` (delisted on two of three: 24%) and `storj-gone` (delisted on both: no loans).
3. Click `storj-mixed`. Under **What could I borrow?** keep the collateral at 1,000,000 and click **Ask the contract**: up to 240,000.
4. Under **Borrow**, enter 300000 and click **Borrow**. The contract refuses it and states the limit. Enter 200000 and borrow again: the loan is recorded.
5. If a basket shows a stale check (checks expire after a day), click **Fresh check** on its markets and wait a minute or two: every validator reads the exchange, and the basket recovers.
6. Optional: click **Create my desk**, then under **Create a basket** choose a token, pick its markets and create your own basket.

## What this proves, and what it doesn't

| It proves | It does not prove |
|---|---|
| What each exchange's own market data and delisting announcements said about a pair when DelistWatch's validators read them, agreed by a committee | That a market is **deep**: a pair can trade and still be thin |
| The limit was computed from those records at the moment of the loan, and each loan keeps the limit and coverage it was made under | The **price** of the collateral: the collateral value is the caller's statement |
| A delisting is counted only with a quoted, dated announcement from the exchange | Anything about **decentralised markets**, other exchanges, or products other than spot |
| | That a loan is safe: the policy lowers a limit for liquidity risk, nothing else |

## Known limitations

- **Three exchanges** (Binance, OKX, KuCoin): the ones DelistWatch can read from validators. Bybit refuses the validators' addresses.
- **Spot markets only.** Futures, margin and Earn delistings do not count.
- **The countdown is proven in tests on real records, not live.** On the day of the proof none of the three exchanges' delisting lists announced a future spot delisting of a watched token, and exchanges give days of notice rather than weeks (OKX's STORJ notice gave ten), so a real notice reaches the 25% and 0% steps, rarely the 75% and 50% ones.
- **Freshness is a policy choice.** Checks older than a day count as zero, so an unattended policy fails closed; anyone can refresh a market with one transaction.
- **A basket is the owner's grouping**: it can only hold markets of the one token, but the owner decides which exchanges count.
- **Studio Next only.**

## Running it

```bash
python3 -m venv .venv && .venv/bin/pip install genlayer-test==0.29.2 genvm-linter==0.11.0 pytest
.venv/bin/pytest tests -q                       # 82 contract tests + 8 trust-path tests
(cd dependencies/delistwatch && ../../.venv/bin/pytest tests -q)   # DelistWatch's own 82 (offline)
.venv/bin/genvm-lint check contracts/collateral_guard.py
python3 scripts/mutation_check.py               # every safety mutation must be killed

cd studio-next && npm ci
npx tsx verify_code.ts <address> collateral_guard_studio_next.py     # on-chain code == this repo
npx tsx verify_dependency.ts                                         # on-chain DelistWatch == dependencies/delistwatch

cd ../web && npm ci && npm test && npm run build && npm run preview
```

## Repository layout

```
contracts/collateral_guard.py              tested source (GenVM v0.2.11)
contracts/collateral_guard_studio_next.py  deployed port (Studio Next); web/src/lib carries a byte-identical copy
dependencies/delistwatch/                  DelistWatch: the exact deployed contract the policy reads (source, tests, docs, licence)
TRUST_PATH.md                              the end-to-end path, generated from the code and the live proof
tests/                                     Direct Mode tests, DelistWatch's real check records, mutations.txt, test_trust_path.py
scripts/                                   port, mutation check, CONTRACT.md and TRUST_PATH.md builders
studio-next/                               deploy, live proof (prove.ts, live_proof.json), verify_code.ts
web/                                       the live app (Vite + React + genlayer-js)
research/                                  what the policy reads from DelistWatch, and what the live data showed
```
