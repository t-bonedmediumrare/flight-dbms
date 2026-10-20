"""app.py — Flask application with authentication and routes (§7).

Routes:
  /register, /login, /logout, /search, /results, /book/<ids>,
  /confirm/<pnr>, /my-bookings, /cancel/<pnr>, /status/<flight_no>,
  /admin/flights, /admin/fares, /admin/analytics, /waitlist/<class_id>
"""

import os
import sys
from datetime import datetime
from decimal import Decimal
from functools import wraps

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from psycopg2.extras import RealDictCursor
from werkzeug.security import check_password_hash, generate_password_hash

# Allow importing sibling modules from app/ and project root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.booking import book_ticket          # noqa: E402
from app.cancellation import cancel_booking  # noqa: E402
from app.db import get_db_connection        # noqa: E402
from app.pricing import reprice_all          # noqa: E402
from app.search import search_routes         # noqa: E402

app = Flask(__name__)
_running_under_gunicorn = "gunicorn" in sys.modules
_secret_key = os.environ.get("SECRET_KEY")
if not _secret_key:
    if __name__ == "__main__" and not _running_under_gunicorn:
        _secret_key = "dev-only-secret-key"
    else:
        raise RuntimeError("SECRET_KEY must be set outside local development")
app.secret_key = _secret_key
app.config["DEBUG"] = not _running_under_gunicorn


# ── Auth & Role Helpers ───────────────────────────────────────────────────────

def is_admin(user_id: int | None) -> bool:
    """Check if the given user_id exists in the admin table."""
    if not user_id:
        return False
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM admin WHERE user_id = %s", (user_id,))
            return cur.fetchone() is not None
    finally:
        conn.close()


def login_required(f):
    """Enforce session-based authentication on protected routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in to continue.", "error")
            return redirect(url_for("login", next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Enforce administrator role backed by the admin database table."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get("user_id")
        if not user_id:
            flash("Please log in as an administrator.", "error")
            return redirect(url_for("login", next=request.url))
        if not is_admin(user_id):
            flash("Administrator privileges required.", "error")
            return redirect(url_for("search"))
        return f(*args, **kwargs)
    return decorated_function


@app.context_processor
def inject_user_context():
    """Make user info available to all templates."""
    return {
        "current_user_id": session.get("user_id"),
        "current_user_name": session.get("user_name"),
        "is_admin": session.get("is_admin", False),
    }


def add_to_waitlist(user_id: int, class_id: int, seats_requested: int = 1) -> int:
    """Insert a waitlist entry with next sequential position and return the position assigned."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(MAX(position), 0) + 1 FROM waitlist "
                "WHERE class_id = %s AND status = 'waiting'",
                (class_id,),
            )
            pos = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO waitlist (user_id, class_id, seats_requested, position, status) "
                "VALUES (%s, %s, %s, %s, 'waiting')",
                (user_id, class_id, seats_requested, pos),
            )
        conn.commit()
        return pos
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()



# ── Public & Auth Routes ──────────────────────────────────────────────────────

@app.route("/")
def index():
    """Redirect home route to search."""
    return redirect(url_for("search"))


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register a new user with werkzeug password hashing."""
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        phone = request.form.get("phone", "").strip() or None

        if not name or not email or not password:
            flash("Name, email, and password are required.", "error")
            return render_template("register.html")

        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT user_id FROM users WHERE email = %s", (email,))
                if cur.fetchone():
                    flash("An account with this email already exists.", "error")
                    return render_template("register.html")

                pw_hash = generate_password_hash(password)
                cur.execute(
                    "INSERT INTO users (name, email, password_hash, phone) "
                    "VALUES (%s, %s, %s, %s) RETURNING user_id",
                    (name, email, pw_hash, phone),
                )
                user_id = cur.fetchone()[0]
            conn.commit()

            session["user_id"] = user_id
            session["user_name"] = name
            session["is_admin"] = False
            flash("Registration successful! Welcome to Flight DBMS.", "success")
            return redirect(url_for("search"))
        except Exception as e:
            conn.rollback()
            flash(f"Registration failed: {e}", "error")
            return render_template("register.html")
        finally:
            conn.close()

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Authenticate user with session-based login and admin check."""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Email and password are required.", "error")
            return render_template("login.html")

        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT user_id, name, password_hash FROM users WHERE email = %s",
                    (email,),
                )
                user = cur.fetchone()

            if not user or not check_password_hash(user[2], password):
                flash("Invalid email or password.", "error")
                return render_template("login.html")

            user_id, name, _ = user
            is_adm = is_admin(user_id)

            session["user_id"] = user_id
            session["user_name"] = name
            session["is_admin"] = is_adm

            flash(f"Welcome back, {name}!", "success")
            next_url = request.args.get("next")
            if next_url and next_url.startswith("/"):
                return redirect(next_url)
            return redirect(url_for("search"))
        finally:
            conn.close()

    return render_template("login.html")


