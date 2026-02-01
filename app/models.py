from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from enum import Enum

class TranscriptionRequest(BaseModel):
    language: Optional[str] = "auto"
    enable_diarization: bool = False
    chunk_length_s: float = 60.0

class TranscriptionStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class TranscriptionResponse(BaseModel):
    task_id: str
    status: TranscriptionStatus
    message: str
    result_url: Optional[str] = None
    error: Optional[str] = None

class TranscriptionResult(BaseModel):
    task_id: str
    raw_text: str
    words: List[Dict[str, Any]]
    srt: str
    speaker_srt: List[Dict[str, Any]]
    srt_segments: List[Dict[str, Any]]
    speaker_segments: List[Dict[str, Any]]
    diarization_segments: Optional[List[Dict[str, Any]]] = None
    speaker_text: str
    language: str
    duration: float
    processing_time: float
