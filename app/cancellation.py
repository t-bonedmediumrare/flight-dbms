"""cancellation.py — booking cancellation, refund, and waitlist promotion (§6.4).

All steps run in a single transaction:
  lock booking + fare_class rows → mark cancelled → free seats →
  refund → reprice → waitlist promotion (direct flights only).
"""

import os
import random
import string
import sys
from datetime import datetime, timezone
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.db import get_db_connection  # noqa: E402
from app.pricing import reprice       # noqa: E402

_PNR_CHARS = string.ascii_uppercase + string.digits

# Seat ranges — must match §5 and booking.py.
_SEAT_RANGES: dict[str, tuple[range, str]] = {
    "business": (range(1, 5),   "ABCDEF"),
    "premium":  (range(5, 10),  "ABCDEF"),
    "economy":  (range(10, 41), "ABCDEF"),
}


# ── Private helpers ───────────────────────────────────────────────────────────

def _unique_pnr(cur) -> str:
    """Generate a unique 6-char alphanumeric PNR."""
    for _ in range(10):
        pnr = "".join(random.choices(_PNR_CHARS, k=6))
        cur.execute("SELECT 1 FROM booking WHERE pnr = %s", (pnr,))
        if cur.fetchone() is None:
            return pnr
    raise RuntimeError("Could not generate unique PNR after 10 attempts")


def _assign_seats(cur, flight_id: int, class_name: str, n: int) -> list[str]:
    """Return n free seat numbers within the class row/letter range."""
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


def _refund_fraction(earliest_dep: datetime) -> Decimal:
    """100% if >7 days, 50% if 2-7 days, 0% if <48 h."""
    now = datetime.now(timezone.utc)
    if earliest_dep.tzinfo is None:
        earliest_dep = earliest_dep.replace(tzinfo=timezone.utc)
    days = (earliest_dep - now).total_seconds() / 86_400
    if days > 7:
        return Decimal("1.00")
    if days >= 2:
        return Decimal("0.50")
    return Decimal("0.00")


# ── Public API ────────────────────────────────────────────────────────────────

