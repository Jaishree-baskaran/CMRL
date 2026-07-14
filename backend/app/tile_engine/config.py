from pathlib import Path
from pydantic_settings import BaseSettings
from app.image_engine.config import settings as core_settings

class TileEngineSettings(BaseSettings):
    # Cache limits (number of parsed PNG tiles in the LRU cache)
    TILE_CACHE_SIZE: int = 1024
    
    # Path to the data directory where TIFF files reside
    DATA_DIR: Path = core_settings.DATA_DIR

    class Config:
        env_prefix = "TILE_ENGINE_"
        case_sensitive = True

settings = TileEngineSettings()
