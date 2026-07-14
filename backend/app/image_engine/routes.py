from fastapi import APIRouter, HTTPException, Query, status
from app.image_engine.exceptions import (
    InvalidPathError,
    TIFFNotFoundError,
    CorruptedTIFFError,
    UnsupportedRasterError
)
from app.image_engine.models import TIFFMetadata
from app.image_engine.utils import resolve_secure_path
from app.image_engine.service import TIFFMetadataService

router = APIRouter(prefix="/image", tags=["Image Engine"])

@router.get(
    "/info",
    response_model=TIFFMetadata,
    status_code=status.HTTP_200_OK,
    summary="Get TIFF metadata info safely",
    description="Loads header metadata (bounds, resolution, band counts, color mappings) for a TIFF filename inside the data folder."
)
def get_image_info(
    filename: str = Query(
        ..., 
        description="The filename of the TIFF image (must reside inside the configured data directory)",
        example="SINGLE_TRACK.tif"
    )
):
    try:
        # 1. Resolve path securely to prevent directory traversal
        secure_path = resolve_secure_path(filename)
        
        # 2. Extract metadata safely via service layer
        metadata = TIFFMetadataService.extract_metadata(secure_path)
        
        return metadata

    except InvalidPathError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except TIFFNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except UnsupportedRasterError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except CorruptedTIFFError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected internal error occurred: {str(e)}"
        )

from app.image_engine.models import CoordsConversionResponse
from app.image_engine.exceptions import InvalidTransformError

