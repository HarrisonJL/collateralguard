import { view, type Signer } from "./genlayer";
import GUARD_CODE from "./collateral_guard_studio_next.py?raw";

// The official policy (the deployment proven in CONTRACT.md) and the DelistWatch oracle it reads.
export const GUARD = "0x1b0C8D779D58DFD67CF491840A8b081094d53e8C";
export const DELISTWATCH = "0x1AFffBad8fCfBEFD9494fd8994118f586B85DAFc";

/** The audited contract source, byte-identical to contracts/collateral_guard_studio_next.py (a test enforces it). */
export const GUARD_SOURCE: string = GUARD_CODE;
/** What a visitor's own desk is constructed with: the same oracle, a day's freshness, 60% base loan-to-value, the same ladder. */
export const DESK_ARGS = [DELISTWATCH, 86400, 6000, "[[100,100],[66,70],[33,40]]"] as const;

export const STATE_NAME: Record<string, string> = {
  TRADING: "Trading", DELISTING: "Delisting announced", OUT: "Not trading", STALE: "Stale check", NO_CHECK: "No check", UNKNOWN: "Unknown",
};
export const STATE_TONE: Record<string, "ok" | "warn" | "bad" | "none" | "info"> = {
  TRADING: "ok", DELISTING: "warn", OUT: "bad", STALE: "none", NO_CHECK: "none", UNKNOWN: "none",
};
export const STATE_RULE: Record<string, string> = {
  TRADING: "The exchange's own market data says the pair is trading, and no delisting announcement it published ends it.",
  DELISTING: "Still trading, but the exchange announced an end date. The share counted shrinks as that date approaches.",
  OUT: "The exchange's own data says the pair is halted, suspended or not listed.",
  STALE: "DelistWatch's latest check is older than this policy accepts. Ask for a fresh one.",
  NO_CHECK: "DelistWatch has never checked this market.",
  UNKNOWN: "A verdict this policy does not know, or one DelistWatch could not settle.",
};

export type Venue = {
  watch_id: string; exchange: string; quote: string; state: string; weight_pct: number; days_left: number | null; reason: string;
  verdict: string; check_id: number | null; checked_at: string; age_seconds: number | null;
};
export type BasketStatus = {
  basket_id: string; token: string; venues: Venue[]; coverage_pct: number; ltv_bps: number; base_ltv_bps: number; borrowed: string; created_at: string;
};
export type Config = {
  owner: string; delistwatch_address: string; max_age_seconds: number; base_ltv_bps: number; ladder: number[][]; basket_count: number; loan_count: number;
};
export type Rules = {
  max_age_seconds: number; base_ltv_bps: number; coverage_ladder: number[][];
  countdown: Array<{ days_at_least: number; venue_share_pct: number }>; venue_states: Record<string, number | string>;
};
export type Loan = {
  loan_id: number; basket_id: string; borrower: string; collateral_value: string; amount: string; ltv_bps: number; coverage_pct: number; recorded_at: string;
};
export type Watch = { watch_id: string; exchange: string; base: string; quote: string; label: string; check_count: number };
export type GuardData = {
  address: string; config: Config; rules: Rules; baskets: BasketStatus[]; loans: Loan[]; watches: Watch[]; loadedAt: Date;
};

export const same = (a: string, b: string) => a.toLowerCase() === b.toLowerCase();
export const isOwner = (signer: Signer | null, data: GuardData | null) => !!signer && !!data && same(signer.address, data.config.owner);

// --- Reads ---------------------------------------------------------------------

const CACHE = "collateralguard-cache-v1:";
type Cached = Omit<GuardData, "loadedAt"> & { loadedAt: string };
export function cachedGuard(address: string): GuardData | null {
  try {
    const c = JSON.parse(localStorage.getItem(CACHE + address.toLowerCase()) ?? "null") as Cached | null;
    return c ? { ...c, loadedAt: new Date(c.loadedAt) } : null;
  } catch { return null; }
}

export async function loadGuard(address: string): Promise<GuardData> {
  const [config, rules, listed, loans, watches] = await Promise.all([
    view(address, "get_config") as Promise<Config>,
    view(address, "get_rules") as Promise<Rules>,
    view(address, "list_baskets") as Promise<Array<{ basket_id: string }>>,
    view(address, "get_loans", [0, 10]) as Promise<Loan[]>,
    view(DELISTWATCH, "list_watches") as Promise<Watch[]>,
  ]);
  const baskets: BasketStatus[] = [];
  for (const b of listed) baskets.push((await view(address, "get_status", [b.basket_id])) as BasketStatus);
  const data: GuardData = { address, config, rules, baskets, loans, watches, loadedAt: new Date() };
  try { localStorage.setItem(CACHE + address.toLowerCase(), JSON.stringify(data)); } catch { /* the cache is optional */ }
  return data;
}

