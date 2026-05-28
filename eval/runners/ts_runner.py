from typing import Any

from eval.runners.common import result_dir, resolve_path, timestamp, validation_errors_from_result, normalize_status


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    from workflows.ts_workflow import compile_ts_graph

    case_id = case["case_id"]
    ts = timestamp()
    out_dir = result_dir()

    output_json_path = out_dir / f"{case_id}_{ts}_ts.json"
    output_docx_path = out_dir / f"{case_id}_{ts}_ts.docx"

    ui_paths = [resolve_path(path) for path in case.get("ui_paths", [])]

    result = compile_ts_graph().invoke(
        {
            "requirement_json_path": resolve_path(case.get("requirement_json_path")),
            "ui_paths": ui_paths,
            "output_json_path": str(output_json_path),
            "output_docx_path": str(output_docx_path),
            "max_retries": int(case.get("max_retries", 1)),
        }
    )

    return {
        "status": normalize_status(result),
        "output_json_path": str(result.get("output_json_path") or output_json_path),
        "output_docx_path": str(result.get("output_docx_path") or output_docx_path),
        "validation_errors": validation_errors_from_result(result),
        "raw_result": result,
    }
