# Restaurant Tracking System

Umizumi pipeline that tracks table occupancy in a restaurant from video (a
live camera/webcam) or standalone images, with an operational dashboard:
real-time state, a waiter shift calendar, and a per-waiter stats report.

> This is an English translation of [`README.md`](README.md). The Spanish
> version is the source of truth; open a PR if they drift apart.

## Stack

- Python 3.12
- Flask + plain HTML/CSS/JavaScript (no frontend framework), Chart.js and
  FullCalendar loaded from a CDN
- PostgreSQL
- OpenCV for ingestion and frame extraction, `yt-dlp`/`ffmpeg` to capture a
  YouTube stream as a live source
- Ultralytics YOLOv8 (`yolov8s` detector, "person" class) for inference
- Docker Compose

## Getting started

Requires Docker and Docker Compose:

```bash
cp .env.example .env
# edit .env: set LIVE_STREAM_URL to the YouTube video/live URL to use

docker compose up -d db web live
```

Dashboard: <http://localhost:8000> (requires login — see [Login](#login) below)

Health check: <http://localhost:8000/health> (no login)

Tests inside a temporary app container:

```bash
docker compose run --rm worker python -m unittest discover -v
```

```text
----------------------------------------------------------------------
Ran 70 tests in 0.155s

OK
```

## Data input

Two sources feed the same `frames` / `table_observations` tables:

1. **Standalone files**: drop `.jpg`, `.jpeg`, `.png` images or `.mp4`
   videos into `data/inbox/` and run `docker compose run --rm worker python
   -m app.worker`. The worker is a batch ETL script: it processes whatever
   is currently in the folder once, computes SHA-256, transforms each
   medium, and only then loads its metadata and frames into PostgreSQL.
   Images produce one frame; videos produce a frame every
   `FRAME_INTERVAL_SECONDS`.
2. **Live camera**: the `live` service (`app/live_worker.py`) resolves a
   YouTube stream with `yt-dlp`, captures snapshots with `ffmpeg` every
   `LIVE_CAPTURE_INTERVAL_SECONDS`, and repeats the cycle every
   `LIVE_POLL_INTERVAL_SECONDS` (`LIVE_MODE=loop`, meant to run
   indefinitely). Each capture runs through the same
   ingest+detect+load pipeline as standalone files.

In both cases, detection runs with YOLOv8s on the "person" class,
`app/vision.py` maps each detection to a fixed table polygon (`db/seed.sql`,
calibrated against the real camera), and the result (`people_count`,
`occupied`, `confidence`) is stored per table and per frame in
`table_observations`.

Real example of a `live` service cycle (note: 0 detections here because the
webcam used as the source was outside its broadcast hours at capture time —
documented, correct behavior, not a bug):

```text
$ docker compose run --rm -e LIVE_MODE=once -e LIVE_FRAME_COUNT=1 live
2026-09-18 23:36:48,991 INFO starting live capture: url=https://www.youtube.com/live/2wqpy036z24 mode=once frames=1 capture_interval=30s poll_interval=30s
2026-09-18 23:36:54,280 INFO captured live frame 1/1: /app/data/inbox/live_20260918T233651742101.jpg
2026-09-18 23:36:54,369 INFO loaded image input with 1 frame(s): live_20260918T233651742101.jpg
2026-09-18 23:36:57,341 INFO frame 699 (/app/data/processed/b0f492e.../0.jpg): 0 person detection(s) -> {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
2026-09-18 23:36:57,341 INFO live capture finished
```

With the camera active during real hours, a cycle looks like this
(captured in an earlier session):

```text
live-1  | 2026-09-09 21:33:44,433 INFO captured live frame 1/1: /app/data/inbox/live_20260909T213339514833.jpg
live-1  | 2026-09-09 21:33:44,822 INFO loaded image input with 1 frame(s): live_20260909T213339514833.jpg
live-1  | 2026-09-09 21:33:49,554 INFO frame 299 (/app/data/processed/9d07994f.../0.jpg): 14 person detection(s) -> {1: 4, 2: 2, 3: 0, 4: 1, 5: 4}
```

To follow the live camera's log stream:

```bash
docker compose logs -f live
```

## Operational dashboard

The whole site (except `/health`) sits behind a session login.

### Login

