-- queries.sql — SQL reference for Flight DBMS
-- Parameterised with %s positional placeholders (psycopg2 order).
-- Executed by app/search.py; do NOT run this file directly.

-- ────────────────────────────────────────────────────────────────────────────
-- MULTI-HOP FLIGHT SEARCH (§6.1)
-- Parameters (in order):
--   %s  passengers  INT   – minimum available seats required on each class
--   %s  origin      CHAR  – IATA code of the departure airport
--   %s  date        DATE  – travel date (applies to first leg only)
--   %s  passengers  INT   – repeated for the recursive leg's LATERAL subquery
--   %s  dest        CHAR  – IATA code of the target airport
-- The ORDER BY expression is injected as a validated literal by search.py.
-- ────────────────────────────────────────────────────────────────────────────

WITH RECURSIVE routes AS (

    -- ── Base case: first leg departing origin on the search date ─────────────
    SELECT
        f.flight_id,
        f.flight_no,
        f.origin,
        f.dest,
        f.dep_time,
        f.arr_time,
        -- path tracks visited airports to prevent cycles
        ARRAY[f.origin, f.dest]::TEXT[]   AS path,
        ARRAY[f.flight_id]::INT[]         AS flight_ids,
        1                                  AS hops,
        -- cheapest class with enough seats on this leg
        fc_min.min_price                   AS total_price,
        f.dep_time                         AS first_dep,
        f.arr_time                         AS last_arr
    FROM flight f
    -- LATERAL ensures we only pick flights that have a qualifying class
    JOIN LATERAL (
        SELECT MIN(fc.current_price) AS min_price
        FROM   fare_class fc
        WHERE  fc.flight_id       = f.flight_id
          AND  fc.available_seats >= %s          -- passengers
    ) fc_min ON fc_min.min_price IS NOT NULL
    WHERE f.origin    = %s                       -- origin
      AND f.dep_time::DATE = %s                  -- search date
      AND f.status    = 'scheduled'

    UNION ALL

    -- ── Recursive case: extend route by one more leg ──────────────────────────
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
        ON nf.origin  = r.dest
        -- layover window: 45 min to 12 hours (§6.1)
       AND nf.dep_time >= r.last_arr + INTERVAL '45 minutes'
       AND nf.dep_time <= r.last_arr + INTERVAL '12 hours'
       -- cycle guard: next destination must not already be in the path
       AND nf.dest   <> ALL(r.path)
       AND nf.status  = 'scheduled'
    -- hop limit: allow at most 3 legs total (< 3 before adding this one)
    JOIN LATERAL (
        SELECT MIN(fc.current_price) AS min_price
        FROM   fare_class fc
        WHERE  fc.flight_id       = nf.flight_id
          AND  fc.available_seats >= %s          -- passengers (repeated)
    ) nfc_min ON nfc_min.min_price IS NOT NULL
    WHERE r.hops < 3

),

-- ── Filter to routes that reach the target destination ───────────────────────
final_routes AS (
    SELECT *
    FROM   routes
    WHERE  dest = %s                             -- target dest
),

-- ── Rank each complete route by all three sort dimensions ────────────────────
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

SELECT
    flight_ids,
    path,
    hops,
    total_price,
    first_dep,
    last_arr,
    duration
FROM   ranked
-- ORDER BY is injected by search.py (validated whitelist, not user string)
ORDER BY /* :sort_expr */
LIMIT  10;
