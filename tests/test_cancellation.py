"""tests/test_cancellation.py — Integration tests for cancel_booking (§6.4).

Tests:
  1. Direct booking: cancel frees seat, ticket marked cancelled, refund
     inserted, waitlisted user auto-booked, waitlist row fulfilled.
  2. Multi-hop booking: cancel frees seats on all segments, waitlist entry
     is NOT promoted (multi-hop guard).

Run from repo root:
    python tests/test_cancellation.py
"""

import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.db import get_db_connection   # noqa: E402
from app.booking import book_ticket    # noqa: E402
from app.cancellation import cancel_booking  # noqa: E402


# ── Test helpers ──────────────────────────────────────────────────────────────

_failures: list[str] = []


def check(label: str, condition: bool) -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"    [{status}]  {label}")
    if not condition:
        _failures.append(label)
    return condition


def _db_one(sql: str, params: tuple):
    """Return the first row of a read-only query."""
    conn = get_db_connection()
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(sql, params)
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def _db_all(sql: str, params: tuple) -> list:
    conn = get_db_connection()
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


# ── Setup helpers ─────────────────────────────────────────────────────────────

def _get_users() -> tuple[int, int]:
    """Return (alice_user_id, bob_user_id) from seeded demo users."""
    alice = _db_one("SELECT user_id FROM users WHERE email = 'alice@demo.com'", ())
    bob   = _db_one("SELECT user_id FROM users WHERE email = 'bob@demo.com'",   ())
    if alice is None or bob is None:
        raise RuntimeError("Demo users not found — run seed/seed.py first")
    return alice[0], bob[0]


def _pick_class(exclude_ids: tuple = ()) -> tuple[int, int, Decimal]:
    """Pick one scheduled economy class, excluding already-chosen class_ids."""
    sql = """
        SELECT fc.class_id, fc.flight_id, fc.current_price
        FROM   fare_class fc
        JOIN   flight     f  ON f.flight_id = fc.flight_id
        WHERE  fc.class_name      = 'economy'
          AND  fc.available_seats > 0
          AND  f.status           = 'scheduled'
    """
    if exclude_ids:
        placeholders = ",".join(["%s"] * len(exclude_ids))
        sql += f"  AND  fc.class_id NOT IN ({placeholders})"
    sql += "  ORDER BY fc.class_id  LIMIT 1"
    row = _db_one(sql, exclude_ids)
    if row is None:
        raise RuntimeError("No eligible flight — run seed/seed.py first")
    return row[0], row[1], Decimal(str(row[2]))


def _set_available(class_id: int, n: int) -> None:
    """Pin available_seats to n for a controlled test."""
    conn = get_db_connection()
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("UPDATE fare_class SET available_seats = %s WHERE class_id = %s", (n, class_id))
    cur.close()
    conn.close()


def _insert_waitlist(user_id: int, class_id: int, seats_req: int = 1) -> int:
    """Insert a 'waiting' waitlist row and return its wl_id."""
    conn = get_db_connection()
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO waitlist (user_id, class_id, seats_requested, position, status) "
        "VALUES (%s, %s, %s, 1, 'waiting') RETURNING wl_id",
        (user_id, class_id, seats_req),
    )
    wl_id = cur.fetchone()[0]
    cur.close()
    conn.close()
    return wl_id


# ── Test 1: Direct booking — cancel + waitlist promotion ─────────────────────

def test_direct_cancel_with_waitlist_promotion() -> None:
    print("\n── Test 1: Direct booking cancel with waitlist promotion ──────────")

    alice_id, bob_id = _get_users()
    class_id, flight_id, price = _pick_class()

    # Pin to 1 seat so the initial booking takes the last one.
    _set_available(class_id, 1)

    # Alice books the last seat.
    result = book_ticket(
        user_id=alice_id,
        segments=[{"flight_id": flight_id, "class_id": class_id}],
        passengers=[{"name": "Alice Demo", "age": 30, "gender": "F"}],
        quoted_price=price,
    )
    if result["status"] != "ok":
        print(f"    [FAIL]  Setup: book_ticket returned {result}")
        _failures.append("Test 1 setup: book_ticket did not succeed")
        return
    pnr = result["pnr"]
    print(f"    [INFO]  Alice booked PNR={pnr}")

    # Bob adds himself to the waitlist.
    wl_id = _insert_waitlist(bob_id, class_id, seats_req=1)
    print(f"    [INFO]  Bob waitlisted (wl_id={wl_id})")

    # Cancel Alice's booking.
    cancel_result = cancel_booking(pnr)

    check("cancel_booking returns status='ok'",
          cancel_result["status"] == "ok")

    check("refund amount is > 0 or == 0 (Decimal type, not None)",
          isinstance(cancel_result["refund"], Decimal))

    promoted_pnr = cancel_result.get("promoted_pnr")
    check("a promoted PNR was returned", promoted_pnr is not None)

    # Ticket for Alice's booking should be cancelled.
    ticket_rows = _db_all(
        """
        SELECT t.status FROM ticket t
        JOIN booking_segment bs ON bs.segment_id = t.segment_id
        WHERE bs.pnr = %s
        """,
        (pnr,),
    )
    check("all original tickets are now 'cancelled'",
          all(r[0] == "cancelled" for r in ticket_rows) and len(ticket_rows) > 0)

    # A 'refunded' payment row must exist.
    refund_row = _db_one(
        "SELECT amount, status FROM payment WHERE pnr = %s AND status = 'refunded'",
        (pnr,),
    )
    check("refund payment row inserted", refund_row is not None)
    check("refund payment amount matches cancel_result['refund']",
          refund_row is not None and Decimal(str(refund_row[0])) == cancel_result["refund"])

    # Bob's promoted booking must exist.
    if promoted_pnr:
        promo_bk = _db_one(
            "SELECT status, user_id FROM booking WHERE pnr = %s",
            (promoted_pnr,),
        )
        check("promoted booking exists and is 'confirmed'",
              promo_bk is not None and promo_bk[0] == "confirmed")
        check("promoted booking belongs to the waitlisted user (Bob)",
              promo_bk is not None and promo_bk[1] == bob_id)

        promo_tickets = _db_all(
            """
            SELECT t.seat_no FROM ticket t
            JOIN booking_segment bs ON bs.segment_id = t.segment_id
            WHERE bs.pnr = %s AND t.status = 'active'
            """,
            (promoted_pnr,),
        )
        check("promoted booking has 1 active ticket", len(promo_tickets) == 1)

    # Waitlist row must now be 'fulfilled'.
    wl_row = _db_one("SELECT status FROM waitlist WHERE wl_id = %s", (wl_id,))
    check("waitlist row status is 'fulfilled'",
          wl_row is not None and wl_row[0] == "fulfilled")

    # After promotion, available_seats should be back to 0 (Bob took the freed seat).
    avail_row = _db_one(
        "SELECT available_seats FROM fare_class WHERE class_id = %s",
        (class_id,),
    )
    check("available_seats = 0 after promotion consumed the freed seat",
          avail_row is not None and avail_row[0] == 0)


