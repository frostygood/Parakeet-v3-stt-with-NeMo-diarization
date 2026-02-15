from typing import Any, Dict, Optional, List, Tuple
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

from app.config import settings


def _get_database_url() -> str:
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    return settings.database_url


def _safe_uuid(value: Optional[str]) -> Optional[UUID]:
    if not value:
        return None
    try:
        return UUID(str(value))
    except ValueError:
        return None


def get_connection() -> psycopg.Connection:
    return psycopg.connect(_get_database_url())


def _json_or_none(value: Any) -> Optional[Json]:
    if value is None:
        return None
    return Json(value)


def save_transcription(data: Dict[str, Any]) -> None:
    query = """
        INSERT INTO public.parakeet (
            task_id,
            user_id,
            raw_text,
            words,
            srt,
            speaker_segments,
            diarization_segments,
            speaker_text,
            language,
            duration,
            processing_time,
            speaker_srt,
            speaker_text_raw
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    task_id = _safe_uuid(str(data.get("task_id") or ""))
    words = data.get("words")
    speaker_segments = data.get("speaker_segments")
    diarization_segments = data.get("diarization_segments")
    speaker_srt = data.get("speaker_srt")
    speaker_text_raw = data.get("speaker_text_raw")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (
                    task_id,
                    data.get("user_id"),
                    data.get("raw_text"),
                    _json_or_none(words),
                    data.get("srt"),
                    _json_or_none(speaker_segments),
                    _json_or_none(diarization_segments),
                    data.get("speaker_text"),
                    data.get("language"),
                    data.get("duration"),
                    data.get("processing_time"),
                    _json_or_none(speaker_srt),
                    _json_or_none(speaker_text_raw),
                ),
            )
        conn.commit()


def create_transcription_stub(task_id: str, user_id: Optional[str]) -> None:
    query = """
        INSERT INTO public.parakeet (
            task_id,
            user_id
        )
        VALUES (%s, %s)
    """

    task_uuid = _safe_uuid(task_id)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (
                    task_uuid,
                    user_id,
                ),
            )
        conn.commit()


def update_transcription(task_id: str, data: Dict[str, Any]) -> bool:
    query = """
        UPDATE public.parakeet
        SET
            raw_text = %s,
            words = %s,
            srt = %s,
            speaker_segments = %s,
            diarization_segments = %s,
            speaker_text = %s,
            language = %s,
            duration = %s,
            processing_time = %s,
            speaker_srt = %s,
            speaker_text_raw = %s
        WHERE id = (
            SELECT id
            FROM public.parakeet
            WHERE task_id = %s
            ORDER BY id DESC
            LIMIT 1
        )
    """

    task_uuid = _safe_uuid(task_id)
    if not task_uuid:
        return False

    words = data.get("words")
    speaker_segments = data.get("speaker_segments")
    diarization_segments = data.get("diarization_segments")
    speaker_srt = data.get("speaker_srt")
    speaker_text_raw = data.get("speaker_text_raw")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (
                    data.get("raw_text"),
                    _json_or_none(words),
                    data.get("srt"),
                    _json_or_none(speaker_segments),
                    _json_or_none(diarization_segments),
                    data.get("speaker_text"),
                    data.get("language"),
                    data.get("duration"),
                    data.get("processing_time"),
                    _json_or_none(speaker_srt),
                    _json_or_none(speaker_text_raw),
                    task_uuid,
                ),
            )
            updated = cur.rowcount > 0
        conn.commit()

    return updated


def delete_transcription(task_id: str) -> None:
    query = """
        DELETE FROM public.parakeet
        WHERE task_id = %s
    """

    task_uuid = _safe_uuid(task_id)
    if not task_uuid:
        return

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (task_uuid,))
        conn.commit()


def fetch_transcription(task_id: str) -> Optional[Dict[str, Any]]:
    query = """
        SELECT
            task_id,
            user_id,
            raw_text,
            words,
            srt,
            speaker_segments,
            diarization_segments,
            speaker_text,
            speaker_text_raw,
            language,
            duration,
            processing_time,
            speaker_srt,
            created_at
        FROM public.parakeet
        WHERE task_id = %s
        ORDER BY id DESC
        LIMIT 1
    """

    task_uuid = _safe_uuid(task_id)
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, (task_uuid,))
            row = cur.fetchone()
            if not row:
                return None
            return dict(row)


def _build_transcriptions_filters(
    task_id_query: Optional[str],
    user_id_query: Optional[str],
) -> Tuple[str, List[Any]]:
    clauses = ["processing_time IS NOT NULL"]
    params: List[Any] = []

    if task_id_query:
        clauses.append("task_id::text ILIKE %s")
        params.append(f"%{task_id_query}%")
    if user_id_query:
        clauses.append("user_id ILIKE %s")
        params.append(f"%{user_id_query}%")

    where_clause = "WHERE " + " AND ".join(clauses) if clauses else ""
    return where_clause, params


def fetch_transcriptions(
    page: int,
    page_size: int = 50,
    task_id_query: Optional[str] = None,
    user_id_query: Optional[str] = None,
) -> List[Dict[str, Any]]:
    offset = max(page - 1, 0) * page_size
    where_clause, params = _build_transcriptions_filters(task_id_query, user_id_query)

    query = f"""
        SELECT
            task_id,
            user_id,
            created_at,
            duration,
            processing_time,
            language
        FROM public.parakeet
        {where_clause}
        ORDER BY created_at DESC
        LIMIT %s
        OFFSET %s
    """

    params.extend([page_size, offset])

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
            return [dict(row) for row in rows]


def count_transcriptions(
    task_id_query: Optional[str] = None,
    user_id_query: Optional[str] = None,
) -> int:
    where_clause, params = _build_transcriptions_filters(task_id_query, user_id_query)

    query = f"""
        SELECT COUNT(*) AS total
        FROM public.parakeet
        {where_clause}
    """

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, params)
            row = cur.fetchone()
            return int(row.get("total") or 0)
