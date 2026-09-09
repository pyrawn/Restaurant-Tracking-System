# Handoff — Umizumi 3 → Umizumi 4

Date: 2026-09-09
Project: Restaurant Tracking System
Team: Umizumi

## Handoff objective

Umizumi 3 connected a real detector to the pipeline and, at the project
owner's request, added a second input source: a live YouTube stream (a
public webcam), in addition to the file-drop `data/inbox/` flow from
Umizumi 2. Detections are transformed into per-table observations and
**loaded into PostgreSQL by Umizumi 3 itself** — this was confirmed
explicitly with the project owner, since it matches the original stage
split in `README.md` ("Umizumi 3: modelo, transformación y carga") and the
existing `table_observations` / `latest_table_state` schema. Umizumi 4 is
read-only: it should not need to write to the database, only query it.

Umizumi 4's job is the part that's still genuinely open: the Flask API and
dashboard already exist as scaffolding (from Umizumi 1) and were verified
working against real data during this handoff, but nothing has tuned them
for continuous/live operation, and there are two concrete data-quality gaps
(below) that affect what the dashboard will actually show.

## Current state

The implementation commits for this handoff span `7c3cac8`..`783d443`
(see git log on this branch for the full sequence — waiter removal,
threshold tuning, table calibration, and the model swap all landed as
separate commits after live testing surfaced each issue).

- `app/detector.py`: loads a YOLOv8-small checkpoint (Ultralytics),
  filters detections to the COCO "person" class, respects `MODEL_PATH`
  and `CONFIDENCE_THRESHOLD` env vars (defaults `/app/models/yolov8s.pt`,
  `0.25`). The checkpoint is baked into the Docker image at build time.
  Started as yolov8n at threshold 0.5 — both were changed after live
  testing (see "Verification performed" below) showed real detections on
  this camera landing at low confidence and yolov8n undercounting people
  in dense clusters compared to yolov8s.
- `app/worker.py`: `main()` now ingests `data/inbox/` **and** runs
  `process_pending_frames()` with the real detector in the same one-shot
  pass. `process_pending_frames()` now returns a summary list
  (`frame_id`, `image_path`, `person_detections`, `observations`) instead
  of `None`, for logging/reporting; existing callers are unaffected.
- `app/youtube.py`: resolves a YouTube URL to a direct stream URL via
  `yt-dlp` (`-f bestvideo/best`; this specific stream only publishes
  separate video-only/audio-only HLS renditions, no muxed format) and
  grabs single-frame snapshots via `ffmpeg`.
- `app/live_worker.py`: new entrypoint. Captures `LIVE_FRAME_COUNT` frames
  from `LIVE_STREAM_URL` spaced `LIVE_CAPTURE_INTERVAL_SECONDS` apart,
  ingests them through the existing `ingest_path()`, runs detection, logs a
  per-frame summary (detections + per-table counts). `LIVE_MODE=once` runs
  a single cycle and exits (used for the confirmation test below);
  `LIVE_MODE=loop` repeats indefinitely with `LIVE_POLL_INTERVAL_SECONDS`
  between cycles — this is the continuous mode for an always-on laptop run.
