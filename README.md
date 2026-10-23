# OsoSense Edge Service

Edge Service of **OsoSense** (Oso Terra, 1ASI0572 Desarrollo de Soluciones IoT, UPC 202620). It runs on a local gateway (Raspberry Pi or PC) next to the plot, receives the readings of the ESP32 devices, validates and compensates them, keeps them in SQLite and synchronizes them with the OsoSense platform when there is connectivity.

## Stack
Python 3.12 · Flask · Peewee · SQLite · requests · pytest

## Bounded contexts
| Context | Responsibility |
|---|---|
| `iam` | Devices served by this gateway (activation code, platform device id, device API key, calibration factor). |
| `monitoring` | Soil Monitoring on the edge: `CaptureReadingCommandHandler`, `SynchronizeBufferedReadingsCommandHandler`, `ReadingValidationService` (TS09), `TemperatureCompensationService` (TS08), `PlatformSyncClient`, `ConnectivityMonitor`, `SyncScheduler`. |
| `health` | Health check of the gateway and of the platform link. |

## Reading lifecycle
1. The Embedded Application sends `POST /api/v1/soil-readings` with `X-API-Key`.
2. Out-of-range values (EC 0–20 dS/m, moisture 0–100 %, temperature −10 to 60 °C) → `DISCARDED` and not sent (TS09).
3. Without temperature → `UNCOMPENSATED`, stored raw and not sent (TS08).
4. Otherwise EC is compensated to 25 °C: `factor = 1 / (1 + α · (T − 25))`, `EC25 = EC · factor · calibration` (α = 0.02 /°C) and stored as `PENDING`.
5. The gateway tries to send it right away; if the platform is unreachable the reading stays `PENDING` and the scheduler retries every `SYNC_INTERVAL_SECONDS`, oldest first, in batches per device (`POST /api/v1/soil-readings/batches` with `X-Edge-Api-Key`).
6. 2xx → `SYNCHRONIZED`; 400 → `DISCARDED`; no network, 401, 404 or 5xx → still `PENDING`; after `MAX_SERVER_ERRORS` server errors → `DISCARDED (gave up)`.

## Endpoints
| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/soil-readings` | Capture a reading from a device (`201` new, `200` repeated, `401` bad key, `422` out of range). |
| GET | `/api/v1/soil-readings?status=PENDING&limit=50` | Latest buffered readings, optionally by status. |
| POST | `/api/v1/soil-readings/synchronizations` | Force a synchronization cycle and get its report. |
| GET | `/api/v1/health` | Gateway status, buffer counts and platform reachability. |

Example request from the device:
```json
{ "deviceId": "OS-014", "conductivityDsM": 2.1, "moisturePercent": 38.0, "temperatureCelsius": 27.5 }
```

## Configuration
| Variable | Default | Meaning |
|---|---|---|
| `PLATFORM_BASE_URL` | `http://localhost:8080` | OsoSense RESTful API (Railway in production). |
| `EDGE_API_KEY` | `local-edge-key` | Key sent in `X-Edge-Api-Key`; must match the platform. |
| `EDGE_DEVICES` | `OS-014:1:os-014-device-key` | `code:platformDeviceId:deviceApiKey[:calibration]`, comma-separated. |
| `EDGE_DATABASE_PATH` | `ososense-edge.db` | SQLite buffer. |
| `SYNC_INTERVAL_SECONDS` | `30` | Retry period of the scheduler. |
| `SYNC_BATCH_SIZE` | `50` | Readings per batch. |
| `MAX_SERVER_ERRORS` | `5` | Server errors before giving up on a reading. |
| `PLATFORM_TIMEZONE` | `local` | `local` or `utc` for `capturedAt`. |
| `COMPENSATION_COEFFICIENT` | `0.02` | α of the temperature compensation. |
| `EDGE_HOST` / `EDGE_PORT` | `0.0.0.0` / `5000` | Listening address. |

## Run
```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt -r requirements-dev.txt
.venv/Scripts/python app.py
```

## Tests
```bash
.venv/Scripts/python -m pytest -q
```
