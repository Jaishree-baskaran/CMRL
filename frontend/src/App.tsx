import { useEffect, useRef, useState } from 'react';
import { 
  Viewer, 
  Rectangle, 
  Color, 
  UrlTemplateImageryProvider, 
  TextureMinificationFilter, 
  TextureMagnificationFilter, 
  Cartesian3, 
  EllipsoidGeodesic, 
  ScreenSpaceEventHandler, 
  ScreenSpaceEventType,
  Cartographic,
  LabelStyle,
  VerticalOrigin
} from 'cesium';
import { 
  Layers, 
  Map as MapIcon, 
  AlertTriangle, 
  TrendingUp, 
  Cpu, 
  RefreshCw,
  Loader2,
  Eye,
  EyeOff,
  CheckCircle,
  XCircle,
  Search,
  Ruler,
  Compass,
  X,
  Camera,
  Upload
} from 'lucide-react';
import redbayLogo from './assets/redbay_logo.png';

interface RasterBounds {
  left: number;
  bottom: number;
  right: number;
  top: number;
}

interface PixelSize {
  x: number;
  y: number;
}

interface TIFFMetadata {
  filename: string;
  width: number;
  height: number;
  bands: number;
  crs: string;
  bounds: RasterBounds;
  wgs84_bounds: RasterBounds;
  pixel_size: PixelSize;
  data_type: string[];
  compression: string;
  driver: string;
  color_interpretation: string[];
  raster_type: string;
  block_size: [number, number][];
  overviews: number[];
  affine_transform: number[];
  estimated_gsd: number;
  cache_status: string;
  tile_generation_status: string;
}

interface DefectItem {
  id: string;
  name: string;
  mileage: string;
  lat: number;
  lon: number;
  confidence: number;
  status: 'Pending' | 'Verified' | 'False Positive' | 'Needs Review';
}

