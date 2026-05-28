import json
import re
from typing import Any


def extract_json(value: str) -> Any:
    text = str(value or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"```json\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))

    match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))

    raise ValueError("LLM 응답에서 JSON을 찾지 못했습니다.")


def strip_mermaid_block(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"^`{1,3}\s*mermaid\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"`{1,3}\s*$", "", text)
    text = text.replace("```mermaid", "").replace("```", "")
    return text.strip()