@app.route("/logout", methods=["GET", "POST"])
def logout():
    """Clear session data and redirect to login."""
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


# ── Flight Search & Results Routes ───────────────────────────────────────────

@app.route("/search")
def search():
    """Display the flight search form with airport selection."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT code, name, city, country FROM airport ORDER BY city, name")
            airports = cur.fetchall()
    finally:
        conn.close()

    return render_template("search.html", airports=airports)


@app.route("/results")
def results():
    """Search direct and multi-hop flight itineraries via search.py."""
    origin = request.args.get("origin", "").strip().upper()
    dest = request.args.get("dest", "").strip().upper()
    date_str = request.args.get("date", "").strip()
    sort = request.args.get("sort", "price").strip().lower()
    passengers_str = request.args.get("passengers", "1").strip()

    if not origin or not dest or not date_str:
        flash("Origin, destination, and departure date are required.", "error")
        return redirect(url_for("search"))

    if origin == dest:
        flash("Origin and destination airports must differ.", "error")
        return redirect(url_for("search"))

    try:
        search_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        flash("Invalid date format. Please use YYYY-MM-DD.", "error")
        return redirect(url_for("search"))

    try:
        passengers = int(passengers_str)
        if passengers < 1:
            passengers = 1
    except ValueError:
        passengers = 1

    if sort not in ("price", "duration", "hops"):
        sort = "price"

    try:
        routes_found = search_routes(
            origin=origin,
            dest=dest,
            search_date=search_date,
            sort=sort,
            passengers=passengers,
        )
    except Exception as e:
        flash(f"Error during route search: {e}", "error")
        routes_found = []

    return render_template(
        "results.html",
        routes=routes_found,
        origin=origin,
        dest=dest,
        date=date_str,
        sort=sort,
        passengers=passengers,
    )


# ── Booking, Confirmation & Cancellation Routes ──────────────────────────────

@app.route("/book/<ids>", methods=["GET", "POST"])
@login_required
def book(ids: str):
    """Review itinerary legs, select fare classes, and book atomically via booking.py."""
    try:
        flight_ids = [int(x) for x in ids.replace("-", ",").split(",") if x.strip().isdigit()]
    except Exception:
        flight_ids = []

    if not flight_ids:
        flash("Invalid flight itinerary specified.", "error")
        return redirect(url_for("search"))

    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            flights = []
            for fid in flight_ids:
                cur.execute(
                    """
                    SELECT f.flight_id, f.flight_no, f.origin, f.dest, f.dep_time, f.arr_time, f.status,
                           a1.city AS origin_city, a1.name AS origin_name,
                           a2.city AS dest_city, a2.name AS dest_name
                    FROM flight f
                    JOIN airport a1 ON a1.code = f.origin
                    JOIN airport a2 ON a2.code = f.dest
                    WHERE f.flight_id = %s
                    """,
                    (fid,),
                )
                fl = cur.fetchone()
                if not fl:
                    flash(f"Flight ID {fid} not found.", "error")
                    return redirect(url_for("search"))

                cur.execute(
                    """
                    SELECT class_id, flight_id, class_name, total_seats, available_seats,
                           base_price, current_price
                    FROM fare_class
                    WHERE flight_id = %s
                    ORDER BY class_id
                    """,
                    (fid,),
                )
                fl["fare_classes"] = cur.fetchall()
                flights.append(fl)
    finally:
        conn.close()

    if request.method == "POST":
        action = request.form.get("action", "book")

        # ── Waitlist Request (direct flights only §6.4) ───────────────────────
        if action == "waitlist":
            if len(flight_ids) != 1:
                flash("Waitlist is only supported for direct flights.", "error")
                return redirect(url_for("book", ids=ids))

            class_id_str = request.form.get("class_id")
            if not class_id_str or not class_id_str.isdigit():
                flash("A fare class must be selected for waitlist.", "error")
                return redirect(url_for("book", ids=ids))

            class_id = int(class_id_str)
            seats_req = max(1, int(request.form.get("seats_requested", 1)))

            try:
                pos = add_to_waitlist(session["user_id"], class_id, seats_req)
                flash(f"Added to waitlist at position #{pos}.", "info")
                return redirect(url_for("my_bookings"))
            except Exception as e:
                flash(f"Waitlist entry failed: {e}", "error")
                return redirect(url_for("book", ids=ids))

        # ── Booking Submission ───────────────────────────────────────────────
        segments = []
        for fid in flight_ids:
            cid = request.form.get(f"class_id_{fid}") or request.form.get("class_id")
            if cid and cid.isdigit():
                segments.append({"flight_id": fid, "class_id": int(cid)})

        if len(segments) != len(flight_ids):
            flash("Please choose a fare class for each flight leg.", "error")
            return render_template(
                "book.html",
                flight_ids=ids,
                flights=flights,
                passengers_count=int(request.form.get("passengers_count", 1)),
                quoted_price=request.form.get("quoted_price", "0.00"),
            )

        names = request.form.getlist("passenger_name")
        ages = request.form.getlist("passenger_age")
        genders = request.form.getlist("passenger_gender")

        passengers = []
        if names:
            for n, a, g in zip(names, ages, genders):
                if n.strip():
                    passengers.append({
                        "name": n.strip(),
                        "age": int(a) if a.strip().isdigit() else 30,
                        "gender": g.strip().upper() if g.strip() else "U",
                    })

        if not passengers:
            pname = request.form.get("name") or session.get("user_name", "Passenger")
            page_val = request.form.get("age", "30")
            page = int(page_val) if page_val.isdigit() else 30
            pgender = request.form.get("gender", "U").strip().upper() or "U"
            passengers.append({"name": pname, "age": page, "gender": pgender})

        try:
            quoted_price = Decimal(str(request.form.get("quoted_price", "0.00")))
        except Exception:
            quoted_price = Decimal("0.00")

        try:
            result = book_ticket(
                user_id=session["user_id"],
                segments=segments,
                passengers=passengers,
                quoted_price=quoted_price,
            )
        except Exception as e:
            flash(f"Booking error: {e}", "error")
            return render_template(
                "book.html",
                flight_ids=ids,
                flights=flights,
                passengers_count=len(passengers),
                quoted_price=quoted_price,
            )

        if result["status"] == "ok":
            flash(f"Booking confirmed! PNR: {result['pnr']}", "success")
            return redirect(url_for("confirm_booking", pnr=result["pnr"]))
        elif result["status"] == "price_changed":
            new_price = result["new_price"]
            flash(
                f"Fare updated from ${quoted_price:.2f} to ${new_price:.2f}. "
                "Please review and re-confirm your booking.",
                "warning",
            )
            return render_template(
                "book.html",
                flight_ids=ids,
                flights=flights,
                passengers_count=len(passengers),
                quoted_price=new_price,
                price_updated=True,
            )
        elif result["status"] == "no_seats":
            flash("Seats are no longer available for this selection.", "error")
            return render_template(
                "book.html",
                flight_ids=ids,
                flights=flights,
                passengers_count=len(passengers),
                quoted_price=quoted_price,
                no_seats=True,
                can_waitlist=(len(flight_ids) == 1),
                failed_class_id=result.get("class_id"),
            )

    passengers_count = int(request.args.get("passengers", 1))
    quoted_price = request.args.get("quoted_price", "0.00")
    return render_template(
        "book.html",
        flight_ids=ids,
        flights=flights,
        passengers_count=passengers_count,
        quoted_price=quoted_price,
    )


@app.route("/confirm/<pnr>")
@login_required
def confirm_booking(pnr: str):
    """Display booking confirmation details and ticket seat assignments."""
    pnr = pnr.strip().upper()
    user_id = session["user_id"]
    is_adm = session.get("is_admin", False)

    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT b.pnr, b.user_id, b.status, b.total_amount, b.created_at,
                       u.name AS user_name, u.email AS user_email
                FROM booking b
                JOIN users u ON u.user_id = b.user_id
                WHERE b.pnr = %s
                """,
                (pnr,),
            )
            booking = cur.fetchone()
            if not booking:
                flash(f"Booking {pnr} not found.", "error")
                return redirect(url_for("my_bookings"))

            if booking["user_id"] != user_id and not is_adm:
                flash("Unauthorized to view this booking.", "error")
                return redirect(url_for("my_bookings"))

            cur.execute(
                """
                SELECT bs.segment_id, bs.flight_id, bs.class_id, bs.price_paid,
                       f.flight_no, f.origin, f.dest, f.dep_time, f.arr_time,
                       fc.class_name
                FROM booking_segment bs
                JOIN flight f      ON f.flight_id  = bs.flight_id
                JOIN fare_class fc ON fc.class_id  = bs.class_id
                WHERE bs.pnr = %s
                ORDER BY bs.segment_id
                """,
                (pnr,),
            )
            segments = cur.fetchall()

            cur.execute(
                """
                SELECT t.ticket_id, t.seat_no, t.status, p.name, p.age, p.gender,
                       f.flight_no, fc.class_name
                FROM ticket t
                JOIN passenger p   ON p.passenger_id = t.passenger_id
                JOIN flight f      ON f.flight_id    = t.flight_id
                JOIN fare_class fc ON fc.class_id    = t.class_id
                WHERE p.pnr = %s
                ORDER BY t.ticket_id
                """,
                (pnr,),
            )
            tickets = cur.fetchall()

            cur.execute(
                """
                SELECT payment_id, amount, method, status, paid_at
                FROM payment
                WHERE pnr = %s
                ORDER BY paid_at
                """,
                (pnr,),
            )
            payments = cur.fetchall()
    finally:
        conn.close()

    return render_template(
        "confirm.html",
        booking=booking,
        segments=segments,
        tickets=tickets,
        payments=payments,
    )


