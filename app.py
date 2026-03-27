"""
ParkSmart India — Main Application (app.py)
Pure web app, no IoT hardware required.
Slot status is managed manually by vendors through the web UI.
"""
import math
import os
import base64
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from functools import wraps
from io import BytesIO

from flask import (Flask, render_template, request, redirect,
                   url_for, flash, jsonify, session, abort)
from flask_bcrypt import Bcrypt
from flask_login import (LoginManager, login_user, logout_user,
                         login_required, current_user)
from dotenv import load_dotenv

load_dotenv()

from models import (db, User, ParkingLot, ParkingSlot, Reservation,
                    UserRole, SlotType, SlotStatus, ReservationStatus, LotStatus)

# ── DB URL helper ────────────────────────────────────────────────
def _fix_db_url(url: str) -> str:
    """
    Normalise Supabase / Heroku / Render database URLs.
    - 'postgres://'      → 'postgresql://'          (SQLAlchemy 2.x)
    - 'postgresql://'   → 'postgresql+psycopg://'   (psycopg3 driver)
    SQLite URLs are returned unchanged.
    """
    if url.startswith("sqlite"):
        return url
    url = url.replace("postgres://", "postgresql://")
    # Switch to psycopg3 dialect if not already set
    if url.startswith("postgresql://") and "+psycopg" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


# ── App factory ──────────────────────────────────────────────────
def create_app():
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY            = os.getenv("SECRET_KEY", "dev-change-me-please"),
        SQLALCHEMY_DATABASE_URI = _fix_db_url(os.getenv(
            "DATABASE_URL",
            "sqlite:///parksmart.db"           # SQLite for local dev — no setup needed
        )),
        SQLALCHEMY_TRACK_MODIFICATIONS = False,
        SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True},
    )

    db.init_app(app)
    bcrypt = Bcrypt(app)

    login_mgr = LoginManager(app)
    login_mgr.login_view = "login"
    login_mgr.login_message = "Please sign in to continue."

    @login_mgr.user_loader
    def load_user(uid):
        return db.session.get(User, uid)

    # ── Register all blueprints/routes ───────────────────────────
    _auth_routes(app, bcrypt)
    _public_routes(app)
    _customer_routes(app)
    _vendor_routes(app)
    _admin_routes(app)
    _api_routes(app)

    # ── DB init ──────────────────────────────────────────────────
    with app.app_context():
        db.create_all()
        _seed(app, bcrypt)

    return app


# ── Role decorators ──────────────────────────────────────────────
def role_required(*roles):
    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapper(*args, **kwargs):
            if current_user.role not in roles:
                flash("Access denied.", "error")
                return redirect(url_for("index"))
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# ── Billing engine ───────────────────────────────────────────────
GRACE_MINUTES = 15
GST_RATE      = Decimal("0.18")

def calculate_bill(entry: datetime, exit_t: datetime,
                   vehicle_type: SlotType, lot: ParkingLot) -> dict:
    total_mins = math.ceil((exit_t - entry).total_seconds() / 60)
    total_mins = max(0, total_mins)

    if total_mins < GRACE_MINUTES:
        return {"duration_mins": total_mins, "is_grace": True,
                "base": Decimal("0"), "gst": Decimal("0"),
                "total": Decimal("0"), "hours": 0}

    hours      = math.ceil(total_mins / 60)
    rate       = lot.rate_2w if vehicle_type == SlotType.TW else lot.rate_4w
    base       = Decimal(str(rate)) * hours
    gst        = (base * GST_RATE).quantize(Decimal("0.01"))
    total      = base + gst
    return {"duration_mins": total_mins, "is_grace": False,
            "base": base, "gst": gst, "total": total, "hours": hours}


