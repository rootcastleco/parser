# -*- coding: utf-8 -*-
"""
GPS Parser Server - Unified GPS data server with REST API
"""
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .models import GPSProvider, GPSLocation, GPSDevice
from .parsers import TrackimoParser, ArventoParser

logging.basicConfig(level=logging.INFO)
_logger = logging.getLogger(__name__)

# Global parser instances
parsers: Dict[str, any] = {}


# Pydantic Models for API
class TrackimoCredentials(BaseModel):
    client_id: str
    client_secret: str
    username: str
    password: str
    offline: bool = False


class TrackimoRefreshCredentials(BaseModel):
    client_id: str
    client_secret: str
    refresh_token: str
    offline: bool = False


class ArventoCredentials(BaseModel):
    host: str
    username: str
    pin1: str
    pin2: str
    offline: bool = False


class AddVehicleRequest(BaseModel):
    license_plate: str
    name: Optional[str] = None


class LocationResponse(BaseModel):
    device_id: str
    provider: str
    latitude: Optional[float]
    longitude: Optional[float]
    altitude: Optional[float]
    speed: Optional[float]
    course: Optional[int]
    battery: Optional[int]
    timestamp: Optional[str]
    address: Optional[str]
    odometer: Optional[float]
    is_moving: bool
    is_gps_fix: bool


class DeviceResponse(BaseModel):
    device_id: str
    provider: str
    name: Optional[str]
    status: Optional[str]
    last_location: Optional[LocationResponse]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    _logger.info("GPS Parser Server starting...")
    yield
    # Cleanup
    for name, parser in parsers.items():
        try:
            await parser.disconnect()
        except:
            pass
    _logger.info("GPS Parser Server stopped")


