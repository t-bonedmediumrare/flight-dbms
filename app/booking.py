"""booking.py — atomic flight booking transaction (§6.2).

All-or-nothing: any failure on any segment rolls back the entire booking.
Deadlock prevention: fare_class rows are locked in class_id order.
"""

import os
import random
import string
import sys
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.db import get_db_connection   # noqa: E402
from app.pricing import reprice        # noqa: E402

# ── Seat ranges — must match schema §5 ──────────────────────────────────────
# business: rows 1-4,  A-F → 24 seats
# premium:  rows 5-9,  A-F → 30 seats
# economy:  rows 10-40, A-F → 186 seats
_SEAT_RANGES: dict[str, tuple[range, str]] = {
    "business": (range(1, 5),   "ABCDEF"),
    "premium":  (range(5, 10),  "ABCDEF"),
    "economy":  (range(10, 41), "ABCDEF"),
}

_PNR_CHARS = string.ascii_uppercase + string.digits


# ── Helpers ──────────────────────────────────────────────────────────────────

def _generate_pnr() -> str:
    """Return a random 6-char alphanumeric PNR candidate."""
    return "".join(random.choices(_PNR_CHARS, k=6))


def _unique_pnr(cur) -> str:
    """Generate a PNR, retrying up to 10 times on collision."""
    for _ in range(10):
        pnr = _generate_pnr()
        cur.execute("SELECT 1 FROM booking WHERE pnr = %s", (pnr,))
        if cur.fetchone() is None:
            return pnr
    raise RuntimeError("Could not generate a unique PNR after 10 attempts")


def _assign_seats(cur, flight_id: int, class_name: str, n: int) -> list[str]:
    """Return n free seat numbers within the class row/letter range.

    Reads already-active tickets for this flight to avoid conflicts.
    Raises RuntimeError if fewer than n seats are free (should not happen
    if available_seats was accurate when locked).
    """
    rows, letters = _SEAT_RANGES[class_name]
    cur.execute(
        "SELECT seat_no FROM ticket WHERE flight_id = %s AND status = 'active'",
        (flight_id,),
    )
    taken = {r[0] for r in cur.fetchall()}

    assigned: list[str] = []
    for row in rows:
        for letter in letters:
            seat = f"{row}{letter}"
            if seat not in taken:
                assigned.append(seat)
            if len(assigned) == n:
                return assigned

    raise RuntimeError(
        f"Seat assignment failed for flight {flight_id} class '{class_name}': "
        f"only {len(assigned)} free seats but {n} needed"
    )


# ── Public API ────────────────────────────────────────────────────────────────

def book_ticket(
    user_id: int,
    segments: list[dict],
    passengers: list[dict],
    quoted_price: Decimal,
) -> dict:
    """Book a (possibly multi-hop) itinerary atomically.

    Args:
        user_id:      ID of the booking user.
        segments:     Ordered list of legs — each a dict with keys
                      ``flight_id`` (int) and ``class_id`` (int).
        passengers:   List of passenger dicts with keys
                      ``name`` (str), ``age`` (int), ``gender`` (str).
        quoted_price: Total price the user saw (sum over all segments × all
                      passengers). Used for the locked-price check.

    Returns one of:
        ``{'status': 'ok', 'pnr': str}``
        ``{'status': 'price_changed', 'new_price': Decimal}``
        ``{'status': 'no_seats', 'class_id': int}``
    """
    n = len(passengers)  # number of passengers

    conn = get_db_connection()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        # ── 1. Lock fare_class rows in class_id order (deadlock prevention) ──
        ordered_segments = sorted(segments, key=lambda s: s["class_id"])
        locked: dict[int, dict] = {}  # class_id -> {available_seats, current_price, class_name}

        for seg in ordered_segments:
            cid = seg["class_id"]
            cur.execute(
                "SELECT available_seats, current_price, class_name "
                "FROM fare_class WHERE class_id = %s FOR UPDATE",
                (cid,),
            )
            row = cur.fetchone()
            if row is None:
                raise ValueError(f"fare_class {cid} not found")
            avail, cur_price, class_name = row
            locked[cid] = {
                "available_seats": avail,
                "current_price":   cur_price,
                "class_name":      class_name,
            }

            # ── 2. Seat availability check (rollback → offer waitlist) ───────
            if avail < n:
                conn.rollback()
                return {"status": "no_seats", "class_id": cid}

        # ── 3. Price-mismatch guard ──────────────────────────────────────────
        # Total = sum of current_price across every segment × number of passengers.
        locked_total = sum(locked[s["class_id"]]["current_price"] for s in segments) * n
        locked_total = Decimal(str(locked_total))

        if locked_total != Decimal(str(quoted_price)):
            conn.rollback()
            return {"status": "price_changed", "new_price": locked_total}

        # ── 4. Generate unique PNR ───────────────────────────────────────────
        pnr = _unique_pnr(cur)

        # ── 5. INSERT booking ────────────────────────────────────────────────
        cur.execute(
            "INSERT INTO booking (pnr, user_id, status, total_amount) "
            "VALUES (%s, %s, 'confirmed', %s)",
            (pnr, user_id, locked_total),
        )

        # ── 6. INSERT passengers ─────────────────────────────────────────────
        passenger_ids: list[int] = []
        for p in passengers:
            cur.execute(
                "INSERT INTO passenger (pnr, name, age, gender) "
                "VALUES (%s, %s, %s, %s) RETURNING passenger_id",
                (pnr, p["name"], p["age"], p["gender"]),
            )
            passenger_ids.append(cur.fetchone()[0])

        # ── 7. Per-segment: decrement seats, insert segment + tickets ────────
        # Iterate in the *original* (itinerary) order for segment insertion;
        # locks were already acquired in class_id order above.
        for seg in segments:
            fid = seg["flight_id"]
            cid = seg["class_id"]
            cls   = locked[cid]
            price = cls["current_price"]

            # booking_segment: price_paid = price per passenger × n
            cur.execute(
                "INSERT INTO booking_segment (pnr, flight_id, class_id, price_paid) "
                "VALUES (%s, %s, %s, %s) RETURNING segment_id",
                (pnr, fid, cid, price * n),
            )
            segment_id = cur.fetchone()[0]

            # Decrement available seats.
            cur.execute(
                "UPDATE fare_class SET available_seats = available_seats - %s "
                "WHERE class_id = %s",
                (n, cid),
            )

            # Assign seat numbers from the class row/letter range.
            seats = _assign_seats(cur, fid, cls["class_name"], n)

            # One ticket per passenger per segment.
            for pid, seat_no in zip(passenger_ids, seats):
                cur.execute(
                    "INSERT INTO ticket "
                    "(segment_id, passenger_id, flight_id, class_id, seat_no, status) "
                    "VALUES (%s, %s, %s, %s, %s, 'active')",
                    (segment_id, pid, fid, cid, seat_no),
                )

            # Reprice this class now that a seat has been sold (§6.3).
            reprice(cur, cid, reason="sale")

        # ── 8. Simulated payment ─────────────────────────────────────────────
        cur.execute(
            "INSERT INTO payment (pnr, amount, method, status) "
            "VALUES (%s, %s, 'card', 'paid')",
            (pnr, locked_total),
        )

        conn.commit()
        return {"status": "ok", "pnr": pnr}

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