```text
username: victor
password: 123
```

![Login](docs/screenshots/01-login.png)

The session uses Flask's signed cookie (`SECRET_KEY`); passwords are stored
hashed with `werkzeug.security` (scrypt), never in plain text.

### Table state (`/`)

Aggregate KPIs (people now, occupied tables, % capacity, busiest table,
average model confidence), a bar chart of people per table, an occupancy
doughnut, an occupancy trend per table over the last few hours, and the
per-table detail grid. Refreshes every 30 seconds via polling (no
WebSockets/SSE, by design).

![Dashboard](docs/screenshots/02-dashboard.png)

### Shift calendar (`/schedule`)

A waiter is manually assigned to one or more tables for a time window
(`waiter_shifts` + `waiter_shift_tables`). This is a business layer separate
from vision — there's no waiter detection in the video, waiter↔table
attribution is always manual. Schedules are in UTC.

![Calendar](docs/screenshots/03-schedule-calendar.png)

- **Create a shift**: dragging on the calendar opens the modal with the
  time range pre-filled.
- **Edit/delete**: click an existing shift.
- **Move/extend**: drag or resize an existing shift.
- **Conflict validation**: a waiter can't have two overlapping shifts, and
  a table can't be assigned to two waiters at the same time — rejected with
  a clear message in the modal.

![New shift with repeat pattern](docs/screenshots/04-schedule-new-shift-modal.png)

**Patterns to speed up assignment** (shifts are still individual dated rows
under the hood — this is just a faster way to create them):

- **Repeat on weekdays**: when creating a shift, checking days (Mon–Sun)
  plus an end date automatically generates an identical shift (same
  waiter, same tables, same time) on every matching date. Each occurrence
  is validated independently — if one collides with an existing shift,
  that date is skipped and the rest are still created.
- **Duplicate week**: the "Duplicate visible week → next week" button takes
  every shift visible in the calendar's current week and recreates it 7
  days later, with the same per-shift conflict validation.

Verified live: repeating Mon/Wed/Fri created 4 additional shifts with no
conflict; duplicating a week that already had copies further ahead
correctly created 5 and skipped 2 due to conflicts, showing the summary on
screen.

### Waiter stats (`/waiters/stats`)

Date range picker (UTC) + charts and a table per waiter: shifts worked,
hours worked, average occupancy, and people served.

![Waiter stats](docs/screenshots/05-waiter-stats.png)

**How the metrics are computed** (important, because `table_observations`
are snapshots every ~30-40s, not "service" events):

- **Average occupancy**: average `people_count` across the shift's
  assigned tables, during the shift's window.
- **People served**: NOT the raw sum of `people_count` per frame (that
  would multiply the same party sitting for an hour by ~90). Occupancy
  episodes are detected — contiguous runs where a table goes from free to
  occupied and back to free — and the peak headcount of each episode is
  summed. Implemented in `_episode_people_served()` (`app/db.py`), with
  unit tests covering closed episodes, episodes still open at the end of
  the window, and windows with no occupancy.

Real example via the API (same range as the screenshot above):

```text
$ curl -s -b cookies.txt "http://localhost:8000/api/waiters/stats?start=2026-09-09T00:00:00Z&end=2026-09-10T03:00:00Z" | python3 -m json.tool
[
    {
        "avg_occupancy": 0.55,
        "hours_worked": 5.8,
        "people_served": 27,
        "shifts": 2,
        "waiter_id": 2,
        "waiter_name": "Ana Torres"
    },
    {
        "avg_occupancy": 1.0,
        "hours_worked": 9.0,
        "people_served": 41,
        "shifts": 2,
        "waiter_id": 1,
        "waiter_name": "Carlos Mendoza"
    }
]
```

## Database

```text
$ docker compose exec db psql -U restaurant -d restaurant_tracker -c "\dt"
                 List of relations
 Schema |        Name         | Type  |   Owner
--------+---------------------+-------+------------
 public | frames              | table | restaurant
 public | media_inputs        | table | restaurant
 public | table_observations  | table | restaurant
 public | tables              | table | restaurant
 public | users               | table | restaurant
 public | waiter_shift_tables | table | restaurant
 public | waiter_shifts       | table | restaurant
 public | waiters             | table | restaurant
(8 rows)
```

