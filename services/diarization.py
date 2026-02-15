import torch
from pyannote.audio import Pipeline
from typing import List, Dict, Any, Optional
import os

from app.logging_config import get_logger

logger = get_logger(__name__)


class DiarizationService:
    """Speaker diarization service using pyannote.audio."""
    
    _instance = None
    _pipeline = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._pipeline is None:
            self._load_pipeline()
    
    def _load_pipeline(self):
        """Load pyannote.audio diarization pipeline."""
        try:
            logger.info("Loading diarization pipeline from pyannote/speaker-diarization-3.1")
            
            self._pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=os.getenv("HF_TOKEN")
            )
            
            device = torch.device("cpu")
            self._pipeline.to(device)
            
            logger.info("Diarization pipeline loaded successfully on CPU")
            
        except Exception as e:
            logger.error(f"Error loading diarization pipeline: {e}", exc_info=True)
            raise
    
    def diarize(
        self,
        audio_path: str,
        num_speakers: Optional[int] = None,
        min_speakers: Optional[int] = None,
        max_speakers: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Perform speaker diarization on audio file.
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            List of speaker segments with start, end, and speaker labels
            
        Raises:
            Exception: If diarization fails
        """
        try:
            logger.debug(f"Starting diarization for: {audio_path}")
            
            pipeline_kwargs: Dict[str, Any] = {}
            if num_speakers is not None:
                pipeline_kwargs["num_speakers"] = num_speakers
            else:
                if min_speakers is not None:
                    pipeline_kwargs["min_speakers"] = min_speakers
                if max_speakers is not None:
                    pipeline_kwargs["max_speakers"] = max_speakers

            if pipeline_kwargs:
                diarization = self._pipeline(audio_path, **pipeline_kwargs)
            else:
                diarization = self._pipeline(audio_path)
            
            speakers = []
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                speakers.append({
                    'start': turn.start,
                    'end': turn.end,
                    'speaker': speaker
                })
            
            logger.debug(f"Diarization completed: {len(speakers)} speaker segments")
            
            return speakers
            
        except Exception as e:
            logger.error(f"Diarization error: {e}", exc_info=True)
            raise
    
    def merge_with_transcription(
        self,
        transcription_segments: List[Dict],
        speaker_segments: List[Dict]
    ) -> List[Dict[str, Any]]:
        """
        Merge transcription segments with speaker labels.
        
        Args:
            transcription_segments: List of transcribed segments
            speaker_segments: List of speaker diarization segments
            
        Returns:
            List of merged segments with speaker labels
        """
        merged = []
        
        for trans_seg in transcription_segments:
            trans_start = trans_seg['start']
            trans_end = trans_seg['end']
            trans_text = trans_seg['text']
            
            speaker = "UNKNOWN"
            max_overlap = 0
            
            for spk_seg in speaker_segments:
                spk_start = spk_seg['start']
                spk_end = spk_seg['end']
                
                overlap_start = max(trans_start, spk_start)
                overlap_end = min(trans_end, spk_end)
                overlap = max(0, overlap_end - overlap_start)
                
                if overlap > max_overlap:
                    max_overlap = overlap
                    speaker = spk_seg['speaker']
            
            merged.append({
                'start': trans_start,
                'end': trans_end,
                'text': trans_text,
                'speaker': speaker
            })
        
        logger.debug(f"Merged {len(merged)} segments with speaker labels")
        
        return merged


diarization_service = DiarizationService()
