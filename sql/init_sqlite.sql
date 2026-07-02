-- ============================================================
-- SmartVoyage SQLite 初始化脚本（零依赖 demo 用）
-- 与 sql/init_database.sql (MySQL) 保持同构，仅保留使用中的字段
-- ============================================================

DROP TABLE IF EXISTS weather_data;
CREATE TABLE weather_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    city TEXT NOT NULL,
    fx_date TEXT NOT NULL,               -- 预报日期 YYYY-MM-DD
    temp_max INTEGER,
    temp_min INTEGER,
    text_day TEXT,
    text_night TEXT,
    wind_dir_day TEXT,
    wind_scale_day TEXT,
    humidity INTEGER,
    precip REAL,
    uv_index INTEGER,
    vis INTEGER,
    UNIQUE (city, fx_date)
);

DROP TABLE IF EXISTS train_tickets;
CREATE TABLE train_tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    departure_city TEXT NOT NULL,
    arrival_city TEXT NOT NULL,
    departure_time TEXT NOT NULL,        -- YYYY-MM-DD HH:MM:SS
    arrival_time TEXT NOT NULL,
    train_number TEXT NOT NULL,
    seat_type TEXT NOT NULL,
    total_seats INTEGER NOT NULL DEFAULT 0,
    remaining_seats INTEGER NOT NULL DEFAULT 0,
    price REAL NOT NULL DEFAULT 0,
    UNIQUE (train_number, departure_time, seat_type)
);

DROP TABLE IF EXISTS flight_tickets;
CREATE TABLE flight_tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    departure_city TEXT NOT NULL,
    arrival_city TEXT NOT NULL,
    departure_time TEXT NOT NULL,
    arrival_time TEXT NOT NULL,
    flight_number TEXT NOT NULL,
    cabin_type TEXT NOT NULL,
    total_seats INTEGER NOT NULL DEFAULT 0,
    remaining_seats INTEGER NOT NULL DEFAULT 0,
    price REAL NOT NULL DEFAULT 0,
    UNIQUE (flight_number, departure_time, cabin_type)
);

DROP TABLE IF EXISTS concert_tickets;
CREATE TABLE concert_tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    artist TEXT NOT NULL,
    city TEXT NOT NULL,
    venue TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    ticket_type TEXT NOT NULL,
    total_seats INTEGER NOT NULL DEFAULT 0,
    remaining_seats INTEGER NOT NULL DEFAULT 0,
    price REAL NOT NULL DEFAULT 0,
    UNIQUE (artist, city, start_time, ticket_type)
);

DROP TABLE IF EXISTS orders;
CREATE TABLE orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_no TEXT NOT NULL UNIQUE,
    ticket_type TEXT NOT NULL,           -- train / flight / concert
    ticket_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    unit_price REAL NOT NULL DEFAULT 0,
    total_price REAL NOT NULL DEFAULT 0,
    contact_name TEXT NOT NULL,
    contact_phone TEXT NOT NULL,
    contact_id_card TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',       -- pending / paid / cancelled / refunded / completed
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
);
