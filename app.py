import os, base64, io, json
from decimal import Decimal, InvalidOperation
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from dotenv import load_dotenv
from models import db, User, ParkingLot, ParkingSlot, Reservation

load_dotenv()

# ── Database URL fix ──────────────────────────────────────────────────────────
def get_db_url():
    url = os.environ.get('DATABASE_URL', '').strip()
    if not url:
        print("[DB] No DATABASE_URL — using SQLite (local dev)")
        return 'sqlite:///parksmart.db'
    # Render/Heroku give postgres:// — SQLAlchemy needs postgresql://
    if url.startswith('postgres://'):
        url = 'postgresql://' + url[len('postgres://'):]
    # Supabase & Neon need sslmode=require for psycopg2
    if 'sslmode' not in url:
        sep = '&' if '?' in url else '?'
        url = url + sep + 'sslmode=require'
    print("[DB] Using PostgreSQL")
    return url

# ── App Factory ───────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-me')

db_url = get_db_url()
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_recycle': 280,
    'pool_pre_ping': True,
}

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to continue.'

@login_manager.user_loader
def load_user(uid):
    return db.session.get(User, int(uid))

with app.app_context():
    try:
        db.create_all()
        admin_email = os.environ.get('ADMIN_EMAIL', 'admin@parksmart.in')
        admin_pw    = os.environ.get('ADMIN_PASSWORD', 'Admin@1234')
        if not User.query.filter_by(email=admin_email).first():
            admin = User(name='Super Admin', email=admin_email, role='admin', is_approved=True)
            admin.set_password(admin_pw)
            db.session.add(admin)
            db.session.commit()
            print(f"[DB] Admin created: {admin_email}")
        print("[DB] Database ready ✅")
    except Exception as e:
        print(f"[DB] WARNING: Could not connect to DB on startup: {e}")
        print("[DB] App will still start — check DATABASE_URL in environment")

# ── Helpers ───────────────────────────────────────────────────────────────────
def _safe_decimal(val, default=0):
    try:
        return Decimal(str(val).replace(',', '').strip())
    except (InvalidOperation, ValueError):
        return Decimal(str(default))

def calculate_bill(entry_time, exit_time, vehicle_type, rate_2w, rate_4w):
    minutes = (exit_time - entry_time).total_seconds() / 60
    if minutes < 15:
        return Decimal('0.00')
    hours = Decimal(str((exit_time - entry_time).total_seconds() / 3600))
    rate  = Decimal(str(rate_2w)) if vehicle_type == '2w' else Decimal(str(rate_4w))
    return (hours * rate).quantize(Decimal('0.01'))

def generate_qr_base64(token):
    try:
        import qrcode
        img = qrcode.make(token)
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        print(f"[QR] Error: {e}")
        return ''

def build_whatsapp_url(res):
    lot = res.slot.lot
    msg = (
        f"Namaste! 🙏%0A"
        f"Your parking at *{lot.name}* is confirmed.%0A"
        f"Slot: *{res.slot.label}* | Vehicle: {res.vehicle_no}%0A"
        f"Entry: {res.entry_time.strftime('%d %b %Y, %I:%M %p')}%0A"
        f"ParkSmart India 🚗"
    )
    return f"https://wa.me/?text={msg}"

def redirect_by_role():
    if current_user.role == 'admin':   return redirect(url_for('admin_dashboard'))
    if current_user.role == 'vendor':  return redirect(url_for('vendor_dashboard'))
    return redirect(url_for('customer_dashboard'))

