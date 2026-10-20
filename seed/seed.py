"""seed.py — load airports, generate 14-day flight schedule, create demo users.

Re-runnable: truncates all mutable tables (FK-safe order) then reloads.
Run: python seed/seed.py  (from repo root, .env must be present)
"""

import csv
import os
import random
import string
import sys
from datetime import date, datetime, timedelta, timezone

from werkzeug.security import generate_password_hash

# Allow importing app/db.py from the repo root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.db import get_db_connection  # noqa: E402

# ── Seat ranges (must match §5) ──────────────────────────────────────────────
# business rows 1-4  A-F  → 4×6 = 24 seats
# premium  rows 5-9  A-F  → 5×6 = 30 seats
# economy  rows 10-40 A-F → 31×6 = 186 seats
SEAT_RANGES = {
    "business": {"rows": range(1, 5),   "letters": "ABCDEF"},
    "premium":  {"rows": range(5, 10),  "letters": "ABCDEF"},
    "economy":  {"rows": range(10, 41), "letters": "ABCDEF"},
}
TOTAL_SEATS = {k: len(v["rows"]) * len(v["letters"]) for k, v in SEAT_RANGES.items()}

# ── Base prices (USD-equivalent) ────────────────────────────────────────────
BASE_PRICES = {
    "short":        {"economy": 60,  "premium": 130, "business": 250},
    "medium":       {"economy": 120, "premium": 260, "business": 500},
    "long":         {"economy": 320, "premium": 650, "business": 1200},
    "international":{"economy": 480, "premium": 950, "business": 1800},
}

# ── Hub airports (3 hubs guarantee multi-hop paths) ──────────────────────────
HUBS = ["DEL", "BOM", "BLR"]

# ── Route table: (origin, dest, duration_minutes, segment_type) ─────────────
# Each tuple generates two flights/day (morning + evening); add a second entry
# for extra-busy hub↔hub pairs to push towards ~80 flights/day.
ROUTES = [
    # Hub ↔ Hub (2 daily + 1 extra peak = 3/day each direction → 6)
    ("DEL", "BOM", 130, "medium"),
    ("DEL", "BOM", 130, "medium"),   # extra peak
    ("DEL", "BLR", 160, "medium"),
    ("DEL", "BLR", 160, "medium"),   # extra peak
    ("BOM", "BLR",  90, "short"),
    ("BOM", "BLR",  90, "short"),    # extra peak
    # DEL spokes (1/day each direction → 2)
    ("DEL", "MAA", 165, "medium"),
    ("DEL", "HYD", 140, "medium"),
    ("DEL", "CCU", 120, "medium"),
    ("DEL", "AMD",  90, "short"),
    ("DEL", "JAI",  70, "short"),
    ("DEL", "LKO",  75, "short"),
    ("DEL", "ATQ",  60, "short"),
    ("DEL", "IXC",  55, "short"),
    # BOM spokes
    ("BOM", "MAA",  90, "short"),
    ("BOM", "HYD",  75, "short"),
    ("BOM", "GOI",  60, "short"),
    ("BOM", "PNQ",  35, "short"),
    ("BOM", "COK", 110, "medium"),
    ("BOM", "AMD",  65, "short"),
    ("BOM", "CCU", 140, "medium"),
    # BLR spokes
    ("BLR", "MAA",  55, "short"),
    ("BLR", "HYD",  70, "short"),
    ("BLR", "GOI",  60, "short"),
    ("BLR", "COK",  70, "short"),
    ("BLR", "PNQ",  90, "short"),
    ("BLR", "CCU", 145, "medium"),
    # International
    ("DEL", "DXB", 200, "international"),
    ("DEL", "LHR", 510, "international"),
    ("DEL", "JFK", 870, "international"),
    ("DEL", "BKK", 280, "international"),
    ("BOM", "DXB", 185, "international"),
    ("BOM", "SIN", 340, "international"),
    ("BOM", "HKG", 370, "international"),
    ("BLR", "SIN", 330, "international"),
    ("BLR", "DXB", 215, "international"),
]

# Departure slots (IST offsets from midnight) for morning and evening waves.
MORNING_SLOTS  = [330, 360, 390, 420, 450]   # 05:30 – 07:30
EVENING_SLOTS  = [930, 960, 990, 1020, 1060] # 15:30 – 17:40
# Long-haul: use different slots to avoid impossible connections.
INTL_SLOTS     = [120, 180, 1200, 1260]       # 02:00, 03:00, 20:00, 21:00

IST = timezone(timedelta(hours=5, minutes=30))


def _dep_slot(seg_type: str, rng: random.Random) -> int:
    """Return a random departure offset (minutes from midnight IST)."""
    if seg_type == "international":
        return rng.choice(INTL_SLOTS)
    return rng.choice(MORNING_SLOTS + EVENING_SLOTS)


def _flight_no(origin: str, dest: str, day_offset: int, idx: int) -> str:
    return f"FX{origin}{dest}{day_offset:02d}{idx:02d}"


