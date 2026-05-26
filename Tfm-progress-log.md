# TFM Progress Log
**Project:** IoT Simulation Platform for Greenhouse Analysis and Decision-Making
**Master:** Software Engineering
**Last updated:** May 19, 2026

---

## Project Overview

The goal of this TFM is to build an IoT simulation platform for a smart greenhouse. The system simulates virtual sensors and actuators, exposes them as real IoT devices via REST and MQTT, allows defining and comparing management scenarios, and calculates KPIs to support decision-making.

**Core components of the final system:**
- Simulation engine (physical models of temperature, humidity, soil moisture, light, crop growth)
- Virtual IoT devices exposed via MQTT and REST API
- Scenario manager (irrigation strategies, ventilation strategies)
- KPI calculator (water consumption, energy, crop productivity)
- Real-time dashboard (Grafana)

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Language | Python 3.14 | Core simulation and sensor logic |
| MQTT Broker | Eclipse Mosquitto 2 | Real-time IoT message distribution |
| Time-series DB | InfluxDB 2.7 | Persistent storage of sensor data |
| Dashboard | Grafana | Real-time data visualization |
| Containerization | Docker + Docker Compose | Reproducible infrastructure |
| REST API | FastAPI (pending) | HTTP interface for virtual devices |
| MQTT Client | Paho-MQTT 1.6.1 | Python MQTT publishing |
| InfluxDB Client | influxdb-client 1.36.1 | Python InfluxDB writing |

---

## Phase 1 — Infrastructure Setup

### What was done

The base infrastructure was set up using **Docker** and **Docker Compose**, launching three services that form the backbone of the platform. Docker allows all services to run in isolated containers with a single command, making the environment fully reproducible on any machine — essential for a TFM that needs to be evaluated by others.

| Service | Image | Port | Purpose |
|---|---|---|---|
| Mosquitto | eclipse-mosquitto:2 | 1883 | MQTT broker — receives and distributes sensor messages |
| InfluxDB | influxdb:2.7 | 8086 | Time-series database — persists all sensor data |
| Grafana | grafana/grafana:latest | 3000 | Dashboard — visualizes data in real time |

### Project folder structure

```
tfm-greenhouse/
├── docker-compose.yml          ← defines all Docker services
├── mosquitto/
│   ├── config/
│   │   └── mosquitto.conf      ← MQTT broker configuration
│   ├── data/                   ← persistent broker data
│   └── log/                    ← broker logs
└── simulator/
    ├── requirements.txt        ← Python dependencies
    └── temperature_sensor.py   ← first virtual sensor
```

### Key configuration files

**`mosquitto/config/mosquitto.conf`**
```conf
listener 1883
allow_anonymous true
persistence true
persistence_location /mosquitto/data/
log_dest file /mosquitto/log/mosquitto.log
```
Configures the broker to listen on port 1883 and allow anonymous connections (no password required for development).

**`docker-compose.yml`**
```yaml
services:

  mosquitto:
    image: eclipse-mosquitto:2
    container_name: tfm-mosquitto
    ports:
      - "1883:1883"
    volumes:
      - ./mosquitto/config:/mosquitto/config
      - ./mosquitto/data:/mosquitto/data
      - ./mosquitto/log:/mosquitto/log
    restart: unless-stopped

  influxdb:
    image: influxdb:2.7
    container_name: tfm-influxdb
    ports:
      - "8086:8086"
    environment:
      - DOCKER_INFLUXDB_INIT_MODE=setup
      - DOCKER_INFLUXDB_INIT_USERNAME=admin
      - DOCKER_INFLUXDB_INIT_PASSWORD=adminadmin
      - DOCKER_INFLUXDB_INIT_ORG=tfm
      - DOCKER_INFLUXDB_INIT_BUCKET=greenhouse
      - DOCKER_INFLUXDB_INIT_RETENTION=30d
      - DOCKER_INFLUXDB_INIT_ADMIN_TOKEN=my-super-secret-token
    volumes:
      - influxdb_data:/var/lib/influxdb2
    restart: unless-stopped

  grafana:
    image: grafana/grafana:latest
    container_name: tfm-grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_USER=admin
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - grafana_data:/var/lib/grafana
    depends_on:
      - influxdb
    restart: unless-stopped

volumes:
  influxdb_data:
  grafana_data:
```

The `DOCKER_INFLUXDB_INIT_*` variables only take effect on the very first run, when the volume is created. If the volume already exists from a previous run, they are ignored. This is why resetting with `docker compose down -v` is necessary when changing initialization parameters.

### Commands reference

```bash
# Start all services in the background
docker compose up -d

# Check all services are running
docker compose ps

# Tear down and delete all data volumes (full reset)
docker compose down -v

# View logs from a specific service
docker compose logs influxdb
```

---

## Phase 2 — First Virtual Sensor (Temperature)

### What was done

The first virtual sensor was implemented in Python: a temperature sensor that simulates a realistic day/night cycle inside a greenhouse and publishes data both via MQTT and directly to InfluxDB every 5 seconds.

### Why two protocols simultaneously

