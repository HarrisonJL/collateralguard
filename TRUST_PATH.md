# Trust path: from the exchanges' own data to a loan

A reviewer's first question about this project is fair: **where in this repository does anything non-deterministic happen?** It does not happen in the policy, and that is on purpose. `contracts/collateral_guard.py` is a deterministic lending policy: it has no web access and no LLM, so it can never be a second, unaudited source of truth about a market. Everything that reads the exchanges, uses a model, and reaches validator consensus is in **DelistWatch**, the contract the policy reads. Its **exact deployed source is included in this repository** under [`dependencies/delistwatch/`](dependencies/delistwatch/), so the whole path can be reviewed here, end to end.

## The path

```
exchange market API (Binance market-data mirror / OKX instruments / KuCoin symbols)    every validator fetches
exchange's own delisting list + announcement pages (URLs built by the contract)         it itself
            |                                                                         dependencies/delistwatch/contracts/delist_watch_studio_next.py:490
            v
   DelistWatch.check(watch)
   - plain code reads the pair's market status from the exchange; that outranks any announcement               :187
   - plain code picks which announcements to open (those naming the token, or generic spot notices, recent)    :336, :499
   - an LLM reads ONLY announcements whose text names the token; it can only move TRADING down; a delisting
     counts only with a verbatim quote and a date written in the text                                         :514, :552, :406, :437
   - consensus: gl.vm.run_nondet; validators must agree EXACTLY on the facts (via a digest of the exact text
     the reader is shown), and on the verdict and date                                                        :661-693
   - the verdict is recomputed from the agreed facts and reading, never taken from the leader                 :442, :695
            |
            v   stored record: verdict, effective_date, checked_at, the facts the validators agreed             :745 (latest_check)
            |
            v   cross-contract VIEW read, at the moment of every call (nothing is cached)
   CollateralGuard (contracts/collateral_guard_studio_next.py)
   - reads each venue's record                                                                                :176
   - venue weight = pure function of the record (trading / countdown / out / stale / none)                    :62
   - coverage = average weight; ladder turns coverage into a share of the base ratio                          :95, :100
   - borrow() records a loan only within collateral x that limit, reading the records again                   :214
```

Line numbers are for the files as committed here; `tests/test_trust_path.py` regenerates this document and fails if it has gone stale.

## What each stage does, and where it is reviewable

