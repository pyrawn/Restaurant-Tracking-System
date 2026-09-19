# Code reference

What every function/class in the project does, grouped by file. For the
"why" behind each decision, see `README.md` and the handoffs
(`handoff-*.md`); this is just the map of what each piece does.

> English translation of [`CODE_REFERENCE.md`](CODE_REFERENCE.md). The
> Spanish version is the source of truth; open a PR if they drift apart.

## Ingestion and detection pipeline

### `app/media.py`

| Function | What it does |
| --- | --- |
| `media_type(path)` | Classifies a file as `"image"` or `"video"` by its extension (`.jpg/.jpeg/.png` vs `.mp4`); raises `ValueError` if the extension isn't recognized. |

### `app/domain.py`

| Function | What it does |
| --- | --- |
| `table_state(people_count, confidence, threshold=0.5)` | Returns `"free"`, `"occupied"`, or `"review"` (insufficient confidence) from a people count and a confidence value. Validates ranges (`people_count >= 0`, `0 <= confidence <= 1`). |

### `app/vision.py`

| Function | What it does |
| --- | --- |
| `_point_on_segment(point, start, end)` | Geometry helper: does the point fall exactly on the `start-end` segment? Used to treat a polygon's edge as "inside". |
| `point_in_polygon(point, polygon)` | Classic ray casting: is the point inside a table's polygon? Treats the edge as "inside" via `_point_on_segment`. |
| `build_table_observations(detections, tables, model_version)` | The core of detection↔table association: for each person detection, uses the bottom-center point of its bounding box as an "anchor" (the feet), assigns it to the first table whose polygon contains it, and builds one observation per table (`people_count`, `occupied`, average `confidence`, `model_version`). A table with no detections gets `people_count=0`, `confidence=1.0`. |

### `app/detector.py`

| Function | What it does |
| --- | --- |
| `get_model_path()` | Reads `MODEL_PATH` from the environment (default `/app/models/yolov8s.pt`). |
| `get_confidence_threshold()` | Reads `CONFIDENCE_THRESHOLD` from the environment (default `0.25`). |
| `model_version_from_path(model_path=None)` | Derives the `model_version` string stored on every observation (e.g. `"yolo:yolov8s"`) from the checkpoint's filename. |
| `load_detector(model_path=None, confidence_threshold=None)` | Loads the YOLOv8 model (Ultralytics) and returns a `detect(image_path)` function closed over that model and threshold, filtered to the "person" class (`PERSON_CLASS_ID=0`). Each detection returns `box` (xyxy) and `confidence`. |

### `app/youtube.py`

| Function | What it does |
| --- | --- |
| `resolve_stream_url(video_url)` | Resolves a YouTube URL to the direct video stream URL via `yt-dlp -g -f bestvideo/best` (this camera only publishes separate video-only renditions, hence `bestvideo`). |
| `capture_snapshot(stream_url, out_path)` | Captures a single frame from the stream with `ffmpeg -frames:v 1`. |
| `capture_frames(video_url, count, interval_seconds, output_dir)` | Resolves the stream once and captures `count` snapshots spaced `interval_seconds` apart, named by timestamp. This is what `live_worker.py` calls each cycle. |

### `app/worker.py` — batch ETL (standalone files)

