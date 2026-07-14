from pathlib import Path
from pydantic_settings import BaseSettings

class ImageEngineSettings(BaseSettings):
    # Base directory for the whole backend app
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    
    # Path to the data directory where TIFF files reside
    DATA_DIR: Path = BASE_DIR / "data"

    class Config:
        env_prefix = "IMAGE_ENGINE_"
        case_sensitive = True

settings = ImageEngineSettings()
