import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any

from agents.ts_prompt import SYSTEM_PROMPT, build_prompt
from services.llm_client import call_llm_messages

TS_MAX_TOKENS = int(os.getenv("TS_MAX_TOKENS", "16384"))
TS_RAW_OUTPUT_DIR = os.getenv("TS_RAW_OUTPUT_DIR", "./json_temp/ts_raw_outputs")


def _strip_markdown_json(raw_output: str) -> str:
    text = raw_output.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:])
    if text.endswith("```"):
        text = text[:-3].strip()
    return text


def parse_and_validate(raw_output: str) -> tuple[dict[str, Any] | None, str]:
    try:
        data = json.loads(_strip_markdown_json(raw_output))
    except json.JSONDecodeError as exc:
        return None, f"JSON 파싱 실패: {exc}"

    if "scenarios" not in data:
        return None, "필수 키 누락: 'scenarios'"
    if "cases" not in data:
        return None, "필수 키 누락: 'cases'"

    for i, scenario in enumerate(data["scenarios"]):
        for key in ["scenario_id", "scenario_name", "scenario_description", "test_cases"]:
            if key not in scenario:
                return None, f"scenarios[{i}] 필수 키 누락: '{key}'"
        for j, test_case in enumerate(scenario["test_cases"]):
            for key in ["test_case_id", "test_case_description", "test_procedure", "scenario_detail"]:
                if key not in test_case:
                    return None, f"scenarios[{i}].test_cases[{j}] 필수 키 누락: '{key}'"

    required_case_keys = [
        "round",
        "scenario_id",
        "scenario_name",
        "test_case_id",
        "sequence",
        "process_content",
        "test_item",
        "input_data",
        "expected_result",
        "screen_id",
    ]
    for i, case in enumerate(data["cases"]):
        for key in required_case_keys:
            if key not in case:
                return None, f"cases[{i}] 필수 키 누락: '{key}'"
        if case.get("test_result") is not None:
            return None, f"cases[{i}].test_result는 설계단계에서 null이어야 합니다. (hallucination 감지)"
        if not isinstance(case.get("input_data"), str):
            return None, f"cases[{i}].input_data는 문자열이어야 합니다. (현재: {type(case.get('input_data')).__name__})"

    for scenario in data["scenarios"]:
        for test_case in scenario["test_cases"]:
            test_case_id = test_case["test_case_id"]
            procedure_count = len(test_case["test_procedure"])
            case_count = sum(1 for case in data["cases"] if case["test_case_id"] == test_case_id)
            if procedure_count != case_count:
                print(
                    f"[WARN] {test_case_id}: test_procedure 항목 수({procedure_count})와 "
                    f"cases 행 수({case_count})가 일치하지 않습니다."
                )

    return data, ""


def fill_missing_cases(data: dict[str, Any]) -> dict[str, Any]:
    filled_count = 0

    for scenario in data["scenarios"]:
        scenario_id = scenario["scenario_id"]
        scenario_name = scenario["scenario_name"]

        for test_case in scenario["test_cases"]:
            test_case_id = test_case["test_case_id"]
            procedures = test_case.get("test_procedure", [])
            existing = {
                case["sequence"]: case
                for case in data["cases"]
                if case["test_case_id"] == test_case_id
            }

            if len(existing) >= len(procedures):
                continue

            template = existing[max(existing.keys())] if existing else {}
            for sequence in range(1, len(procedures) + 1):
                if sequence in existing:
                    continue
                data["cases"].append(
                    {
                        "round": template.get("round", 1),
                        "scenario_id": scenario_id,
                        "scenario_name": scenario_name,
                        "test_case_id": test_case_id,
                        "sequence": sequence,
                        "process_content": procedures[sequence - 1],
                        "test_item": "(자동 보완 필요)",
                        "precondition": None,
                        "input_data": "(자동 보완 필요)",
                        "expected_result": "(자동 보완 필요)",
                        "screen_id": template.get("screen_id", ""),
                        "test_result": None,
                        "note": "자동 보완된 행입니다. 내용을 검토하고 수정하세요.",
                    }
                )
                filled_count += 1
                print(f"[FIX] {test_case_id} sequence {sequence} 자동 보완")

    if filled_count > 0:
        data["cases"].sort(key=lambda case: (case["scenario_id"], case["test_case_id"], case["sequence"]))
        print(f"[INFO] 총 {filled_count}개 행 자동 보완 완료")
    else:
        print("[INFO] cases 누락 없음. 자동 보완 불필요.")

    return data


def save_raw_output(requirement_id: str, raw_output: str) -> str:
    output_dir = Path(TS_RAW_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_id = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in requirement_id)
    output_path = output_dir / f"{safe_id}_raw_output.txt"
    output_path.write_text(raw_output, encoding="utf-8")
    return str(output_path)


def generate_test_scenarios(
    requirement_doc: dict[str, Any],
    ui_screens_raw: list[str] | None = None,
    *,
    max_retries: int = 0,
) -> dict[str, Any]:
    requirements = requirement_doc.get("requirements", [])
    all_scenarios: list[dict[str, Any]] = []
    all_cases: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for index, requirement in enumerate(requirements, start=1):
        requirement_id = requirement.get("requirement_id", f"REQ-{index}")
        print(f"\n[INFO] [{index}/{len(requirements)}] {requirement_id} 처리 중...")

        single_req_json = json.dumps({"requirements": [requirement]}, ensure_ascii=False, indent=2)
        messages = build_prompt(single_req_json, ui_screens_raw)
        full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages

        parsed = None
        last_error = ""
        started_at = time.time()
        for _ in range(max_retries + 1):
            try:
                raw_output = call_llm_messages(
                    full_messages,
                    temperature=0,
                    max_tokens=TS_MAX_TOKENS,
                    timeout=600,
                )
            except Exception as exc:
                last_error = f"LLM 호출 실패: {exc}"
                break

            parsed, last_error = parse_and_validate(raw_output)
            if not last_error and parsed:
                break
            raw_path = save_raw_output(str(requirement_id), raw_output)
            print(f"[FAIL] {requirement_id} 검증 실패: {last_error}")
            print(f"[INFO] raw output 저장됨: {raw_path}")
            full_messages.append({"role": "assistant", "content": raw_output})
            full_messages.append(
                {
                    "role": "user",
                    "content": f"위 응답은 오류가 있습니다: {last_error}. 스키마에 맞는 JSON만 다시 출력하세요.",
                }
            )

        if not parsed:
            errors.append({"requirement_id": requirement_id, "error": last_error})
            continue

        parsed = fill_missing_cases(parsed)
        all_scenarios.extend(parsed.get("scenarios", []))
        all_cases.extend(parsed.get("cases", []))
        print(f"[PASS] {requirement_id} 통합 시험 시나리오 생성 완료 ({time.time() - started_at:.1f}초)")

    return {
        "scenarios": all_scenarios,
        "cases": all_cases,
        "errors": errors,
        "summary": summarize_test_scenarios({"scenarios": all_scenarios, "cases": all_cases}),
    }


def summarize_test_scenarios(data: dict[str, Any]) -> dict[str, Any]:
    counter = Counter(case["test_case_id"] for case in data.get("cases", []))
    return {
        "scenario_count": len(data.get("scenarios", [])),
        "case_row_count": len(data.get("cases", [])),
        "case_rows_by_test_case": dict(counter),
    }
