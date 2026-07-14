from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.image_engine.routes import router as image_engine_router
from app.tile_engine.routes import router as tile_engine_router
from app.preview_engine.routes import router as preview_engine_router

app = FastAPI(
    title="RailVision AI API",
    description="Production-grade AI-powered Railway Geometry & Digital Twin Platform",
    version="1.0.0",
)

# Set up CORS middleware to communicate with the React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the modular routers
app.include_router(image_engine_router, prefix="/api/v1")
app.include_router(tile_engine_router, prefix="/api/v1")
app.include_router(preview_engine_router, prefix="/api/v1")

@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "RailVision AI Backend API",
        "capabilities": [
            "Railway Geometry Alignment Processing",
            "PostGIS 3D Spatial Trajectories",
            "Computer Vision Defect Inspection",
            "Network Topology Mapping"
        ]
    }

@app.get("/api/v1/health")
async def health_check():
    return {"status": "healthy"}



