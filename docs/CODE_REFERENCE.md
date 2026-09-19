# Referencia de código

*[English version](CODE_REFERENCE.en.md)*

Qué hace cada función/clase del proyecto, agrupado por archivo. Para el
"por qué" de cada decisión, ver `README.md` y los handoffs (`handoff-*.md`);
esto es solo el mapa de qué hace cada pieza.

## Pipeline de ingesta y detección

### `app/media.py`

| Función | Qué hace |
| --- | --- |
| `media_type(path)` | Clasifica un archivo como `"image"` o `"video"` por su extensión (`.jpg/.jpeg/.png` vs `.mp4`); lanza `ValueError` si no reconoce la extensión. |

### `app/domain.py`

| Función | Qué hace |
| --- | --- |
| `table_state(people_count, confidence, threshold=0.5)` | Devuelve `"free"`, `"occupied"` o `"review"` (confianza insuficiente) a partir de un conteo de personas y una confianza. Valida rangos (`people_count >= 0`, `0 <= confidence <= 1`). |

### `app/vision.py`

| Función | Qué hace |
| --- | --- |
| `_point_on_segment(point, start, end)` | Auxiliar geométrico: ¿el punto cae exactamente sobre el segmento `start-end`? Usado para tratar el borde del polígono como "dentro". |
| `point_in_polygon(point, polygon)` | Ray casting clásico: ¿el punto está dentro del polígono de una mesa? Incluye el borde como "dentro" vía `_point_on_segment`. |
| `build_table_observations(detections, tables, model_version)` | Núcleo de la asociación detección↔mesa: para cada detección de persona, usa el punto medio-inferior de su bounding box como "ancla" (los pies), la asigna a la primera mesa cuyo polígono la contenga, y arma una observación por mesa (`people_count`, `occupied`, `confidence` promedio, `model_version`). Una mesa sin detecciones queda con `people_count=0`, `confidence=1.0`. |

### `app/detector.py`

| Función | Qué hace |
| --- | --- |
| `get_model_path()` | Lee `MODEL_PATH` del entorno (default `/app/models/yolov8s.pt`). |
| `get_confidence_threshold()` | Lee `CONFIDENCE_THRESHOLD` del entorno (default `0.25`). |
| `model_version_from_path(model_path=None)` | Deriva el string `model_version` guardado en cada observación (ej. `"yolo:yolov8s"`) a partir del nombre del checkpoint. |
| `load_detector(model_path=None, confidence_threshold=None)` | Carga el modelo YOLOv8 (Ultralytics) y devuelve una función `detect(image_path)` cerrada sobre ese modelo y threshold, filtrada a la clase "person" (`PERSON_CLASS_ID=0`). Cada detección devuelve `box` (xyxy) y `confidence`. |

### `app/youtube.py`

| Función | Qué hace |
| --- | --- |
| `resolve_stream_url(video_url)` | Resuelve una URL de YouTube a la URL directa del stream de video vía `yt-dlp -g -f bestvideo/best` (esta cámara solo publica renditions separadas video-only, de ahí el `bestvideo`). |
| `capture_snapshot(stream_url, out_path)` | Captura un solo frame del stream con `ffmpeg -frames:v 1`. |
| `capture_frames(video_url, count, interval_seconds, output_dir)` | Resuelve el stream una vez y captura `count` snapshots espaciados `interval_seconds`, nombrados por timestamp. Es lo que llama `live_worker.py` en cada ciclo. |

### `app/worker.py` — ETL batch (archivos sueltos)