@app.route("/my-bookings")
@login_required
def my_bookings():
    """List all bookings and waitlist positions for the authenticated user."""
    user_id = session["user_id"]
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT b.pnr, b.status, b.total_amount, b.created_at,
                       COUNT(DISTINCT bs.segment_id)           AS segment_count,
                       COUNT(DISTINCT t.ticket_id)            AS ticket_count,
                       MIN(f.dep_time)                        AS first_dep,
                       MAX(f.arr_time)                        AS last_arr,
                       STRING_AGG(DISTINCT f.flight_no, ', ') AS flight_numbers
                FROM booking b
                LEFT JOIN booking_segment bs ON bs.pnr = b.pnr
                LEFT JOIN flight f           ON f.flight_id = bs.flight_id
                LEFT JOIN ticket t           ON t.segment_id = bs.segment_id
                WHERE b.user_id = %s
                GROUP BY b.pnr, b.status, b.total_amount, b.created_at
                ORDER BY b.created_at DESC
                """,
                (user_id,),
            )
            bookings = cur.fetchall()

            cur.execute(
                """
                SELECT w.wl_id, w.class_id, w.seats_requested, w.position, w.status, w.created_at,
                       fc.class_name, f.flight_no, f.origin, f.dest, f.dep_time
                FROM waitlist w
                JOIN fare_class fc ON fc.class_id = w.class_id
                JOIN flight f      ON f.flight_id = fc.flight_id
                WHERE w.user_id = %s
                ORDER BY w.created_at DESC
                """,
                (user_id,),
            )
            waitlists = cur.fetchall()
    finally:
        conn.close()

    return render_template("my_bookings.html", bookings=bookings, waitlists=waitlists)


@app.route("/cancel/<pnr>", methods=["GET", "POST"])
@login_required
def cancel(pnr: str):
    """Cancel booking and execute refund + waitlist promotion via cancellation.py."""
    pnr = pnr.strip().upper()
    user_id = session["user_id"]
    is_adm = session.get("is_admin", False)

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id, status FROM booking WHERE pnr = %s", (pnr,))
            row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        flash(f"Booking {pnr} not found.", "error")
        return redirect(url_for("my_bookings"))

    owner_id, b_status = row
    if owner_id != user_id and not is_adm:
        flash("You are not authorized to cancel this booking.", "error")
        return redirect(url_for("my_bookings"))

    if b_status == "cancelled":
        flash(f"Booking {pnr} is already cancelled.", "warning")
        return redirect(url_for("my_bookings"))

    try:
        result = cancel_booking(pnr)
        if result["status"] == "ok":
            refund = result["refund"]
            msg = f"Booking {pnr} cancelled. Refund processed: ${refund:.2f}."
            if result.get("promoted_pnr"):
                msg += f" Waitlisted user was auto-booked under PNR {result['promoted_pnr']}."
            flash(msg, "success")
        elif result["status"] == "already_cancelled":
            flash(f"Booking {pnr} is already cancelled.", "warning")
        else:
            flash(f"Cancellation error: {result['status']}", "error")
    except Exception as e:
        flash(f"Error cancelling booking: {e}", "error")

    return redirect(url_for("my_bookings"))


@app.route("/waitlist/<int:class_id>", methods=["POST"])
@login_required
def join_waitlist(class_id: int):
    """Join waitlist for a specific fare class directly."""
    user_id = session["user_id"]
    seats_req = max(1, int(request.form.get("seats_requested", 1)))

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM fare_class fc
                WHERE fc.class_id = %s
                """,
                (class_id,),
            )
            if not cur.fetchone():
                flash("Selected fare class not found.", "error")
                return redirect(url_for("search"))
    finally:
        conn.close()

    try:
        pos = add_to_waitlist(user_id, class_id, seats_req)
        flash(f"Successfully joined waitlist at position #{pos}.", "info")
    except Exception as e:
        flash(f"Failed to join waitlist: {e}", "error")

    return redirect(url_for("my_bookings"))


