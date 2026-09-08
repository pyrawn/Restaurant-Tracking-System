# Handoff — Umizumi 2 → Umizumi 3

Date: 2026-09-07
Project: Restaurant Tracking System
Team: Umizumi

## Handoff objective

Implement the real model inference, transform detections into table-level
observations, and load those observations into PostgreSQL.

The ingestion and frame-normalization contracts are already in place. The next
person should focus on connecting a lightweight pretrained detector, such as a
YOLO nano checkpoint, without changing the database contract or the dashboard.

## Current state

Umizumi 2 has completed the image-independent pipeline work:

- The `worker` reads `.jpg`, `.jpeg`, `.png`, and `.mp4` files from
  `data/inbox/`.
- Each input is identified with SHA-256 and inserted into `media_inputs` only
  once.
- Images are validated with OpenCV and normalized to
  `data/processed/<media_hash>/0.jpg`.
- Videos are sampled in batch at `FRAME_INTERVAL_SECONDS` and normalized to
  numbered JPEG frames.
- Every normalized frame is inserted into `frames` with `status = 'pending'`.
- The worker receives `DATABASE_URL`, `INPUT_DIR`, `PROCESSED_DIR`,
  `INGEST_POLL_SECONDS`, and `FRAME_INTERVAL_SECONDS` through Compose.
- `app/vision.py` assigns detections to tables using the bottom-center point of
  each bounding box and returns one observation per configured table.
- `app/db.py` provides pending-frame queries, table queries, idempotent media
  insertion, and transactional observation loading.
- `process_pending_frames(detector, model_version)` is ready to receive a
  detector callable. The real detector and runtime wiring are still pending.
- The `/api/tables/latest` row mapping bug was fixed.
- The base image includes Flask, psycopg, and OpenCV. Ultralytics is not
  installed yet because it brings heavy ML dependencies and was not needed for
  ingestion.
- A clean implementation commit is `e6cdd4f`.

## Available input

There is currently one image frame in:

```text
data/inbox/WhatsApp Image 2026-09-07 at 7.32.40 PM.jpeg
```

Use this file to iterate on the detector and end-to-end flow. The file is a
local input fixture and may not be included in a Git clone unless it is shared
or committed separately. There is no labeled dataset yet.

## Scope for Umizumi 3

1. Add `ultralytics` and any strictly necessary model dependencies.
2. Create a small detector adapter that receives an `image_path` and returns
   person detections in this shape:

   ```python
   [{"box": [x1, y1, x2, y2], "confidence": 0.87}]
   ```

3. Connect that adapter to `process_pending_frames(detector, model_version)`.
4. Run the pipeline against the one available Roblox frame.
5. Inspect the resulting `table_observations` and tune the confidence threshold
   or table polygons only if the frame demonstrates a real need.

The detector adapter should filter for people before calling
`build_table_observations()`. Do not duplicate the point-in-polygon logic.

## Input contract

Pending frames are queried from PostgreSQL:

```sql
SELECT id, image_path, media_input_id, frame_index, captured_at
FROM frames
WHERE status = 'pending'
ORDER BY id;
```

The fixed table polygons are queried with:

```sql
SELECT id, name, capacity, polygon
FROM tables
ORDER BY id;
```

The detector receives the `image_path` stored in each frame. It must return
only person detections; table assignment is handled by `app/vision.py`.

## Output contract

For every configured table and processed frame, persist one row in
`table_observations`:

```text
frame_id           = <processed frame id>
table_id           = <configured table id>
people_count       = <detections assigned to the table>
occupied           = <true when people_count > 0>
confidence         = <value between 0 and 1>
detected_waiter_id = <waiter id when implemented, otherwise NULL>
model_version      = <fixed or configured model version>
```

After all table observations for a frame are written successfully, the frame
must become:

```text
status = 'processed'
```

If inference or image loading fails, mark the frame as `failed`. The existing
`save_frame_observations()` function writes all observations and the processed
status in one transaction.

## Files to use

- `app/worker.py`: connect the real detector and call
  `process_pending_frames()`.
- `app/vision.py`: reuse `build_table_observations()` and
  `point_in_polygon()`.
- `app/db.py`: reuse `fetch_pending_frames()`, `fetch_tables()`,
  `save_frame_observations()`, and `mark_frame_failed()`.
- `requirements.txt`: add Ultralytics only when implementing inference.
- `compose.yaml`: keep the worker environment and shared `data` volume
  consistent.
- `db/schema.sql`: treat `frames` and `table_observations` as the interface;
  do not change them without coordinating with Umizumi 4.

## Constraints

- Do not use Streamlit, Kafka, Airflow, Redis, Celery, a data lake, WebSockets,
  or another service.
- Do not modify Flask or the dashboard; that belongs to Umizumi 4.
- Waiters and skins remain fixed; there is no waiter CRUD.
- Do not train a neural network from scratch.
- Keep the inference path batch-based and simple enough for a university MVP.
- If the one frame is insufficient to validate accuracy, document the limitation
  instead of claiming a production-quality metric.

## Acceptance criteria

- [ ] The detector adapter loads a pretrained model and returns person
  detections in the documented shape.
- [ ] Only frames with `status = 'pending'` are processed.
- [ ] The bottom-center point of each detection determines its table.
- [ ] A table with no assigned detections gets `people_count = 0` and
  `occupied = false`.
- [ ] Exactly one observation is written per configured table and frame.
- [ ] Observation writes and the frame status update are atomic.
- [ ] Successful frames become `processed`; failed frames become `failed`.
- [ ] Reprocessing does not create duplicate observations.
- [ ] `latest_table_state` exposes the generated observations.
- [ ] The available Roblox frame is processed successfully end to end.

## Minimum tests

Keep the existing mock-based tests and add or complete tests for:

- positive person detection assigned to the expected table;
- no detections producing a free table;
- detections outside all polygons being ignored;
- pending frames being processed while processed/failed frames are skipped;
- inference failure marking the frame as `failed`;
- duplicate processing respecting the `(frame_id, table_id)` constraint;
- the real available frame producing database rows.

Run the dependency-aware suite inside the application container:

```bash
docker compose up --build -d
docker compose exec worker python -m unittest discover -v
```

## Manual verification

```bash
docker compose logs -f worker
curl http://localhost:8000/health
curl http://localhost:8000/api/tables/latest
```

Inspect PostgreSQL after processing the input frame:

```bash
docker compose exec db psql -U restaurant -d restaurant_tracker -c \
  "SELECT id, status, source_path FROM media_inputs ORDER BY id;"

docker compose exec db psql -U restaurant -d restaurant_tracker -c \
  "SELECT frame_id, table_id, people_count, occupied, confidence, model_version FROM table_observations ORDER BY frame_id, table_id;"
```

## Handoff to Umizumi 4

Deliver:

- modified files and commit hash;
- model name/version and confidence threshold;
- test output;
- proof that `table_observations` and `latest_table_state` contain data;
- known limitations from using a single Roblox frame.

Umizumi 4 can then connect the existing Flask API and 30-second dashboard
polling to the populated `latest_table_state` view.
