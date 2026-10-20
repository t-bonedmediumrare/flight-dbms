"""search.py — multi-hop flight search using the recursive CTE from db/queries.sql."""

import sys
import os
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.db import get_db_connection  # noqa: E402

# Validated ORDER BY expressions — never built from raw user input.
_SORT_EXPR = {
    "price":    "rn_price ASC",
    "duration": "rn_duration ASC",
    "hops":     "rn_hops ASC",
}

_SEARCH_SQL = """\
WITH RECURSIVE routes AS (

    SELECT
        f.flight_id,
        f.flight_no,
        f.origin,
        f.dest,
        f.dep_time,
        f.arr_time,
        ARRAY[f.origin, f.dest]::TEXT[]   AS path,
        ARRAY[f.flight_id]::INT[]         AS flight_ids,
        1                                  AS hops,
        fc_min.min_price                   AS total_price,
        f.dep_time                         AS first_dep,
        f.arr_time                         AS last_arr
    FROM flight f
    JOIN LATERAL (
        SELECT MIN(fc.current_price) AS min_price
        FROM   fare_class fc
        WHERE  fc.flight_id       = f.flight_id
          AND  fc.available_seats >= %s
    ) fc_min ON fc_min.min_price IS NOT NULL
    WHERE f.origin        = %s
      AND f.dep_time::DATE = %s
      AND f.status        = 'scheduled'

    UNION ALL

    SELECT
        nf.flight_id,
        nf.flight_no,
        nf.origin,
        nf.dest,
        nf.dep_time,
        nf.arr_time,
        r.path       || nf.dest,
        r.flight_ids || nf.flight_id,
        r.hops + 1,
        r.total_price + nfc_min.min_price,
        r.first_dep,
        nf.arr_time
    FROM   routes r
    JOIN   flight nf
        ON nf.origin   = r.dest
       AND nf.dep_time >= r.last_arr + INTERVAL '45 minutes'
       AND nf.dep_time <= r.last_arr + INTERVAL '12 hours'
       AND nf.dest    <> ALL(r.path)
       AND nf.status   = 'scheduled'
    JOIN LATERAL (
        SELECT MIN(fc.current_price) AS min_price
        FROM   fare_class fc
        WHERE  fc.flight_id       = nf.flight_id
          AND  fc.available_seats >= %s
    ) nfc_min ON nfc_min.min_price IS NOT NULL
    WHERE r.hops < 3

),
final_routes AS (
    SELECT * FROM routes WHERE dest = %s
),
ranked AS (
    SELECT
        flight_ids,
        path,
        hops,
        total_price,
        first_dep,
        last_arr,
        (last_arr - first_dep)                                  AS duration,
        ROW_NUMBER() OVER (ORDER BY total_price ASC)            AS rn_price,
        ROW_NUMBER() OVER (ORDER BY (last_arr - first_dep) ASC) AS rn_duration,
        ROW_NUMBER() OVER (ORDER BY hops ASC, total_price ASC)  AS rn_hops
    FROM final_routes
)
SELECT flight_ids, path, hops, total_price, first_dep, last_arr, duration
FROM   ranked
ORDER BY {sort_expr}
LIMIT  10
"""


def search_routes(
    origin: str,
    dest: str,
    search_date: date,
    sort: str = "price",
    passengers: int = 1,
) -> list[dict]:
    """Return up to 10 itineraries from origin to dest on search_date.

    Args:
        origin:      IATA departure airport code (e.g. "DEL").
        dest:        IATA arrival airport code (e.g. "BOM").
        search_date: Date of first departure leg.
        sort:        One of 'price', 'duration', 'hops'.
        passengers:  Minimum seats required on each fare class.

    Returns:
        List of dicts with keys: flight_ids, path, hops, total_price,
        first_dep, last_arr, duration_minutes.

    Raises:
        ValueError: if sort is not a recognised option.
    """
    if sort not in _SORT_EXPR:
        raise ValueError(f"sort must be one of {list(_SORT_EXPR)}; got {sort!r}")

    # Safe: sort_expr comes from our internal whitelist, not raw user input.
    sql = _SEARCH_SQL.format(sort_expr=_SORT_EXPR[sort])

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (passengers, origin, search_date, passengers, dest))
            cols = [d.name for d in cur.description]
            rows = cur.fetchall()
    finally:
        conn.close()

    results = []
    for row in rows:
        rec = dict(zip(cols, row))
        # Expose duration as total minutes for convenience.
        rec["duration_minutes"] = (
            int(rec["duration"].total_seconds() // 60) if rec["duration"] else None
        )
        results.append(rec)
    return results