| Función | Qué hace |
| --- | --- |
| `get_file_hash(path)` | SHA-256 de un archivo, en streaming (no carga todo a memoria) — es la clave de idempotencia de la ingesta. |
| `get_frame_interval_seconds()` | Lee `FRAME_INTERVAL_SECONDS` del entorno para el muestreo de video. |
| `process_image(path, media_hash, processed_dir)` | Normaliza una imagen a un único frame en `processed_dir/<hash>/0.jpg`. |
| `process_video(path, media_hash, processed_dir)` | Extrae frames de un video cada `FRAME_INTERVAL_SECONDS`, cada uno guardado como `<n>.jpg`. |
| `transform_media(kind, path, media_hash, processed_dir)` | Despacha a `process_image` o `process_video` según `kind`. |
| `ingest_path(path, processed_dir)` | Orquesta un archivo: clasifica → hashea → chequea duplicado (`media_input_exists`) → transforma → carga a DB (`load_media_and_frames`). Absorbe y loguea cada tipo de fallo sin detener el batch; devuelve `bool` de éxito. |
| `process_pending_frames(detector, model_version)` | Toma los frames en estado `pending`, corre el detector, asocia detecciones a mesas (`build_table_observations`) y guarda las observaciones. Un frame que falla se marca `failed` y no detiene a los demás. Devuelve un resumen por frame (usado para logging). |
| `discover_media(input_dir)` | Lista los archivos de `data/inbox/` a procesar en esta corrida. |
| `main()` | Entry point del ETL de un solo paso: ingesta todo lo que hay en `INPUT_DIR`, corre el detector sobre los frames pendientes, termina. Pensado para correr una vez por invocación (`docker compose run --rm worker python -m app.worker`), no en loop. |

### `app/live_worker.py` — captura continua desde YouTube

| Función | Qué hace |
| --- | --- |
| `get_env_int(name, default)` | Helper para leer enteros positivos del entorno, con validación. |
| `run_cycle(video_url, frame_count, capture_interval, input_dir, processed_dir, detector, model_version)` | Un ciclo completo: captura frames del stream (`capture_frames`), los ingesta (`ingest_path`) y corre la inferencia pendiente (`process_pending_frames`); loguea un resumen por frame. |
| `main()` | Bucle del servicio `live`: cada ciclo va envuelto en `try/except` para que un fallo puntual (timeout de `ffmpeg`, stream caído) no tumbe el servicio — se loguea y se reintenta en el siguiente `LIVE_POLL_INTERVAL_SECONDS`. `LIVE_MODE=once` corre un solo ciclo y sale; `LIVE_MODE=loop` es el modo continuo real. |

## Acceso a datos — `app/db.py`

Todas las funciones abren su propia conexión (`get_connection()`, vía
`DATABASE_URL`) y la cierran al terminar; no hay pool ni conexión
compartida entre llamadas.

