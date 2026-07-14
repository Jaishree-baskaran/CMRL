from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Response, status
from app.image_engine.exceptions import (
    InvalidPathError,
    TIFFNotFoundError,
    CorruptedTIFFError,
    UnsupportedRasterError
)
from app.preview_engine.exceptions import InvalidWindowError
from app.preview_engine.service import PreviewService

router = APIRouter(prefix="/image", tags=["Preview Engine"])

@router.get(
    "/preview",
    response_class=Response,
    responses={
        200: {
            "content": {"image/png": {}},
            "description": "Returns the dynamic crop preview.",
        },
        400: {
            "description": "Bad Request due to traversal, invalid crop coordinates or file corruption."
        },
        404: {
            "description": "TIFF image not found."
        }
    },
    summary="Get TIFF preview window",
    description="Extracts a window of pixels dynamically and returns a PNG. Falls back to a centered 1024x1024 crop if dimensions/offsets are omitted."
)
def get_preview(
    filename: str = Query(
        ...,
        description="The filename of the TIFF image (must reside inside the configured data directory)",
        example="SINGLE_TRACK.tif"
    ),
    x: Optional[int] = Query(None, description="Column offset in pixels (X coord)", ge=0),
    y: Optional[int] = Query(None, description="Row offset in pixels (Y coord)", ge=0),
    width: Optional[int] = Query(None, description="Width of the preview crop window", gt=0),
    height: Optional[int] = Query(None, description="Height of the preview crop window", gt=0)
):
    try:
        # Generate the crop preview PNG bytes
        png_bytes = PreviewService.get_preview(
            filename=filename,
            x=x,
            y=y,
            width=width,
            height=height
        )
        return Response(content=png_bytes, media_type="image/png")

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
    except InvalidWindowError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except (UnsupportedRasterError, CorruptedTIFFError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected internal error occurred: {str(e)}"
        )