| | MQTT | InfluxDB |
|---|---|---|
| Communication model | Push (sensor broadcasts) | Direct write |
| Data lifetime | Only while subscribers are listening | Persisted permanently |
| Best for | Real-time streaming to multiple consumers | Historical queries and KPI calculation |
| Consumed by | Grafana live panels, future external systems | Grafana historical charts, scenario analysis |

Without MQTT, the system would not behave as a real IoT platform — it would just be a script writing to a database. Without InfluxDB, data would be lost every time the script stops.

### Python dependencies

**`simulator/requirements.txt`**
```
paho-mqtt==1.6.1
influxdb-client==1.36.1
```

### Temperature simulation model

The temperature follows a **sinusoidal curve** that models the natural day/night cycle of a greenhouse:

```
T(t) = base_temp + amplitude × sin(2π × t / 86400 − π/2) + noise
```

| Parameter | Value | Meaning |
|---|---|---|
| `base_temp` | 23.5 °C | Average daily temperature |
| `amplitude` | 8.5 °C | Variation above/below average |
| `noise` | ±0.3 °C | Random variation simulating real sensor noise |
| Period | 86,400 s | One full day cycle |

This produces a curve that starts at ~15 °C at midnight, rises to ~32 °C at noon, and falls back.

### Full source code

**`simulator/temperature_sensor.py`**
```python
import time
import math
import json
import random
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# ── Configuration ──────────────────────────────────────────
MQTT_BROKER   = "localhost"
MQTT_PORT     = 1883
MQTT_TOPIC    = "greenhouse/sensor/temperature"

INFLUX_URL    = "http://localhost:8086"
INFLUX_TOKEN  = "<your-token-here>"
INFLUX_ORG    = "tfm"
INFLUX_BUCKET = "greenhouse"

PUBLISH_INTERVAL_SEC = 5
# ───────────────────────────────────────────────────────────


def simulate_temperature(elapsed_seconds: float) -> float:
    """
    Simulates a day/night temperature cycle inside a greenhouse.
    Returns temperature in Celsius.
    """
    seconds_per_day = 86_400
    cycle_position  = elapsed_seconds % seconds_per_day
    angle           = (2 * math.pi * cycle_position / seconds_per_day) - (math.pi / 2)

    base_temp = 23.5
    amplitude = 8.5
    noise     = random.uniform(-0.3, 0.3)

    return round(base_temp + amplitude * math.sin(angle) + noise, 2)


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("  [MQTT] Connected to broker")
    else:
        print(f"  [MQTT] Connection failed — code {rc}")


mqtt_client = mqtt.Client(client_id="sensor-temperature-01")
mqtt_client.on_connect = on_connect
mqtt_client.connect(MQTT_BROKER, MQTT_PORT)
mqtt_client.loop_start()

influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api = influx_client.write_api(write_options=SYNCHRONOUS)

print("=" * 50)
print("  Greenhouse temperature sensor started")
print(f"  MQTT topic : {MQTT_TOPIC}")
print(f"  Interval   : every {PUBLISH_INTERVAL_SEC}s")
print("  Press Ctrl+C to stop")
print("=" * 50)

simulated_elapsed = 0

try:
    while True:
        temperature = simulate_temperature(simulated_elapsed)
        timestamp   = datetime.now(timezone.utc).isoformat()

        payload = json.dumps({
            "sensor_id" : "temp-01",
            "location"  : "central_zone",
            "value"     : temperature,
            "unit"      : "C",
            "timestamp" : timestamp
        })
        mqtt_client.publish(MQTT_TOPIC, payload)

        point = (
            Point("temperature")
            .tag("sensor_id", "temp-01")
            .tag("location",  "central_zone")
            .field("value", temperature)
        )
        write_api.write(bucket=INFLUX_BUCKET, record=point)

        print(f"[{timestamp}]  temperature: {temperature:.1f} C  →  MQTT OK  |  InfluxDB OK")

        simulated_elapsed += PUBLISH_INTERVAL_SEC
        time.sleep(PUBLISH_INTERVAL_SEC)

except KeyboardInterrupt:
    print("\n  Sensor stopped.")
    mqtt_client.loop_stop()
    influx_client.close()
```

### Data flow

```
simulate_temperature()
        │
        ├──► MQTT publish ──► topic: greenhouse/sensor/temperature
        │         payload: { sensor_id, location, value, unit, timestamp }
        │
        └──► InfluxDB write ──► measurement: temperature
                    tags:   sensor_id=temp-01, location=central_zone
                    field:  value=<float>
                    timestamp: auto UTC
```

### Issues encountered and resolved

| Issue | Cause | Solution |
|---|---|---|
| `401 Unauthorized` from InfluxDB | Bucket name mismatch (`invernadero` vs `greenhouse`) | Updated `DOCKER_INFLUXDB_INIT_BUCKET=greenhouse`, reset with `docker compose down -v` |
| `401 Unauthorized` after reset | Old token invalidated after volume deletion | Generated new All Access Token from InfluxDB UI |
| `DeprecationWarning` on `utcnow()` | Python 3.14 deprecates `datetime.utcnow()` | Replaced with `datetime.now(timezone.utc)` |
| Script not found | Running from project root instead of `simulator/` | `cd simulator` first, or `python simulator/temperature_sensor.py` |

