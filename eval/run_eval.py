import csv
import json
import os
import sys
import time
import traceback
from datetime import datetime
from importlib import import_module
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from eval.metrics import (
    calc_basic_score,
    calc_keyword_hit_rate,
    calc_name_hit_rate,
    find_values_by_keys,
    load_json_safe,
    stringify,
)


TASK_RUNNERS = {
    "srs": "eval.runners.srs_runner",
    "erd": "eval.runners.erd_runner",
    "db": "eval.runners.db_runner",
    "architecture": "eval.runners.architecture_runner",
    "interface": "eval.runners.interface_runner",
    "ts": "eval.runners.ts_runner",
}

NAME_KEYS_BY_TASK = {
    "srs": {"requirement_name", "requirement_title", "name", "title"},
    "erd": {"entity_name", "table_name", "name"},
    "db": {"table_name", "column_name", "name"},
    "architecture": {"component_name", "name", "title"},
    "interface": {"screen_name", "screen_id", "level4", "title", "name"},
    "ts": {"scenario_name", "test_case_name", "name", "title"},
}

EXPECTED_NAME_KEYS_BY_TASK = {
    "srs": "expected_requirements",
    "erd": "expected_entities",
    "db": "expected_tables",
    "architecture": "expected_components",
    "interface": "expected_screens",
    "ts": "expected_scenarios",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        print(f"[WARN] case file not found: {path}")
        return []

    rows: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSONL: {path}:{line_no} - {e}") from e

    return rows


def load_cases() -> list[dict[str, Any]]:
    case_dir = ROOT_DIR / os.getenv("EVAL_CASE_DIR", "eval/cases")
    task_names = [
        task.strip()
        for task in os.getenv("EVAL_TASKS", "srs,erd,db,architecture,interface,ts").split(",")
        if task.strip()
    ]

    all_cases: list[dict[str, Any]] = []

    for task in task_names:
        case_path = case_dir / f"{task}.jsonl"
        cases = read_jsonl(case_path)
        all_cases.extend(cases)

    return all_cases


def run_agent_case(case: dict[str, Any]) -> dict[str, Any]:
    task = case["task"]

    if task not in TASK_RUNNERS:
        raise ValueError(f"Unsupported task: {task}")

    module = import_module(TASK_RUNNERS[task])
    return module.run_case(case)


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    start = time.perf_counter()

    task = case["task"]
    model_name = os.getenv("LLM_MODEL", "unknown")

    row = {
        "model_name": model_name,
        "task": task,
        "case_id": case.get("case_id"),
        "description": case.get("description", ""),
        "status": "ERROR",
        "elapsed_sec": 0.0,
        "json_valid": False,
        "validation_pass": False,
        "name_hit_rate": 0.0,
        "keyword_hit_rate": 0.0,
        "basic_score": 0.0,
        "error_count": 0,
        "output_json_path": "",
        "output_docx_path": "",
        "error_message": "",
    }

    try:
        result = run_agent_case(case)
        elapsed = round(time.perf_counter() - start, 3)

        output_json_path = result.get("output_json_path")
        output_docx_path = result.get("output_docx_path")
        output_data = load_json_safe(output_json_path)

        json_valid = output_data is not None
        validation_errors = result.get("validation_errors") or []
        validation_pass = str(result.get("status")).upper() == "VALID" and not validation_errors

        raw_text = stringify(result.get("raw_result", {}))
        output_text = stringify(output_data) if output_data is not None else raw_text

        name_keys = NAME_KEYS_BY_TASK.get(task, {"name", "title"})
        actual_names = find_values_by_keys(output_data, name_keys)

        expected_key = EXPECTED_NAME_KEYS_BY_TASK.get(task, "expected_names")
        expected_names = case.get(expected_key, [])

        name_hit_rate = calc_name_hit_rate(actual_names, expected_names)
        keyword_hit_rate = calc_keyword_hit_rate(output_text + raw_text, case.get("expected_keywords", []))

        basic_score = calc_basic_score(
            json_valid=json_valid,
            validation_pass=validation_pass,
            name_hit_rate=name_hit_rate,
            keyword_hit_rate=keyword_hit_rate,
        )

        row.update(
            {
                "status": result.get("status", "UNKNOWN"),
                "elapsed_sec": elapsed,
                "json_valid": json_valid,
                "validation_pass": validation_pass,
                "name_hit_rate": name_hit_rate,
                "keyword_hit_rate": keyword_hit_rate,
                "basic_score": basic_score,
                "error_count": len(validation_errors),
                "output_json_path": output_json_path or "",
                "output_docx_path": output_docx_path or "",
                "error_message": " | ".join(map(str, validation_errors)),
            }
        )

    except Exception as e:
        row["elapsed_sec"] = round(time.perf_counter() - start, 3)
        row["error_message"] = f"{type(e).__name__}: {e}"
        traceback.print_exc()

    return row


def save_csv(rows: list[dict[str, Any]]) -> str:
    result_dir = ROOT_DIR / os.getenv("EVAL_RESULT_DIR", "eval/results")
    result_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_name = os.getenv("LLM_MODEL", "unknown").replace("/", "_").replace(":", "_")
    path = result_dir / f"eval_result_{model_name}_{timestamp}.csv"

    fieldnames = [
        "model_name",
        "task",
        "case_id",
        "description",
        "status",
        "elapsed_sec",
        "json_valid",
        "validation_pass",
        "name_hit_rate",
        "keyword_hit_rate",
        "basic_score",
        "error_count",
        "output_json_path",
        "output_docx_path",
        "error_message",
    ]

    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return str(path)


def print_summary(rows: list[dict[str, Any]]) -> None:
    grouped: dict[str, list[dict[str, Any]]] = {}

    for row in rows:
        grouped.setdefault(row["task"], []).append(row)

    print("\n========== EVAL SUMMARY ==========")

    for task, task_rows in grouped.items():
        avg_score = sum(float(r["basic_score"]) for r in task_rows) / len(task_rows)
        avg_elapsed = sum(float(r["elapsed_sec"]) for r in task_rows) / len(task_rows)
        pass_count = sum(1 for r in task_rows if r["validation_pass"])

        print(
            f"{task:12s} | cases={len(task_rows)} "
            f"| pass={pass_count}/{len(task_rows)} "
            f"| avg_score={avg_score:.2f} "
            f"| avg_elapsed={avg_elapsed:.2f}s"
        )


def main() -> None:
    load_dotenv(ROOT_DIR / ".env")

    print(f"[EVAL] model    : {os.getenv('LLM_MODEL')}")
    print(f"[EVAL] base_url : {os.getenv('LLM_BASE_URL')}")
    print(f"[EVAL] tasks    : {os.getenv('EVAL_TASKS')}")

    cases = load_cases()

    if not cases:
        raise RuntimeError("No eval cases loaded. Check eval/cases/*.jsonl")

    print(f"[EVAL] cases    : {len(cases)}")

    rows = []

    for case in cases:
        print(f"\n[EVAL] running {case.get('task')} / {case.get('case_id')} - {case.get('description', '')}")
        row = evaluate_case(case)
        rows.append(row)
        print(
            f"[EVAL] done {row['task']} / {row['case_id']} "
            f"status={row['status']} score={row['basic_score']} elapsed={row['elapsed_sec']}s"
        )

    csv_path = save_csv(rows)
    print_summary(rows)
    print(f"\n[EVAL] saved: {csv_path}")


if __name__ == "__main__":
    main()
