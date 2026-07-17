from functools import lru_cache
from pathlib import Path
import os
import onnxruntime as ort
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

MODEL_PATH = "c:\\Users\\Jaishree Baskaran\\Downloads\\Railway\\backend\\data\\models\\real_esrgan_x2.onnx"
_realesrgan_session = None

def get_realesrgan_session():
    global _realesrgan_session
    if _realesrgan_session is None:
        if os.path.exists(MODEL_PATH):
            _realesrgan_session = ort.InferenceSession(MODEL_PATH, providers=['CPUExecutionProvider'])
    return _realesrgan_session

class TileService:
    @staticmethod
    def get_tile(filename: str, z: int, x: int, y: int, clarity: bool = False) -> bytes:
        """
        Securely resolves the filename, checks cached tiles, or processes the windowed raster.
        """
        # Resolve path securely
        secure_path = resolve_secure_path(filename)
        
        # Get secure COG path (preprocesses Standard TIFFs dynamically)
        cog_path, _ = TIFFMetadataService.get_secure_cog_path(secure_path)
        
        # Convert path to string for caching hashability
        return _read_tile_cached(str(cog_path), z, x, y, clarity)

@lru_cache(maxsize=settings.TILE_CACHE_SIZE)
def _read_tile_cached(file_path_str: str, z: int, x: int, y: int, clarity: bool = False) -> bytes:
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

                # 4. AI Detail Enhancement and Sharp upscaler (Real-ESRGAN x2 ONNX Inference)
                if clarity and vrt.count >= 3:
                    try:
                        session = get_realesrgan_session()
                        if session is not None:
                            # 1. Prepare RGB channel (convert shape to HWC, get raw RGB)
                            img_hwc = np.transpose(tile_data, (1, 2, 0))
                            if img_hwc.dtype != np.uint8:
                                max_val = img_hwc.max() if img_hwc.max() > 0 else 1.0
                                img_hwc = (img_hwc / max_val * 255).astype(np.uint8)
                            
                            has_alpha = img_hwc.shape[2] == 4
                            rgb = img_hwc[:, :, :3]
                            alpha = img_hwc[:, :, 3] if has_alpha else None
                            
                            # Real-ESRGAN ONNX expects CHW input shape (1, 3, 256, 256) normalized to [0, 1]
                            rgb_chw = np.transpose(rgb, (2, 0, 1)).astype(np.float32) / 255.0
                            input_blob = np.expand_dims(rgb_chw, axis=0)
                            
                            # Run inference session
                            input_name = session.get_inputs()[0].name
                            output_name = session.get_outputs()[0].name
                            out = session.run([output_name], {input_name: input_blob})
                            
                            # Output shape is (1, 3, 512, 512), scaled [0.0, 1.0]
                            # Post-process back to uint8 (3, 512, 512)
                            out_img = (out[0][0] * 255.0).clip(0, 255).astype(np.uint8)
                            
                            # Handle alpha band (resize separately using linear)
                            if has_alpha:
                                import cv2
                                alpha_up = cv2.resize(alpha, (512, 512), interpolation=cv2.INTER_LINEAR)
                                # Reassemble to (4, 512, 512)
                                tile_data = np.zeros((4, 512, 512), dtype=np.uint8)
                                tile_data[:3, :, :] = out_img
                                tile_data[3, :, :] = alpha_up
                            else:
                                tile_data = out_img
                                
                    except Exception as ex:
                        # Fallback silently to normal rendering if inference fails
                        pass

                # 5. Compress and write the windowed data as standard PNG bytes
                out_w, out_h = (512, 512) if (clarity and vrt.count >= 3) else (256, 256)
                with MemoryFile() as memfile:
                    with memfile.open(
                        driver="PNG",
                        width=out_w,
                        height=out_h,
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
