from pydantic import BaseModel, Field

class TileCoordinates(BaseModel):
    z: int = Field(..., description="Zoom level", ge=0, le=24)
    x: int = Field(..., description="Tile X coordinate", ge=0)
    y: int = Field(..., description="Tile Y coordinate", ge=0)
