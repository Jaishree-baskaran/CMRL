from fastapi import APIRouter, HTTPException, Query, Response, status
from app.image_engine.exceptions import (
    InvalidPathError,
    TIFFNotFoundError,
    CorruptedTIFFError,
    UnsupportedRasterError
)
from app.tile_engine.exceptions import TileOutOfBoundsError, TileRenderError
from app.tile_engine.service import TileService

router = APIRouter(prefix="/tiles", tags=["Tile Engine"])

@router.get(
    "/{z}/{x}/{y}.png",
    response_class=Response,
    responses={
        200: {
            "content": {"image/png": {}},
            "description": "Returns the requested PNG tile.",
        },
        204: {
            "description": "Tile is out of bounds (contains no raster data)."
        },
        400: {
            "description": "Bad Request due to traversal or corruption."
        },
        404: {
            "description": "TIFF image not found."
        }
    },
    summary="Fetch map tile (XYZ)",
    description="Loads a 256x256 Web Mercator tile on-the-fly from the requested TIFF raster window."
)
def get_tile(
    z: int,
    x: int,
    y: int,
    filename: str = Query(
        ...,
        description="The filename of the TIFF image (must reside inside the configured data directory)",
        example="SINGLE_TRACK.tif"
    )
):
    try:
        # Retrieve the rendered tile bytes
        tile_bytes = TileService.get_tile(filename, z, x, y)
        
        return Response(content=tile_bytes, media_type="image/png")

    except TileOutOfBoundsError:
        # Return 204 No Content for coordinates outside the spatial coverage
        return Response(status_code=status.HTTP_204_NO_CONTENT)

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
    except (UnsupportedRasterError, CorruptedTIFFError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except TileRenderError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected internal error occurred: {str(e)}"
        )
