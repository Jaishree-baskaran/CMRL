import rasterio
import numpy as np
import cv2
from pathlib import Path
from rasterio.enums import Resampling

def test_extract_real_rails():
    data_dir = Path("backend/data")
    tiff_path = data_dir / "SINGLE_TRACK.tif"
    if not tiff_path.exists():
        print("TIFF not found locally, looking in parent...")
        tiff_path = Path("../backend/data/SINGLE_TRACK.tif")
    
    print(f"Opening {tiff_path}...")
    with rasterio.open(tiff_path) as src:
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
        
    print(f"Image read successful. Running Canny Edge Detection on downsampled {ds_w}x{ds_h} grid...")
    # Normalize image
    norm_img = cv2.normalize(data, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
    
    # Run Canny Edge
    edges = cv2.Canny(norm_img, 50, 150)
    
    # Let's locate the rails by finding peaks in each row
    # The rails run roughly vertically, so for each row y from bottom (499) to top (0),
    # we look for edge points.
    left_rail_points = []
    right_rail_points = []
    
    for y in range(ds_h - 1, -1, -10):  # step of 10 rows for smoothness
        row_edges = np.where(edges[y, :] > 0)[0]
        if len(row_edges) < 2:
            continue
            
        # We know the rails are in the middle of the image, let's filter out border noise
        valid_cols = [x for x in row_edges if 100 < x < 400]
        if len(valid_cols) < 2:
            continue
            
        # Cluster cols into left and right rails
        # Since gauge width is constant (around 80-100 pixels in this 500px downsampled image),
        # we can partition the points by the column center
        mid = np.mean(valid_cols)
        lefts = [x for x in valid_cols if x < mid - 20]
        rights = [x for x in valid_cols if x > mid + 20]
        
        if lefts and rights:
            lx = np.mean(lefts)
            rx = np.mean(rights)
            
            # Convert to geographic coordinate
            l_lon, l_lat = rasterio.transform.xy(ds_transform, y, lx)
            r_lon, r_lat = rasterio.transform.xy(ds_transform, y, rx)
            
            left_rail_points.append([l_lon, l_lat])
            right_rail_points.append([r_lon, r_lat])
            
    print(f"Extraction complete! Found {len(left_rail_points)} track centerline points.")
    if left_rail_points:
        print("Sample Left Rail WGS84 Pt:", left_rail_points[0])
        print("Sample Right Rail WGS84 Pt:", right_rail_points[0])

if __name__ == "__main__":
    test_extract_real_rails()