---

<!--  ============================================================  -->
<!--  🆕 ADDED: May 2026 — Grafana dashboard                        -->
<!--  ============================================================  -->

## Phase 3 — Grafana Real-Time Dashboard 🆕

### What was done

Grafana was connected to InfluxDB as a data source and the first real-time visualization panel was created, displaying the simulated greenhouse temperature as a live time-series chart. This completes the first full end-to-end data pipeline of the platform.

### Why Grafana

Grafana is the industry standard for visualizing time-series data. It connects natively to InfluxDB, requires no custom frontend code, and produces professional dashboards. For this TFM it serves two purposes: validating that the full data pipeline works correctly (sensor → MQTT → InfluxDB → visualization), and providing the final presentation layer for KPI analysis and scenario comparison results.

### Connecting InfluxDB as a data source

Access Grafana at `http://localhost:3000` (credentials: `admin / admin`).

**Connections → Data sources → Add data source → InfluxDB**

| Field | Value | Notes |
|---|---|---|
| Query Language | **Flux** | Must be changed first — it transforms the entire form |
| URL | `http://influxdb:8086` | Service name, not localhost (see note below) |
| Token | `<influxdb-api-token>` | From InfluxDB UI → Load Data → API Tokens → All Access |
| Organization | `tfm` | Must match docker-compose.yml exactly |
| Default Bucket | `greenhouse` | The bucket where sensor data is stored |

> **Why `http://influxdb:8086` and not `localhost:8086`?**
> Inside a Docker network, containers communicate with each other using their service names as hostnames. Both Grafana and InfluxDB live inside the same Docker network defined in docker-compose.yml, so Grafana reaches InfluxDB by the name `influxdb` — not `localhost`, which from Grafana's perspective refers to the Grafana container itself, not the host machine.

### Why Flux and not InfluxQL

InfluxDB 2.x introduced Flux as its native query language, replacing InfluxQL (used in v1.x). Flux is more expressive, supports complex transformations, joins across measurements, and is the recommended approach for all InfluxDB 2.x development. InfluxQL remains available for backwards compatibility but is not appropriate for new projects.

### Flux query for the temperature panel

```flux
from(bucket: "greenhouse")
  |> range(start: -30m)
  |> filter(fn: (r) => r._measurement == "temperature")
  |> filter(fn: (r) => r._field == "value")
```

**How this query works:**

Each line uses the pipe operator `|>` to pass data to the next transformation step, similar to Unix pipes:

1. `from(bucket: "greenhouse")` — opens the greenhouse data bucket
2. `range(start: -30m)` — limits the result to the last 30 minutes
3. `filter(fn: (r) => r._measurement == "temperature")` — keeps only temperature rows
4. `filter(fn: (r) => r._field == "value")` — keeps only the numeric value field

### Dashboard configuration

| Setting | Value |
|---|---|
| Panel title | `Temperature - Central Zone` |
| Visualization type | Time series (auto-detected) |
| Time range | Last 30 minutes |
| Auto-refresh | Every 5 seconds |
| Dashboard name | `Greenhouse Monitor` |

### Confirmed result

The panel displays the simulated temperature curve updating in real time every 5 seconds. The values at the time of creation (~14–15 °C) correspond to the early-morning section of the sinusoidal model, which is the expected output when the simulation starts at midnight (elapsed time = 0).

The full end-to-end pipeline is now validated:

```
temperature_sensor.py
    │
    ├──► Mosquitto (MQTT)  ✅
    │
    ├──► InfluxDB           ✅
    │
    └──► Grafana dashboard  ✅  ← confirmed live
```

<!--  ============================================================  -->
<!--  🆕 ADDED: May 19, 2026 — Multi-sensor simulator               -->
<!--  ============================================================  -->

## Phase 4 — Multi-Sensor Simulator with Physical Models 🆕

### What was done

The single-sensor prototype was replaced by a fully structured multi-sensor simulator. The code was refactored into three files following the **separation of concerns** principle, and four additional virtual sensors were implemented with physical models that interact with each other. A first behaviour rule (threshold-based irrigation) was also introduced.

### Why the code was split into three files

With a single sensor, keeping everything in one file was acceptable. With five sensors, interdependent variables, and a coordination loop, a monolithic file becomes unmaintainable. Each file now has a single, clear responsibility:

| File | Responsibility |
|---|---|
| `config.py` | All connection parameters and simulation constants |
| `sensors.py` | All physical models — how each variable behaves |
| `greenhouse_simulator.py` | Coordination, state management, publishing loop |

This structure means that changing the MQTT broker only requires editing `config.py`, changing a physical model only requires editing `sensors.py`, and neither change breaks anything else. This is a direct application of the **Single Responsibility Principle** from software engineering.

### Updated folder structure

```
simulator/
├── requirements.txt
├── config.py                  ← connection config + simulation constants
├── sensors.py                 ← physical models for all variables
├── greenhouse_simulator.py    ← main entry point, coordinates everything
└── temperature_sensor.py      ← kept as reference, no longer used
```

