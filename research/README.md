# Research: what CollateralGuard reads, and what the live data showed

CollateralGuard has no data source of its own. Everything it knows comes from [DelistWatch](https://github.com/HarrisonJL/delistwatch), read as a **cross-contract view** at the moment of each call.

## What DelistWatch's check record offers

`latest_check(watch_id)` carries (fixtures: [`tests/fixtures/`](../tests/fixtures/), captured from the live contract):

- `verdict`: `TRADING`, `DELISTING_ANNOUNCED`, `NOT_TRADING`, `UNDETERMINED` (or `NONE` before any check);
- `effective_date`: for a delisting, the date the exchange's own announcement states, which DelistWatch's validators each verified against their own copy of the text;
- `checked_at`: the transaction time of the check, so a consumer can judge how old it is;
- `reasons` and `facts` (the market API's own words, and the announcements opened) and `reading` (the quoted evidence).

The policy uses only `verdict`, `effective_date` and `checked_at`. Every rule is a **pure function** of those fields (`_venue`, `_coverage`, `_ltv_bps`, `_max_borrow`), tested on the real records and on edited copies of them (the countdown tests change only the effective date of a real check). The calls that read DelistWatch are proven live.

## What the markets said on the day of the proof (11 October 2026)

DelistWatch's validators read the exchanges' own data (CONTRACT.md has every transaction):

- **BTC/USDT** on Binance and OKX, **ETH/USDT** on Binance, OKX and KuCoin: trading.
- **STORJ/USDT** on Binance: `status=BREAK` (the exchange's market data), consistent with the spot delisting Binance scheduled for 3 September. On OKX: `Instrument ID doesn't exist`, after the delisting OKX announced on 23 September for 3 October. On KuCoin: still trading (only STORJ *futures* were delisted there, in August).

So one token, STORJ, is simultaneously fully delisted on two exchanges and live on a third: the case a switch cannot express and a coverage ladder can.

The exchanges' delisting lists were also read directly that day (Binance catalogue 161, OKX `announcements-delistings`, KuCoin `delistings`): the newest **spot** removals were dated in the past (Binance 2 October, OKX 3 October, KuCoin 8 October). None announced a future spot delisting, so the countdown (75/50/25/0%) could not be exercised live. Real notices give days, not weeks (OKX's STORJ notice, 23 September for 3 October, gave ten), so in practice they reach the 25% and 0% steps.

## Design choices these facts drove

- **Average, not minimum.** A token trading on two of three exchanges is less exposed than one trading on one; the minimum would treat them the same. The ladder is the lender's caution.
- **Fresh or nothing.** An old check says what the market was; the policy counts it as 0% after its limit (a day here, a constructor argument).
- **Weights shrink with the countdown, in calendar days (UTC).** A delisting announced for a known date is a known risk that grows as the date approaches; one with an unreadable date counts 0.
- **Nothing is priced here.** DelistWatch says nothing about price or depth, so neither does the policy: the collateral value is an input.

## Things the live runs established

- A **view can read another contract's view** (`get_status` reads DelistWatch's `latest_check` for every venue), and so can a write (`borrow`, `create_basket`).
- Amounts are `u256` and must be passed as `BigInt` from genlayer-js; views return them as strings, because a view must never return a float or an integer too large for calldata.
- A **deployed contract can be created from a browser**, by a wallet or a throwaway account, from the contract source alone: the app's "Create my desk" does that, and the resulting on-chain code was compared byte for byte with the repository's port.
- The public RPC allows 30 reads a minute per client, which the app paces for itself (`web/src/lib/genlayer.ts`).
