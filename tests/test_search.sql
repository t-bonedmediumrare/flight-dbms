-- tests/test_search.sql — Manual test queries for multi-hop flight search
-- Run directly in psql: psql $DATABASE_URL -f tests/test_search.sql

\echo '==================================================='
\echo 'TEST 1: Direct route search (DEL -> BOM, CURRENT_DATE)'
\echo 'Expected: Direct flights (hops = 1) sorted by price'
\echo '==================================================='

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
          AND  fc.available_seats >= 1
    ) fc_min ON fc_min.min_price IS NOT NULL
    WHERE f.origin        = 'DEL'
      AND f.dep_time::DATE = CURRENT_DATE
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
          AND  fc.available_seats >= 1
    ) nfc_min ON nfc_min.min_price IS NOT NULL
    WHERE r.hops < 3
),
final_routes AS (
    SELECT * FROM routes WHERE dest = 'BOM'
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
ORDER BY rn_price ASC
LIMIT  10;


\echo '==================================================='
\echo 'TEST 2: Hub-connection route (JAI -> SIN, CURRENT_DATE)'
\echo 'Expected: Multi-hop itineraries via DEL, BOM, or BLR (hops >= 2)'
\echo '==================================================='

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
          AND  fc.available_seats >= 1
    ) fc_min ON fc_min.min_price IS NOT NULL
    WHERE f.origin        = 'JAI'
      AND f.dep_time::DATE = CURRENT_DATE
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
          AND  fc.available_seats >= 1
    ) nfc_min ON nfc_min.min_price IS NOT NULL
    WHERE r.hops < 3
),
final_routes AS (
    SELECT * FROM routes WHERE dest = 'SIN'
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
ORDER BY rn_duration ASC
LIMIT  10;


\echo '==================================================='
\echo 'TEST 3: Nonexistent / impossible route (JFK -> IXC, CURRENT_DATE)'
\echo 'Expected: 0 rows returned'
\echo '==================================================='

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
          AND  fc.available_seats >= 1
    ) fc_min ON fc_min.min_price IS NOT NULL
    WHERE f.origin        = 'JFK'
      AND f.dep_time::DATE = CURRENT_DATE
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
          AND  fc.available_seats >= 1
    ) nfc_min ON nfc_min.min_price IS NOT NULL
    WHERE r.hops < 3
),
final_routes AS (
    SELECT * FROM routes WHERE dest = 'IXC'
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
ORDER BY rn_hops ASC
LIMIT  10;
