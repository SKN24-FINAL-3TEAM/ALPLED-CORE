from typing import Any

from eval.runners.common import result_dir, resolve_path, timestamp, validation_errors_from_result, normalize_status


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    from workflows.architecture_workflow import compile_architecture_graph

    case_id = case["case_id"]
    ts = timestamp()
    out_dir = result_dir()

    output_json_path = out_dir / f"{case_id}_{ts}_architecture.json"
    output_md_path = out_dir / f"{case_id}_{ts}_architecture.md"
    output_docx_path = out_dir / f"{case_id}_{ts}_architecture.docx"
    output_image_path = out_dir / f"{case_id}_{ts}_architecture.png"

    result = compile_architecture_graph().invoke(
        {
            "requirement_json_path": resolve_path(case.get("requirement_json_path")),
            "infra_spec_path": resolve_path(case.get("infra_spec_path")),
            "render_image": bool(case.get("render_image", False)),
            "output_json_path": str(output_json_path),
            "output_md_path": str(output_md_path),
            "output_docx_path": str(output_docx_path),
            "output_image_path": str(output_image_path),
        }
    )

    return {
        "status": normalize_status(result),
        "output_json_path": str(result.get("output_json_path") or output_json_path),
        "output_docx_path": str(result.get("output_docx_path") or output_docx_path),
        "validation_errors": validation_errors_from_result(result),
        "raw_result": result,
    }