`users`, `waiters`, `waiter_shifts` and `waiter_shift_tables` are owned
exclusively by the dashboard (Umizumi 4) — they don't interfere with the
read/write contract of `table_observations`/`frames`/`media_inputs`, which
stays owned by ingestion (Umizumi 2) and inference (Umizumi 3). The
dashboard only reads those three tables, never writes to them.

Example of already-assigned shifts (sample data, `db/seed.sql`):

```text
$ docker compose exec db psql -U restaurant -d restaurant_tracker -c "
SELECT w.name AS waiter, s.starts_at, s.ends_at, string_agg(t.name, ', ' ORDER BY t.name) AS tables
FROM waiter_shifts s
JOIN waiters w ON w.id = s.waiter_id
JOIN waiter_shift_tables wst ON wst.shift_id = s.id
JOIN tables t ON t.id = wst.table_id
WHERE s.starts_at >= '2026-09-09' AND s.starts_at < '2026-09-10'
GROUP BY w.name, s.id, s.starts_at, s.ends_at
ORDER BY s.starts_at;"

     waiter      |       starts_at        |        ends_at         |      tables
-----------------+------------------------+------------------------+------------------
 Carlos Mendoza | 2026-09-09 07:00:00+00 | 2026-09-09 11:30:00+00 | Table 1, Table 2
 Ana Torres     | 2026-09-09 11:30:00+00 | 2026-09-09 16:00:00+00 | Table 3, Table 4
 Luis Ramirez   | 2026-09-09 16:00:00+00 | 2026-09-09 20:30:00+00 | Table 1, Table 5
 Carlos Mendoza | 2026-09-09 20:30:00+00 | 2026-09-10 01:00:00+00 | Table 5
 Sofia Herrera  | 2026-09-09 20:30:00+00 | 2026-09-10 01:00:00+00 | Table 2, Table 3
(5 rows)
```

## API

| Route | Method | Description |
| --- | --- | --- |
| `/health` | GET | DB connection status. No login. |
| `/login`, `/logout` | GET/POST, GET | Admin session. |
| `/api/tables/latest` | GET | Current per-table snapshot (`latest_table_state`). |
| `/api/tables/history` | GET | Observation history (`?hours=`, 1–24). |
| `/api/waiters` | GET, POST | List / create waiters. |
| `/api/shift-tables` | GET | Tables available to assign. |
| `/api/shifts` | GET, POST | Shifts in a range (`?start=&end=`) / create one. |
| `/api/shifts/<id>` | PUT, DELETE | Edit / delete a shift. |
| `/api/shifts/bulk` | POST | Create several shifts at once (used by the repeat patterns); responds `207` with `created`/`conflicts` per index, without aborting the rest on a single conflict. |
| `/api/waiters/stats` | GET | Aggregate stats per waiter (`?start=&end=`). |

All `/api/*` routes (except `/health`) respond `401` in JSON when there's
no session, instead of redirecting — meant to be consumed via `fetch()`
from the frontend.

Reference for what every function/class in the project does (backend and
frontend): [`docs/CODE_REFERENCE.en.md`](docs/CODE_REFERENCE.en.md).

## Umizumi handoffs

1. **Umizumi 1**: containers, schema, and fixture data.
2. **Umizumi 2**: ingestion and normalization to frames.
3. **Umizumi 3**: real YOLOv8 detector, second input source (live YouTube
   camera), loading to PostgreSQL. Details and known limitations in
   `handoff-to-umizumi-4.md`.
4. **Umizumi 4**: operational dashboard — real-time KPIs and charts,
   login, shift calendar with repeat patterns, per-waiter stats.

The original architecture details are in
`docs/superpowers/specs/2026-09-07-restaurant-tracker-design.md` (note:
that document is the initial MVP design — some sections, like "no video
detection" or "no waiter identification", were superseded by later
decisions from the project owner, documented in the handoffs).

## Project constraints

- No Streamlit, Kafka, Airflow, Redis, Celery, or a data lake.
- Dashboard on polling (30s); no WebSockets/SSE.
- The dashboard (Umizumi 4) doesn't write to `table_observations`,
  `frames`, or `media_inputs` — those tables stay owned by ingestion and
  inference.
- No waiter identification by video: waiter↔table assignment is always
  manual, via the calendar.
