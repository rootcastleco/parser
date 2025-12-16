# -*- coding: utf-8 -*-
"""
GPS Data Models - Unified data structures for all GPS providers
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum


class GPSProvider(Enum):
    """Supported GPS providers"""
    TRACKIMO = "trackimo"
    ARVENTO = "arvento"


@dataclass
class GPSLocation:
    """Unified GPS location data model"""
    device_id: str
    provider: GPSProvider
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude: Optional[float] = None
    speed: Optional[float] = None  # km/h
    course: Optional[int] = None  # degrees
    battery: Optional[int] = None  # percentage
    timestamp: Optional[datetime] = None
    address: Optional[str] = None
    odometer: Optional[float] = None
    is_moving: bool = False
    is_gps_fix: bool = True
    hdop: Optional[float] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "provider": self.provider.value,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "altitude": self.altitude,
            "speed": self.speed,
            "course": self.course,
            "battery": self.battery,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "address": self.address,
            "odometer": self.odometer,
            "is_moving": self.is_moving,
            "is_gps_fix": self.is_gps_fix,
            "hdop": self.hdop,
        }


@dataclass
class GPSDevice:
    """Unified GPS device model"""
    device_id: str
    provider: GPSProvider
    name: Optional[str] = None
    imsi: Optional[str] = None
    status: Optional[str] = None
    device_type: Optional[str] = None
    last_location: Optional[GPSLocation] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "provider": self.provider.value,
            "name": self.name,
            "imsi": self.imsi,
            "status": self.status,
            "device_type": self.device_type,
            "last_location": self.last_location.to_dict() if self.last_location else None,
        }

