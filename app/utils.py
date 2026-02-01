"""Utility functions"""

import re
import time
from pathlib import Path
from typing import List, Dict, Any

from fastapi import HTTPException

from app.constants import ALLOWED_EXTENSIONS, MAX_FILE_SIZE


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal and remove unsafe characters.
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized safe filename
    """
    # Get only the filename (no path)
    safe_name = Path(filename).name
    
    # Replace unsafe characters with underscore
    safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', safe_name)
    
    # Remove leading/trailing dots and spaces
    safe_name = safe_name.strip('. ')
    
    # Limit length
    safe_name = safe_name[:255]
    
    return safe_name


def validate_file_size(file_size: int) -> None:
    """
    Validate file size against maximum allowed.
    
    Args:
        file_size: Size of file in bytes
        
    Raises:
        HTTPException: If file size exceeds maximum
    """
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE / 1024 / 1024}MB"
        )


def validate_file_type(filename: str) -> None:
    """
    Validate file extension against allowed types.
    
    Args:
        filename: Name of the file
        
    Raises:
        HTTPException: If file type is not allowed
    """
    file_ext = Path(filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        allowed = ', '.join(sorted(ALLOWED_EXTENSIONS))
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed types: {allowed}"
        )


def get_audio_output_path(input_path: str, suffix: str = '_converted', ext: str = '.wav') -> str:
    """
    Generate output path for audio conversion/extraction.
    
    Args:
        input_path: Input file path
        suffix: Suffix to add to filename
        ext: Extension to use
        
    Returns:
        Output file path
    """
    return str(Path(input_path).with_suffix('')) + suffix + ext


def parse_duration_str(duration_str: str) -> float:
    """
    Parse duration string in various formats to seconds.
    
    Args:
        duration_str: Duration string (e.g., "10s", "2m", "1h", "1:30", "1:30:45")
        
    Returns:
        Duration in seconds
    """
    if ':' in duration_str:
        # Format: HH:MM:SS or MM:SS
        parts = [float(x) for x in duration_str.split(':')]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        elif len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
    
    # Format: 10s, 2m, 1h
    duration_str = duration_str.lower().strip()
    if duration_str.endswith('s'):
        return float(duration_str[:-1])
    elif duration_str.endswith('m'):
        return float(duration_str[:-1]) * 60
    elif duration_str.endswith('h'):
        return float(duration_str[:-1]) * 3600
    
    # Try to parse as plain number (seconds)
    return float(duration_str)


def safe_float(value: Any, default: float = 0.0) -> float:
    """
    Safely convert value to float.
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
        
    Returns:
        Float value or default
    """
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def parse_srt(srt_text: str) -> List[Dict[str, Any]]:
    """
    Parse SRT text into segments.

    Args:
        srt_text: SRT content

    Returns:
        List of segments with start, end, and text
    """
    if not srt_text:
        return []

    lines = [line.rstrip("\n") for line in srt_text.splitlines()]
    segments: List[Dict[str, Any]] = []
    idx = 0

    while idx < len(lines):
        line = lines[idx].strip()
        if not line:
            idx += 1
            continue
        if line.isdigit():
            idx += 1
            if idx >= len(lines):
                break
            line = lines[idx].strip()
        if "-->" not in line:
            idx += 1
            continue

        start_str, end_str = [part.strip() for part in line.split("-->")]
        start = _parse_srt_timestamp(start_str)
        end = _parse_srt_timestamp(end_str)
        idx += 1

        text_lines = []
        while idx < len(lines) and lines[idx].strip():
            text_lines.append(lines[idx])
            idx += 1

        text = "\n".join(text_lines).strip()
        segments.append({
            'start': start,
            'end': end,
            'text': text
        })

    return segments


def cleanup_old_uploads(upload_dir: str, max_age_hours: int = 24) -> int:
    """
    Remove files older than max_age_hours in upload_dir.

    Args:
        upload_dir: Directory with uploads
        max_age_hours: Age threshold in hours

    Returns:
        Number of deleted files
    """
    now = time.time()
    cutoff = max_age_hours * 3600
    deleted = 0

    for path in Path(upload_dir).glob("*"):
        if not path.is_file():
            continue
        try:
            age = now - path.stat().st_mtime
        except OSError:
            continue
        if age > cutoff:
            try:
                path.unlink()
                deleted += 1
            except OSError:
                continue

    return deleted


def _parse_srt_timestamp(value: str) -> float:
    try:
        time_part, millis_part = value.split(",")
        hours, minutes, seconds = [int(part) for part in time_part.split(":")]
        millis = int(millis_part)
        return hours * 3600 + minutes * 60 + seconds + millis / 1000
    except (ValueError, AttributeError):
        return 0.0
