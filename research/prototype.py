import argparse
import sys
import time
import json
from pathlib import Path
import cv2

# Ensure the research directory can import sibling files
sys.path.append(str(Path(__file__).resolve().parent))

from models import YOLO11Segmenter, SAM2Segmenter, ClassicalSegmenter
from utils import get_tiff_crop, setup_run_dir
from evaluate import get_skeleton, create_overlay, evaluate_run

def run_benchmark(
    tiff_name: str,
    model_type: str,
    crop_size: int
):
    print(f"==================================================")
    print(f"Starting Rail Segmentation Benchmark Run")
    print(f"Image: {tiff_name} | Model: {model_type} | Crop: {crop_size}x{crop_size}")
    print(f"==================================================")
    
    t_start = time.time()
    
    # 1. Resolve source pathways
    base_dir = Path(__file__).resolve().parent
    workspace_dir = base_dir.parent
    
    # Check if file resides in secure backend/data or local folder
    data_dir = workspace_dir / "backend" / "data"
    tiff_path = data_dir / tiff_name
    
    if not tiff_path.exists():
        # Fallback to direct path check
        tiff_path = Path(tiff_name)
        if not tiff_path.exists():
            print(f"[ERROR] Source TIFF file could not be found: '{tiff_name}'")
            sys.exit(1)

    # 2. Extract crop window
    print("Reading image crop from TIFF...")
    try:
        original_crop = get_tiff_crop(tiff_path, crop_size)
    except Exception as e:
        print(f"[ERROR] Failed to crop TIFF: {e}")
        sys.exit(1)

    # 3. Initialize model
    print(f"Initializing segmenter model: {model_type}...")
    if model_type.lower() == "yolo11":
        segmenter = YOLO11Segmenter()
    elif model_type.lower() == "sam2":
        segmenter = SAM2Segmenter()
    elif model_type.lower() == "classical":
        segmenter = ClassicalSegmenter()
    else:
        print(f"[ERROR] Unknown model type: {model_type}")
        sys.exit(1)

    # 4. Execute segmenter
    print("Running segmenter model inference...")
    mask, inf_time, confidence = segmenter.segment(original_crop)

    # 5. Extract centerline skeleton & overlay
    print("Extracting centerline skeleton...")
    centerline = get_skeleton(mask)
    
    print("Generating transparent overlay...")
    overlay = create_overlay(original_crop, mask)

    # 6. Evaluate metrics
    run_time = time.time() - t_start
    print("Calculating evaluation metrics...")
    report = evaluate_run(
        original=original_crop,
        mask=mask,
        inference_time=inf_time,
        confidence=confidence,
        run_time=run_time,
        model_name=model_type
    )

    # 7. Setup run directory and write files
    run_dir = setup_run_dir(base_dir)
    print(f"Saving run outputs to: {run_dir.relative_to(workspace_dir)}")
    
    cv2.imwrite(str(run_dir / "original.png"), original_crop)
    cv2.imwrite(str(run_dir / "mask.png"), mask)
    cv2.imwrite(str(run_dir / "overlay.png"), overlay)
    cv2.imwrite(str(run_dir / "centerline.png"), centerline)
    
    with open(run_dir / "report.json", "w") as f:
        json.dump(report, f, indent=4)

    print("\n--- Execution Report ---")
    print(json.dumps(report, indent=2))
    print("==================================================")
    print("Run completed successfully!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rail Segmentation R&D Benchmark Framework")
    parser.add_argument(
        "--filename", 
        type=str, 
        required=True,
        help="Source TIFF filename (looks in backend/data/)"
    )
    parser.add_argument(
        "--model", 
        type=str, 
        default="classical",
        choices=["yolo11", "sam2", "classical"],
        help="Segmentation approach to test"
    )
    parser.add_argument(
        "--crop_size", 
        type=int, 
        default=1024,
        choices=[512, 1024, 2048, 4096],
        help="Pixel crop dimensions"
    )
    
    args = parser.parse_args()
    run_benchmark(
        tiff_name=args.filename,
        model_type=args.model,
        crop_size=args.crop_size
    )
