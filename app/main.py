import os
import uuid
import aiofiles
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.logging_config import setup_logging, get_logger
from app.db import fetch_transcription
from app.task_queue import TaskQueue
from app.utils import sanitize_filename, validate_file_size, validate_file_type, parse_srt
from app.models import (
    TranscriptionResponse, 
    TranscriptionStatus,
)
from app.task_store import task_store
from tasks.transcription_task import process_transcription

# Setup logging
setup_logging()
logger = get_logger(__name__)

app = FastAPI(
    title="STT API",
    description="Speech-to-Text API with Parakeet v3 and Speaker Diarization",
    version="1.0.0"
)

QUEUE_MAX_SIZE = 100
QUEUE_WORKERS = 3


def build_transcription_payload(row: dict) -> dict:
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


@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)

    path = request.url.path
    if (
        path == "/"
        or path == "/health"
        or path.startswith("/static")
        or path in {"/docs", "/openapi.json", "/redoc"}
    ):
        return await call_next(request)

    expected_key = settings.api_key
    if not expected_key:
        logger.error("API key is not configured")
        return JSONResponse(status_code=500, content={"detail": "API key not configured"})

    provided_key = request.headers.get("X-API-Key")
    if provided_key != expected_key:
        return JSONResponse(status_code=401, content={"detail": "Invalid API key"})

    return await call_next(request)


@app.on_event("startup")
async def startup_tasks():
    task_queue = TaskQueue(maxsize=QUEUE_MAX_SIZE, workers=QUEUE_WORKERS)
    await task_queue.start()
    app.state.task_queue = task_queue


@app.on_event("shutdown")
async def shutdown_tasks():
    task_queue = getattr(app.state, "task_queue", None)
    if task_queue:
        await task_queue.stop()

# CORS - TODO: Configure allowed origins from settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the HTML interface."""
    try:
        with open("static/index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.error("index.html not found")
        raise HTTPException(status_code=404, detail="Interface not found")


@app.get("/health")
async def health_check():
    """
    Health check endpoint for monitoring.
    
    Returns:
        Health status of the service
    """
    return {
        "status": "healthy",
        "service": "stt-api",
        "version": "1.0.0"
    }


@app.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe(
    request: Request,
    file: UploadFile = File(...),
    enable_diarization: bool = Form(False),
):
    """
    Upload file and start transcription task.
    
    Validates file size and type, saves file, and starts background processing.
    
    Args:
        file: Audio or video file to transcribe
        
    Returns:
        Task ID for polling status
        
    Raises:
        HTTPException: If file validation fails
    """
    try:
        task_queue = getattr(request.app.state, "task_queue", None)
        if not task_queue:
            raise HTTPException(status_code=500, detail="Task queue not initialized")
        if task_queue.full():
            raise HTTPException(status_code=429, detail="Queue is full")

        # Read file size
        file_size = 0
        content = await file.read()
        file_size = len(content)
        
        # Validate file size
        validate_file_size(file_size)
        
        # Validate file type
        validate_file_type(file.filename)
        
        # Sanitize filename and create safe path
        safe_filename = sanitize_filename(file.filename)
        file_path = Path(settings.upload_dir) / f"{uuid.uuid4()}_{safe_filename}"
        
        logger.info(f"Saving uploaded file: {safe_filename} ({file_size} bytes)")
        
        # Save uploaded file
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(content)
        
        # Create task
        task_id = str(uuid.uuid4())
        
        logger.info(f"Starting transcription task {task_id} for file {safe_filename}")
        task_store.create(task_id)
        task_store.update(task_id, status="pending", progress=0, step="Queued")

        enqueued = task_queue.enqueue(
            process_transcription,
            file_path=str(file_path),
            task_id=task_id,
            language="auto",
            enable_diarization=enable_diarization,
        )
        if not enqueued:
            if file_path.exists():
                file_path.unlink()
            task_store.set_error(task_id, "Queue is full")
            raise HTTPException(status_code=429, detail="Queue is full")
        
        return TranscriptionResponse(
            task_id=task_id,
            status=TranscriptionStatus.PENDING,
            message="Transcription task started",
            result_url=f"/result/{task_id}"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in transcribe endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/status/{task_id}")
async def get_status(task_id: str):
    """
    Get transcription task status.
    
    Args:
        task_id: Task ID from transcribe endpoint
        
    Returns:
        Task status with progress (when processing) or result (when completed)
        
    Raises:
        HTTPException: If task not found
    """
    try:
        task_state = task_store.get(task_id)
        if task_state:
            if task_state.status == TranscriptionStatus.PENDING.value:
                return {
                    'task_id': task_id,
                    'status': 'pending',
                    'progress': task_state.progress,
                    'step': task_state.step
                }
            if task_state.status == TranscriptionStatus.PROCESSING.value:
                return {
                    'task_id': task_id,
                    'status': 'processing',
                    'progress': task_state.progress,
                    'step': task_state.step
                }
            if task_state.status == TranscriptionStatus.FAILED.value:
                return {
                    'task_id': task_id,
                    'status': 'failed',
                    'error': task_state.error or 'Unknown error'
                }

        row = fetch_transcription(task_id)
        if not row:
            if task_state:
                raise HTTPException(status_code=404, detail="Result not found")
            raise HTTPException(status_code=404, detail="Task not found")

        response = build_transcription_payload(row)
        response['task_id'] = task_id
        response['status'] = 'completed'
        response['result_url'] = f"/result/{task_id}"
        return response
            
    except Exception as e:
        logger.error(f"Error getting status for task {task_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get task status")


@app.get("/result/{task_id}")
async def get_result(task_id: str):
    """
    Download transcription result file.
    
    Args:
        task_id: Task ID from transcribe endpoint
        
    Returns:
        File response with transcription result
        
    Raises:
        HTTPException: If result not ready or file not found
    """
    try:
        task_state = task_store.get(task_id)
        if task_state and task_state.status == TranscriptionStatus.FAILED.value:
            raise HTTPException(status_code=500, detail=task_state.error or "Task failed")
        
        row = fetch_transcription(task_id)
        if not row:
            raise HTTPException(status_code=404, detail="Result not found")

        payload = build_transcription_payload(row)
        payload['task_id'] = task_id

        return JSONResponse(
            content=payload,
            headers={
                "Content-Disposition": f"attachment; filename=transcription_{task_id}.json"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting result for task {task_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get result")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.app_host, port=settings.app_port)
