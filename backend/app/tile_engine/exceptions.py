from app.image_engine.exceptions import ImageEngineException

class TileEngineException(ImageEngineException):
    """Base exception for all tiling operations."""
    pass

class TileOutOfBoundsError(TileEngineException):
    """Raised when a requested map tile falls outside the geographic boundaries of the raster."""
    pass

class TileRenderError(TileEngineException):
    """Raised when image processing or encoding fails during dynamic rendering."""
    pass
