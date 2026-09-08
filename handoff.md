# Handoff — Umizumi 1 → Umizumi 2

Fecha: 2026-09-07  
Proyecto: Restaurant Tracking System  
Equipo: Umizumi

Estado: Umizumi 2 implementado. Este documento conserva el alcance original;
el handoff vigente para el siguiente paso es `handoff-to-umizumi-3.md`.

## Objetivo de este handoff

Implementar la ingestión y normalización de medios para que el pipeline
convierta cada entrada en uno o más registros de `frames` que Umizumi 3 pueda
procesar con el modelo.

Prioridad inmediata:

1. Imágenes `.jpg`, `.jpeg` y `.png` para el MVP inicial.
2. Vídeos `.mp4` procesados por lotes con OpenCV para la siguiente entrega.

La transformación, el modelo y el dashboard deben recibir frames sin importar
si el origen fue una imagen o un vídeo.

## Estado actual

Ya existe el scaffold inicial:

- `Dockerfile` y `compose.yaml` con servicios `db`, `worker` y `web`.
- PostgreSQL con schema, vista `latest_table_state` y datos fijos.
- Catálogo fijo de cuatro meseros en `db/seed.sql`.
- Carpetas `data/inbox`, `data/processed`, `data/failed` y `data/skins`.
- Flask con `/health`, `/` y `/api/tables/latest`.
- Dashboard HTML/CSS/JavaScript con polling cada 30 segundos.
- `requirements.txt` incluye Flask, `psycopg` y OpenCV para ingestión y vídeo.
- `app/worker.py` detecta archivos nuevos, calcula SHA-256, persiste medios y
  genera frames para imágenes y vídeos.
- La ingesta es ETL batch: primero transforma los medios a frames y después
  carga `media_inputs` y `frames`; no mantiene un proceso de polling.
- `app/vision.py` contiene la asociación por punto inferior central y la
  generación de observaciones por mesa.
- `app/db.py` expone consultas de frames pendientes, mesas y carga transaccional
  de observaciones.
- Pruebas sin dependencias externas: `6/6` pasan; las pruebas que importan
  OpenCV y psycopg deben ejecutarse dentro del contenedor de aplicación.
- La configuración base de Docker Compose fue validada: PostgreSQL queda
  `Healthy` y `web`/`worker` inician correctamente.

Commits base:

- `e00f4be feat: initialize restaurant tracker scaffold`
- `9f7fa4d test: cover invalid table values`

Ultralytics todavía no está instalado en la imagen. Se debe agregar en
Umizumi 3 junto con la inferencia; OpenCV ya está disponible para ingestión y
extracción de frames.

## No cambiar

- No usar Streamlit.
- No agregar Kafka, Airflow, Redis, Celery, data lake ni otro servicio.
- No crear CRUD para meseros: el catálogo y las skins son fijos.
- No cambiar los nombres de las tablas ni el contrato de `frames` sin avisar a
  Umizumi 3.
- No hacer streaming ni WebSockets; el dashboard seguirá usando polling de 30
  segundos.
- Mantener ligera la imagen base; agregar dependencias de visión únicamente en
  el handoff que las necesite.

## Contrato de entrada

Las entradas se colocan en:

```text
data/inbox/
```

Tipos aceptados:

```text
.jpg  .jpeg  .png  .mp4
```

Cada archivo debe:

1. Detectarse sin detener el worker si otro archivo falla.
2. Identificarse mediante SHA-256.
3. Registrarse una sola vez en `media_inputs`.
4. Validarse como medio legible, no solamente por extensión.

Un archivo duplicado debe ignorarse usando el índice único de
`media_inputs.media_hash`.

## Salida esperada

### Imagen

Una imagen válida produce un frame:

```text
frame_index = 0
offset_ms   = 0
image_path  = ruta de la imagen normalizada
status      = pending
```

El registro de `media_inputs` debe marcarse como `processed` después de que el
frame se haya creado correctamente.

### Vídeo

Un `.mp4` válido debe producir frames separados por
`FRAME_INTERVAL_SECONDS`. Para cada frame guardar:

```text
media_input_id
frame_index
offset_ms
image_path
captured_at
status = pending
```

La extracción debe ser batch; no se necesita reproducción ni procesamiento en
tiempo real.

Los archivos derivados pueden guardarse en:

```text
data/processed/<media_hash>/
```

Los medios corruptos o no procesables deben quedar con `status = failed` y
`error_message` en `media_inputs`; no deben detener el resto de la cola.

## Archivos a revisar

Punto de entrada actual:

- `app/worker.py`: script ETL batch y coordinación de frames pendientes.
- `app/media.py`: clasificación de medios; extenderlo solo si hace falta.
- `app/db.py`: conexión a PostgreSQL; agregar únicamente las consultas mínimas.
- `db/schema.sql`: contrato de `media_inputs` y `frames`.
- `compose.yaml`: variables y volúmenes disponibles.
- `requirements.txt`: dependencias base; agregar `opencv-python-headless` para
  extracción de vídeo y dejar `ultralytics` para Umizumi 3.

Preferir funciones pequeñas y reutilizar el código existente. No crear una
capa adicional si la lógica cabe en `app/media.py` y `app/worker.py`.

## Criterios de aceptación

- [ ] Una imagen válida en `data/inbox/` crea un registro en `media_inputs` y
  un registro en `frames`.
- [ ] Una imagen duplicada no crea otro `media_input` ni otro frame.
- [ ] Una imagen corrupta queda en `failed` con un mensaje útil.
- [ ] Un archivo no soportado se ignora y no detiene el worker.
- [ ] Un `.mp4` válido genera frames según el intervalo configurado.
- [ ] Los frames entregados a Umizumi 3 tienen `status = pending`.
- [ ] El script continúa procesando los archivos restantes después de un error.
- [ ] El procesamiento es reproducible al reiniciar el worker.
- [ ] Las pruebas unitarias y la prueba manual con Docker quedan documentadas.
- [x] La imagen base se construye y los tres servicios inician con Docker
  Compose.

## Pruebas mínimas

Agregar pruebas con `unittest` para:

- Imagen válida → un frame.
- Duplicado por SHA-256 → no se duplica.
- Archivo corrupto → estado `failed`.
- Vídeo → varios frames con índices y offsets crecientes.
- Archivo no soportado → se ignora sin interrumpir la cola.

Para las pruebas de vídeo basta crear o usar un `.mp4` pequeño; no se necesita
un dataset grande.

## Cómo ejecutar

Desde la raíz del repositorio:

```bash
docker compose up --build -d db web
docker compose run --rm worker python -m app.worker
```

Para inspeccionar la API después de la ingesta:

```bash
docker compose ps
curl http://localhost:8000/health
curl http://localhost:8000/api/tables/latest
```

La respuesta esperada de health check es:

```json
{"status":"ok"}
```

Para las pruebas dentro del contenedor de aplicación:

```bash
docker compose run --rm worker python -m unittest discover -v
```

La prueba base de Docker ya fue validada. La prueba end-to-end de una imagen
todavía queda pendiente porque la inferencia del modelo aún no está integrada.

## Entrega al siguiente Umizumi

El handoff debe incluir:

- Archivos modificados.
- Comandos ejecutados y resultado de las pruebas.
- Un ejemplo de entrada procesada.
- Ejemplo de registros creados en `media_inputs` y `frames`.
- Cualquier limitación conocida.

La salida mínima para Umizumi 3 es: `frame_id`, `image_path`,
`media_input_id`, `frame_index`, `captured_at` y `status = pending`.
