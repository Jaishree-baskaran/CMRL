from pathlib import Path
from typing import Optional
import rasterio
from rasterio.windows import Window
from rasterio.io import MemoryFile
from rasterio.errors import RasterioIOError

from app.image_engine.utils import resolve_secure_path
from app.image_engine.exceptions import (
    TIFFNotFoundError,
    CorruptedTIFFError,
    UnsupportedRasterError
)
from app.preview_engine.exceptions import InvalidWindowError
from app.preview_engine.config import settings

class PreviewService:
    @staticmethod
    def get_preview(
        filename: str,
        x: Optional[int] = None,
        y: Optional[int] = None,
        width: Optional[int] = None,
        height: Optional[int] = None
    ) -> bytes:
        """
        Extracts a specific pixel crop window from a TIFF and returns the raw PNG bytes.
        If parameters are omitted, falls back to the center of the image.
        """
        # Resolve the secure file path
        secure_path = resolve_secure_path(filename)
        
        if not secure_path.exists():
            raise TIFFNotFoundError(f"TIFF file not found: {secure_path.name}")

        try:
            with rasterio.open(secure_path) as src:
                # 1. Determine read dimensions (clip to file size if defaults exceed)
                w_crop = width if width is not None else settings.DEFAULT_SIZE
                h_crop = height if height is not None else settings.DEFAULT_SIZE

                w_crop = min(w_crop, src.width)
                h_crop = min(h_crop, src.height)

                # 2. Determine offsets (fallback to center coordinate alignment)
                x_off = x if x is not None else (src.width - w_crop) // 2
                y_off = y if y is not None else (src.height - h_crop) // 2

                # 3. Check for out-of-bounds offset bounds
                if x_off < 0 or y_off < 0 or (x_off + w_crop) > src.width or (y_off + h_crop) > src.height:
                    raise InvalidWindowError(
                        f"Requested window (x={x_off}, y={y_off}, w={w_crop}, h={h_crop}) "
                        f"exceeds image dimensions (width={src.width}, height={src.height})."
                    )

                # 4. Construct the rasterio Window object
                window = Window(col_off=x_off, row_off=y_off, width=w_crop, height=h_crop)

                # 5. Read the pixel slice dynamically without parsing the rest of the image
                tile_data = src.read(window=window)

                # 6. Encode the data into PNG bytes using MemoryFile
                dtype = src.dtypes[0] if len(src.dtypes) > 0 else 'uint8'
                
                with MemoryFile() as memfile:
                    with memfile.open(
                        driver="PNG",
                        width=w_crop,
                        height=h_crop,
                        count=src.count,
                        dtype=dtype
                    ) as dst:
                        dst.write(tile_data)
                    return memfile.read()

        except RasterioIOError as e:
            err_msg = str(e)
            if "not recognized as a supported file format" in err_msg:
                raise UnsupportedRasterError(f"Unsupported file format: {secure_path.name}")
            raise CorruptedTIFFError(f"Corrupted raster file: {secure_path.name}. Info: {err_msg}")
        except InvalidWindowError as e:
            raise e
        except Exception as e:
            raise CorruptedTIFFError(f"Failed extracting preview for '{secure_path.name}': {str(e)}")
