# SPEC.md — Flight Route & Fare Optimization System

> Agents: read this file first. Follow it exactly. Work on ONE phase at a time. Do not touch files outside the phase. Check PROGRESS.md for current state.

## 1. Goal
Web app: registered users search direct + multi-hop flights between two airports on a date, see live per-class seat availability with demand-driven dynamic pricing, and book/cancel tickets. DBMS correctness is the priority (no double booking, consistent price/seat data, audit trail). UI stays minimal.

## 2. Stack (fixed, do not change)
- PostgreSQL 15+ (raw SQL, recursive CTEs, row locks)
- Python 3.11 + Flask + psycopg2 (NO ORM)
- Jinja templates, plain HTML/CSS, minimal vanilla JS (NO React, NO build step)
- Passwords: werkzeug hash. Config via `.env`.

## 3. Out of scope
Real payments, real GDS/booking APIs, multi-mode transport, real-time seat maps from airlines.

## 4. Data sources
| Data | Source | Use |
|---|---|---|
| Airports (code, name, city, country, lat/lon) | Static CSV: OurAirports or OpenFlights (free, no key) | Loaded ONCE by `seed.py` |
| Flights/schedules | Option A: generated synthetic schedule (default). Option B: one-time pull from AeroDataBox or Aviationstack free tier into `flight_cache`, then convert | Seed only |
| Live status/delay (optional, last phase) | AeroDataBox / Aviationstack free tier | `/status/<flight>` page, cached 10 min in `api_cache` table |
| Fares | SIMULATED (no free API provides bookable fares) | `fare_class.current_price` |

Rules: never call external APIs from user-facing search/booking paths. Always read from our DB. API failure must not break the app (fall back to cached/seeded data). API keys only in `.env`.

## 5. Schema (3NF) — table: columns
- `airport`(code PK char(3), name, city, country, lat, lon)
- `users`(user_id PK, name, email UNIQUE, password_hash, phone, created_at)
- `admin`(admin_id PK, user_id FK UNIQUE)
- `flight`(flight_id PK, flight_no, origin FK→airport, dest FK→airport, dep_time timestamptz, arr_time timestamptz, status, CHECK origin<>dest, CHECK arr_time>dep_time)
- `fare_class`(class_id PK, flight_id FK, class_name ENUM economy/premium/business, total_seats, available_seats, base_price, current_price, UNIQUE(flight_id,class_name), CHECK 0<=available_seats<=total_seats)
- `booking`(pnr PK char(6), user_id FK, status ENUM confirmed/cancelled/waitlisted, total_amount, created_at)
- `booking_segment`(segment_id PK, pnr FK, flight_id FK, class_id FK, price_paid)
- `passenger`(passenger_id PK, pnr FK, name, age, gender)
- `ticket`(ticket_id PK, segment_id FK, passenger_id FK, flight_id FK, class_id FK, seat_no, status ENUM active/cancelled). Double-booking guard: `CREATE UNIQUE INDEX ... ON ticket(flight_id, seat_no) WHERE status='active'`
- Seat numbers: generated per class range (e.g. economy rows 10-40, premium 5-9, business 1-4, letters A-F); total_seats of each class must match its range.
- `payment`(payment_id PK, pnr FK, amount, method, status, paid_at)
- `waitlist`(wl_id PK, user_id FK, class_id FK, seats_requested, position, created_at, status)
- `price_history`(ph_id PK, class_id FK, old_price, new_price, reason, changed_at)
- `api_cache`(cache_key PK, payload jsonb, fetched_at)
- Indexes: flight(origin, dep_time), flight(dest), fare_class(flight_id), booking(user_id), price_history(class_id, changed_at)

## 6. Key logic

### 6.1 Multi-hop search (recursive CTE)
Inputs: origin, dest, date, sort ∈ {price, duration, hops}.
- Base: flights from origin departing on date with seats available.
- Recursive: join next flight where `next.origin = prev.dest`, `next.dep_time >= prev.arr_time + interval '45 min'` AND `<= prev.arr_time + interval '12 hours'`, `hops < 3`, `next.dest <> ALL(path)` (cycle guard).
- Carry: `path` (airport array), `flight_ids` array, `hops`, `total_price` (cheapest available class), `arr_time`.
- Final: filter `dest = target`; rank with `ROW_NUMBER()/RANK()` per sort option; return top 10.
- The search date applies to the first leg only. Duration = last arrival minus first departure. Only count classes with `available_seats >= passengers`.

