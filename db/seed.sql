INSERT INTO tables (name, capacity, polygon)
VALUES
    ('Table 1', 4, '[[10,10],[30,10],[30,30],[10,30]]'),
    ('Table 2', 4, '[[40,10],[60,10],[60,30],[40,30]]'),
    ('Table 3', 4, '[[10,40],[30,40],[30,60],[10,60]]'),
    ('Table 4', 4, '[[40,40],[60,40],[60,60],[40,60]]')
ON CONFLICT (name) DO NOTHING;
