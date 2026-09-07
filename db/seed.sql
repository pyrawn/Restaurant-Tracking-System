INSERT INTO waiters (code, display_name, skin_reference_path)
VALUES
    ('waiter_1', 'Waiter 1', 'data/skins/waiter_1.png'),
    ('waiter_2', 'Waiter 2', 'data/skins/waiter_2.png'),
    ('waiter_3', 'Waiter 3', 'data/skins/waiter_3.png'),
    ('waiter_4', 'Waiter 4', 'data/skins/waiter_4.png')
ON CONFLICT (code) DO NOTHING;

INSERT INTO tables (name, capacity, polygon)
VALUES
    ('Table 1', 4, '[[10,10],[30,10],[30,30],[10,30]]'),
    ('Table 2', 4, '[[40,10],[60,10],[60,30],[40,30]]'),
    ('Table 3', 4, '[[10,40],[30,40],[30,60],[10,60]]'),
    ('Table 4', 4, '[[40,40],[60,40],[60,60],[40,60]]')
ON CONFLICT (name) DO NOTHING;