def truncate_tables(cur) -> None:
    """Delete all seeded data in FK-safe reverse order."""
    tables = [
        "api_cache", "price_history", "waitlist", "payment",
        "ticket", "passenger", "booking_segment", "booking",
        "fare_class", "flight", "admin", "users", "airport",
    ]
    cur.execute(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE")


def load_airports(cur, csv_path: str) -> None:
    """Insert airport rows from CSV."""
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [(r["code"], r["name"], r["city"], r["country"],
                 float(r["lat"]), float(r["lon"])) for r in reader]
    cur.executemany(
        "INSERT INTO airport (code, name, city, country, lat, lon) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        rows,
    )
    print(f"  Loaded {len(rows)} airports.")


def generate_flights(cur, today: date, rng: random.Random) -> int:
    """Generate ~80 flights/day for 14 days; insert flights + fare classes."""
    flight_count = 0
    fare_count   = 0
    for day_offset in range(14):
        day = today + timedelta(days=day_offset)
        day_idx: dict[tuple, int] = {}

        for i, (orig, dest, dur_min, seg_type) in enumerate(ROUTES):
            key = (orig, dest)
            day_idx[key] = day_idx.get(key, 0) + 1
            idx = day_idx[key]

            dep_min = _dep_slot(seg_type, rng)
            dep_dt  = datetime(day.year, day.month, day.day,
                               dep_min // 60, dep_min % 60, tzinfo=IST)
            arr_dt  = dep_dt + timedelta(minutes=dur_min)
            fno     = _flight_no(orig, dest, day_offset, idx)

            cur.execute(
                "INSERT INTO flight (flight_no, origin, dest, dep_time, arr_time, status) "
                "VALUES (%s, %s, %s, %s, %s, 'scheduled') RETURNING flight_id",
                (fno, orig, dest, dep_dt, arr_dt),
            )
            flight_id = cur.fetchone()[0]
            flight_count += 1

            # Also add the reverse direction.
            r_dep_min = _dep_slot(seg_type, rng)
            r_dep_dt  = datetime(day.year, day.month, day.day,
                                 r_dep_min // 60, r_dep_min % 60, tzinfo=IST)
            r_arr_dt  = r_dep_dt + timedelta(minutes=dur_min)
            r_fno     = _flight_no(dest, orig, day_offset, idx)

            cur.execute(
                "INSERT INTO flight (flight_no, origin, dest, dep_time, arr_time, status) "
                "VALUES (%s, %s, %s, %s, %s, 'scheduled') RETURNING flight_id",
                (r_fno, dest, orig, r_dep_dt, r_arr_dt),
            )
            r_flight_id = cur.fetchone()[0]
            flight_count += 1

            bp = BASE_PRICES[seg_type]
            for fid in (flight_id, r_flight_id):
                for cls in ("business", "premium", "economy"):
                    price = bp[cls] + rng.randint(-10, 10)
                    cur.execute(
                        "INSERT INTO fare_class "
                        "(flight_id, class_name, total_seats, available_seats, "
                        " base_price, current_price) "
                        "VALUES (%s, %s, %s, %s, %s, %s)",
                        (fid, cls, TOTAL_SEATS[cls], TOTAL_SEATS[cls],
                         price, price),
                    )
                    fare_count += 1

    print(f"  Generated {flight_count} flights, {fare_count} fare-class rows.")
    return flight_count


def create_users(cur) -> None:
    """Insert 2 demo users and 1 admin user."""
    users = [
        ("Alice Demo",  "alice@demo.com",  "pass1234", "9876543210"),
        ("Bob Demo",    "bob@demo.com",    "pass1234", "9876543211"),
        ("Admin User",  "admin@demo.com",  "adminpass","9000000001"),
    ]
    user_ids = []
    for name, email, pw, phone in users:
        cur.execute(
            "INSERT INTO users (name, email, password_hash, phone) "
            "VALUES (%s, %s, %s, %s) RETURNING user_id",
            (name, email, generate_password_hash(pw), phone),
        )
        user_ids.append(cur.fetchone()[0])
        print(f"  User created: {email}")

    # Make the last user (admin@demo.com) an admin.
    cur.execute("INSERT INTO admin (user_id) VALUES (%s)", (user_ids[-1],))
    print(f"  Admin role granted to: {users[-1][1]}")


def main() -> None:
    csv_path = os.path.join(os.path.dirname(__file__), "airports.csv")
    rng      = random.Random(42)   # deterministic; change seed for variety
    today    = date.today()

    print("Connecting to database…")
    conn = get_db_connection()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        print("Truncating tables…")
        truncate_tables(cur)

        print("Loading airports…")
        load_airports(cur, csv_path)

        print("Generating flights…")
        generate_flights(cur, today, rng)

        print("Creating users…")
        create_users(cur)

        conn.commit()
        print("Seed complete.")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
