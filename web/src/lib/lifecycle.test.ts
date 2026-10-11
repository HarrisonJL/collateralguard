import { describe, expect, it } from "vitest";
import { classify } from "./lifecycle";
import { errorText } from "./genlayer";

// The guarantees a reviewer checks first: only ACCEPTED / FINALIZED are success,
// and a call the contract rejected is never shown as one, whatever the consensus status says.
describe("classify", () => {
  it("accepts ACCEPTED (5) and FINALIZED (7)", () => {
    expect(classify({ status: 5 }, "x").ok).toBe(true);
    expect(classify({ status: "7" }, "x").ok).toBe(true);
  });

  it.each([[6, "UNDETERMINED"], [8, "CANCELED"], [12, "VALIDATORS_TIMEOUT"], [13, "LEADER_TIMEOUT"], [1, "PENDING"]])(
    "does not accept status %s (%s)", (status) => {
      const out = classify({ status }, "x");
      expect(out.ok).toBe(false);
      if (!out.ok) expect(out.kind).toBe("consensus");
    });

  it("a contract rejection is a rejection even when consensus accepted it", () => {
    const tx = { status: 5, txExecutionResultName: "FINISHED_WITH_ERROR", result: "basket_id already exists" };
    const out = classify(tx, "fallback hint");
    expect(out.ok).toBe(false);
    if (!out.ok) {
      expect(out.kind).toBe("rejected");
      expect(out.message).toContain("already exists");
    }
  });

  // The refusals the contract produces (the live proof records them in CONTRACT.md), kept whole including percentages and punctuation.
  it.each([
    "'btc-core' refused: 60% loan-to-value at 100% coverage allows 600000 against 1000000",
    "'storj-gone' refused: coverage of STORJ is 0%, which allows no loans",
    "'binance-storj' refused: it watches STORJ, not BTC",
    "'binance-doge' refused: DelistWatch has no such watch",
    "basket_id already exists",
    "unknown basket_id",
    "a venue can only be in a basket once",
    "only the owner can create a basket",
  ])("keeps the policy's own refusal whole: %s", (reason) => {
    const out = classify({ status: 5, txExecutionResultName: "FINISHED_WITH_ERROR", result: reason }, "hint");
    expect(out.ok).toBe(false);
    if (!out.ok) expect(out.message).toContain(reason);
  });

  it("falls back to the hint when the revert text is not found", () => {
    const out = classify({ status: 7, txExecutionResultName: "FINISHED_WITH_ERROR" }, "the contract refused it");
    expect(out.ok).toBe(false);
    if (!out.ok) expect(out.message).toContain("the contract refused it");
  });
});

describe("errorText", () => {
  it("surfaces a 429 buried in viem's cause chain instead of 'unknown RPC error'", () => {
    const err = Object.assign(new Error("An unknown RPC error occurred."), {
      name: "UnknownRpcError", details: "Rate limit exceeded: 30 requests per minute",
      cause: { code: -32029, message: "Rate limit exceeded: 30 requests per minute" },
    });
    const text = errorText(err);
    expect(text).toMatch(/Rate limit exceeded/);
    expect(text).not.toMatch(/unknown RPC error/);
  });

  it("falls back to the plain message", () => {
    expect(errorText(new Error("boom"))).toBe("boom");
  });
});