### `config.py` — Centralised configuration

```python
PUBLISH_INTERVAL_SEC  = 5      # real seconds between each publish cycle
SIMULATED_STEP_SEC    = 300    # simulated seconds advanced per cycle (5 min)
```

The critical design decision here is the **time acceleration ratio**: every 5 real seconds, the internal simulation clock advances 5 minutes (300 seconds). This means one real minute of execution equals one simulated hour, and a full 24-hour simulation completes in 24 real minutes. This is essential for the TFM — it allows running and comparing multi-day scenarios in minutes rather than days.

### `sensors.py` — Physical models

Each function implements a simplified but physically grounded model of a greenhouse variable.

---

**Temperature model**

```python
T(t) = 23.5 + 8.5 × sin(2π × t/86400 − π/2) + noise(±0.3)
```

A sinusoidal function with a 24-hour period. The phase offset `-π/2` shifts the curve so that the minimum (~15 °C) falls at midnight and the maximum (~32 °C) at solar noon. The noise term (±0.3 °C uniform random) simulates the natural variability of a real sensor reading.

| Parameter | Value | Justification |
|---|---|---|
| Base temperature | 23.5 °C | Midpoint of a typical Mediterranean greenhouse |
| Amplitude | 8.5 °C | Realistic day/night thermal swing |
| Noise | ±0.3 °C | Simulates real sensor precision limits |

---

**Ambient humidity model**

```python
H = 70 − 1.8 × (T − 23.5) + noise(±1.0)
```

Ambient relative humidity is inversely correlated with temperature. As temperature rises, the air's capacity to hold water vapour increases, which reduces relative humidity. The sensitivity constant (1.8 % per °C) is a simplified linear approximation of the psychrometric relationship. Output is clamped to the physically valid range of 40–90% RH.

---

**Solar radiation model**

```python
R(t) = 900 × sin(π × (hour − 6) / (20 − 6))   for 6h ≤ hour ≤ 20h
R(t) = 0                                          otherwise
```

A half-sinusoid between sunrise (06:00) and sunset (20:00), peaking at ~900 W/m² at solar noon. Zero outside daylight hours. The peak value of 900 W/m² is consistent with clear-sky irradiance at Mediterranean latitudes.

---

**Soil moisture model**

```python
evapotranspiration = (T × 0.0005) + (R × 0.00005)

if irrigating:
    Δ = +1.2 − evapotranspiration
else:
    Δ = −evapotranspiration
```

This is the most important model because it connects multiple variables. **Evapotranspiration** — the combined process of soil evaporation and plant transpiration — is driven by both temperature and solar radiation. Higher temperature and more solar energy both accelerate water loss from the soil. When irrigation is active, the soil gains +1.2% moisture per tick, partially offset by ongoing evapotranspiration. Output is clamped to 10–100%.

This interdependency (soil moisture depends on temperature and radiation) is what gives the simulation its physical realism and academic value.

---

**Water tank level model**

```python
if irrigating:
    Δ = −0.8 per tick
else:
    Δ = 0
```

The tank level only decreases when the irrigation pump is active. This directly models water consumption — one of the primary KPIs of the TFM. Over a simulated day, the total decrease in tank level corresponds to total irrigation water used.

---

### `greenhouse_simulator.py` — Simulation coordinator

**State variables:**

```python
soil_moisture = 65.0    # initial value (%)
water_level   = 100.0   # full tank at start
irrigating    = False   # actuator state
```

Temperature, humidity, and radiation are **stateless** — their value depends only on the current simulated time. Soil moisture and water level are **stateful** — each tick's value depends on the previous tick's value. This distinction is fundamental: stateful variables must be stored between iterations, which is why they live outside the main loop.

**First behaviour rule — threshold-based irrigation:**

```python
if soil_moisture < 30.0 and water_level > 0:
    irrigating = True
elif soil_moisture >= 60.0 or water_level <= 0:
    irrigating = False
```

This implements the first management strategy that will be compared in the TFM: **hysteresis-based irrigation control**. The system activates irrigation when soil moisture drops below 30% and deactivates it when moisture recovers to 60%. Using two different thresholds (hysteresis) prevents the system from rapidly switching on and off when moisture is near a single threshold. This is exactly one of the scenarios whose KPIs will be evaluated and compared against scheduled irrigation.

**Unified publish loop:**

```python
readings = {
    "temperature":    {"value": temperature,    "topic": "greenhouse/sensor/temperature"},
    "humidity":       {"value": humidity,        "topic": "greenhouse/sensor/humidity"},
    "solar_radiation":{"value": radiation,       "topic": "greenhouse/sensor/solar_radiation"},
    "soil_moisture":  {"value": soil_moisture,   "topic": "greenhouse/sensor/soil_moisture"},
    "water_level":    {"value": water_level,     "topic": "greenhouse/sensor/water_level"},
}

for name, data in readings.items():
    publish(data["topic"], {...})
    write_point(name, "value", data["value"], tags)
```

