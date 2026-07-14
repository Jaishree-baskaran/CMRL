from typing import Optional
from pydantic import BaseModel, Field

class PreviewCropParams(BaseModel):
    x: Optional[int] = Field(None, description="Column offset in pixels (X coord)", ge=0)
    y: Optional[int] = Field(None, description="Row offset in pixels (Y coord)", ge=0)
    width: Optional[int] = Field(None, description="Width of the preview crop window", gt=0)
    height: Optional[int] = Field(None, description="Height of the preview crop window", gt=0)