# ── Flight Status (Optional §7) ──────────────────────────────────────────────

@app.route("/status/<flight_no>")
def flight_status(flight_no: str):
    """Display latest schedule and status for a given flight number."""
    flight_no = flight_no.strip().upper()
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT f.flight_id, f.flight_no, f.origin, f.dest, f.dep_time, f.arr_time, f.status,
                       a1.name AS origin_name, a1.city AS origin_city,
                       a2.name AS dest_name, a2.city AS dest_city
                FROM flight f
                JOIN airport a1 ON a1.code = f.origin
                JOIN airport a2 ON a2.code = f.dest
                WHERE f.flight_no = %s
                ORDER BY f.dep_time DESC
                LIMIT 5
                """,
                (flight_no,),
            )
            flights = cur.fetchall()
    finally:
        conn.close()

    if not flights:
        flash(f"No records found for flight {flight_no}.", "warning")
        return redirect(url_for("search"))

    return render_template("flight_status.html", flights=flights, flight_no=flight_no)


# ── Admin Routes (§7 & §6.5) ──────────────────────────────────────────────────

@app.route("/admin/flights", methods=["GET", "POST"])
@admin_required
def admin_flights():
    """Admin dashboard to view flights and update status."""
    conn = get_db_connection()
    try:
        if request.method == "POST":
            flight_id = request.form.get("flight_id")
            new_status = request.form.get("status")
            if flight_id and new_status in ("scheduled", "delayed", "cancelled", "landed"):
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE flight SET status = %s WHERE flight_id = %s",
                        (new_status, int(flight_id)),
                    )
                conn.commit()
                flash(f"Flight {flight_id} status updated to {new_status}.", "success")
            else:
                flash("Invalid flight status update.", "error")
            return redirect(url_for("admin_flights"))

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT f.flight_id, f.flight_no, f.origin, f.dest, f.dep_time, f.arr_time, f.status,
                       a1.city AS origin_city, a2.city AS dest_city,
                       COALESCE(SUM(fc.total_seats), 0)     AS total_seats,
                       COALESCE(SUM(fc.available_seats), 0) AS available_seats
                FROM flight f
                JOIN airport a1 ON a1.code = f.origin
                JOIN airport a2 ON a2.code = f.dest
                LEFT JOIN fare_class fc ON fc.flight_id = f.flight_id
                GROUP BY f.flight_id, f.flight_no, f.origin, f.dest, f.dep_time, f.arr_time, f.status,
                         a1.city, a2.city
                ORDER BY f.dep_time ASC
                LIMIT 100
                """
            )
            flights = cur.fetchall()
    finally:
        conn.close()

    return render_template("admin_flights.html", flights=flights)