All sensors are treated uniformly — a dictionary maps each sensor name to its current value and MQTT topic. The loop publishes all of them with the same code. Adding a new sensor only requires adding one entry to the dictionary, with no changes to the publishing logic.

### MQTT topic structure

```
greenhouse/sensor/temperature       → float (°C)
greenhouse/sensor/humidity          → float (% RH)
greenhouse/sensor/solar_radiation   → float (W/m²)
greenhouse/sensor/soil_moisture     → float (%)
greenhouse/sensor/water_level       → float (%)
```

### Grafana dashboard — Greenhouse Monitor

Five panels were created in the `Greenhouse Monitor` dashboard, one per sensor, all using the same Flux query pattern:

```flux
from(bucket: "greenhouse")
  |> range(start: -30m)
  |> filter(fn: (r) => r._measurement == "<measurement_name>")
  |> filter(fn: (r) => r._field == "value")
```

| Panel | Measurement | Unit | Observed behaviour |
|---|---|---|---|
| Temperature | `temperature` | °C | Rising sinusoid — midnight to noon cycle |
| Ambient Humidity | `humidity` | % RH | Decreasing as temperature rises |
| Solar Radiation | `solar_radiation` | W/m² | Rising from 0 at dawn toward ~900 at noon |
| Soil Moisture | `soil_moisture` | % | Slowly decreasing due to evapotranspiration |
| Water Tank Level | `water_level` | % | Stable at 100% — irrigation not yet triggered |

Dashboard settings: time range `Last 15 minutes`, auto-refresh every `5s`.

### Physical coherence validation

The observed data in the dashboard confirms that all physical relationships are working correctly:

- As temperature rises, humidity decreases ✅ (inverse correlation)
- As temperature and radiation rise, soil moisture decreases faster ✅ (evapotranspiration)
- Solar radiation is zero at night and rises through the morning ✅ (half-sinusoid model)
- Water tank remains full until soil moisture drops below 30% ✅ (hysteresis rule)

### Issues encountered and resolved

| Issue | Cause | Solution |
|---|---|---|
| `401 Unauthorized` on first run | Token placeholder not replaced in `config.py` | Updated `INFLUX_TOKEN` with real token from InfluxDB UI |
| Water tank Y-axis showing 0–200 | Grafana auto-scaled from old data | Set manual axis Min=0, Max=100 in panel options |

---

## Current Status

| Component | Status |
|---|---|
| Docker infrastructure (Mosquitto + InfluxDB + Grafana) | ✅ Running |
| MQTT data flow | ✅ Working |
| InfluxDB persistence | ✅ Writing correctly |
| Grafana connected to InfluxDB | ✅ Connected (Flux mode) |
| Temperature virtual sensor | ✅ Sinusoidal day/night model |
| Ambient humidity virtual sensor | ✅ Inverse correlation with temperature |
| Solar radiation virtual sensor | ✅ Half-sinusoid daylight model |
| Soil moisture virtual sensor | ✅ Evapotranspiration model |
| Water tank level virtual sensor | ✅ Consumption model |
| Threshold-based irrigation rule | ✅ Hysteresis control implemented |
| Grafana dashboard (5 panels) | ✅ All sensors live |
| Crop growth model (GDD) | ⏳ Not started |
| REST API (FastAPI) | ⏳ Not started |
| Scenario manager | ⏳ Not started |
| KPI calculator | ⏳ Not started |

---

## Next Steps

1. Build the REST API with FastAPI to expose all virtual sensors and actuators as HTTP endpoints
2. Add the crop growth model (Growing Degree Days — GDD)
3. Implement the scenario manager (scheduled irrigation vs threshold irrigation vs ventilation strategies)
4. Implement the KPI calculator (water efficiency, energy consumption, crop productivity)
5. Connect KPI results to Grafana for comparative scenario analysis
6. Validate simulation outputs against real-world agricultural reference values

<!--  ============================================================  -->
<!--  🆕 ADDED: May 19, 2026 — REST API with FastAPI                -->
<!--  ============================================================  -->

## Phase 5 — REST API with FastAPI 🆕

### What was done

A REST API was built using FastAPI to expose all virtual sensors and actuators as standard HTTP endpoints. The API runs simultaneously with the simulation loop using Python threads, sharing state through a thread-safe shared object.

### The concurrency problem and its solution

Both the simulation loop and the API server need to run indefinitely and simultaneously. Two infinite processes cannot run sequentially — they must run in parallel. The solution was Python's `threading` module:

```
python greenhouse_simulator.py
         │
         ├──► Background thread → run_simulation()
         │         updates sensors every 5s
         │         writes to state.py, MQTT, InfluxDB
         │
         └──► Main thread → uvicorn (web server)
                   listens for HTTP requests on :8000
                   reads from state.py on each request
```

The background thread is started as a **daemon thread**, meaning it will automatically stop when the main thread (uvicorn) stops. This ensures clean shutdown when the process is terminated.

### New files created

| File | Purpose |
|---|---|
| `state.py` | Thread-safe shared state between simulator and API |
| `api.py` | FastAPI application with all route definitions |

`greenhouse_simulator.py` was updated to import and write to `state.py`, and to start the simulation loop in a background thread before launching uvicorn.

