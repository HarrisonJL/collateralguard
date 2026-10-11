# CollateralGuard: deployment and live proof

## Deployment

| | |
|---|---|
| Network | GenLayer Studio Next, chain 61997 (`chains.studioDevnet`, genlayer-js 2.0.0-rc.1) |
| CollateralGuard | [`0x1b0C8D779D58DFD67CF491840A8b081094d53e8C`](https://explorer-studio-dev.genlayer.com/address/0x1b0C8D779D58DFD67CF491840A8b081094d53e8C) - deploy tx [`0x433caa5c…`](https://explorer-studio-dev.genlayer.com/tx/0x433caa5c2d8d7a661c673591a1ceac31cdc5efeee19e46d1b114fcecd090d732); constructed with DelistWatch's address, `max_age_seconds` 86400, `base_ltv_bps` 6000 (60%) and the ladder `[[100,100],[66,70],[33,40]]` |
| DelistWatch (the oracle it reads) | [`0x1AFffBad8fCfBEFD9494fd8994118f586B85DAFc`](https://explorer-studio-dev.genlayer.com/address/0x1AFffBad8fCfBEFD9494fd8994118f586B85DAFc) - deploy tx [`0x6ace2420…`](https://explorer-studio-dev.genlayer.com/tx/0x6ace2420cb9a57c6cbca4d8aae1553f757fd01347c64d3ad57881fd0517a1f04), the contract behind the published DelistWatch project |
| Runner | `py-genlayer:5jycge4q8k23462jtb0b9fyey1s9qz928sz2nbrd9mg4sxqg2qng` (v0.3.0) |
| Deployer and owner | `0x5cdb5699bc1038e115A973bb91A646f7E98C075b` |

CollateralGuard passed the live runner's `getContractSchemaForCode` check before deploying, and **the code on-chain is byte-identical to this repo**: `cd studio-next && npx tsx verify_code.ts <address> collateral_guard_studio_next.py` fetches it with `gen_getContractCode` and compares.

| Contract | SHA-256 on-chain = SHA-256 of the repo file |
|---|---|
| CollateralGuard / `contracts/collateral_guard_studio_next.py` | `f421faf1124ee70c8ff8fc22cdbfce1b5663bca8d576f715cd1fe70e99db4a35` |

## Live proof (2026-10-11)

Reproduce with `cd studio-next && npx tsx prove.ts <collateralguard> <delistwatch> <watches|baskets|check|borrow|read>`. Every row is from [`studio-next/live_proof.json`](studio-next/live_proof.json), written as it ran (it resumes where it stopped). "Agree" counts the validators that actively voted (Studio Next leaves the rest of the 5-seat committee idle). **All 26 transactions reached consensus with every voting validator agreeing**, including the ones the contract refused: a refusal is a decided outcome.

### 1. The markets: DelistWatch reads each exchange

DelistWatch already watched Bitcoin and STORJ on the exchanges it supports. This proof adds Ether on three of them (registration is permissionless and immutable), then asks DelistWatch for a fresh check of all eight markets, because the policy wants a check no older than a day. Each check is DelistWatch's validators reading the exchange's own market data and delisting announcements.

| Market | DelistWatch check | Verdict | What the exchange said |
|---|---|---|---|
| `binance-eth` | registered: [`0x0df3170c…`](https://explorer-studio-dev.genlayer.com/tx/0x0df3170cf82a873e237b1dd25c44d1c4bf4ce5aeff195f21f1ffb63f49116ea2) 3 agree | | ETH/USDT on Binance |
| `okx-eth` | registered: [`0x144848d7…`](https://explorer-studio-dev.genlayer.com/tx/0x144848d7329e7053666609be4aa1492e9bf9032428d2377ac8d95edfc7218ee0) 3 agree | | ETH/USDT on OKX |
| `kucoin-eth` | registered: [`0x9b43b63c…`](https://explorer-studio-dev.genlayer.com/tx/0x9b43b63cb29f8a05a83354729f9e3891a3b9af2524253cf828cdd40435d00c0a) 3 agree | | ETH/USDT on KuCoin |
| `binance-btc` | check 10: [`0x509d0f24…`](https://explorer-studio-dev.genlayer.com/tx/0x509d0f2474e7df77b0c799b9934e3541e89eb16203d2a11b6d5cd00b9571a15d) 3 agree | **TRADING** | trading, and no announced delisting names it |
| `okx-btc` | check 11: [`0xd912ccc6…`](https://explorer-studio-dev.genlayer.com/tx/0xd912ccc64d72219e43d107598a8c5ae97766590fe800c49d0dab4339b1938f08) 3 agree | **TRADING** | trading, and no announced delisting names it |
| `binance-eth` | check 12: [`0xb5ca763a…`](https://explorer-studio-dev.genlayer.com/tx/0xb5ca763a6dc294617b0cf1d281cb55495ea80c78b577e0192e461c755b42c7e9) 3 agree | **TRADING** | trading, and no announced delisting names it |
| `okx-eth` | check 13: [`0xbe6f2bdc…`](https://explorer-studio-dev.genlayer.com/tx/0xbe6f2bdc8b4da91b426ebf766aa6bf64ec5f985d4fa85beb517fe6afd133e361) 3 agree | **TRADING** | trading, and no announced delisting names it |
| `kucoin-eth` | check 14: [`0xb9a894fc…`](https://explorer-studio-dev.genlayer.com/tx/0xb9a894fc341ba87d8b090ee6a10ab892b3d48377b142e19696510fa268063da9) 3 agree | **TRADING** | trading, and no announced delisting names it |
| `binance-storj` | check 15: [`0x8f0540e4…`](https://explorer-studio-dev.genlayer.com/tx/0x8f0540e48b29ea18ef7c7bc3aa361f24d4b37294d008a2ffff9206ca4e98a0c5) 3 agree | **NOT_TRADING** | market_not_trading:status=BREAK |
| `okx-storj` | check 16: [`0xb0133b2c…`](https://explorer-studio-dev.genlayer.com/tx/0xb0133b2c302603bb93221cee23ff2de59b43ea05495409c21119847408acf33a) 3 agree | **NOT_TRADING** | market_not_listed:Instrument ID doesn't exist |
| `kucoin-storj` | check 17: [`0x971b5cd4…`](https://explorer-studio-dev.genlayer.com/tx/0x971b5cd4efdd3d34fa16a574b75caecdffdd87e9c168d81b06f33e5d5e81a2bc) 3 agree | **TRADING** | trading, and no announced delisting names it |

### 2. Baskets, and what the policy refuses to create

A basket is one token across up to five of DelistWatch's markets. Creating one is owner-only; the policy checks each market against DelistWatch's own list.

| What it does | Call | Tx | Outcome |
|---|---|---|---|
| Bitcoin on two exchanges, both trading | `create_basket(btc-core, BTC, [binance-btc, okx-btc])` | [`0x66e2661d…`](https://explorer-studio-dev.genlayer.com/tx/0x66e2661dce4899314f6e81900225f0d9102491496ee10d0064521814e5044c4a) 3 agree | created |
| Ether on three exchanges, all trading | `create_basket(eth-core, ETH, [binance-eth, okx-eth, kucoin-eth])` | [`0x978e2669…`](https://explorer-studio-dev.genlayer.com/tx/0x978e2669d8b48a7bab94a68d837ded4741c8c9dfb63dcc63b6006423b458a77e) 3 agree | created |
| STORJ delisted on Binance and OKX, still trading on KuCoin: one venue in three | `create_basket(storj-mixed, STORJ, [binance-storj, okx-storj, kucoin-storj])` | [`0x9527bf44…`](https://explorer-studio-dev.genlayer.com/tx/0x9527bf4430a106fb862ea2eb5c0ff4a71cf54a5d740167dcc22c116172079c04) 3 agree | created |
| STORJ on the two exchanges that delisted it: nothing left | `create_basket(storj-gone, STORJ, [binance-storj, okx-storj])` | [`0x54eb68be…`](https://explorer-studio-dev.genlayer.com/tx/0x54eb68beb6526f105ea1de20680c5d8511851dfe415ce2c353b5c20a0ac52cc8) 3 agree | created |
| a basket id used twice | `create_basket(btc-core, BTC, [binance-btc])` | [`0x60aeeb2c…`](https://explorer-studio-dev.genlayer.com/tx/0x60aeeb2cb34e531b7aa6c2516f0d3d9096b7f140269872d93c318a45f0a6aca1) 3 agree | refused: `basket_id already exists` |
| a STORJ market inside a BTC basket | `create_basket(x-wrong, BTC, [binance-btc, binance-storj])` | [`0x57d5b02f…`](https://explorer-studio-dev.genlayer.com/tx/0x57d5b02fdbdbd6818f0eb2d0da1e5dc327fb6b0818b3096481a843a8dc583be8) 3 agree | refused: `'binance-storj' refused: it watches STORJ, not BTC` |
| a market DelistWatch has never heard of | `create_basket(x-unknown, BTC, [binance-doge])` | [`0x978ba1e4…`](https://explorer-studio-dev.genlayer.com/tx/0x978ba1e420b4d82e81d410fe743a9f31199d1fd197986d91a7c394e1eec5f2fd) 3 agree | refused: `'binance-doge' refused: DelistWatch has no such watch` |
| the same market listed twice | `create_basket(x-dup, BTC, [binance-btc, binance-btc])` | [`0x68059039…`](https://explorer-studio-dev.genlayer.com/tx/0x680590397f98b319b27c18fa24d48a8da3ad0a8d14f193b30f1c96490b2b8b1d) 3 agree | refused: `a venue can only be in a basket once` |

### 3. What each basket allows, read from the markets above

| Basket | Venues now | Coverage | Loan-to-value |
|---|---|---|---|
| `btc-core` (BTC) | binance trading (100%), okx trading (100%) | 100% | **60%** of 60% base |
| `eth-core` (ETH) | binance trading (100%), okx trading (100%), kucoin trading (100%) | 100% | **60%** of 60% base |
| `storj-mixed` (STORJ) | binance out (0%), okx out (0%), kucoin trading (100%) | 33% | **24%** of 60% base |
| `storj-gone` (STORJ) | binance out (0%), okx out (0%) | 0% | **0%** of 60% base |

### 4. Loans: at the limit, over it, and against nothing

Anyone can borrow; the limit is read from DelistWatch at the moment of the call. `max_borrow` is the same sum as a read.

| What it shows | Call | Outcome | Tx |
|---|---|---|---|
| full coverage: 60% loan-to-value, so up to 600,000 against 1,000,000 | `borrow(btc-core, 1,000,000, 500,000)` | **recorded** (`max_borrow` said 600,000) | [`0x3e082963…`](https://explorer-studio-dev.genlayer.com/tx/0x3e08296318d38d6304a3b6a8bb28f7e02d9721ea1498521b64f67b950082748d) 3 agree |
| more than the limit: refused, with the limit stated | `borrow(btc-core, 1,000,000, 700,000)` | refused: `'btc-core' refused: 60% loan-to-value at 100% coverage allows 600000 against 1000000` (`max_borrow` said 600,000) | [`0x1e89a70c…`](https://explorer-studio-dev.genlayer.com/tx/0x1e89a70c543e793dedeea74c862f95cc9dd8e1984c80b140c721c92b15596a0d) 3 agree |
| exactly at the limit (60% of 2,000,000): allowed | `borrow(eth-core, 2,000,000, 1,200,000)` | **recorded** (`max_borrow` said 1,200,000) | [`0x2ea9842a…`](https://explorer-studio-dev.genlayer.com/tx/0x2ea9842ad1cde0a67049e9bea2984dd5b040351eab72f7a37b8fddc5229caaa1) 3 agree |
| one venue in three trades: coverage 33%, so 40% of the 60%: up to 240,000 | `borrow(storj-mixed, 1,000,000, 200,000)` | **recorded** (`max_borrow` said 240,000) | [`0x1ad57020…`](https://explorer-studio-dev.genlayer.com/tx/0x1ad5702006b61fed0d78e36bbe944a523772d3550891302b7969cb0c1541762a) 3 agree |
| above that reduced limit: refused | `borrow(storj-mixed, 1,000,000, 300,000)` | refused: `'storj-mixed' refused: 24% loan-to-value at 33% coverage allows 240000 against 1000000` (`max_borrow` said 240,000) | [`0x55c26be1…`](https://explorer-studio-dev.genlayer.com/tx/0x55c26be14e7afca374bc2a6dbd112c53409ad22cd1c1f2a1806db5737b0088ae) 3 agree |
| coverage 0%: no loans at all | `borrow(storj-gone, 1,000,000, 1)` | refused: `'storj-gone' refused: coverage of STORJ is 0%, which allows no loans` (`max_borrow` said 0) | [`0x770a6c38…`](https://explorer-studio-dev.genlayer.com/tx/0x770a6c38171984c951c44bc8c29a9ccddfc33daa735d230180d1f09703c18525) 3 agree |
| a basket that does not exist | `borrow(no-such-basket, 1,000,000, 1)` | refused: `unknown basket_id` | [`0x41b328f4…`](https://explorer-studio-dev.genlayer.com/tx/0x41b328f457a01a13445602f0db418c8ab59336eb0a86c32e14c99933dc826fc1) 3 agree |

After the run `get_config()` reports 4 baskets and 3 loans; each loan record keeps the loan-to-value and coverage it was made under (`get_loans()`).

## What the live run found

- **One venue's delisting is not the token's.** STORJ has been delisted on Binance (the exchange's market data says `status=BREAK`) and on OKX (`Instrument ID doesn't exist`), and still trades on KuCoin. The same token, in three baskets of the same shape, got three different answers: ETH on three exchanges, all trading, 100% coverage and the full 60% loan-to-value; STORJ across all three, 33% coverage and 24%; STORJ across only the two exchanges that delisted it, 0% and no loans.
- **The limit is read at the moment of the loan, from DelistWatch's own record.** Borrowing 500,000 against 1,000,000 of Bitcoin was recorded; 700,000 was refused with the limit in the message (`allows 600000 against 1000000`). The STORJ loan of 200,000 was recorded under the 24% limit and 300,000 was refused under it. `max_borrow` told the same numbers before any loan was sent.
- **Borrowing is permissionless, and the policy does not need to know the borrower.** The limit comes from DelistWatch's record of the exchanges, not from anything the borrower supplies except the basket, the collateral value and the amount. (The loans in this proof were sent by the deployer; the web app lets any account borrow.)
- **Nothing here was a trade or a custody.** The policy records loans and limits; no tokens moved, and its numbers are units of account, as in the proof's 1,000,000-unit collateral.

## Superseded deployments

| Contract | Address | Why it is superseded |
|---|---|---|
| CollateralGuard (trial instance) | `0x585F7cb9561683b9AA079ac77cD831Afc724135a` | Same code (byte-identical), deployed for a trial run. Replaced by a clean deployment so every row of the live proof starts from empty. |

## Proven in tests, not live

Direct Mode proves these on DelistWatch's real check records (captured from the live contract, `tests/fixtures/`) and on edited copies of them; none has a live transaction:

- **The countdown.** A delisting announced for a known date counts 75% with 30 or more days to go, 50% from 14, 25% from 7 and 0 inside a week, in calendar days in UTC; an announced delisting whose date is unreadable counts 0. No exchange had announced a future spot delisting of a watched token on the day of the proof (their notices give days, not weeks), so a live row would have reached only the 25% or 0% step.
- **A stale check** (older than the limit, or dated in the future) and **no check at all** count 0, as does an `UNDETERMINED` check or an unknown verdict.
- **Coverage and the ladder**: the average rounds down, the ladder rounds down, a ladder can end in a rung that allows something at any coverage, and an invalid ladder or configuration is refused at deployment.
- Every owner-only check, an invalid basket id or token, a zero loan, and an unknown basket, which are decided before any cross-contract call. The calls that read DelistWatch (`create_basket`, `borrow`, `get_status`, `max_borrow`) cannot be simulated in Direct Mode and are proven by the live tables above.