- `compose.yaml`: new `live` service (`restart: unless-stopped`,
  `LIVE_MODE=loop`, `LIVE_FRAME_COUNT=1` by default so a full cycle stays
  close to the dashboard's 30s poll interval). `worker` and `live` both
  take `MODEL_PATH`/`CONFIDENCE_THRESHOLD`.
- `Dockerfile`: installs `ffmpeg`; installs CPU-only PyTorch explicitly
  from `download.pytorch.org/whl/cpu` (the default PyPI `torch` wheel pulls
  ~4GB of CUDA runtime libraries that are useless on a laptop with no GPU —
  worth knowing if you touch this layer); copies `tests/` into the image
  (previously missing, so `docker compose run --rm worker python -m
  unittest discover -v` — the command documented in `README.md` and both
  prior handoffs — silently found and ran 0 tests; fixed as part of this
  handoff since it blocked verifying this stage's own tests).
- `requirements.txt` / `.env.example`: added `ultralytics`, `yt-dlp`, and
  the `LIVE_*` env vars.
- Tests: `tests/test_detector.py`, `tests/test_youtube.py`,
  `tests/test_live_worker.py` (new), `tests/test_worker.py` (updated for
  the detector wiring). All mock the heavy dependencies (Ultralytics,
  subprocess/yt-dlp/ffmpeg) — no network or GPU needed to run them.

## Verification performed

All of this was run for real, inside Docker, not just unit-tested:

```text
docker compose build
docker compose run --rm worker python -m unittest discover -v
  -> Ran 30 tests in 0.125s, OK
```

**Live capture test** (`docker compose run --rm -e LIVE_MODE=once live`,
against `https://www.youtube.com/live/2wqpy036z24`, a public beach-bar
webcam used as a stand-in live source): captured 5 frames end to end
(resolve stream → snapshot → ingest → transform → load → detect → load
observations). All 5 returned 0 person detections — **correctly**, because
the webcam was outside its posted operating hours at test time and was
showing a static "BAR & WEBCAM HOURS" placeholder card instead of live
footage, not a pipeline failure. See the frame at
`data/processed/<hash>/0.jpg` from that run if you re-derive it.

**Confidence threshold and polygon calibration** (done live, after the
initial handoff, once the project owner ran the continuous `live` service
during real operating hours): raw detections on this camera were landing
around 0.24-0.38 confidence, so the default `CONFIDENCE_THRESHOLD=0.5` was
silently dropping every real detection. Lowered to `0.25`; confirmed frames
went from 0 to 2-3 detections. Table polygons were then calibrated against
a real captured frame (see the 5 tables above) and confirmed correct: e.g.
frame 76 recorded `people_count=2` at `Left Table`, frame 77 recorded
`people_count=1` at both `Left Table` and `Middle Bar Table`, frame 78/80
recorded `people_count=1` at `Middle Bar Table` — all matching what was
visibly true in the source frames at capture time.

**Detector sanity check** (against the Roblox sample image already
committed in `data/inbox/`, run via `docker compose run --rm worker python
-m app.worker`): the detector found **1 person at 58.9% confidence**
(`box: [861, 359, 947, 487]`), confirming YOLOv8n does detect Roblox
avatars, at least sometimes — though the image visibly has 8-10 avatars
and only 1 was picked up, which is expected: the model is trained on real
photos (COCO), and stylized/blocky game avatars are a domain mismatch it
wasn't trained for.

**API/dashboard check**: `curl http://localhost:8000/api/tables/latest`
returns the real observations with correct `model_version` (`yolo:yolov8s`)
and `processed_at`, confirming the existing Flask scaffold from Umizumi 1
already serves live pipeline output correctly with zero changes needed.

## Known limitations for Umizumi 4 to be aware of

1. **Table polygons are now calibrated to the live YouTube camera** (the
   Beach Bar St. John webcam, 1920x1080), not the placeholder corner
   coordinates Umizumi 1 originally seeded. `db/seed.sql` defines 5 tables
   (`Right Front Table`, `Behind Right-Middle Table`, `Left Table`, `Middle
   Bar Table`, `Background Left Table`) with polygons drawn against a real
   captured frame and confirmed against live detections (see verification
   below). **If the camera source ever changes** (different URL, different
   framing, back to Roblox), these polygons stop being meaningful and need
   to be recalibrated the same way: capture a frame, draw candidate boxes
   with matplotlib/OpenCV, verify against real detections, then update
   `tables.polygon` for each row (an `UPDATE`, not a reseed, if there's
   observation history worth keeping — `db/seed.sql`'s `ON CONFLICT (name)
   DO NOTHING` won't touch already-seeded rows).
2. **`yt-dlp` needs to stay current.** YouTube changes its extraction
   internals often enough that an outdated `yt-dlp` breaks with `No video
   formats found` (this happened with the system-installed `apt` version,
   over a year stale, during this handoff). `requirements.txt` intentionally
   leaves `yt-dlp` unpinned so `docker compose build` always pulls the
   latest release — if the live source ever stops resolving, rebuilding the
   image is the first thing to try.
3. **The live source is a stand-in, not the actual Roblox restaurant.**
   The YouTube capture path was added at the project owner's explicit
   request as an additional input source for a "real-time" dashboard demo,
   separate from the original Roblox-screenshot flow from Umizumi 2. Both
   sources feed the same `frames`/`table_observations` contract, so nothing
   about Umizumi 4 needs to know which source produced a given frame.
4. **Waiter tracking was removed entirely, on purpose.** Earlier drafts of
   this project (visible in `handoff.md` and the original design spec)
   planned a `waiters` catalog, `waiter_assignments`, and a
   `detected_waiter_id` column tied to matching Roblox avatar "skins." The
   project owner explicitly dropped this scope once the project moved to
   real video: there's no equivalent to a swappable avatar skin for real
   staff, and the project now only counts customers per table. The
   `waiters` and `waiter_assignments` tables, `detected_waiter_id`,
   `skin_reference_path`, and `data/skins/` are all gone — from the schema,
   the seed data, `app/db.py`, `app/vision.py`, the dashboard JS, and the
   design spec. Umizumi 4 should not reintroduce any of this.
5. **People counts undercount in dense, overlapping clusters — this is a
   model-capacity ceiling, not a bug.** When the project owner manually
   counted 7 people at one table in a live frame, the pipeline reported far
   fewer. Investigated by running yolov8n, yolov8s, and yolov8m against the
   identical frame at a permissive confidence floor: yolov8n found ~3
   distinct people, yolov8s found ~4, yolov8m found ~4 (different ones,
   16x slower). None got close to 7. Overlapping bounding boxes in a
   shoulder-to-shoulder crowd get merged or suppressed by NMS regardless of
   model size — this is a known failure mode for general-purpose
   COCO-pretrained detectors, not something further threshold tuning or a
   bigger stock model fixes. yolov8s was kept as the best speed/accuracy
   trade-off found. If Umizumi 4 needs materially better crowd recall, the
   next real lever is fine-tuning on labeled frames from this specific
   camera, not swapping stock checkpoints.

## Scope for Umizumi 4

The Flask API (`app/web.py`) and dashboard (`app/templates/dashboard.html`,
`app/static/app.js`) already exist and already work against real data (see
verification above) — Umizumi 1 scaffolded them further than the README
implies. What's actually left:

1. Decide on and implement table polygon calibration (or explicitly
   document that per-table occupancy is illustrative-only for this MVP).
2. Review whether the dashboard should surface staleness — e.g. a frame
   that hasn't updated in `STALE_AFTER_SECONDS` (already in `.env.example`,
   unused by any code) could visually warn that a table's data is old,
   useful once the `live` service runs unattended for hours.
3. Confirm the continuous `live` service (`docker compose up -d db web
   live`) holds up over a multi-hour unattended run — this handoff verified
   a single cycle, not sustained operation.
4. Anything else API/dashboard-shaped that surfaces during the live demo.

## Files to use

- `app/web.py`: Flask routes — `/health`, `/`, `/api/tables/latest`.
- `app/templates/dashboard.html`, `app/static/app.js`,
  `app/static/styles.css`: the dashboard UI, 30s polling already wired.
- `app/db.py`: `fetch_latest_table_state()` is the only read path Umizumi 4
  should need; avoid adding new write paths here.
- `db/schema.sql`: `latest_table_state` view — treat as the read contract;
  do not change without coordinating back with Umizumi 3's writers.
- `db/seed.sql`: table polygons, if calibration is undertaken.
- `compose.yaml`: `live` service env vars if continuous-run tuning is
  needed (`LIVE_FRAME_COUNT`, `LIVE_CAPTURE_INTERVAL_SECONDS`,
  `LIVE_POLL_INTERVAL_SECONDS`).

## Constraints

- Do not use Streamlit, Kafka, Airflow, Redis, Celery, a data lake, or a
  new service beyond what already exists — same constraint every prior
  handoff has carried.
- Keep the dashboard on polling; WebSockets/SSE are still out of scope
  per the original design (the 30s cadence is what "real-time" means in
  this project).
- Umizumi 4 should not write to `table_observations`, `frames`, or
  `media_inputs` — those stay owned by ingestion (Umizumi 2) and inference
  (Umizumi 3).

## How to run everything

```bash
cp .env.example .env
# edit .env: set LIVE_STREAM_URL to the YouTube video/live URL to use

docker compose build
docker compose up -d db web live
docker compose logs -f live      # watch capture+detection cycles stream in
```

Check results directly:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/tables/latest

docker compose exec db psql -U restaurant -d restaurant_tracker -c \
  "SELECT frame_id, table_id, people_count, occupied, confidence, model_version FROM table_observations ORDER BY frame_id, table_id;"
```

One-off confirmation test (5 frames, then exit, without starting the
continuous service):

```bash
docker compose run --rm -e LIVE_MODE=once -e LIVE_FRAME_COUNT=5 live
```

Full test suite:

```bash
docker compose run --rm worker python -m unittest discover -v
```

## Handoff to whoever picks up Umizumi 4

Deliver:

- modified files and commit hash;
- confirmation the dashboard shows live-updating data over a sustained
  `docker compose up -d live` run, not just one cycle;
- decision made on table polygon calibration (fixed vs. documented as
  illustrative);
- any UI changes made, with a screenshot or description.
