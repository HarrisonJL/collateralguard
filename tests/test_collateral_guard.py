"""
Deterministic tests for CollateralGuard using genlayer-test's Direct Mode.

Every decision CollateralGuard makes is a pure function of DelistWatch's own
check records, so the inputs here are DelistWatch's real checks as they stand
on Studio Next (tests/fixtures/, captured 2026-10-11): KuCoin STORJ/USDT trading;
OKX and Binance STORJ/USDT not trading (both delisted STORJ); Binance and OKX
BTC/USDT trading. No exchange has a spot delisting announced for a future date
today, so the countdown is tested on the real KuCoin check with its verdict and
date changed - marked SYNTHETIC wherever it is used. Direct Mode can't simulate
a cross-contract call, so the reads of DelistWatch (create_basket, borrow,
get_status, max_borrow) are proven live; what is tested here is every rule they
apply, and everything that runs before them.

Four layers: a venue's standing, a basket's coverage and limit, the ladder's
configuration, and the contract's own checks.
"""

import copy
import datetime
import json
import pathlib
import sys

import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def _check(name):
    return json.loads((FIXTURES / f"check_{name}.json").read_text())


KUCOIN_STORJ = _check("kucoin-storj")      # TRADING
OKX_STORJ = _check("okx-storj")            # NOT_TRADING
BINANCE_STORJ = _check("binance-storj")    # NOT_TRADING
BINANCE_BTC = _check("binance-btc")        # TRADING
OKX_BTC = _check("okx-btc")                # TRADING
DW = "0x" + "88" * 20                       # never actually called in these tests
MAX_AGE = 3600
LADDER = [[100, 100], [66, 70], [33, 40]]
BASE = 6000


def _deploy(direct_vm, direct_deploy, owner, max_age=MAX_AGE, base=BASE, ladder=LADDER):
    direct_vm.sender = owner
    return direct_deploy("contracts/collateral_guard.py", DW, max_age, base, json.dumps(ladder))


@pytest.fixture
def mod(direct_vm, direct_deploy, direct_owner):
    """The loaded contract module itself, for its pure functions (Direct Mode allows one contract class per process)."""
    _deploy(direct_vm, direct_deploy, direct_owner)
    return sys.modules["_contract_collateral_guard"]


def _seconds(check):
    return int(datetime.datetime.fromisoformat(check["checked_at"]).timestamp())


def _venue(mod, check, after=60, max_age=MAX_AGE):
    return mod._venue(check, _seconds(check) + after, max_age)


def _delisting(effective_days: int, from_check=KUCOIN_STORJ, after=60):
    """SYNTHETIC: the real KuCoin check, announced for delisting `effective_days` days after the moment it is read at."""
    c = copy.deepcopy(from_check)
    at = datetime.datetime.fromtimestamp(_seconds(c) + after, datetime.timezone.utc)
    c["verdict"] = "DELISTING_ANNOUNCED"
    c["effective_date"] = (at.date() + datetime.timedelta(days=effective_days)).isoformat()
    return c


# --- 1. A venue's standing, on DelistWatch's real checks -------------------------------------


def test_a_trading_market_counts_in_full(mod):
    for check in (KUCOIN_STORJ, BINANCE_BTC, OKX_BTC):
        v = _venue(mod, check)
        assert (v["state"], v["weight_pct"], v["days_left"]) == ("TRADING", 100, None)


def test_a_market_the_exchange_says_is_not_trading_counts_for_nothing(mod):
    for check in (OKX_STORJ, BINANCE_STORJ):
        v = _venue(mod, check)
        assert (v["state"], v["weight_pct"]) == ("OUT", 0)


@pytest.mark.parametrize("check", [KUCOIN_STORJ, OKX_STORJ, BINANCE_BTC])
def test_a_check_older_than_the_limit_counts_for_nothing_whatever_it_said(mod, check):
    v = _venue(mod, check, after=MAX_AGE + 1)
    assert (v["state"], v["weight_pct"]) == ("STALE", 0) and str(MAX_AGE + 1) in v["reason"]


def test_the_freshness_limit_is_inclusive_and_a_check_from_the_future_is_stale(mod):
    assert _venue(mod, KUCOIN_STORJ, after=MAX_AGE)["state"] == "TRADING"
    assert _venue(mod, KUCOIN_STORJ, after=MAX_AGE + 1)["state"] == "STALE"
    assert _venue(mod, KUCOIN_STORJ, after=0)["state"] == "TRADING"
    assert _venue(mod, KUCOIN_STORJ, after=-1)["state"] == "STALE"


