# v0.1.0
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

# CollateralGuard - a lending policy over exchange liquidity, built on
# DelistWatch's verdicts. A lender that accepts a token as collateral depends on
# being able to sell it, and one exchange's delisting is a different risk from
# the token being unsellable anywhere. DelistWatch says, for one token on one
# exchange, whether its spot market is trading, has an announced end, or is not
# trading; CollateralGuard groups the same token across exchanges into a BASKET
# and turns the venues' verdicts into a loan-to-value limit:
#
#   - Each venue is weighted by its latest DelistWatch check: 100% if trading,
#     less and less as a delisting announced for a known date approaches (75%
#     with 30 or more days to go, 50% from 14, 25% from 7, 0 inside a week),
#     and 0 if the market is not trading, the check is undetermined, or the
#     check is missing or stale.
#   - The basket's coverage is the average weight of its venues. A ladder set
#     at deployment turns coverage into a share of the base loan-to-value
#     ratio (for example full coverage 100%, two thirds 70%, one third 40%,
#     less than that nothing).
#   - borrow() records a loan only up to collateral value x that limit, read
#     from DelistWatch at the moment of the loan.
#
# Every rule is a pure function of DelistWatch's own check records, so it is
# tested on the real checks; the cross-contract reads are proven live.
#
# GenVM v0.2.11 conventions (locally tested source of truth);
# contracts/collateral_guard_studio_next.py is the deployed port.
# Header must end in a blank line (real GenVM v0.2.11 requirement).

from genlayer import *
import datetime
import json
import re

BPS = 10000
# Days left before an announced delisting takes effect -> the share of a venue still counted.
COUNTDOWN = ((30, 75), (14, 50), (7, 25))
MAX_VENUES = 5
MAX_PAGE_LIMIT = 50


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise gl.vm.UserError(message)


def _now() -> datetime.datetime:
    return datetime.datetime.fromisoformat(gl.message_raw['datetime'])


def _seconds(iso: str) -> int:
    return int(datetime.datetime.fromisoformat(iso).timestamp())


def _venue(check: dict, now_seconds: int, max_age: int) -> dict:
    """One venue's standing from DelistWatch's latest check: {state, weight_pct, days_left, reason}."""
    verdict = check.get("verdict", "NONE")
    if verdict == "NONE":
        return {"state": "NO_CHECK", "weight_pct": 0, "days_left": None, "reason": "DelistWatch has no check of this market"}
    age = now_seconds - _seconds(check["checked_at"])
    if not 0 <= age <= max_age:
        return {"state": "STALE", "weight_pct": 0, "days_left": None,
                "reason": f"the latest check is {age} seconds old; this policy wants at most {max_age}"}
    if verdict == "TRADING":
        return {"state": "TRADING", "weight_pct": 100, "days_left": None, "reason": "the spot market is trading, with no announced end"}
    if verdict == "NOT_TRADING":
        return {"state": "OUT", "weight_pct": 0, "days_left": None, "reason": "the exchange's own data says the market is not trading"}
    if verdict == "DELISTING_ANNOUNCED":
        effective = check.get("effective_date", "")
        try:
            on = datetime.date.fromisoformat(effective) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", effective) else None
        except (ValueError, TypeError):
            on = None
        if on is None:
            return {"state": "DELISTING", "weight_pct": 0, "days_left": None, "reason": "a delisting is announced and its date is unreadable"}
        today = datetime.datetime.fromtimestamp(now_seconds, datetime.timezone.utc).date()
        days = (on - today).days
        weight = 0
        for threshold, share in COUNTDOWN:
            if days >= threshold:
                weight = share
                break
        return {"state": "DELISTING", "weight_pct": weight, "days_left": days,
                "reason": f"a delisting takes effect on {effective}, {days} days from now"}
    return {"state": "UNKNOWN", "weight_pct": 0, "days_left": None, "reason": f"the latest check is {verdict}"}


def _coverage(weights: list) -> int:
    """The basket's coverage: the average weight of its venues (whole percent)."""
    return sum(weights) // len(weights) if weights else 0


def _ltv_bps(base_ltv_bps: int, coverage_pct: int, ladder: list) -> int:
    """The loan-to-value limit: the base ratio times the share of the first ladder rung the coverage reaches."""
    for minimum, share in ladder:
        if coverage_pct >= minimum:
            return base_ltv_bps * share // 100
    return 0


def _max_borrow(collateral_value: int, ltv_bps: int) -> int:
    return collateral_value * ltv_bps // BPS