| Función/Clase | Qué hace |
| --- | --- |
| `_rows_to_dicts(rows, columns)` | Convierte filas de cursor (tuplas) a `dict`, serializando `date`/`datetime` a ISO. Usado por casi todas las funciones de lectura. |
| `fetch_latest_table_state()` | Lee la vista `latest_table_state` — snapshot actual por mesa. Es el único endpoint que necesita el dashboard para el estado "ahora". |
| `fetch_observation_history(hours=3)` | Histórico de `table_observations` de las últimas `hours` horas, para el gráfico de tendencia. |
| `media_input_exists(media_hash)` | ¿Ya se ingirió este archivo antes? (idempotencia por hash). |
| `load_media_and_frames(media_type, source_path, media_hash, frames, status="processed", error_message=None)` | Inserta `media_inputs` + sus `frames` en una transacción; `ON CONFLICT (media_hash) DO NOTHING` — si ya existía, devuelve `None` sin tocar nada. |
| `fetch_pending_frames()` | Frames en estado `pending`, listos para inferencia. |
| `fetch_tables()` | Las 5 mesas con su polígono (deserializado de JSONB a lista de puntos). |
| `save_frame_observations(frame_id, observations)` | Inserta/actualiza las observaciones de un frame (`ON CONFLICT (frame_id, table_id) DO UPDATE`) y marca el frame como `processed`. |
| `mark_frame_failed(frame_id, error_message)` | Marca un frame como `failed` cuando la inferencia truena. |
| `ScheduleConflict` | Excepción propia: un turno se solaparía con otro del mismo mesero o de una mesa ya asignada. |
| `verify_user(username, password)` | Login: busca el usuario y valida el hash (`werkzeug.security.check_password_hash`). Devuelve `{id, username}` o `None`. |
| `fetch_waiters(active_only=False)` | Lista de meseros. |
| `create_waiter(name)` | Alta de un mesero nuevo. |
| `fetch_shifts(start, end)` | Turnos que **se solapan** con `[start, end]` (para pintar el calendario, incluye los que cruzan el borde de la ventana), con el nombre del mesero y las mesas asignadas ya agregadas (`array_agg`). |
| `_has_waiter_overlap(cursor, waiter_id, starts_at, ends_at, exclude_shift_id=None)` | ¿Ese mesero ya tiene otro turno en ese rango? |
| `_has_table_overlap(cursor, table_ids, starts_at, ends_at, exclude_shift_id=None)` | ¿Alguna de esas mesas ya está asignada a otro turno en ese rango? |
| `_replace_shift_tables(cursor, shift_id, table_ids)` | Borra y reinserta las filas de `waiter_shift_tables` de un turno (usado al crear/editar). |
| `create_shift(waiter_id, starts_at, ends_at, table_ids)` | Crea un turno tras validar ambos tipos de solapamiento; lanza `ScheduleConflict` si choca. |
| `update_shift(shift_id, waiter_id, starts_at, ends_at, table_ids)` | Igual que crear, pero excluyendo el propio turno de la validación de solapamiento. |
| `delete_shift(shift_id)` | Borra un turno (`waiter_shift_tables` cae en cascada por FK). |
| `_episode_people_served(observations)` | El cálculo más delicado del proyecto: dado un stream de `(table_id, people_count, occupied)` ordenado por tiempo, detecta rachas contiguas de ocupación por mesa y suma el pico de cada racha — para no contar el mismo grupo sentado una vez por cada frame (~cada 30-40s). |
| `fetch_waiter_stats(start, end)` | Por cada turno que se solapa con `[start, end]`, trae las observaciones de sus mesas asignadas en esa ventana, y agrega por mesero: turnos, horas trabajadas, ocupación promedio, personas atendidas (vía `_episode_people_served`). |

## Web / API — `app/web.py`

| Función | Qué hace |
| --- | --- |
| `login_required(view)` | Decorador: sin sesión, redirige a `/login` (rutas de página) o devuelve `401` JSON (rutas `/api/*`). |
| `_parse_datetime(value)` | Parsea un ISO string a `datetime`; si no trae timezone, asume UTC. |
| `health()` | `GET /health` — prueba la conexión a la DB, sin requerir login. |
| `login()` | `GET/POST /login` — formulario y verificación de credenciales (`verify_user`); guarda `user_id`/`username` en sesión. |
| `logout()` | `GET /logout` — limpia la sesión. |
| `dashboard()` | `GET /` — la página principal (KPIs + gráficos). |
| `latest_tables()` | `GET /api/tables/latest`. |
| `tables_history()` | `GET /api/tables/history?hours=` (clamp 1–24). |
| `schedule()` | `GET /schedule` — la página del calendario. |
| `list_waiters()` / `add_waiter()` | `GET/POST /api/waiters`. |
| `list_shift_tables()` | `GET /api/shift-tables` — las mesas disponibles para asignar (para los checkboxes del modal). |
| `list_shifts()` | `GET /api/shifts?start=&end=`. |
| `_shift_payload(body)` | Extrae y castea `waiter_id`/`starts_at`/`ends_at`/`table_ids` de un JSON de request; comparte validación entre crear, editar y el endpoint bulk. |
| `add_shift()` / `edit_shift()` / `remove_shift()` | `POST/PUT /api/shifts`, `DELETE /api/shifts/<id>` — `ScheduleConflict` se traduce a `409`. |
| `add_shifts_bulk()` | `POST /api/shifts/bulk` — crea varios turnos de una vez, cada uno validado por separado; responde `207` con `created`/`conflicts` por índice en vez de abortar el lote entero ante un choque puntual. Es lo que usan los patrones de repetición del calendario. |
| `waiter_stats_page()` | `GET /waiters/stats` — la página de estadísticas. |
| `waiter_stats_api()` | `GET /api/waiters/stats?start=&end=` — default: últimos 7 días. |

