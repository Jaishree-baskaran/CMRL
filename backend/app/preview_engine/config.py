from pathlib import Path
from pydantic_settings import BaseSettings
from app.image_engine.config import settings as core_settings

class PreviewEngineSettings(BaseSettings):
    # Default preview width and height (crop size in pixels)
    DEFAULT_SIZE: int = 1024
    
    # Path to the data directory where TIFF files reside
    DATA_DIR: Path = core_settings.DATA_DIR

    class Config:
        env_prefix = "PREVIEW_ENGINE_"
        case_sensitive = True

settings = PreviewEngineSettings()
