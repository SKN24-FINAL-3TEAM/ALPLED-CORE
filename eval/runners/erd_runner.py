from typing import Any

from eval.runners.common import result_dir, resolve_path, timestamp, validation_errors_from_result, normalize_status


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    from workflows.erd_workflow import compile_erd_graph

    case_id = case["case_id"]
    ts = timestamp()
    out_dir = result_dir()

    output_json_path = out_dir / f"{case_id}_{ts}_erd.json"
    output_docx_path = out_dir / f"{case_id}_{ts}_erd.docx"

    result = compile_erd_graph().invoke(
        {
            "requirement_json_path": resolve_path(case.get("requirement_json_path")),
            "use_llm": bool(case.get("use_llm", True)),
            "use_mermaid": bool(case.get("use_mermaid", False)),
            "fast_table": bool(case.get("fast_table", True)),
            "output_json_path": str(output_json_path),
            "output_docx_path": str(output_docx_path),
        }
    )

    return {
        "status": normalize_status(result),
        "output_json_path": str(result.get("output_json_path") or output_json_path),
        "output_docx_path": str(result.get("erd_docx_path") or output_docx_path),
        "validation_errors": validation_errors_from_result(result),
        "raw_result": result,
    }