# ── QR generator ─────────────────────────────────────────────────
def make_qr_b64(data: str) -> str:
    try:
        import qrcode
        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H,
                           box_size=10, border=4)
        qr.add_data(data)
        qr.make(fit=True)
        img    = qr.make_image(fill_color="#0f172a", back_color="white")
        buf    = BytesIO()
        img.save(buf, "PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        # Fallback SVG QR placeholder if qrcode not installed
        return ""


# ── WhatsApp link ─────────────────────────────────────────────────
def whatsapp_link(phone: str, res: Reservation, lot: ParkingLot, bill: dict) -> str:
    from urllib.parse import quote
    dur = f"{bill['duration_mins']} min"
    if bill['duration_mins'] >= 60:
        h = bill['duration_mins'] // 60
        m = bill['duration_mins'] % 60
        dur = f"{h}h {m}m" if m else f"{h}h"
    msg = (
        f"🚗 *ParkSmart India — Receipt*\n\n"
        f"📍 *Lot:* {lot.name}\n"
        f"🔑 *Pass:* PS-{res.id[:8].upper()}\n"
        f"🚘 *Vehicle:* {res.vehicle_number}\n"
        f"⏱ *Duration:* {dur}\n"
        f"💰 *Amount:* ₹{bill['total']}\n"
        f"✅ Thank you for using ParkSmart India! 🇮🇳"
    )
    clean = phone.replace("+","").replace("-","").replace(" ","")
    return f"https://wa.me/{clean}?text={quote(msg)}"


# ── Haversine distance ────────────────────────────────────────────
def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = math.sin(dLat/2)**2 + math.cos(math.radians(lat1)) * \
        math.cos(math.radians(lat2)) * math.sin(dLon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


# ════════════════════════════════════════════════════════════════
#   ROUTES
# ════════════════════════════════════════════════════════════════

def _public_routes(app):
    @app.route("/")
    def index():
        lots = ParkingLot.query.filter_by(status=LotStatus.active).limit(6).all()
        return render_template("index.html", lots=lots)

    @app.route("/map")
    def map_view():
        return render_template("map.html")


def _auth_routes(app, bcrypt):
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            email    = request.form.get("email", "").lower().strip()
            password = request.form.get("password", "")
            user     = User.query.filter_by(email=email).first()
            if user and bcrypt.check_password_hash(user.password_hash, password):
                if not user.is_active:
                    flash("Account suspended. Contact support.", "error")
                    return redirect(url_for("login"))
                login_user(user, remember=True)
                return redirect(url_for("dashboard"))
            flash("Invalid email or password.", "error")
        return render_template("login.html")

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            email = request.form.get("email", "").lower().strip()
            if User.query.filter_by(email=email).first():
                flash("Email already registered.", "error")
                return redirect(url_for("register"))
            role_str = request.form.get("role", "customer")
            if role_str == "super_admin":
                flash("Cannot self-register as Super Admin.", "error")
                return redirect(url_for("register"))
            try:
                role = UserRole(role_str)
            except ValueError:
                role = UserRole.customer
            user = User(
                full_name     = request.form.get("full_name", "").strip(),
                email         = email,
                phone         = request.form.get("phone", "").strip() or None,
                password_hash = bcrypt.generate_password_hash(
                                    request.form.get("password")).decode(),
                role          = role,
                business_name = request.form.get("business_name", "").strip() or None,
            )
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash(f"Welcome, {user.full_name}! Account created.", "success")
            return redirect(url_for("dashboard"))
        return render_template("register.html")

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        flash("Logged out successfully.", "success")
        return redirect(url_for("index"))


def _customer_routes(app):
    @app.route("/dashboard")
    @login_required
    def dashboard():
        if current_user.role == UserRole.super_admin:
            return redirect(url_for("admin_dashboard"))
        if current_user.role == UserRole.vendor:
            return redirect(url_for("vendor_dashboard"))
        # Customer dashboard
        reservations = Reservation.query.filter_by(
            customer_id=current_user.id
        ).order_by(Reservation.booked_at.desc()).limit(10).all()
        active = next((r for r in reservations
                       if r.status == ReservationStatus.active), None)
        return render_template("dashboard_customer.html",
                               reservations=reservations,
                               active_reservation=active)

    @app.route("/lots")
    @login_required
    def lots_list():
        lots = ParkingLot.query.filter_by(status=LotStatus.active).all()
        return render_template("lots_list.html", lots=lots)

    @app.route("/lots/<lot_id>/book", methods=["GET", "POST"])
    @role_required(UserRole.customer)
    def book_slot(lot_id):
        lot = db.session.get(ParkingLot, lot_id)
        if not lot or lot.status != LotStatus.active:
            flash("Parking lot not found.", "error")
            return redirect(url_for("lots_list"))

        if request.method == "POST":
            slot_id = request.form.get("slot_id")
            vnum    = request.form.get("vehicle_number", "").upper().strip()
            vtype   = request.form.get("vehicle_type", "4W")

            slot = db.session.get(ParkingSlot, slot_id)
            if not slot or slot.status != SlotStatus.available:
                flash("Slot no longer available. Please choose another.", "error")
                return redirect(url_for("book_slot", lot_id=lot_id))

            try:
                vt = SlotType(vtype)
            except ValueError:
                flash("Invalid vehicle type.", "error")
                return redirect(url_for("book_slot", lot_id=lot_id))

            if slot.slot_type != vt:
                flash(f"Slot {slot.slot_number} is for {slot.slot_type.value} only.", "error")
                return redirect(url_for("book_slot", lot_id=lot_id))

            res = Reservation(
                customer_id    = current_user.id,
                slot_id        = slot.id,
                vehicle_number = vnum,
                vehicle_type   = vt,
            )
            slot.status = SlotStatus.reserved
            db.session.add(res)
            db.session.commit()
            flash(f"Slot {slot.slot_number} booked! Show your pass at entry.", "success")
            return redirect(url_for("view_pass", res_id=res.id))

        # GET — show available slots
        available_slots = [s for s in lot.slots if s.status == SlotStatus.available]
        return render_template("book_slot.html", lot=lot,
                               available_slots=available_slots)

    @app.route("/pass/<res_id>")
    @login_required
    def view_pass(res_id):
        res = db.session.get(Reservation, res_id)
        if not res:
            abort(404)
        if (res.customer_id != current_user.id and
                current_user.role not in (UserRole.vendor, UserRole.super_admin)):
            abort(403)
        lot    = res.slot.lot
        qr_url = request.url_root.rstrip("/") + url_for("scan_qr", token=res.qr_token)
        qr_b64 = make_qr_b64(qr_url)

        bill = None
        wa   = None
        if res.status == ReservationStatus.completed and res.entry_time and res.exit_time:
            bill = {
                "duration_mins": res.duration_mins,
                "is_grace":      res.is_grace,
                "total":         res.amount_charged or Decimal("0"),
            }
            if current_user.phone:
                wa = whatsapp_link(current_user.phone, res, lot, bill)

        return render_template("digital_pass.html",
                               res=res, lot=lot, qr_b64=qr_b64,
                               bill=bill, wa_link=wa)

    @app.route("/my-bookings")
    @role_required(UserRole.customer)
    def my_bookings():
        reservations = Reservation.query.filter_by(
            customer_id=current_user.id
        ).order_by(Reservation.booked_at.desc()).all()
        return render_template("my_bookings.html", reservations=reservations)

    @app.route("/cancel/<res_id>", methods=["POST"])
    @role_required(UserRole.customer)
    def cancel_booking(res_id):
        res = db.session.get(Reservation, res_id)
        if not res or res.customer_id != current_user.id:
            abort(403)
        if res.status not in (ReservationStatus.pending, ReservationStatus.active):
            flash("Cannot cancel this booking.", "error")
        else:
            res.status      = ReservationStatus.cancelled
            res.slot.status = SlotStatus.available
            db.session.commit()
            flash("Booking cancelled.", "success")
        return redirect(url_for("my_bookings"))


def _vendor_routes(app):
    @app.route("/vendor/dashboard")
    @role_required(UserRole.vendor)
    def vendor_dashboard():
        lots = ParkingLot.query.filter_by(owner_id=current_user.id).all()
        return render_template("dashboard_vendor.html", lots=lots)

    @app.route("/vendor/lots/new", methods=["GET", "POST"])
    @role_required(UserRole.vendor)
    def add_lot():
        if request.method == "POST":
            try:
                lot = ParkingLot(
                    owner_id  = current_user.id,
                    name      = request.form["name"].strip(),
                    address   = request.form["address"].strip(),
                    city      = request.form["city"].strip(),
                    state     = request.form.get("state", "Uttar Pradesh").strip(),
                    latitude  = Decimal(request.form["latitude"]),
                    longitude = Decimal(request.form["longitude"]),
                    rate_2w   = Decimal(request.form["rate_2w"]),
                    rate_4w   = Decimal(request.form["rate_4w"]),
                    opens_at  = request.form.get("opens_at", "00:00"),
                    closes_at = request.form.get("closes_at", "23:59"),
                )
                db.session.add(lot)
                db.session.commit()
                # Auto-create slots
                rows = ["A","B","C","D","E"]
                count_2w = int(request.form.get("count_2w", 10))
                count_4w = int(request.form.get("count_4w", 20))
                n = 1
                for row in rows:
                    if n > count_4w: break
                    for col in range(1, 7):
                        if n > count_4w: break
                        db.session.add(ParkingSlot(
                            lot_id=lot.id, slot_number=f"{row}-{str(col).zfill(2)}",
                            slot_type=SlotType.FW, floor="G"))
                        n += 1
                n = 1
                for row in ["F","G"]:
                    if n > count_2w: break
                    for col in range(1, 7):
                        if n > count_2w: break
                        db.session.add(ParkingSlot(
                            lot_id=lot.id, slot_number=f"{row}-{str(col).zfill(2)}",
                            slot_type=SlotType.TW, floor="G"))
                        n += 1
                db.session.commit()
                flash(f"Lot '{lot.name}' submitted for approval!", "success")
                return redirect(url_for("vendor_dashboard"))
            except Exception as e:
                flash(f"Error: {str(e)}", "error")
        return render_template("add_lot.html")

    @app.route("/vendor/lots/<lot_id>/grid")
    @role_required(UserRole.vendor)
    def lot_grid(lot_id):
        lot = db.session.get(ParkingLot, lot_id)
        if not lot or lot.owner_id != current_user.id:
            abort(403)
        reservations = Reservation.query.join(ParkingSlot).filter(
            ParkingSlot.lot_id == lot_id,
            Reservation.status.in_([ReservationStatus.active, ReservationStatus.pending])
        ).all()
        return render_template("lot_grid.html", lot=lot, reservations=reservations)

    # Vendor manually checks in a vehicle (simulates IoT gate scan)
    @app.route("/vendor/checkin/<res_id>", methods=["POST"])
    @role_required(UserRole.vendor)
    def checkin(res_id):
        res = db.session.get(Reservation, res_id)
        if not res:
            return jsonify({"error": "Not found"}), 404
        res.status      = ReservationStatus.active
        res.entry_time  = datetime.now(timezone.utc)
        res.slot.status = SlotStatus.occupied
        db.session.commit()
        return jsonify({"ok": True, "entry_time": res.entry_time.strftime("%I:%M %p")})

    # Vendor manually checks out (simulates IoT exit scan)
    @app.route("/vendor/checkout/<res_id>", methods=["POST"])
    @role_required(UserRole.vendor)
    def checkout(res_id):
        res = db.session.get(Reservation, res_id)
        if not res or res.status != ReservationStatus.active:
            return jsonify({"error": "Not active"}), 400
        exit_t = datetime.now(timezone.utc)
        lot    = res.slot.lot
        bill   = calculate_bill(res.entry_time, exit_t, res.vehicle_type, lot)
        res.exit_time      = exit_t
        res.status         = ReservationStatus.completed
        res.duration_mins  = bill["duration_mins"]
        res.amount_charged = bill["total"]
        res.is_grace       = bill["is_grace"]
        res.slot.status    = SlotStatus.available
        db.session.commit()
        return jsonify({
            "ok":           True,
            "duration_mins": bill["duration_mins"],
            "is_grace":     bill["is_grace"],
            "total":        str(bill["total"]),
        })

    # Scan QR (vendor scans customer QR code)
    @app.route("/scan/<token>")
    @login_required
    def scan_qr(token):
        res = Reservation.query.filter_by(qr_token=token).first()
        if not res:
            flash("Invalid QR code.", "error")
            return redirect(url_for("vendor_dashboard"))
        return render_template("scan_result.html", res=res, lot=res.slot.lot)

    @app.route("/vendor/slot/<slot_id>/toggle", methods=["POST"])
    @role_required(UserRole.vendor)
    def toggle_slot(slot_id):
        """Vendor manually marks a slot available/maintenance (no hardware)."""
        slot = db.session.get(ParkingSlot, slot_id)
        if not slot or slot.lot.owner_id != current_user.id:
            return jsonify({"error": "forbidden"}), 403
        new_status = request.json.get("status", "available")
        try:
            slot.status = SlotStatus(new_status)
            db.session.commit()
            return jsonify({"ok": True, "status": slot.status.value})
        except ValueError:
            return jsonify({"error": "invalid status"}), 400


def _admin_routes(app):
    @app.route("/admin/dashboard")
    @role_required(UserRole.super_admin)
    def admin_dashboard():
        users    = User.query.order_by(User.created_at.desc()).all()
        lots     = ParkingLot.query.order_by(ParkingLot.created_at.desc()).all()
        pending  = [l for l in lots if l.status == LotStatus.pending]
        total_rev = db.session.query(
            db.func.sum(Reservation.amount_charged)
        ).filter(Reservation.amount_charged != None).scalar() or 0
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0)
        today_bookings = Reservation.query.filter(
            Reservation.booked_at >= today_start).count()
        return render_template("dashboard_admin.html",
                               users=users, lots=lots, pending=pending,
                               total_rev=total_rev, today_bookings=today_bookings)

    @app.route("/admin/lots/<lot_id>/approve", methods=["POST"])
    @role_required(UserRole.super_admin)
    def approve_lot(lot_id):
        lot = db.session.get(ParkingLot, lot_id)
        if lot:
            lot.status = LotStatus.active
            db.session.commit()
            flash(f"'{lot.name}' approved and now live!", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/lots/<lot_id>/reject", methods=["POST"])
    @role_required(UserRole.super_admin)
    def reject_lot(lot_id):
        lot = db.session.get(ParkingLot, lot_id)
        if lot:
            lot.status = LotStatus.rejected
            db.session.commit()
            flash(f"'{lot.name}' rejected.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/users/<user_id>/toggle", methods=["POST"])
    @role_required(UserRole.super_admin)
    def toggle_user(user_id):
        user = db.session.get(User, user_id)
        if user and user.role != UserRole.super_admin:
            user.is_active = not user.is_active
            db.session.commit()
            flash(f"User {'activated' if user.is_active else 'suspended'}.", "success")
        return redirect(url_for("admin_dashboard"))


def _api_routes(app):
    """JSON API endpoints for JavaScript polling."""

    @app.route("/api/lots/nearby")
    def api_nearby():
        lat    = float(request.args.get("lat", 26.8467))
        lng    = float(request.args.get("lng", 80.9462))
        radius = float(request.args.get("radius", 10))
        lots   = ParkingLot.query.filter_by(status=LotStatus.active).all()
        result = []
        for lot in lots:
            dist = haversine(lat, lng, float(lot.latitude), float(lot.longitude))
            if dist <= radius:
                d = lot.to_dict()
                d["distance_km"] = round(dist, 2)
                result.append(d)
        result.sort(key=lambda x: x["distance_km"])
        return jsonify({"lots": result})

    @app.route("/api/lots/<lot_id>/slots")
    def api_slots(lot_id):
        lot = db.session.get(ParkingLot, lot_id)
        if not lot:
            return jsonify({"error": "Not found"}), 404
        slots = [s.to_dict() for s in lot.slots]
        summary = {
            "total":     len(slots),
            "available": sum(1 for s in slots if s["status"] == "available"),
            "occupied":  sum(1 for s in slots if s["status"] == "occupied"),
            "reserved":  sum(1 for s in slots if s["status"] == "reserved"),
        }
        return jsonify({"slots": slots, "summary": summary})


# ── Seed ──────────────────────────────────────────────────────────
def _seed(app, bcrypt):
    admin_email = os.getenv("SUPER_ADMIN_EMAIL", "admin@parksmart.in")
    if not User.query.filter_by(email=admin_email).first():
        admin = User(
            full_name     = "ParkSmart Admin",
            email         = admin_email,
            password_hash = bcrypt.generate_password_hash(
                os.getenv("SUPER_ADMIN_PASSWORD", "Admin@123")).decode(),
            role          = UserRole.super_admin,
            is_active     = True,
        )
        db.session.add(admin)

        # Demo vendor
        vendor = User(
            full_name     = "Ramesh Kumar",
            email         = "vendor@parksmart.in",
            password_hash = bcrypt.generate_password_hash("Vendor@123").decode(),
            role          = UserRole.vendor,
            business_name = "Kumar Parking Solutions",
            is_active     = True,
        )
        db.session.add(vendor)
        db.session.flush()

        # Demo lot
        lot = ParkingLot(
            owner_id  = vendor.id,
            name      = "Hazratganj Central Parking",
            address   = "Hazratganj, Near GPO",
            city      = "Lucknow",
            latitude  = Decimal("26.8483"),
            longitude = Decimal("80.9462"),
            rate_2w   = Decimal("10"),
            rate_4w   = Decimal("30"),
            status    = LotStatus.active,
        )
        db.session.add(lot)
        db.session.flush()

        # Demo slots
        for row in ["A","B","C"]:
            for col in range(1, 7):
                st = SlotStatus.available if col % 3 != 0 else SlotStatus.occupied
                db.session.add(ParkingSlot(
                    lot_id=lot.id,
                    slot_number=f"{row}-{str(col).zfill(2)}",
                    slot_type=SlotType.FW,
                    status=st, floor="G"))
        for col in range(1, 9):
            db.session.add(ParkingSlot(
                lot_id=lot.id,
                slot_number=f"D-{str(col).zfill(2)}",
                slot_type=SlotType.TW,
                status=SlotStatus.available, floor="G"))

        # Demo customer
        customer = User(
            full_name     = "Priya Singh",
            email         = "customer@parksmart.in",
            password_hash = bcrypt.generate_password_hash("Customer@123").decode(),
            role          = UserRole.customer,
            phone         = "919876543210",
            is_active     = True,
        )
        db.session.add(customer)
        db.session.commit()
        print("✅ Demo accounts seeded:")
        print(f"   Admin:    {admin_email}  / Admin@123")
        print("   Vendor:   vendor@parksmart.in / Vendor@123")
        print("   Customer: customer@parksmart.in / Customer@123")


# ── Run ───────────────────────────────────────────────────────────
app = create_app()

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0",
            port=int(os.getenv("PORT", 5000)))
