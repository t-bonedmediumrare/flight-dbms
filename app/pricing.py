"""pricing.py — dynamic fare repricing (§6.3).

reprice(cur, class_id, reason) — recalculates one fare_class row.
reprice_all(cur)               — reprices every class with a future flight.

Both functions use the caller's cursor and participate in its transaction.
"""

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP


def reprice(cur, class_id: int, reason: str = "sale") -> None:
    """Recalculate current_price for one fare_class and log if changed.

    Formula (§6.3):
        price = base_price * demand_mult * time_mult
        demand_mult = 1 + 0.6 * (sold / total)^2
        time_mult   = >30d→0.9 | 15-30d→1.0 | 7-14d→1.15 | 3-6d→1.35 | <3d→1.6
        cap:  min(price, base * 3)
        floor: max(price, base * 0.8)
        round to 2 dp
    """
    cur.execute(
        """
        SELECT fc.base_price,
               fc.current_price,
               fc.total_seats,
               fc.available_seats,
               f.dep_time
        FROM   fare_class fc
        JOIN   flight     f  ON f.flight_id = fc.flight_id
        WHERE  fc.class_id = %s
        """,
        (class_id,),
    )
    row = cur.fetchone()
    if row is None:
        return  # class vanished; skip silently

    base_price, old_price, total_seats, available_seats, dep_time = row

    # ── demand_mult ──────────────────────────────────────────────────────────
    sold = total_seats - available_seats
    sold_ratio  = sold / total_seats if total_seats > 0 else 0.0
    demand_mult = 1.0 + 0.6 * (sold_ratio ** 2)

    # ── time_mult ────────────────────────────────────────────────────────────
    now = datetime.now(timezone.utc)
    # Ensure dep_time is tz-aware (psycopg2 returns timestamptz as aware).
    if dep_time.tzinfo is None:
        dep_time = dep_time.replace(tzinfo=timezone.utc)
    days_until = (dep_time - now).total_seconds() / 86_400

    if days_until > 30:
        time_mult = 0.9
    elif days_until >= 15:
        time_mult = 1.0
    elif days_until >= 7:
        time_mult = 1.15
    elif days_until >= 3:
        time_mult = 1.35
    else:
        time_mult = 1.6

    # ── raw price, cap + floor, round ────────────────────────────────────────
    base = float(base_price)
    raw  = base * demand_mult * time_mult
    raw  = max(base * 0.8, min(raw, base * 3.0))          # cap & floor
    new_price = Decimal(str(raw)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    if new_price == Decimal(str(old_price)):
        return  # unchanged — do not write price_history

    # ── update fare_class ─────────────────────────────────────────────────────
    cur.execute("SELECT set_config('app.price_reason', %s, true)", (reason,))
    cur.execute(
        "UPDATE fare_class SET current_price = %s WHERE class_id = %s",
        (new_price, class_id),
    )


def reprice_all(cur) -> int:
    """Reprice every fare_class whose flight departs in the future.

    Intended for the admin 'Run pricing update' button and app startup.
    Returns the number of classes processed.
    """
    cur.execute(
        """
        SELECT fc.class_id
        FROM   fare_class fc
        JOIN   flight     f  ON f.flight_id = fc.flight_id
        WHERE  f.dep_time > NOW()
        ORDER  BY fc.class_id
        """,
    )
    class_ids = [r[0] for r in cur.fetchall()]
    for cid in class_ids:
        reprice(cur, cid, reason="time")
    return len(class_ids)
