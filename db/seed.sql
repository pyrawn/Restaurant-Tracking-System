-- Table polygons are calibrated to the Beach Bar St. John live webcam feed
-- (1920x1080), not a generic/arbitrary layout. If the camera source changes,
-- these need to be recalibrated against a real frame from the new source.
INSERT INTO tables (name, capacity, polygon)
VALUES
    ('Right Front Table', 4, '[[1150,460],[1950,460],[1950,780],[1150,780]]'),
    ('Behind Right-Middle Table', 4, '[[1580,470],[1900,470],[1900,670],[1580,670]]'),
    ('Left Table', 4, '[[250,460],[720,460],[720,980],[250,980]]'),
    ('Middle Bar Table', 4, '[[420,340],[900,340],[900,590],[420,590]]'),
    ('Background Left Table', 4, '[[380,140],[830,140],[830,300],[380,300]]')
ON CONFLICT (name) DO NOTHING;