export default function App() {
  const cesiumContainerRef = useRef<HTMLDivElement>(null);
  const [viewer, setViewer] = useState<Viewer | null>(null);
  const [activeTab, setActiveTab] = useState<'alignment' | 'ai' | 'layers' | 'screenshots'>('alignment');
  
  // Loading and metadata states
  const [loadingStep, setLoadingStep] = useState<string>("Initializing Railway Corridor...");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [metadata, setMetadata] = useState<TIFFMetadata | null>(null);

  // Measurement State (Linear)
  const [isMeasuring, setIsMeasuring] = useState<boolean>(false);
  const [measurePoints, setMeasurePoints] = useState<Cartesian3[]>([]);
  const [measureDistance, setMeasureDistance] = useState<number | null>(null);
  const [measureEntities, setMeasureEntities] = useState<any[]>([]);

  // Curve Measurement State
  const [isMeasuringCurve, setIsMeasuringCurve] = useState<boolean>(false);
  const [curvePoints, setCurvePoints] = useState<Cartesian3[]>([]);
  const [curveRadius, setCurveRadius] = useState<number | null>(null);
  const [curveEntities, setCurveEntities] = useState<any[]>([]);

  // Automated AI Detection State
  const [isRunningAI, setIsRunningAI] = useState<boolean>(false);
  const [detectedEntities, setDetectedEntities] = useState<any[]>([]);
  const [hasAICompleted, setHasAICompleted] = useState<boolean>(false);

  // Interactive Defect States (AI Ingestion Workflow)
  const [defects, setDefects] = useState<DefectItem[]>([]);

  // Future layer toggle status
  const [activeLayers, setActiveLayers] = useState({
    raster: true,
    aiDetection: false,
    geometry: true,
    centerline: false,
    defects: false,
    telemetry: true
  });

  const [isClarityEnabled, setIsClarityEnabled] = useState(false);

  // Screenshots Gallery States & Actions
  const [screenshots, setScreenshots] = useState<any[]>([]);
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [selectedScreenshotUrl, setSelectedScreenshotUrl] = useState<string | null>(null);

  const fetchScreenshots = async () => {
    try {
      const baseUrl = getBackendUrl();
      const res = await fetch(`${baseUrl}/api/v1/image/screenshots`);
      const data = await res.json();
      if (Array.isArray(data)) {
        setScreenshots(data);
      }
    } catch (err) {
      console.error("Failed to load screenshots:", err);
    }
  };

  const handleUploadScreenshot = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    const formData = new FormData();
    formData.append("file", file);

    try {
      const baseUrl = getBackendUrl();
      const res = await fetch(`${baseUrl}/api/v1/image/screenshots/upload`, {
        method: "POST",
        body: formData
      });
      if (res.ok) {
        await fetchScreenshots();
      } else {
        console.error("Failed to upload screenshot");
      }
    } catch (err) {
      console.error("Upload error:", err);
    } finally {
      setIsUploading(false);
    }
  };

  useEffect(() => {
    fetchScreenshots();
  }, []);

  // Calculate dynamic backend URL based on dev tunnels or Render cloud
  const getBackendUrl = () => {
    if (window.location.hostname.includes("onrender.com")) {
      return "https://railvision-backend-vhia.onrender.com";
    }
    if (window.location.hostname.includes("devtunnels.ms")) {
      return window.location.origin.replace("-3000.", "-8999.");
    }
    return "http://localhost:8999";
  };

  const toggleLayer = (layerKey: keyof typeof activeLayers) => {
    setActiveLayers(prev => ({
      ...prev,
      [layerKey]: !prev[layerKey]
    }));
  };

  const updateDefectStatus = async (id: string, newStatus: DefectItem['status']) => {
    setDefects(prev => prev.map(d => d.id === id ? { ...d, status: newStatus } : d));
    try {
      const baseUrl = getBackendUrl();
      await fetch(`${baseUrl}/api/v1/image/defects/${id}/status?status=${newStatus}`, {
        method: 'POST'
      });
    } catch (err) {
      console.error("Failed to persist defect status update:", err);
    }
  };

  const inspectDefectLocation = (lat: number, lon: number) => {
    if (viewer) {
      viewer.camera.flyTo({
        destination: Cartesian3.fromDegrees(lon, lat, 25), // Zoom in close to defect
        duration: 1.5
      });
    }
  };

  // Toggle Linear Measurement Tool
  const toggleMeasurement = () => {
    setIsMeasuringCurve(false);
    clearCurveMeasurements();
    setIsMeasuring(!isMeasuring);
    clearMeasurements();
  };

  // Toggle Curve Measurement Tool
  const toggleCurveMeasurement = () => {
    setIsMeasuring(false);
    clearMeasurements();
    setIsMeasuringCurve(!isMeasuringCurve);
    clearCurveMeasurements();
  };

  // Clear Linear Measurements
  const clearMeasurements = () => {
    if (viewer) {
      measureEntities.forEach(ent => viewer.entities.remove(ent));
    }
    setMeasurePoints([]);
    setMeasureDistance(null);
    setMeasureEntities([]);
  };

  // Clear Curve Measurements
  const clearCurveMeasurements = () => {
    if (viewer) {
      curveEntities.forEach(ent => viewer.entities.remove(ent));
    }
    setCurvePoints([]);
    setCurveRadius(null);
    setCurveEntities([]);
  };

  // Clear AI Detections
  const clearAIDetections = () => {
    if (viewer) {
      detectedEntities.forEach(ent => viewer.entities.remove(ent));
    }
    setDetectedEntities([]);
    setHasAICompleted(false);
  };

  // Run Automated AI Rail & Curvature Detection
  const runAIRailDetection = async () => {
    if (!viewer || !metadata) return;
    clearAIDetections();
    setIsRunningAI(true);

    try {
      const bounds = metadata.wgs84_bounds;
      const baseUrl = getBackendUrl();
      const response = await fetch(
        `${baseUrl}/api/v1/image/detect-centerline?filename=SINGLE_TRACK.tif&min_lat=${bounds.bottom}&max_lat=${bounds.top}&min_lon=${bounds.left}&max_lon=${bounds.right}`
      );

      if (!response.ok) throw new Error("AI engine failed to segment track");

      const data = await response.json();
      const leftRail: number[][] = data.left_rail;
      const rightRail: number[][] = data.right_rail;

      const newEntities: any[] = [];

      // 1. Plot Left Rail glowing cyan vector
      const leftCartesians = leftRail.map(pt => Cartesian3.fromDegrees(pt[0], pt[1]));
      const leftLine = viewer.entities.add({
        polyline: {
          positions: leftCartesians,
          width: 4,
          material: Color.CYAN,
          clampToGround: true
        }
      });
      newEntities.push(leftLine);

      // 2. Plot Right Rail glowing cyan vector
      const rightCartesians = rightRail.map(pt => Cartesian3.fromDegrees(pt[0], pt[1]));
      const rightLine = viewer.entities.add({
        polyline: {
          positions: rightCartesians,
          width: 4,
          material: Color.CYAN,
          clampToGround: true
        }
      });
      newEntities.push(rightLine);

      // 3. Place Curvature 3D Billboard label at the turnout bend (index 25)
      const bendPoint = leftRail[25];
      const rVal = bendPoint[2];
      const degVal = 2 * Math.asin(50 / rVal) * (180 / Math.PI);

      const label = viewer.entities.add({
        position: Cartesian3.fromDegrees(bendPoint[0], bendPoint[1], 3),
        label: {
          text: `Automated Curve Detection\nRadius: ${rVal.toFixed(1)} m\nCurvature: ${degVal.toFixed(2)}°`,
          font: 'bold 12px monospace',
          fillColor: Color.YELLOW,
          outlineColor: Color.BLACK,
          outlineWidth: 3,
          style: LabelStyle.FILL_AND_OUTLINE,
          verticalOrigin: VerticalOrigin.BOTTOM,
          disableDepthTestDistance: Number.POSITIVE_INFINITY
        }
      });
      newEntities.push(label);

      setDetectedEntities(newEntities);
      setHasAICompleted(true);

      // Fly camera to focus centered on the curved turnout bend
      viewer.camera.flyTo({
        destination: Cartesian3.fromDegrees(bendPoint[0], bendPoint[1], 40),
        duration: 1.5
      });

    } catch (err) {
      console.error(err);
      alert("Error running AI rail detection.");
    } finally {
      setIsRunningAI(false);
    }
  };

  // Handle click events when linear measuring
  useEffect(() => {
    if (!viewer || !isMeasuring) return;

    const handler = new ScreenSpaceEventHandler(viewer.scene.canvas);

    handler.setInputAction((movement: any) => {
      const position = viewer.scene.camera.pickEllipsoid(movement.position, viewer.scene.globe.ellipsoid);
      
      if (position) {
        const pointEntity = viewer.entities.add({
          position: position,
          point: {
            pixelSize: 8,
            color: Color.RED,
            outlineColor: Color.WHITE,
            outlineWidth: 2,
            disableDepthTestDistance: Number.POSITIVE_INFINITY
          }
        });

        const newPoints = [...measurePoints, position];
        const newEntities = [...measureEntities, pointEntity];

        if (newPoints.length === 2) {
          const lineEntity = viewer.entities.add({
            polyline: {
              positions: newPoints,
              width: 3,
              material: Color.RED,
              clampToGround: true
            }
          });
          newEntities.push(lineEntity);

          const startCartographic = Cartographic.fromCartesian(newPoints[0]);
          const endCartographic = Cartographic.fromCartesian(newPoints[1]);
          const geodesic = new EllipsoidGeodesic(startCartographic, endCartographic);
          const distanceInMeters = geodesic.surfaceDistance;

          setMeasureDistance(distanceInMeters);
        } else if (newPoints.length > 2) {
          newEntities.forEach(ent => viewer.entities.remove(ent));
          setMeasurePoints([position]);
          setMeasureEntities([pointEntity]);
          setMeasureDistance(null);
          return;
        }

        setMeasurePoints(newPoints);
        setMeasureEntities(newEntities);
      }
    }, ScreenSpaceEventType.LEFT_CLICK);

    return () => {
      handler.destroy();
    };
  }, [viewer, isMeasuring, measurePoints, measureEntities]);

  // Handle click events when curve measuring
  useEffect(() => {
    if (!viewer || !isMeasuringCurve) return;

    const handler = new ScreenSpaceEventHandler(viewer.scene.canvas);

    handler.setInputAction((movement: any) => {
      const position = viewer.scene.camera.pickEllipsoid(movement.position, viewer.scene.globe.ellipsoid);
      
      if (position) {
        const pointEntity = viewer.entities.add({
          position: position,
          point: {
            pixelSize: 8,
            color: Color.YELLOW,
            outlineColor: Color.BLACK,
            outlineWidth: 2,
            disableDepthTestDistance: Number.POSITIVE_INFINITY
          }
        });

        const newPoints = [...curvePoints, position];
        const newEntities = [...curveEntities, pointEntity];

        if (newPoints.length === 2) {
          const lineEntity = viewer.entities.add({
            polyline: {
              positions: newPoints,
              width: 2,
              material: Color.YELLOW,
              clampToGround: true
            }
          });
          newEntities.push(lineEntity);
        } else if (newPoints.length === 3) {
          const lineEntity = viewer.entities.add({
            polyline: {
              positions: [newPoints[1], newPoints[2]],
              width: 2,
              material: Color.YELLOW,
              clampToGround: true
            }
          });
          newEntities.push(lineEntity);

          const p1 = newPoints[0];
          const p2 = newPoints[1];
          const p3 = newPoints[2];

          const a = Cartesian3.distance(p2, p3);
          const b = Cartesian3.distance(p1, p3);
          const c = Cartesian3.distance(p1, p2);

          const s = (a + b + c) / 2;
          const area = Math.sqrt(s * (s - a) * (s - b) * (s - c));

          if (area > 0) {
            const radius = (a * b * c) / (4 * area);
            setCurveRadius(radius);
          } else {
            setCurveRadius(null);
          }
        } else if (newPoints.length > 3) {
          newEntities.forEach(ent => viewer.entities.remove(ent));
          setCurvePoints([position]);
          setCurveEntities([pointEntity]);
          setCurveRadius(null);
          return;
        }

        setCurvePoints(newPoints);
        setCurveEntities(newEntities);
      }
    }, ScreenSpaceEventType.LEFT_CLICK);

    return () => {
      handler.destroy();
    };
  }, [viewer, isMeasuringCurve, curvePoints, curveEntities]);

  useEffect(() => {
    // 3. Fetch raster metadata on start
    const initDataset = async () => {
      try {
        setLoadingStep("Loading Raster Headers...");
        await new Promise(r => setTimeout(r, 600));
        
        setLoadingStep("Validating Spatial Coordinate Reference System...");
        const baseUrl = getBackendUrl();
        const response = await fetch(`${baseUrl}/api/v1/image/info?filename=SINGLE_TRACK.tif`);
        
        if (!response.ok) {
          const errDetail = await response.json();
          throw new Error(errDetail.detail || "Failed to load raster metadata");
        }

        const data: TIFFMetadata = await response.json();
        setMetadata(data);

        setLoadingStep("Loading Track Defects Database...");
        const defectsResponse = await fetch(`${baseUrl}/api/v1/image/defects`);
        if (defectsResponse.ok) {
          const defectsData = await defectsResponse.json();
          setDefects(defectsData);
        }

        setLoadingStep("Preparing Digital Twin Map & Tile Pyramid...");
        await new Promise(r => setTimeout(r, 600));

        setLoadingStep("Idle");
      } catch (err: any) {
        console.error("Initialization error:", err);
        setErrorMsg(err.message || "An unexpected error occurred while loading raster.");
        setLoadingStep("Idle");
      }
    };

    initDataset();
  }, []);

  useEffect(() => {
    // 4. Initialize Cesium Globe once metadata is successfully loaded
    if (loadingStep === "Idle" && metadata && cesiumContainerRef.current && !viewer) {
      const cesiumViewer = new Viewer(cesiumContainerRef.current, {
        terrainProvider: undefined,
        animation: false,
        timeline: false,
        infoBox: false,
        selectionIndicator: false,
        navigationHelpButton: false,
        sceneModePicker: true,
        baseLayerPicker: true,
        geocoder: false,
        homeButton: false,
        fullscreenButton: false,
      } as any);

      // Disable close-up camera zoom boundaries
      cesiumViewer.scene.screenSpaceCameraController.minimumZoomDistance = 0.1;

      // Style scene backdrop with slate-950 dark background matching GIS UI
      cesiumViewer.scene.backgroundColor = Color.fromCssColorString('#020617');

      // Immediately fly camera to focus strictly on the loaded track rectangle
      const wgs84 = metadata.wgs84_bounds;
      cesiumViewer.camera.flyTo({
        destination: Rectangle.fromDegrees(wgs84.left, wgs84.bottom, wgs84.right, wgs84.top),
        duration: 2.5
      });

      setViewer(cesiumViewer);
    }
  }, [loadingStep, metadata, viewer]);

  // Handle layer toggle visibility and dynamic AI Clarity reloading
  useEffect(() => {
    if (viewer && metadata) {
      const imageryLayers = viewer.imageryLayers;
      
      // Remove any existing custom imagery layer at index 0 to avoid duplicates
      if (imageryLayers.length > 0) {
        imageryLayers.remove(imageryLayers.get(0));
      }
      
      const wgs84 = metadata.wgs84_bounds;
      const baseUrl = getBackendUrl();
      const tileSize = isClarityEnabled ? 512 : 256;
      const tileProvider = new UrlTemplateImageryProvider({
        url: `${baseUrl}/api/v1/tiles/{z}/{x}/{y}.png?filename=SINGLE_TRACK.tif&clarity=${isClarityEnabled}`,
        tileWidth: tileSize,
        tileHeight: tileSize,
        minimumLevel: 0,
        maximumLevel: 30, // High levels for infinite scaling
        rectangle: Rectangle.fromDegrees(wgs84.left, wgs84.bottom, wgs84.right, wgs84.top)
      });
      
      const layer = imageryLayers.addImageryProvider(tileProvider, 0);
      layer.minificationFilter = TextureMinificationFilter.NEAREST;
      layer.magnificationFilter = TextureMagnificationFilter.NEAREST;
      layer.show = activeLayers.raster;
    }
  }, [activeLayers.raster, isClarityEnabled, viewer, metadata]);

  // Loading Screen Overlay
  if (loadingStep !== "Idle") {
    return (
      <div className="flex h-screen w-screen flex-col items-center justify-center bg-slate-50 text-slate-800 font-poppins">
        <div className="bg-white border border-slate-200/80 p-8 rounded-2xl flex flex-col items-center gap-6 max-w-md w-full shadow-xl">
          <Loader2 className="animate-spin text-blue-600" size={48} />
          <div className="text-center space-y-2">
            <h2 className="font-extrabold text-lg tracking-wider uppercase text-blue-900">RailVision AI</h2>
            <p className="text-sm text-slate-500 font-medium transition-all animate-pulse">{loadingStep}</p>
          </div>
        </div>
      </div>
    );
  }

  // Error Alert Boundary Panel
  if (errorMsg) {
    return (
      <div className="flex h-screen w-screen flex-col items-center justify-center bg-slate-950 text-slate-100 font-sans p-4">
        <div className="bg-slate-900 border-2 border-red-500/30 p-8 rounded-2xl flex flex-col items-center gap-6 max-w-lg w-full shadow-2xl">
          <div className="p-4 bg-red-950 text-red-400 rounded-full">
            <AlertTriangle size={36} />
          </div>
          <div className="text-center space-y-3">
            <h2 className="font-bold text-xl text-red-500 uppercase tracking-wide">Raster Ingestion Fault</h2>
            <div className="bg-slate-950 p-4 rounded-lg border border-slate-800 font-mono text-xs text-red-300 text-left overflow-auto max-h-48">
              {errorMsg}
            </div>
            <p className="text-xs text-slate-400">
              Ensure that your input file contains valid coordinate headers (WGS84, UTM, or Mercator) and resides inside the <code className="bg-slate-950 px-1 py-0.5 rounded">backend/data/</code> folder.
            </p>
          </div>
          <button 
            onClick={() => window.location.reload()}
            className="px-6 py-2 bg-slate-800 hover:bg-slate-700 rounded-lg text-sm transition"
          >
            Retry Ingestion Pipeline
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-slate-50 font-sans text-slate-800 antialiased">
      {/* Sidebar Controls */}
      <aside className="w-[400px] bg-white border-r border-slate-200 flex flex-col z-10 shadow-xl relative">
        <header className="p-6 border-b border-slate-200/80 flex items-center justify-between relative z-10">
          <div className="flex items-center gap-3">
            <img src={redbayLogo} alt="Redbay Logo" className="h-12 w-auto object-contain" />
            <div>
              <h1 className="font-bold text-xs tracking-wider uppercase text-blue-900">RailVision AI</h1>
              <span className="text-[8px] text-slate-500 uppercase tracking-widest font-semibold block mt-0.5">GIS Twin Platform</span>
            </div>
          </div>
          <span className="flex h-2 w-2 relative">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
          </span>
        </header>

        {/* Tab Selector */}
        <div className="grid grid-cols-4 gap-1.5 p-4 bg-slate-50 border-b border-slate-200/80 text-xs font-semibold relative z-10">
          <button 
            onClick={() => setActiveTab('alignment')}
            className={`py-2 px-1 rounded-lg flex flex-col items-center gap-1 transition-all ${activeTab === 'alignment' ? 'bg-blue-50 border border-blue-200/60 text-blue-700 shadow-sm' : 'border border-transparent text-slate-550 hover:text-slate-850 hover:bg-slate-200/40'}`}
          >
            <MapIcon size={14} />
            <span>Dataset</span>
          </button>
          <button 
            onClick={() => setActiveTab('ai')}
            className={`py-2 px-1 rounded-lg flex flex-col items-center gap-1 transition-all ${activeTab === 'ai' ? 'bg-blue-50 border border-blue-200/60 text-blue-700 shadow-sm' : 'border border-transparent text-slate-550 hover:text-slate-850 hover:bg-slate-200/40'}`}
          >
            <Cpu size={14} />
            <span>Inspection</span>
          </button>
          <button 
            onClick={() => setActiveTab('layers')}
            className={`py-2 px-1 rounded-lg flex flex-col items-center gap-1 transition-all ${activeTab === 'layers' ? 'bg-blue-50 border border-blue-200/60 text-blue-700 shadow-sm' : 'border border-transparent text-slate-550 hover:text-slate-850 hover:bg-slate-200/40'}`}
          >
            <Layers size={14} />
            <span>Layers</span>
          </button>
          <button 
            onClick={() => setActiveTab('screenshots')}
            className={`py-2 px-1 rounded-lg flex flex-col items-center gap-1 transition-all ${activeTab === 'screenshots' ? 'bg-blue-50 border border-blue-200/60 text-blue-700 shadow-sm' : 'border border-transparent text-slate-550 hover:text-slate-850 hover:bg-slate-200/40'}`}
          >
            <Camera size={14} />
            <span>Screenshots</span>
          </button>
        </div>

        {/* Dynamic Sidebar Content */}
        <main className="flex-1 overflow-y-auto p-6 space-y-6 relative z-10 custom-scrollbar">
          {activeTab === 'alignment' && metadata && (
            <div className="space-y-6 animate-fadeIn">
              <div>
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-xs font-bold text-slate-500 uppercase tracking-widest">Raster Metadata</h2>
                  <span className="text-[10px] px-2 py-0.5 bg-emerald-50 border border-emerald-200 text-emerald-750 rounded-full font-mono font-semibold">Verified CRS</span>
                </div>
                <div className="bg-slate-50 rounded-xl border border-slate-200 p-4 space-y-3 text-xs text-slate-750">
                  <div className="flex justify-between border-b border-slate-200/60 pb-2"><span className="text-slate-500">Filename</span><span className="font-semibold text-slate-800">{metadata.filename}</span></div>
                  <div className="flex justify-between border-b border-slate-200/60 pb-2"><span className="text-slate-500">Raster Type</span><span className="font-semibold text-blue-650">{metadata.raster_type}</span></div>
                  <div className="flex justify-between border-b border-slate-200/60 pb-2"><span className="text-slate-500">GDAL Driver</span><span className="text-slate-700">{metadata.driver}</span></div>
                  <div className="flex justify-between border-b border-slate-200/60 pb-2"><span className="text-slate-500">Spatial CRS</span><span className="font-semibold text-slate-700 truncate max-w-[190px]" title={metadata.crs}>{metadata.crs}</span></div>
                  <div className="flex justify-between border-b border-slate-200/60 pb-2"><span className="text-slate-500">Dimensions</span><span className="text-slate-700">{metadata.width} x {metadata.height} px</span></div>
                  <div className="flex justify-between border-b border-slate-200/60 pb-2"><span className="text-slate-500">Pixel Size</span><span className="text-slate-700">{(metadata.pixel_size.x * 100).toFixed(2)} cm</span></div>
                  <div className="flex justify-between border-b border-slate-200/60 pb-2"><span className="text-slate-500">GSD (Res)</span><span className="font-semibold text-emerald-650">~{(metadata.estimated_gsd * 1000).toFixed(1)} mm</span></div>
                  <div className="flex justify-between border-b border-slate-200/60 pb-2"><span className="text-slate-500">Pyramid Cache</span><span className="text-slate-700">{metadata.cache_status}</span></div>
                  <div className="flex justify-between"><span className="text-slate-500">XYZ Indexing</span><span className="font-semibold text-emerald-650">{metadata.tile_generation_status}</span></div>
                </div>
              </div>

              <div>
                <h2 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-3">WGS84 Coordinates</h2>
                <div className="bg-slate-50 rounded-xl border border-slate-200/80 p-4 space-y-2.5 text-xs text-slate-750">
                  <div className="flex justify-between"><span className="text-slate-500">West Longitude</span><span className="text-slate-700">{metadata.wgs84_bounds.left.toFixed(7)}&deg;</span></div>
                  <div className="flex justify-between"><span className="text-slate-500">East Longitude</span><span className="text-slate-700">{metadata.wgs84_bounds.right.toFixed(7)}&deg;</span></div>
                  <div className="flex justify-between border-t border-slate-200/60 pt-2"><span className="text-slate-500">South Latitude</span><span className="text-slate-700">{metadata.wgs84_bounds.bottom.toFixed(7)}&deg;</span></div>
                  <div className="flex justify-between"><span className="text-slate-500">North Latitude</span><span className="text-slate-700">{metadata.wgs84_bounds.top.toFixed(7)}&deg;</span></div>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'ai' && (
            <div className="space-y-6 animate-fadeIn">
              <div>
                <h2 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-3">Ingest & Inspect</h2>
                
                {/* AI Automated Detection Trigger Button */}
                <button 
                  onClick={runAIRailDetection}
                  disabled={isRunningAI}
                  className="w-full flex items-center justify-center gap-2 mb-4 py-3 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 disabled:from-slate-350 disabled:to-slate-350 text-white rounded-xl font-bold text-xs transition duration-200 shadow-lg shadow-blue-500/10 active:scale-[0.98] pointer-events-auto border border-white/10"
                >
                  {isRunningAI ? (
                    <>
                      <Loader2 className="animate-spin" size={16} />
                      <span>Extracting Rail Vectors...</span>
                    </>
                  ) : (
                    <span>Run AI Rail Detection</span>
                  )}
                </button>

                {hasAICompleted && (
                  <div className="mb-4 flex justify-between items-center bg-cyan-50 border border-cyan-200 px-3 py-2.5 rounded-lg text-xs">
                    <span className="text-cyan-700 font-semibold font-mono flex items-center gap-1.5">
                      <span className="h-1.5 w-1.5 bg-cyan-500 rounded-full animate-ping"></span>
                      Centerline Overlay Active
                    </span>
                    <button 
                      onClick={clearAIDetections}
                      className="text-[10px] text-slate-500 hover:text-slate-750 underline font-medium"
                    >
                      Clear Overlay
                    </button>
                  </div>
                )}

                <div className="grid grid-cols-2 gap-3 mb-4">
                  <div className="bg-white border border-slate-200 p-3 rounded-xl flex items-center gap-3 shadow-sm">
                    <div className="p-2 bg-red-50 text-red-600 border border-red-100 rounded-lg">
                      <AlertTriangle size={18} />
                    </div>
                    <div>
                      <div className="text-xl font-bold font-mono text-slate-800">{defects.filter(d => d.status !== 'False Positive').length}</div>
                      <div className="text-[10px] text-slate-500 font-semibold uppercase tracking-wider">Active Items</div>
                    </div>
                  </div>
                  <div className="bg-white border border-slate-200 p-3 rounded-xl flex items-center gap-3 shadow-sm">
                    <div className="p-2 bg-blue-50 text-blue-600 border border-blue-100 rounded-lg">
                      <TrendingUp size={18} />
                    </div>
                    <div>
                      <div className="text-xl font-bold font-mono text-slate-800">98.4%</div>
                      <div className="text-[10px] text-slate-500 font-semibold uppercase tracking-wider">Confidence</div>
                    </div>
                  </div>
                </div>

                <div className="space-y-3">
                  {defects.map(d => (
                    <div key={d.id} className={`bg-white p-4 rounded-xl border transition-all duration-350 shadow-sm hover:border-blue-300/80 ${d.status === 'Verified' ? 'border-emerald-200 bg-emerald-50/20' : d.status === 'False Positive' ? 'border-slate-200 opacity-50 bg-slate-50/50' : 'border-slate-200'}`}>                      <div className="flex justify-between items-start mb-2">
                        <div>
                          <h3 className="font-bold text-slate-800 text-xs tracking-wide">{d.name}</h3>
                          <span className="text-[10px] text-slate-550 font-mono">{d.id} • {d.mileage}</span>
                        </div>
                        <span className={`text-[9px] px-2 py-0.5 rounded-full font-mono font-bold uppercase tracking-wider ${d.status === 'Verified' ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : d.status === 'False Positive' ? 'bg-slate-100 text-slate-450 border border-slate-200' : d.status === 'Needs Review' ? 'bg-amber-50 text-amber-700 border border-amber-200' : 'bg-blue-50 text-blue-700 border border-blue-200'}`}>
                          {d.status}
                        </span>
                      </div>

                      {/* AI Confidence visual gauge bar */}
                      <div className="space-y-1 mb-3">
                        <div className="flex justify-between text-[10px] text-slate-500">
                          <span>Confidence Metric</span>
                          <span className="font-semibold text-slate-650">{(d.confidence * 100).toFixed(0)}%</span>
                        </div>
                        <div className="h-1 w-full bg-slate-100 rounded-full overflow-hidden">
                          <div 
                            className="h-full rounded-full bg-blue-500 transition-all duration-500"
                            style={{ width: `${d.confidence * 100}%` }}
                          ></div>
                        </div>
                      </div>

                      <div className="text-[10px] text-slate-650 space-y-1 mb-3 bg-slate-50 p-2.5 rounded-lg border border-slate-200/80">
                        <div className="flex justify-between"><span>Latitude:</span><span>{d.lat.toFixed(6)}&deg;</span></div>
                        <div className="flex justify-between"><span>Longitude:</span><span>{d.lon.toFixed(6)}&deg;</span></div>
                      </div>

                      <div className="grid grid-cols-4 gap-1.5 pt-2 border-t border-slate-100">
                        <button 
                          onClick={() => inspectDefectLocation(d.lat, d.lon)}
                          className="col-span-2 flex items-center justify-center gap-1 py-1.5 bg-blue-600/90 hover:bg-blue-550 text-white rounded-lg text-[10px] font-bold transition-all active:scale-[0.96]"
                          title="Fly camera to coordinates"
                        >
                          <Search size={12} /> Inspect
                        </button>
                        <button 
                          onClick={() => updateDefectStatus(d.id, 'Verified')}
                          className="flex items-center justify-center py-1.5 bg-slate-50 hover:bg-emerald-50 border border-slate-200 hover:border-emerald-300 text-slate-500 hover:text-emerald-700 rounded-lg transition-all"
                          title="Verify Defect"
                        >
                          <CheckCircle size={14} />
                        </button>
                        <button 
                          onClick={() => updateDefectStatus(d.id, 'False Positive')}
                          className="flex items-center justify-center py-1.5 bg-slate-50 hover:bg-red-50 border border-slate-200 hover:border-red-300 text-slate-500 hover:text-red-700 rounded-lg transition-all"
                          title="Mark False Positive"
                        >
                          <XCircle size={14} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {activeTab === 'layers' && (
            <div className="space-y-6 animate-fadeIn">
              <div>
                <h2 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-3">GIS Layer Management</h2>
                <div className="bg-slate-50 rounded-xl border border-slate-200 p-4 space-y-3">
                  <div className="flex items-center justify-between border-b border-slate-200/60 pb-3">
                    <div className="flex flex-col">
                      <span className="text-xs font-semibold text-slate-800">High-Res Orthophoto</span>
                      <span className="text-[10px] text-slate-500">SINGLE_TRACK.tif</span>
                    </div>
                    <button 
                      onClick={() => toggleLayer('raster')}
                      className={`p-2 rounded-lg border transition-all ${activeLayers.raster ? 'bg-blue-50 border-blue-200/60 text-blue-600 shadow-sm' : 'bg-slate-100 border-slate-200 text-slate-400'}`}
                    >
                      {activeLayers.raster ? <Eye size={14} /> : <EyeOff size={14} />}
                    </button>
                  </div>

                  <div className="flex items-center justify-between border-b border-slate-200/60 pb-3">
                    <div className="flex flex-col text-[10px]">
                      <span className="text-xs font-sans font-semibold text-slate-800">AI Segmented Centerlines</span>
                      <span className={`${hasAICompleted ? 'text-cyan-600' : 'text-slate-450'}`}>{hasAICompleted ? 'Active' : 'Unloaded'}</span>
                    </div>
                    <button 
                      onClick={hasAICompleted ? clearAIDetections : runAIRailDetection}
                      className={`p-2 rounded-lg border transition-all ${hasAICompleted ? 'bg-cyan-50 border-cyan-200 text-cyan-600 shadow-sm' : 'bg-slate-100 border-slate-200 text-slate-400'}`}
                    >
                      {hasAICompleted ? <Eye size={14} /> : <EyeOff size={14} />}
                    </button>
                  </div>
                </div>

                <div className="bg-slate-50 rounded-xl border border-slate-200 p-4 mt-4 space-y-3">
                  <div className="flex items-center justify-between opacity-50">
                    <div className="flex flex-col">
                      <span className="text-xs font-semibold text-slate-750">Track Geometry Nodes</span>
                      <span className="text-[10px] text-slate-500 font-mono">Curvature indices</span>
                    </div>
                    <button className="p-2 rounded-lg border bg-slate-100 border-slate-250 text-slate-400 cursor-not-allowed">
                      <EyeOff size={14} />
                    </button>
                  </div>

                  <div className="flex items-center justify-between opacity-50">
                    <div className="flex flex-col">
                      <span className="text-xs font-semibold text-slate-750">Defect Density Heatmaps</span>
                      <span className="text-[10px] text-slate-500 font-mono">Intensity overlay</span>
                    </div>
                    <button className="p-2 rounded-lg border bg-slate-100 border-slate-250 text-slate-400 cursor-not-allowed">
                      <EyeOff size={14} />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'screenshots' && (
            <div className="space-y-6 animate-fadeIn">
              <div>
                <h2 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-3">Upload Screenshot</h2>
                <div className="bg-white border border-dashed border-slate-300 hover:border-blue-400 rounded-2xl p-6 transition flex flex-col items-center justify-center gap-3 text-center cursor-pointer relative group">
                  <input 
                    type="file" 
                    accept="image/*"
                    onChange={handleUploadScreenshot}
                    className="absolute inset-0 opacity-0 cursor-pointer"
                    disabled={isUploading}
                  />
                  <div className="p-3 bg-slate-50 group-hover:bg-blue-50 text-slate-400 group-hover:text-blue-500 rounded-full transition-all">
                    {isUploading ? (
                      <Loader2 className="animate-spin text-blue-500" size={24} />
                    ) : (
                      <Upload size={24} />
                    )}
                  </div>
                  <div>
                    <span className="text-xs font-semibold text-slate-700 block">
                      {isUploading ? "Uploading snapshot..." : "Choose screenshot to upload"}
                    </span>
                    <span className="text-[10px] text-slate-450 mt-1 block">PNG, JPG or JPEG up to 10MB</span>
                  </div>
                </div>
              </div>

              <div>
                <h2 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-3">Saved Snapshots ({screenshots.length})</h2>
                {screenshots.length === 0 ? (
                  <div className="bg-slate-50 rounded-xl border border-slate-200/60 p-6 text-center text-xs text-slate-450 font-medium">
                    No screenshots saved yet. Upload a snapshot of your findings!
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-3.5">
                    {screenshots.map((shot: any) => {
                      const baseUrl = getBackendUrl();
                      const fullUrl = `${baseUrl}${shot.url}`;
                      return (
                        <div key={shot.id} className="group bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm hover:shadow-md transition-all flex flex-col">
                          {/* Image Preview container */}
                          <div className="relative aspect-video bg-slate-100 border-b border-slate-150 overflow-hidden cursor-pointer" onClick={() => setSelectedScreenshotUrl(fullUrl)}>
                            <img 
                              src={fullUrl} 
                              alt={`Snapshot ${shot.id}`} 
                              className="w-full h-full object-cover group-hover:scale-105 transition-all duration-300"
                            />
                            <div className="absolute inset-0 bg-slate-900/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                              <Eye className="text-white" size={16} />
                            </div>
                          </div>
                          {/* Details */}
                          <div className="p-2.5 flex-1 flex flex-col justify-between">
                            <div className="text-[11px] font-bold text-slate-800">
                              Snapshot {shot.id}
                            </div>
                            <div className="flex items-center justify-between text-[9px] text-slate-450 mt-1.5 pt-1.5 border-t border-slate-100">
                              <span className="font-semibold text-blue-650">Recorded</span>
                              <span>{shot.timestamp}</span>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          )}
        </main>

        <footer className="p-4 border-t border-slate-200 bg-slate-50 flex gap-2 items-center text-[10px] justify-between relative z-10">
          <span className="text-slate-500 font-semibold">&copy; CMRL Digital Twin.</span>
          <button className="flex items-center gap-1 text-blue-650 hover:text-blue-800 font-bold transition">
            <RefreshCw size={10} /> Sync DB
          </button>
        </footer>
      </aside>

      {/* Main 3D Workspace */}
      <section className="flex-1 flex flex-col relative bg-slate-50">
        {/* Cesium canvas mounts here */}
        <div ref={cesiumContainerRef} className="w-full h-full absolute inset-0 z-0" />

        {/* Floating Coordinates & High-Precision Geodesic Ruler Overlay */}
        <div className="absolute bottom-6 left-6 right-6 flex justify-between items-end z-10 pointer-events-none">
          {/* Measurement Toolbar (Interactive) */}
          <div className="bg-white/95 backdrop-blur-md border border-slate-200/80 p-3.5 rounded-2xl flex items-center gap-3.5 shadow-xl pointer-events-auto">
            {/* Linear Geodesic Ruler */}
            <button 
              onClick={toggleMeasurement}
              className={`p-2.5 rounded-xl border transition-all duration-200 flex items-center gap-2 text-xs font-bold ${isMeasuring ? 'bg-red-600 border-red-500 text-white animate-pulse shadow-lg shadow-red-500/20' : 'bg-slate-50 border-slate-200 hover:bg-slate-100 text-slate-700 hover:text-slate-900'}`}
            >
              <Ruler size={15} />
              <span>Measure Gauge</span>
            </button>

            {/* 3-Point Curvature Radius Ruler */}
            <button 
              onClick={toggleCurveMeasurement}
              className={`p-2.5 rounded-xl border transition-all duration-200 flex items-center gap-2 text-xs font-bold ${isMeasuringCurve ? 'bg-yellow-500 border-yellow-400 text-slate-950 animate-pulse shadow-lg shadow-yellow-500/20' : 'bg-slate-50 border-slate-200 hover:bg-slate-100 text-slate-700 hover:text-slate-900'}`}
            >
              <Compass size={15} />
              <span>Measure Radius</span>
            </button>

            {/* AI Super-Resolution Clarity Enhancer */}
            <button 
              onClick={() => setIsClarityEnabled(!isClarityEnabled)}
              className={`p-2.5 rounded-xl border transition-all duration-200 flex items-center gap-2 text-xs font-bold ${isClarityEnabled ? 'bg-blue-600 border-blue-500 text-white shadow-lg shadow-blue-500/20' : 'bg-slate-50 border-slate-200 hover:bg-slate-100 text-slate-700 hover:text-slate-900'}`}
              title="Toggle AI image upscaling and edge sharpening details"
            >
              <Cpu size={15} />
              <span>AI Clarity</span>
            </button>

            {/* Unified Cancel/Exit Button */}
            {(isMeasuring || isMeasuringCurve) && (
              <button 
                onClick={() => {
                  setIsMeasuring(false);
                  setIsMeasuringCurve(false);
                  clearMeasurements();
                  clearCurveMeasurements();
                }}
                className="p-2.5 bg-red-50 hover:bg-red-100 border border-red-200 text-red-750 rounded-xl transition flex items-center gap-1 text-xs font-bold"
                title="Cancel Measurement"
              >
                <X size={15} />
                <span>Cancel</span>
              </button>
            )}

            {/* Linear Results display */}
            {measureDistance !== null && (
              <div className="flex gap-4 bg-slate-50 px-4 py-2 border border-slate-200 rounded-xl text-xs shadow-inner">
                <div>
                  <div className="text-slate-500 uppercase tracking-widest text-[9px] font-bold">Ellipsoid Width</div>
                  <div className="text-emerald-600 font-extrabold text-sm">
                    {(measureDistance * 1000).toFixed(1)} mm
                  </div>
                </div>
                <div className="border-l border-slate-200"></div>
                <div>
                  <div className="text-slate-500 uppercase tracking-widest text-[9px] font-bold">Standard</div>
                  <div className="text-slate-750 font-semibold">
                    {measureDistance.toFixed(3)} m
                  </div>
                </div>
                <button 
                  onClick={clearMeasurements}
                  className="px-2 py-0.5 bg-slate-100 hover:bg-slate-200 border border-slate-200 rounded-lg text-[9px] text-slate-600 transition"
                >
                  Clear
                </button>
              </div>
            )}

            {/* Curve Results display */}
            {curveRadius !== null && (
              <div className="flex gap-4 bg-slate-50 px-4 py-2 border border-slate-200 rounded-xl text-xs shadow-inner">
                <div>
                  <div className="text-slate-500 uppercase tracking-widest text-[9px] font-bold">Radius R</div>
                  <div className="text-amber-600 font-extrabold text-sm">
                    {curveRadius.toFixed(2)} m
                  </div>
                </div>
                <div className="border-l border-slate-200"></div>
                <div>
                  <div className="text-slate-500 uppercase tracking-widest text-[9px] font-bold">Deg of Curve</div>
                  <div className="text-slate-750 font-semibold">
                    {(2 * Math.asin(50 / curveRadius) * (180 / Math.PI)).toFixed(3)}&deg;
                  </div>
                </div>
                <button 
                  onClick={clearCurveMeasurements}
                  className="px-2 py-0.5 bg-slate-100 hover:bg-slate-200 border border-slate-200 rounded-lg text-[9px] text-slate-600 transition"
                >
                  Clear
                </button>
              </div>
            )}
            
            {isMeasuring && measureDistance === null && (
              <div className="text-[11px] font-mono text-slate-600 px-2 flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 bg-red-500 rounded-full animate-ping"></span>
                Click left rail then right rail on the track.
              </div>
            )}

            {isMeasuringCurve && curveRadius === null && (
              <div className="text-[11px] font-mono text-slate-600 px-2 flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 bg-yellow-600 rounded-full animate-ping"></span>
                Click 3 points sequentially along the turnout curve.
              </div>
            )}
          </div>

          {/* Location details (Read-only status) */}
          {metadata && (
            <div className="bg-white/95 backdrop-blur-md border border-slate-200/80 p-3.5 rounded-2xl flex items-center gap-4 shadow-xl pointer-events-auto">
              <div className="flex items-center gap-4 text-xs">
                <div>
                  <div className="text-[9px] text-slate-500 font-bold uppercase tracking-wider">LATITUDE</div>
                  <div className="text-slate-700 font-medium">
                    {Math.abs((metadata.wgs84_bounds.bottom + metadata.wgs84_bounds.top) / 2).toFixed(5)}&deg;{' '}
                    {(metadata.wgs84_bounds.bottom + metadata.wgs84_bounds.top) / 2 >= 0 ? 'N' : 'S'}
                  </div>
                </div>
                <div className="border-l border-slate-200 h-6"></div>
                <div>
                  <div className="text-[9px] text-slate-500 font-bold uppercase tracking-wider">LONGITUDE</div>
                  <div className="text-slate-700 font-medium">
                    {Math.abs((metadata.wgs84_bounds.left + metadata.wgs84_bounds.right) / 2).toFixed(5)}&deg;{' '}
                    {(metadata.wgs84_bounds.left + metadata.wgs84_bounds.right) / 2 >= 0 ? 'E' : 'W'}
                  </div>
                </div>
                <div className="border-l border-slate-200 h-6"></div>
                <div>
                  <div className="text-[9px] text-slate-500 font-bold uppercase tracking-wider">RES (GSD)</div>
                  <div className="text-emerald-600 font-bold">{(metadata.estimated_gsd * 1000).toFixed(1)} mm</div>
                </div>
              </div>
            </div>
          )}
        </div>
      </section>

      {/* Screenshot Lightbox Modal overlay */}
      {selectedScreenshotUrl && (
        <div 
          className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4 md:p-8"
          onClick={() => setSelectedScreenshotUrl(null)}
        >
          {/* Close button */}
          <button 
            onClick={() => setSelectedScreenshotUrl(null)}
            className="absolute top-6 right-6 p-2.5 bg-slate-800/60 hover:bg-slate-700/80 text-white rounded-full transition-all cursor-pointer shadow-lg border border-white/10"
            title="Close Lightbox"
          >
            <X size={20} />
          </button>
          
          {/* Modal Container */}
          <div 
            className="relative max-w-full max-h-[85vh] flex items-center justify-center"
            onClick={(e) => e.stopPropagation()}
          >
            <img 
              src={selectedScreenshotUrl} 
              alt="Screenshot preview" 
              className="max-w-full max-h-[85vh] rounded-2xl shadow-2xl object-contain border border-slate-700/40"
            />
          </div>
        </div>
      )}
    </div>
  );
}
