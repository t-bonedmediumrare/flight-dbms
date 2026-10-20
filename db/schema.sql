-- Schema for Flight Route & Fare Optimization System
-- Run with: psql $DATABASE_URL -f db/schema.sql

-- ── ENUMs ──────────────────────────────────────────────────────────────────

CREATE TYPE flight_status_enum    AS ENUM ('scheduled', 'delayed', 'cancelled', 'landed');
CREATE TYPE class_name_enum       AS ENUM ('economy', 'premium', 'business');
CREATE TYPE booking_status_enum   AS ENUM ('confirmed', 'cancelled', 'waitlisted');
CREATE TYPE ticket_status_enum    AS ENUM ('active', 'cancelled');
CREATE TYPE payment_status_enum   AS ENUM ('paid', 'refunded', 'pending');
CREATE TYPE waitlist_status_enum  AS ENUM ('waiting', 'fulfilled', 'cancelled');

-- ── TABLES ─────────────────────────────────────────────────────────────────

-- IATA airport reference data (code, coordinates, location).
CREATE TABLE airport (
    code    CHAR(3)      PRIMARY KEY,
    name    TEXT         NOT NULL,
    city    TEXT         NOT NULL,
    country TEXT         NOT NULL,
    lat     NUMERIC(9,6) NOT NULL,
    lon     NUMERIC(9,6) NOT NULL
);

-- Registered travellers with hashed passwords.
CREATE TABLE users (
    user_id       SERIAL       PRIMARY KEY,
    name          TEXT         NOT NULL,
    email         TEXT         NOT NULL UNIQUE,
    password_hash TEXT         NOT NULL,
    phone         TEXT,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Elevated users who have admin access.
CREATE TABLE admin (
    admin_id  SERIAL  PRIMARY KEY,
    user_id   INT     NOT NULL UNIQUE REFERENCES users(user_id) ON DELETE CASCADE
);

-- A scheduled flight leg between two airports.
CREATE TABLE flight (
    flight_id  SERIAL               PRIMARY KEY,
    flight_no  TEXT                 NOT NULL,
    origin     CHAR(3)              NOT NULL REFERENCES airport(code),
    dest       CHAR(3)              NOT NULL REFERENCES airport(code),
    dep_time   TIMESTAMPTZ          NOT NULL,
    arr_time   TIMESTAMPTZ          NOT NULL,
    status     flight_status_enum   NOT NULL DEFAULT 'scheduled',
    CHECK (origin <> dest),
    CHECK (arr_time > dep_time)
);

-- Seat class inventory and dynamic pricing per flight.
CREATE TABLE fare_class (
    class_id        SERIAL           PRIMARY KEY,
    flight_id       INT              NOT NULL REFERENCES flight(flight_id) ON DELETE CASCADE,
    class_name      class_name_enum  NOT NULL,
    total_seats     INT              NOT NULL,
    available_seats INT              NOT NULL,
    base_price      NUMERIC(10,2)    NOT NULL,
    current_price   NUMERIC(10,2)    NOT NULL,
    UNIQUE (flight_id, class_name),
    CHECK (available_seats >= 0),
    CHECK (available_seats <= total_seats)
);

-- A booking record (one or more segments, one or more passengers).
CREATE TABLE booking (
    pnr          CHAR(6)              PRIMARY KEY,
    user_id      INT                  NOT NULL REFERENCES users(user_id),
    status       booking_status_enum  NOT NULL DEFAULT 'confirmed',
    total_amount NUMERIC(10,2)        NOT NULL,
    created_at   TIMESTAMPTZ          NOT NULL DEFAULT NOW()
);

-- One flight leg within a multi-hop booking.
CREATE TABLE booking_segment (
    segment_id  SERIAL  PRIMARY KEY,
    pnr         CHAR(6) NOT NULL REFERENCES booking(pnr) ON DELETE CASCADE,
    flight_id   INT     NOT NULL REFERENCES flight(flight_id),
    class_id    INT     NOT NULL REFERENCES fare_class(class_id),
    price_paid  NUMERIC(10,2) NOT NULL
);

-- Passenger details attached to a booking.
CREATE TABLE passenger (
    passenger_id  SERIAL  PRIMARY KEY,
    pnr           CHAR(6) NOT NULL REFERENCES booking(pnr) ON DELETE CASCADE,
    name          TEXT    NOT NULL,
    age           INT     NOT NULL,
    gender        TEXT    NOT NULL
);

-- One issued ticket per passenger per flight segment.
CREATE TABLE ticket (
    ticket_id    SERIAL               PRIMARY KEY,
    segment_id   INT                  NOT NULL REFERENCES booking_segment(segment_id) ON DELETE CASCADE,
    passenger_id INT                  NOT NULL REFERENCES passenger(passenger_id),
    flight_id    INT                  NOT NULL REFERENCES flight(flight_id),
    class_id     INT                  NOT NULL REFERENCES fare_class(class_id),
    seat_no      TEXT                 NOT NULL,
    status       ticket_status_enum   NOT NULL DEFAULT 'active'
);

-- Guard: no two active tickets may share the same seat on the same flight.
CREATE UNIQUE INDEX ticket_active_seat_uidx
    ON ticket (flight_id, seat_no)
    WHERE status = 'active';

-- Simulated payment record for a booking.
CREATE TABLE payment (
    payment_id  SERIAL                PRIMARY KEY,
    pnr         CHAR(6)               NOT NULL REFERENCES booking(pnr),
    amount      NUMERIC(10,2)         NOT NULL,
    method      TEXT                  NOT NULL,
    status      payment_status_enum   NOT NULL DEFAULT 'paid',
    paid_at     TIMESTAMPTZ           NOT NULL DEFAULT NOW()
);

-- Queue of users waiting for a seat when a class is full.
CREATE TABLE waitlist (
    wl_id           SERIAL                PRIMARY KEY,
    user_id         INT                   NOT NULL REFERENCES users(user_id),
    class_id        INT                   NOT NULL REFERENCES fare_class(class_id),
    seats_requested INT                   NOT NULL CHECK (seats_requested > 0),
    position        INT                   NOT NULL,
    created_at      TIMESTAMPTZ           NOT NULL DEFAULT NOW(),
    status          waitlist_status_enum  NOT NULL DEFAULT 'waiting'
);

-- Audit log of every price change with its reason.
CREATE TABLE price_history (
    ph_id      SERIAL        PRIMARY KEY,
    class_id   INT           NOT NULL REFERENCES fare_class(class_id),
    old_price  NUMERIC(10,2) NOT NULL,
    new_price  NUMERIC(10,2) NOT NULL,
    reason     TEXT,
    changed_at TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

-- Key-value store for external API responses (10-min TTL cache).
CREATE TABLE api_cache (
    cache_key  TEXT        PRIMARY KEY,
    payload    JSONB       NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── INDEXES ────────────────────────────────────────────────────────────────

CREATE INDEX flight_origin_dep_idx  ON flight      (origin, dep_time);
CREATE INDEX flight_dest_idx        ON flight      (dest);
CREATE INDEX fare_class_flight_idx  ON fare_class  (flight_id);
CREATE INDEX booking_user_idx       ON booking     (user_id);
CREATE INDEX price_history_cls_idx  ON price_history (class_id, changed_at);
