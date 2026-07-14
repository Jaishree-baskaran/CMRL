import os
import subprocess
import boto3
from pathlib import Path
from botocore.exceptions import NoCredentialsError

# Configuration
AWS_REGION = "ap-southeast-2"
FRONTEND_BUCKET_NAME = "cmrl-trials"
RASTER_BUCKET_NAME = "cmrl-trials-data"

def build_frontend():
    print("Building React frontend...")
    frontend_dir = Path(__file__).parent.parent / "frontend"
    subprocess.run("npm run build", shell=True, cwd=frontend_dir, check=True)
    print("Frontend build complete.")

def upload_directory_to_s3(local_dir, bucket_name):
    s3 = boto3.client('s3')
    local_path = Path(local_dir)
    
    print(f"Syncing local directory {local_path} to S3 bucket: {bucket_name}...")
    for file_path in local_path.rglob('*'):
        if file_path.is_file():
            # Calculate S3 relative key
            relative_key = file_path.relative_to(local_path).as_posix()
            
            # Detect Content-Type
            content_type = "binary/octet-stream"
            if file_path.suffix == ".html":
                content_type = "text/html"
            elif file_path.suffix == ".css":
                content_type = "text/css"
            elif file_path.suffix == ".js":
                content_type = "application/javascript"
            elif file_path.suffix == ".png":
                content_type = "image/png"
            elif file_path.suffix == ".svg":
                content_type = "image/svg+xml"
            
            try:
                s3.upload_file(
                    Filename=str(file_path),
                    Bucket=bucket_name,
                    Key=relative_key,
                    ExtraArgs={'ContentType': content_type}
                )
                print(f"Uploaded {relative_key}")
            except NoCredentialsError:
                print("AWS credentials not found. Configure using 'aws configure'.")
                return False
            except Exception as e:
                print(f"Failed to upload {relative_key}: {e}")
    return True

def upload_raster_to_s3(raster_path, bucket_name):
    s3 = boto3.client('s3')
    path = Path(raster_path)
    if not path.exists():
        print(f"Raster file not found: {path}")
        return False
    
    print(f"Uploading high-res raster {path.name} to S3 bucket: {bucket_name}...")
    try:
        s3.upload_file(
            Filename=str(path),
            Bucket=bucket_name,
            Key=path.name,
            ExtraArgs={'ContentType': 'image/tiff'}
        )
        print("Raster upload complete.")
        return True
    except Exception as e:
        print(f"Failed to upload raster: {e}")
        return False

if __name__ == "__main__":
    # 1. Build React
    build_frontend()
    
    # 2. Upload Frontend
    frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
    upload_directory_to_s3(frontend_dist, FRONTEND_BUCKET_NAME)
    
    # 3. Upload Raster Data
    raster_file = Path(__file__).parent.parent / "backend" / "data" / "SINGLE_TRACK.tif"
    upload_raster_to_s3(raster_file, RASTER_BUCKET_NAME)
    
    print("\nS3 Deployment Complete!")
    print(f"Frontend URL: http://{FRONTEND_BUCKET_NAME}.s3-website-{AWS_REGION}.amazonaws.com")
