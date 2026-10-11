import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { GUARD_SOURCE, amountProblem, basketProblem, deployedAddress, isOwner, maxBorrowFor, same, toUnits } from "./guard";

// The desk a visitor creates must run exactly the code the official policy runs.
const DEPLOYED_SHA256 = "f421faf1124ee70c8ff8fc22cdbfce1b5663bca8d576f715cd1fe70e99db4a35";
const sha = (s: string) => createHash("sha256").update(s).digest("hex");

describe("the contract the app deploys", () => {
  it("is byte-identical to the code on-chain at the official policy (CONTRACT.md)", () => {
    expect(sha(GUARD_SOURCE)).toBe(DEPLOYED_SHA256);
  });
  it("is byte-identical to contracts/collateral_guard_studio_next.py when this app is built inside the repository", () => {
    const repoCopy = new URL("../../../contracts/collateral_guard_studio_next.py", import.meta.url);
    if (!existsSync(repoCopy)) return; // built from web/ alone (e.g. a hosting root): the hash above is the check
    expect(readFileSync(repoCopy, "utf-8")).toBe(GUARD_SOURCE);
  });
});

describe("the limit sum mirrors the contract", () => {
  // collateral value x loan-to-value in basis points / 10000, rounded down: the contract's own integer division.
  it.each([
    [1000000n, 6000, 600000n], [1000000n, 2400, 240000n], [2000000n, 6000, 1200000n], [1n, 6000, 0n], [999n, 2400, 239n], [1000000n, 0, 0n],
  ])("%s at %s bps allows %s", (collateral, bps, expected) => {
    expect(maxBorrowFor(collateral, bps)).toBe(expected);
  });
});

describe("input checks mirror the contract", () => {
  it("an amount is a positive whole number", () => {
    for (const bad of ["", "0", "-5", "1.5", "abc", "1e6", " "]) expect(amountProblem(bad)).not.toBe("");
    expect(amountProblem("250,000")).toBe("");
    expect(toUnits("1,500,000")).toBe(1500000n);
    expect(typeof toUnits("5")).toBe("bigint"); // u256 arguments must be BigInt
  });
  it("a basket id, a token and 1-5 markets", () => {
    expect(basketProblem("my-basket", "BTC", ["a"], [])).toBe("");
    expect(basketProblem("bad id", "BTC", ["a"], [])).not.toBe("");
    expect(basketProblem("x".repeat(33), "BTC", ["a"], [])).not.toBe("");
    expect(basketProblem("my-basket", "BTC", ["a"], ["my-basket"])).not.toBe("");
    expect(basketProblem("my-basket", "btc", ["a"], [])).not.toBe("");
    expect(basketProblem("my-basket", "BTC", [], [])).not.toBe("");
    expect(basketProblem("my-basket", "BTC", ["a", "b", "c", "d", "e", "f"], [])).not.toBe("");
  });
});

describe("owner and address handling", () => {
  it("compares addresses without regard to case, and is the owner only when the signer is", () => {
    expect(same("0xAbC", "0xaBc")).toBe(true);
    const data: any = { config: { owner: "0x5cdb5699bc1038e115A973bb91A646f7E98C075b" } };
    expect(isOwner({ kind: "temporary", address: "0x5CDB5699BC1038E115A973BB91A646F7E98C075B" }, data)).toBe(true);
    expect(isOwner({ kind: "temporary", address: "0x0000000000000000000000000000000000000001" }, data)).toBe(false);
    expect(isOwner(null, data)).toBe(false);
  });
  it("reads a deployed contract's address from the transaction, or refuses to guess", () => {
    const a = "0x31c89cA668Cf19E1dA583f983d77d4848b25522B";
    expect(deployedAddress({ to_address: a })).toBe(a);
    expect(() => deployedAddress({})).toThrow();
    expect(() => deployedAddress({ to_address: "0x123" })).toThrow();
  });
});