| Stage | Non-deterministic? | Who must agree | Code | Tests |
|---|---|---|---|---|
| Fetch the exchange's market data and delisting notices | yes (web) | every validator fetches itself; exact agreement on the facts (via `facts_digest`) | [`delist_watch_studio_next.py:490`](dependencies/delistwatch/contracts/delist_watch_studio_next.py#L490) | [`dependencies/delistwatch/tests/`](dependencies/delistwatch/tests/) (82 tests on real exchange responses) |
| Market status of the exact pair | no (plain code) | exact, as above | [`delist_watch_studio_next.py:187`](dependencies/delistwatch/contracts/delist_watch_studio_next.py#L187) | same |
| Judge whether announcements end spot trading | yes (LLM) | same verdict and date as each validator's own reader; the quote and the date must be in each validator's own copy | [`delist_watch_studio_next.py:514`](dependencies/delistwatch/contracts/delist_watch_studio_next.py#L514), [`delist_watch_studio_next.py:406`](dependencies/delistwatch/contracts/delist_watch_studio_next.py#L406) | consensus-boundary tests in the same suite |
| Decide the verdict | no | recomputed after consensus | [`delist_watch_studio_next.py:442`](dependencies/delistwatch/contracts/delist_watch_studio_next.py#L442) | same |
| Weight a venue, average, apply the ladder | no (pure) | n/a: functions of the records | [`collateral_guard_studio_next.py:62`](contracts/collateral_guard_studio_next.py#L62), [`collateral_guard_studio_next.py:95`](contracts/collateral_guard_studio_next.py#L95), [`collateral_guard_studio_next.py:100`](contracts/collateral_guard_studio_next.py#L100) | [`tests/test_collateral_guard.py`](tests/test_collateral_guard.py) on real check records, plus mutation checks |

## Evidence that it ran: the live transactions

DelistWatch's own live proof ([`dependencies/delistwatch/CONTRACT.md`](dependencies/delistwatch/CONTRACT.md)): the first five markets registered, then each read by the validators.

| Market | Registered | First check | Verdict |
|---|---|---|---|
| `kucoin-storj` (KuCoin STORJ/USDT) | [`0x1bfaca29…`](https://explorer-studio-dev.genlayer.com/tx/0x1bfaca298fd171b148930bc1eba853d777155fada07928c0d2e40d6256dc01eb) | [`0xaeaa61ea…`](https://explorer-studio-dev.genlayer.com/tx/0xaeaa61eaeb20e45d959714408a4410d64ae75b8e58f377dfa27a09fae9d97bd6) | **TRADING** |
| `okx-storj` (OKX STORJ/USDT) | [`0xbe4cf3e5…`](https://explorer-studio-dev.genlayer.com/tx/0xbe4cf3e527136dfb7d823e77ae1b19fad0a08b3b28647320733c2c6e9828605f) | [`0x3d547be4…`](https://explorer-studio-dev.genlayer.com/tx/0x3d547be4265e8803089dbdc51ad625ffdeb6f5a36f2a72681d3d3ded8306ef8e) | **NOT_TRADING** |
| `binance-storj` (Binance STORJ/USDT) | [`0x8a756e2c…`](https://explorer-studio-dev.genlayer.com/tx/0x8a756e2c52e344cfbd59f0b61db9d604b547401c86c4d9ed7c1d9cb0ecc14ec0) | [`0xcef68338…`](https://explorer-studio-dev.genlayer.com/tx/0xcef68338a532cc9de154bea74cb4625d910a721cb90efce522148bb9b89102d6) | **NOT_TRADING** |
| `binance-btc` (Binance BTC/USDT) | [`0x7796963d…`](https://explorer-studio-dev.genlayer.com/tx/0x7796963d5c581d7b40a019f0612e74aafd1b5bf9b57899452f1c2a9365f72c62) | [`0xc5e75e8a…`](https://explorer-studio-dev.genlayer.com/tx/0xc5e75e8a93ef51620afd896787cfc1efb08d55e8247b5d502dc4c1888c12671c) | **TRADING** |
| `okx-btc` (OKX BTC/USDT) | [`0x1acff24e…`](https://explorer-studio-dev.genlayer.com/tx/0x1acff24e7c8dad08a99a8fb8b2f2198a04fffd546f5843005faeb992bc740327) | [`0xd5f81f61…`](https://explorer-studio-dev.genlayer.com/tx/0xd5f81f61fb44796eb9a790d4c1c9ea00cdfd6e102930a027330be8675e202d7f) | **TRADING** |

This project's live proof added three Ether markets and asked DelistWatch for a fresh check of all eight, each a DelistWatch transaction that its validators decided before the policy read it ([`CONTRACT.md`](CONTRACT.md), section 1):

| Market | Tx | Validators | Verdict | What the exchange said |
|---|---|---|---|---|
| `binance-eth` | [`0x0df3170c…`](https://explorer-studio-dev.genlayer.com/tx/0x0df3170cf82a873e237b1dd25c44d1c4bf4ce5aeff195f21f1ffb63f49116ea2) (registered) | 3 agree | | ETH/USDT on Binance |
| `okx-eth` | [`0x144848d7…`](https://explorer-studio-dev.genlayer.com/tx/0x144848d7329e7053666609be4aa1492e9bf9032428d2377ac8d95edfc7218ee0) (registered) | 3 agree | | ETH/USDT on OKX |
| `kucoin-eth` | [`0x9b43b63c…`](https://explorer-studio-dev.genlayer.com/tx/0x9b43b63cb29f8a05a83354729f9e3891a3b9af2524253cf828cdd40435d00c0a) (registered) | 3 agree | | ETH/USDT on KuCoin |
| `binance-btc` (check 10) | [`0x509d0f24…`](https://explorer-studio-dev.genlayer.com/tx/0x509d0f2474e7df77b0c799b9934e3541e89eb16203d2a11b6d5cd00b9571a15d) | 3 agree | **TRADING** | trading, and no announced delisting names it |
| `okx-btc` (check 11) | [`0xd912ccc6…`](https://explorer-studio-dev.genlayer.com/tx/0xd912ccc64d72219e43d107598a8c5ae97766590fe800c49d0dab4339b1938f08) | 3 agree | **TRADING** | trading, and no announced delisting names it |
| `binance-eth` (check 12) | [`0xb5ca763a…`](https://explorer-studio-dev.genlayer.com/tx/0xb5ca763a6dc294617b0cf1d281cb55495ea80c78b577e0192e461c755b42c7e9) | 3 agree | **TRADING** | trading, and no announced delisting names it |
| `okx-eth` (check 13) | [`0xbe6f2bdc…`](https://explorer-studio-dev.genlayer.com/tx/0xbe6f2bdc8b4da91b426ebf766aa6bf64ec5f985d4fa85beb517fe6afd133e361) | 3 agree | **TRADING** | trading, and no announced delisting names it |
| `kucoin-eth` (check 14) | [`0xb9a894fc…`](https://explorer-studio-dev.genlayer.com/tx/0xb9a894fc341ba87d8b090ee6a10ab892b3d48377b142e19696510fa268063da9) | 3 agree | **TRADING** | trading, and no announced delisting names it |
| `binance-storj` (check 15) | [`0x8f0540e4…`](https://explorer-studio-dev.genlayer.com/tx/0x8f0540e48b29ea18ef7c7bc3aa361f24d4b37294d008a2ffff9206ca4e98a0c5) | 3 agree | **NOT_TRADING** | market_not_trading:status=BREAK |
| `okx-storj` (check 16) | [`0xb0133b2c…`](https://explorer-studio-dev.genlayer.com/tx/0xb0133b2c302603bb93221cee23ff2de59b43ea05495409c21119847408acf33a) | 3 agree | **NOT_TRADING** | market_not_listed:Instrument ID doesn't exist |
| `kucoin-storj` (check 17) | [`0x971b5cd4…`](https://explorer-studio-dev.genlayer.com/tx/0x971b5cd4efdd3d34fa16a574b75caecdffdd87e9c168d81b06f33e5d5e81a2bc) | 3 agree | **TRADING** | trading, and no announced delisting names it |

## Identity of the dependency

| | |
|---|---|
| DelistWatch (deployed) | [`0x1AFffBad8fCfBEFD9494fd8994118f586B85DAFc`](https://explorer-studio-dev.genlayer.com/address/0x1AFffBad8fCfBEFD9494fd8994118f586B85DAFc), deploy tx [`0x6ace2420…`](https://explorer-studio-dev.genlayer.com/tx/0x6ace2420cb9a57c6cbca4d8aae1553f757fd01347c64d3ad57881fd0517a1f04) |
| Vendored from | [github.com/HarrisonJL/delistwatch](https://github.com/HarrisonJL/delistwatch), every tracked file at the commit recorded in [`dependencies/README.md`](dependencies/README.md) |
| Deployed file | `dependencies/delistwatch/contracts/delist_watch_studio_next.py`, byte-identical to the code on-chain (SHA-256 in `dependencies/README.md`; checked by `tests/test_trust_path.py` and by `studio-next/verify_dependency.ts` against the chain) |

## How to review it

```bash
# 1. the policy's tests, and the checks that tie it to the vendored dependency
.venv/bin/pytest tests -q
# 2. the dependency's own tests (offline: its exchange responses are committed)
cd dependencies/delistwatch && ../../.venv/bin/pytest tests -q
# 3. the vendored code is what is deployed
cd studio-next && npm ci && npx tsx verify_dependency.ts
```