@app.route("/admin/fares", methods=["GET", "POST"])
@admin_required
def admin_fares():
    """Admin fare overview, price audit history, and dynamic repricing trigger."""
    conn = get_db_connection()
    try:
        if request.method == "POST":
            with conn.cursor() as cur:
                count = reprice_all(cur)
            conn.commit()
            flash(f"Dynamic repricing executed. Recalculated {count} fare classes.", "success")
            return redirect(url_for("admin_fares"))

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT fc.class_id, fc.flight_id, f.flight_no, f.origin, f.dest, f.dep_time,
                       fc.class_name, fc.total_seats, fc.available_seats,
                       fc.base_price, fc.current_price
                FROM fare_class fc
                JOIN flight f ON f.flight_id = fc.flight_id
                WHERE f.dep_time > NOW()
                ORDER BY f.dep_time ASC, fc.class_id ASC
                LIMIT 100
                """
            )
            fares = cur.fetchall()

            cur.execute(
                """
                SELECT ph.ph_id, ph.class_id, f.flight_no, fc.class_name,
                       ph.old_price, ph.new_price, ph.reason, ph.changed_at
                FROM price_history ph
                JOIN fare_class fc ON fc.class_id = ph.class_id
                JOIN flight f      ON f.flight_id = fc.flight_id
                ORDER BY ph.changed_at DESC
                LIMIT 50
                """
            )
            history = cur.fetchall()
    finally:
        conn.close()

    return render_template("admin_fares.html", fares=fares, history=history)


@app.route("/admin/analytics")
@admin_required
def admin_analytics():
    """Analytical metrics using window functions (§6.5)."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # 1. Load factor per flight: (total - available) / total
            cur.execute(
                """
                SELECT f.flight_id, f.flight_no, f.origin, f.dest, f.dep_time,
                       SUM(fc.total_seats) AS total_seats,
                       SUM(fc.available_seats) AS available_seats,
                       ROUND(
                           (SUM(fc.total_seats - fc.available_seats)::NUMERIC / NULLIF(SUM(fc.total_seats), 0)) * 100,
                           2
                       ) AS load_factor_pct
                FROM flight f
                JOIN fare_class fc ON fc.flight_id = f.flight_id
                GROUP BY f.flight_id, f.flight_no, f.origin, f.dest, f.dep_time
                ORDER BY f.dep_time DESC
                LIMIT 50
                """
            )
            load_factors = cur.fetchall()

            # 2. Revenue rank per route: RANK() OVER (PARTITION BY origin, dest ORDER BY revenue DESC)
            cur.execute(
                """
                WITH route_rev AS (
                    SELECT f.origin, f.dest, f.flight_id, f.flight_no,
                           COALESCE(SUM(bs.price_paid), 0) AS revenue
                    FROM flight f
                    LEFT JOIN booking_segment bs ON bs.flight_id = f.flight_id
                    GROUP BY f.origin, f.dest, f.flight_id, f.flight_no
                )
                SELECT origin, dest, flight_id, flight_no, revenue,
                       RANK() OVER (PARTITION BY origin, dest ORDER BY revenue DESC) AS rev_rank
                FROM route_rev
                ORDER BY origin, dest, rev_rank
                LIMIT 50
                """
            )
            route_ranks = cur.fetchall()

            # 3. Price trend per class: LAG(new_price) OVER (PARTITION BY class_id ORDER BY changed_at)
            cur.execute(
                """
                SELECT ph.ph_id, ph.class_id, f.flight_no, fc.class_name,
                       ph.old_price, ph.new_price, ph.reason, ph.changed_at,
                       LAG(ph.new_price) OVER (PARTITION BY ph.class_id ORDER BY ph.changed_at) AS prev_price
                FROM price_history ph
                JOIN fare_class fc ON fc.class_id = ph.class_id
                JOIN flight f      ON f.flight_id = fc.flight_id
                ORDER BY ph.changed_at DESC
                LIMIT 50
                """
            )
            price_trends = cur.fetchall()

            # 4. Running monthly revenue: SUM() OVER (ORDER BY day)
            cur.execute(
                """
                WITH daily_rev AS (
                    SELECT p.paid_at::DATE AS day,
                           SUM(p.amount)   AS daily_total
                    FROM payment p
                    WHERE p.status = 'paid'
                    GROUP BY p.paid_at::DATE
                )
                SELECT day, daily_total,
                       SUM(daily_total) OVER (
                           PARTITION BY DATE_TRUNC('month', day)
                           ORDER BY day
                       ) AS running_monthly_rev
                FROM daily_rev
                ORDER BY day DESC
                LIMIT 30
                """
            )
            monthly_revenue = cur.fetchall()
    finally:
        conn.close()

    return render_template(
        "admin_analytics.html",
        load_factors=load_factors,
        route_ranks=route_ranks,
        price_trends=price_trends,
        monthly_revenue=monthly_revenue,
    )


# ── App Startup ───────────────────────────────────────────────────────────────

def init_pricing():
    """Recalculate dynamic prices for future flights once at startup (§6.3)."""
    try:
        conn = get_db_connection()
        conn.autocommit = False
        with conn.cursor() as cur:
            reprice_all(cur)
            conn.commit()
        conn.close()
    except Exception:
        pass


if __name__ == "__main__":
    init_pricing()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=not _running_under_gunicorn)
