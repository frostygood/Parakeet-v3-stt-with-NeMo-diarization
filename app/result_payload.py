from typing import Any, Dict, List

from app.utils import parse_srt


def format_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def generate_srt(segments: List[Dict[str, Any]]) -> str:
    srt_lines = []
    for index, seg in enumerate(segments, 1):
        start = format_time(seg['start'])
        end = format_time(seg['end'])
        text = seg['text'].strip()

        if 'speaker' in seg:
            text = f"[{seg['speaker']}] {text}"

        srt_lines.append(f"{index}")
        srt_lines.append(f"{start} --> {end}")
        srt_lines.append(text)
        srt_lines.append("")

    return "\n".join(srt_lines)


def build_speaker_text(segments: List[Dict[str, Any]]) -> str:
    lines = []
    for seg in segments:
        line = f"[{seg['start']:.2f} - {seg['end']:.2f}]"
        if 'speaker' in seg:
            line += f" {seg['speaker']}:"
        line += f" {seg['text']}"
        lines.append(line)
    return "\n".join(lines)


def build_speaker_srt_segments(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    speaker_srt = []
    for seg in segments:
        label = seg.get('text', '')
        if seg.get('speaker'):
            label = f"{seg['speaker']}: {label}"
        speaker_srt.append({
            'start': seg['start'],
            'end': seg['end'],
            'text': label,
        })
    return speaker_srt


def build_result_record(
    task_id: str,
    transcription_result: Dict[str, Any],
    speaker_segments: List[Dict[str, Any]],
    diarization_segments: List[Dict[str, Any]],
    language: str,
    processing_time: float,
) -> Dict[str, Any]:
    raw_text = transcription_result.get('raw_text') or transcription_result.get('text', '')
    words = transcription_result.get('words', [])
    srt_segments = transcription_result.get('segments', [])
    srt_text = generate_srt(srt_segments)

    speaker_srt = build_speaker_srt_segments(speaker_segments)
    speaker_text = build_speaker_text(speaker_segments)

    return {
        'task_id': task_id,
        'raw_text': raw_text,
        'words': words,
        'srt': srt_text,
        'speaker_srt': speaker_srt,
        'speaker_segments': speaker_segments,
        'diarization_segments': diarization_segments,
        'speaker_text': speaker_text,
        'language': transcription_result.get('language', language),
        'duration': transcription_result.get('duration', 0.0),
        'processing_time': processing_time,
    }


def build_response_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    raw_text = row.get("raw_text") or ""
    srt_text = row.get("srt") or ""

    return {
        'task_id': str(row.get('task_id') or ''),
        'raw_text': raw_text,
        'text': raw_text,
        'words': row.get('words') or [],
        'srt': srt_text,
        'speaker_srt': row.get('speaker_srt') or [],
        'srt_segments': parse_srt(srt_text),
        'speaker_segments': row.get('speaker_segments') or [],
        'diarization_segments': row.get('diarization_segments') or [],
        'speaker_text': row.get('speaker_text') or "",
        'processing_time': row.get('processing_time'),
        'duration': row.get('duration'),
        'language': row.get('language')
    }
