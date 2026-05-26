from threading import Lock


class GreenhouseState:
    def __init__(self):
        self._lock = Lock()

        # ── Sensor values ──────────────────────────────────
        self.temperature     = 0.0
        self.humidity        = 0.0
        self.solar_radiation = 0.0
        self.soil_moisture   = 65.0
        self.water_level     = 100.0
        self.crop_growth     = 0.0     # ← NUEVO

        # ── Actuator states ────────────────────────────────
        self.irrigating = False

        # ── Simulation metadata ────────────────────────────
        self.simulated_elapsed = 0.0
        self.last_update       = ""
        self.running           = False

    def update(self, **kwargs):
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self, key):
                    setattr(self, key, value)

    def snapshot(self) -> dict:
        with self._lock:
            sim_hour = (self.simulated_elapsed % 86_400) / 3600
            return {
                "sensors": {
                    "temperature":     {"value": self.temperature,     "unit": "C"},
                    "humidity":        {"value": self.humidity,        "unit": "%"},
                    "solar_radiation": {"value": self.solar_radiation, "unit": "W/m2"},
                    "soil_moisture":   {"value": self.soil_moisture,   "unit": "%"},
                    "water_level":     {"value": self.water_level,     "unit": "%"},
                    "crop_growth":     {"value": self.crop_growth,     "unit": "index"},  # ← NUEVO
                },
                "actuators": {
                    "irrigation": self.irrigating,
                },
                "simulation": {
                    "elapsed_seconds": self.simulated_elapsed,
                    "simulated_hour":  round(sim_hour, 2),
                    "last_update":     self.last_update,
                    "running":         self.running,
                }
            }


state = GreenhouseState()