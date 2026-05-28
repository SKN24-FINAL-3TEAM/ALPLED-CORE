from typing import Any

from eval.runners.common import result_dir, resolve_path, timestamp, validation_errors_from_result, normalize_status


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    from workflows.db_design_workflow import compile_database_design_graph

    case_id = case["case_id"]
    ts = timestamp()
    out_dir = result_dir()

    output_json_path = out_dir / f"{case_id}_{ts}_db.json"
    output_docx_path = out_dir / f"{case_id}_{ts}_db.docx"

    result = compile_database_design_graph().invoke(
        {
            "requirement_json_path": resolve_path(case.get("requirement_json_path")),
            "erd_docx_path": resolve_path(case.get("erd_docx_path")),
            "use_rag": bool(case.get("use_rag", True)),
            "output_json_path": str(output_json_path),
            "output_docx_path": str(output_docx_path),
        }
    )

    return {
        "status": normalize_status(result),
        "output_json_path": str(result.get("output_json_path") or output_json_path),
        "output_docx_path": str(result.get("database_design_docx_path") or output_docx_path),
        "validation_errors": validation_errors_from_result(result),
        "raw_result": result,
    }
