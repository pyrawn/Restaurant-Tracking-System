# Restaurant Tracker Initial Scaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Crear un scaffold local ejecutable para el pipeline de Restaurant Tracking System con Flask, PostgreSQL, worker, entrada de imágenes y contrato inicial compatible con video.

**Architecture:** Un `web` y un `worker` reutilizan la misma imagen Python; PostgreSQL es el único servicio de datos. El worker leerá `data/inbox/` y el dashboard Flask expondrá una vista y una API mínima. La inferencia completa se integrará después sobre los frames persistidos.

**Tech Stack:** Python 3.12, Flask, psycopg, OpenCV, Ultralytics, PostgreSQL, Docker Compose, HTML/CSS/JavaScript nativo y `unittest`.

---

### Task 1: Crear el contrato mínimo de entrada y estado

**Files:**
- Create: `app/__init__.py`
- Create: `app/media.py`
- Create: `app/domain.py`
- Create: `tests/test_media_and_domain.py`

- [x] **Step 1: Write the failing test**

```python
from unittest import TestCase

from app.domain import table_state
from app.media import media_type


class MediaAndDomainTests(TestCase):
    def test_classifies_images_and_mp4(self):
        self.assertEqual(media_type("capture.PNG"), "image")
        self.assertEqual(media_type("session.mp4"), "video")

    def test_rejects_unknown_media(self):
        with self.assertRaises(ValueError):
            media_type("notes.txt")

    def test_table_state_uses_count_and_confidence(self):
        self.assertEqual(table_state(0, 0.90), "free")
        self.assertEqual(table_state(2, 0.90), "occupied")
        self.assertEqual(table_state(2, 0.40), "review")
```

- [x] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests/test_media_and_domain.py -v`  
Expected: FAIL because `app.media` and `app.domain` do not exist.

- [x] **Step 3: Write minimal implementation**

```python
# app/media.py
from pathlib import Path


def media_type(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png"}:
        return "image"
    if suffix == ".mp4":
        return "video"
    raise ValueError(f"unsupported media type: {suffix or '<none>'}")
```

```python
# app/domain.py
def table_state(people_count: int, confidence: float, threshold: float = 0.5) -> str:
    if people_count < 0:
        raise ValueError("people_count cannot be negative")
    if not 0 <= confidence <= 1:
        raise ValueError("confidence must be between 0 and 1")
    if confidence < threshold:
        return "review"
    return "occupied" if people_count > 0 else "free"
```

- [x] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests/test_media_and_domain.py -v`  
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add app tests
git commit -m "test: add initial media and table contracts"
```

### Task 2: Crear PostgreSQL, schema y datos fijos

**Files:**
- Create: `compose.yaml`
- Create: `Dockerfile`
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `db/schema.sql`
- Create: `db/seed.sql`
- Create: `data/inbox/.gitkeep`
- Create: `data/processed/.gitkeep`
- Create: `data/failed/.gitkeep`

- [x] **Step 1: Define the database schema**

Crear las tablas `media_inputs`, `frames`, `tables`, `table_observations`,
`waiters` y `waiter_assignments`, con claves foráneas, hashes únicos, estado
restringido a `pending|processing|processed|failed` y `people_count >= 0`.
Crear también la vista `latest_table_state` para el dashboard.

- [x] **Step 2: Seed fixed restaurant data**

Insertar cuatro meseros con códigos `waiter_1` a `waiter_4` y referencias de
skin `data/skins/waiter_1.png` a `data/skins/waiter_4.png`. Insertar cuatro
mesas de ejemplo con capacidad 4 y polígonos JSON para que el dashboard tenga
datos iniciales.

- [x] **Step 3: Define the container environment**

Usar un servicio PostgreSQL con volumen persistente y servicios `web` y
`worker` construidos desde el mismo `Dockerfile`. Montar `./data` en ambos
servicios y montar `schema.sql` y `seed.sql` como scripts de inicialización de
PostgreSQL.

- [x] **Step 4: Commit**

```bash
git add compose.yaml Dockerfile requirements.txt .env.example db data
git commit -m "build: initialize postgres and containers"
```

### Task 3: Crear Flask y worker ejecutables

**Files:**
- Create: `app/db.py`
- Create: `app/web.py`
- Create: `app/worker.py`
- Create: `app/templates/dashboard.html`
- Create: `app/static/app.js`
- Create: `app/static/styles.css`

- [x] **Step 1: Add database connection helper**

`app/db.py` expone `get_connection()` y usa `DATABASE_URL`. No agrega ORM;
las consultas serán SQL directo mediante `psycopg`.

- [x] **Step 2: Add web health and dashboard routes**

`app/web.py` debe exponer:

```text
GET /health
GET /
GET /api/tables/latest
```

`/health` responde `{"status": "ok"}`. `/api/tables/latest` consulta la vista
`latest_table_state` y devuelve JSON. La página muestra las mesas y ejecuta
`fetch("/api/tables/latest")` cada 30 segundos.

- [x] **Step 3: Add the worker loop**

`app/worker.py` debe revisar `data/inbox/` cada `INGEST_POLL_SECONDS`, validar
extensiones con `media_type()` y registrar logs en stdout. En este init el
worker solo prepara el contrato de ingestión; la inserción de `media_inputs`,
la extracción de frames y la inferencia serán el siguiente handoff.

- [x] **Step 4: Commit**

```bash
git add app
git commit -m "feat: add flask dashboard and worker entrypoints"
```

### Task 4: Verificar el init y documentar ejecución

**Files:**
- Modify: `README.md`
- Test: `tests/test_media_and_domain.py`

- [x] **Step 1: Run local standard-library tests**

Run: `python3 -m unittest discover -v`  
Expected: PASS.

- [ ] **Step 2: Verify Docker when available**

Docker no está instalado en el entorno de Codex; este paso queda para la
máquina del equipo Umizumi.

Run: `docker compose config`  
Expected: configuración válida.

Run: `docker compose up --build`  
Expected: PostgreSQL queda healthy, Flask escucha en `http://localhost:8000` y
worker inicia sin traceback.

- [x] **Step 3: Document the handoff commands**

README debe incluir:

```bash
docker compose up --build
python3 -m unittest discover -v
```

También debe indicar que las imágenes se colocan en `data/inbox/`, que el
dashboard actualiza cada 30 segundos y que el video MP4 se integrará en el
siguiente handoff usando el mismo contrato de frames.

- [x] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document initial project setup"
```
