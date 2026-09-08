# Image-Independent Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dejar lista y probada la parte del pipeline que no depende de capturas reales: contratos de PostgreSQL, parametrización de frames, asociación geométrica y coordinación de inferencia mediante un detector inyectable.

**Architecture:** PostgreSQL seguirá siendo el único almacenamiento. `app/vision.py` tendrá la lógica pura de punto-en-polígono y agregación; `app/db.py` expondrá consultas y una carga transaccional; `app/worker.py` coordinará frames pendientes sin cargar YOLO todavía.

**Tech Stack:** Python 3.12, PostgreSQL, psycopg, OpenCV, `unittest` y mocks únicamente donde no exista una imagen o base disponible.

---

### Task 1: Definir pruebas de transformación y coordinación

**Files:**
- Create: `tests/test_vision.py`
- Modify: `tests/test_worker.py`

- [ ] **Step 1: Write the failing tests**

Cubrir:

- un punto dentro, fuera y sobre el borde de un polígono;
- una detección asignada a una mesa por el punto inferior central;
- una mesa sin detecciones con `people_count = 0`;
- un frame pendiente procesado con un detector falso;
- un intervalo de vídeo leído desde `FRAME_INTERVAL_SECONDS`.

- [ ] **Step 2: Run the tests to verify the new behavior fails**

Run: `python3 -m unittest tests.test_vision -v`
Expected: FAIL because `app.vision` and the new worker behavior do not exist yet.

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_vision.py tests/test_worker.py
git commit -m "test: define image-independent pipeline behavior"
```

### Task 2: Implementar contratos de datos y transformación

**Files:**
- Create: `app/vision.py`
- Modify: `app/db.py`
- Modify: `app/worker.py`

- [ ] **Step 1: Implement the smallest code for the tests**

Agregar:

- `point_in_polygon(point, polygon)` con ray casting y borde incluido;
- `build_table_observations(detections, tables, model_version)`, usando el
  punto inferior central y devolviendo una observación por mesa;
- `fetch_pending_frames()`, `fetch_tables()` y una carga transaccional de
  observaciones que marque el frame como `processed`;
- `process_pending_frames(detector, model_version)` con el detector como
  callable inyectado;
- `FRAME_INTERVAL_SECONDS` configurable por entorno, conservando 30 como
  valor por defecto;
- inserción idempotente de `media_inputs` mediante `ON CONFLICT DO NOTHING`;
- codificación real a JPEG en vez de copiar un PNG con extensión `.jpg`.

- [ ] **Step 2: Run focused tests**

Run: `python3 -m unittest tests.test_vision -v`
Expected: PASS.

Run: `python3 -m unittest tests.test_worker -v`
Expected: PASS when executed in the application container, where OpenCV and
psycopg are installed.

- [ ] **Step 3: Run the complete suite and syntax checks**

```bash
python3 -m unittest discover -v
python3 -m compileall -q app tests
```

Expected: all tests pass in the container and compilation produces no output.

### Task 3: Actualizar handoff y verificar integración disponible

**Files:**
- Modify: `handoff-to-umizumi-3.md`

- [ ] **Step 1: Document the completed contracts**

Indicar que Umizumi 3 recibe frames pendientes, mesas con polígonos y un
coordinador listo para recibir un detector real. Indicar también qué queda
pendiente: modelo YOLO, calibración con capturas Roblox y prueba end-to-end.

- [ ] **Step 2: Verify Docker and API smoke checks**

```bash
docker compose up --build -d
docker compose ps
curl http://localhost:8000/health
curl http://localhost:8000/api/tables/latest
```

Expected: PostgreSQL `healthy`, `web` y `worker` iniciados, health check `ok` y
la API devolviendo JSON. Si la API falla, corregir el mapeo de filas antes de
continuar.

- [ ] **Step 3: Commit the implementation**

```bash
git add app tests handoff-to-umizumi-3.md docs/superpowers/plans
git commit -m "feat: prepare model pipeline contracts"
```