def _ladder(raw: str) -> list:
    """The coverage ladder, JSON [[min coverage %, share of the base ratio %], ...], strictly descending."""
    try:
        ladder = json.loads(raw)
    except ValueError:
        _require(False, "ladder must be JSON, e.g. [[100, 100], [66, 70], [33, 40]]")
    _require(isinstance(ladder, list) and 1 <= len(ladder) <= 8
             and all(isinstance(r, list) and len(r) == 2 and all(isinstance(v, int) and not isinstance(v, bool) for v in r)
                     and 0 <= r[0] <= 100 and 0 <= r[1] <= 100 for r in ladder),
             "ladder must be 1-8 pairs of whole percentages between 0 and 100")
    _require(all(ladder[i][0] > ladder[i + 1][0] for i in range(len(ladder) - 1)),
             "ladder's minimum coverages must be strictly descending")
    _require(all(ladder[i][1] >= ladder[i + 1][1] for i in range(len(ladder) - 1)),
             "ladder's shares must not rise as coverage falls")
    return ladder


@allow_storage
class Basket:
    token: str
    venues_json: str  # [[watch_id, exchange, quote], ...] as DelistWatch recorded them
    created_by: Address
    created_at: datetime.datetime
    borrowed: u256


@allow_storage
class Loan:
    basket_id: str
    borrower: Address
    collateral_value: u256
    amount: u256
    ltv_bps: u32
    coverage_pct: u32
    recorded_at: datetime.datetime