app = FastAPI(
    title="GPS Parser Server",
    description="""
    Unified GPS Parser Server supporting multiple GPS providers.
    
    ## Supported Providers
    - **Trackimo**: Cloud-based GPS tracking devices
    - **Arvento**: Vehicle tracking system (SOAP API)
    
    ## Features
    - Multi-provider support
    - Real-time location tracking
    - Location history
    - Device management
    """,
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== TRACKIMO ENDPOINTS ====================

@app.post("/trackimo/connect", tags=["Trackimo"])
async def trackimo_connect(credentials: TrackimoCredentials):
    """
    Connect to Trackimo API
    
    Requires Trackimo API credentials (client_id, client_secret) and user credentials.
    """
    parser = TrackimoParser(
        client_id=credentials.client_id,
        client_secret=credentials.client_secret,
        offline=credentials.offline
    )
    
    success = await parser.connect(
        username=credentials.username,
        password=credentials.password
    )
    
    if not success:
        raise HTTPException(status_code=401, detail="Trackimo authentication failed")
    
    parsers["trackimo"] = parser
    
    return {
        "status": "connected",
        "provider": "trackimo",
        "auth": parser.auth_info
    }


@app.post("/trackimo/restore", tags=["Trackimo"])
async def trackimo_restore(credentials: TrackimoRefreshCredentials):
    """
    Restore Trackimo session using refresh token
    """
    parser = TrackimoParser(
        client_id=credentials.client_id,
        client_secret=credentials.client_secret,
        offline=credentials.offline
    )
    
    success = await parser.connect(refresh_token=credentials.refresh_token)
    
    if not success:
        raise HTTPException(status_code=401, detail="Session restore failed")
    
    parsers["trackimo"] = parser
    
    return {
        "status": "connected",
        "provider": "trackimo",
        "auth": parser.auth_info
    }


@app.get("/trackimo/devices", tags=["Trackimo"], response_model=List[DeviceResponse])
async def trackimo_get_devices():
    """Get all Trackimo devices"""
    if "trackimo" not in parsers:
        raise HTTPException(status_code=400, detail="Trackimo not connected")
    
    devices = await parsers["trackimo"].get_devices()
    return [_device_to_response(d) for d in devices]


@app.get("/trackimo/devices/{device_id}/location", tags=["Trackimo"], response_model=LocationResponse)
async def trackimo_get_location(device_id: str):
    """Get current location for a Trackimo device"""
    if "trackimo" not in parsers:
        raise HTTPException(status_code=400, detail="Trackimo not connected")
    
    location = await parsers["trackimo"].get_device_location(device_id)
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    
    return _location_to_response(location)


@app.get("/trackimo/devices/{device_id}/history", tags=["Trackimo"], response_model=List[LocationResponse])
async def trackimo_get_history(
    device_id: str,
    hours: int = Query(24, description="Hours of history to retrieve")
):
    """Get location history for a Trackimo device"""
    if "trackimo" not in parsers:
        raise HTTPException(status_code=400, detail="Trackimo not connected")
    
    end_date = datetime.now()
    start_date = end_date - timedelta(hours=hours)
    
    locations = await parsers["trackimo"].get_device_history(
        device_id, start_date, end_date
    )
    
    return [_location_to_response(loc) for loc in locations]


@app.post("/trackimo/devices/{device_id}/beep", tags=["Trackimo"])
async def trackimo_beep_device(device_id: str):
    """Send beep command to a Trackimo device"""
    if "trackimo" not in parsers:
        raise HTTPException(status_code=400, detail="Trackimo not connected")
    
    success = await parsers["trackimo"].send_beep(device_id)
    return {"status": "success" if success else "failed"}


@app.post("/trackimo/devices/{device_id}/locate", tags=["Trackimo"])
async def trackimo_request_location(device_id: str):
    """Request location update from a Trackimo device"""
    if "trackimo" not in parsers:
        raise HTTPException(status_code=400, detail="Trackimo not connected")
    
    success = await parsers["trackimo"].request_location(device_id)
    return {"status": "success" if success else "failed"}


# ==================== ARVENTO ENDPOINTS ====================

@app.post("/arvento/connect", tags=["Arvento"])
async def arvento_connect(credentials: ArventoCredentials):
    """
    Connect to Arvento SOAP API
    
    Requires Arvento credentials (host, username, pin1, pin2).
    """
    parser = ArventoParser(
        host=credentials.host,
        username=credentials.username,
        pin1=credentials.pin1,
        pin2=credentials.pin2,
        offline=credentials.offline
    )
    
    success = await parser.connect()
    
    if not success:
        raise HTTPException(status_code=401, detail="Arvento connection failed")
    
    parsers["arvento"] = parser
    
    return {
        "status": "connected",
        "provider": "arvento"
    }


@app.post("/arvento/vehicles", tags=["Arvento"], response_model=DeviceResponse)
async def arvento_add_vehicle(request: AddVehicleRequest):
    """Add a vehicle to track by license plate"""
    if "arvento" not in parsers:
        raise HTTPException(status_code=400, detail="Arvento not connected")
    
    device = await parsers["arvento"].add_vehicle(
        license_plate=request.license_plate,
        name=request.name
    )
    
    if not device:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    
    return _device_to_response(device)


@app.get("/arvento/vehicles", tags=["Arvento"], response_model=List[DeviceResponse])
async def arvento_get_vehicles():
    """Get all tracked Arvento vehicles"""
    if "arvento" not in parsers:
        raise HTTPException(status_code=400, detail="Arvento not connected")
    
    devices = await parsers["arvento"].get_devices()
    return [_device_to_response(d) for d in devices]


@app.get("/arvento/vehicles/{node}/location", tags=["Arvento"], response_model=LocationResponse)
async def arvento_get_location(node: str):
    """Get current location for an Arvento vehicle by node ID"""
    if "arvento" not in parsers:
        raise HTTPException(status_code=400, detail="Arvento not connected")
    
    location = await parsers["arvento"].get_vehicle_status(node)
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    
    return _location_to_response(location)


@app.get("/arvento/vehicles/plate/{license_plate}/location", tags=["Arvento"], response_model=LocationResponse)
async def arvento_get_location_by_plate(license_plate: str):
    """Get current location for an Arvento vehicle by license plate"""
    if "arvento" not in parsers:
        raise HTTPException(status_code=400, detail="Arvento not connected")
    
    location = await parsers["arvento"].get_vehicle_by_plate(license_plate)
    if not location:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    
    return _location_to_response(location)


# ==================== UNIFIED ENDPOINTS ====================

@app.get("/devices", tags=["Unified"])
async def get_all_devices():
    """Get all devices from all connected providers"""
    all_devices = []
    
    for provider_name, parser in parsers.items():
        try:
            devices = await parser.get_devices()
            all_devices.extend([_device_to_response(d) for d in devices])
        except Exception as e:
            _logger.error(f"Error getting devices from {provider_name}: {e}")
    
    return all_devices


@app.get("/status", tags=["System"])
async def get_status():
    """Get server and connection status"""
    return {
        "status": "running",
        "connected_providers": list(parsers.keys()),
        "timestamp": datetime.now().isoformat()
    }


@app.post("/disconnect/{provider}", tags=["System"])
async def disconnect_provider(provider: str):
    """Disconnect a specific provider"""
    if provider not in parsers:
        raise HTTPException(status_code=404, detail=f"Provider {provider} not connected")
    
    await parsers[provider].disconnect()
    del parsers[provider]
    
    return {"status": "disconnected", "provider": provider}


# ==================== HELPER FUNCTIONS ====================

def _location_to_response(location: GPSLocation) -> LocationResponse:
    """Convert GPSLocation to API response"""
    return LocationResponse(
        device_id=location.device_id,
        provider=location.provider.value,
        latitude=location.latitude,
        longitude=location.longitude,
        altitude=location.altitude,
        speed=location.speed,
        course=location.course,
        battery=location.battery,
        timestamp=location.timestamp.isoformat() if location.timestamp else None,
        address=location.address,
        odometer=location.odometer,
        is_moving=location.is_moving,
        is_gps_fix=location.is_gps_fix
    )


def _device_to_response(device: GPSDevice) -> DeviceResponse:
    """Convert GPSDevice to API response"""
    return DeviceResponse(
        device_id=device.device_id,
        provider=device.provider.value,
        name=device.name,
        status=device.status,
        last_location=_location_to_response(device.last_location) if device.last_location else None
    )


def run_server(host: str = "0.0.0.0", port: int = 8000):
    """Run the GPS Parser Server"""
    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()

