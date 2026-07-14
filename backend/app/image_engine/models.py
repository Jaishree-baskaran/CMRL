from typing import List, Optional, Tuple
from pydantic import BaseModel, Field

class RasterBounds(BaseModel):
    left: float = Field(..., description="Left bounding coordinate")
    bottom: float = Field(..., description="Bottom bounding coordinate")
    right: float = Field(..., description="Right bounding coordinate")
    top: float = Field(..., description="Top bounding coordinate")

class PixelSize(BaseModel):
    x: float = Field(..., description="Pixel size width (X resolution)")
    y: float = Field(..., description="Pixel size height (Y resolution)")

class TIFFMetadata(BaseModel):
    filename: str = Field(..., description="Name of the raster file")
    width: int = Field(..., description="Raster width in pixels")
    height: int = Field(..., description="Raster height in pixels")
    bands: int = Field(..., description="Number of image bands")
    crs: Optional[str] = Field(None, description="Coordinate Reference System description")
    bounds: RasterBounds = Field(..., description="Spatial bounding coordinates in native CRS")
    wgs84_bounds: RasterBounds = Field(..., description="Spatial bounding coordinates in EPSG:4326 Lat/Lon")
    pixel_size: PixelSize = Field(..., description="Physical pixel resolution dimensions")
    data_type: List[str] = Field(..., description="Data types for each band")
    compression: Optional[str] = Field(None, description="Image compression scheme used")
    driver: str = Field(..., description="GDAL Driver used to read the file")
    color_interpretation: List[str] = Field(..., description="Color interpretation for each band")
    raster_type: str = Field(..., description="Classification: COG, GeoTIFF, or Standard TIFF")
    block_size: List[Tuple[int, int]] = Field(..., description="Block read sizes (tiles) for each band")
    overviews: List[int] = Field(..., description="Overview scaling levels (pyramids)")
    affine_transform: List[float] = Field(..., description="6-parameter Affine Transform matrix coefficients")
    estimated_gsd: float = Field(..., description="Estimated Ground Sampling Distance (GSD) in meters")
    cache_status: str = Field(..., description="Preprocessing cache state (e.g. Cached, Uncached)")
    tile_generation_status: str = Field(..., description="Status of tile indexing availability")

class PixelCoords(BaseModel):
    col: float = Field(..., description="Column pixel index")
    row: float = Field(..., description="Row pixel index")

class GeoCoords(BaseModel):
    x: float = Field(..., description="Easting / Longitude coordinate")
    y: float = Field(..., description="Northing / Latitude coordinate")

class CoordsConversionResponse(BaseModel):
    col: float = Field(..., description="Resolved column index")
    row: float = Field(..., description="Resolved row index")
    x: float = Field(..., description="Resolved geographic X coordinate")
    y: float = Field(..., description="Resolved geographic Y coordinate")
    crs: str = Field(..., description="Coordinate reference system name used")
