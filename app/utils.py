"""Utility functions"""

import re
from pathlib import Path
from typing import Tuple, List

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


def safe_float(value: any, default: float = 0.0) -> float:
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
