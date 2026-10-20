"""Integration tests for fare price history triggers."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.db import get_db_connection  # noqa: E402
from app.pricing import reprice       # noqa: E402


_failures: list[str] = []


def check(label: str, condition: bool) -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"    [{status}]  {label}")
    if not condition:
        _failures.append(label)
    return condition


def main() -> None:
    print("=== Fare Price History Trigger Tests ===")
    conn = get_db_connection()
    conn.autocommit = False
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT fc.class_id, fc.current_price
            FROM fare_class fc
            JOIN flight f ON f.flight_id = fc.flight_id
            WHERE f.dep_time > NOW()
            ORDER BY fc.class_id
            LIMIT 1
            """
        )
        class_row = cur.fetchone()
        if class_row is None:
            raise RuntimeError("No future fare class found; run seed/seed.py first")
        class_id, old_price = class_row

        # Raise the base inside this rollback-only transaction to force a new price.
        cur.execute(
            "UPDATE fare_class SET base_price = %s WHERE class_id = %s",
            (old_price * 2, class_id),
        )
        cur.execute(
            "SELECT COUNT(*) FROM price_history WHERE class_id = %s",
            (class_id,),
        )
        before_change = cur.fetchone()[0]
        reprice(cur, class_id, reason="trigger_test_change")
        cur.execute(
            "SELECT COUNT(*) FROM price_history WHERE class_id = %s",
            (class_id,),
        )
        changed_count = cur.fetchone()[0]
        cur.execute(
            "SELECT reason FROM price_history WHERE class_id = %s ORDER BY ph_id DESC LIMIT 1",
            (class_id,),
        )
        changed_reason = cur.fetchone()[0]
        check("price change adds exactly one history row with reprice reason",
              changed_count - before_change == 1 and changed_reason == "trigger_test_change")

        before_unchanged = changed_count
        reprice(cur, class_id, reason="trigger_test_unchanged")
        cur.execute(
            "SELECT COUNT(*) FROM price_history WHERE class_id = %s",
            (class_id,),
        )
        after_unchanged = cur.fetchone()[0]
        check("unchanged reprice adds zero history rows",
              after_unchanged - before_unchanged == 0)

        # Clear the transaction-local reason so a direct update uses the fallback.
        cur.execute("SELECT set_config('app.price_reason', '', true)")
        before_direct = after_unchanged
        cur.execute(
            "UPDATE fare_class SET current_price = current_price + 10 WHERE class_id = %s",
            (class_id,),
        )
        cur.execute(
            "SELECT COUNT(*) FROM price_history WHERE class_id = %s",
            (class_id,),
        )
        direct_count = cur.fetchone()[0]
        cur.execute(
            "SELECT reason FROM price_history WHERE class_id = %s ORDER BY ph_id DESC LIMIT 1",
            (class_id,),
        )
        direct_reason = cur.fetchone()[0]
        check("direct price update adds one row with reason 'price update'",
              direct_count - before_direct == 1 and direct_reason == "price update")
    finally:
        conn.rollback()
        cur.close()
        conn.close()

    print()
    if _failures:
        print(f"=== RESULT: FAIL ({len(_failures)} assertion(s) failed) ===")
        for failure in _failures:
            print(f"  ✗  {failure}")
        sys.exit(1)
    print("=== RESULT: PASS (all assertions passed) ===")


if __name__ == "__main__":
    main()
