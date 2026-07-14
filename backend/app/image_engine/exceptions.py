class ImageEngineException(Exception):
    """Base exception for all image engine operations."""
    pass

class InvalidPathError(ImageEngineException):
    """Raised when file name violates path security boundaries (traversal or invalid input)."""
    pass

class TIFFNotFoundError(ImageEngineException):
    """Raised when the specified TIFF file cannot be found."""
    pass

class CorruptedTIFFError(ImageEngineException):
    """Raised when the TIFF file exists but is corrupted or unreadable."""
    pass

class UnsupportedRasterError(ImageEngineException):
    """Raised when the file format is not a supported TIFF/raster format or has missing CRS."""
    pass

class ConversionError(ImageEngineException):
    """Raised when on-the-fly conversion to COG fails."""
    pass

class InvalidTransformError(ImageEngineException):
    """Raised when converting between pixel and geographic coordinates fails."""
    pass