### 6.2 Booking (single transaction, READ COMMITTED + row locks)
```
BEGIN
 for each segment, ORDER BY class_id (prevents deadlock):
   SELECT available_seats, current_price FROM fare_class WHERE class_id=%s FOR UPDATE
   if available_seats < n  -> ROLLBACK, offer waitlist
   assign seat numbers; UPDATE fare_class SET available_seats = available_seats - n
 INSERT booking(pnr), booking_segment, passenger, ticket (one per passenger per segment, with seat_no), payment(simulated)
 call reprice(class_id)  -> may INSERT price_history
COMMIT
```
PNR = 6-char unique random alphanumeric; retry on collision.
Price rule: the booking form sends the price the user saw. Inside the transaction, compare it with the locked `current_price`. If different, ROLLBACK and show the new price for re-confirmation. Charge only the locked price.
A multi-hop booking is all-or-nothing: if any segment fails, the whole booking rolls back.

### 6.3 Dynamic pricing — `reprice(class_id)` (SQL function)
`price = base_price * demand_mult * time_mult`, rounded to 2 dp.
- `demand_mult = 1 + 0.6 * (sold/total)^2`
- `time_mult`: >30d 0.9 | 15–30d 1.0 | 7–14d 1.15 | 3–6d 1.35 | <3d 1.6
- Cap at 3x base, floor at 0.8x base.
- Insert into `price_history` only if price changed. Trigger or explicit call after any seat change.
- Sale-based changes happen inside the booking transaction. Time-based changes need `reprice_all()` (recalculates every class whose flight is in the future); run it from an admin button "Run pricing update" and once at app start. No background scheduler needed.

### 6.4 Cancellation + waitlist
Cancel: lock booking and fare_class rows, mark booking and its tickets cancelled (seat becomes free), +available_seats, refund payment row (simulated), reprice. Refund policy: 100% if >7 days before departure, 50% if 2-7 days, 0% if <48h.
Waitlist applies to single-flight (direct) bookings only; multi-hop itineraries cannot be waitlisted. Then promote: select oldest `waitlist` row for that class with `seats_requested <= available_seats` using `FOR UPDATE SKIP LOCKED`, auto-create booking, mark waitlist fulfilled. All in one transaction.

### 6.5 Analytics (window functions)
- Load factor per flight: `(total-available)/total`
- Revenue rank per route: `RANK() OVER (PARTITION BY origin,dest ORDER BY revenue DESC)`
- Price trend per class: `LAG(new_price) OVER (PARTITION BY class_id ORDER BY changed_at)`
- Running monthly revenue: `SUM() OVER (ORDER BY day)`

## 7. Routes (Flask)
`/register /login /logout /search /results /book/<ids> /confirm/<pnr> /my-bookings /cancel/<pnr> /status/<flight_no>(optional) /admin/flights /admin/fares /admin/analytics`
Admin routes require admin role. All SQL parameterized (%s), never string-formatted.

## 8. Folder layout
```
db/schema.sql  db/functions.sql  db/queries.sql
seed/airports.csv  seed/seed.py
app/app.py  app/db.py  app/booking.py  app/search.py  app/pricing.py  app/templates/  app/static/
tests/concurrency_test.py  tests/test_search.sql
SPEC.md  PROGRESS.md  .env.example  README.md
```

## 9. Seed targets
All flight dates are generated relative to today (`current_date` + 0..14 days) so the demo never goes stale. Seed script must be re-runnable (truncate then reload).
~20 airports (mix of Indian + a few international hubs), ~80 flights/day pattern across 14 days, 3 fare classes per flight, ~3 hubs to guarantee multi-hop paths, a few demo users + 1 admin.

## 10. Build phases (one chat each; update PROGRESS.md at end)
0. Repo + DB setup + .env
1. `schema.sql` (+ plan mode, review before running)
2. `seed.py`
3. Recursive search query + `test_search.sql`
4. Booking transaction (+ plan mode)
5. `reprice()` + price_history
6. Cancel + waitlist promotion
7. Auth + Flask routes
8. Templates (search, results, booking form, my bookings, admin)
9. Analytics queries/page
10. `concurrency_test.py`: 50 threads race for last seat; assert exactly 1 success, available_seats = 0, no duplicate seat_no
11. (Optional) live status API with `api_cache`

## 11. Definition of done
- Schema runs clean from scratch; seed is repeatable
- Search returns direct + 1–2 stop routes sorted three ways
- Concurrency test passes consistently
- Price changes logged for every sale and time bucket change
- Cancel frees seat and promotes waitlist atomically
- README has ER diagram, run steps, and demo script

## 12. Agent working rules (token discipline)
- Edit only the files named in the prompt. Return diffs / changed functions only.
- Do not scan the whole repo. Do not open the browser to verify; write a psql or Python test instead.
- Ask before adding any dependency. No refactors outside the phase.
- Keep comments to one line per function/table. No long explanations in replies.