def test_a_market_with_no_check_or_an_undetermined_one_counts_for_nothing(mod):
    none = mod._venue({"watch_id": "x", "verdict": "NONE"}, 10 ** 10, MAX_AGE)
    assert (none["state"], none["weight_pct"]) == ("NO_CHECK", 0)
    undetermined = _venue(mod, dict(copy.deepcopy(KUCOIN_STORJ), verdict="UNDETERMINED"))
    assert (undetermined["state"], undetermined["weight_pct"]) == ("UNKNOWN", 0)
    odd = _venue(mod, dict(copy.deepcopy(KUCOIN_STORJ), verdict="SOMETHING_NEW"))
    assert (odd["state"], odd["weight_pct"]) == ("UNKNOWN", 0)


@pytest.mark.parametrize("days, weight", [
    (400, 75), (31, 75), (30, 75),        # a month or more: three quarters still counted
    (29, 50), (14, 50),                   # from a fortnight: half
    (13, 25), (7, 25),                    # from a week: a quarter
    (6, 0), (1, 0), (0, 0),               # inside a week, nothing
    (-1, 0), (-30, 0),                    # the date has passed and the market still shows as trading: nothing
])
def test_an_announced_delisting_counts_less_as_it_approaches(mod, days, weight):
    v = _venue(mod, _delisting(days))
    assert v["state"] == "DELISTING" and v["weight_pct"] == weight and v["days_left"] == days


@pytest.mark.parametrize("date", ["", "soon", "2026-13-45", "11/10/2026", None, "20261010", "2026-W41-1", "2026-10-10T00:00:00"])
def test_an_announced_delisting_with_an_unreadable_date_counts_for_nothing(mod, date):
    c = copy.deepcopy(KUCOIN_STORJ)
    c["verdict"] = "DELISTING_ANNOUNCED"
    c["effective_date"] = date
    v = _venue(mod, c)
    assert v["state"] == "DELISTING" and v["weight_pct"] == 0 and v["days_left"] is None


