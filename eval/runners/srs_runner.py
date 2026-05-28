from types import SimpleNamespace
from typing import Any

from eval.runners.common import result_dir, resolve_path, timestamp


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    from main_generate_srs import generate_mode, modify_mode

    case_id = case["case_id"]
    ts = timestamp()
    out_dir = result_dir()

    output_json_path = out_dir / f"{case_id}_{ts}_srs.json"
    output_reqs_path = out_dir / f"{case_id}_{ts}_srs_final_reqs.json"

    mode = case.get("mode", "generate")

    if mode == "modify":
        args = SimpleNamespace(
            existing_reqs_path=resolve_path(case.get("existing_reqs_path")),
            instruction=case.get("instruction"),
            instruction_file=resolve_path(case.get("instruction_file")),
            output_json_path=str(output_json_path),
            output_reqs_path=str(output_reqs_path),
            save_docx=bool(case.get("save_docx", False)),
        )
        modify_mode(args)
    else:
        args = SimpleNamespace(
            rfp_json_path=resolve_path(case.get("rfp_json_path")),
            minutes_path=resolve_path(case.get("minutes_path")),
            output_json_path=str(output_json_path),
            output_reqs_path=str(output_reqs_path),
            save_docx=bool(case.get("save_docx", False)),
        )
        generate_mode(args)

    return {
        "status": "VALID",
        "output_json_path": str(output_json_path),
        "output_docx_path": "",
        "validation_errors": [],
        "raw_result": {
            "output_json_path": str(output_json_path),
            "output_reqs_path": str(output_reqs_path),
        },
    }
