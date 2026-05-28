import json
from pathlib import Path
from typing import Any


def load_json_safe(path: str | None) -> dict[str, Any] | list[Any] | None:
    if not path:
        return None

    file_path = Path(path)
    if not file_path.exists():
        return None

    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def stringify(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return str(value)


def calc_keyword_hit_rate(text: str, expected_keywords: list[str]) -> float:
    if not expected_keywords:
        return 0.0

    lowered = text.lower()
    hit_count = sum(1 for keyword in expected_keywords if keyword.lower() in lowered)
    return round(hit_count / len(expected_keywords), 4)


def find_values_by_keys(obj: Any, target_keys: set[str]) -> list[str]:
    found: list[str] = []

    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in target_keys and value:
                found.append(str(value))
            found.extend(find_values_by_keys(value, target_keys))

    elif isinstance(obj, list):
        for item in obj:
            found.extend(find_values_by_keys(item, target_keys))

    return found


def calc_name_hit_rate(actual_names: list[str], expected_names: list[str]) -> float:
    if not expected_names:
        return 0.0

    actual_lower = {name.lower() for name in actual_names}
    hit_count = 0

    for expected in expected_names:
        if expected.lower() in actual_lower:
            hit_count += 1

    return round(hit_count / len(expected_names), 4)


def calc_basic_score(
    json_valid: bool,
    validation_pass: bool,
    name_hit_rate: float,
    keyword_hit_rate: float,
) -> float:
    score = 0.0

    if json_valid:
        score += 25
    if validation_pass:
        score += 25

    score += name_hit_rate * 30
    score += keyword_hit_rate * 20

    return round(score, 2)
