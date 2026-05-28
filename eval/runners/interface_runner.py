from typing import Any

from eval.runners.common import result_dir, resolve_path, timestamp, validation_errors_from_result, normalize_status


def _resolve_paths(paths: str | list[str] | None) -> str | list[str] | None:
    if isinstance(paths, list):
        return [resolve_path(path) for path in paths]
    return resolve_path(paths)


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    from workflows.interface_workflow import compile_interface_graph

    case_id = case["case_id"]
    ts = timestamp()
    out_dir = result_dir()

    output_json_path = out_dir / f"{case_id}_{ts}_interface.json"
    output_docx_path = out_dir / f"{case_id}_{ts}_interface.docx"
    work_dir = out_dir / f"{case_id}_{ts}_interface_work"

    result = compile_interface_graph().invoke(
        {
            "requirement_paths": _resolve_paths(case.get("requirement_paths") or case.get("requirement_path")),
            "image_paths": _resolve_paths(case.get("image_paths") or case.get("image_path")),
            "output_json_path": str(output_json_path),
            "output_docx_path": str(output_docx_path),
            "work_dir": str(work_dir),
            "max_images": case.get("max_images", 1),
        }
    )

    return {
        "status": normalize_status(result),
        "output_json_path": str(result.get("output_json_path") or output_json_path),
        "output_docx_path": str(result.get("output_docx_path") or output_docx_path),
        "validation_errors": validation_errors_from_result(result),
        "raw_result": result,
    }