# ── Test 2: Multi-hop booking — cancel does NOT promote waitlist ──────────────

def test_multihop_cancel_no_waitlist_promotion() -> None:
    print("\n── Test 2: Multi-hop booking cancel — waitlist must NOT be promoted ─")

    alice_id, bob_id = _get_users()

    # Pick two different classes for the two segments.
    class_id_1, flight_id_1, price_1 = _pick_class()
    class_id_2, flight_id_2, price_2 = _pick_class(exclude_ids=(class_id_1,))

    _set_available(class_id_1, 2)
    _set_available(class_id_2, 2)

    quoted = price_1 + price_2   # 1 passenger, 2 segments

    result = book_ticket(
        user_id=alice_id,
        segments=[
            {"flight_id": flight_id_1, "class_id": class_id_1},
            {"flight_id": flight_id_2, "class_id": class_id_2},
        ],
        passengers=[{"name": "Alice Demo", "age": 30, "gender": "F"}],
        quoted_price=quoted,
    )
    if result["status"] != "ok":
        print(f"    [FAIL]  Setup: multi-hop book_ticket returned {result}")
        _failures.append("Test 2 setup: book_ticket did not succeed")
        return
    pnr = result["pnr"]
    print(f"    [INFO]  Alice booked multi-hop PNR={pnr}")

    # Bob waitlists on the first class.
    wl_id = _insert_waitlist(bob_id, class_id_1, seats_req=1)
    print(f"    [INFO]  Bob waitlisted on class_id={class_id_1} (wl_id={wl_id})")

    # Cancel Alice's multi-hop booking.
    cancel_result = cancel_booking(pnr)

    check("cancel_booking returns status='ok'",
          cancel_result["status"] == "ok")

    check("promoted_pnr is None (multi-hop guard)",
          cancel_result.get("promoted_pnr") is None)

    # All tickets cancelled.
    ticket_rows = _db_all(
        """
        SELECT t.status FROM ticket t
        JOIN booking_segment bs ON bs.segment_id = t.segment_id
        WHERE bs.pnr = %s
        """,
        (pnr,),
    )
    check("all tickets are 'cancelled'",
          all(r[0] == "cancelled" for r in ticket_rows) and len(ticket_rows) > 0)

    # available_seats restored on both classes.
    avail_1 = _db_one("SELECT available_seats FROM fare_class WHERE class_id = %s", (class_id_1,))
    avail_2 = _db_one("SELECT available_seats FROM fare_class WHERE class_id = %s", (class_id_2,))
    check("class 1 available_seats restored to 2",
          avail_1 is not None and avail_1[0] == 2)
    check("class 2 available_seats restored to 2",
          avail_2 is not None and avail_2[0] == 2)

    # Refund payment inserted.
    refund_row = _db_one(
        "SELECT status FROM payment WHERE pnr = %s AND status = 'refunded'",
        (pnr,),
    )
    check("refund payment row inserted", refund_row is not None)

    # Waitlist row must still be 'waiting'.
    wl_row = _db_one("SELECT status FROM waitlist WHERE wl_id = %s", (wl_id,))
    check("waitlist row remains 'waiting' (no promotion for multi-hop)",
          wl_row is not None and wl_row[0] == "waiting")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=== Cancellation & Waitlist Promotion Tests ===")

    test_direct_cancel_with_waitlist_promotion()
    test_multihop_cancel_no_waitlist_promotion()

    print()
    if _failures:
        print(f"=== RESULT: FAIL ({len(_failures)} assertion(s) failed) ===")
        for f in _failures:
            print(f"  ✗  {f}")
        sys.exit(1)
    else:
        print("=== RESULT: PASS (all assertions passed) ===")


if __name__ == "__main__":
    main()