### `state.py` — Shared state

The shared state is a Python class instance (singleton) imported by both the simulator and the API. It holds the current value of every sensor and actuator, plus simulation metadata.

**Thread safety with Lock:**

```python
from threading import Lock

class GreenhouseState:
    def __init__(self):
        self._lock = Lock()
        ...

    def update(self, **kwargs):
        with self._lock:    # only one thread can write at a time
            ...

    def snapshot(self) -> dict:
        with self._lock:    # read and write cannot overlap
            ...
```

The `Lock` ensures that if the simulator is writing values at the exact same moment the API is reading them, one operation waits for the other to complete. Without this, a read could see a partially-updated state — for example, temperature updated but humidity not yet — producing inconsistent responses. This is called a **race condition**, and the Lock prevents it.

**State fields:**

```python
# Sensor values
temperature     = 0.0
humidity        = 0.0
solar_radiation = 0.0
soil_moisture   = 65.0
water_level     = 100.0

# Actuator states
irrigating = False

# Simulation metadata
simulated_elapsed = 0.0
last_update       = ""
running           = False
```

### `api.py` — FastAPI application

FastAPI converts Python functions into HTTP endpoints using decorators. The framework handles JSON serialization, input validation, error responses, and documentation generation automatically.

```python
@app.get("/sensors/{sensor_name}")
def get_sensor(sensor_name: str):
    sensors = state.snapshot()["sensors"]
    if sensor_name not in sensors:
        raise HTTPException(status_code=404, detail="Sensor not found")
    return {"sensor": sensor_name, **sensors[sensor_name]}
```

**Pydantic models for request validation:**

```python
class IrrigationCommand(BaseModel):
    active: bool
```

FastAPI uses Pydantic models to validate incoming request bodies. If a client sends `{ "active": "yes" }` instead of `{ "active": true }`, FastAPI automatically rejects it with a 422 error before the function is even called.

### API endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | API info and version |
| GET | `/status` | Simulator running state and simulated time |
| GET | `/sensors` | All sensor readings |
| GET | `/sensors/{name}` | Single sensor by name |
| GET | `/actuators` | All actuator states |
| POST | `/actuators/irrigation` | Activate or deactivate irrigation |
| GET | `/docs` | Interactive Swagger UI (auto-generated) |

### Swagger UI — Automatic documentation

FastAPI generates a fully interactive API documentation page at `http://localhost:8000/docs` with zero additional code. Every endpoint, its parameters, request body schema, and response format are documented automatically from the Python function signatures and Pydantic models. This is one of FastAPI's key advantages for a TFM: any evaluator can explore and test the API without any additional tooling.

### Complete system architecture at this stage

```
greenhouse_simulator.py
        │
        ├──► MQTT  ──────────────► Mosquitto  :1883
        │
        ├──► InfluxDB ───────────► InfluxDB   :8086 ──► Grafana :3000
        │
        └──► REST API ───────────► FastAPI    :8000/docs
```

### New dependencies added

```
fastapi==0.111.0
uvicorn==0.29.0
```

### Running the full system

```bash
# 1 — Start Docker services (from project root)
docker compose up -d

# 2 — Start simulator + API (from simulator/)
cd simulator
python greenhouse_simulator.py
```

Both the simulation loop and the REST API start simultaneously. The Swagger UI is available at `http://localhost:8000/docs`.

---

## Session Startup Checklist

At the beginning of every working session, always run these steps in order:

```bash
# Step 1 — Open Docker Desktop and wait for "Engine running"

# Step 2 — Start infrastructure (from project root)
docker compose up -d

# Step 3 — Start simulator + API (from simulator/)
cd simulator
python greenhouse_simulator.py

# Step 4 — Verify
# Grafana dashboard → http://localhost:3000
# Swagger API docs  → http://localhost:8000/docs
# InfluxDB UI       → http://localhost:8086
```

---

## Current Status

| Component | Status |
|---|---|
| Docker infrastructure (Mosquitto + InfluxDB + Grafana) | ✅ Running |
| MQTT data flow | ✅ Working |
| InfluxDB persistence | ✅ Writing correctly |
| Grafana dashboard (5 panels) | ✅ All sensors live |
| Temperature virtual sensor | ✅ Sinusoidal day/night model |
| Ambient humidity virtual sensor | ✅ Inverse correlation with temperature |
| Solar radiation virtual sensor | ✅ Half-sinusoid daylight model |
| Soil moisture virtual sensor | ✅ Evapotranspiration model |
| Water tank level virtual sensor | ✅ Consumption model |
| Threshold-based irrigation rule | ✅ Hysteresis control |
| REST API (FastAPI) | ✅ 6 endpoints live |
| Swagger UI documentation | ✅ Auto-generated at /docs |
| Crop growth model (GDD) | ⏳ Next |
| Scenario manager | ⏳ Not started |
| KPI calculator | ⏳ Not started |

---

## Next Steps

