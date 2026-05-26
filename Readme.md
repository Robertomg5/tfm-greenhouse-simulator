# TFM — Greenhouse IoT Simulation Platform

IoT simulation platform for smart greenhouse analysis and decision-making,
based on virtual sensors, MQTT, REST API, and scenario comparison.

## Stack
- Python 3.14 · FastAPI · Paho-MQTT · InfluxDB 2.7 · Grafana · Docker

## Requirements
- Docker Desktop
- Python 3.10+

## Setup

### 1 — Configure environment
Create `simulator/.env` with your InfluxDB token: 

### 2 — Start infrastructure
```bash
docker compose up -d
```

### 3 — Install Python dependencies
```bash
cd simulator
pip install -r requirements.txt
```

### 4 — Run the simulator
```bash
python greenhouse_simulator.py
```

## Access
| Service | URL |
|---|---|
| REST API + Swagger | http://localhost:8000/docs |
| Grafana dashboard | http://localhost:3000 |
| InfluxDB UI | http://localhost:8086 |