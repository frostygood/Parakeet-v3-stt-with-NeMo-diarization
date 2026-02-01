import os
import uuid
import aiofiles
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.logging_config import setup_logging, get_logger
from app.utils import sanitize_filename, validate_file_size, validate_file_type
from app.constants import MEDIA_TYPES
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
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
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
        
        # Start background task
        background_tasks.add_task(
            process_transcription,
            file_path=str(file_path),
            task_id=task_id,
            language="auto"
        )
        
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
        if not task_state:
            raise HTTPException(status_code=404, detail="Task not found")
        
        if task_state.status == TranscriptionStatus.PENDING.value:
            return {
                'task_id': task_id,
                'status': 'pending',
                'progress': task_state.progress
            }
        elif task_state.status == TranscriptionStatus.PROCESSING.value:
            return {
                'task_id': task_id,
                'status': 'processing',
                'progress': task_state.progress,
                'step': task_state.step
            }
        elif task_state.status == TranscriptionStatus.COMPLETED.value:
            result = task_state.result or {}
            response = {
                'task_id': task_id,
                'status': 'completed',
                'result_url': f"/result/{task_id}",
                'raw_text': result.get('raw_text'),
                'text': result.get('raw_text'),
                'words': result.get('words'),
                'srt': result.get('srt'),
                'srt_segments': result.get('srt_segments'),
                'speaker_segments': result.get('speaker_segments'),
                'diarization_segments': result.get('diarization_segments'),
                'speaker_text': result.get('speaker_text'),
                'processing_time': result.get('processing_time'),
                'duration': result.get('duration'),
                'language': result.get('language')
            }
            return response
        else:
            return {
                'task_id': task_id,
                'status': 'failed',
                'error': task_state.error or 'Unknown error'
            }
            
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
        if not task_state:
            raise HTTPException(status_code=404, detail="Task not found")
        
        if task_state.status == TranscriptionStatus.FAILED.value:
            raise HTTPException(status_code=500, detail=task_state.error or "Task failed")
        
        if task_state.status != TranscriptionStatus.COMPLETED.value:
            raise HTTPException(status_code=404, detail="Result not ready or task failed")
        
        result = task_state.result or {}
        result_file = result.get('result_file')
        if not result_file or not os.path.exists(result_file):
            raise HTTPException(status_code=404, detail="Result file not found")

        return FileResponse(
            result_file,
            media_type=MEDIA_TYPES.get('json', 'application/json'),
            filename=f"transcription_{task_id}.json"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting result for task {task_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get result")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.app_host, port=settings.app_port)
