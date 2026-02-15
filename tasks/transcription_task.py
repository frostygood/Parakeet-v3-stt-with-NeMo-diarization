import time
from pathlib import Path
from typing import List, Dict, Any, Optional

from app.db import update_transcription
from app.logging_config import get_logger
from app.task_store import task_store
from app.config import settings
from app.result_payload import build_result_record
from app.utils import get_audio_output_path, cleanup_old_uploads
from app.constants import (
    PROGRESS_INIT,
    PROGRESS_AUDIO_EXTRACTED,
    PROGRESS_TRANSCRIBING,
    PROGRESS_DIARIZATION,
    PROGRESS_SAVING,
    DEFAULT_CHUNK_LENGTH_S,
    ALLOWED_VIDEO_EXTENSIONS,
)
from services.transcription import transcription_service
from services.diarization import diarization_service
from services.audio_processor import audio_processor

logger = get_logger(__name__)


def _update_task_progress(task_id: str, progress: int, step: str) -> None:
    task_store.update(
        task_id,
        status="processing",
        progress=progress,
        step=step,
    )


def _prepare_audio_file(file_path: str, task_id: str, temp_files: List[str]) -> str:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    file_ext = path.suffix.lower()
    audio_path = file_path

    if file_ext in ALLOWED_VIDEO_EXTENSIONS:
        _update_task_progress(task_id, PROGRESS_AUDIO_EXTRACTED, "Extracting audio from video")
        audio_path = get_audio_output_path(file_path, suffix="_audio", ext=".wav")
        audio_processor.extract_audio(file_path, audio_path)
        temp_files.append(audio_path)
        logger.info("Audio extracted from video: %s", audio_path)
        return audio_path

    if file_ext != ".wav":
        _update_task_progress(task_id, PROGRESS_AUDIO_EXTRACTED, "Converting audio format")
        audio_path = get_audio_output_path(file_path)
        audio_processor.convert_to_wav(file_path, audio_path)
        temp_files.append(audio_path)
        logger.info("Audio converted to WAV: %s", audio_path)

    return audio_path


def _run_diarization(
    audio_path: str,
    transcription_segments: List[Dict[str, Any]],
    task_id: str,
    enable_diarization: bool,
    num_speakers: Optional[int],
    min_speakers: Optional[int],
    max_speakers: Optional[int],
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if not enable_diarization:
        _update_task_progress(task_id, PROGRESS_DIARIZATION, "Skipping speaker diarization")
        return [], []

    _update_task_progress(task_id, PROGRESS_DIARIZATION, "Performing speaker diarization")
    diarization_segments = diarization_service.diarize(
        audio_path,
        num_speakers=num_speakers,
        min_speakers=min_speakers,
        max_speakers=max_speakers,
    )
    speaker_segments = diarization_service.merge_with_transcription(
        transcription_segments,
        diarization_segments,
    )
    logger.info("Diarization completed: %s speaker segments", len(diarization_segments))
    return diarization_segments, speaker_segments


def process_transcription(
    file_path: str,
    task_id: str,
    language: str = "auto",
    enable_diarization: bool = False,
    user_id: Optional[str] = None,
    num_speakers: Optional[int] = None,
    min_speakers: Optional[int] = None,
    max_speakers: Optional[int] = None,
    chunk_length_s: float = DEFAULT_CHUNK_LENGTH_S,
    max_retries: int = 3,
    retry_delay_s: int = 60,
) -> Dict[str, Any]:
    """
    Background task for audio/video transcription.
    
    Args:
        file_path: Path to uploaded file
        task_id: Unique task identifier
        language: Language code (always 'auto')
        enable_diarization: Enable speaker diarization
        chunk_length_s: Audio chunk length in seconds
        max_retries: Maximum number of retries for transient failures
        retry_delay_s: Delay between retries in seconds
        
    Returns:
        Dict with task results
    """
    for attempt in range(max_retries + 1):
        start_time = time.time()
        temp_files: List[str] = []
        try:
            logger.info(f"Starting transcription task {task_id} for file: {file_path}")
            _update_task_progress(task_id, PROGRESS_INIT, "Preparing file")
            audio_path = _prepare_audio_file(file_path, task_id, temp_files)
            _update_task_progress(task_id, PROGRESS_TRANSCRIBING, "Transcribing audio")
            
            transcription_result = transcription_service.transcribe(
                audio_path=audio_path,
                language=language,
                chunk_length_s=chunk_length_s,
            )
            
            transcription_segments = transcription_result['segments']
            logger.info(
                "Transcription completed: %s segments",
                len(transcription_segments)
            )

            diarization_segments, speaker_segments = _run_diarization(
                audio_path=audio_path,
                transcription_segments=transcription_segments,
                task_id=task_id,
                enable_diarization=enable_diarization,
                num_speakers=num_speakers,
                min_speakers=min_speakers,
                max_speakers=max_speakers,
            )

            _update_task_progress(task_id, PROGRESS_SAVING, "Saving results")

            processing_time = time.time() - start_time

            result_data = build_result_record(
                task_id=task_id,
                user_id=user_id,
                transcription_result=transcription_result,
                speaker_segments=speaker_segments,
                diarization_segments=diarization_segments,
                language=language,
                processing_time=processing_time,
            )

            updated = update_transcription(task_id, result_data)
            if not updated:
                raise RuntimeError("Failed to update transcription record")

            audio_processor.cleanup_files(*temp_files, file_path)

            removed = cleanup_old_uploads(settings.upload_dir)
            if removed:
                logger.info("Removed %s old uploads", removed)

            logger.info(f"Task {task_id} completed in {processing_time:.2f}s")

            task_store.set_result(task_id, {'task_id': task_id})
            return result_data
            
        except Exception as exc:
            logger.error(f"Task {task_id} failed: {exc}", exc_info=True)
            audio_processor.cleanup_files(*temp_files)
            
            if attempt < max_retries:
                logger.info(
                    f"Retrying task {task_id} (attempt {attempt + 1}/{max_retries})"
                )
                task_store.update(
                    task_id,
                    status="processing",
                    step=f"Retrying transcription ({attempt + 1}/{max_retries})",
                )
                time.sleep(retry_delay_s)
                continue
            
            audio_processor.cleanup_files(file_path)
            task_store.set_error(task_id, str(exc))
            return {
                'task_id': task_id,
                'status': 'failed',
                'error': str(exc),
            }

    return {
        'task_id': task_id,
        'status': 'failed',
        'error': 'Task cancelled',
    }