1. Add crop growth model (Growing Degree Days — GDD) to sensors.py and expose via API
2. Implement scenario manager — run same simulation with different strategies
3. Implement KPI calculator — water efficiency, energy, crop productivity
4. Connect KPI results to Grafana for comparative analysis
5. Validate simulation outputs against real-world agricultural reference values

<!--  ============================================================  -->
<!--  🆕 ADDED: May 26, 2026 — Crop growth model                    -->
<!--  ============================================================  -->

## Phase 6 — Crop Growth Model (GDD) 🆕

### What was done

A crop growth model based on the **Growing Degree Days (GDD)** concept was added to the simulation. This model accumulates a growth index over time based on temperature, solar radiation, and soil moisture conditions. It is the primary agronomic indicator of the platform and the main output variable used to evaluate the effectiveness of irrigation strategies.

### Why GDD

Growing Degree Days is the standard agronomic model for quantifying crop development. The core principle is that plant growth only occurs when temperature is within a viable range, and accumulates faster when conditions are optimal. It is widely used in precision agriculture and provides a scientifically grounded basis for comparing management strategies.

### Mathematical model

```
GDD per tick = max(0, (T − T_base) / (T_opt − T_base))  capped at 1.0

growth_delta = GDD × light_factor × moisture_factor × day_fraction × 2.0

accumulated_growth += growth_delta
```

| Parameter | Value | Meaning |
|---|---|---|
| T_base | 10 °C | Minimum temperature for growth |
| T_opt | 24 °C | Temperature of maximum growth rate |
| T_max | 35 °C | Temperature above which growth stops |
| light_factor | radiation / 600, capped at 1.0 | Reduces growth when radiation is low |
| moisture_factor | 1.0 when 40–80% soil moisture | Drought stress below 40%, waterlogging above 80% |
| day_fraction | step_sec / 86400 | Scales contribution by simulated time step |

### Key design decisions

**Three interacting factors:** growth is not driven by temperature alone. Light and soil moisture act as multipliers that can boost or limit the temperature-driven base rate. This models the real-world interaction between environmental variables and plant physiology.

**Moisture factor detail:**
- Below 40% soil moisture: drought stress — factor drops linearly toward 0
- Between 40–80%: optimal range — factor = 1.0 (no penalty)
- Above 80%: waterlogging — factor decreases (excess water starves roots of oxygen)

This waterlogging penalty is critical — it explains why over-irrigation reduces crop growth, a result confirmed in the scenario comparison.

**Night behaviour:** when solar radiation is 0 (nighttime), light_factor = 0, so growth delta = 0 regardless of temperature. This is physically correct — photosynthesis requires light.

### Console output change

The simulated time display was improved from a decimal (`10.92h`) to a clock format (`10:55h`) for readability:

```python
sim_hours   = int(sim_hour)
sim_minutes = int((sim_hour - sim_hours) * 60)
print(f"[{sim_hours:02d}:{sim_minutes:02d}h] ...")
```

### New MQTT topic

```
greenhouse/sensor/crop_growth   → float (growth index 0–100)
```

---

<!--  ============================================================  -->
<!--  🆕 ADDED: May 26, 2026 — Scenario engine and KPI calculator   -->
<!--  ============================================================  -->

## Phase 7 — Scenario Engine and KPI Calculator 🆕

### What was done

A scenario engine was implemented that runs complete multi-day simulations in memory at maximum speed, evaluating different irrigation strategies. A KPI calculator automatically computes performance indicators at the end of each scenario. Three scenarios were run and compared, producing the first meaningful analytical results of the platform.

### Architecture

Scenarios run differently from the live simulator. The live simulator runs with real-time delays and publishes to MQTT and InfluxDB. Scenarios run at maximum CPU speed in memory, with no delays, no MQTT, and no InfluxDB — pure computation. This allows simulating 7 days in under one second.

```
POST /scenarios/run
        │
        └──► scenarios.py — runs N days of ticks in memory
                    │
                    └──► kpi_calculator.py — computes KPIs from all ticks
                                │
                                └──► result stored in scenario_store (in-memory dict)
                                         retrieved via GET /scenarios/{id}
                                         compared via GET /scenarios/compare
```

### New files created

**`kpi_calculator.py`** — computes all KPIs from a list of simulation ticks:

| KPI | Calculation |
|---|---|
| `total_water_liters` | ticks with irrigation active × 2.0 L/tick |
| `energy_kwh` | irrigation hours × 0.5 kW pump power |
| `final_crop_growth` | accumulated GDD index at last tick |
| `water_efficiency` | final_crop_growth / total_water_liters |
| `water_stress_hours` | ticks with soil_moisture < 30% × hours_per_tick |
| `irrigation_activations` | count of off→on transitions in irrigation state |

**`scenarios.py`** — defines irrigation strategies and runs simulations:

```python
STRATEGIES = {
    "threshold":     _strategy_threshold,      # smart, demand-driven
    "scheduled":     _strategy_scheduled,      # fixed time windows
    "no_irrigation": _strategy_no_irrigation,  # baseline
}
```

Each strategy is a function with the same signature:
```python
def strategy(soil_moisture, water_level, irrigating, sim_hour) -> bool
```

This uniform interface means adding a new strategy only requires adding one function and one dictionary entry — no changes to the simulation engine.

