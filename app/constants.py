"""Application constants"""

# File size limits
MAX_FILE_SIZE = 524288000  # 500MB
CHUNK_SIZE_BYTES = 1024 * 1024  # 1MB

# Audio processing
SAMPLE_RATE = 16000
CHANNELS = 1
MAX_INT16 = 2**15

# Allowed file extensions
ALLOWED_AUDIO_EXTENSIONS = {'.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg'}
ALLOWED_VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv'}
ALLOWED_EXTENSIONS = ALLOWED_AUDIO_EXTENSIONS | ALLOWED_VIDEO_EXTENSIONS

# Media types
MEDIA_TYPES = {
    'txt': 'text/plain',
    'srt': 'text/plain',
    'json': 'application/json',
    'mp3': 'audio/mpeg',
    'wav': 'audio/wav',
    'flac': 'audio/flac',
    'mp4': 'video/mp4',
    'avi': 'video/x-msvideo',
    'mov': 'video/quicktime',
    'mkv': 'video/x-matroska',
}

# Progress percentages for background tasks
PROGRESS_INIT = 10
PROGRESS_AUDIO_EXTRACTED = 20
PROGRESS_TRANSCRIBING = 30
PROGRESS_DIARIZATION = 60
PROGRESS_SAVING = 80

# Task configuration
DEFAULT_CHUNK_LENGTH_S = 60.0
MAX_CHUNK_LENGTH_S = 60.0
MIN_CHUNK_LENGTH_S = 10.0
TASK_TIMEOUT_SECONDS = 3600  # 1 hour
