import os
import json
import time
from pathlib import Path
from typing import List, Dict, Any

from app.config import settings
from app.logging_config import get_logger
from app.task_store import task_store
from app.utils import get_audio_output_path
from app.constants import (
    PROGRESS_INIT,
    PROGRESS_AUDIO_EXTRACTED,
    PROGRESS_TRANSCRIBING,
    PROGRESS_DIARIZATION,
    PROGRESS_SAVING,
    DEFAULT_CHUNK_LENGTH_S
)
from services.transcription import transcription_service
from services.diarization import diarization_service
from services.audio_processor import audio_processor

logger = get_logger(__name__)


def format_time(seconds: float) -> str:
    """
    Format seconds to SRT time format (HH:MM:SS,mmm).
    
    Args:
        seconds: Time in seconds
        
    Returns:
        Formatted time string
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def generate_srt(segments: List[Dict[str, Any]]) -> str:
    """
    Generate SRT subtitle format from segments.
    
    Args:
        segments: List of transcription segments
        
    Returns:
        SRT formatted string
    """
    srt_lines = []
    for i, seg in enumerate(segments, 1):
        start = format_time(seg['start'])
        end = format_time(seg['end'])
        text = seg['text'].strip()
        
        if 'speaker' in seg:
            text = f"[{seg['speaker']}] {text}"
        
        srt_lines.append(f"{i}")
        srt_lines.append(f"{start} --> {end}")
        srt_lines.append(text)
        srt_lines.append("")
    
    return "\n".join(srt_lines)


def process_transcription(
    file_path: str,
    task_id: str,
    language: str = "auto",
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
            task_store.update(
                task_id,
                status="processing",
                progress=PROGRESS_INIT,
                step="Preparing file",
            )
            
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")
            
            file_ext = Path(file_path).suffix.lower()
            audio_path = file_path
            
            if file_ext in ['.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv']:
                task_store.update(
                    task_id,
                    status="processing",
                    progress=PROGRESS_AUDIO_EXTRACTED,
                    step="Extracting audio from video",
                )
                audio_path = get_audio_output_path(file_path, suffix='_audio', ext='.wav')
                audio_processor.extract_audio(file_path, audio_path)
                temp_files.append(audio_path)
                logger.info(f"Audio extracted from video: {audio_path}")
            elif file_ext != '.wav':
                task_store.update(
                    task_id,
                    status="processing",
                    progress=PROGRESS_AUDIO_EXTRACTED,
                    step="Converting audio format",
                )
                audio_path = get_audio_output_path(file_path)
                audio_processor.convert_to_wav(file_path, audio_path)
                temp_files.append(audio_path)
                logger.info(f"Audio converted to WAV: {audio_path}")
            
            task_store.update(
                task_id,
                status="processing",
                progress=PROGRESS_TRANSCRIBING,
                step="Transcribing audio",
            )
            
            transcription_result = transcription_service.transcribe(
                audio_path=audio_path,
                language=language,
                chunk_length_s=chunk_length_s,
            )
            
            segments = transcription_result['segments']
            logger.info(f"Transcription completed: {len(segments)} segments")
            
            task_store.update(
                task_id,
                status="processing",
                progress=PROGRESS_DIARIZATION,
                step="Performing speaker diarization",
            )
            
            diarization_segments = diarization_service.diarize(audio_path)
            speaker_segments = diarization_service.merge_with_transcription(
                transcription_result['segments'],
                diarization_segments,
            )
            logger.info(f"Diarization completed: {len(diarization_segments)} speaker segments")
            
            task_store.update(
                task_id,
                status="processing",
                progress=PROGRESS_SAVING,
                step="Saving results",
            )
            
            transcription_dir = Path(settings.transcription_dir)
            transcription_dir.mkdir(parents=True, exist_ok=True)
            result_file = transcription_dir / f"{task_id}.json"

            raw_text = transcription_result.get('raw_text') or transcription_result.get('text', '')
            words = transcription_result.get('words', [])
            srt_segments = transcription_result.get('segments', [])
            srt_text = generate_srt(srt_segments)

            speaker_lines = []
            for seg in speaker_segments:
                line = f"[{seg['start']:.2f} - {seg['end']:.2f}]"
                if 'speaker' in seg:
                    line += f" {seg['speaker']}:"
                line += f" {seg['text']}"
                speaker_lines.append(line)
            speaker_text = "\n".join(speaker_lines)

            processing_time = time.time() - start_time

            result_data = {
                'task_id': task_id,
                'raw_text': raw_text,
                'words': words,
                'srt': srt_text,
                'srt_segments': srt_segments,
                'speaker_segments': speaker_segments,
                'diarization_segments': diarization_segments,
                'speaker_text': speaker_text,
                'language': transcription_result.get('language', language),
                'duration': transcription_result.get('duration', 0.0),
                'processing_time': processing_time,
            }

            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(result_data, f, ensure_ascii=False, indent=2)

            logger.info(f"Results saved to: {result_file}")

            audio_processor.cleanup_files(*temp_files, file_path)

            logger.info(f"Task {task_id} completed in {processing_time:.2f}s")

            result_payload = {
                'task_id': task_id,
                'status': 'completed',
                'result_file': str(result_file),
                'raw_text': raw_text,
                'words': words,
                'srt': srt_text,
                'srt_segments': srt_segments,
                'speaker_segments': speaker_segments,
                'diarization_segments': diarization_segments,
                'speaker_text': speaker_text,
                'language': transcription_result.get('language', language),
                'duration': transcription_result.get('duration', 0.0),
                'processing_time': processing_time,
            }
            task_store.set_result(task_id, result_payload)
            return result_payload
            
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
