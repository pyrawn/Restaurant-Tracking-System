CREATE TABLE IF NOT EXISTS media_inputs (
    id BIGSERIAL PRIMARY KEY,
    media_type TEXT NOT NULL CHECK (media_type IN ('image', 'video')),
    source_path TEXT NOT NULL,
    media_hash TEXT NOT NULL UNIQUE,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'processed', 'failed')),
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS tables (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    capacity INTEGER NOT NULL CHECK (capacity > 0),
    polygon JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS frames (
    id BIGSERIAL PRIMARY KEY,
    media_input_id BIGINT NOT NULL REFERENCES media_inputs(id),
    frame_index INTEGER NOT NULL CHECK (frame_index >= 0),
    offset_ms INTEGER NOT NULL DEFAULT 0 CHECK (offset_ms >= 0),
    image_path TEXT NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'processed', 'failed')),
    UNIQUE (media_input_id, frame_index)
);

CREATE TABLE IF NOT EXISTS table_observations (
    id BIGSERIAL PRIMARY KEY,
    frame_id BIGINT NOT NULL REFERENCES frames(id),
    table_id BIGINT NOT NULL REFERENCES tables(id),
    people_count INTEGER NOT NULL CHECK (people_count >= 0),
    occupied BOOLEAN NOT NULL,
    confidence DOUBLE PRECISION NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    model_version TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (frame_id, table_id)
);

CREATE INDEX IF NOT EXISTS table_observations_latest_idx
    ON table_observations (table_id, processed_at DESC);

CREATE OR REPLACE VIEW latest_table_state AS
WITH latest_observations AS (
    SELECT DISTINCT ON (table_id)
        table_id,
        people_count,
        occupied,
        confidence,
        model_version,
        processed_at
    FROM table_observations
    ORDER BY table_id, processed_at DESC
)
SELECT
    t.id AS table_id,
    t.name AS table_name,
    t.capacity,
    o.people_count,
    o.occupied,
    o.confidence,
    o.model_version,
    o.processed_at
FROM tables AS t
LEFT JOIN latest_observations AS o ON o.table_id = t.id;
