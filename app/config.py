import os
from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # HuggingFace
    hf_home: str = "./models"
    hf_hub_cache: str = "./models"
    hf_hub_disable_symlinks_warning: str = "true"
    huggingface_token: str = ""
    
    # App
    app_host: str = "0.0.0.0"
    app_port: int = 4787
    max_file_size: int = 524288000  # 500MB
    upload_chunk_size: int = 10485760  # 10MB
    api_key: str = ""
    database_url: str = ""
    
    # Paths
    upload_dir: str = "./uploads"
    transcription_dir: str = "./transcriptions"
    models_dir: str = "./models"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()

# Ensure directories exist
Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
Path(settings.transcription_dir).mkdir(parents=True, exist_ok=True)
Path(settings.models_dir).mkdir(parents=True, exist_ok=True)

# Set environment variables for HuggingFace
os.environ["HF_HOME"] = settings.hf_home
os.environ["HF_HUB_CACHE"] = settings.hf_hub_cache
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = settings.hf_hub_disable_symlinks_warning
if settings.huggingface_token:
    os.environ["HF_TOKEN"] = settings.huggingface_token
