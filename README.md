# Restaurant Tracking System

Pipeline inicial del proyecto Umizumi para monitorear mesas de un restaurante
en Roblox.

## Stack

- Python 3.12
- Flask + HTML/CSS/JavaScript nativo
- PostgreSQL
- OpenCV para ingestión y extracción de frames
- Ultralytics para el siguiente handoff de inferencia
- Docker Compose

## Arranque

Requiere Docker y Docker Compose:

```bash
docker compose up --build
```

Dashboard: <http://localhost:8000>

Health check: <http://localhost:8000/health>

Pruebas dentro del contenedor de aplicación:

```bash
docker compose exec worker python -m unittest discover -v
```

## Entrada

Colocar imágenes `.jpg`, `.jpeg` o `.png`, o vídeos `.mp4`, en:

```text
data/inbox/
```

El worker revisa la carpeta cada 30 segundos, calcula SHA-256, registra cada
medio una sola vez y guarda los frames normalizados en
`data/processed/<media_hash>/`. Las imágenes producen un frame; los vídeos
producen frames cada 30 segundos. Los frames quedan en estado `pending` para
la inferencia posterior.

La detección con YOLO todavía no está integrada. El siguiente handoff reutiliza
los frames pendientes y la lógica de asociación geométrica ya disponible.

## Handoffs Umizumi

1. Umizumi 1: contenedores, schema y datos fijos.
2. Umizumi 2: ingestión y normalización a frames.
3. Umizumi 3: modelo, transformación y carga.
4. Umizumi 4: API y dashboard.

Los detalles de arquitectura están en
`docs/superpowers/specs/2026-09-07-restaurant-tracker-design.md`.
