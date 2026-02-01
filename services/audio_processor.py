import os
import ffmpeg
from pathlib import Path
from typing import Optional

from app.logging_config import get_logger
from app.utils import get_audio_output_path
from app.constants import SAMPLE_RATE, CHANNELS

logger = get_logger(__name__)


class AudioProcessor:
    """Audio processing utility class using FFmpeg."""
    
    @staticmethod
    def extract_audio(video_path: str, output_audio_path: Optional[str] = None) -> str:
        """
        Extract audio from video file.
        
        Args:
            video_path: Path to video file
            output_audio_path: Output path for extracted audio (default: same as video)
            
        Returns:
            Path to extracted audio file
            
        Raises:
            Exception: If extraction fails
        """
        if output_audio_path is None:
            output_audio_path = get_audio_output_path(video_path, suffix='_audio', ext='.wav')
        
        try:
            logger.info(f"Extracting audio from video: {video_path}")
            
            (
                ffmpeg
                .input(video_path)
                .output(
                    output_audio_path,
                    acodec='pcm_s16le',
                    ac=CHANNELS,
                    ar=SAMPLE_RATE
                )
                .overwrite_output()
                .run(quiet=True)
            )
            
            logger.debug(f"Audio extracted to: {output_audio_path}")
            return output_audio_path
            
        except ffmpeg.Error as e:
            logger.error(f"FFmpeg error extracting audio: {e}", exc_info=True)
            raise
    
    @staticmethod
    def convert_to_wav(audio_path: str, output_path: Optional[str] = None) -> str:
        """
        Convert any audio format to WAV (16kHz, mono).
        
        Args:
            audio_path: Path to audio file
            output_path: Output path for WAV file (default: appends _converted)
            
        Returns:
            Path to converted WAV file
            
        Raises:
            Exception: If conversion fails
        """
        if output_path is None:
            output_path = get_audio_output_path(audio_path)
        
        try:
            logger.info(f"Converting audio to WAV: {audio_path}")
            
            (
                ffmpeg
                .input(audio_path)
                .output(
                    output_path,
                    acodec='pcm_s16le',
                    ac=CHANNELS,
                    ar=SAMPLE_RATE
                )
                .overwrite_output()
                .run(quiet=True)
            )
            
            logger.debug(f"Audio converted to: {output_path}")
            return output_path
            
        except ffmpeg.Error as e:
            logger.error(f"FFmpeg error converting audio: {e}", exc_info=True)
            raise
    
    @staticmethod
    def cleanup_files(*file_paths: str):
        """
        Delete temporary files safely.
        
        Args:
            *file_paths: Paths to files to delete
        """
        for path in file_paths:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                    logger.debug(f"Deleted temporary file: {path}")
                except Exception as e:
                    logger.error(f"Error deleting file {path}: {e}", exc_info=True)


audio_processor = AudioProcessor()
