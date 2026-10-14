// Confirms the DelistWatch source included in this repository (dependencies/delistwatch) is byte-identical to the
// code deployed on Studio Next at the address CollateralGuard reads, fetched straight from the chain.
//
//   npx tsx verify_dependency.ts [address]
import * as crypto from "crypto";
import * as fs from "fs";
import { readClient } from "./lib";

const ADDRESS = "0x1AFffBad8fCfBEFD9494fd8994118f586B85DAFc";
const FILE = "../dependencies/delistwatch/contracts/delist_watch_studio_next.py";

async function main() {
  const address = process.argv[2] ?? ADDRESS;
  let onchain: any = await readClient().getContractCode(address);
  if (typeof onchain !== "string") onchain = Buffer.from(onchain).toString("utf-8");
  const local = fs.readFileSync(FILE, "utf-8");
  const sha = (s: string) => crypto.createHash("sha256").update(s).digest("hex");
  console.log(`on-chain  sha256 ${sha(onchain)} (${onchain.length} chars) at ${address}`);
  console.log(`vendored  sha256 ${sha(local)} (${local.length} chars)`);
  console.log(onchain === local ? "IDENTICAL" : "DIFFERENT");
  process.exit(onchain === local ? 0 : 1);
}
main().catch((e) => {
  console.error(e?.shortMessage ?? e?.message ?? e);
  process.exit(1);
});
