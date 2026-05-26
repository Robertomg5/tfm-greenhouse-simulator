import uuid
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import config
import config
from kpi_calculator import TickData, calculate_kpis
from sensors import (
    simulate_temperature,
    simulate_humidity,
    simulate_solar_radiation,
    simulate_soil_moisture,
    simulate_water_level,
    simulate_crop_growth,
)

# ── In-memory store for completed scenario results ──────────
scenario_store: dict[str, dict] = {}


# ── Irrigation strategies ───────────────────────────────────

def _strategy_threshold(soil_moisture, water_level, irrigating, sim_hour):
    """
    Threshold-based irrigation with hysteresis.
    Activates below 30% soil moisture, deactivates above 60%.
    """
    if soil_moisture < 30.0 and water_level > 0:
        return True
    elif soil_moisture >= 60.0 or water_level <= 0:
        return False
    return irrigating   # maintain current state within hysteresis band


def _strategy_scheduled(soil_moisture, water_level, irrigating, sim_hour):
    """
    Scheduled irrigation: active 07:00–07:30 and 19:00–19:30.
    Ignores soil moisture — runs on fixed time windows.
    """
    in_window = (7.0 <= sim_hour < 7.5) or (19.0 <= sim_hour < 19.5)
    return in_window and water_level > 0


def _strategy_no_irrigation(soil_moisture, water_level, irrigating, sim_hour):
    """
    Baseline scenario: no irrigation at all.
    Used to measure the impact of irrigation strategies.
    """
    return False


STRATEGIES = {
    "threshold":     _strategy_threshold,
    "scheduled":     _strategy_scheduled,
    "no_irrigation": _strategy_no_irrigation,
}

VALID_STRATEGIES = list(STRATEGIES.keys())


# ── Scenario runner ─────────────────────────────────────────

def run_scenario(strategy: str, duration_days: int = 7) -> str:
    """
    Runs a complete scenario simulation in memory at maximum speed.
    No delays, no MQTT, no InfluxDB — pure computation.

    Args:
        strategy:      one of 'threshold', 'scheduled', 'no_irrigation'
        duration_days: number of simulated days to run

    Returns:
        scenario_id: unique identifier for retrieving results
    """
    if strategy not in STRATEGIES:
        raise ValueError(f"Unknown strategy '{strategy}'. Valid: {VALID_STRATEGIES}")

    scenario_id   = str(uuid.uuid4())[:8]
    strategy_fn   = STRATEGIES[strategy]
    step          = config.SIMULATED_STEP_SEC
    total_elapsed = duration_days * 86_400

    # ── Initial state ───────────────────────────────────────
    soil_moisture = 65.0
    water_level   = 100.0
    crop_growth   = 0.0
    irrigating    = False

    all_ticks: list[TickData] = []
    elapsed = 0.0

    # ── Run simulation at full speed ────────────────────────
    while elapsed < total_elapsed:
        sim_hour = (elapsed % 86_400) / 3600

        temperature   = simulate_temperature(elapsed)
        humidity      = simulate_humidity(temperature)
        radiation     = simulate_solar_radiation(elapsed)
        soil_moisture = simulate_soil_moisture(
            soil_moisture, temperature, radiation, irrigating
        )
        water_level   = simulate_water_level(water_level, irrigating)
        crop_growth   = simulate_crop_growth(
            crop_growth, temperature, radiation, soil_moisture, step
        )
        irrigating    = strategy_fn(soil_moisture, water_level, irrigating, sim_hour)

        all_ticks.append(TickData(
            elapsed         = elapsed,
            sim_hour        = round(sim_hour, 2),
            temperature     = temperature,
            humidity        = humidity,
            solar_radiation = radiation,
            soil_moisture   = soil_moisture,
            water_level     = water_level,
            crop_growth     = crop_growth,
            irrigating      = irrigating,
        ))

        elapsed += step

    # ── Calculate KPIs from all ticks ──────────────────────
    kpis = calculate_kpis(all_ticks, step)

    # ── Store hourly samples for inspection (not all ticks) ─
    ticks_per_hour = int(3600 / step)
    hourly_samples = [
        {
            "day":          int(t.elapsed // 86_400) + 1,
            "sim_hour":     t.sim_hour,
            "temperature":  t.temperature,
            "soil_moisture":t.soil_moisture,
            "crop_growth":  t.crop_growth,
            "irrigating":   t.irrigating,
        }
        for i, t in enumerate(all_ticks)
        if i % ticks_per_hour == 0
    ]

    # ── Save result ─────────────────────────────────────────
    scenario_store[scenario_id] = {
        "scenario_id":   scenario_id,
        "strategy":      strategy,
        "duration_days": duration_days,
        "status":        "completed",
        "kpis":          kpis,
        "hourly_samples":hourly_samples,
    }

    # ── Write KPIs to InfluxDB for Grafana visualization ───
    client    = InfluxDBClient(url=config.INFLUX_URL, token=config.INFLUX_TOKEN, org=config.INFLUX_ORG)
    write_api = client.write_api(write_options=SYNCHRONOUS)

    for kpi_name, kpi_value in kpis.items():
        point = (
            Point("scenario_kpi")
            .tag("strategy", strategy)
            .tag("scenario_id", scenario_id)
            .field(kpi_name, float(kpi_value))
        )
        write_api.write(bucket=config.INFLUX_BUCKET, record=point)

    client.close()

    return scenario_id