def test_the_countdown_is_in_calendar_days_in_utc(mod):
    c = _delisting(14)
    at = _seconds(c) + 60                                   # a moment late in the UTC day
    late = (at // 86400) * 86400 + 86399
    assert mod._venue(c, late, 10 ** 9)["days_left"] == 14 and mod._venue(c, late + 1, 10 ** 9)["days_left"] == 13


# --- 2. A basket's coverage and its loan-to-value limit ----------------------------------------------


@pytest.mark.parametrize("weights, coverage", [
    ([100, 100, 100], 100), ([100, 0, 0], 33), ([100, 100, 0], 66), ([100, 50], 75), ([75], 75),
    ([0, 0, 0], 0), ([], 0), ([100, 0, 0, 0, 0], 20),
])
def test_coverage_is_the_average_weight_of_the_venues(mod, weights, coverage):
    assert mod._coverage(weights) == coverage


@pytest.mark.parametrize("coverage, ltv", [
    (100, 6000), (99, 4200), (66, 4200), (65, 2400), (33, 2400), (32, 0), (0, 0),
])
def test_the_ladder_turns_coverage_into_a_share_of_the_base_ratio(mod, coverage, ltv):
    assert mod._ltv_bps(BASE, coverage, LADDER) == ltv


def test_the_ladder_rounds_down(mod):
    assert mod._ltv_bps(6001, 66, [[66, 70]]) == 4200          # 4200.7
    assert mod._ltv_bps(333, 100, [[100, 33]]) == 109          # 109.89


def test_a_ladder_can_end_in_a_rung_that_allows_something_at_any_coverage(mod):
    assert mod._ltv_bps(BASE, 0, [[100, 100], [0, 10]]) == 600


@pytest.mark.parametrize("collateral, ltv, maximum", [
    (10_000, 6000, 6000), (10_000, 4200, 4200), (10_000, 2400, 2400), (10_000, 0, 0), (999, 6000, 599), (1, 6000, 0),
])
def test_what_may_be_borrowed_rounds_down(mod, collateral, ltv, maximum):
    assert mod._max_borrow(collateral, ltv) == maximum


def test_the_real_baskets_on_studio_next(mod):
    """The three real baskets, at the moment DelistWatch's checks were fresh."""
    def basket(*checks):
        weights = [_venue(mod, c)["weight_pct"] for c in checks]
        return mod._coverage(weights), mod._ltv_bps(BASE, mod._coverage(weights), LADDER)
    assert basket(BINANCE_BTC, OKX_BTC) == (100, 6000)                    # BTC on two venues, both trading
    assert basket(KUCOIN_STORJ, OKX_STORJ, BINANCE_STORJ) == (33, 2400)   # STORJ: one venue left of three
    assert basket(OKX_STORJ, BINANCE_STORJ) == (0, 0)                     # STORJ without KuCoin: no loans


def test_a_delisting_announced_on_one_venue_lowers_the_limit_progressively(mod):
    # SYNTHETIC: BTC on two venues, one of them announcing a delisting.
    limits = []
    for days in (60, 20, 10, 3):
        weights = [_venue(mod, BINANCE_BTC)["weight_pct"], _venue(mod, _delisting(days, OKX_BTC))["weight_pct"]]
        limits.append((mod._coverage(weights), mod._ltv_bps(BASE, mod._coverage(weights), LADDER)))
    assert limits == [(87, 4200), (75, 4200), (62, 2400), (50, 2400)]


# --- 3. The ladder's configuration ----------------------------------------------------------------------


@pytest.mark.parametrize("ladder, message", [
    ("not json", "ladder must be JSON"), ("{}", "1-8 pairs"), ("[]", "1-8 pairs"), ("[[100]]", "1-8 pairs"),
    ("[[100, 100, 1]]", "1-8 pairs"), ("[[101, 100]]", "1-8 pairs"), ("[[100, -1]]", "1-8 pairs"),
    ("[[100, 100.5]]", "1-8 pairs"), ("[[true, 100]]", "1-8 pairs"),
    (json.dumps([[100 - 10 * i, 100 - 10 * i] for i in range(9)]), "1-8 pairs"),
    ("[[66, 70], [100, 100]]", "strictly descending"), ("[[100, 100], [100, 50]]", "strictly descending"),
    ("[[100, 40], [66, 70]]", "must not rise"),
])
def test_an_invalid_ladder_is_rejected(direct_vm, direct_deploy, direct_owner, ladder, message):
    direct_vm.sender = direct_owner
    with pytest.raises(Exception, match=message):
        direct_deploy("contracts/collateral_guard.py", DW, MAX_AGE, BASE, ladder)


@pytest.mark.parametrize("max_age, base", [(0, 6000), (3600, 0), (3600, 10001)])
def test_an_invalid_configuration_is_rejected(direct_vm, direct_deploy, direct_owner, max_age, base):
    with pytest.raises(Exception):
        _deploy(direct_vm, direct_deploy, direct_owner, max_age, base)


# --- 4. The contract's own checks, before it reads DelistWatch -------------------------------------------


def test_config_rules_and_empty_state(direct_vm, direct_deploy, direct_owner):
    cg = _deploy(direct_vm, direct_deploy, direct_owner)
    cfg = cg.get_config()
    assert cfg["delistwatch_address"].lower() == DW and (cfg["max_age_seconds"], cfg["base_ltv_bps"]) == (MAX_AGE, BASE)
    assert cfg["ladder"] == LADDER and (cfg["basket_count"], cfg["loan_count"]) == (0, 0)
    rules = cg.get_rules()
    assert rules["coverage_ladder"] == LADDER
    assert rules["countdown"] == [{"days_at_least": 30, "venue_share_pct": 75}, {"days_at_least": 14, "venue_share_pct": 50},
                                  {"days_at_least": 7, "venue_share_pct": 25}]
    assert cg.list_baskets() == [] and cg.get_loans(0, 10) == []
    with pytest.raises(Exception, match="unknown basket_id"):
        cg.get_status("nope")
    with pytest.raises(Exception, match="unknown basket_id"):
        cg.max_borrow("nope", 1000)


def test_only_the_owner_can_create_a_basket(direct_vm, direct_deploy, direct_owner, direct_alice):
    cg = _deploy(direct_vm, direct_deploy, direct_owner)
    direct_vm.sender = direct_alice
    with pytest.raises(Exception, match="only the owner can create a basket"):
        cg.create_basket("btc", "BTC", ["binance-btc"])


@pytest.mark.parametrize("args, message", [
    (("", "BTC", ["binance-btc"]), "basket_id must be"), (("a b", "BTC", ["binance-btc"]), "basket_id must be"),
    (("x" * 33, "BTC", ["binance-btc"]), "basket_id must be"),
    (("btc", "btc", ["binance-btc"]), "token must be"), (("btc", "", ["binance-btc"]), "token must be"),
    (("btc", "BTC-USDT&x=1", ["binance-btc"]), "token must be"), (("btc", "A" * 16, ["binance-btc"]), "token must be"),
    (("btc", "BTC", []), "a basket holds 1-5 venues"), (("btc", "BTC", ["a", "b", "c", "d", "e", "f"]), "a basket holds 1-5 venues"),
    (("btc", "BTC", ["binance-btc", "binance-btc"]), "a venue can only be in a basket once"),
])
def test_invalid_baskets_are_rejected_before_any_cross_contract_call(direct_vm, direct_deploy, direct_owner, args, message):
    cg = _deploy(direct_vm, direct_deploy, direct_owner)
    with pytest.raises(Exception, match=message):
        cg.create_basket(*args)


def test_a_zero_loan_and_an_unknown_basket_are_rejected_before_any_cross_contract_call(direct_vm, direct_deploy, direct_owner):
    cg = _deploy(direct_vm, direct_deploy, direct_owner)
    with pytest.raises(Exception, match="amount must be positive"):
        cg.borrow("btc", 1000, 0)
    with pytest.raises(Exception, match="unknown basket_id"):
        cg.borrow("btc", 1000, 100)
