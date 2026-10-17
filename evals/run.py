"""Run deterministic eval cases and compare them with a saved baseline."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import yaml
from app.main import create_app
from fastapi.testclient import TestClient

EVALS_DIR = Path(__file__).resolve().parent
DEFAULT_CASES = EVALS_DIR / "cases"
DEFAULT_BASELINE = EVALS_DIR / "baseline.json"
REGRESSION_THRESHOLD = 0.15


@dataclass(frozen=True, slots=True)
class EvalCase:
    """One declarative evaluation case."""

    case_id: str
    kind: str
    description: str
    input: dict[str, Any]
    expect: dict[str, Any]
    forbidden: dict[str, Any]
    cost_cny: float


@dataclass(frozen=True, slots=True)
class EvalResult:
    """Observed result for one evaluation case."""

    case_id: str
    passed: bool
    cost_cny: float
    failure_reason: str | None = None


@dataclass(frozen=True, slots=True)
class EvalReport:
    """Aggregate evaluation result written to stdout and the baseline."""

    results: tuple[EvalResult, ...]
    generated_at: str

    @property
    def passed(self) -> int:
        return sum(result.passed for result in self.results)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def total_cost_cny(self) -> float:
        return sum(result.cost_cny for result in self.results)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "generated_at": self.generated_at,
            "total": self.total,
            "passed": self.passed,
            "pass_rate": round(self.pass_rate, 6),
            "total_cost_cny": round(self.total_cost_cny, 6),
            "cases": [asdict(result) for result in self.results],
        }


def _object_mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be a mapping")
    mapping = cast(dict[object, object], value)
    if any(not isinstance(key, str) for key in mapping):
        raise ValueError(f"{field} keys must be strings")
    return {cast(str, key): item for key, item in mapping.items()}


def _optional_mapping(value: object, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    return _object_mapping(value, field)


def _parse_case(raw: object, source: Path) -> EvalCase:
    data = _object_mapping(raw, f"{source} case")
    case_id = data.get("id")
    kind = data.get("kind")
    description = data.get("description")
    if not isinstance(case_id, str) or not case_id:
        raise ValueError(f"{source} has an invalid id")
    if not isinstance(kind, str) or not kind:
        raise ValueError(f"{source} has an invalid kind")
    if not isinstance(description, str) or not description:
        raise ValueError(f"{source} has an invalid description")
    cost = data.get("cost_cny", 0.0)
    if not isinstance(cost, (int, float)) or isinstance(cost, bool) or cost < 0:
        raise ValueError(f"{source} has an invalid cost_cny")
    return EvalCase(
        case_id=case_id,
        kind=kind,
        description=description,
        input=_object_mapping(data.get("input"), f"{source}.input"),
        expect=_object_mapping(data.get("expect"), f"{source}.expect"),
        forbidden=_optional_mapping(data.get("forbidden"), f"{source}.forbidden"),
        cost_cny=float(cost),
    )


def load_cases(cases_path: Path = DEFAULT_CASES) -> tuple[EvalCase, ...]:
    """Load and validate all YAML cases from a file or directory."""

    paths = sorted(cases_path.glob("*.yaml")) if cases_path.is_dir() else [cases_path]
    if not paths:
        raise ValueError(f"no eval cases found at {cases_path}")
    cases: list[EvalCase] = []
    seen_ids: set[str] = set()
    for path in paths:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if raw is None:
            raise ValueError(f"{path} is empty")
        case = _parse_case(raw, path)
        if case.case_id in seen_ids:
            raise ValueError(f"duplicate eval case id: {case.case_id}")
        seen_ids.add(case.case_id)
        cases.append(case)
    return tuple(cases)


def _assert_contains(actual: object, expected: object, field: str) -> None:
    if isinstance(expected, dict):
        actual_mapping = _object_mapping(actual, field)
        expected_mapping = _object_mapping(expected, field)
        for key, expected_value in expected_mapping.items():
            if key not in actual_mapping:
                raise AssertionError(f"{field}.{key} is missing")
            _assert_contains(actual_mapping[key], expected_value, f"{field}.{key}")
        return
    if actual != expected:
        raise AssertionError(f"{field}: expected {expected!r}, got {actual!r}")


def _run_http_case(client: TestClient, case: EvalCase) -> None:
    method = case.input.get("method", "GET")
    path = case.input.get("path")
    if not isinstance(method, str) or not isinstance(path, str):
        raise ValueError(f"{case.case_id}: input.method and input.path are required")
    headers = _optional_mapping(case.input.get("headers"), f"{case.case_id}.input.headers")
    body = case.input.get("json")
    response = client.request(method, path, headers=headers, json=body)

    expected_status = case.expect.get("status_code", 200)
    if response.status_code != expected_status:
        raise AssertionError(
            f"status_code: expected {expected_status!r}, got {response.status_code}"
        )

    expected_headers = _optional_mapping(
        case.expect.get("headers"), f"{case.case_id}.expect.headers"
    )
    for name, expected_value in expected_headers.items():
        if response.headers.get(name) != expected_value:
            raise AssertionError(
                f"header {name}: expected {expected_value!r}, got {response.headers.get(name)!r}"
            )

    expected_json = _optional_mapping(
        case.expect.get("json_contains"), f"{case.case_id}.expect.json_contains"
    )
    if expected_json:
        _assert_contains(response.json(), expected_json, "response.json")

    forbidden_text = case.forbidden.get("text_contains", [])
    if not isinstance(forbidden_text, list):
        raise ValueError(f"{case.case_id}: forbidden.text_contains must be a list")
    for fragment in forbidden_text:
        if not isinstance(fragment, str):
            raise ValueError(f"{case.case_id}: forbidden text fragments must be strings")
        if fragment in response.text:
            raise AssertionError(f"forbidden response text found: {fragment!r}")


def run_suite(cases_path: Path = DEFAULT_CASES) -> EvalReport:
    """Execute all cases and return a baseline-compatible report."""

    cases = load_cases(cases_path)
    results: list[EvalResult] = []
    app = create_app()
    with TestClient(app) as client:
        for case in cases:
            failure_reason: str | None = None
            try:
                if case.kind == "http_contract":
                    _run_http_case(client, case)
                else:
                    raise ValueError(f"unsupported eval kind: {case.kind}")
            except Exception as exc:
                failure_reason = f"{type(exc).__name__}: {exc}"
            results.append(
                EvalResult(
                    case_id=case.case_id,
                    passed=failure_reason is None,
                    cost_cny=case.cost_cny,
                    failure_reason=failure_reason,
                )
            )
    return EvalReport(
        results=tuple(results),
        generated_at=datetime.now(UTC).isoformat(),
    )


def compare_with_baseline(report: EvalReport, baseline_path: Path) -> list[str]:
    """Return regression reasons using the approved 15% relative thresholds."""

    baseline = _object_mapping(
        json.loads(baseline_path.read_text(encoding="utf-8")),
        str(baseline_path),
    )
    baseline_pass_rate = baseline.get("pass_rate")
    baseline_cost = baseline.get("total_cost_cny")
    if not isinstance(baseline_pass_rate, (int, float)) or isinstance(baseline_pass_rate, bool):
        raise ValueError(f"{baseline_path} has an invalid pass_rate")
    if not isinstance(baseline_cost, (int, float)) or isinstance(baseline_cost, bool):
        raise ValueError(f"{baseline_path} has an invalid total_cost_cny")

    regressions: list[str] = []
    minimum_pass_rate = float(baseline_pass_rate) * (1 - REGRESSION_THRESHOLD)
    if report.pass_rate < minimum_pass_rate:
        regressions.append(
            f"pass_rate regressed from {baseline_pass_rate:.2%} to {report.pass_rate:.2%}"
        )

    maximum_cost = float(baseline_cost) * (1 + REGRESSION_THRESHOLD)
    if float(baseline_cost) == 0 and report.total_cost_cny > 0:
        regressions.append(f"total_cost_cny increased from 0 to {report.total_cost_cny:.6f}")
    elif report.total_cost_cny > maximum_cost:
        regressions.append(
            f"total_cost_cny regressed from {baseline_cost:.6f} to {report.total_cost_cny:.6f}"
        )
    return regressions


def save_baseline(report: EvalReport, baseline_path: Path) -> None:
    """Persist a report as the next comparison baseline."""

    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(
        json.dumps(report.as_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument(
        "--save-baseline",
        action="store_true",
        help="write the current all-pass report as the comparison baseline",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the eval CLI and return a process exit code."""

    args = _parser().parse_args(argv)
    try:
        report = run_suite(args.cases)
        payload = report.as_dict()
        if args.save_baseline:
            if report.passed != report.total:
                payload["error"] = "baseline not saved because the eval suite failed"
                sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
                return 1
            save_baseline(report, args.baseline)
            payload["baseline_saved"] = str(args.baseline)
        elif args.baseline.exists():
            regressions = compare_with_baseline(report, args.baseline)
            if regressions:
                payload["regressions"] = regressions
                sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
                return 1
        else:
            payload["baseline_missing"] = str(args.baseline)

        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        return 0 if report.passed == report.total else 1
    except Exception as exc:
        sys.stderr.write(f"eval failed: {type(exc).__name__}: {exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
