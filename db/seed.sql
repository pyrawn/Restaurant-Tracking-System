-- Table polygons are calibrated to the Beach Bar St. John live webcam feed
-- (1920x1080), not a generic/arbitrary layout. If the camera source changes,
-- these need to be recalibrated against a real frame from the new source.
--
-- These exact coordinates came from the project owner marking up a real
-- frame directly (originally annotated at 3840x2160, scaled by 0.96 to this
-- feed's 1920x1080), not an AI-guessed region.
INSERT INTO tables (name, capacity, polygon)
VALUES
    ('Table 1', 4, '[[149,543],[754,543],[754,966],[149,966]]'),
    ('Table 2', 4, '[[149,382],[488,382],[488,534],[149,534]]'),
    ('Table 3', 4, '[[334,103],[658,103],[658,426],[334,426]]'),
    ('Table 4', 4, '[[747,109],[1036,109],[1036,493],[747,493]]'),
    ('Table 5', 4, '[[1054,285],[1771,285],[1771,570],[1054,570]]')
ON CONFLICT (name) DO NOTHING;

-- Admin login. Password is "123", hashed with werkzeug's scrypt-based
-- generate_password_hash (never stored in plain text). Change it after
-- first login in a real deployment.
INSERT INTO users (username, password_hash)
VALUES ('victor', 'scrypt:32768:8:1$v8KHX1xpgJHFcM6C$028df6c6b3578b1c5409e02247db8dbead5468e998470de1f63f67b1dd521cd6c7f14783f8a67e4fb4f98d597ac39cbed8ddde2431bec15183e8cf4b4da1dd0f')
ON CONFLICT (username) DO NOTHING;

INSERT INTO waiters (name) VALUES
    ('Carlos Mendoza'),
    ('Ana Torres'),
    ('Luis Ramirez'),
    ('Sofia Herrera')
ON CONFLICT (name) DO NOTHING;

-- Sample shifts placed inside the live capture window recorded during
-- development (2026-09-09 06:47 UTC to 2026-09-10 02:28 UTC), so the
-- waiter stats report has real table_observations to aggregate against.
WITH s AS (
    INSERT INTO waiter_shifts (waiter_id, starts_at, ends_at)
    SELECT id, TIMESTAMPTZ '2026-09-09 07:00:00+00', TIMESTAMPTZ '2026-09-09 11:30:00+00'
    FROM waiters WHERE name = 'Carlos Mendoza'
    RETURNING id
)
INSERT INTO waiter_shift_tables (shift_id, table_id)
SELECT s.id, t.id FROM s, tables t WHERE t.name IN ('Table 1', 'Table 2');

WITH s AS (
    INSERT INTO waiter_shifts (waiter_id, starts_at, ends_at)
    SELECT id, TIMESTAMPTZ '2026-09-09 11:30:00+00', TIMESTAMPTZ '2026-09-09 16:00:00+00'
    FROM waiters WHERE name = 'Ana Torres'
    RETURNING id
)
INSERT INTO waiter_shift_tables (shift_id, table_id)
SELECT s.id, t.id FROM s, tables t WHERE t.name IN ('Table 3', 'Table 4');

WITH s AS (
    INSERT INTO waiter_shifts (waiter_id, starts_at, ends_at)
    SELECT id, TIMESTAMPTZ '2026-09-09 16:00:00+00', TIMESTAMPTZ '2026-09-09 20:30:00+00'
    FROM waiters WHERE name = 'Luis Ramirez'
    RETURNING id
)
INSERT INTO waiter_shift_tables (shift_id, table_id)
SELECT s.id, t.id FROM s, tables t WHERE t.name IN ('Table 1', 'Table 5');

WITH s AS (
    INSERT INTO waiter_shifts (waiter_id, starts_at, ends_at)
    SELECT id, TIMESTAMPTZ '2026-09-09 20:30:00+00', TIMESTAMPTZ '2026-09-10 01:00:00+00'
    FROM waiters WHERE name = 'Sofia Herrera'
    RETURNING id
)
INSERT INTO waiter_shift_tables (shift_id, table_id)
SELECT s.id, t.id FROM s, tables t WHERE t.name IN ('Table 2', 'Table 3');

WITH s AS (
    INSERT INTO waiter_shifts (waiter_id, starts_at, ends_at)
    SELECT id, TIMESTAMPTZ '2026-09-09 20:30:00+00', TIMESTAMPTZ '2026-09-10 01:00:00+00'
    FROM waiters WHERE name = 'Carlos Mendoza'
    RETURNING id
)
INSERT INTO waiter_shift_tables (shift_id, table_id)
SELECT s.id, t.id FROM s, tables t WHERE t.name = 'Table 5';

WITH s AS (
    INSERT INTO waiter_shifts (waiter_id, starts_at, ends_at)
    SELECT id, TIMESTAMPTZ '2026-09-10 01:00:00+00', TIMESTAMPTZ '2026-09-10 02:15:00+00'
    FROM waiters WHERE name = 'Ana Torres'
    RETURNING id
)
INSERT INTO waiter_shift_tables (shift_id, table_id)
SELECT s.id, t.id FROM s, tables t WHERE t.name = 'Table 4';
