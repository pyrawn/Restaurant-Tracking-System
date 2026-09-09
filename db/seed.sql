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
