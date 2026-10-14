"""
The trust path in TRUST_PATH.md, checked offline.

CollateralGuard is a deterministic lending policy: it has no web access and no LLM. Everything non-deterministic
(reading the exchanges, the reader, validator consensus) happens in DelistWatch, whose exact deployed source is
included under dependencies/delistwatch. These tests pin the properties a reviewer relies on when following the path
from an exchange's own data to a loan, so the path cannot silently break:

  - the included dependency is the deployed code (by SHA-256; studio-next/verify_dependency.ts checks the chain itself);
  - the dependency really does the non-deterministic work and the policy does none of it;
  - every view the policy calls exists in the dependency, and every verdict the dependency can record is accounted for;
  - the policy reads fields the dependency actually stores;
  - everything points at one deployed dependency; the trust-path document is current.
"""
import ast
import hashlib
import importlib.util
import json
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parent.parent
DEP_DIR = REPO / "dependencies" / "delistwatch"
DEP = DEP_DIR / "contracts" / "delist_watch_studio_next.py"
GUARD = REPO / "contracts" / "collateral_guard_studio_next.py"

DEPLOYED_SHA256 = "65450eb378d26236bad24241c096b4929d8a710b436bad154b65abbf5d17f77b"
DELISTWATCH_ADDRESS = "0x1AFffBad8fCfBEFD9494fd8994118f586B85DAFc"


def _function(path: pathlib.Path, name: str) -> ast.FunctionDef:
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found in {path.name}")


def _strings(node: ast.AST) -> set:
    return {n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def test_the_included_dependency_is_the_deployed_code():
    assert hashlib.sha256(DEP.read_bytes()).hexdigest() == DEPLOYED_SHA256


def test_the_included_dependency_is_complete():
    for rel in ("LICENSE", "README.md", "CONTRACT.md", "contracts/delist_watch.py", "contracts/delist_watch_studio_next.py",
                "tests/test_delist_watch.py", "tests/mutations.txt", "scripts/build_fixtures.py"):
        assert (DEP_DIR / rel).is_file(), f"dependencies/delistwatch/{rel} is missing"


def test_the_dependency_does_the_non_deterministic_work_and_the_policy_does_none_of_it():
    dep, guard = DEP.read_text(), GUARD.read_text()
    for needed in ("gl.nondet.web.get", "gl.nondet.exec_prompt", "gl.vm.run_nondet"):
        assert needed in dep, f"DelistWatch no longer uses {needed}"
        assert needed not in guard, f"CollateralGuard must stay deterministic but uses {needed}"


def test_every_view_the_policy_calls_exists_in_the_dependency():
    called = set(re.findall(r"\.view\(\)\.(\w+)\(", GUARD.read_text()))
    assert called == {"latest_check", "list_watches"}, called
    views = set(re.findall(r"@gl\.public\.view\s+def (\w+)\(", DEP.read_text()))
    assert called <= views, f"DelistWatch has no view {called - views}"


def test_every_verdict_the_dependency_can_record_is_accounted_for_by_the_policy():
    recorded = set()
    for node in ast.walk(_function(DEP, "_decide")):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.List) and node.value.elts:
            first = node.value.elts[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                recorded.add(first.value)
    assert recorded == {"UNDETERMINED", "NOT_TRADING", "DELISTING_ANNOUNCED", "TRADING"}, recorded
    venue = _function(GUARD, "_venue")
    handled = _strings(venue)
    # Trading, not trading and an announced delisting each have a rule; a market never checked has one too.
    assert {"TRADING", "NOT_TRADING", "DELISTING_ANNOUNCED", "NONE"} <= handled
    # Anything else (UNDETERMINED, or a verdict added later) falls through to the fail-closed state, weight 0.
    last = [n for n in venue.body if isinstance(n, ast.Return)][-1]
    assert "UNKNOWN" in _strings(last) and any(isinstance(n, ast.Constant) and n.value == 0 for n in ast.walk(last))
    assert (recorded - handled) <= {"UNDETERMINED"}, f"unhandled verdicts: {recorded - handled}"


def test_the_policy_reads_the_fields_the_dependency_stores():
    stored = _strings(_function(DEP, "_check_dict"))
    for field in ("check_id", "verdict", "effective_date", "checked_at"):
        assert field in stored, f"DelistWatch's check record has no {field}"
    used = _strings(_function(GUARD, "_venue"))
    assert {"verdict", "checked_at", "effective_date"} <= used
    listed = _strings(_function(DEP, "list_watches"))
    assert {"watch_id", "exchange", "base", "quote"} <= listed, "list_watches no longer lists what create_basket needs"
    needs = _strings(_function(GUARD, "create_basket"))
    assert {"watch_id", "base", "exchange", "quote"} <= needs


def test_everything_points_at_one_deployed_dependency():
    for rel in ("studio-next/deployment.json", "web/src/lib/guard.ts", "dependencies/delistwatch/CONTRACT.md",
                "dependencies/README.md", "README.md", "TRUST_PATH.md", "studio-next/verify_dependency.ts"):
        assert DELISTWATCH_ADDRESS in (REPO / rel).read_text(), f"{rel} does not name DelistWatch at {DELISTWATCH_ADDRESS}"
    assert json.loads((REPO / "studio-next" / "deployment.json").read_text())["delistwatch"]["address"] == DELISTWATCH_ADDRESS


def test_the_trust_path_document_is_current():
    spec = importlib.util.spec_from_file_location("build_trust_path", REPO / "scripts" / "build_trust_path.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert (REPO / "TRUST_PATH.md").read_text() == module.TEXT, "TRUST_PATH.md is stale: run scripts/build_trust_path.py"
