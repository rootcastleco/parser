# GPS Parser Server

Birden fazla GPS sağlayıcısını destekleyen birleşik GPS veri sunucusu.

## 📡 Desteklenen Sağlayıcılar

### 1. Trackimo
- **Kaynak**: [python-trackimo](https://github.com/rootcastleco/python-trackimo)
- **API Türü**: REST API (OAuth2)
- **Özellikler**:
  - Cihaz listesi
  - Gerçek zamanlı konum
  - Konum geçmişi
  - Cihaza bip gönderme
  - Konum güncelleme isteği

### 2. Arvento
- **Kaynak**: [arvento-api-library](https://github.com/secgin/arvento-api-library)
- **API Türü**: SOAP API
- **Özellikler**:
  - Plaka ile araç sorgulama
  - Gerçek zamanlı konum
  - Adres bilgisi
  - Kilometre sayacı

## 🚀 Kurulum

```bash
# Bağımlılıkları yükle
pip install -r requirements.txt

# Sunucuyu başlat
python -m src.server
```

## 📖 API Kullanımı

Sunucu başladıktan sonra API dokümantasyonu: `http://localhost:8000/docs`

### Trackimo Bağlantısı

```bash
# Giriş yap
curl -X POST http://localhost:8000/trackimo/connect \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "YOUR_CLIENT_ID",
    "client_secret": "YOUR_CLIENT_SECRET",
    "username": "your@email.com",
    "password": "your_password"
  }'

# Cihazları listele
curl http://localhost:8000/trackimo/devices

# Konum al
curl http://localhost:8000/trackimo/devices/{device_id}/location

# Geçmiş al (son 24 saat)
curl http://localhost:8000/trackimo/devices/{device_id}/history?hours=24
```

### Arvento Bağlantısı

```bash
# Bağlan
curl -X POST http://localhost:8000/arvento/connect \
  -H "Content-Type: application/json" \
  -d '{
    "host": "https://ws.arvento.com/v1/report.asmx?wsdl",
    "username": "YOUR_USERNAME",
    "pin1": "YOUR_PIN1",
    "pin2": "YOUR_PIN2"
  }'

# Araç ekle (plaka ile)
curl -X POST http://localhost:8000/arvento/vehicles \
  -H "Content-Type: application/json" \
  -d '{
    "license_plate": "34ABC123",
    "name": "Şirket Aracı"
  }'

# Plaka ile konum al
curl http://localhost:8000/arvento/vehicles/plate/34ABC123/location
```

## 🏗️ Proje Yapısı

```
parser/
├── src/
│   ├── __init__.py
│   ├── models.py           # Veri modelleri (GPSLocation, GPSDevice)
│   ├── server.py           # FastAPI sunucusu
│   └── parsers/
│       ├── __init__.py
│       ├── base.py         # Temel parser sınıfı
│       ├── trackimo_parser.py  # Trackimo implementasyonu
│       └── arvento_parser.py   # Arvento implementasyonu
├── trackimo-parser/        # Orijinal Trackimo kütüphanesi
├── arvento-parser/         # Orijinal Arvento kütüphanesi
├── requirements.txt
└── README.md
```

## 📊 Veri Modelleri

### GPSLocation
```python
{
    "device_id": "12345",
    "provider": "trackimo",
    "latitude": 41.0082,
    "longitude": 28.9784,
    "altitude": 50.0,
    "speed": 45.5,          # km/h
    "course": 180,          # derece
    "battery": 85,          # yüzde
    "timestamp": "2024-01-15T10:30:00",
    "address": "İstanbul, Türkiye",
    "odometer": 12500.5,    # km
    "is_moving": true,
    "is_gps_fix": true
}
```

### GPSDevice
```python
{
    "device_id": "12345",
    "provider": "trackimo",
    "name": "Araç 1",
    "status": "active",
    "last_location": { ... }  # GPSLocation
}
```

## 🔧 Programatik Kullanım

```python
import asyncio
from src.parsers import TrackimoParser, ArventoParser

async def main():
    # Trackimo kullanımı
    trackimo = TrackimoParser(
        client_id="your_client_id",
        client_secret="your_client_secret"
    )
    await trackimo.connect(username="user@email.com", password="pass")
    
    devices = await trackimo.get_devices()
    for device in devices:
        print(f"{device.name}: {device.last_location}")
    
    # Arvento kullanımı
    arvento = ArventoParser(
        host="https://ws.arvento.com/v1/report.asmx?wsdl",
        username="user",
        pin1="pin1",
        pin2="pin2"
    )
    await arvento.connect()
    
    location = await arvento.get_vehicle_by_plate("34ABC123")
    print(f"Konum: {location.latitude}, {location.longitude}")

asyncio.run(main())
```

## 📝 API Referansı

| Endpoint | Method | Açıklama |
|----------|--------|----------|
| `/status` | GET | Sunucu durumu |
| `/devices` | GET | Tüm cihazlar (tüm sağlayıcılar) |
| `/trackimo/connect` | POST | Trackimo'ya bağlan |
| `/trackimo/devices` | GET | Trackimo cihazları |
| `/trackimo/devices/{id}/location` | GET | Cihaz konumu |
| `/trackimo/devices/{id}/history` | GET | Konum geçmişi |
| `/arvento/connect` | POST | Arvento'ya bağlan |
| `/arvento/vehicles` | POST | Araç ekle |
| `/arvento/vehicles/plate/{plate}/location` | GET | Plaka ile konum |

## 🔐 Güvenlik Notları

- API anahtarlarını environment variable olarak saklayın
- Production'da HTTPS kullanın
- CORS ayarlarını kısıtlayın

## 📄 Lisans

MIT License

## 🙏 Teşekkürler

- [python-trackimo](https://github.com/rootcastleco/python-trackimo)
- [arvento-api-library](https://github.com/secgin/arvento-api-library)