/** DelistWatch's latest check of one market: the verdict, its reasons and, for a delisting, the quoted announcement. */
export type DelistCheck = {
  check_id: number; watch_id: string; verdict: string; reasons: string[]; effective_date: string; submitted_by: string; checked_at: string;
  reading: { evidence?: string; effective_date?: string } | null;
  facts: { announcements?: Array<{ title?: string; url?: string }>; as_of?: string };
};
export const loadDelistCheck = (watchId: string): Promise<DelistCheck> => view(DELISTWATCH, "latest_check", [watchId]);

/** What a borrower may take against this collateral, asked of the contract itself (a read). */
export const askMaxBorrow = (address: string, basketId: string, collateral: bigint): Promise<{ ltv_bps: number; coverage_pct: number; max_borrow: string }> =>
  view(address, "max_borrow", [basketId, collateral]);

// --- Desk storage: a visitor's own policy, deployed from their own account ----------------

const DESK = "collateralguard-desk";
export function savedDesk(): { address: string; owner: string } | null {
  try {
    const d = JSON.parse(localStorage.getItem(DESK) ?? "null");
    return d && /^0x[0-9a-fA-F]{40}$/.test(d.address) ? d : null;
  } catch { return null; }
}
export function saveDesk(d: { address: string; owner: string } | null): void {
  try { d ? localStorage.setItem(DESK, JSON.stringify(d)) : localStorage.removeItem(DESK); } catch { /* ignore */ }
}

/** The address a deploy transaction created. */
export function deployedAddress(tx: any): string {
  const a = tx?.to_address ?? tx?.recipient ?? tx?.data?.contract_address ?? tx?.txData?.contract_address;
  if (typeof a !== "string" || !/^0x[0-9a-fA-F]{40}$/.test(a)) throw new Error("the transaction did not report a contract address");
  return a;
}

// --- Validation and the limit, mirroring the contract so a refused call is not paid for -----

export const BPS = 10000n;
export const isId = (s: string) => /^[A-Za-z0-9_-]{1,32}$/.test(s);
export function amountProblem(raw: string): string {
  return /^[1-9][0-9]{0,30}$/.test(raw.trim().replace(/,/g, "")) ? "" : "Enter a positive whole number.";
}
export const toUnits = (raw: string): bigint => BigInt(raw.trim().replace(/,/g, ""));
/** collateral value x loan-to-value, whole units (the contract's own integer division). */
export const maxBorrowFor = (collateral: bigint, ltvBps: number): bigint => (collateral * BigInt(ltvBps)) / BPS;
export function basketProblem(id: string, token: string, watchIds: string[], existing: string[]): string {
  if (!isId(id)) return "A basket id is 1-32 characters of A-Z, a-z, 0-9, _ or -.";
  if (existing.includes(id)) return "That basket id is already used.";
  if (!/^[A-Z0-9]{1,15}$/.test(token)) return "Pick a token.";
  if (watchIds.length < 1 || watchIds.length > 5) return "A basket holds 1 to 5 markets.";
  return "";
}

// --- Binding a write to the record THIS transaction created --------------------------------

export async function delistCheckCount(): Promise<number> {
  return Number((await view(DELISTWATCH, "get_state")).check_count);
}
export async function boundCheck(before: number, signer: Signer, watchId: string): Promise<DelistCheck> {
  const c = await loadDelistCheck(watchId);
  if (!(Number(c.check_id) >= before)) throw new Error("no new check was recorded for this market");
  if (!same(c.submitted_by ?? "", signer.address)) throw new Error("the newest check was submitted by someone else");
  return c;
}
export async function boundLoan(guard: string, before: number, signer: Signer, basketId: string): Promise<Loan> {
  const list = (await view(guard, "get_loans", [0, 5])) as Loan[];
  const l = list.find((x) => x.loan_id >= before && x.basket_id === basketId && same(x.borrower, signer.address));
  if (!l) throw new Error("no new loan by this account was found");
  return l;
}
export async function boundBasket(guard: string, basketId: string): Promise<{ basket_id: string; token: string }> {
  const list = (await view(guard, "list_baskets")) as Array<{ basket_id: string; token: string }>;
  const b = list.find((x) => x.basket_id === basketId);
  if (!b) throw new Error("the basket was not created");
  return b;
}
