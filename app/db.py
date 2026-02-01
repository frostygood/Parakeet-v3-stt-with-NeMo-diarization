from typing import Any, Dict, Optional
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


def save_transcription(data: Dict[str, Any]) -> None:
    query = """
        INSERT INTO public.parakeet (
            task_id,
            raw_text,
            words,
            srt,
            speaker_segments,
            diarization_segments,
            speaker_text,
            language,
            duration,
            processing_time,
            speaker_srt
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    task_id = _safe_uuid(str(data.get("task_id") or ""))
    words = data.get("words")
    speaker_segments = data.get("speaker_segments")
    diarization_segments = data.get("diarization_segments")
    speaker_srt = data.get("speaker_srt")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (
                    task_id,
                    data.get("raw_text"),
                    Json(words) if words is not None else None,
                    data.get("srt"),
                    Json(speaker_segments) if speaker_segments is not None else None,
                    Json(diarization_segments) if diarization_segments is not None else None,
                    data.get("speaker_text"),
                    data.get("language"),
                    data.get("duration"),
                    data.get("processing_time"),
                    Json(speaker_srt) if speaker_srt is not None else None,
                ),
            )
        conn.commit()


def fetch_transcription(task_id: str) -> Optional[Dict[str, Any]]:
    query = """
        SELECT
            task_id,
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
