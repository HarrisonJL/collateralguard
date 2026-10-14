# Dependencies

CollateralGuard depends on exactly one contract, and its complete source is included here so the whole trust path can be reviewed inside this repository (see [`TRUST_PATH.md`](../TRUST_PATH.md)).

| | |
|---|---|
| Contract | **DelistWatch** |
| What it does for the policy | Every validator reads an exchange's own market data and delisting announcements for an exact pair; plain code decides whether the market trades, an LLM reads only the announcements that name the token (a delisting counts only with a verbatim quote and a stated date), and the validators must reach consensus. CollateralGuard reads the resulting record with a cross-contract view call. |
| Upstream | [github.com/HarrisonJL/delistwatch](https://github.com/HarrisonJL/delistwatch), commit `c4fddf0bac77fd13a8dad2cf1e1dd33d76f10bd2` |
| Included as | [`delistwatch/`](delistwatch/): every tracked file of that commit, none edited, except one left out: `studio-next/zz_audit.ts`, a stray audit helper that is not part of the contract, its tests or its proof (contracts, tests with their committed exchange responses, scripts, live-proof tooling, its README and CONTRACT.md, its MIT licence are all here) |
| Deployed at | [`0x1AFffBad8fCfBEFD9494fd8994118f586B85DAFc`](https://explorer-studio-dev.genlayer.com/address/0x1AFffBad8fCfBEFD9494fd8994118f586B85DAFc), deploy tx [`0x6ace2420…`](https://explorer-studio-dev.genlayer.com/tx/0x6ace2420cb9a57c6cbca4d8aae1553f757fd01347c64d3ad57881fd0517a1f04) |
| Deployed file | `delistwatch/contracts/delist_watch_studio_next.py`, SHA-256 `65450eb378d26236bad24241c096b4929d8a710b436bad154b65abbf5d17f77b`, byte-identical to the code on-chain |

## Verifying

```bash
# offline: the included file is the one recorded above, and the policy's assumptions about it hold
.venv/bin/pytest tests/test_trust_path.py -q

# against the chain: fetch the code deployed at that address and compare it with the included file
cd studio-next && npm ci && npx tsx verify_dependency.ts

# the dependency's own tests (82; its exchange responses are committed, so this runs offline)
cd dependencies/delistwatch && ../../.venv/bin/pytest tests -q
```

DelistWatch is MIT-licensed and was published earlier as a project of its own; including it here changes nothing about its licence.
