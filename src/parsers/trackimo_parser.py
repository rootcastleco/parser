# -*- coding: utf-8 -*-
"""
Trackimo Parser - GPS data parser for Trackimo devices
Based on: https://github.com/rootcastleco/python-trackimo
"""
import logging
import asyncio
import requests
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from .base import BaseParser
from ..models import GPSDevice, GPSLocation, GPSProvider

_logger = logging.getLogger(__name__)


class TrackimoParser(BaseParser):
    """
    Trackimo GPS Parser
    
    Trackimo API'sine bağlanarak GPS verilerini çeker ve parse eder.
    
    Kullanım:
        parser = TrackimoParser(
            client_id="your_client_id",
            client_secret="your_client_secret"
        )
        await parser.connect(username="user@email.com", password="password")
        devices = await parser.get_devices()
    """
    
    API_HOST = "app.trackimo.com"
    API_VERSION = 3
    API_PORT = 443
    API_PROTOCOL = "https"
    
    def __init__(self, client_id: str, client_secret: str):
        super().__init__()
        self._client_id = client_id
        self._client_secret = client_secret
        self._session: Optional[requests.Session] = None
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._token_expires: Optional[datetime] = None
        self._account_id: Optional[int] = None
        self._username: Optional[str] = None
        self._password: Optional[str] = None
        
        self._api_url = f"{self.API_PROTOCOL}://{self.API_HOST}:{self.API_PORT}/api/v{self.API_VERSION}"
        self._internal_url = f"{self.API_PROTOCOL}://{self.API_HOST}:{self.API_PORT}/api/internal/v1"
        self._login_url = f"{self.API_PROTOCOL}://{self.API_HOST}:{self.API_PORT}/api/internal/v2/user/login"

    async def connect(self, username: str = None, password: str = None, refresh_token: str = None) -> bool:
        """
        Trackimo API'ye bağlan
        
        Args:
            username: Trackimo kullanıcı adı
            password: Trackimo şifresi
            refresh_token: Mevcut refresh token (opsiyonel)
        """
        self._username = username
        self._password = password

        if refresh_token:
            return await self._restore_session(refresh_token)
        
        if not username or not password:
            raise ValueError("Username and password required for login")
        
        return await self._login()
    
    async def _login(self) -> bool:
        """Trackimo API'ye giriş yap"""
        self._session = requests.Session()
        
        # Step 1: Login
        login_payload = {
            "username": self._username,
            "password": self._password,
            "remember_me": True,
            "whitelabel": "TRACKIMO",
        }
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self._session.post(self._login_url, json=login_payload)
        )
        
        if response.status_code != 200:
            _logger.error(f"Login failed: {response.status_code}")
            return False
        
        # Step 2: Get OAuth code
        auth_payload = {
            "client_id": self._client_id,
            "redirect_uri": "https://app.trackimo.com/api/internal/v1/oauth_redirect",
            "response_type": "code",
            "scope": "locations,notifications,devices,accounts,settings,geozones",
        }
        
        data = await self._api_request("GET", "oauth2/auth", params=auth_payload, no_auth=True)
        if not data or "code" not in data:
            _logger.error("Failed to get OAuth code")
            return False
        
        # Step 3: Exchange code for token
        token_payload = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "code": data["code"],
        }
        
        data = await self._api_request("POST", "oauth2/token", json=token_payload, no_auth=True)
        if not data or "access_token" not in data:
            _logger.error("Failed to get access token")
            return False
        
        self._access_token = data["access_token"]
        self._refresh_token = data.get("refresh_token")
        
        if "expires_in" in data:
            self._token_expires = datetime.now() + timedelta(seconds=int(data["expires_in"]) / 1000)
        
        # Get account info
        await self._get_user_info()
        
        _logger.info("Trackimo login successful")
        return True
    
    async def _restore_session(self, refresh_token: str) -> bool:
        """Mevcut session'ı restore et"""
        self._session = requests.Session()
        self._refresh_token = refresh_token
        return await self._refresh_access_token()
    
    async def _refresh_access_token(self) -> bool:
        """Access token'ı yenile"""
        if not self._refresh_token:
            return await self._login()
        
        refresh_payload = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "refresh_token": self._refresh_token,
        }
        
        try:
            data = await self._api_request("POST", "oauth2/token/refresh", json=refresh_payload, no_auth=True)
            if data and "access_token" in data:
                self._access_token = data["access_token"]
                self._refresh_token = data.get("refresh_token", self._refresh_token)
                if "expires_in" in data:
                    self._token_expires = datetime.now() + timedelta(seconds=int(data["expires_in"]) / 1000)
                await self._get_user_info()
                return True
        except Exception as e:
            _logger.error(f"Token refresh failed: {e}")
        
        return await self._login()
    
    async def _get_user_info(self) -> None:
        """Kullanıcı bilgilerini al"""
        data = await self._api_request("GET", "users/me", use_internal=True)
        if data and "accountId" in data:
            self._account_id = data["accountId"]
    
    async def _api_request(
        self,
        method: str,
        path: str,
        params: Dict = None,
        json: Dict = None,
        no_auth: bool = False,
        use_internal: bool = False
    ) -> Optional[Dict]:
        """API isteği yap"""
        if not self._session:
            self._session = requests.Session()
        
        # Token expiry check
        if not no_auth and self._token_expires and datetime.now() > self._token_expires:
            await self._refresh_access_token()
        
        base_url = self._internal_url if use_internal else self._api_url
        url = f"{base_url}/{path}"
        
        headers = {}
        if not no_auth and self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        
        loop = asyncio.get_event_loop()
        
        try:
            response = await loop.run_in_executor(
                None,
                lambda: self._session.request(method, url, params=params, json=json, headers=headers)
            )
            
            if response.status_code == 401 and not no_auth:
                await self._refresh_access_token()
                headers["Authorization"] = f"Bearer {self._access_token}"
                response = await loop.run_in_executor(
                    None,
                    lambda: self._session.request(method, url, params=params, json=json, headers=headers)
                )
            
            if 200 <= response.status_code < 300:
                return response.json() if response.text else {}
            
            _logger.error(f"API error: {response.status_code} - {response.text}")
        except Exception as e:
            _logger.exception(f"API request failed: {e}")
        
        return None
    
    async def disconnect(self) -> None:
        """Bağlantıyı kapat"""
        if self._session:
            self._session.close()
            self._session = None
        self._access_token = None
        self._refresh_token = None
    
    def _ensure_authenticated(self) -> None:
        """Kimlik doğrulamasının yapıldığından emin ol"""
        if self._account_id is None:
            raise RuntimeError("Not authenticated. Call connect() first.")
    
    async def get_devices(self) -> List[GPSDevice]:
        """Tüm cihazları getir"""
        self._ensure_authenticated()

        devices = []
        page = 1
        limit = 20

        while True:
            data = await self._api_request(
                "GET",
                f"accounts/{self._account_id}/devices",
                params={"limit": limit, "page": page}
            )

            if not data:
                break

            for device_data in data:
                device = await self._parse_device(device_data)
                if device:
                    devices.append(device)
                    self._devices[device.device_id] = device

            if len(data) < limit:
                break
            page += 1

        # Get locations for all devices
        await self._fetch_all_locations()

        return list(self._devices.values())
    
    async def _parse_device(self, data: Dict) -> Optional[GPSDevice]:
        """Cihaz verisini parse et"""
        device_id = data.get("deviceId")
        if not device_id:
            return None
        
        # Get device details
        details = await self._api_request(
            "GET",
            f"accounts/{self._account_id}/devices/{device_id}"
        )
        
        return GPSDevice(
            device_id=str(device_id),
            provider=GPSProvider.TRACKIMO,
            name=details.get("name") if details else None,
            imsi=details.get("imsi") if details else None,
            status=details.get("status") if details else None,
            device_type=details.get("type") if details else None,
            raw_data=details or data
        )
    
    async def _fetch_all_locations(self) -> None:
        """Tüm cihazların konumlarını getir"""
        device_ids = list(self._devices.keys())
        if not device_ids:
            return

        data = await self._api_request(
            "POST",
            f"accounts/{self._account_id}/locations/filter",
            json={"device_ids": [int(d) for d in device_ids]},
            params={"limit": len(device_ids), "page": 1}
        )
        
        if data:
            for loc_data in data:
                device_id = str(loc_data.get("device_id"))
                if device_id in self._devices:
                    location = self._parse_location(device_id, loc_data)
                    self._devices[device_id].last_location = location
    
    def _parse_location(self, device_id: str, data: Dict) -> GPSLocation:
        """Konum verisini parse et"""
        timestamp = None
        if "time" in data:
            timestamp = datetime.fromtimestamp(int(data["time"]))
        elif "updated" in data:
            timestamp = datetime.fromtimestamp(int(data["updated"]) / 1000.0)
        
        speed = data.get("speed")
        speed_unit = data.get("speed_unit", "kph")
        if speed and speed_unit == "mph":
            speed = speed * 1.60934  # Convert to km/h
        
        return GPSLocation(
            device_id=device_id,
            provider=GPSProvider.TRACKIMO,
            latitude=float(data["lat"]) if data.get("lat") is not None else None,
            longitude=float(data["lng"]) if data.get("lng") is not None else None,
            altitude=float(data["altitude"]) if data.get("altitude") is not None else None,
            speed=speed,
            battery=int(data["battery"]) if data.get("battery") is not None else None,
            timestamp=timestamp,
            is_moving=data.get("moving", False),
            is_gps_fix=data.get("gps", True),
            hdop=float(data["hdop"]) if data.get("hdop") is not None else None,
            raw_data=data
        )
    
    async def get_device_location(self, device_id: str) -> Optional[GPSLocation]:
        """Belirli bir cihazın konumunu getir"""
        self._ensure_authenticated()

        data = await self._api_request(
            "GET",
            f"accounts/{self._account_id}/devices/{device_id}/location"
        )
        
        if data:
            return self._parse_location(device_id, data)
        return None
    
    async def get_device_history(
        self, 
        device_id: str, 
        start_date: datetime = None, 
        end_date: datetime = None,
        limit: int = 100,
        page: int = 1
    ) -> List[GPSLocation]:
        """Cihaz konum geçmişini getir"""
        self._ensure_authenticated()

        if not start_date:
            start_date = datetime.now() - timedelta(hours=24)
        if not end_date:
            end_date = datetime.now()
        
        params = {
            "from": int(start_date.timestamp()),
            "to": int(end_date.timestamp()),
            "limit": limit,
            "page": page
        }
        
        data = await self._api_request(
            "GET",
            f"accounts/{self._account_id}/devices/{device_id}/history",
            params=params
        )
        
        locations = []
        if data:
            for loc_data in data:
                locations.append(self._parse_location(device_id, loc_data))
        
        return locations
    
    async def send_beep(self, device_id: str, period: int = 2, sound: int = 1) -> bool:
        """Cihaza bip sesi gönder"""
        self._ensure_authenticated()

        data = await self._api_request(
            "POST",
            f"accounts/{self._account_id}/devices/ops/beep",
            json={"devices": [int(device_id)], "beepPeriod": period, "beepType": sound}
        )
        return data is not None

    async def request_location(self, device_id: str) -> bool:
        """Cihazdan konum güncellemesi iste"""
        self._ensure_authenticated()

        data = await self._api_request(
            "POST",
            f"accounts/{self._account_id}/devices/ops/getLocation",
            json={"devices": [int(device_id)], "forceGpsRead": True, "sendGsmBeforeLock": True}
        )
        return data is not None
    
    @property
    def auth_info(self) -> Dict[str, Any]:
        """Kimlik doğrulama bilgilerini döndür"""
        return {
            "access_token": self._access_token,
            "refresh_token": self._refresh_token,
            "expires": self._token_expires.isoformat() if self._token_expires else None,
            "account_id": self._account_id
        }

