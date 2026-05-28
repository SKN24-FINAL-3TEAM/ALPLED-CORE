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
    calc_binary_score,
    calc_keyword_hit_rate,
    calc_name_hit_rate,
    calc_speed_score,
    calc_weighted_score,
    find_values_by_keys,
    load_json_safe,
    stringify,
)


TASK_RUNNERS = {
    "embedding": "eval.runners.embedding_runner",
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
    "embedding": {"title", "section", "source", "doc_type", "chunk_type"},
}

EXPECTED_NAME_KEYS_BY_TASK = {
    "srs": "expected_requirements",
    "erd": "expected_entities",
    "db": "expected_tables",
    "architecture": "expected_components",
    "interface": "expected_screens",
    "ts": "expected_scenarios",
    "embedding": "expected_names",
}


def current_llm_model_name() -> str:
    return os.getenv("LLM_MODEL") or os.getenv("LLM_MODEL_NAME") or "unknown"


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
        for task in os.getenv("EVAL_TASKS", "embedding,srs,erd,db,architecture,interface,ts").split(",")
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


def _empty_selection_metrics() -> dict[str, Any]:
    return {
        "search_accuracy": "",
        "search_rank_quality": "",
        "search_result_relevance": "",
        "embedding_generation_speed_sec": "",
        "embedding_generation_speed_score": "",
        "embedding_deployment_efficiency": "",
        "first_expected_rank": "",
        "retrieved_count": "",
        "generated_document_quality": "",
        "rag_evidence_reflection_rate": "",
        "structured_output_compliance": "",
        "inference_speed_sec": "",
        "inference_speed_score": "",
        "llm_deployment_efficiency": "",
        "selection_score": 0.0,
    }


def _llm_selection_metrics(
    *,
    case: dict[str, Any],
    elapsed_sec: float,
    json_valid: bool,
    validation_pass: bool,
    name_hit_rate: float,
    keyword_hit_rate: float,
    output_text: str,
    raw_text: str,
) -> dict[str, Any]:
    document_quality = calc_weighted_score(
        [
            (calc_binary_score(json_valid), 0.2),
            (calc_binary_score(validation_pass), 0.3),
            (name_hit_rate * 100, 0.25),
            (keyword_hit_rate * 100, 0.25),
        ]
    )

    evidence_keywords = case.get("expected_evidence_keywords") or case.get("expected_keywords", [])
    rag_evidence_reflection = round(
        calc_keyword_hit_rate(output_text + raw_text, evidence_keywords) * 100,
        2,
    )
    structured_output = calc_weighted_score(
        [
            (calc_binary_score(json_valid), 0.5),
            (calc_binary_score(validation_pass), 0.5),
        ]
    )
    speed_score = calc_speed_score(elapsed_sec, float(os.getenv("EVAL_LLM_SPEED_TARGET_SEC", "120")))
    deployment_efficiency = float(os.getenv("EVAL_LLM_DEPLOYMENT_EFFICIENCY_SCORE", "0"))

    return {
        "generated_document_quality": document_quality,
        "rag_evidence_reflection_rate": rag_evidence_reflection,
        "structured_output_compliance": structured_output,
        "inference_speed_sec": elapsed_sec,
        "inference_speed_score": speed_score,
        "llm_deployment_efficiency": deployment_efficiency,
        "selection_score": calc_weighted_score(
            [
                (document_quality, 0.3),
                (rag_evidence_reflection, 0.25),
                (structured_output, 0.2),
                (speed_score, 0.15),
                (deployment_efficiency, 0.1),
            ]
        ),
    }


