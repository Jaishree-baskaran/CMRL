from pathlib import Path
from typing import Tuple, List, Optional
import time
import rasterio
import rasterio.warp
from rasterio.errors import RasterioIOError
from rasterio.enums import Resampling

from app.image_engine.exceptions import (
    TIFFNotFoundError,
    CorruptedTIFFError,
    UnsupportedRasterError,
    ConversionError,
    InvalidTransformError
)
from app.image_engine.models import TIFFMetadata, RasterBounds, PixelSize

class TIFFMetadataService:
    @staticmethod
    def get_secure_cog_path(file_path: Path) -> Tuple[Path, str]:
        """
        Verifies if the raster is a Cloud Optimized GeoTIFF (COG). If not,
        automatically triggers an overview generation pipeline storing results in backend/cache/.
        """
        if not file_path.exists():
            raise TIFFNotFoundError(f"TIFF file not found: {file_path.name}")

        try:
            with rasterio.open(file_path) as src:
                # Validate spatial reference (CRS)
                if not src.crs:
                    raise UnsupportedRasterError(
                        f"Missing Spatial Reference (CRS) in '{file_path.name}'. "
                        f"A valid georeferenced Coordinate Reference System is required for Digital Twin simulation."
                    )

                # Classify COG: must be tiled AND contain overviews (pyramids)
                has_overviews = any(len(src.overviews(i)) > 0 for i in src.indexes)
                is_cog = src.is_tiled and has_overviews

                if is_cog:
                    return file_path, "Cached (Source is COG)"

            # If not a COG, compile dynamic tiled pyramid under backend/cache/
            cache_dir = file_path.parent.parent / "cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cog_path = cache_dir / f"cog_{file_path.name}"

            # Only rebuild if source is newer or doesn't exist
            if not cog_path.exists() or cog_path.stat().st_mtime < file_path.stat().st_mtime:
                print(f"[Ingestion] Converting standard GeoTIFF '{file_path.name}' to optimized tiled format...")
                
                with rasterio.open(file_path) as src:
                    profile = src.profile.copy()
                    profile.update(
                        tiled=True,
                        blockxsize=256,
                        blockysize=256,
                        compress='deflate'
                    )
                    
                    with rasterio.open(cog_path, 'w', **profile) as dst:
                        for i in range(1, src.count + 1):
                            dst.write(src.read(i), i)
                        # Build overview levels
                        factors = [2, 4, 8, 16, 32]
                        dst.build_overviews(factors, Resampling.nearest)
                        dst.update_tags(ns='rio', overview_resampling='nearest')

                return cog_path, "Generated (Pyramid Compiled)"

            return cog_path, "Cached (Pyramid Reused)"

        except UnsupportedRasterError as e:
            raise e
        except RasterioIOError as e:
            raise CorruptedTIFFError(f"GDAL failed reading raster structure: {str(e)}")
        except Exception as e:
            raise ConversionError(f"Failed preprocessing raster pyramid: {str(e)}")

    @staticmethod
    def extract_metadata(file_path: Path) -> TIFFMetadata:
        """
        Extracts extensive geospatial parameters from the raster header.
        Automatically checks and caches optimized COG layers.
        """
        # Ensure we run check and get cached COG if necessary
        cog_path, cache_status = TIFFMetadataService.get_secure_cog_path(file_path)

        try:
            # We open the cached COG to read block layouts and overviews
            with rasterio.open(cog_path) as src:
                crs_str = src.crs.to_string() if src.crs else "Unknown"

                # Native Bounds
                bounds = RasterBounds(
                    left=src.bounds.left,
                    bottom=src.bounds.bottom,
                    right=src.bounds.right,
                    top=src.bounds.top
                )

                # WGS84 Bounds
                w_left, w_bottom, w_right, w_top = rasterio.warp.transform_bounds(
                    src.crs, 'EPSG:4326', src.bounds.left, src.bounds.bottom, src.bounds.right, src.bounds.top
                )
                wgs84_bounds = RasterBounds(
                    left=w_left, bottom=w_bottom, right=w_right, top=w_top
                )

                # Pixel resolution
                res_x, res_y = src.res
                pixel_size = PixelSize(x=res_x, y=res_y)

                # Calculate Ground Sampling Distance (GSD) in meters
                if src.crs.is_geographic:
                    # Roughly scale degrees to meters at equator
                    gsd = (res_x + res_y) / 2.0 * 111319.9
                else:
                    gsd = (res_x + res_y) / 2.0

                # Data Type & Color Interpretations
                data_types = [str(dtype) for dtype in src.dtypes]
                color_interpretations = []
                for index in src.indexes:
                    try:
                        color_interpretations.append(src.colorinterp(index).name)
                    except Exception:
                        color_interpretations.append("unknown")

                # Block sizes and overviews
                block_sizes = src.block_shapes
                overviews = src.overviews(1) if src.count > 0 else []

                # Compression tags
                compression = src.profile.get('compress')
                if not compression and 'compress' in src.meta:
                    compression = src.meta['compress']

                # Affine transform parameters
                affine_list = [
                    src.transform.a, src.transform.b, src.transform.c,
                    src.transform.d, src.transform.e, src.transform.f
                ]

                # Determine if COG
                raster_type = "COG" if (src.is_tiled and len(overviews) > 0) else "GeoTIFF"

                return TIFFMetadata(
                    filename=file_path.name,
                    width=src.width,
                    height=src.height,
                    bands=src.count,
                    crs=crs_str,
                    bounds=bounds,
                    wgs84_bounds=wgs84_bounds,
                    pixel_size=pixel_size,
                    data_type=data_types,
                    compression=compression,
                    driver=src.driver,
                    color_interpretation=color_interpretations,
                    raster_type=raster_type,
                    block_size=block_sizes,
                    overviews=overviews,
                    affine_transform=affine_list,
                    estimated_gsd=gsd,
                    cache_status=cache_status,
                    tile_generation_status="Ready"
                )

        except Exception as e:
            if isinstance(e, UnsupportedRasterError):
                raise e
            raise CorruptedTIFFError(f"Unexpected error loading spatial headers: {str(e)}")

    @staticmethod
    def pixel_to_geo(file_path: Path, col: float, row: float) -> Tuple[float, float, str]:
        """
        Translates pixel coordinates (col, row) to geographic coordinates (X, Y) in the raster CRS.
        """
        cog_path, _ = TIFFMetadataService.get_secure_cog_path(file_path)
        try:
            with rasterio.open(cog_path) as src:
                x, y = src.transform * (col, row)
                crs_name = src.crs.to_string() if src.crs else "Unknown"
                return x, y, crs_name
        except Exception as e:
            raise InvalidTransformError(f"Failed to transform pixel to geo: {str(e)}")

    @staticmethod
    def geo_to_pixel(file_path: Path, x: float, y: float) -> Tuple[float, float, str]:
        """
        Translates geographic coordinates (X, Y) to pixel column and row offsets.
        """
        cog_path, _ = TIFFMetadataService.get_secure_cog_path(file_path)
        try:
            with rasterio.open(cog_path) as src:
                # Invert transform matrix
                inv_transform = ~src.transform
                col, row = inv_transform * (x, y)
                crs_name = src.crs.to_string() if src.crs else "Unknown"
                return col, row, crs_name
        except Exception as e:
            raise InvalidTransformError(f"Failed to transform geo to pixel: {str(e)}")
