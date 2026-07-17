from functools import lru_cache
from pathlib import Path
import rasterio
from rasterio.vrt import WarpedVRT
from rasterio.io import MemoryFile
from rasterio.errors import RasterioIOError
from rasterio.enums import Resampling

from app.image_engine.utils import resolve_secure_path
from app.image_engine.exceptions import (
    TIFFNotFoundError,
    CorruptedTIFFError,
    UnsupportedRasterError
)
from app.tile_engine.exceptions import TileOutOfBoundsError, TileRenderError
from app.tile_engine.utils import xyz_to_mercator_bounds
from app.tile_engine.config import settings

from app.image_engine.service import TIFFMetadataService

class TileService:
    @staticmethod
    def get_tile(filename: str, z: int, x: int, y: int) -> bytes:
        """
        Securely resolves the filename, checks cached tiles, or processes the windowed raster.
        """
        # Resolve path securely
        secure_path = resolve_secure_path(filename)
        
        # Get secure COG path (preprocesses Standard TIFFs dynamically)
        cog_path, _ = TIFFMetadataService.get_secure_cog_path(secure_path)
        
        # Convert path to string for caching hashability
        return _read_tile_cached(str(cog_path), z, x, y)

@lru_cache(maxsize=settings.TILE_CACHE_SIZE)
def _read_tile_cached(file_path_str: str, z: int, x: int, y: int) -> bytes:
    """
    LRU Cached internal reader. Reads and compiles a 256x256 tile slice.
    """
    file_path = Path(file_path_str)
    if not file_path.exists():
        raise TIFFNotFoundError(f"TIFF file not found: {file_path.name}")

    # 1. Calculate the spatial bounding box of the requested tile in EPSG:3857
    t_left, t_bottom, t_right, t_top = xyz_to_mercator_bounds(x, y, z)

    try:
        with rasterio.open(file_path) as src:
            # Wrap the dataset in a WarpedVRT to handle EPSG:3857 projection dynamically
            # Set resampling to nearest neighbor to prevent texture blurring
            with WarpedVRT(src, crs="EPSG:3857", resampling=Resampling.nearest) as vrt:
                # 2. Check if the tile bounds overlap the raster bounds in EPSG:3857
                v_left, v_bottom, v_right, v_top = vrt.bounds
                
                # Check for non-overlapping bounding coordinates
                if (t_left > v_right or t_right < v_left or 
                        t_bottom > v_top or t_top < v_bottom):
                    raise TileOutOfBoundsError("Tile coordinates are outside the raster spatial bounds.")

                import numpy as np
                from rasterio.windows import Window, intersection

                # 3. Define the full read window relative to the virtual dataset
                tile_window = vrt.window(t_left, t_bottom, t_right, t_top)
                
                # Clip the window to the actual dimensions of the virtual dataset
                vrt_full_window = Window(0, 0, vrt.width, vrt.height)
                intersect_window = intersection(tile_window, vrt_full_window)

                # Determine destination canvas dtype and band count
                dtype = vrt.dtypes[0] if len(vrt.dtypes) > 0 else 'uint8'
                tile_data = np.zeros((vrt.count, 256, 256), dtype=dtype)

                if intersect_window.width > 0 and intersect_window.height > 0:
                    # Calculate scaling factors
                    scale_x = 256 / tile_window.width
                    scale_y = 256 / tile_window.height

                    # Calculate target coordinates and dimensions in the 256x256 output tile
                    out_w = max(1, int(round(intersect_window.width * scale_x)))
                    out_h = max(1, int(round(intersect_window.height * scale_y)))

                    offset_x = max(0, int(round((intersect_window.col_off - tile_window.col_off) * scale_x)))
                    offset_y = max(0, int(round((intersect_window.row_off - tile_window.row_off) * scale_y)))

                    # Read only the intersecting area from the raster
                    tile_subset = vrt.read(
                        window=intersect_window,
                        out_shape=(vrt.count, out_h, out_w)
                    )

                    # Blit the raster pixels into the correct offset on the 256x256 black canvas
                    h_limit = min(out_h, 256 - offset_y)
                    w_limit = min(out_w, 256 - offset_x)
                    tile_data[:, offset_y:offset_y+h_limit, offset_x:offset_x+w_limit] = tile_subset[:, :h_limit, :w_limit]

                # 4. Super-Resolution / Image Clarity Enhancer for Deep Zooms
                if z >= 20 and vrt.count >= 3:
                    try:
                        import cv2
                        # Convert CHW to HWC for OpenCV processing
                        img_hwc = np.transpose(tile_data, (1, 2, 0))
                        
                        # Handle float to uint8 conversion if needed
                        if img_hwc.dtype != np.uint8:
                            max_val = img_hwc.max() if img_hwc.max() > 0 else 1.0
                            img_hwc = (img_hwc / max_val * 255).astype(np.uint8)
                            
                        has_alpha = img_hwc.shape[2] == 4
                        rgb = img_hwc[:, :, :3]
                        alpha = img_hwc[:, :, 3] if has_alpha else None
                        
                        # 2x Bilinear/Lanczos upscaling to interpolate sub-pixel edges
                        upscaled = cv2.resize(rgb, (512, 512), interpolation=cv2.INTER_LANCZOS4)
                        
                        # Unsharp Mask Filter: Original + (Original - GaussianBlur) * Strength
                        gaussian = cv2.GaussianBlur(upscaled, (0, 0), 2.0)
                        sharpened = cv2.addWeighted(upscaled, 1.8, gaussian, -0.8, 0)
                        
                        # High-frequency detail reinforcement (Laplacian kernel pass)
                        kernel = np.array([
                            [0, -0.15, 0],
                            [-0.15, 1.6, -0.15],
                            [0, -0.15, 0]
                        ], dtype=np.float32)
                        detail_boost = cv2.filter2D(sharpened, -1, kernel)
                        
                        # Downscale back to 256x256 using Area mapping to avoid aliasing artifacts
                        rgb_final = cv2.resize(detail_boost, (256, 256), interpolation=cv2.INTER_AREA)
                        
                        # Reassemble bands
                        if has_alpha:
                            img_final = np.zeros((256, 256, 4), dtype=np.uint8)
                            img_final[:, :, :3] = rgb_final
                            img_final[:, :, 3] = alpha
                        else:
                            img_final = rgb_final
                            
                        # Convert back to CHW for rasterio writer
                        tile_data = np.transpose(img_final, (2, 0, 1))
                        
                    except Exception as ex:
                        # Fallback silently to normal rendering if CV2 fails
                        pass

                # 5. Compress and write the windowed data as standard PNG bytes
                with MemoryFile() as memfile:
                    with memfile.open(
                        driver="PNG",
                        width=256,
                        height=256,
                        count=vrt.count,
                        dtype=dtype
                    ) as dst:
                        dst.write(tile_data)
                    return memfile.read()

    except RasterioIOError as e:
        err_msg = str(e)
        if "not recognized as a supported file format" in err_msg:
            raise UnsupportedRasterError(f"Unsupported file format: {file_path.name}")
        raise CorruptedTIFFError(f"Corrupted raster file: {file_path.name}. Info: {err_msg}")
    except TileOutOfBoundsError as e:
        # Re-raise out-of-bounds error so routers can handle 204
        raise e
    except Exception as e:
        raise TileRenderError(f"Failed rendering tile {z}/{x}/{y}: {str(e)}")
