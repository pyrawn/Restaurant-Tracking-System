# Handoff — Umizumi 2 → Umizumi 3

Fecha: 2026-09-07  
Proyecto: Restaurant Tracking System  
Equipo: Umizumi

## Objetivo de este handoff

Implementar la inferencia (detección de ocupación y conteo de personas usando Ultralytics/OpenCV) y transformar esos datos para cargarlos en PostgreSQL. Umizumi 3 es responsable del modelo, la transformación y la carga (pipeline ML).

Prioridad inmediata:

1. Leer todos los `frames` en estado `pending`.
2. Realizar inferencia utilizando un modelo preentrenado.
3. Evaluar colisiones de centroides con los polígonos de las mesas.
4. Generar y persistir las observaciones en la tabla `table_observations`.

## Estado actual

Ya existe el pipeline de ingestión y la normalización:

- El servicio `worker` ya lee medios (`.jpg`, `.png`, `.mp4`) de `data/inbox/`.
- Cada medio se registra en `media_inputs` (validado mediante hash SHA-256 para evitar duplicados).
- Los medios válidos se normalizan copiándose en `data/processed/<media_hash>/<frame_index>.jpg`.
- Por cada imagen o _frame_ de video normalizado, existe un registro en la tabla `frames` con `status = pending`.
- La variable de entorno `DATABASE_URL` ya está correctamente configurada para el worker en `compose.yaml`.
- OpenCV ya está instalado (`opencv-python-headless`) en los requerimientos.

## No cambiar

- No modificar la lógica de ingestión de medios (`get_file_hash`, `process_image`, `process_video`).
- No alterar las carpetas `data/inbox` ni `data/processed`.
- No modificar el esquema de `frames` o `media_inputs`.
- No cambiar la estructura de la base de datos a menos que sea estrictamente necesario para el modelo.
- No desarrollar nada relacionado a Flask (eso es para Umizumi 4).

## Contrato de entrada

Umizumi 3 consume información desde PostgreSQL (tabla `frames`) y disco (carpeta `data/processed/`).

Debe consultar:
```sql
SELECT id, image_path, media_input_id, frame_index, captured_at 
FROM frames 
WHERE status = 'pending'
```

Las mesas fijas contra las que se deben calcular las colisiones están en la tabla `tables`:
```sql
SELECT id, name, capacity, polygon FROM tables
```

## Salida esperada

Para cada frame consultado, el modelo debe generar observaciones por mesa.
Cada observación debe persistirse en `table_observations` con la siguiente estructura mínima (siguiendo el esquema):

```text
frame_id           = <ID del frame procesado>
table_id           = <ID de la mesa evaluada>
people_count       = <conteo de personas en el polígono>
occupied           = <true si people_count > 0 else false>
confidence         = <confianza de la inferencia, entre 0 y 1>
detected_waiter_id = <ID del mesero si detectado, o NULL>
model_version      = "configured-model-version" (o string fijo)
```

Al terminar de generar todas las observaciones del frame, el registro de la tabla `frames` correspondiente debe actualizarse:
```text
status = 'processed'
```
*(Si ocurre un error insalvable durante la inferencia para ese frame, pasarlo a `status = 'failed'`)*.

## Archivos a revisar

Punto de entrada:

- `app/worker.py`: Añadir la función de coordinación que lea los frames `pending`, llame a la inferencia y escriba los resultados (ej. función `process_pending_frames()`).
- `app/db.py`: Añadir funciones para obtener frames `pending`, obtener las mesas y persistir las observaciones (`insert_table_observation`).
- `requirements.txt`: Agregar `ultralytics` u otras dependencias necesarias para la red neuronal.

## Criterios de aceptación

- [ ] El worker de Umizumi 3 toma los `frames` en estado `pending` y no procesa los `processed` ni `failed`.
- [ ] La inferencia identifica personas y utiliza el polígono de las mesas para filtrar a qué mesa pertenece la detección (el punto inferior central cae en el polígono).
- [ ] Las inserciones a `table_observations` son atómicas (todas las observaciones del frame entran, o ninguna).
- [ ] Tras un procesamiento exitoso, el frame queda marcado como `processed`.
- [ ] Las dependencias extras como `ultralytics` o `torch` quedan empaquetadas en `requirements.txt` y construyen bien en el `Dockerfile`.

## Pruebas mínimas

Agregar pruebas con `unittest` para:

- Inferencia mockeada con detección positiva -> Genera un registro en `table_observations` con `occupied = true`.
- Inferencia mockeada con detección vacía -> Genera un registro en `table_observations` con `occupied = false` y `people_count = 0`.
- Frame inexistente o ilegible en disco -> El estado del frame cambia a `failed`.
- Prueba de colisión matemática: asegurar que la lógica del polígono evalúa si un punto de coordenada está o no dentro de la mesa.

## Cómo ejecutar

Desde la raíz del repositorio, levantar todo:

```bash
docker compose up --build -d
```

Validar los logs del worker para ver que la inferencia sucede:

```bash
docker compose logs -f worker
```

Simular entrada:

```bash
cp /ruta/a/captura.png data/inbox/
```

Revisar la base de datos y comprobar que `table_observations` se puebla correctamente tras la ingestión.

## Entrega al siguiente Umizumi (Umizumi 4)

El handoff final para Umizumi 4 debe incluir:

- Archivos modificados en este paso.
- Resultados de pruebas que corroboren que `table_observations` tiene data real o útil.
- Confirmación de que la vista de PostgreSQL `latest_table_state` arroja la data generada.
- Cualquier limitación (por ejemplo, FPS reales de procesamiento del modelo).

La salida de Umizumi 3 es el corazón del sistema: la vista `latest_table_state` completamente poblada, lista para ser consumida por el backend de Flask en Umizumi 4.
