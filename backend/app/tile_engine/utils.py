import math
from typing import Tuple

def xyz_to_mercator_bounds(x: int, y: int, z: int) -> Tuple[float, float, float, float]:
    """
    Translates XYZ tile coordinates (x, y, z) to Web Mercator (EPSG:3857) meters
    returning a tuple: (left, bottom, right, top).
    """
    n = 2.0 ** z
    merc_max = 20037508.342789244
    tile_span = (merc_max * 2.0) / n

    left = -merc_max + (x * tile_span)
    right = -merc_max + ((x + 1) * tile_span)
    top = merc_max - (y * tile_span)
    bottom = merc_max - ((y + 1) * tile_span)

    return (left, bottom, right, top)
