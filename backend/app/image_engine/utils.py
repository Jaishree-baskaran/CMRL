import os
from pathlib import Path
from app.image_engine.config import settings
from app.image_engine.exceptions import InvalidPathError

def resolve_secure_path(filename: str) -> Path:
    """
    Validates the filename and resolves it to an absolute path inside the configured DATA_DIR.
    Explicitly checks and blocks directory traversal attempts and absolute path overrides.
    """
    normalized = filename.strip()
    if not normalized:
        raise InvalidPathError("Filename cannot be empty or consist only of whitespace.")
    
    if ".." in normalized or normalized.startswith("/") or normalized.startswith("\\") or ":" in normalized:
        raise InvalidPathError(f"Directory traversal or absolute path detected in filename: '{filename}'")

    try:
        # 2. Build the base path candidate
        base_dir = settings.DATA_DIR.resolve()
        target_path = (base_dir / normalized).resolve()
        
        # 3. Double check security: the resolved path MUST be inside the resolved base data directory
        if not target_path.is_relative_to(base_dir):
            raise InvalidPathError(f"Access denied. Path resolves outside the data directory: '{filename}'")
            
        return target_path
    except Exception as e:
        if not isinstance(e, InvalidPathError):
            raise InvalidPathError(f"Error resolving path details: {str(e)}")
        raise e