def cancel_booking(pnr: str) -> dict:
    """Cancel a confirmed booking and attempt waitlist promotion.

    Returns one of:
        {'status': 'ok', 'refund': Decimal, 'promoted_pnr': str | None}
        {'status': 'not_found'}
        {'status': 'already_cancelled'}
    """
    conn = get_db_connection()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        # ── 1. Lock the booking row ───────────────────────────────────────────
        cur.execute(
            "SELECT user_id, status, total_amount "
            "FROM booking WHERE pnr = %s FOR UPDATE",
            (pnr,),
        )
        row = cur.fetchone()
        if row is None:
            conn.rollback()
            return {"status": "not_found"}
        _user_id, bk_status, total_amount = row

        if bk_status == "cancelled":
            conn.rollback()
            return {"status": "already_cancelled"}

        # ── 2. Fetch segment metadata (needed for locking and refund date) ────
        cur.execute(
            """
            SELECT bs.segment_id, bs.flight_id, bs.class_id,
                   fc.class_name, f.dep_time
            FROM   booking_segment bs
            JOIN   flight          f   ON f.flight_id  = bs.flight_id
            JOIN   fare_class      fc  ON fc.class_id  = bs.class_id
            WHERE  bs.pnr = %s
            ORDER  BY bs.class_id          -- consistent lock order → no deadlock
            """,
            (pnr,),
        )
        segments = cur.fetchall()
        # segments: [(segment_id, flight_id, class_id, class_name, dep_time), …]

        # ── 3. Lock fare_class rows in class_id order ─────────────────────────
        for _, _, class_id, _, _ in segments:
            cur.execute(
                "SELECT 1 FROM fare_class WHERE class_id = %s FOR UPDATE",
                (class_id,),
            )

        # ── 4. Count active tickets per segment BEFORE cancelling them ────────
        #       (so we know exactly how many seats each class gets back)
        cur.execute(
            """
            SELECT bs.class_id, bs.flight_id, fc.class_name,
                   COUNT(t.ticket_id) AS freed
            FROM   booking_segment bs
            JOIN   ticket          t   ON t.segment_id  = bs.segment_id
                                      AND t.status       = 'active'
            JOIN   fare_class      fc  ON fc.class_id   = bs.class_id
            WHERE  bs.pnr = %s
            GROUP  BY bs.class_id, bs.flight_id, fc.class_name
            """,
            (pnr,),
        )
        freed_rows = cur.fetchall()
        # freed_rows: [(class_id, flight_id, class_name, freed), …]

        # ── 5. Mark booking cancelled ─────────────────────────────────────────
        cur.execute(
            "UPDATE booking SET status = 'cancelled' WHERE pnr = %s",
            (pnr,),
        )

        # ── 6. Mark all active tickets for this booking cancelled ─────────────
        cur.execute(
            """
            UPDATE ticket SET status = 'cancelled'
            WHERE  segment_id IN (
                SELECT segment_id FROM booking_segment WHERE pnr = %s
            )
            AND    status = 'active'
            """,
            (pnr,),
        )

        # ── 7. Increment available_seats for each class ───────────────────────
        for class_id, _flight_id, _class_name, freed in freed_rows:
            cur.execute(
                "UPDATE fare_class SET available_seats = available_seats + %s "
                "WHERE class_id = %s",
                (freed, class_id),
            )

        # ── 8. Refund: based on earliest departure across all segments ─────────
        earliest_dep = min(dep_time for _, _, _, _, dep_time in segments)
        fraction     = _refund_fraction(earliest_dep)
        refund_amount = (Decimal(str(total_amount)) * fraction).quantize(
            Decimal("0.01")
        )
        cur.execute(
            "INSERT INTO payment (pnr, amount, method, status) "
            "VALUES (%s, %s, 'refund', 'refunded')",
            (pnr, refund_amount),
        )

        # ── 9. Reprice each freed class ───────────────────────────────────────
        for class_id, _, _, _ in freed_rows:
            reprice(cur, class_id, reason="cancellation")

        # ── 10. Waitlist promotion — direct bookings only ─────────────────────
        #        Multi-hop itineraries (>1 segment) are never waitlist-eligible.
        promoted_pnr: str | None = None
        is_direct = (len(segments) == 1)

        if is_direct:
            the_class_id   = freed_rows[0][0]
            the_flight_id  = freed_rows[0][1]
            the_class_name = freed_rows[0][2]

            # Re-read available_seats after reprice (price may have changed).
            cur.execute(
                "SELECT available_seats, current_price FROM fare_class "
                "WHERE class_id = %s",
                (the_class_id,),
            )
            avail, promo_price = cur.fetchone()

            # Oldest waiting row that fits; skip rows locked by other transactions.
            cur.execute(
                """
                SELECT wl.wl_id, wl.user_id, wl.seats_requested
                FROM   waitlist wl
                WHERE  wl.class_id        = %s
                  AND  wl.status          = 'waiting'
                  AND  wl.seats_requested <= %s
                ORDER  BY wl.created_at ASC
                LIMIT  1
                FOR UPDATE SKIP LOCKED
                """,
                (the_class_id, avail),
            )
            wl_row = cur.fetchone()

            if wl_row:
                wl_id, wl_user_id, seats_req = wl_row

                # Placeholder passenger name from the user record.
                cur.execute(
                    "SELECT name FROM users WHERE user_id = %s",
                    (wl_user_id,),
                )
                wl_user_name = cur.fetchone()[0]

                promo_total  = Decimal(str(promo_price)) * seats_req
                promoted_pnr = _unique_pnr(cur)

                # INSERT promoted booking.
                cur.execute(
                    "INSERT INTO booking (pnr, user_id, status, total_amount) "
                    "VALUES (%s, %s, 'confirmed', %s)",
                    (promoted_pnr, wl_user_id, promo_total),
                )

                # INSERT booking_segment.
                cur.execute(
                    "INSERT INTO booking_segment "
                    "(pnr, flight_id, class_id, price_paid) "
                    "VALUES (%s, %s, %s, %s) RETURNING segment_id",
                    (promoted_pnr, the_flight_id, the_class_id, promo_total),
                )
                promo_seg_id = cur.fetchone()[0]

                # Decrement seats for the promoted booking.
                cur.execute(
                    "UPDATE fare_class SET available_seats = available_seats - %s "
                    "WHERE class_id = %s",
                    (seats_req, the_class_id),
                )

                # INSERT placeholder passengers (age/gender unknown from waitlist).
                promo_pids: list[int] = []
                for i in range(seats_req):
                    suffix = f" {i + 1}" if seats_req > 1 else ""
                    cur.execute(
                        "INSERT INTO passenger (pnr, name, age, gender) "
                        "VALUES (%s, %s, 0, 'U') RETURNING passenger_id",
                        (promoted_pnr, f"{wl_user_name}{suffix}"),
                    )
                    promo_pids.append(cur.fetchone()[0])

                # Assign seats and INSERT tickets.
                promo_seats = _assign_seats(
                    cur, the_flight_id, the_class_name, seats_req
                )
                for pid, seat_no in zip(promo_pids, promo_seats):
                    cur.execute(
                        "INSERT INTO ticket "
                        "(segment_id, passenger_id, flight_id, class_id, "
                        " seat_no, status) "
                        "VALUES (%s, %s, %s, %s, %s, 'active')",
                        (promo_seg_id, pid, the_flight_id,
                         the_class_id, seat_no),
                    )

                # INSERT payment for the promoted booking.
                cur.execute(
                    "INSERT INTO payment (pnr, amount, method, status) "
                    "VALUES (%s, %s, 'card', 'paid')",
                    (promoted_pnr, promo_total),
                )

                # Mark waitlist entry fulfilled.
                cur.execute(
                    "UPDATE waitlist SET status = 'fulfilled' WHERE wl_id = %s",
                    (wl_id,),
                )

                # Reprice after the promoted booking fills seats.
                reprice(cur, the_class_id, reason="waitlist_promotion")


        conn.commit()
        return {
            "status":        "ok",
            "refund":        refund_amount,
            "promoted_pnr":  promoted_pnr,
        }

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
