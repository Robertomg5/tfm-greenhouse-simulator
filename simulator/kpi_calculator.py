from dataclasses import dataclass


# Liters pumped per tick when irrigation is active
LITERS_PER_TICK = 2.0

# Pump power consumption (kW)
PUMP_KW = 0.5


@dataclass
class TickData:
    """Snapshot of all greenhouse variables at one simulation tick."""
    elapsed:          float
    sim_hour:         float
    temperature:      float
    humidity:         float
    solar_radiation:  float
    soil_moisture:    float
    water_level:      float
    crop_growth:      float
    irrigating:       bool


def calculate_kpis(ticks: list[TickData], step_sec: float) -> dict:
    """
    Calculates all KPIs from the list of simulation ticks.

    Args:
        ticks:    all recorded ticks from a scenario run
        step_sec: simulated seconds per tick (from config)

    Returns:
        Dictionary of KPI names and values
    """
    if not ticks:
        return {}

    hours_per_tick = step_sec / 3600

    # ── Water consumption ──────────────────────────────────
    irrigation_ticks = [t for t in ticks if t.irrigating]
    total_water_liters = len(irrigation_ticks) * LITERS_PER_TICK

    # ── Energy consumption (irrigation pump only) ──────────
    irrigation_hours = len(irrigation_ticks) * hours_per_tick
    energy_kwh = round(PUMP_KW * irrigation_hours, 2)

    # ── Crop growth ────────────────────────────────────────
    final_crop_growth = ticks[-1].crop_growth

    # ── Water efficiency ───────────────────────────────────
    if total_water_liters > 0:
        water_efficiency = round(final_crop_growth / total_water_liters, 4)
    else:
        water_efficiency = 0.0

    # ── Water stress ───────────────────────────────────────
    stress_ticks = [t for t in ticks if t.soil_moisture < 30.0]
    water_stress_hours = round(len(stress_ticks) * hours_per_tick, 1)

    # ── Irrigation activations (on→off cycles) ─────────────
    activations = sum(
        1 for i in range(1, len(ticks))
        if ticks[i].irrigating and not ticks[i - 1].irrigating
    )

    return {
        "total_water_liters":   round(total_water_liters, 1),
        "energy_kwh":           energy_kwh,
        "final_crop_growth":    round(final_crop_growth, 3),
        "water_efficiency":     water_efficiency,
        "water_stress_hours":   water_stress_hours,
        "irrigation_activations": activations,
    }