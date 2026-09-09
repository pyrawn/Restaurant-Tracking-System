# Restaurant Tracking System — diseño del MVP

Fecha: 2026-09-07  
Equipo: Umizumi (4 integrantes)  
Estado: arquitectura aprobada; pendiente de revisión del documento

## 1. Objetivo

Construir un pipeline que reciba capturas de un restaurante dentro de Roblox,
detecte la ocupación de mesas y el número de personas, conserve el historial en
PostgreSQL y presente el estado en un dashboard web propio.

El MVP procesa imágenes colocadas periódicamente en un directorio. La interfaz
interna trabaja con frames para permitir que, más adelante, un video pueda
producir esos mismos frames sin modificar la transformación, el almacenamiento
o el dashboard.

## 2. Alcance

Incluido en el MVP:

- Entrada de imágenes JPEG y PNG.
- Validación e ingestión idempotente mediante SHA-256.
- Detección de avatares/personas con un modelo preentrenado validado contra
  capturas reales de Roblox.
- Asociación de detecciones con zonas fijas de mesas.
- Conteo de personas, estado de ocupación y confianza por mesa.
- Historial operacional en PostgreSQL.
- Dashboard Flask con HTML, CSS y JavaScript nativo.
- Actualización del dashboard mediante polling cada 30 segundos.
- Ejecución reproducible con Docker Compose.

Fuera del MVP:

- Procesamiento directo de video.
- Streaming continuo.
- Kafka, Airflow, Redis, Celery o un data lake.
- WebSockets o Server-Sent Events.
- React u otro framework de frontend.
- Entrenamiento de una red neuronal desde cero.
- Reconocimiento facial.
- Identificación o seguimiento de meseros: el proyecto solo cuenta clientes
  por mesa.

## 3. Arquitectura

```text
Imagen Roblox ahora / video después
                 |
                 v
          Ingestión de medios
                 |
                 v
       Normalización a uno o más frames
       imagen -> 1 frame
       video  -> N frames (extensión futura)
                 |
                 v
        Detección y transformación
                 |
                 v
              PostgreSQL
                 |
                 v
       Flask API + HTML/CSS/JS
          polling cada 30 s
```

Las cinco etapas son límites lógicos, no microservicios independientes. Docker
Compose contiene tres servicios:

- `db`: PostgreSQL y volumen persistente.
- `worker`: ingestión, normalización, inferencia y carga.
- `web`: Flask, API y dashboard.

`worker` y `web` reutilizan una sola imagen de aplicación Python con comandos
de inicio diferentes.

## 4. Requisitos

### REQ-01 — Contenedores y entorno reproducible

El sistema debe iniciar con `docker compose up --build`. La configuración se
inyecta mediante variables de entorno y se documenta en `.env.example`.

Variables mínimas:

```text
DATABASE_URL
INPUT_DIR
MODEL_PATH
CONFIDENCE_THRESHOLD
FRAME_INTERVAL_SECONDS
INGEST_POLL_SECONDS=30
DASHBOARD_REFRESH_SECONDS=30
STALE_AFTER_SECONDS
```

Criterios de aceptación:

- Una Umizumi puede clonar el repositorio y levantar los tres servicios con un
  solo comando.
- PostgreSQL conserva sus datos después de reiniciar los contenedores.
- El servicio web no se considera listo hasta que la base responda.

### REQ-02 — Ingestión idempotente y adaptable

El worker revisa `data/inbox/` cada 30 segundos. Para cada archivo calcula
SHA-256, valida que pueda decodificarse y registra el medio una sola vez.

Estados:

```text
pending -> processing -> processed
                      -> failed
```

Una imagen genera un frame con `frame_index = 0` y `offset_ms = 0`. La
transformación solo recibe registros de `frames`; no conoce si estos provienen
de una imagen o de un video.

La extensión futura de video implementará una función que reciba un archivo y
produzca frames separados por `FRAME_INTERVAL_SECONDS`. No requiere cambiar el
contrato de salida de ingestión.

Criterios de aceptación:

- Se aceptan `.jpg`, `.jpeg` y `.png`.
- Un archivo duplicado no vuelve a procesarse.
- Un archivo corrupto queda en estado `failed` con el motivo registrado.
- El fallo de un archivo no detiene el procesamiento de los demás.

### REQ-03 — Transformación e inferencia

Cada frame procesado produce una observación para cada mesa configurada:

```json
{
  "frame_id": 42,
  "table_id": 1,
  "people_count": 2,
  "occupied": true,
  "confidence": 0.87,
  "model_version": "configured-model-version"
}
```

Las mesas se representan mediante polígonos fijos. Una detección se asigna a
una mesa cuando su punto inferior central cae dentro del polígono. Una mesa se
considera ocupada cuando `people_count > 0`.

Antes de fijar el modelo, el equipo prueba al menos 20 capturas representativas
de Roblox. El modelo se acepta inicialmente si obtiene:

- F1 de ocupación mayor o igual a 0.80.
- Error absoluto medio de conteo menor o igual a una persona por mesa.

Si el modelo preentrenado no alcanza esos valores, el siguiente paso es
ajustarlo con capturas etiquetadas de Roblox; no se entrena desde cero.

