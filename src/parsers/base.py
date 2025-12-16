# -*- coding: utf-8 -*-
"""
Base Parser - Abstract base class for GPS parsers
"""
import asyncio
import inspect
from abc import ABC, abstractmethod
from typing import List, Optional, Callable, Any
from ..models import GPSDevice, GPSLocation


class BaseParser(ABC):
    """Abstract base class for all GPS parsers"""
    
    def __init__(self):
        self._devices: dict = {}
        self._on_location_update: Optional[Callable] = None
    
    @abstractmethod
    async def connect(self) -> bool:
        """Connect to the GPS provider"""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the GPS provider"""
        pass
    
    @abstractmethod
    async def get_devices(self) -> List[GPSDevice]:
        """Get all devices from the provider"""
        pass
    
    @abstractmethod
    async def get_device_location(self, device_id: str) -> Optional[GPSLocation]:
        """Get current location for a specific device"""
        pass
    
    @abstractmethod
    async def get_device_history(
        self, 
        device_id: str, 
        start_date: Any, 
        end_date: Any
    ) -> List[GPSLocation]:
        """Get location history for a device"""
        pass
    
    def on_location_update(self, callback: Callable) -> None:
        """Register callback for location updates"""
        self._on_location_update = callback
    
    async def _emit_location_update(self, location: GPSLocation) -> None:
        """Emit location update to registered callback"""
        if self._on_location_update:
            result = self._on_location_update(location)
            # Async callback ise await et, sync ise direkt çalıştır
            if asyncio.iscoroutine(result):
                await result