def _embedding_selection_metrics(result: dict[str, Any]) -> dict[str, Any]:
    metrics = result.get("selection_metrics") or {}
    speed_sec = float(metrics.get("embedding_generation_speed_sec") or 0.0)
    speed_score = calc_speed_score(speed_sec, float(os.getenv("EVAL_EMBED_SPEED_TARGET_SEC", "1")))
    deployment_efficiency = float(metrics.get("embedding_deployment_efficiency") or 0.0)
    search_accuracy = float(metrics.get("search_accuracy") or 0.0)
    search_rank_quality = float(metrics.get("search_rank_quality") or 0.0)
    search_result_relevance = float(metrics.get("search_result_relevance") or 0.0)

    return {
        **metrics,
        "embedding_generation_speed_score": speed_score,
        "embedding_deployment_efficiency": deployment_efficiency,
        "selection_score": calc_weighted_score(
            [
                (search_accuracy, 0.3),
                (search_rank_quality, 0.25),
                (search_result_relevance, 0.25),
                (speed_score, 0.1),
                (deployment_efficiency, 0.1),
            ]
        ),
    }


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    start = time.perf_counter()

    task = case["task"]
    model_name = current_llm_model_name()
    embed_model_name = os.getenv("EMBED_MODEL_NAME", "unknown")
    qdrant_collection = os.getenv("QDRANT_COLLECTION", "")

    row = {
        "model_name": model_name,
        "embed_model_name": embed_model_name,
        "qdrant_collection": qdrant_collection,
        "task": task,
        "case_id": case.get("case_id"),
        "description": case.get("description", ""),
        "criteria_group": "embedding" if task == "embedding" else "llm",
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
        **_empty_selection_metrics(),
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
        selection_metrics = (
            _embedding_selection_metrics(result)
            if task == "embedding"
            else _llm_selection_metrics(
                case=case,
                elapsed_sec=elapsed,
                json_valid=json_valid,
                validation_pass=validation_pass,
                name_hit_rate=name_hit_rate,
                keyword_hit_rate=keyword_hit_rate,
                output_text=output_text,
                raw_text=raw_text,
            )
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
                **selection_metrics,
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
    model_name = current_llm_model_name().replace("/", "_").replace(":", "_")
    embed_model_name = os.getenv("EMBED_MODEL_NAME", "unknown").replace("/", "_").replace(":", "_")
    path = result_dir / f"eval_result_{model_name}_{embed_model_name}_{timestamp}.csv"

    fieldnames = [
        "model_name",
        "embed_model_name",
        "qdrant_collection",
        "criteria_group",
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
        "search_accuracy",
        "search_rank_quality",
        "search_result_relevance",
        "embedding_generation_speed_sec",
        "embedding_generation_speed_score",
        "embedding_deployment_efficiency",
        "first_expected_rank",
        "retrieved_count",
        "generated_document_quality",
        "rag_evidence_reflection_rate",
        "structured_output_compliance",
        "inference_speed_sec",
        "inference_speed_score",
        "llm_deployment_efficiency",
        "selection_score",
    ]

    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return str(path)


def _avg(rows: list[dict[str, Any]], key: str) -> float:
    values = []
    for row in rows:
        value = row.get(key)
        if value in ("", None):
            continue
        values.append(float(value))
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


def save_selection_summary_csv(rows: list[dict[str, Any]]) -> str:
    result_dir = ROOT_DIR / os.getenv("EVAL_RESULT_DIR", "eval/results")
    result_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = result_dir / f"eval_selection_summary_{timestamp}.csv"

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        group = row.get("criteria_group") or "llm"
        model_key = row.get("embed_model_name") if group == "embedding" else row.get("model_name")
        grouped.setdefault((group, model_key or "unknown"), []).append(row)

    summary_rows = []
    for (group, model_key), group_rows in grouped.items():
        if group == "embedding":
            summary_rows.append(
                {
                    "criteria_group": "embedding",
                    "model": model_key,
                    "search_accuracy": _avg(group_rows, "search_accuracy"),
                    "search_rank_quality": _avg(group_rows, "search_rank_quality"),
                    "search_result_relevance": _avg(group_rows, "search_result_relevance"),
                    "embedding_generation_speed_score": _avg(group_rows, "embedding_generation_speed_score"),
                    "deployment_efficiency": _avg(group_rows, "embedding_deployment_efficiency"),
                    "generated_document_quality": "",
                    "rag_evidence_reflection_rate": "",
                    "structured_output_compliance": "",
                    "inference_speed_score": "",
                    "selection_score": _avg(group_rows, "selection_score"),
                }
            )
        else:
            summary_rows.append(
                {
                    "criteria_group": "llm",
                    "model": model_key,
                    "search_accuracy": "",
                    "search_rank_quality": "",
                    "search_result_relevance": "",
                    "embedding_generation_speed_score": "",
                    "deployment_efficiency": _avg(group_rows, "llm_deployment_efficiency"),
                    "generated_document_quality": _avg(group_rows, "generated_document_quality"),
                    "rag_evidence_reflection_rate": _avg(group_rows, "rag_evidence_reflection_rate"),
                    "structured_output_compliance": _avg(group_rows, "structured_output_compliance"),
                    "inference_speed_score": _avg(group_rows, "inference_speed_score"),
                    "selection_score": _avg(group_rows, "selection_score"),
                }
            )

    fieldnames = [
        "criteria_group",
        "model",
        "search_accuracy",
        "search_rank_quality",
        "search_result_relevance",
        "embedding_generation_speed_score",
        "generated_document_quality",
        "rag_evidence_reflection_rate",
        "structured_output_compliance",
        "inference_speed_score",
        "deployment_efficiency",
        "selection_score",
    ]

    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summary_rows)

    return str(path)


def print_summary(rows: list[dict[str, Any]]) -> None:
    grouped: dict[str, list[dict[str, Any]]] = {}

    for row in rows:
        grouped.setdefault(row["task"], []).append(row)

    print("\n========== EVAL SUMMARY ==========")

    for task, task_rows in grouped.items():
        avg_score = sum(float(r["basic_score"]) for r in task_rows) / len(task_rows)
        avg_selection_score = sum(float(r["selection_score"] or 0) for r in task_rows) / len(task_rows)
        avg_elapsed = sum(float(r["elapsed_sec"]) for r in task_rows) / len(task_rows)
        pass_count = sum(1 for r in task_rows if r["validation_pass"])

        print(
            f"{task:12s} | cases={len(task_rows)} "
            f"| pass={pass_count}/{len(task_rows)} "
            f"| avg_score={avg_score:.2f} "
            f"| avg_selection={avg_selection_score:.2f} "
            f"| avg_elapsed={avg_elapsed:.2f}s"
        )


def main() -> None:
    load_dotenv(ROOT_DIR / ".env")

    print(f"[EVAL] model    : {current_llm_model_name()}")
    print(f"[EVAL] embed    : {os.getenv('EMBED_MODEL_NAME')}")
    print(f"[EVAL] qdrant   : {os.getenv('QDRANT_COLLECTION')}")
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
    summary_csv_path = save_selection_summary_csv(rows)
    print_summary(rows)
    print(f"\n[EVAL] saved: {csv_path}")
    print(f"[EVAL] summary saved: {summary_csv_path}")


if __name__ == "__main__":
    main()
