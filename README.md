# Restaurant Tracking System

Scaffold inicial del proyecto Umizumi para monitorear mesas de un restaurante
en Roblox.

## Stack

- Python 3.12
- Flask + HTML/CSS/JavaScript nativo
- PostgreSQL
- OpenCV y Ultralytics para los siguientes handoffs de visión
- Docker Compose

## Arranque

Requiere Docker y Docker Compose:

```bash
docker compose up --build
```

Dashboard: <http://localhost:8000>

Health check: <http://localhost:8000/health>

Prueba local sin Docker:

```bash
python3 -m unittest discover -v
```

## Entrada

Durante el checkpoint inicial, colocar imágenes `.jpg`, `.jpeg` o `.png` en:

```text
data/inbox/
```

El worker revisa la carpeta cada 30 segundos y registra los archivos
reconocidos en sus logs. El contrato de medios ya reconoce `.mp4`; el siguiente
handoff agregará extracción batch de frames con OpenCV y reutilizará la misma
transformación y carga.

## Handoffs Umizumi

1. Umizumi 1: contenedores, schema y datos fijos.
2. Umizumi 2: ingestión y normalización a frames.
3. Umizumi 3: modelo, transformación y carga.
4. Umizumi 4: API y dashboard.

Los detalles de arquitectura están en
`docs/superpowers/specs/2026-09-07-restaurant-tracker-design.md`.
