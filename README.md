# data-flighto: Flight Route & Fare Optimization System

A web-based flight search and booking system built as a DBMS mini project. Users search direct and multi-hop flights, book seats, cancel bookings, and join waitlists. Admins manage flight status, view fares and price history, and see analytics.

**Live demo:** https://flight-dbms-hakm.onrender.com

> The free hosting tier sleeps after 15 minutes of inactivity. The first load can take about a minute.

## Demo accounts

| Role | Email | Password | Access |
|---|---|---|---|
| Passenger | alice@demo.com | pass1234 | Search, book, cancel, My Bookings |
| Passenger | bob@demo.com | pass1234 | Same as Alice |
| Admin | admin@demo.com | adminpass | All of the above, plus /admin/flights, /admin/fares, /admin/analytics |

These accounts exist for demonstration only.

## Important: simulated data

- **Real:** airport codes, names, cities, countries, and coordinates, loaded from `seed/airports.csv`.
- **Generated for demonstration:** flights, schedules, fares, and seat inventory.
- **Simulated:** the payment step. No real payments are processed.

This is not a real booking site. Flights cover the 14 days from the date the seed was run.

## Features

- **Accounts:** register, log in, and log out. Passwords are stored as Werkzeug hashes, never in plain text.
- **Search:** direct flights and up to two connections, sorted by price, duration, or number of stops.
- **Booking:** one or more passengers per itinerary, with seat assignment by cabin class (business, premium, economy).
- **Price protection:** if the fare changes before you confirm, you are shown the new price and asked to confirm again.
- **Cancellation:** cancel a booking with a refund based on how far away departure is (full, partial, or none).
- **Waitlist:** join the waitlist for a full direct flight. The next person in line is promoted automatically when a seat frees up. Multi-leg itineraries cannot be waitlisted.
- **Dynamic pricing:** fares rise as seats sell and as departure approaches. An admin can run a pricing update on demand.
- **Admin pages:** update flight status, view fare levels and price history, and see analytics.

## Database concepts demonstrated

- **Normalized schema (3NF)** with primary keys, foreign keys, CHECK, and UNIQUE constraints.
- **Partial unique index** on `ticket(flight_id, seat_no) WHERE status = 'active'`. The database itself blocks double-booking, independent of application code.
- **Recursive CTE** for multi-hop route search, with a cycle guard, a two-connection limit, and layover rules (45 minutes to 12 hours between legs).
- **Row-level locking:** `SELECT ... FOR UPDATE` in booking and cancellation, and `FOR UPDATE SKIP LOCKED` for waitlist promotion.
- **Transactions:** a multi-leg booking is all-or-nothing. If any leg fails, the whole booking rolls back.
- **Trigger:** `trg_fare_price_history` in `db/functions.sql` logs every change to `fare_class.current_price` into `price_history`. `[VERIFY: remove this bullet if the trigger is not applied to the database]`
- **Window functions** in analytics: `RANK()` for route revenue, `LAG()` for price changes, and `SUM() OVER` for running monthly revenue.

## Entity-relationship diagram

```mermaid
erDiagram
    AIRPORT ||--o{ FLIGHT : "origin / dest"
    FLIGHT ||--o{ FARE_CLASS : "has"
    FARE_CLASS ||--o{ PRICE_HISTORY : "logs changes"
    FARE_CLASS ||--o{ WAITLIST : "waitlisted for"
    USERS ||--o{ BOOKING : "makes"
    USERS ||--o| ADMIN : "may be"
    USERS ||--o{ WAITLIST : "joins"
    BOOKING ||--o{ BOOKING_SEGMENT : "contains"
    BOOKING ||--o{ PASSENGER : "includes"
    BOOKING ||--o{ PAYMENT : "paid by"
    BOOKING_SEGMENT }o--|| FLIGHT : "on"
    BOOKING_SEGMENT }o--|| FARE_CLASS : "in class"
    TICKET }o--|| PASSENGER : "for"
    TICKET }o--|| BOOKING_SEGMENT : "belongs to"
```

## Tech stack

- Python 3.11+, Flask, psycopg2 (raw SQL, no ORM), Werkzeug
- PostgreSQL 15+ (Neon for the live demo)
- Jinja2 templates with Tailwind CSS (via CDN)
- Gunicorn on Render

## Project structure

```
app/              Flask app, routes, booking, cancellation, pricing, search
app/templates/    HTML templates (Jinja2)
db/               schema.sql (tables), functions.sql (price trigger), queries.sql
seed/             airports.csv and seed.py (generates demo data)
tests/            concurrency, cancellation, and trigger tests, plus test_search.sql
stitch-exports/   design source files for the templates
SPEC.md           project specification
PROGRESS.md       build log
```

## Running locally

**Requirements:** Python 3.11+ and PostgreSQL 15+.

```bash
# 1. Create the database
psql -U postgres -c "CREATE DATABASE flight_dbms;"

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure the environment
cp .env.example .env
# Edit .env and set DATABASE_URL, for example:
# DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/flight_dbms

# 4. Create tables, the price trigger, and demo data
psql -U postgres -d flight_dbms -f db/schema.sql
psql -U postgres -d flight_dbms -f db/functions.sql
python seed/seed.py

# 5. Run the app
python -m app.app
```

Open http://127.0.0.1:5000 in your browser.

## Running the tests

Run these from the project root against a local test database. The tests write rows, so do not point them at the live database.

```bash
python tests/concurrency_test.py     # 50 threads race for 1 seat
python tests/test_cancellation.py    # cancellation, refunds, waitlist promotion
python tests/test_triggers.py        # price history trigger
psql -U postgres -d flight_dbms -f tests/test_search.sql   # sample route searches (SQL)
```

The concurrency test is the key result. When 50 bookings race for one seat, exactly one succeeds, the other 49 are rejected, and no seat is assigned twice.

## Deployment

- **Database:** Neon (free serverless Postgres). Run `schema.sql`, `functions.sql`, and `seed.py` against it once.
- **App:** Render web service, built from this repository.
  - Build command: `pip install -r requirements.txt`
  - Start command: `gunicorn app.app:app`
  - Environment variables: `DATABASE_URL` (the Neon connection string) and `SECRET_KEY` (a long random value)

Never commit `.env`. It holds database credentials. `.gitignore` already excludes it.

## Known limitations

- **Waitlist status:** in one test run, a promoted waitlist entry was not marked `fulfilled`, although the replacement booking was created correctly. The cause was not fully resolved. Booking, cancellation refunds, and seat restoration pass their tests.
- **Multi-leg waitlists:** not supported by design. Waitlisting an itinerary would require holding several seats at once.
- **Seed resets data:** `seed.py` clears all tables before loading. Running it on the live database deletes existing bookings.
- **Date window:** flights cover 14 days from the seed date. Search returns nothing for other dates until the seed is run again.
- **Simulated payments:** no real money moves.

## Authors

Qusai Saify, 
Vedant Sahu, Tanmay Rathi, Tanishq Rane

DBMS mini project, Sardar Patel Institute Of Technology
