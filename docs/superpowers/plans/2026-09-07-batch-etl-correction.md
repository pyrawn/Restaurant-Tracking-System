# Batch ETL Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert media ingestion from load-before-transform behavior into a one-shot ETL batch that transforms frames first and loads only successful artifacts into PostgreSQL.

**Architecture:** `app/worker.py` will discover inputs, transform them into normalized JPEG artifacts, and then call one transactional loader. A failed transformation may load only a failed `media_inputs` record for traceability, but no frame row is loaded. The model stage remains separate and consumes `frames.status = 'pending'`.

**Tech Stack:** Python 3.12, OpenCV, PostgreSQL/psycopg, `unittest`, and existing Docker Compose services.

---

### Task 1: Define ETL ordering and one-shot behavior with tests

**Files:**
- Modify: `tests/test_worker.py`

- [ ] **Step 1: Write failing tests**

Cover:

- transformation runs before the database loader;
- a failed transformation loads no frame and records a failed media input;
- the worker processes the inbox once and exits instead of sleeping forever;
- image/video transformation returns frame artifacts without writing to the DB.

- [ ] **Step 2: Run the focused tests to verify they fail**

Run inside the application container:

```bash
docker compose exec worker python -m unittest tests.test_worker -v
```

Expected: FAIL because the current worker loads `media_inputs` before
transformation and loops continuously.

### Task 2: Implement the ETL boundary

**Files:**
- Modify: `app/db.py`
- Modify: `app/worker.py`
- Modify: `compose.yaml`

- [ ] **Step 1: Transform before loading**

Make image/video functions return normalized frame artifacts containing
`frame_index`, `offset_ms`, `image_path`, and `captured_at`. They must not call
PostgreSQL.

- [ ] **Step 2: Add one transactional loader**

Insert the media row and all frame rows in one transaction after transformation
has succeeded. Use `ON CONFLICT (media_hash) DO NOTHING` for idempotency. On a
transformation failure, insert only a `failed` media row with the error message.

- [ ] **Step 3: Make the worker one-shot**

Process the current contents of `data/inbox/` once and exit. Keep the existing
30-second dashboard polling; remove ingestion sleep from the worker runtime.

- [ ] **Step 4: Keep configuration explicit**

Pass `FRAME_INTERVAL_SECONDS` to the worker through Compose and keep 30 seconds
as the default.

### Task 3: Update documentation and verify

**Files:**
- Modify: `README.md`
- Modify: `handoff.md`
- Modify: `handoff-to-umizumi-3.md`

- [ ] **Step 1: Document the ETL sequence**

Explain that the worker is run as a batch script, normalized frames are created
before database loading, and Umizumi 3 consumes the resulting pending frames.

- [ ] **Step 2: Run verification**

```bash
docker compose up --build -d db
docker compose run --rm worker python -m unittest discover -v
docker compose run --rm worker python -m app.worker
```

Expected: tests pass, the script exits after processing the inbox, and a
successful input produces a `processed` media row plus `pending` frame rows.

- [ ] **Step 3: Commit**

```bash
git add app tests compose.yaml README.md handoff.md handoff-to-umizumi-3.md docs/superpowers/plans
git commit -m "refactor: make media ingestion batch ETL"
```
