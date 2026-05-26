import os
from dotenv import load_dotenv

load_dotenv()

# ── MQTT ───────────────────────────────────────────────────
MQTT_BROKER = "localhost"
MQTT_PORT   = 1883

# ── InfluxDB ───────────────────────────────────────────────
INFLUX_URL    = "http://localhost:8086"
INFLUX_TOKEN  = os.getenv("INFLUX_TOKEN", "")
INFLUX_ORG    = "tfm"
INFLUX_BUCKET = "greenhouse"

# ── Simulation ─────────────────────────────────────────────
PUBLISH_INTERVAL_SEC = 5
SIMULATED_STEP_SEC   = 300