"""concurrency_test.py — 50 threads race for the last seat on one flight.

Assertions (all must pass):
  1. Exactly 1 thread succeeded with status 'ok'.
  2. All other threads got 'no_seats' (or 'price_changed' is tolerated but counted).
  3. fare_class.available_seats = 0 for the targeted class.
  4. No duplicate seat_no in ticket for the targeted flight.

Run from repo root:
    python tests/concurrency_test.py
"""

import os
import sys
import threading
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.db import get_db_connection  # noqa: E402
from app.booking import book_ticket   # noqa: E402

THREAD_COUNT = 50


# ── Setup helpers ─────────────────────────────────────────────────────────────

def _pick_target() -> dict:
    """Pick one flight/class, pin available_seats = 1, return test context."""
    conn = get_db_connection()
    conn.autocommit = False
    cur  = conn.cursor()
    try:
        # Pick the first flight that has economy seats still available.
        cur.execute(
            """
            SELECT fc.class_id, fc.flight_id, fc.current_price
            FROM   fare_class fc
            JOIN   flight     f  ON f.flight_id = fc.flight_id
            WHERE  fc.class_name      = 'economy'
              AND  fc.available_seats > 0
              AND  f.status           = 'scheduled'
            ORDER  BY fc.class_id
            LIMIT  1
            """,
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError("No eligible flight found — have you run seed.py?")
        class_id, flight_id, current_price = row

        # Pin available_seats to exactly 1 so the race is for the last seat.
        cur.execute(
            "UPDATE fare_class SET available_seats = 1 WHERE class_id = %s",
            (class_id,),
        )

        # Fetch a demo user to act as the booker for all threads.
        cur.execute(
            "SELECT user_id FROM users WHERE email = 'alice@demo.com' LIMIT 1"
        )
        user_row = cur.fetchone()
        if user_row is None:
            raise RuntimeError("Demo user alice@demo.com not found — have you run seed.py?")
        user_id = user_row[0]

        conn.commit()
        print(f"[setup] class_id={class_id}  flight_id={flight_id}  "
              f"current_price={current_price}  available_seats set to 1")
        return {
            "class_id":      class_id,
            "flight_id":     flight_id,
            "current_price": Decimal(str(current_price)),
            "user_id":       user_id,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def _check_state(class_id: int, flight_id: int) -> dict:
    """Read final DB state after all threads have finished."""
    conn = get_db_connection()
    conn.autocommit = True
    cur  = conn.cursor()
    try:
        cur.execute(
            "SELECT available_seats FROM fare_class WHERE class_id = %s",
            (class_id,),
        )
        available_seats = cur.fetchone()[0]

        # All seat_no values for active tickets on this flight.
        cur.execute(
            "SELECT seat_no FROM ticket WHERE flight_id = %s AND status = 'active'",
            (flight_id,),
        )
        seats = [r[0] for r in cur.fetchall()]
        return {"available_seats": available_seats, "seats": seats}
    finally:
        cur.close()
        conn.close()


# ── Thread worker ─────────────────────────────────────────────────────────────

def _worker(idx: int, ctx: dict, results: list, lock: threading.Lock) -> None:
    """Each thread attempts to book 1 seat on the pinned flight/class."""
    passenger = {"name": f"Racer-{idx:02d}", "age": 25, "gender": "M"}
    try:
        result = book_ticket(
            user_id=ctx["user_id"],
            segments=[{"flight_id": ctx["flight_id"], "class_id": ctx["class_id"]}],
            passengers=[passenger],
            quoted_price=ctx["current_price"],  # pre-fetched; matches locked price
        )
    except Exception as exc:
        result = {"status": "exception", "error": str(exc)}

    with lock:
        results.append({"thread": idx, **result})


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"=== Concurrency test: {THREAD_COUNT} threads racing for 1 seat ===\n")

    ctx = _pick_target()

    results: list[dict] = []
    lock    = threading.Lock()
    threads = [
        threading.Thread(target=_worker, args=(i, ctx, results, lock), daemon=True)
        for i in range(THREAD_COUNT)
    ]

    # Start all threads as close together as possible.
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # ── Gather outcomes ───────────────────────────────────────────────────────
    ok_results       = [r for r in results if r["status"] == "ok"]
    no_seats_results = [r for r in results if r["status"] == "no_seats"]
    price_changed    = [r for r in results if r["status"] == "price_changed"]
    exceptions       = [r for r in results if r["status"] == "exception"]

    print(f"\nResults:  ok={len(ok_results)}  no_seats={len(no_seats_results)}  "
          f"price_changed={len(price_changed)}  exception={len(exceptions)}")
    if ok_results:
        print(f"  PNR:  {ok_results[0].get('pnr')}")
    if exceptions:
        for e in exceptions:
            print(f"  [thread {e['thread']}] exception: {e['error']}")

    state = _check_state(ctx["class_id"], ctx["flight_id"])
    print(f"\nDB state: available_seats={state['available_seats']}  "
          f"active_tickets={len(state['seats'])}  seats={state['seats']}")

    # ── Assertions ────────────────────────────────────────────────────────────
    failures: list[str] = []

    if len(ok_results) != 1:
        failures.append(
            f"FAIL  Expected exactly 1 success, got {len(ok_results)}"
        )
    else:
        print("\n  ✓  Exactly 1 thread succeeded")

    expected_no_seats = THREAD_COUNT - len(ok_results) - len(price_changed) - len(exceptions)
    if len(no_seats_results) != expected_no_seats:
        failures.append(
            f"FAIL  Expected {expected_no_seats} 'no_seats', got {len(no_seats_results)}"
        )
    else:
        print(f"  ✓  All remaining {len(no_seats_results)} threads got 'no_seats'")

    if state["available_seats"] != 0:
        failures.append(
            f"FAIL  available_seats = {state['available_seats']}, expected 0"
        )
    else:
        print("  ✓  available_seats = 0")

    duplicate_seats = len(state["seats"]) != len(set(state["seats"]))
    if duplicate_seats:
        failures.append(
            f"FAIL  Duplicate seat_no values found: {state['seats']}"
        )
    else:
        print(f"  ✓  No duplicate seat_no values")

    if exceptions:
        failures.append(
            f"FAIL  {len(exceptions)} thread(s) raised unexpected exceptions"
        )

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    if failures:
        for f in failures:
            print(f"  {f}")
        print("\n=== RESULT: FAIL ===")
        sys.exit(1)
    else:
        print("=== RESULT: PASS ===")


if __name__ == "__main__":
    main()
