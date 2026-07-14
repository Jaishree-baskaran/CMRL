import os
import sys
import time
from pathlib import Path
from typing import Tuple, Optional
import numpy as np
import cv2
import rasterio
from rasterio.windows import Window

# --- Interface Setup ---

class SegmenterInterface:
    def segment(self, image: np.ndarray) -> Tuple[np.ndarray, float, dict]:
        """
        Runs image segmentation.
        Returns:
            mask: Binary 2D array (0 or 255) of the same width & height as the input
            confidence: average confidence score (0.0 to 1.0)
            metadata: dictionary containing performance parameters like 'inference_time'
        """
        raise NotImplementedError

class ClassicalOpenCVSegmenter(SegmenterInterface):
    def segment(self, image: np.ndarray) -> Tuple[np.ndarray, float, dict]:
        t0 = time.time()
        height, width = image.shape[:2]
        
        # 1. Grayscale conversion
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # 2. Gaussian blur to remove surface noise
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        # 3. Canny edge detection
        edges = cv2.Canny(blurred, 30, 100)

        # 4. Hough Line Transform to identify structural parallel segments
        lines = cv2.HoughLinesP(
            edges, 
            rho=1, 
            theta=np.pi/180, 
            threshold=100, 
            minLineLength=int(height * 0.25), 
            maxLineGap=40
        )

        # 5. Draw detected lines on binary mask (preserving resolution)
        mask = np.zeros((height, width), dtype=np.uint8)
        if lines is not None:
            for line in lines:
                coords = line.ravel()
                if len(coords) == 4:
                    x1, y1, x2, y2 = coords
                    # Rails typically occupy a width range, draw robust line indicators
                    cv2.line(mask, (x1, y1), (x2, y2), 255, thickness=max(5, int(width * 0.005)))

        # 6. Apply morphological close to connect dashed segments
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        inf_time = time.time() - t0
        confidence = 0.65 if lines is not None else 0.0
        
        metadata = {
            "inference_time_seconds": inf_time,
            "algorithm": "Classical OpenCV (Canny + HoughLinesP)",
            "lines_detected": len(lines) if lines is not None else 0
        }
        
        return mask, confidence, metadata

# --- Helper Functions ---

def get_skeleton(mask: np.ndarray) -> np.ndarray:
    """
    Applies thinning to extract a 1-pixel wide centerline skeleton, preserving input resolution.
    """
    _, binary = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
    skel = np.zeros(binary.shape, np.uint8)
    element = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    
    temp = binary.copy()
    done = False
    
    while not done:
        eroded = cv2.erode(temp, element)
        temp_dilate = cv2.dilate(eroded, element)
        temp_sub = cv2.subtract(temp, temp_dilate)
        skel = cv2.bitwise_or(skel, temp_sub)
        temp = eroded.copy()
        
        if cv2.countNonZero(temp) == 0:
            done = True
            
    return skel

def create_overlay(original: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """
    Blends the binary mask in red on top of the original image.
    """
    color_mask = np.zeros_like(original)
    color_mask[:, :, 2] = mask # Red channel highlight
    return cv2.addWeighted(original, 0.7, color_mask, 0.3, 0)

# --- Execution ---

def run_poc(
    tiff_filename: str = "SINGLE_TRACK.tif",
    crop_size: int = 2048
):
    print("==================================================")
    print("Railway Vision Validation PoC (Sprint 4)")
    print("==================================================")
    t_start = time.time()

    # 1. Resolve TIFF pathway
    research_dir = Path(__file__).resolve().parent
    workspace_dir = research_dir.parent
    tiff_path = workspace_dir / "backend" / "data" / tiff_filename
    
    if not tiff_path.exists():
        print(f"[ERROR] Source file missing: {tiff_path}")
        sys.exit(1)

    print(f"Reading center {crop_size}x{crop_size} crop from '{tiff_path.name}'...")
    
    # 2. Extract crop (preserving original resolution)
    with rasterio.open(tiff_path) as src:
        w_crop = min(crop_size, src.width)
        h_crop = min(crop_size, src.height)
        
        x_off = (src.width - w_crop) // 2
        y_off = (src.height - h_crop) // 2
        
        window = Window(col_off=x_off, row_off=y_off, width=w_crop, height=h_crop)
        data = src.read(window=window)
        
        # Format shape to HWC for OpenCV
        if src.count >= 3:
            original_crop = np.transpose(data[:3], (1, 2, 0))
            # Convert RGB to BGR
            original_crop = original_crop[:, :, ::-1]
        else:
            # Grayscale to 3-channel BGR representation
            gray_img = data[0]
            original_crop = np.stack([gray_img, gray_img, gray_img], axis=-1)

    print(f"Crop loaded. Resolution: {original_crop.shape[1]}x{original_crop.shape[0]}")

    # 3. Instantiate and run Classical Segmenter
    segmenter = ClassicalOpenCVSegmenter()
    print("Running pluggable classical OpenCV segmenter...")
    mask, confidence, metadata = segmenter.segment(original_crop)

    # 4. Generate centerline skeleton and overlay
    print("Generating centerline track skeleton...")
    centerline = get_skeleton(mask)
    
    print("Generating transparent visualization overlay...")
    overlay = create_overlay(original_crop, mask)

    # 5. Compute stats
    processing_time = time.time() - t_start
    inf_time = metadata.get("inference_time_seconds", 0.0)
    
    rail_detected = "Yes" if cv2.countNonZero(mask) > 50 else "No"
    
    # Connected components
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask)
    rail_segments = max(0, num_labels - 1)

    # 6. Save assets (no downsampling or compression)
    output_dir = research_dir / "outputs" / "poc_run"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    cv2.imwrite(str(output_dir / "original.png"), original_crop)
    cv2.imwrite(str(output_dir / "mask.png"), mask)
    cv2.imwrite(str(output_dir / "overlay.png"), overlay)
    cv2.imwrite(str(output_dir / "centerline.png"), centerline)

    # 7. Print requested stats
    print("\n--- PoC Benchmarking Stats ---")
    print(f"Processing Time:      {processing_time:.4f} seconds")
    print(f"Rail Detected:        {rail_detected}")
    print(f"Connected Components: {rail_segments}")
    print(f"Inference Time:       {inf_time:.4f} seconds")
    print(f"Average Confidence:   {confidence:.2f}")
    
    print("\nGenerated Images Paths:")
    print(f"- Original:   {output_dir / 'original.png'}")
    print(f"- Mask:       {output_dir / 'mask.png'}")
    print(f"- Overlay:    {output_dir / 'overlay.png'}")
    print(f"- Centerline: {output_dir / 'centerline.png'}")
    print("==================================================")

if __name__ == "__main__":
    run_poc()
