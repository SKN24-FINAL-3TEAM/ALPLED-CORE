import os
import time
from typing import Any

from qdrant_client.models import FieldCondition, Filter, MatchValue

from eval.metrics import calc_keyword_hit_rate, calc_rank_quality


def _payload_text(payload: dict[str, Any]) -> str:
    values = [
        payload.get("text", ""),
        payload.get("title", ""),
        payload.get("section", ""),
        payload.get("source", ""),
        payload.get("source_name", ""),
        payload.get("doc_type", ""),
        payload.get("chunk_type", ""),
    ]
    return " ".join(str(value) for value in values if value)


def _build_filter(case: dict[str, Any]) -> Filter | None:
    conditions = []

    for key, value in (case.get("filters") or {}).items():
        if value is not None:
            conditions.append(FieldCondition(key=key, match=MatchValue(value=value)))

    if case.get("active_only", True):
        conditions.append(FieldCondition(key="is_active", match=MatchValue(value=True)))

    if not conditions:
        return None

    return Filter(must=conditions)


def _first_expected_rank(rows: list[dict[str, Any]], expected_keywords: list[str]) -> int | None:
    if not expected_keywords:
        return None

    for idx, row in enumerate(rows, start=1):
        text = row.get("text", "").lower()
        if all(keyword.lower() in text for keyword in expected_keywords):
            return idx

    return None


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    from rag.qdrant_config import COLLECTION_NAME, EMBED_MODEL_NAME, get_client, get_embedder

    query = case["query"]
    top_k = int(case.get("top_k", os.getenv("EVAL_EMBED_TOP_K", "5")))
    expected_keywords = case.get("expected_keywords", [])

    embedder = get_embedder()
    started = time.perf_counter()
    query_vector = embedder.encode(query, normalize_embeddings=True).tolist()
    embedding_elapsed_sec = round(time.perf_counter() - started, 4)

    result = get_client().query_points(
        collection_name=case.get("collection_name") or COLLECTION_NAME,
        query=query_vector,
        query_filter=_build_filter(case),
        limit=top_k,
        with_payload=True,
    )

    rows = []
    for point in result.points:
        payload = point.payload or {}
        rows.append(
            {
                "score": point.score,
                "text": _payload_text(payload),
                "metadata": payload,
            }
        )

    combined_text = "\n".join(row["text"] for row in rows)
    first_rank = _first_expected_rank(rows, expected_keywords)
    hit = first_rank is not None or bool(expected_keywords and calc_keyword_hit_rate(combined_text, expected_keywords) > 0)

    return {
        "status": "VALID" if rows else "INVALID",
        "output_json_path": "",
        "output_docx_path": "",
        "validation_errors": [] if rows else ["검색 결과가 없습니다."],
        "raw_result": {
            "embedding_model": EMBED_MODEL_NAME,
            "collection_name": case.get("collection_name") or COLLECTION_NAME,
            "query": query,
            "top_k": top_k,
            "rows": rows,
        },
        "selection_metrics": {
            "search_accuracy": 100.0 if hit else 0.0,
            "search_rank_quality": calc_rank_quality(first_rank, top_k),
            "search_result_relevance": round(calc_keyword_hit_rate(combined_text, expected_keywords) * 100, 2),
            "embedding_generation_speed_sec": embedding_elapsed_sec,
            "embedding_generation_speed_score": 0.0,
            "embedding_deployment_efficiency": float(os.getenv("EVAL_EMBED_DEPLOYMENT_EFFICIENCY_SCORE", "0")),
            "first_expected_rank": first_rank or "",
            "retrieved_count": len(rows),
        },
    }