## Frontend

### `app/static/app.js` — dashboard (`/`)

| Función | Qué hace |
| --- | --- |
| `toUtcInputValue` / `fromUtcInputValue` | Conversión entre `Date` y el valor de un `<input type="datetime-local">`, siempre en UTC (no en la zona horaria del navegador). |
| `renderTables(tables)` | Pinta las tarjetas de detalle por mesa. |
| `renderKpis(tables)` | Calcula y pinta la fila de KPIs (personas ahora, % ocupación, aforo, mesa con más gente, confianza promedio) a partir del snapshot actual. |
| `renderCurrentChart(tables)` | Bar chart de personas vs. capacidad por mesa (Chart.js); reutiliza la instancia existente en refrescos posteriores en vez de recrearla. |
| `renderOccupancyChart(tables)` | Dona de mesas ocupadas vs. libres. |
| `renderTrendChart(history)` | Line chart multi-mesa con el histórico de ocupación; agrupa las observaciones por timestamp para alinear las series. |
| `fetchJson(url)` | `fetch` con manejo de error uniforme. |
| `refresh()` | Orquesta un ciclo de refresco: trae `latest`+`history`, repinta todo. Se llama al cargar y cada `REFRESH_MS` (30s). |

### `app/static/schedule.js` — calendario (`/schedule`)

| Función | Qué hace |
| --- | --- |
| `loadWaiters(selectedId)` / `loadTables()` | Pueblan el `<select>` de meseros y los checkboxes de mesas del modal. |
| `renderRepeatWeekdays()` / `getCheckedWeekdays()` / `resetRepeatFields()` | Manejo de los checkboxes Lun–Dom del patrón de repetición. |
| `setCheckedTables` / `getCheckedTables` | Leer/escribir qué mesas están marcadas en el modal. |
| `openModal({...})` / `closeModal()` | Abren el modal en modo crear o editar (oculta la sección de repetición al editar); cierran y resetean el formulario. |
| `computeRepeatOccurrences(baseStart, baseEnd, weekdays, untilValue)` | Dado un turno base y un patrón de días de la semana + fecha límite, calcula las fechas adicionales a crear (misma hora y duración, avanzando de a 24h para no arrastrar drift de zona horaria). |
| `saveShift(event)` | Submit del modal: crea o edita el turno; si es creación y hay patrón de repetición marcado, pide confirmación y crea las repeticiones vía `/api/shifts/bulk`. |
| `deleteShift()` | Borra el turno que está abierto en el modal. |
| `addWaiter()` | Alta rápida de un mesero nuevo desde el modal (`prompt()` + `POST /api/waiters`). |
| `updateShiftTimes(info)` | Handler de `eventDrop`/`eventResize` de FullCalendar: al arrastrar o redimensionar un turno, actualiza sus horarios vía `PUT`; revierte el cambio visual si el backend lo rechaza (conflicto). |
| `duplicateWeek()` | Duplica a la semana siguiente los turnos **totalmente contenidos** en la semana visible del calendario (los que cruzan el borde se omiten, ver `README.md`); confirma con el usuario antes de crear. |
| `init()` | Instancia FullCalendar (vista semanal, UTC, `select`/`eventClick`/`eventDrop`/`eventResize`), carga meseros y mesas, engancha los listeners de botones. |

### `app/static/waiter_stats.js` — estadísticas (`/waiters/stats`)

| Función | Qué hace |
| --- | --- |
| `defaultRange()` | Rango inicial del selector de fechas: últimos 7 días. |
| `renderTable(stats)` | Pinta la tabla "Detalle por mesero". |
| `renderCharts(stats)` | Bar chart de personas atendidas y bar chart de ocupación promedio, uno por mesero. |
| `loadStats()` | Lee el rango de fechas de los inputs, pide `/api/waiters/stats` y repinta tabla + gráficos. Se llama al cargar y al hacer clic en "Aplicar". |