# ── Auth ──────────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect_by_role()
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        pw    = request.form.get('password', '')
        user  = User.query.filter_by(email=email).first()
        if user and user.check_password(pw):
            if user.role == 'vendor' and not user.is_approved:
                flash('Your vendor account is awaiting admin approval.', 'warning')
                return redirect(url_for('login'))
            login_user(user)
            return redirect_by_role()
        flash('Invalid email or password.', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name  = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        pw    = request.form.get('password', '')
        role  = request.form.get('role', 'customer')
        phone = request.form.get('phone', '').strip()

        if not name or not email or not pw:
            flash('Name, email and password are required.', 'danger')
            return render_template('register.html')
        if User.query.filter_by(email=email).first():
            flash('Email already registered. Please login.', 'danger')
            return render_template('register.html')
        if role not in ('customer', 'vendor'):
            role = 'customer'

        user = User(name=name, email=email, role=role, phone=phone,
                    is_approved=(role == 'customer'))
        user.set_password(pw)
        db.session.add(user)
        db.session.commit()

        if role == 'vendor':
            flash('Vendor account created! Awaiting admin approval.', 'info')
            return redirect(url_for('login'))
        login_user(user)
        return redirect(url_for('customer_dashboard'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# ── Admin ─────────────────────────────────────────────────────────────────────
@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    vendors      = User.query.filter_by(role='vendor').all()
    customers    = User.query.filter_by(role='customer').all()
    lots         = ParkingLot.query.all()
    reservations = Reservation.query.order_by(Reservation.created_at.desc()).limit(20).all()
    return render_template('dashboard_admin.html',
                           vendors=vendors, customers=customers,
                           lots=lots, reservations=reservations)

@app.route('/admin/approve_vendor/<int:uid>', methods=['POST'])
@login_required
def approve_vendor(uid):
    if current_user.role != 'admin':
        flash('Forbidden.', 'danger')
        return redirect(url_for('index'))
    user = db.session.get(User, uid)
    if user and user.role == 'vendor':
        user.is_approved = True
        db.session.commit()
        flash(f'Vendor {user.name} approved!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/approve_lot/<int:lid>', methods=['POST'])
@login_required
def approve_lot(lid):
    if current_user.role != 'admin':
        flash('Forbidden.', 'danger')
        return redirect(url_for('index'))
    lot = db.session.get(ParkingLot, lid)
    if lot:
        lot.is_active = True
        db.session.commit()
        flash(f'Lot "{lot.name}" is now live!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/db')
@login_required
def admin_db_view():
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    users        = User.query.all()
    lots         = ParkingLot.query.all()
    reservations = Reservation.query.order_by(Reservation.created_at.desc()).all()
    return render_template('db_view.html', users=users, lots=lots, reservations=reservations)

# ── Vendor ────────────────────────────────────────────────────────────────────
@app.route('/vendor/dashboard')
@login_required
def vendor_dashboard():
    if current_user.role != 'vendor':
        return redirect(url_for('index'))
    lots = ParkingLot.query.filter_by(owner_id=current_user.id).all()
    return render_template('dashboard_vendor.html', lots=lots)

@app.route('/vendor/add_lot', methods=['GET', 'POST'])
@login_required
def add_lot():
    if current_user.role != 'vendor':
        return redirect(url_for('index'))
    if request.method == 'POST':
        try:
            name        = request.form.get('name', '').strip()
            address     = request.form.get('address', '').strip()
            city        = request.form.get('city', '').strip()
            lat_str     = request.form.get('latitude', '').strip()
            lng_str     = request.form.get('longitude', '').strip()
            slots_str   = request.form.get('total_slots', '').strip()
            rate_2w_str = request.form.get('rate_2w', '').strip()
            rate_4w_str = request.form.get('rate_4w', '').strip()

            # Validate all fields present
            if not all([name, address, city, lat_str, lng_str, slots_str, rate_2w_str, rate_4w_str]):
                flash('All fields are required.', 'danger')
                return render_template('add_lot.html')

            # Parse numbers
            try:
                lat   = float(lat_str)
                lng   = float(lng_str)
                total = int(slots_str)
            except ValueError:
                flash('Latitude, Longitude must be decimals and Slots must be a whole number.', 'danger')
                return render_template('add_lot.html')

            rate_2w = _safe_decimal(rate_2w_str)
            rate_4w = _safe_decimal(rate_4w_str)

            if total < 1 or total > 500:
                flash('Slot count must be between 1 and 500.', 'danger')
                return render_template('add_lot.html')
            if rate_2w <= 0 or rate_4w <= 0:
                flash('Rates must be greater than zero.', 'danger')
                return render_template('add_lot.html')

            lot = ParkingLot(
                owner_id=current_user.id, name=name, address=address,
                city=city, latitude=lat, longitude=lng,
                total_slots=total, rate_2w=rate_2w, rate_4w=rate_4w, is_active=False
            )
            db.session.add(lot)
            db.session.flush()  # get lot.id without full commit

            for i in range(1, total + 1):
                stype = '2w' if i <= total // 2 else '4w'
                db.session.add(ParkingSlot(
                    lot_id=lot.id, label=f'S{i:03d}', status='available', slot_type=stype
                ))

            db.session.commit()
            flash(f'Lot "{name}" added! Awaiting admin approval.', 'success')
            return redirect(url_for('vendor_dashboard'))

        except Exception as e:
            db.session.rollback()
            flash(f'Server error: {str(e)}', 'danger')
            return render_template('add_lot.html')

    return render_template('add_lot.html')

@app.route('/vendor/lot/<int:lid>')
@login_required
def vendor_lot_grid(lid):
    if current_user.role not in ('vendor', 'admin'):
        return redirect(url_for('index'))
    lot = db.session.get(ParkingLot, lid)
    if not lot or (current_user.role == 'vendor' and lot.owner_id != current_user.id):
        flash('Lot not found.', 'danger')
        return redirect(url_for('vendor_dashboard'))
    return render_template('lot_grid.html', lot=lot)

@app.route('/vendor/slot/<int:sid>/toggle', methods=['POST'])
@login_required
def toggle_slot(sid):
    if current_user.role not in ('vendor', 'admin'):
        return jsonify({'error': 'Forbidden'}), 403
    slot = db.session.get(ParkingSlot, sid)
    if not slot:
        return jsonify({'error': 'Not found'}), 404
    slot.status = 'occupied' if slot.status == 'available' else 'available'
    db.session.commit()
    return jsonify({'id': slot.id, 'status': slot.status})

# ── Live Grid API ─────────────────────────────────────────────────────────────
@app.route('/api/lot/<int:lid>/slots')
@login_required
def api_lot_slots(lid):
    lot = db.session.get(ParkingLot, lid)
    if not lot:
        return jsonify({'error': 'Not found'}), 404
    return jsonify({
        'slots':     [s.to_dict() for s in lot.slots],
        'available': lot.available_count,
        'occupied':  lot.occupied_count,
        'total':     lot.total_slots,
    })

# ── Customer ──────────────────────────────────────────────────────────────────
@app.route('/customer/dashboard')
@login_required
def customer_dashboard():
    if current_user.role != 'customer':
        return redirect(url_for('index'))
    reservations = (Reservation.query
                    .filter_by(customer_id=current_user.id)
                    .order_by(Reservation.created_at.desc()).all())
    return render_template('dashboard_customer.html', reservations=reservations)

@app.route('/lots')
def lots_list():
    lots      = ParkingLot.query.filter_by(is_active=True).all()
    lots_json = [l.to_dict() for l in lots]
    return render_template('lots_list.html', lots=lots, lots_json=lots_json)

@app.route('/lot/<int:lid>/book', methods=['GET', 'POST'])
@login_required
def book_slot(lid):
    if current_user.role != 'customer':
        flash('Only customers can book slots.', 'warning')
        return redirect(url_for('index'))
    lot = db.session.get(ParkingLot, lid)
    if not lot or not lot.is_active:
        flash('Parking lot not available.', 'danger')
        return redirect(url_for('lots_list'))

    available_slots = [s for s in lot.slots if s.status == 'available']

    if request.method == 'POST':
        slot_id      = request.form.get('slot_id', '').strip()
        vehicle_no   = request.form.get('vehicle_no', '').strip().upper()
        vehicle_type = request.form.get('vehicle_type', '4w')

        if not slot_id or not vehicle_no:
            flash('Please select a slot and enter your vehicle number.', 'danger')
            return render_template('book_slot.html', lot=lot, slots=available_slots)

        slot = db.session.get(ParkingSlot, int(slot_id))
        if not slot or slot.status != 'available':
            flash('That slot is no longer available. Please choose another.', 'warning')
            return redirect(url_for('book_slot', lid=lid))

        slot.status = 'occupied'
        res = Reservation(
            customer_id=current_user.id, slot_id=slot.id,
            vehicle_no=vehicle_no, vehicle_type=vehicle_type
        )
        db.session.add(res)
        db.session.commit()
        flash('Booking confirmed! 🎉', 'success')
        return redirect(url_for('digital_pass', rid=res.id))

    return render_template('book_slot.html', lot=lot, slots=available_slots)

@app.route('/reservation/<int:rid>/pass')
@login_required
def digital_pass(rid):
    res = db.session.get(Reservation, rid)
    if not res or res.customer_id != current_user.id:
        flash('Pass not found.', 'danger')
        return redirect(url_for('customer_dashboard'))
    qr_b64 = generate_qr_base64(res.qr_token)
    wa_url  = build_whatsapp_url(res)
    return render_template('digital_pass.html', res=res, qr_b64=qr_b64, wa_url=wa_url)

@app.route('/reservation/<int:rid>/checkout', methods=['POST'])
@login_required
def checkout(rid):
    res = db.session.get(Reservation, rid)
    if not res or res.status != 'active':
        flash('Reservation not found or already completed.', 'danger')
        return redirect(url_for('customer_dashboard'))
    if current_user.role == 'customer' and res.customer_id != current_user.id:
        flash('Not authorised.', 'danger')
        return redirect(url_for('index'))

    res.exit_time   = datetime.utcnow()
    res.status      = 'completed'
    lot             = res.slot.lot
    res.amount_paid = calculate_bill(
        res.entry_time, res.exit_time, res.vehicle_type, lot.rate_2w, lot.rate_4w
    )
    res.slot.status = 'available'
    db.session.commit()
    flash(f'Checkout done! Amount: ₹{res.amount_paid}', 'success')
    return redirect(url_for('digital_pass', rid=rid))

# ── Health Check ──────────────────────────────────────────────────────────────
@app.route('/health')
def health():
    try:
        db_type = 'postgresql' if 'postgresql' in app.config['SQLALCHEMY_DATABASE_URI'] else 'sqlite'
        return jsonify({
            'status': 'ok ✅',
            'db': f'connected ({db_type})',
            'users': User.query.count(),
            'lots': ParkingLot.query.count(),
            'reservations': Reservation.query.count(),
        })
    except Exception as e:
        return jsonify({
            'status': 'error ❌',
            'db': 'NOT connected',
            'error': str(e),
            'fix': 'Set DATABASE_URL in Render > Environment'
        }), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500
