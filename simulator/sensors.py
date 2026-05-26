import math
import random


def simulate_temperature(elapsed_seconds: float) -> float:
    """
    Day/night sinusoidal cycle.
    Min ~15°C at midnight, max ~32°C at noon.
    """
    cycle  = elapsed_seconds % 86_400
    angle  = (2 * math.pi * cycle / 86_400) - (math.pi / 2)
    value  = 23.5 + 8.5 * math.sin(angle) + random.uniform(-0.3, 0.3)
    return round(value, 2)


def simulate_humidity(temperature: float) -> float:
    """
    Ambient humidity (%).
    Inversely correlated with temperature:
    higher temperature → lower humidity (typical greenhouse behaviour).
    Range: 40–90% RH.
    """
    base_humidity = 70.0
    base_temp     = 23.5
    sensitivity   = 1.8        # % drop per degree above base

    value = base_humidity - sensitivity * (temperature - base_temp)
    value = value + random.uniform(-1.0, 1.0)
    value = max(40.0, min(90.0, value))   # clamp to valid range
    return round(value, 2)


def simulate_solar_radiation(elapsed_seconds: float) -> float:
    """
    Solar radiation (W/m²).
    Zero at night, peaks ~900 W/m² at solar noon.
    Follows a half-sinusoid between sunrise (~6h) and sunset (~20h).
    """
    hour = (elapsed_seconds % 86_400) / 3600   # current simulated hour

    sunrise = 6.0
    sunset  = 20.0

    if hour < sunrise or hour > sunset:
        return 0.0

    cycle = math.pi * (hour - sunrise) / (sunset - sunrise)
    value = 900 * math.sin(cycle) + random.uniform(-10, 10)
    value = max(0.0, value)
    return round(value, 2)


def simulate_soil_moisture(
    current_moisture: float,
    temperature: float,
    radiation: float,
    irrigating: bool
) -> float:
    """
    Soil moisture (%).
    Decreases over time due to evapotranspiration (driven by temp and radiation).
    Increases when irrigation is active.
    Range: 10–100%.
    """
    # Evapotranspiration: higher temp and radiation → faster drying
    evapotranspiration = (temperature * 0.0005) + (radiation * 0.00005)

    if irrigating:
        delta = +1.2 - evapotranspiration   # irrigation adds moisture
    else:
        delta = -evapotranspiration          # moisture only decreases

    value = current_moisture + delta + random.uniform(-0.1, 0.1)
    value = max(10.0, min(100.0, value))
    return round(value, 2)


def simulate_water_level(
    current_level: float,
    irrigating: bool
) -> float:
    """
    Water tank level (%).
    Decreases when irrigation pump is active.
    Range: 0–100%.
    """
    if irrigating:
        delta = -0.8 + random.uniform(-0.05, 0.05)
    else:
        delta = 0.0

    value = current_level + delta
    value = max(0.0, min(100.0, value))
    return round(value, 2)

def simulate_crop_growth(
    current_growth: float,
    temperature: float,
    solar_radiation: float,
    soil_moisture: float,
    simulated_step_sec: float
) -> float:
    """
    Crop growth model based on Growing Degree Days (GDD).

    Growth accumulates when temperature is within the optimal
    range (10–35°C). Light and soil moisture act as multipliers
    that can boost or limit growth.

    Args:
        current_growth:     accumulated growth index so far (0–100)
        temperature:        current temperature (°C)
        solar_radiation:    current solar radiation (W/m²)
        soil_moisture:      current soil moisture (%)
        simulated_step_sec: simulated seconds per tick

    Returns:
        Updated accumulated growth index (0–100)
    """
    T_BASE    = 10.0    # minimum temperature for growth (°C)
    T_OPT     = 24.0    # optimal temperature (°C)
    T_MAX     = 35.0    # maximum temperature — growth stops above this

    # No growth outside viable range
    if temperature <= T_BASE or temperature >= T_MAX:
        return round(current_growth, 3)

    # Base GDD contribution for this tick
    # Scaled by simulated time step (fraction of a day)
    gdd = (temperature - T_BASE) / (T_OPT - T_BASE)
    gdd = min(gdd, 1.0)   # cap at 1.0 (optimal conditions)

    # Light multiplier: full effect at 600+ W/m², reduced below that
    light_factor = min(solar_radiation / 600.0, 1.0)

    # Soil moisture multiplier: optimal 40–80%, stressed outside
    if 40.0 <= soil_moisture <= 80.0:
        moisture_factor = 1.0
    elif soil_moisture < 40.0:
        moisture_factor = soil_moisture / 40.0   # drought stress
    else:
        moisture_factor = 1.0 - (soil_moisture - 80.0) / 20.0  # excess water

    moisture_factor = max(0.0, moisture_factor)

    # Time scaling: convert simulated step to fraction of a day
    day_fraction = simulated_step_sec / 86_400

    # Final growth delta
    delta = gdd * light_factor * moisture_factor * day_fraction * 2.0

    new_growth = current_growth + delta
    return round(min(new_growth, 100.0), 3)