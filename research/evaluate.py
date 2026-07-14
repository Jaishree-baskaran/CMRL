import time
import json
import numpy as np
import cv2
from pathlib import Path

def get_skeleton(mask: np.ndarray) -> np.ndarray:
    """
    Applies mathematical morphological thinning to extract 1-pixel wide centerlines.
    Pure OpenCV/NumPy implementation.
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
    Generates a translucent red overlay of the mask on top of the original image.
    """
    color_mask = np.zeros_like(original)
    # Highlight segmented areas in high-vis red
    color_mask[:, :, 2] = mask 
    
    # Blended output
    return cv2.addWeighted(original, 0.7, color_mask, 0.3, 0)

def evaluate_run(
    original: np.ndarray,
    mask: np.ndarray,
    inference_time: float,
    confidence: float,
    run_time: float,
    model_name: str
) -> dict:
    """
    Computes key benchmarking metrics and return a structured report dictionary.
    """
    height, width = mask.shape[:2]
    total_pixels = height * width
    
    # 1. Mask Coverage ratio
    active_pixels = cv2.countNonZero(mask)
    coverage = float(active_pixels / total_pixels) if total_pixels > 0 else 0.0
    
    # 2. Connected components analysis
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask)
    # Subtract 1 to exclude background label
    connected_components = int(max(0, num_labels - 1))
    
    # 3. Formulate R&D recommendations
    # Rails are long continuous parallel lines. Ideal segmenters should return
    # continuous strips (small number of connected components) and reasonable coverage.
    if connected_components == 0:
        recommendation = "Reject: No rails detected."
    elif connected_components <= 4 and coverage > 0.01:
        recommendation = "Highly Recommended: Output shows high line continuity and low fragmentation."
    elif connected_components > 15:
        recommendation = "Marginal: High fragmentation detected (too many separate segments). Needs post-processing."
    else:
        recommendation = "Acceptable: Rails detected, moderately segmented."

    report = {
        "model_name": model_name,
        "input_dimensions": f"{width}x{height}",
        "metrics": {
            "inference_time_seconds": round(inference_time, 4),
            "total_processing_time_seconds": round(run_time, 4),
            "mask_coverage_percentage": round(coverage * 100, 2),
            "connected_components_count": connected_components,
            "average_confidence": round(confidence, 2)
        },
        "recommendation": recommendation
    }
    
    return report
