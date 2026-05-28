import os
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]


def result_dir() -> Path:
    path = ROOT_DIR / os.getenv("EVAL_RESULT_DIR", "eval/results")
    path.mkdir(parents=True, exist_ok=True)
    return path


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def resolve_path(path: str | None) -> str | None:
    if not path:
        return None

    p = Path(path)
    if p.is_absolute():
        return str(p)

    return str(ROOT_DIR / p)


def validation_errors_from_result(result: dict[str, Any]) -> list[Any]:
    for key in ["validation_errors", "errors"]:
        value = result.get(key)
        if isinstance(value, list):
            return value

    validation_result = result.get("validation_result")
    if isinstance(validation_result, dict):
        errors = validation_result.get("errors")
        if isinstance(errors, list):
            return errors

    return []


def normalize_status(result: dict[str, Any]) -> str:
    return str(result.get("status") or result.get("result_status") or "UNKNOWN")
