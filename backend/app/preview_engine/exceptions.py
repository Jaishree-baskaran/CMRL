from app.image_engine.exceptions import ImageEngineException

class PreviewEngineException(ImageEngineException):
    """Base exception for all preview engine operations."""
    pass

class InvalidWindowError(PreviewEngineException):
    """Raised when the specified preview window falls outside the image extent or is invalid."""
    pass