### Irrigation strategies implemented

**Threshold (hysteresis control):**
```python
if soil_moisture < 30.0 and water_level > 0:  return True   # activate
elif soil_moisture >= 60.0 or water_level <= 0: return False  # deactivate
else:                                            return irrigating  # hold
```
Demand-driven: only reacts when the soil actually needs water. The two thresholds (30% ON, 60% OFF) form a hysteresis band that prevents rapid on/off cycling near a single threshold.

**Scheduled:**
```python
in_window = (7.0 <= sim_hour < 7.5) or (19.0 <= sim_hour < 19.5)
return in_window and water_level > 0
```
Time-driven: irrigates for 30 minutes at 07:00 and 19:00 every simulated day, regardless of actual soil moisture. Represents the most common real-world practice in non-automated farms.

**No irrigation:**
```python
return False
```
Baseline scenario. Used to quantify the value of any irrigation strategy relative to doing nothing.

### New API endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/scenarios/run` | Run a scenario — body: `{ strategy, duration_days }` |
| GET | `/scenarios` | List all completed scenarios with KPIs |
| GET | `/scenarios/{id}` | Full result including hourly samples |
| GET | `/scenarios/compare` | All scenarios side by side for comparison |

### Scenario results — 7-day simulation

Three scenarios were executed with `duration_days: 7` and identical initial conditions:
- Initial soil moisture: 65%
- Initial water tank: 100% (full)
- Simulation start: midnight (00:00h)

#### Raw results

| KPI | No irrigation | Scheduled | Threshold |
|---|---|---|---|
| Water consumed (L) | 0 | 168 | **54** |
| Energy (kWh) | 0 | 3.50 | **1.12** |
| Crop growth index | 5.060 | 3.885 | **6.162** |
| Water efficiency | 0 | 0.0231 | **0.1141** |
| Water stress (h) | 59.6 | 0 | **0.1** |
| Irrigation activations | 0 | 14 | 1 |

#### Interpretation of results

**No irrigation** establishes the baseline. Without any water input, the soil dries out progressively through evapotranspiration, accumulating 59.6 hours of water stress. Despite this, the crop reaches a growth index of 5.06 because temperature and light conditions remain favourable during daylight hours. This scenario represents the worst case for crop welfare but consumes no resources.

**Scheduled irrigation** produces a counterintuitive result: it uses the most water (168L — three times more than threshold) yet achieves the lowest crop growth (3.885). The cause is the waterlogging effect in the growth model. Fixed-time irrigation at 07:00 and 19:00 raises soil moisture above 80% repeatedly, regardless of whether the soil actually needs water. When moisture exceeds 80%, the moisture_factor applies a waterlogging penalty (roots deprived of oxygen), which suppresses photosynthesis and reduces growth. This models a well-documented real-world phenomenon: over-irrigation is as harmful as under-irrigation. The water efficiency of 0.0231 is the worst of all irrigated scenarios.

**Threshold irrigation** wins on every meaningful KPI. It uses 68% less water than scheduled irrigation while producing 59% more crop growth. The single irrigation activation across the entire 7-day period reflects the efficiency of the hysteresis control: one well-timed irrigation event kept soil moisture in the optimal range (40–80%) for nearly the entire simulation, with only 0.1 hours of mild water stress. The water efficiency of 0.1141 is almost five times better than scheduled irrigation.

#### Academic significance

These results demonstrate a core finding of precision agriculture research: **demand-driven irrigation consistently outperforms time-based irrigation** in both resource efficiency and crop productivity. The platform successfully quantifies this difference through simulated KPIs, validating the value of IoT-based monitoring and intelligent control strategies over traditional fixed-schedule approaches.

The comparison also highlights an important nuance: **more water does not mean more growth**. The scheduled scenario consumes the most resources and produces the worst agricultural outcome among irrigated scenarios, which is a non-obvious result that the simulation makes immediately visible.

These findings provide the analytical foundation for the TFM conclusions chapter.

---

## Current Status

| Component | Status |
|---|---|
| Docker infrastructure | ✅ Running |
| MQTT data flow | ✅ Working |
| InfluxDB persistence | ✅ Writing correctly |
| Grafana dashboard (6 panels) | ✅ All sensors + crop growth live |
| All virtual sensors (5 + crop growth) | ✅ Complete |
| Threshold irrigation rule (live) | ✅ Working |
| REST API — live sensor endpoints | ✅ 6 endpoints |
| REST API — scenario endpoints | ✅ 4 endpoints |
| Crop growth model (GDD) | ✅ Implemented and validated |
| Scenario engine (3 strategies) | ✅ Threshold, scheduled, no_irrigation |
| KPI calculator | ✅ 6 KPIs computed |
| Scenario comparison | ✅ Results validated and interpreted |
| Scenario results in Grafana | ⏳ Not started |
| Validation against real-world data | ⏳ Not started |

---

## Next Steps

1. Visualize scenario KPI comparison in Grafana (bar charts)
2. Validate simulation models against real-world agricultural reference values
3. Write conclusions based on scenario results
4. Final documentation and memory