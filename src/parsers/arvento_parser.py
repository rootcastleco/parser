# -*- coding: utf-8 -*-
"""
Arvento Parser - GPS data parser for Arvento devices
Based on: https://github.com/secgin/arvento-api-library

Arvento, SOAP tabanlı bir API kullanır ve araç takip sistemleri için tasarlanmıştır.
"""
import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from xml.etree import ElementTree

try:
    from zeep import Client
    from zeep.transports import Transport
    ZEEP_AVAILABLE = True
except ImportError:
    ZEEP_AVAILABLE = False

import requests

from .base import BaseParser
from ..models import GPSDevice, GPSLocation, GPSProvider

_logger = logging.getLogger(__name__)


class ArventoParser(BaseParser):
    """
    Arvento GPS Parser
    
    Arvento SOAP API'sine bağlanarak GPS verilerini çeker ve parse eder.
    
    Kullanım:
        parser = ArventoParser(
            host="https://ws.arvento.com/v1/report.asmx?wsdl",
            username="your_username",
            pin1="your_pin1",
            pin2="your_pin2"
        )
        await parser.connect()
        location = await parser.get_vehicle_status("34ABC123")
    
    API Yanıt Örneği:
        strNode: K1200098807
        dtGMTDateTime: 2023-06-01T03:42:23
        dLatitude: 40.97681
        dLongitude: 34.810963
        dSpeed: 0
        strAddress: Ömer Derindere Blv., Cumhuriyet Mh., Osmancık, Çorum, Türkiye
        nCourse: 0
        dOdometer: 24507
        nAltitude: 0
    """
    
    def __init__(self, host: str, username: str, pin1: str, pin2: str, offline: bool = False):
        super().__init__()
        self._host = host
        self._username = username
        self._pin1 = pin1
        self._pin2 = pin2
        self._client = None
        self._connected = False
        self._offline = offline
        self._mock_nodes: Dict[str, str] = {}
        self._mock_locations: Dict[str, GPSLocation] = {}
    
    async def connect(self) -> bool:
        """
        Arvento SOAP API'ye bağlan
        
        Returns:
            bool: Bağlantı başarılı ise True
        """
        try:
            if self._offline:
                self._connected = True
                self._load_mock_data()
                _logger.info("Arvento offline mode enabled; using mock data")
                return True

            if ZEEP_AVAILABLE:
                loop = asyncio.get_event_loop()
                self._client = await loop.run_in_executor(
                    None,
                    lambda: Client(self._host)
                )
            else:
                # Zeep yoksa basit SOAP client kullan
                _logger.warning("Zeep not available, using basic SOAP client")
            
            self._connected = True
            _logger.info("Arvento connection established")
            return True
        except Exception as e:
            _logger.error(f"Arvento connection failed: {e}")
            return False
    
    async def disconnect(self) -> None:
        """Bağlantıyı kapat"""
        self._client = None
        self._connected = False
    
    def _get_auth_params(self) -> Dict[str, str]:
        """Kimlik doğrulama parametrelerini döndür"""
        return {
            "Username": self._username,
            "PIN1": self._pin1,
            "PIN2": self._pin2
        }
    
    async def _soap_request(self, method: str, params: Dict) -> Optional[Any]:
        """SOAP isteği yap"""
        full_params = {**self._get_auth_params(), **params}

        try:
            if self._offline:
                _logger.debug("Offline mode: skipping SOAP request %s", method)
                return None
            if ZEEP_AVAILABLE and self._client:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: getattr(self._client.service, method)(**full_params)
                )
                return result
            else:
                # Basit SOAP isteği
                return await self._basic_soap_request(method, full_params)
        except Exception as e:
            _logger.error(f"SOAP request failed: {e}")
            return None
    
    async def _basic_soap_request(self, method: str, params: Dict) -> Optional[Dict]:
        """Zeep olmadan basit SOAP isteği"""
        from xml.sax.saxutils import escape
        
        # SOAP envelope oluştur - XML injection'a karşı escape uygula
        param_xml = "\n".join([f"<{k}>{escape(str(v))}</{k}>" for k, v in params.items()])
        
        soap_body = f"""<?xml version="1.0" encoding="utf-8"?>
<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope" 
                 xmlns:ns="http://www.intelli-track.com/">
    <soap12:Body>
        <ns:{method}>
            {param_xml}
        </ns:{method}>
    </soap12:Body>
</soap12:Envelope>"""
        
        headers = {
            "Content-Type": "application/soap+xml; charset=utf-8",
        }
        
        # WSDL URL'den endpoint URL'i çıkar
        endpoint = self._host.replace("?wsdl", "").replace("?WSDL", "")
        
        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(
                None,
                lambda: requests.post(endpoint, data=soap_body, headers=headers)
            )
            
            if response.status_code == 200:
                return self._parse_soap_response(response.text, method)
        except Exception as e:
            _logger.error(f"Basic SOAP request failed: {e}")
        
        return None
    
    def _parse_soap_response(self, xml_text: str, method: str) -> Optional[Dict]:
        """SOAP yanıtını parse et"""
        try:
            # Namespace'leri kaldır (basitleştirme için)
            import re
            xml_text = re.sub(r'xmlns[^"]*"[^"]*"', '', xml_text)
            xml_text = re.sub(r'<[a-z0-9]+:', '<', xml_text, flags=re.IGNORECASE)
            xml_text = re.sub(r'</[a-z0-9]+:', '</', xml_text, flags=re.IGNORECASE)
            
            root = ElementTree.fromstring(xml_text)
            
            # Result elementini bul
            result_tag = f"{method}Result"
            for elem in root.iter():
                if result_tag in elem.tag:
                    return self._element_to_dict(elem)
            
            # LastPacket'i ara
            for elem in root.iter():
                if "LastPacket" in elem.tag:
                    return self._element_to_dict(elem)
                    
        except Exception as e:
            _logger.error(f"SOAP response parsing failed: {e}")
        
        return None
    
    def _element_to_dict(self, element) -> Dict:
        """XML elementini dict'e çevir"""
        result = {}
        for child in element:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if len(child) > 0:
                result[tag] = self._element_to_dict(child)
            else:
                result[tag] = child.text
        return result
    
    async def get_node_from_license_plate(self, license_plate: str) -> Optional[str]:
        """
        Plakadan node ID'si al
        
        Args:
            license_plate: Araç plakası (örn: "34ABC123")
            
        Returns:
            Node ID veya None
        """
        result = await self._soap_request("GetNodeFromLicensePlate", {
            "LicensePlate": license_plate
        })

        if self._offline:
            return self._mock_nodes.get(license_plate)

        if result:
            if hasattr(result, "GetNodeFromLicensePlateResult"):
                return result.GetNodeFromLicensePlateResult
            elif isinstance(result, dict):
                return result.get("GetNodeFromLicensePlateResult")
        
        return None
    
    async def get_vehicle_status(self, node: str) -> Optional[GPSLocation]:
        """
        Araç durumunu al
        
        Args:
            node: Node ID (GetNodeFromLicensePlate'den alınır)
            
        Returns:
            GPSLocation veya None
        """
        result = await self._soap_request("GetVehicleStatusByNodeV3", {
            "Node": node,
            "Language": "0"
        })

        if self._offline:
            return self._mock_locations.get(node)

        if result:
            return self._parse_vehicle_status(node, result)

        return None
    
    def _parse_vehicle_status(self, node: str, data: Any) -> GPSLocation:
        """Araç durumu verisini parse et"""
        
        def _safe_get(obj: Any, key: str, default=None):
            """Dict veya object'ten güvenli değer al"""
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)
        
        # Zeep object veya dict olabilir - packet'i çıkar
        packet = data
        if hasattr(data, "GetVehicleStatusByNodeV3Result"):
            packet = data.GetVehicleStatusByNodeV3Result.LastPacket
        elif isinstance(data, dict) and "LastPacket" in data:
            packet = data["LastPacket"]
        
        # raw dict'i oluştur (her zaman dict olacak)
        raw = {
            "strNode": _safe_get(packet, "strNode"),
            "dtGMTDateTime": str(_safe_get(packet, "dtGMTDateTime", "")),
            "dLatitude": _safe_get(packet, "dLatitude"),
            "dLongitude": _safe_get(packet, "dLongitude"),
            "dSpeed": _safe_get(packet, "dSpeed"),
            "strAddress": _safe_get(packet, "strAddress"),
            "nCourse": _safe_get(packet, "nCourse"),
            "dOdometer": _safe_get(packet, "dOdometer"),
            "nAltitude": _safe_get(packet, "nAltitude"),
        }
        
        # Timestamp parse
        timestamp = None
        dt_str = raw.get("dtGMTDateTime")
        if dt_str:
            try:
                timestamp = datetime.fromisoformat(str(dt_str).replace("Z", "+00:00"))
            except:
                pass
        
        # Latitude/Longitude
        lat = raw.get("dLatitude")
        lng = raw.get("dLongitude")
        
        return GPSLocation(
            device_id=node,
            provider=GPSProvider.ARVENTO,
            latitude=float(lat) if lat else None,
            longitude=float(lng) if lng else None,
            altitude=float(raw.get("nAltitude") or 0),
            speed=float(raw.get("dSpeed") or 0),
            course=int(raw.get("nCourse") or 0),
            timestamp=timestamp,
            address=raw.get("strAddress"),
            odometer=float(raw.get("dOdometer") or 0),
            is_moving=(float(raw.get("dSpeed") or 0) > 0),
            raw_data=raw
        )
    
    async def get_vehicle_by_plate(self, license_plate: str) -> Optional[GPSLocation]:
        """
        Plaka ile araç konumunu al (convenience method)
        
        Args:
            license_plate: Araç plakası
            
        Returns:
            GPSLocation veya None
        """
        node = await self.get_node_from_license_plate(license_plate)
        if node:
            return await self.get_vehicle_status(node)
        return None
    
    async def get_devices(self) -> List[GPSDevice]:
        """
        Tüm cihazları getir
        
        Not: Arvento API'si cihaz listesi endpoint'i sağlamıyor.
        Bu method manuel olarak eklenen plakaları takip eder.
        """
        return list(self._devices.values())
    
    async def add_vehicle(self, license_plate: str, name: str = None) -> Optional[GPSDevice]:
        """
        Takip edilecek araç ekle
        
        Args:
            license_plate: Araç plakası
            name: Araç adı (opsiyonel)
            
        Returns:
            GPSDevice veya None
        """
        node = await self.get_node_from_license_plate(license_plate)
        if not node:
            _logger.error(f"Vehicle not found: {license_plate}")
            return None

        location = await self.get_vehicle_status(node)
        
        device = GPSDevice(
            device_id=node,
            provider=GPSProvider.ARVENTO,
            name=name or license_plate,
            status="active",
            last_location=location,
            raw_data={"license_plate": license_plate, "node": node}
        )
        
        self._devices[node] = device
        return device
    
    async def get_device_location(self, device_id: str) -> Optional[GPSLocation]:
        """Belirli bir cihazın konumunu getir"""
        return await self.get_vehicle_status(device_id)
    
    async def get_device_history(
        self, 
        device_id: str, 
        start_date: datetime = None, 
        end_date: datetime = None
    ) -> List[GPSLocation]:
        """
        Cihaz konum geçmişini getir
        
        Not: Bu özellik Arvento API'sinde mevcut olabilir ancak
        mevcut kütüphanede implementasyonu yok.
        """
        _logger.warning("Arvento history endpoint not implemented in source library")
        return []

    def _load_mock_data(self) -> None:
        """Offline mod için örnek araç verileri yükle"""
        now = datetime.now()
        sample_locations = {
            "NODE001": GPSLocation(
                device_id="NODE001",
                provider=GPSProvider.ARVENTO,
                latitude=40.978,
                longitude=29.092,
                speed=12.3,
                course=45,
                odometer=25010,
                address="İstanbul, Türkiye",
                timestamp=now - timedelta(minutes=3),
                is_moving=True,
                raw_data={"source": "mock"}
            ),
            "NODE002": GPSLocation(
                device_id="NODE002",
                provider=GPSProvider.ARVENTO,
                latitude=38.4237,
                longitude=27.1428,
                speed=0.0,
                course=0,
                odometer=10200,
                address="İzmir, Türkiye",
                timestamp=now - timedelta(minutes=7),
                is_moving=False,
                raw_data={"source": "mock"}
            ),
        }

        self._mock_nodes = {
            "34ABC123": "NODE001",
            "35XYZ789": "NODE002",
        }

        self._mock_locations = sample_locations

        for node, location in sample_locations.items():
            self._devices[node] = GPSDevice(
                device_id=node,
                provider=GPSProvider.ARVENTO,
                name=f"Mock Vehicle {node}",
                status="active",
                last_location=location,
                raw_data={"source": "mock"}
            )

