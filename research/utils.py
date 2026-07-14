import os
from pathlib import Path
import numpy as np
import rasterio
from rasterio.windows import Window

def get_tiff_crop(tiff_path: Path, crop_size: int) -> np.ndarray:
    """
    Reads a central pixel crop of crop_size x crop_size from the geotiff file.
    Does not load the complete image in memory.
    """
    if not tiff_path.exists():
        raise FileNotFoundError(f"Source file not found at: {tiff_path}")

    with rasterio.open(tiff_path) as src:
        # Determine center coordinates
        w_crop = min(crop_size, src.width)
        h_crop = min(crop_size, src.height)
        
        x_off = (src.width - w_crop) // 2
        y_off = (src.height - h_crop) // 2
        
        # Read windowed array
        window = Window(col_off=x_off, row_off=y_off, width=w_crop, height=h_crop)
        
        # Read dataset. Shape is (bands, height, width)
        data = src.read(window=window)
        
        # Re-order dimensions to (height, width, bands) for OpenCV
        if src.count == 1:
            # Grayscale to BGR
            img = data[0]
            img = cv2_convert = cv2_convert = cv2_convert = np.stack([img, img, img], axis=-1) if 'cv2_convert' not in locals() else img
        elif src.count >= 3:
            # Take first 3 bands (usually RGB)
            img = np.transpose(data[:3], (1, 2, 0))
            # Convert RGB to BGR for OpenCV standard saving
            img = img[:, :, ::-1]
        else:
            img = np.transpose(data, (1, 2, 0))
            
        return img

def setup_run_dir(base_dir: Path) -> Path:
    """
    Scans the outputs directory and creates the next run folder, e.g. outputs/run_001
    """
    outputs_dir = base_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    
    existing_runs = [d for d in outputs_dir.iterdir() if d.is_dir() and d.name.startswith("run_")]
    
    if not existing_runs:
        next_id = 1
    else:
        run_ids = []
        for run in existing_runs:
            try:
                run_ids.append(int(run.name.split("_")[1]))
            except ValueError:
                pass
        next_id = max(run_ids) + 1 if run_ids else 1
        
    next_run_dir = outputs_dir / f"run_{next_id:03d}"
    next_run_dir.mkdir(parents=True, exist_ok=True)
    return next_run_dir
