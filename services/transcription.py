import os
import re
import onnxruntime as ort
from typing import List, Dict, Any, Optional
from pydub import AudioSegment
import onnx_asr

from app.logging_config import get_logger
from app.constants import SAMPLE_RATE, CHANNELS, DEFAULT_CHUNK_LENGTH_S

logger = get_logger(__name__)


class ParakeetTranscriptionService:
    """Parakeet v3 transcription service using onnx_asr."""
    
    _instance = None
    _model = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._model is None:
            self._load_model()
    
    def _load_model(self):
        """Load Parakeet v3 model using onnx_asr."""
        try:
            model_id = "nemo-parakeet-tdt-0.6b-v3"
            
            logger.info(f"Loading Parakeet v3 model: {model_id}")
            
            # Get available providers
            providers_to_try = []
            available_providers = ort.get_available_providers()
            
            if 'TensorrtExecutionProvider' in available_providers:
                providers_to_try.append('TensorrtExecutionProvider')
            if 'CUDAExecutionProvider' in available_providers:
                providers_to_try.append('CUDAExecutionProvider')
            
            # Always add CPU as fallback
            providers_to_try.append('CPUExecutionProvider')
            
            sess_options = ort.SessionOptions()
            sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            
            # Load model
            self._model = onnx_asr.load_model(
                model_id,
                quantization="int8",
                providers=providers_to_try,
                sess_options=sess_options
            ).with_timestamps()
            
            logger.info("Parakeet v3 model loaded successfully on CPU")
            
        except Exception as e:
            logger.error(f"Error loading Parakeet model: {e}", exc_info=True)
            raise
    
    def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        chunk_length_s: float = DEFAULT_CHUNK_LENGTH_S,
    ) -> Dict[str, Any]:
        """
        Transcribe audio file using Parakeet v3.
        
        Args:
            audio_path: Path to audio file
            language: Language code (not used by onnx_asr)
            chunk_length_s: Audio chunk length in seconds
            
        Returns:
            Dict with keys: text, segments, language, duration
            
        Raises:
            Exception: If transcription fails
        """
        try:
            logger.debug(f"Transcribing file: {audio_path}")
            
            # Load audio for duration
            audio = AudioSegment.from_file(audio_path)
            audio = audio.set_frame_rate(SAMPLE_RATE).set_channels(CHANNELS)
            duration = len(audio) / 1000.0
            
            logger.debug(f"Audio duration: {duration:.2f}s")
            logger.debug("Starting transcription with onnx_asr")
            
            words: List[Dict[str, Any]] = []
            texts: List[str] = []
            temp_paths: List[str] = []

            try:
                chunk_length_s = max(chunk_length_s, 1.0)
                chunk_length_ms = int(chunk_length_s * 1000)
                if duration <= chunk_length_s:
                    result = self._model.recognize(audio_path)
                    chunk_text = result.text if hasattr(result, "text") else str(result)
                    chunk_text = self._clean_text(chunk_text)
                    texts.append(chunk_text)
                    words.extend(self._extract_words(result, duration, chunk_text))
                else:
                    logger.info(
                        "Audio is %.2fs, chunking into %.2fs pieces",
                        duration,
                        chunk_length_s,
                    )
                    chunk_index = 0
                    for start_ms in range(0, int(duration * 1000), chunk_length_ms):
                        end_ms = min(start_ms + chunk_length_ms, int(duration * 1000))
                        chunk = audio[start_ms:end_ms]
                        chunk = chunk.set_frame_rate(SAMPLE_RATE).set_channels(CHANNELS)
                        chunk_duration = len(chunk) / 1000.0
                        chunk_path = f"{audio_path}_chunk_{chunk_index}.wav"
                        temp_paths.append(chunk_path)
                        chunk.export(chunk_path, format="wav", codec="pcm_s16le")

                        result = self._model.recognize(chunk_path)
                        chunk_text = result.text if hasattr(result, "text") else str(result)
                        chunk_text = self._clean_text(chunk_text)
                        texts.append(chunk_text)

                        chunk_words = self._extract_words(
                            result,
                            chunk_duration,
                            chunk_text,
                        )
                        offset = start_ms / 1000.0
                        for word in chunk_words:
                            word['start'] += offset
                            word['end'] += offset
                        words.extend(chunk_words)
                        chunk_index += 1
            finally:
                for path in temp_paths:
                    try:
                        if os.path.exists(path):
                            os.remove(path)
                    except OSError:
                        logger.debug("Failed to remove temp chunk %s", path)

            raw_text = self._clean_text(" ".join([t for t in texts if t]))
            if not words:
                words = self._fallback_words(raw_text, duration)
            else:
                words.sort(key=lambda item: item['start'])

            segments = self._build_segments_from_words(words, raw_text, duration)

            logger.debug(f"Transcription completed: {len(segments)} segments")

            return {
                'raw_text': raw_text,
                'text': raw_text,
                'words': words,
                'segments': segments,
                'language': language or 'auto',
                'duration': duration
            }
            
        except Exception as e:
            logger.error(f"Transcription error: {e}", exc_info=True)
            raise

    @staticmethod
    def _clean_text(text: str) -> str:
        if not text:
            return ""
        cleaned = text.replace("\u2581", " ")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def _extract_words(
        self,
        result: Any,
        duration: float,
        fallback_text: str
    ) -> List[Dict[str, Any]]:
        tokens = getattr(result, "tokens", None)
        timestamps = getattr(result, "timestamps", None)
        if not tokens or not timestamps:
            return self._fallback_words(fallback_text, duration)

        words: List[Dict[str, Any]] = []
        current_word = ""
        current_start: Optional[float] = None
        last_time: Optional[float] = None

        for token, timestamp in zip(tokens, timestamps):
            if not isinstance(timestamp, (int, float)):
                continue
            token_text = token.replace("\u2581", " ")
            if token.startswith("\u2581") or not current_word:
                if current_word:
                    words.append({
                        'word': current_word,
                        'start': float(current_start or 0.0),
                        'end': float(timestamp),
                    })
                current_word = token_text.strip()
                current_start = float(timestamp)
            else:
                current_word += token_text
            last_time = float(timestamp)

        if current_word:
            end_time = float(last_time) if last_time is not None else duration
            words.append({
                'word': current_word,
                'start': float(current_start or 0.0),
                'end': end_time,
            })

        words = [word for word in words if word['word']]

        if words:
            for idx in range(len(words) - 1):
                next_start = words[idx + 1]['start']
                min_end = words[idx]['start'] + 0.05
                words[idx]['end'] = max(next_start, min_end)

            last_word = words[-1]
            min_end = last_word['start'] + 0.05
            if duration > 0:
                last_word['end'] = max(min_end, duration)
            else:
                last_word['end'] = max(min_end, last_word['end'])

        estimated_count = self._estimate_word_count(fallback_text)
        if estimated_count and len(words) < max(3, estimated_count // 4):
            return self._fallback_words(fallback_text, duration)

        return words

    def _fallback_words(self, text: str, duration: float) -> List[Dict[str, Any]]:
        cleaned = self._clean_text(text)
        parts = re.findall(r"\S+", cleaned)
        if not parts:
            return []
        step = duration / len(parts) if duration > 0 else 0.0
        words: List[Dict[str, Any]] = []
        for idx, part in enumerate(parts):
            start = step * idx
            end = step * (idx + 1) if idx + 1 < len(parts) else duration
            if end <= start:
                end = start + 0.05
            words.append({
                'word': part,
                'start': start,
                'end': end,
            })
        return words

    @staticmethod
    def _estimate_word_count(text: str) -> int:
        if not text:
            return 0
        return len(re.findall(r"\S+", text))

    def _build_segments_from_words(
        self,
        words: List[Dict[str, Any]],
        raw_text: str,
        duration: float
    ) -> List[Dict[str, Any]]:
        if not words:
            if raw_text:
                return [{
                    'start': 0.0,
                    'end': duration,
                    'text': raw_text,
                }]
            return []

        max_chars = 80
        max_duration = 8.0
        min_duration = 1.0
        max_gap = 1.2

        segments: List[Dict[str, Any]] = []
        segment_words: List[Dict[str, Any]] = []
        segment_start = 0.0
        last_end = 0.0

        for word in words:
            if not segment_words:
                segment_words = [word]
                segment_start = word['start']
                last_end = word['end']
                continue

            gap = word['start'] - last_end
            candidate_words = segment_words + [word]
            candidate_text = self._join_words(candidate_words)
            segment_duration = word['end'] - segment_start
            should_break = (
                gap > max_gap
                or segment_duration > max_duration
                or len(candidate_text) > max_chars
                or (self._is_sentence_end(segment_words[-1]['word']) and segment_duration >= min_duration)
            )

            if should_break:
                segments.append({
                    'start': segment_start,
                    'end': last_end,
                    'text': self._join_words(segment_words),
                })
                segment_words = [word]
                segment_start = word['start']
            else:
                segment_words.append(word)
            last_end = word['end']

        if segment_words:
            segments.append({
                'start': segment_start,
                'end': last_end,
                'text': self._join_words(segment_words),
            })

        return segments

    def _join_words(self, words: List[Dict[str, Any]]) -> str:
        return self._clean_text(" ".join(word['word'] for word in words if word['word']))

    @staticmethod
    def _is_sentence_end(text: str) -> bool:
        return text.rstrip().endswith(('.', '!', '?'))


transcription_service = ParakeetTranscriptionService()
