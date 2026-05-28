from typing import Any
from pathlib import Path

from eval.runners.common import result_dir, resolve_path, timestamp, validation_errors_from_result, normalize_status


def _ensure_erd_docx(case: dict[str, Any], case_id: str, ts: str, out_dir) -> str:
    erd_docx_path = resolve_path(case.get("erd_docx_path"))
    if erd_docx_path and Path(erd_docx_path).exists():
        return erd_docx_path
    if erd_docx_path:
        raise FileNotFoundError(f"지정한 ERD 설계서 DOCX를 찾지 못했습니다: {erd_docx_path}")

    from workflows.erd_workflow import compile_erd_graph

    generated_erd_json_path = out_dir / f"{case_id}_{ts}_db_source_erd.json"
    generated_erd_docx_path = out_dir / f"{case_id}_{ts}_db_source_erd.docx"

    erd_result = compile_erd_graph().invoke(
        {
            "requirement_json_path": resolve_path(case.get("requirement_json_path")),
            "use_llm": bool(case.get("generate_erd_with_llm", False)),
            "use_mermaid": bool(case.get("use_mermaid", False)),
            "fast_table": bool(case.get("fast_table", True)),
            "output_json_path": str(generated_erd_json_path),
            "output_docx_path": str(generated_erd_docx_path),
        }
    )
    errors = validation_errors_from_result(erd_result)
    if normalize_status(erd_result).upper() != "VALID" or errors:
        raise RuntimeError(f"DB eval용 ERD 생성 실패: {errors}")

    return str(erd_result.get("erd_docx_path") or generated_erd_docx_path)


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
            "erd_docx_path": _ensure_erd_docx(case, case_id, ts, out_dir),
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
