import time
import json
import threading
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
import uvicorn
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

import config
from sensors import (
    simulate_temperature,
    simulate_humidity,
    simulate_solar_radiation,
    simulate_soil_moisture,
    simulate_water_level,
    simulate_crop_growth,       # ← NUEVO
)
from state import state
from api import app  # noqa: F401


# ── MQTT setup ──────────────────────────────────────────────
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("  [MQTT] Connected to broker")
    else:
        print(f"  [MQTT] Connection failed — code {rc}")

mqtt_client = mqtt.Client(client_id="greenhouse-simulator")
mqtt_client.on_connect = on_connect
mqtt_client.connect(config.MQTT_BROKER, config.MQTT_PORT)
mqtt_client.loop_start()

# ── InfluxDB setup ──────────────────────────────────────────
influx_client = InfluxDBClient(
    url=config.INFLUX_URL,
    token=config.INFLUX_TOKEN,
    org=config.INFLUX_ORG
)
write_api = influx_client.write_api(write_options=SYNCHRONOUS)


def publish_mqtt(topic: str, payload: dict):
    mqtt_client.publish(topic, json.dumps(payload))


def write_influx(measurement: str, value: float, tags: dict):
    point = Point(measurement).field("value", value)
    for key, val in tags.items():
        point = point.tag(key, val)
    write_api.write(bucket=config.INFLUX_BUCKET, record=point)


# ── Simulation loop ─────────────────────────────────────────
def run_simulation():
    IRRIGATION_ON  = 30.0
    IRRIGATION_OFF = 60.0
    tags = {"location": "central_zone"}

    # ── State variables (depend on previous tick) ───────────
    soil_moisture = state.soil_moisture
    water_level   = state.water_level
    crop_growth   = state.crop_growth   # ← NUEVO
    irrigating    = state.irrigating

    state.update(running=True)

    print("=" * 55)
    print("  Greenhouse IoT Simulator")
    print(f"  Simulated step : {config.SIMULATED_STEP_SEC}s per tick")
    print(f"  Publish every  : {config.PUBLISH_INTERVAL_SEC}s real time")
    print("  API running at : http://localhost:8000/docs")
    print("=" * 55)

    try:
        while True:
            timestamp  = datetime.now(timezone.utc).isoformat()
            elapsed    = state.simulated_elapsed

            # ── Simulate all sensors ───────────────────────
            temperature   = simulate_temperature(elapsed)
            humidity      = simulate_humidity(temperature)
            radiation     = simulate_solar_radiation(elapsed)
            soil_moisture = simulate_soil_moisture(
                soil_moisture, temperature, radiation, irrigating
            )
            water_level   = simulate_water_level(water_level, irrigating)
            crop_growth   = simulate_crop_growth(      # ← NUEVO
                crop_growth, temperature, radiation,
                soil_moisture, config.SIMULATED_STEP_SEC
            )

            # ── Apply irrigation rule ──────────────────────
            if soil_moisture < IRRIGATION_ON and water_level > 0:
                irrigating = True
            elif soil_moisture >= IRRIGATION_OFF or water_level <= 0:
                irrigating = False

            # ── Update shared state ────────────────────────
            state.update(
                temperature       = temperature,
                humidity          = humidity,
                solar_radiation   = radiation,
                soil_moisture     = soil_moisture,
                water_level       = water_level,
                crop_growth       = crop_growth,    # ← NUEVO
                irrigating        = irrigating,
                simulated_elapsed = elapsed + config.SIMULATED_STEP_SEC,
                last_update       = timestamp,
            )

            # ── Publish to MQTT + InfluxDB ─────────────────
            readings = {
                "temperature":    {"value": temperature,   "topic": "greenhouse/sensor/temperature"},
                "humidity":       {"value": humidity,      "topic": "greenhouse/sensor/humidity"},
                "solar_radiation":{"value": radiation,     "topic": "greenhouse/sensor/solar_radiation"},
                "soil_moisture":  {"value": soil_moisture, "topic": "greenhouse/sensor/soil_moisture"},
                "water_level":    {"value": water_level,   "topic": "greenhouse/sensor/water_level"},
                "crop_growth":    {"value": crop_growth,   "topic": "greenhouse/sensor/crop_growth"},  # ← NUEVO
            }

            for name, data in readings.items():
                publish_mqtt(data["topic"], {
                    "value": data["value"], "timestamp": timestamp
                })
                write_influx(name, data["value"], tags)

            # ── Console output ─────────────────────────────
            sim_hour    = (elapsed % 86_400) / 3600
            sim_hours   = int(sim_hour)
            sim_minutes = int((sim_hour - sim_hours) * 60)
            print(
                f"[{sim_hours:02d}:{sim_minutes:02d}h]  "
                f"[{sim_hour:05.2f}h]  "
                f"temp={temperature:.1f}°C  "
                f"hum={humidity:.1f}%  "
                f"rad={radiation:.0f}W  "
                f"soil={soil_moisture:.1f}%  "
                f"tank={water_level:.1f}%  "
                f"growth={crop_growth:.3f}  "   
                f"{'💧' if irrigating else ''}"
            )

            time.sleep(config.PUBLISH_INTERVAL_SEC)

    except Exception as e:
        print(f"\n  [Simulator] Error: {e}")
        state.update(running=False)


# ── Entry point ─────────────────────────────────────────────
if __name__ == "__main__":
    sim_thread = threading.Thread(target=run_simulation, daemon=True)
    sim_thread.start()

    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=False)