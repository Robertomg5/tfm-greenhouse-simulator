from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from state import state
from scenarios import run_scenario, scenario_store, VALID_STRATEGIES

app = FastAPI(
    title="Greenhouse IoT Simulator API",
    description="REST interface for the virtual greenhouse IoT platform.",
    version="1.0.0"
)


# ── Request models ──────────────────────────────────────────

class IrrigationCommand(BaseModel):
    active: bool


class ScenarioRequest(BaseModel):
    strategy:      str = "threshold"
    duration_days: int = 7


# ── Live sensor routes ──────────────────────────────────────

@app.get("/", summary="API info")
def root():
    return {
        "name":    "Greenhouse IoT Simulator API",
        "version": "1.0.0",
        "docs":    "/docs"
    }


@app.get("/status", summary="Simulator status")
def get_status():
    snap = state.snapshot()
    return {
        "running":        snap["simulation"]["running"],
        "simulated_hour": snap["simulation"]["simulated_hour"],
        "last_update":    snap["simulation"]["last_update"],
    }


@app.get("/sensors", summary="All sensor readings")
def get_all_sensors():
    return state.snapshot()["sensors"]


@app.get("/sensors/{sensor_name}", summary="Single sensor reading")
def get_sensor(sensor_name: str):
    sensors = state.snapshot()["sensors"]
    if sensor_name not in sensors:
        raise HTTPException(
            status_code=404,
            detail=f"Sensor '{sensor_name}' not found. "
                   f"Valid: {list(sensors.keys())}"
        )
    return {"sensor": sensor_name, **sensors[sensor_name]}


@app.get("/actuators", summary="All actuator states")
def get_actuators():
    return state.snapshot()["actuators"]


@app.post("/actuators/irrigation", summary="Control irrigation")
def control_irrigation(command: IrrigationCommand):
    state.update(irrigating=command.active)
    action = "activated" if command.active else "deactivated"
    return {"actuator": "irrigation", "status": action, "active": command.active}


# ── Scenario routes ─────────────────────────────────────────

@app.post("/scenarios/run", summary="Run a scenario")
def start_scenario(request: ScenarioRequest):
    """
    Runs a full simulation scenario in memory at maximum speed.

    Available strategies:
    - **threshold**: irrigate when soil moisture < 30%
    - **scheduled**: irrigate at 07:00 and 19:00 daily
    - **no_irrigation**: no irrigation (baseline)
    """
    if request.strategy not in VALID_STRATEGIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid strategy. Valid options: {VALID_STRATEGIES}"
        )
    if not 1 <= request.duration_days <= 30:
        raise HTTPException(
            status_code=400,
            detail="duration_days must be between 1 and 30"
        )

    scenario_id = run_scenario(request.strategy, request.duration_days)
    result      = scenario_store[scenario_id]

    return {
        "scenario_id":   scenario_id,
        "strategy":      result["strategy"],
        "duration_days": result["duration_days"],
        "status":        result["status"],
        "kpis":          result["kpis"],
    }


@app.get("/scenarios", summary="List all completed scenarios")
def list_scenarios():
    """Returns a summary of all scenarios run in this session."""
    return [
        {
            "scenario_id":   s["scenario_id"],
            "strategy":      s["strategy"],
            "duration_days": s["duration_days"],
            "status":        s["status"],
            "kpis":          s["kpis"],
        }
        for s in scenario_store.values()
    ]


@app.get("/scenarios/compare", summary="Compare all scenarios")
def compare_scenarios():
    """
    Returns all scenarios side by side for direct KPI comparison.
    """
    if not scenario_store:
        raise HTTPException(
            status_code=404,
            detail="No scenarios have been run yet. Use POST /scenarios/run first."
        )

    return {
        "scenarios": [
            {
                "scenario_id": s["scenario_id"],
                "strategy":    s["strategy"],
                "kpis":        s["kpis"],
            }
            for s in scenario_store.values()
        ]
    }


@app.get("/scenarios/{scenario_id}", summary="Get scenario results")
def get_scenario(scenario_id: str):
    """Returns full results including hourly samples for a specific scenario."""
    if scenario_id not in scenario_store:
        raise HTTPException(
            status_code=404,
            detail=f"Scenario '{scenario_id}' not found."
        )
    return scenario_store[scenario_id]