class CollateralGuard(gl.Contract):
    owner: Address
    delistwatch_address: Address
    max_age_seconds: u32
    base_ltv_bps: u32
    ladder_json: str
    baskets: TreeMap[str, Basket]
    loans: DynArray[Loan]

    def __init__(self, delistwatch_address: str, max_age_seconds: u32, base_ltv_bps: u32, ladder_json: str) -> None:
        _require(max_age_seconds > 0, "max_age_seconds must be positive")
        _require(0 < base_ltv_bps <= BPS, "base_ltv_bps must be between 1 and 10000")
        _ladder(ladder_json)
        self.owner = gl.message.sender_address
        self.delistwatch_address = Address(delistwatch_address)
        self.max_age_seconds = max_age_seconds
        self.base_ltv_bps = base_ltv_bps
        self.ladder_json = ladder_json

    def _venues(self, basket: Basket) -> list:
        """Each venue's standing right now, from DelistWatch's latest checks."""
        watch = gl.get_contract_at(self.delistwatch_address)
        now = int(_now().timestamp())
        out = []
        for watch_id, exchange, quote in json.loads(basket.venues_json):
            check = watch.view().latest_check(watch_id)
            v = _venue(check, now, self.max_age_seconds)
            out.append(dict(v, watch_id=watch_id, exchange=exchange, quote=quote, verdict=check["verdict"],
                            check_id=check.get("check_id"), checked_at=check.get("checked_at", ""),
                            age_seconds=(now - _seconds(check["checked_at"])) if "checked_at" in check else None))
        return out

    def _limit(self, venues: list) -> dict:
        coverage = _coverage([v["weight_pct"] for v in venues])
        return {"coverage_pct": coverage, "ltv_bps": _ltv_bps(int(self.base_ltv_bps), coverage, json.loads(self.ladder_json))}

    # Owner only: a basket is the same token on up to five venues, each a DelistWatch watch for that token.
    @gl.public.write
    def create_basket(self, basket_id: str, token: str, watch_ids: list) -> None:
        _require(gl.message.sender_address == self.owner, "only the owner can create a basket")
        _require(re.fullmatch(r"[A-Za-z0-9_-]{1,32}", basket_id) is not None,
                 "basket_id must be 1-32 characters of A-Z, a-z, 0-9, _ or -")
        _require(basket_id not in self.baskets, "basket_id already exists")
        _require(re.fullmatch(r"[A-Z0-9]{1,15}", token) is not None, "token must be 1-15 characters of A-Z or 0-9")
        _require(1 <= len(watch_ids) <= MAX_VENUES, f"a basket holds 1-{MAX_VENUES} venues")
        _require(len(set(watch_ids)) == len(watch_ids), "a venue can only be in a basket once")
        known = {w["watch_id"]: w for w in gl.get_contract_at(self.delistwatch_address).view().list_watches()}
        venues = []
        for watch_id in watch_ids:
            _require(watch_id in known, f"{watch_id!r} refused: DelistWatch has no such watch")
            w = known[watch_id]
            _require(w["base"] == token, f"{watch_id!r} refused: it watches {w['base']}, not {token}")
            venues.append([watch_id, w["exchange"], w["quote"]])
        b = self.baskets.get_or_insert_default(basket_id)
        b.token = token
        b.venues_json = json.dumps(venues)
        b.created_by = gl.message.sender_address
        b.created_at = _now()
        b.borrowed = u256(0)

    # Any borrower. The limit is read from DelistWatch now, so a venue that has since stopped trading,
    # announced a delisting or gone unchecked lowers it.
    @gl.public.write
    def borrow(self, basket_id: str, collateral_value: u256, amount: u256) -> None:
        _require(amount > 0, "amount must be positive")
        _require(basket_id in self.baskets, "unknown basket_id")
        b = self.baskets[basket_id]
        venues = self._venues(b)
        limit = self._limit(venues)
        _require(limit["ltv_bps"] > 0,
                 f"{basket_id!r} refused: coverage of {b.token} is {limit['coverage_pct']}%, which allows no loans")
        maximum = _max_borrow(int(collateral_value), limit["ltv_bps"])
        _require(int(amount) <= maximum,
                 f"{basket_id!r} refused: {limit['ltv_bps'] / 100:g}% loan-to-value at {limit['coverage_pct']}% coverage "
                 f"allows {maximum} against {collateral_value}")
        loan = self.loans.append_new_get()
        loan.basket_id = basket_id
        loan.borrower = gl.message.sender_address
        loan.collateral_value = collateral_value
        loan.amount = amount
        loan.ltv_bps = u32(limit["ltv_bps"])
        loan.coverage_pct = u32(limit["coverage_pct"])
        loan.recorded_at = _now()
        b.borrowed = u256(int(b.borrowed) + int(amount))

    # --- Views -----------------------------------------------------------------

    # The policy's answer for a basket, from DelistWatch's latest checks as of right now.
    @gl.public.view
    def get_status(self, basket_id: str) -> dict:
        _require(basket_id in self.baskets, "unknown basket_id")
        b = self.baskets[basket_id]
        venues = self._venues(b)
        limit = self._limit(venues)
        return {"basket_id": basket_id, "token": b.token, "venues": venues, "coverage_pct": limit["coverage_pct"],
                "ltv_bps": limit["ltv_bps"], "base_ltv_bps": self.base_ltv_bps, "borrowed": str(b.borrowed),
                "created_at": b.created_at.isoformat()}

    # What a borrower may take against this collateral, right now.
    @gl.public.view
    def max_borrow(self, basket_id: str, collateral_value: u256) -> dict:
        _require(basket_id in self.baskets, "unknown basket_id")
        limit = self._limit(self._venues(self.baskets[basket_id]))
        return {"basket_id": basket_id, "collateral_value": str(collateral_value), "ltv_bps": limit["ltv_bps"],
                "coverage_pct": limit["coverage_pct"], "max_borrow": str(_max_borrow(int(collateral_value), limit["ltv_bps"]))}

    @gl.public.view
    def list_baskets(self) -> list:
        return [{"basket_id": k, "token": b.token, "venues": json.loads(b.venues_json), "borrowed": str(b.borrowed)}
                for k, b in self.baskets.items()]

    @gl.public.view
    def get_loans(self, offset: u32, limit: u32) -> list:
        limit = min(limit, MAX_PAGE_LIMIT)
        out = []
        i = len(self.loans) - 1 - offset
        while i >= 0 and len(out) < limit:
            ln = self.loans[i]
            out.append({"loan_id": i, "basket_id": ln.basket_id, "borrower": ln.borrower.as_hex,
                        "collateral_value": str(ln.collateral_value), "amount": str(ln.amount), "ltv_bps": ln.ltv_bps,
                        "coverage_pct": ln.coverage_pct, "recorded_at": ln.recorded_at.isoformat()})
            i -= 1
        return out

    @gl.public.view
    def get_config(self) -> dict:
        return {"owner": self.owner.as_hex, "delistwatch_address": self.delistwatch_address.as_hex,
                "max_age_seconds": self.max_age_seconds, "base_ltv_bps": self.base_ltv_bps,
                "ladder": json.loads(self.ladder_json), "basket_count": len(self.baskets), "loan_count": len(self.loans)}

    @gl.public.view
    def get_rules(self) -> dict:
        return {"max_age_seconds": self.max_age_seconds, "base_ltv_bps": self.base_ltv_bps,
                "coverage_ladder": json.loads(self.ladder_json),
                "countdown": [{"days_at_least": d, "venue_share_pct": s} for d, s in COUNTDOWN],
                "venue_states": {"TRADING": 100, "DELISTING": "by countdown", "OUT": 0, "STALE": 0, "NO_CHECK": 0, "UNKNOWN": 0}}