Criterios de aceptación:

- Cada frame termina en `processed` o `failed`.
- Cada observación conserva confianza y versión del modelo.
- Reprocesar el mismo frame no duplica observaciones.
- Una inferencia fallida no reemplaza el último estado válido del dashboard.

### REQ-04 — Carga e histórico en PostgreSQL

PostgreSQL funciona como almacenamiento OLTP e histórico del MVP. No existe un
warehouse separado.

Tablas:

```text
media_inputs
  id, media_type, source_path, media_hash,
  ingested_at, status, error_message

frames
  id, media_input_id, frame_index, offset_ms,
  image_path, captured_at, status

tables
  id, name, capacity, polygon

table_observations
  id, frame_id, table_id, people_count, occupied,
  confidence, model_version, processed_at
```

Restricciones mínimas:

- `media_inputs.media_hash` es único.
- La combinación `(media_input_id, frame_index)` es única.
- La combinación `(frame_id, table_id)` en observaciones es única.
- `people_count` no puede ser negativo.
- La carga de todas las observaciones de un frame ocurre en una transacción.

Las imágenes se almacenan en el filesystem; PostgreSQL conserva sus rutas y
metadatos. Una vista `latest_table_state` entrega la última observación válida,
capacidad y antigüedad por mesa.

### REQ-05 — Dashboard web propio

Flask expone el dashboard y una API JSON mínima:

```text
GET  /api/tables/latest
GET  /api/tables/{id}/history
```

El navegador consulta `/api/tables/latest` cada 30 segundos y actualiza el DOM
sin recargar la página. El plano se construye con SVG o elementos HTML
posicionados; no se incorpora un framework frontend.

Cada mesa muestra:

- Estado libre, ocupada o sin datos.
- Número de personas y capacidad.
- Confianza del modelo.
- Hora de la última observación.
- Indicador de información atrasada cuando supera `STALE_AFTER_SECONDS`.

Colores iniciales:

```text
verde     libre
rojo      ocupada
amarillo  baja confianza
gris      sin datos o información atrasada
```

Criterios de aceptación:

- El dashboard funciona sin Streamlit.
- Una observación nueva aparece en un máximo de 30 segundos después de quedar
  disponible en PostgreSQL.
- Una actualización fallida conserva los últimos datos visibles y muestra un
  indicador de desconexión.

## 5. Handoffs del equipo Umizumi

| Integrante | Responsabilidad | Salida del handoff |
| --- | --- | --- |
| Umizumi 1 | Docker, PostgreSQL y esquema | Servicios sanos, tablas, vista y datos iniciales |
| Umizumi 2 | Ingestión y normalización | Registros `media_inputs` y `frames` pendientes |
| Umizumi 3 | Modelo, transformación y carga | Registros `table_observations` procesados |
| Umizumi 4 | Flask, API y dashboard | Visualización consumiendo `latest_table_state` |

Cada handoff incluye:

- Comando de ejecución.
- Entrada esperada.
- Salida producida.
- Ejemplo válido.
- Una comprobación mínima ejecutable.

Orden de integración:

```text
Umizumi 1: schema + catálogo fijo
        |
        +------> Umizumi 2: media -> frame
        |
        +------> Umizumi 4: dashboard con datos semilla

Umizumi 2 -> Umizumi 3: frame_id + image_path
Umizumi 3 -> Umizumi 4: latest_table_state actualizado
```

Umizumi 4 puede desarrollar el dashboard con observaciones semilla mientras
Umizumi 2 y Umizumi 3 terminan el pipeline.

## 6. Manejo de errores

- Los medios inválidos se registran como `failed` sin detener el worker.
- Las cargas por frame son atómicas: se insertan todas las observaciones o
  ninguna.
- El dashboard conserva la última observación válida ante fallos del modelo.
- Los datos atrasados se distinguen visualmente de una mesa libre.
- Los archivos originales no se eliminan automáticamente durante el MVP.

## 7. Verificación mínima

La prueba end-to-end del MVP debe:

1. Colocar una captura conocida en `data/inbox/`.
2. Confirmar la creación de un `media_input` y un frame.
3. Confirmar una observación por mesa.
4. Consultar `/api/tables/latest` y encontrar esas observaciones.
5. Volver a colocar la misma captura y confirmar que no se duplicó.

También se mantiene un pequeño conjunto etiquetado de capturas Roblox para
medir ocupación y error de conteo antes de cambiar de modelo.

## 8. Estructura prevista

```text
Restaurant-Tracking-System/
├── compose.yaml
├── Dockerfile
├── requirements.txt
├── .env.example
├── app/
│   ├── pipeline.py
│   ├── web.py
│   ├── db.py
│   ├── templates/
│   │   └── dashboard.html
│   └── static/
│       ├── app.js
│       └── styles.css
├── db/
│   └── schema.sql
├── data/
│   ├── inbox/
│   ├── processed/
│   └── failed/
└── tests/
    └── test_pipeline.py
```

No se crean interfaces, servicios o directorios adicionales hasta que una
necesidad del MVP los justifique.