| Function | What it does |
| --- | --- |
| `get_file_hash(path)` | SHA-256 of a file, streamed (doesn't load it all into memory) — the key to ingestion idempotency. |
| `get_frame_interval_seconds()` | Reads `FRAME_INTERVAL_SECONDS` from the environment for video sampling. |
| `process_image(path, media_hash, processed_dir)` | Normalizes an image into a single frame at `processed_dir/<hash>/0.jpg`. |
| `process_video(path, media_hash, processed_dir)` | Extracts frames from a video every `FRAME_INTERVAL_SECONDS`, each saved as `<n>.jpg`. |
| `transform_media(kind, path, media_hash, processed_dir)` | Dispatches to `process_image` or `process_video` based on `kind`. |
| `ingest_path(path, processed_dir)` | Orchestrates one file: classify → hash → check duplicate (`media_input_exists`) → transform → load to the DB (`load_media_and_frames`). Absorbs and logs every kind of failure without stopping the batch; returns a success `bool`. |
| `process_pending_frames(detector, model_version)` | Takes frames in `pending` status, runs the detector, maps detections to tables (`build_table_observations`), and saves the observations. A frame that fails is marked `failed` and doesn't stop the rest. Returns a per-frame summary (used for logging). |
| `discover_media(input_dir)` | Lists the files in `data/inbox/` to process in this run. |
| `main()` | Entry point for the one-shot ETL: ingests everything in `INPUT_DIR`, runs the detector on pending frames, exits. Meant to run once per invocation (`docker compose run --rm worker python -m app.worker`), not in a loop. |

### `app/live_worker.py` — continuous capture from YouTube

| Function | What it does |
| --- | --- |
| `get_env_int(name, default)` | Helper to read positive integers from the environment, with validation. |
| `run_cycle(video_url, frame_count, capture_interval, input_dir, processed_dir, detector, model_version)` | One full cycle: captures frames from the stream (`capture_frames`), ingests them (`ingest_path`), and runs pending inference (`process_pending_frames`); logs a per-frame summary. |
| `main()` | The `live` service's loop: every cycle is wrapped in `try/except` so a one-off failure (an `ffmpeg` timeout, a dropped stream) doesn't take the service down — it's logged and retried on the next `LIVE_POLL_INTERVAL_SECONDS`. `LIVE_MODE=once` runs a single cycle and exits; `LIVE_MODE=loop` is the real continuous mode. |

## Data access — `app/db.py`

Every function opens its own connection (`get_connection()`, via
`DATABASE_URL`) and closes it when done; there's no pool or shared
connection across calls.

| Function/Class | What it does |
| --- | --- |
| `_rows_to_dicts(rows, columns)` | Converts cursor rows (tuples) to `dict`, serializing `date`/`datetime` to ISO. Used by nearly every read function. |
| `fetch_latest_table_state()` | Reads the `latest_table_state` view — the current per-table snapshot. The only endpoint the dashboard needs for "right now" state. |
| `fetch_observation_history(hours=3)` | History of `table_observations` for the last `hours` hours, for the trend chart. |
| `media_input_exists(media_hash)` | Was this file already ingested? (hash-based idempotency). |
| `load_media_and_frames(media_type, source_path, media_hash, frames, status="processed", error_message=None)` | Inserts `media_inputs` + its `frames` in a transaction; `ON CONFLICT (media_hash) DO NOTHING` — if it already existed, returns `None` without touching anything. |
| `fetch_pending_frames()` | Frames in `pending` status, ready for inference. |
| `fetch_tables()` | The 5 tables with their polygon (deserialized from JSONB to a list of points). |
| `save_frame_observations(frame_id, observations)` | Inserts/updates a frame's observations (`ON CONFLICT (frame_id, table_id) DO UPDATE`) and marks the frame `processed`. |
| `mark_frame_failed(frame_id, error_message)` | Marks a frame `failed` when inference blows up. |
| `ScheduleConflict` | Custom exception: a shift would overlap another one for the same waiter, or for a table already assigned. |
| `verify_user(username, password)` | Login: looks up the user and checks the hash (`werkzeug.security.check_password_hash`). Returns `{id, username}` or `None`. |
| `fetch_waiters(active_only=False)` | List of waiters. |
| `create_waiter(name)` | Adds a new waiter. |
| `fetch_shifts(start, end)` | Shifts that **overlap** `[start, end]` (for rendering the calendar, this includes ones crossing the window's edge), with the waiter's name and assigned tables already aggregated (`array_agg`). |
| `_has_waiter_overlap(cursor, waiter_id, starts_at, ends_at, exclude_shift_id=None)` | Does that waiter already have another shift in that range? |
| `_has_table_overlap(cursor, table_ids, starts_at, ends_at, exclude_shift_id=None)` | Is any of those tables already assigned to another shift in that range? |
| `_replace_shift_tables(cursor, shift_id, table_ids)` | Deletes and re-inserts a shift's `waiter_shift_tables` rows (used on create/edit). |
| `create_shift(waiter_id, starts_at, ends_at, table_ids)` | Creates a shift after validating both kinds of overlap; raises `ScheduleConflict` on a collision. |
| `update_shift(shift_id, waiter_id, starts_at, ends_at, table_ids)` | Same as create, but excluding the shift itself from the overlap check. |
| `delete_shift(shift_id)` | Deletes a shift (`waiter_shift_tables` cascades via FK). |
| `_episode_people_served(observations)` | The project's trickiest calculation: given a time-ordered stream of `(table_id, people_count, occupied)`, detects contiguous occupancy runs per table and sums the peak of each run — so the same seated party isn't counted once per detection frame (~every 30-40s). |
| `fetch_waiter_stats(start, end)` | For every shift overlapping `[start, end]`, fetches the observations of its assigned tables in that window, and aggregates per waiter: shifts, hours worked, average occupancy, people served (via `_episode_people_served`). |

## Web / API — `app/web.py`

| Function | What it does |
| --- | --- |
| `login_required(view)` | Decorator: with no session, redirects to `/login` (page routes) or returns `401` JSON (`/api/*` routes). |
| `_parse_datetime(value)` | Parses an ISO string to `datetime`; assumes UTC if it carries no timezone. |
| `health()` | `GET /health` — tests the DB connection, no login required. |
| `login()` | `GET/POST /login` — the form and credential check (`verify_user`); stores `user_id`/`username` in the session. |
| `logout()` | `GET /logout` — clears the session. |
| `dashboard()` | `GET /` — the main page (KPIs + charts). |
| `latest_tables()` | `GET /api/tables/latest`. |
| `tables_history()` | `GET /api/tables/history?hours=` (clamped 1–24). |
| `schedule()` | `GET /schedule` — the calendar page. |
| `list_waiters()` / `add_waiter()` | `GET/POST /api/waiters`. |
| `list_shift_tables()` | `GET /api/shift-tables` — the tables available to assign (for the modal's checkboxes). |
| `list_shifts()` | `GET /api/shifts?start=&end=`. |
| `_shift_payload(body)` | Extracts and casts `waiter_id`/`starts_at`/`ends_at`/`table_ids` from a request's JSON; shares validation between create, edit, and the bulk endpoint. |
| `add_shift()` / `edit_shift()` / `remove_shift()` | `POST/PUT /api/shifts`, `DELETE /api/shifts/<id>` — `ScheduleConflict` maps to `409`. |
| `add_shifts_bulk()` | `POST /api/shifts/bulk` — creates several shifts at once, each validated independently; responds `207` with `created`/`conflicts` per index instead of aborting the whole batch on a single collision. This is what the calendar's repeat patterns use. |
| `waiter_stats_page()` | `GET /waiters/stats` — the stats page. |
| `waiter_stats_api()` | `GET /api/waiters/stats?start=&end=` — defaults to the last 7 days. |

## Frontend

### `app/static/app.js` — dashboard (`/`)

| Function | What it does |
| --- | --- |
| `toUtcInputValue` / `fromUtcInputValue` | Converts between a `Date` and an `<input type="datetime-local">` value, always in UTC (not the browser's local timezone). |
| `renderTables(tables)` | Renders the per-table detail cards. |
| `renderKpis(tables)` | Computes and renders the KPI row (people now, % occupancy, capacity used, busiest table, average confidence) from the current snapshot. |
| `renderCurrentChart(tables)` | Bar chart of people vs. capacity per table (Chart.js); reuses the existing chart instance on later refreshes instead of recreating it. |
| `renderOccupancyChart(tables)` | Doughnut of occupied vs. free tables. |
| `renderTrendChart(history)` | Multi-table line chart of occupancy history; groups observations by timestamp to align the series. |
| `fetchJson(url)` | `fetch` with uniform error handling. |
| `refresh()` | Runs one refresh cycle: fetches `latest`+`history`, redraws everything. Called on load and every `REFRESH_MS` (30s). |

### `app/static/schedule.js` — calendar (`/schedule`)

| Function | What it does |
| --- | --- |
| `loadWaiters(selectedId)` / `loadTables()` | Populate the modal's waiter `<select>` and table checkboxes. |
| `renderRepeatWeekdays()` / `getCheckedWeekdays()` / `resetRepeatFields()` | Manage the Mon–Sun checkboxes for the repeat pattern. |
| `setCheckedTables` / `getCheckedTables` | Read/write which tables are checked in the modal. |
| `openModal({...})` / `closeModal()` | Open the modal in create or edit mode (hides the repeat section when editing); close and reset the form. |
| `computeRepeatOccurrences(baseStart, baseEnd, weekdays, untilValue)` | Given a base shift and a weekday pattern + end date, computes the extra dates to create (same time and duration, stepping by 24h to avoid timezone drift). |
| `saveShift(event)` | Modal submit: creates or edits the shift; on create, if a repeat pattern is checked, asks for confirmation and creates the repeats via `/api/shifts/bulk`. |
| `deleteShift()` | Deletes the shift currently open in the modal. |
| `addWaiter()` | Quick waiter creation from the modal (`prompt()` + `POST /api/waiters`). |
| `updateShiftTimes(info)` | FullCalendar's `eventDrop`/`eventResize` handler: dragging or resizing a shift updates its times via `PUT`; reverts the visual change if the backend rejects it (conflict). |
| `duplicateWeek()` | Duplicates to the next week the shifts **fully contained** in the calendar's visible week (ones crossing the edge are skipped, see `README.md`); confirms with the user before creating. |
| `init()` | Instantiates FullCalendar (week view, UTC, `select`/`eventClick`/`eventDrop`/`eventResize`), loads waiters and tables, wires up button listeners. |

### `app/static/waiter_stats.js` — stats (`/waiters/stats`)

| Function | What it does |
| --- | --- |
| `defaultRange()` | Initial date-picker range: the last 7 days. |
| `renderTable(stats)` | Renders the "Detail per waiter" table. |
| `renderCharts(stats)` | Bar chart of people served and bar chart of average occupancy, one per waiter. |
| `loadStats()` | Reads the date range from the inputs, requests `/api/waiters/stats`, and redraws the table + charts. Called on load and when clicking "Apply". |