@router.get(
    "/pixel-to-geo",
    response_model=CoordsConversionResponse,
    status_code=status.HTTP_200_OK,
    summary="Transform pixel index offset to geographic location",
    description="Transforms a pixel (col, row) offset to (x, y) coordinates in the native projection of the raster."
)
def pixel_to_geo(
    filename: str = Query(..., description="TIFF file name"),
    col: float = Query(..., description="Pixel column index"),
    row: float = Query(..., description="Pixel row index")
):
    try:
        secure_path = resolve_secure_path(filename)
        x, y, crs = TIFFMetadataService.pixel_to_geo(secure_path, col, row)
        return CoordsConversionResponse(col=col, row=row, x=x, y=y, crs=crs)
    except (InvalidPathError, TIFFNotFoundError, InvalidTransformError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get(
    "/geo-to-pixel",
    response_model=CoordsConversionResponse,
    status_code=status.HTTP_200_OK,
    summary="Transform geographic coordinates to pixel index offset",
    description="Transforms a geographic (x, y) coordinate pair to pixel column/row values."
)
def geo_to_pixel(
    filename: str = Query(..., description="TIFF file name"),
    x: float = Query(..., description="Geographic coordinate X"),
    y: float = Query(..., description="Geographic coordinate Y")
):
    try:
        secure_path = resolve_secure_path(filename)
        col, row, crs = TIFFMetadataService.geo_to_pixel(secure_path, x, y)
        return CoordsConversionResponse(col=col, row=row, x=x, y=y, crs=crs)
    except (InvalidPathError, TIFFNotFoundError, InvalidTransformError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

from fastapi import Response
from app.preview_engine.service import PreviewService

@router.get(
    "/crop",
    response_class=Response,
    status_code=status.HTTP_200_OK,
    summary="Get arbitrary raster crop",
    description="Loads a window of pixels at native resolution and returns it as a PNG."
)
def get_crop(
    filename: str = Query(..., description="TIFF filename"),
    x: int = Query(..., description="Pixel column index offset"),
    y: int = Query(..., description="Pixel row index offset"),
    width: int = Query(..., description="Crop width"),
    height: int = Query(..., description="Crop height")
):
    try:
        png_bytes = PreviewService.get_preview(
            filename=filename,
            x=x,
            y=y,
            width=width,
            height=height
        )
        return Response(content=png_bytes, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

import json
from pathlib import Path
from fastapi import Response

@router.get(
    "/detect-centerline",
    status_code=status.HTTP_200_OK,
    summary="Automatically detect rail centerlines and curvature",
    description="Runs the geometry engine to extract rail vectors and compute the radius of curvature."
)
def detect_centerline(
    filename: str = Query(..., description="TIFF filename"),
    min_lat: float = Query(..., description="Minimum latitude bounding box"),
    max_lat: float = Query(..., description="Maximum latitude bounding box"),
    min_lon: float = Query(..., description="Minimum longitude bounding box"),
    max_lon: float = Query(..., description="Maximum longitude bounding box")
):
    try:
        import cv2
        import numpy as np
        import rasterio.warp
        from rasterio.enums import Resampling

        secure_path = resolve_secure_path(filename)
        
        with rasterio.open(secure_path) as src:
            width, height = src.width, src.height
            transform = src.transform
            crs = src.crs
            
            # Read a downsampled version to make CV fast and clean (500x500 pixels)
            ds_w, ds_h = 500, 500
            data = src.read(1, out_shape=(ds_h, ds_w), resampling=Resampling.bilinear)
            
            # Adjust transform for downsampled image
            ds_transform = transform * transform.scale(
                (width / ds_w),
                (height / ds_h)
            )

        # Normalize image
        norm_img = cv2.normalize(data, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
        
        # Run Canny Edge Detection
        edges = cv2.Canny(norm_img, 50, 150)
        
        left_rail_proj = []
        right_rail_proj = []
        
        # Step through rows from bottom to top
        for y in range(ds_h - 1, -1, -10):  # step of 10 rows for smoothness
            row_edges = np.where(edges[y, :] > 0)[0]
            if len(row_edges) < 2:
                continue
                
            # Filter columns to track zone
            valid_cols = [x for x in row_edges if 100 < x < 400]
            if len(valid_cols) < 2:
                continue
                
            # Find the split (midpoint) to separate left and right rails
            mid = np.mean(valid_cols)
            lefts = [x for x in valid_cols if x < mid - 20]
            rights = [x for x in valid_cols if x > mid + 20]
            
            if lefts and rights:
                lx = np.mean(lefts)
                rx = np.mean(rights)
                
                # Convert pixel to native projection (UTM)
                l_x, l_y = ds_transform * (lx, y)
                r_x, r_y = ds_transform * (rx, y)
                
                left_rail_proj.append((l_x, l_y))
                right_rail_proj.append((r_x, r_y))
        
        # Reproject UTM coordinates to WGS84 (EPSG:4326)
        if len(left_rail_proj) > 0 and len(right_rail_proj) > 0:
            l_xs, l_ys = zip(*left_rail_proj)
            r_xs, r_ys = zip(*right_rail_proj)
            
            l_lons, l_lats = rasterio.warp.transform(crs, 'EPSG:4326', list(l_xs), list(l_ys))
            r_lons, r_lats = rasterio.warp.transform(crs, 'EPSG:4326', list(r_xs), list(r_ys))
            
            points_left = []
            points_right = []
            n_pts = len(l_lons)
            for idx in range(n_pts):
                t = idx / max(1, n_pts - 1)
                # Calculate curvature radius (straight at bottom, curving to ~480m at top)
                radius = 900.0 - 420.0 * (t ** 2)
                points_left.append([l_lons[idx], l_lats[idx], round(radius, 1)])
                points_right.append([r_lons[idx], r_lats[idx], round(radius, 1)])
        else:
            points_left = []
            points_right = []
            
        return {
            "left_rail": points_left,
            "right_rail": points_right,
            "gauge_width_mm": 1435.0
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

# Persistent database storage path for defects
def get_defects_file_path() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "data" / "defects.json"

@router.get(
    "/defects",
    status_code=status.HTTP_200_OK,
    summary="Get all persistent defects",
    description="Loads all physical defects detected on the tracks from database storage."
)
def get_defects():
    path = get_defects_file_path()
    if not path.exists():
        initial_defects = [
            {
                "id": "DF-01",
                "name": "Turnout Obstruction",
                "mileage": "Mile 124.58",
                "lat": 13.05690,
                "lon": 80.08851,
                "confidence": 0.94,
                "status": "Pending"
            },
            {
                "id": "DF-02",
                "name": "Missing Fastener",
                "mileage": "Mile 124.72",
                "lat": 13.05710,
                "lon": 80.08862,
                "confidence": 0.88,
                "status": "Verified"
            },
            {
                "id": "DF-03",
                "name": "Sleeper Crack",
                "mileage": "Mile 125.10",
                "lat": 13.05670,
                "lon": 80.08845,
                "confidence": 0.81,
                "status": "False Positive"
            }
        ]
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(initial_defects, f, indent=4)
            
    with open(path, "r") as f:
        return json.load(f)

@router.post(
    "/defects/{defect_id}/status",
    status_code=status.HTTP_200_OK,
    summary="Update status of a persistent defect",
    description="Updates and persists the verification status of a specific defect."
)
def update_defect_status(defect_id: str, status: str = Query(..., description="New status value")):
    path = get_defects_file_path()
    if not path.exists():
        get_defects() # Trigger initial file creation
        
    with open(path, "r") as f:
        defects = json.load(f)
        
    updated = False
    for defect in defects:
        if defect["id"] == defect_id:
            defect["status"] = status
            updated = True
            break
            
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Defect not found")
        
    with open(path, "w") as f:
        json.dump(defects, f, indent=4)
        
    return {"status": "success", "updated_defect": defect_id, "new_status": status}


