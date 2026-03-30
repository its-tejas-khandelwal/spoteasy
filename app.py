import os, base64, io, threading, time
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory, make_response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user

# ── Self-Ping Keep-Alive (prevents Render free tier from sleeping) ─────────────
def _keep_alive():
    """Pings own /health endpoint every 13 minutes so Render never sleeps."""
    time.sleep(60)  # wait 1 min after startup before first ping
    app_url = os.environ.get('RENDER_EXTERNAL_URL', '')
    if not app_url:
        print("[KeepAlive] No RENDER_EXTERNAL_URL set — skipping self-ping")
        return
    import requests as _req
    while True:
        try:
            r = _req.get(f"{app_url}/health", timeout=10)
            print(f"[KeepAlive] Pinged {app_url}/health → {r.status_code}")
        except Exception as e:
            print(f"[KeepAlive] Ping failed: {e}")
        time.sleep(13 * 60)  # 13 minutes

_ping_thread = threading.Thread(target=_keep_alive, daemon=True)
_ping_thread.start()
from dotenv import load_dotenv
from models import db, User, ParkingLot, ParkingSlot, Reservation

load_dotenv()

# IST timezone
IST = timezone(timedelta(hours=5, minutes=30))

def now_ist():
    return datetime.now(IST).replace(tzinfo=None)

def to_ist(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST).replace(tzinfo=None)

# ── Database URL ───────────────────────────────────────────────────────────────
def get_db_url():
    url = os.environ.get('DATABASE_URL', '').strip()
    if not url:
        print("[DB] No DATABASE_URL — using SQLite (local dev)")
        return 'sqlite:///parksmart.db'
    if url.startswith('postgres://'):
        url = 'postgresql://' + url[len('postgres://'):]
    if 'sslmode' not in url:
        sep = '&' if '?' in url else '?'
        url = url + sep + 'sslmode=require'
    print("[DB] Using PostgreSQL")
    return url

# ── App ────────────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = get_db_url()
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Firebase config (set these in Render environment)
app.config['FIREBASE_API_KEY']        = os.environ.get('FIREBASE_API_KEY', '')
app.config['FIREBASE_AUTH_DOMAIN']    = os.environ.get('FIREBASE_AUTH_DOMAIN', '')
app.config['FIREBASE_PROJECT_ID']     = os.environ.get('FIREBASE_PROJECT_ID', '')
app.config['FIREBASE_STORAGE_BUCKET'] = os.environ.get('FIREBASE_STORAGE_BUCKET', '')
app.config['FIREBASE_SENDER_ID']      = os.environ.get('FIREBASE_SENDER_ID', '')
app.config['FIREBASE_APP_ID']         = os.environ.get('FIREBASE_APP_ID', '')
app.config['FIREBASE_VAPID_KEY']      = os.environ.get('FIREBASE_VAPID_KEY', '')
# UPI Payment — set your UPI ID in Render environment
app.config['VENDOR_UPI_ID']           = os.environ.get('VENDOR_UPI_ID', 'spoteasy@upi')
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_recycle': 280, 'pool_pre_ping': True}

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to continue.'

@login_manager.user_loader
def load_user(uid):
    try:
        return db.session.get(User, int(uid))
    except (ValueError, TypeError):
        return None
    except Exception:
        db.session.rollback()
        return None

with app.app_context():
    try:
        db.create_all()
        admin_email = os.environ.get('ADMIN_EMAIL', 'admin@spoteasy.in')
        admin_pw    = os.environ.get('ADMIN_PASSWORD', 'Admin@1234')
        if not User.query.filter_by(email=admin_email).first():
            admin = User(name='Super Admin', email=admin_email, role='admin', is_approved=True)
            admin.set_password(admin_pw)
            db.session.add(admin)
            db.session.commit()
            print(f"[DB] Admin created: {admin_email}")
        print("[DB] Database ready ✅")
    except Exception as e:
        print(f"[DB] WARNING: {e}")

# ── Helpers ────────────────────────────────────────────────────────────────────
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
        from qrcode.image.pure import PyPNGImage
        qr = qrcode.QRCode(version=1, box_size=8, border=2)
        qr.add_data(token)
        qr.make(fit=True)
        img = qr.make_image(image_factory=PyPNGImage)
        buf = io.BytesIO()
        img.save(buf)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode()
    except Exception as e:
        print(f"[QR] PyPNG failed: {e}, trying PIL...")
        try:
            import qrcode as qr2
            img2 = qr2.make(token)
            buf2 = io.BytesIO()
            img2.save(buf2, format='PNG')
            buf2.seek(0)
            return base64.b64encode(buf2.read()).decode()
        except Exception as e2:
            print(f"[QR] All methods failed: {e2}")
            return ''

def build_whatsapp_url(res):
    lot      = res.slot.lot
    ist_time = to_ist(res.entry_time)
    duration_hint = "Grace period: FREE if exit within 15 mins! ⏰"
    rate = f"₹{lot.rate_2w}/hr (🛵)" if res.vehicle_type == '2w' else f"₹{lot.rate_4w}/hr (🚗)"
    msg = (
        f"🅿️ *SpotEasy* — Booking Confirmed!%0A"
        f"━━━━━━━━━━━━━━━━━━━━%0A"
        f"🏢 *Lot:* {lot.name}%0A"
        f"📍 *Address:* {lot.address}, {lot.city}%0A"
        f"🔢 *Slot:* {res.slot.label}%0A"
        f"🚘 *Vehicle:* {res.vehicle_no} ({'2-Wheeler' if res.vehicle_type=='2w' else '4-Wheeler'})%0A"
        f"⏱️ *Entry:* {ist_time.strftime('%d %b %Y, %I:%M %p')} IST%0A"
        f"💰 *Rate:* {rate}%0A"
        f"━━━━━━━━━━━━━━━━━━━━%0A"
        f"{duration_hint}%0A"
        f"Show QR code at entry/exit gate.%0A"
        f"🙏 _Powered by SpotEasy_"
    )
    return f"https://wa.me/?text={msg}"

def redirect_by_role():
    if current_user.role == 'admin':  return redirect(url_for('admin_dashboard'))
    if current_user.role == 'vendor': return redirect(url_for('vendor_dashboard'))
    return redirect(url_for('customer_dashboard'))

# Pass IST converter to all templates
@app.context_processor
def inject_helpers():
    return {'to_ist': to_ist, 'now_ist': now_ist()}

# ── Email Helper ──────────────────────────────────────────────────────────────
def send_email(to_email, subject, html_body):
    """Send email via SMTP. Set MAIL_USER and MAIL_PASS in Railway env vars."""
    try:
        gmail_user = os.environ.get('MAIL_USER', '')
        gmail_pass = os.environ.get('MAIL_PASS', '')
        if not gmail_user or not gmail_pass:
            print(f"[Email] No credentials set — skipping email to {to_email}")
            return False
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From']    = f"SpotEasy India <{gmail_user}>"
        msg['To']      = to_email
        msg.attach(MIMEText(html_body, 'html'))
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(gmail_user, gmail_pass)
            server.sendmail(gmail_user, to_email, msg.as_string())
        print(f"[Email] ✅ Sent to {to_email}: {subject}")
        return True
    except Exception as e:
        print(f"[Email] ❌ Failed: {e}")
        return False

# ── Auth ───────────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    try:
        total_lots  = ParkingLot.query.filter_by(is_active=True).count()
        total_slots = sum(l.total_slots for l in ParkingLot.query.filter_by(is_active=True).all())
        cities      = list(set(l.city for l in ParkingLot.query.filter_by(is_active=True).all()))
        city_count  = len(cities)
    except Exception:
        total_lots = total_slots = city_count = 0
    return render_template('index.html',
        total_lots=total_lots,
        total_slots=total_slots,
        city_count=city_count)

@app.route('/api/public/stats')
def api_public_stats():
    try:
        lots       = ParkingLot.query.filter_by(is_active=True).all()
        total_lots = len(lots)
        total_slots= sum(l.total_slots for l in lots)
        free_slots = sum(l.available_count for l in lots)
        cities     = list(set(l.city for l in lots))
        total_users= User.query.filter_by(role='customer').count()
        return jsonify({
            'total_lots':  total_lots,
            'total_slots': total_slots,
            'free_slots':  free_slots,
            'city_count':  len(cities),
            'cities':      cities,
            'total_users': total_users,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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

# ── Admin ──────────────────────────────────────────────────────────────────────
@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if current_user.role != 'admin': return redirect(url_for('index'))
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
    if current_user.role != 'admin': return redirect(url_for('index'))
    user = db.session.get(User, uid)
    if user and user.role == 'vendor':
        user.is_approved = True
        db.session.commit()
        flash(f'Vendor {user.name} approved!', 'success')
        # Send approval email
        site_url = os.environ.get('RENDER_EXTERNAL_URL', 'https://www.spoteasy.in')
        email_html = f'''
        <div style="font-family:Inter,sans-serif;max-width:520px;margin:0 auto;background:#f9fafb;padding:32px;">
          <div style="background:linear-gradient(135deg,#16a34a,#22c55e);border-radius:20px;padding:32px;text-align:center;margin-bottom:24px;">
            <div style="font-size:48px;margin-bottom:12px;">🎉</div>
            <h1 style="color:white;font-size:24px;font-weight:900;margin:0;">You are Approved!</h1>
            <p style="color:rgba(255,255,255,0.85);margin:8px 0 0;font-size:14px;">Your SpotEasy Vendor account is now active</p>
          </div>
          <div style="background:white;border-radius:16px;padding:24px;margin-bottom:16px;border:1px solid #e5e7eb;">
            <p style="color:#374151;font-size:15px;line-height:1.6;">Hi <b>{user.name}</b>,</p>
            <p style="color:#374151;font-size:14px;line-height:1.7;margin-top:12px;">
              Great news! Your parking vendor account on <b>SpotEasy India</b> has been approved by our admin team.
              You can now log in and start adding your parking lots.
            </p>
            <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:12px;padding:16px;margin:16px 0;">
              <p style="color:#166534;font-weight:700;font-size:13px;margin:0 0 8px;">What you can do now:</p>
              <p style="color:#166534;font-size:13px;margin:4px 0;">✅ Add your parking lot</p>
              <p style="color:#166534;font-size:13px;margin:4px 0;">✅ Set slot counts for 2-wheelers & 4-wheelers</p>
              <p style="color:#166534;font-size:13px;margin:4px 0;">✅ Set your hourly rates</p>
              <p style="color:#166534;font-size:13px;margin:4px 0;">✅ View live slot grid and manage bookings</p>
            </div>
            <a href="{site_url}/login" style="display:block;background:linear-gradient(135deg,#16a34a,#22c55e);color:white;text-align:center;padding:14px;border-radius:12px;font-weight:800;font-size:15px;text-decoration:none;margin-top:16px;">
              Login to SpotEasy →
            </a>
          </div>
          <p style="color:#9ca3af;font-size:11px;text-align:center;">SpotEasy India &copy; 2026 &bull; Smart Parking Platform</p>
        </div>'''
        send_email(user.email, '🎉 Your SpotEasy Vendor Account is Approved!', email_html)
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/approve_lot/<int:lid>', methods=['POST'])
@login_required
def approve_lot(lid):
    if current_user.role != 'admin': return redirect(url_for('index'))
    lot = db.session.get(ParkingLot, lid)
    if lot:
        lot.is_active = True
        db.session.commit()
        flash(f'Lot "{lot.name}" is now live!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/db')
@login_required
def admin_db_view():
    if current_user.role != 'admin': return redirect(url_for('index'))
    users        = User.query.all()
    lots         = ParkingLot.query.all()
    reservations = Reservation.query.order_by(Reservation.created_at.desc()).all()
    return render_template('db_view.html', users=users, lots=lots, reservations=reservations)

# ── Vendor ─────────────────────────────────────────────────────────────────────
@app.route('/vendor/dashboard')
@login_required
def vendor_dashboard():
    if current_user.role != 'vendor': return redirect(url_for('index'))
    lots = ParkingLot.query.filter_by(owner_id=current_user.id).all()
    return render_template('dashboard_vendor.html', lots=lots)

@app.route('/vendor/add_lot', methods=['GET', 'POST'])
@login_required
def add_lot():
    if current_user.role != 'vendor': return redirect(url_for('index'))
    if request.method == 'POST':
        try:
            name        = request.form.get('name', '').strip()
            address     = request.form.get('address', '').strip()
            city        = request.form.get('city', '').strip()
            lat_str     = request.form.get('latitude', '').strip()
            lng_str     = request.form.get('longitude', '').strip()
            slots_2w    = request.form.get('slots_2w', '0').strip()
            slots_4w    = request.form.get('slots_4w', '0').strip()
            rate_2w_str = request.form.get('rate_2w', '').strip()
            rate_4w_str = request.form.get('rate_4w', '').strip()

            if not all([name, address, city, lat_str, lng_str, rate_2w_str, rate_4w_str]):
                flash('All fields are required.', 'danger')
                return render_template('add_lot.html')
            try:
                lat    = float(lat_str)
                lng    = float(lng_str)
                n_2w   = int(slots_2w) if slots_2w else 0
                n_4w   = int(slots_4w) if slots_4w else 0
            except ValueError:
                flash('Latitude, Longitude and slot counts must be valid numbers.', 'danger')
                return render_template('add_lot.html')

            total = n_2w + n_4w
            if total < 1:
                flash('Total slots must be at least 1.', 'danger')
                return render_template('add_lot.html')

            rate_2w = _safe_decimal(rate_2w_str)
            rate_4w = _safe_decimal(rate_4w_str)
            if rate_2w <= 0 or rate_4w <= 0:
                flash('Rates must be greater than zero.', 'danger')
                return render_template('add_lot.html')

            lot = ParkingLot(
                owner_id=current_user.id, name=name, address=address,
                city=city, latitude=lat, longitude=lng,
                total_slots=total, rate_2w=rate_2w, rate_4w=rate_4w, is_active=False
            )
            db.session.add(lot)
            db.session.flush()

            for i in range(1, n_2w + 1):
                db.session.add(ParkingSlot(lot_id=lot.id, label=f'2W-{i:03d}', status='available', slot_type='2w'))
            for i in range(1, n_4w + 1):
                db.session.add(ParkingSlot(lot_id=lot.id, label=f'4W-{i:03d}', status='available', slot_type='4w'))

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
    if current_user.role not in ('vendor', 'admin'): return redirect(url_for('index'))
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

@app.route('/api/lot/<int:lid>/slots')
@login_required
def api_lot_slots(lid):
    lot = db.session.get(ParkingLot, lid)
    if not lot: return jsonify({'error': 'Not found'}), 404
    return jsonify({
        'slots':     [s.to_dict() for s in lot.slots],
        'available': lot.available_count,
        'occupied':  lot.occupied_count,
        'total':     lot.total_slots,
        'avail_2w':  sum(1 for s in lot.slots if s.slot_type=='2w' and s.status=='available'),
        'avail_4w':  sum(1 for s in lot.slots if s.slot_type=='4w' and s.status=='available'),
    })

# ── Customer ───────────────────────────────────────────────────────────────────
@app.route('/customer/dashboard')
@login_required
def customer_dashboard():
    if current_user.role != 'customer': return redirect(url_for('index'))
    reservations = (Reservation.query.filter_by(customer_id=current_user.id)
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
            flash('Slot no longer available. Please choose another.', 'warning')
            return redirect(url_for('book_slot', lid=lid))
        slot.status = 'occupied'
        res = Reservation(
            customer_id=current_user.id, slot_id=slot.id,
            vehicle_no=vehicle_no, vehicle_type=vehicle_type,
            entry_time=now_ist()
        )
        db.session.add(res)
        db.session.commit()
        flash('Booking confirmed! 🎉', 'success')
        # Send booking confirmation email to customer
        try:
            site_url = os.environ.get('RENDER_EXTERNAL_URL', 'https://www.spoteasy.in')
            rate = lot.rate_2w if slot.vehicle_type == '2w' else lot.rate_4w
            booking_html = f'''
            <div style="font-family:Inter,sans-serif;max-width:520px;margin:0 auto;background:#f9fafb;padding:24px;">
              <div style="background:linear-gradient(135deg,#16a34a,#22c55e);border-radius:20px;padding:28px;text-align:center;margin-bottom:20px;">
                <div style="font-size:44px;margin-bottom:8px;">P</div>
                <h1 style="color:white;font-size:22px;font-weight:900;margin:0;">Booking Confirmed!</h1>
                <p style="color:rgba(255,255,255,0.85);margin:6px 0 0;font-size:13px;">Your parking slot is reserved</p>
              </div>
              <div style="background:white;border-radius:14px;padding:20px;border:1px solid #e5e7eb;margin-bottom:14px;">
                <p style="color:#374151;font-size:14px;">Hi <b>{current_user.name}</b>,</p>
                <p style="color:#374151;font-size:13px;margin-top:10px;">Your parking booking is confirmed!</p>
                <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:14px;margin:14px 0;">
                  <p style="color:#166534;font-size:13px;margin:3px 0;"><b>Slot:</b> {slot.label}</p>
                  <p style="color:#166534;font-size:13px;margin:3px 0;"><b>Lot:</b> {lot.name}, {lot.city}</p>
                  <p style="color:#166534;font-size:13px;margin:3px 0;"><b>Vehicle:</b> {res.vehicle_number}</p>
                  <p style="color:#166534;font-size:13px;margin:3px 0;"><b>Entry Time:</b> {res.entry_time.strftime("%d %b %Y, %I:%M %p")} IST</p>
                  <p style="color:#166534;font-size:13px;margin:3px 0;"><b>Rate:</b> Rs.{rate}/hour</p>
                  <p style="color:#dc2626;font-size:12px;margin-top:8px;"><b>First 15 minutes are FREE!</b></p>
                </div>
                <a href="{site_url}/digital_pass/{res.id}" style="display:block;background:linear-gradient(135deg,#16a34a,#22c55e);color:white;text-align:center;padding:12px;border-radius:10px;font-weight:800;font-size:14px;text-decoration:none;">
                  View Digital QR Pass
                </a>
              </div>
              <p style="color:#9ca3af;font-size:11px;text-align:center;">SpotEasy India 2026 - Smart Parking Platform</p>
            </div>'''
            send_email(current_user.email, f'Booking Confirmed - Slot {slot.label} | SpotEasy India', booking_html)
            # Also email the vendor
            vendor = lot.owner
            if vendor and vendor.email:
                vendor_html = f'''
                <div style="font-family:Inter,sans-serif;max-width:520px;margin:0 auto;background:#f9fafb;padding:24px;">
                  <div style="background:linear-gradient(135deg,#2563eb,#3b82f6);border-radius:20px;padding:28px;text-align:center;margin-bottom:20px;">
                    <div style="font-size:44px;margin-bottom:8px;">P</div>
                    <h1 style="color:white;font-size:22px;font-weight:900;margin:0;">New Booking!</h1>
                    <p style="color:rgba(255,255,255,0.85);margin:6px 0 0;font-size:13px;">A customer just booked a slot at your lot</p>
                  </div>
                  <div style="background:white;border-radius:14px;padding:20px;border:1px solid #e5e7eb;">
                    <p style="color:#374151;font-size:13px;margin:4px 0;"><b>Customer:</b> {current_user.name}</p>
                    <p style="color:#374151;font-size:13px;margin:4px 0;"><b>Lot:</b> {lot.name}</p>
                    <p style="color:#374151;font-size:13px;margin:4px 0;"><b>Slot:</b> {slot.label}</p>
                    <p style="color:#374151;font-size:13px;margin:4px 0;"><b>Vehicle:</b> {res.vehicle_number}</p>
                    <p style="color:#374151;font-size:13px;margin:4px 0;"><b>Entry:</b> {res.entry_time.strftime("%d %b %Y, %I:%M %p")} IST</p>
                  </div>
                </div>'''
                send_email(vendor.email, f'New Booking at {lot.name} | SpotEasy', vendor_html)
        except Exception as e:
            print(f'[Booking Email] Failed: {e}')
        # Send push notification
        if current_user.fcm_token:
            send_push_notification(
                current_user.fcm_token,
                '🅿️ Booking Confirmed! — SpotEasy',
                f'Slot {slot.label} at {lot.name}. Show QR at gate.',
                {'url': f'/reservation/{res.id}/pass', 'booking_id': str(res.id)}
            )
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
    payment_method  = request.form.get('payment_method', 'cash')
    exit_time       = now_ist()
    res.exit_time   = exit_time
    res.status      = 'completed'
    raw_amount      = calculate_bill(res.entry_time, exit_time, res.vehicle_type,
                                     res.slot.lot.rate_2w, res.slot.lot.rate_4w)
    # Round off to nearest rupee
    res.amount_paid = Decimal(str(round(float(raw_amount))))
    res.payment_method = payment_method
    res.slot.status = 'available'
    db.session.commit()
    flash(f'Checkout done! Amount: ₹{res.amount_paid} ({payment_method})', 'success')
    # Send checkout/bill email to customer
    try:
        site_url = os.environ.get('RENDER_EXTERNAL_URL', 'https://www.spoteasy.in')
        duration_mins = int((exit_time - res.entry_time).total_seconds() / 60)
        hours = duration_mins // 60
        mins  = duration_mins % 60
        duration_str = f"{hours}h {mins}m" if hours > 0 else f"{mins} minutes"
        checkout_html = f'''
        <div style="font-family:Inter,sans-serif;max-width:520px;margin:0 auto;background:#f9fafb;padding:24px;">
          <div style="background:linear-gradient(135deg,#111827,#1a2e1a);border-radius:20px;padding:28px;text-align:center;margin-bottom:20px;">
            <div style="font-size:44px;margin-bottom:8px;">P</div>
            <h1 style="color:white;font-size:22px;font-weight:900;margin:0;">Checkout Complete!</h1>
            <p style="color:rgba(255,255,255,0.85);margin:6px 0 0;font-size:13px;">Thank you for using SpotEasy India</p>
          </div>
          <div style="background:white;border-radius:14px;padding:20px;border:1px solid #e5e7eb;margin-bottom:14px;">
            <p style="color:#374151;font-size:14px;">Hi <b>{current_user.name}</b>,</p>
            <p style="color:#374151;font-size:13px;margin-top:10px;">Your parking session has ended. Here is your bill:</p>
            <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:14px;margin:14px 0;">
              <p style="color:#166534;font-size:13px;margin:3px 0;"><b>Slot:</b> {res.slot.label}</p>
              <p style="color:#166534;font-size:13px;margin:3px 0;"><b>Lot:</b> {res.slot.lot.name}, {res.slot.lot.city}</p>
              <p style="color:#166534;font-size:13px;margin:3px 0;"><b>Vehicle:</b> {res.vehicle_number}</p>
              <p style="color:#166534;font-size:13px;margin:3px 0;"><b>Entry:</b> {res.entry_time.strftime("%d %b %Y, %I:%M %p")} IST</p>
              <p style="color:#166534;font-size:13px;margin:3px 0;"><b>Exit:</b> {exit_time.strftime("%d %b %Y, %I:%M %p")} IST</p>
              <p style="color:#166534;font-size:13px;margin:3px 0;"><b>Duration:</b> {duration_str}</p>
              <p style="color:#166534;font-size:13px;margin:3px 0;"><b>Payment:</b> {payment_method.upper()}</p>
              <div style="border-top:2px solid #16a34a;margin-top:10px;padding-top:10px;">
                <p style="color:#166534;font-size:18px;font-weight:900;margin:0;"><b>Total Paid: Rs.{res.amount_paid}</b></p>
                {"<p style='color:#16a34a;font-size:12px;margin-top:4px;'>Grace period applied - No charge!</p>" if res.amount_paid == 0 else ""}
              </div>
            </div>
            <a href="{site_url}/customer/dashboard" style="display:block;background:#111827;color:white;text-align:center;padding:12px;border-radius:10px;font-weight:800;font-size:14px;text-decoration:none;">
              View Booking History
            </a>
          </div>
          <p style="color:#9ca3af;font-size:11px;text-align:center;">SpotEasy India 2026 - Smart Parking Platform</p>
        </div>'''
        send_email(current_user.email, f'Bill Receipt - Rs.{res.amount_paid} | SpotEasy India', checkout_html)
    except Exception as e:
        print(f'[Checkout Email] Failed: {e}')
    return redirect(url_for('digital_pass', rid=rid))

# ── Admin Delete Routes ───────────────────────────────────────────────────────
@app.route('/admin/delete_user/<int:uid>', methods=['POST'])
@login_required
def admin_delete_user(uid):
    if current_user.role != 'admin': return redirect(url_for('index'))
    user = db.session.get(User, uid)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('admin_dashboard'))
    if user.role == 'admin':
        flash('Cannot delete admin account.', 'danger')
        return redirect(url_for('admin_dashboard'))
    try:
        # Delete user's reservations first
        Reservation.query.filter_by(customer_id=uid).delete()
        # Delete user's lots and slots if vendor
        if user.role == 'vendor':
            lots = ParkingLot.query.filter_by(owner_id=uid).all()
            for lot in lots:
                Reservation.query.filter(
                    Reservation.slot_id.in_([s.id for s in lot.slots])
                ).delete(synchronize_session=False)
                ParkingSlot.query.filter_by(lot_id=lot.id).delete()
            ParkingLot.query.filter_by(owner_id=uid).delete()
        db.session.delete(user)
        db.session.commit()
        flash(f'User {user.name} deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting user: {str(e)}', 'danger')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_lot/<int:lid>', methods=['POST'])
@login_required
def admin_delete_lot(lid):
    if current_user.role != 'admin': return redirect(url_for('index'))
    lot = db.session.get(ParkingLot, lid)
    if not lot:
        flash('Lot not found.', 'danger')
        return redirect(url_for('admin_dashboard'))
    try:
        # Delete reservations linked to slots in this lot
        Reservation.query.filter(
            Reservation.slot_id.in_([s.id for s in lot.slots])
        ).delete(synchronize_session=False)
        # Delete slots
        ParkingSlot.query.filter_by(lot_id=lid).delete()
        # Delete lot
        db.session.delete(lot)
        db.session.commit()
        flash(f'Lot "{lot.name}" deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting lot: {str(e)}', 'danger')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_reservation/<int:rid>', methods=['POST'])
@login_required
def admin_delete_reservation(rid):
    if current_user.role != 'admin': return redirect(url_for('index'))
    res = db.session.get(Reservation, rid)
    if not res:
        flash('Reservation not found.', 'danger')
        return redirect(url_for('admin_dashboard'))
    try:
        # Free the slot if active
        if res.slot and res.status == 'active':
            res.slot.status = 'available'
        db.session.delete(res)
        db.session.commit()
        flash('Reservation deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
    return redirect(url_for('admin_dashboard'))

# ── Live API Routes (for auto-refresh polling) ────────────────────────────────

@app.route('/api/admin/stats')
@login_required
def api_admin_stats():
    """Admin dashboard live stats — polled every 5 seconds."""
    if current_user.role != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    pending_vendors = User.query.filter_by(role='vendor', is_approved=False).count()
    pending_lots    = ParkingLot.query.filter_by(is_active=False).count()
    total_users     = User.query.filter(User.role != 'admin').count()
    total_lots      = ParkingLot.query.count()
    active_bookings = Reservation.query.filter_by(status='active').count()
    total_revenue   = db.session.query(db.func.sum(Reservation.amount_paid)).scalar() or 0
    # Latest pending vendors (for notification badge)
    new_vendors = [{'id': u.id, 'name': u.name, 'email': u.email}
                   for u in User.query.filter_by(role='vendor', is_approved=False)
                   .order_by(User.id.desc()).limit(5).all()]
    new_lots    = [{'id': l.id, 'name': l.name, 'city': l.city}
                   for l in ParkingLot.query.filter_by(is_active=False)
                   .order_by(ParkingLot.id.desc()).limit(5).all()]
    return jsonify({
        'pending_vendors': pending_vendors,
        'pending_lots':    pending_lots,
        'total_users':     total_users,
        'total_lots':      total_lots,
        'active_bookings': active_bookings,
        'total_revenue':   float(total_revenue),
        'new_vendors':     new_vendors,
        'new_lots':        new_lots,
    })

@app.route('/api/vendor/stats/<int:vid>')
@login_required
def api_vendor_stats(vid):
    """Vendor dashboard live stats — polled every 5 seconds."""
    if current_user.role != 'vendor' or current_user.id != vid:
        return jsonify({'error': 'Forbidden'}), 403
    lots = ParkingLot.query.filter_by(owner_id=vid).all()
    total_slots     = sum(lot.total_slots for lot in lots)
    occupied_slots  = sum(lot.occupied_count for lot in lots)
    free_slots      = total_slots - occupied_slots
    active_bookings = Reservation.query.join(ParkingSlot).join(ParkingLot)                      .filter(ParkingLot.owner_id==vid, Reservation.status=='active').count()
    total_revenue   = db.session.query(db.func.sum(Reservation.amount_paid))                      .join(ParkingSlot).join(ParkingLot)                      .filter(ParkingLot.owner_id==vid).scalar() or 0
    return jsonify({
        'total_slots':     total_slots,
        'occupied_slots':  occupied_slots,
        'free_slots':      free_slots,
        'active_bookings': active_bookings,
        'total_revenue':   float(total_revenue),
        'lots':            [{'id': l.id, 'name': l.name,
                             'free': l.available_count,
                             'occupied': l.occupied_count} for l in lots],
    })

# ── Health ─────────────────────────────────────────────────────────────────────
@app.route('/health')
def health():
    try:
        db_type = 'postgresql' if 'postgresql' in app.config['SQLALCHEMY_DATABASE_URI'] else 'sqlite'
        return jsonify({
            'status': 'ok ✅', 'db': f'connected ({db_type})',
            'time_ist': now_ist().strftime('%d %b %Y %I:%M %p IST'),
            'users': User.query.count(), 'lots': ParkingLot.query.count(),
            'reservations': Reservation.query.count(),
        })
    except Exception as e:
        return jsonify({'status': 'error ❌', 'error': str(e)}), 500



# ── Account / Profile ──────────────────────────────────────────────────────────
@app.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'update_profile':
            name  = request.form.get('name', '').strip()
            phone = request.form.get('phone', '').strip()
            if name and len(name) >= 3:
                current_user.name  = name
                current_user.phone = phone
                db.session.commit()
                flash('Profile updated successfully!', 'success')
            else:
                flash('Name must be at least 3 characters.', 'danger')
        elif action == 'change_password':
            old_pw  = request.form.get('old_password', '')
            new_pw  = request.form.get('new_password', '')
            conf_pw = request.form.get('confirm_password', '')
            if not current_user.check_password(old_pw):
                flash('Current password is incorrect.', 'danger')
            elif len(new_pw) < 8:
                flash('New password must be at least 8 characters.', 'danger')
            elif new_pw != conf_pw:
                flash('Passwords do not match.', 'danger')
            else:
                current_user.set_password(new_pw)
                db.session.commit()
                flash('Password changed successfully!', 'success')
        return redirect(url_for('account'))

    if current_user.role == 'customer':
        reservations = Reservation.query.filter_by(customer_id=current_user.id).order_by(Reservation.created_at.desc()).all()
        total_spent  = sum(float(r.amount_paid or 0) for r in reservations if r.status == 'completed')
        stats = {
            'total_bookings': len(reservations),
            'active':   sum(1 for r in reservations if r.status == 'active'),
            'completed': sum(1 for r in reservations if r.status == 'completed'),
            'total_spent': round(total_spent, 2),
            'recent': reservations[:5],
        }
    elif current_user.role == 'vendor':
        lots  = ParkingLot.query.filter_by(owner_id=current_user.id).all()
        stats = {
            'total_lots': len(lots),
            'total_slots': sum(l.total_slots for l in lots),
            'active_lots': sum(1 for l in lots if l.is_active),
        }
    else:
        stats = {}
    return render_template('account.html', stats=stats)


# ── Admin Notify ───────────────────────────────────────────────────────────────
@app.route('/admin/notify', methods=['GET', 'POST'])
@login_required
def admin_notify():
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    if request.method == 'POST':
        title   = request.form.get('title', '').strip()
        body    = request.form.get('body', '').strip()
        user_id = request.form.get('user_id', 'all')
        sent = 0
        if user_id == 'all':
            users = User.query.filter(User.fcm_token.isnot(None)).all()
        else:
            users = User.query.filter_by(id=int(user_id)).all()
        for u in users:
            if u.fcm_token:
                ok = send_push_notification(u.fcm_token, title, body)
                if ok: sent += 1
        flash(f'Notification sent to {sent} users.', 'success')
        return redirect(url_for('admin_notify'))
    users     = User.query.filter(User.fcm_token.isnot(None)).all()
    all_users = User.query.all()
    return render_template('admin_notify.html', users=users, all_users=all_users)


# ── Save FCM Token ─────────────────────────────────────────────────────────────
@app.route('/save_fcm_token', methods=['POST'])
@login_required
def save_fcm_token():
    try:
        token = request.json.get('token', '').strip()
        if token:
            current_user.fcm_token = token
            db.session.commit()
            return jsonify({'status': 'saved'})
        return jsonify({'status': 'no token'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'msg': str(e)}), 500


# ── Customer Stats API ─────────────────────────────────────────────────────────
@app.route('/api/customer/stats')
@login_required
def api_customer_stats():
    if current_user.role != 'customer':
        return jsonify({}), 403
    reservations = Reservation.query.filter_by(customer_id=current_user.id).all()
    total_spent  = sum(float(r.amount_paid or 0) for r in reservations if r.status == 'completed')
    return jsonify({
        'total_bookings': len(reservations),
        'active':   sum(1 for r in reservations if r.status == 'active'),
        'completed': sum(1 for r in reservations if r.status == 'completed'),
        'total_spent': int(round(total_spent)),
    })


# ── CSV Export ─────────────────────────────────────────────────────────────────
import csv, io as _io
from flask import make_response

@app.route('/admin/export/<string:table>')
@login_required
def export_csv(table):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    output = _io.StringIO()
    writer = csv.writer(output)
    if table == 'users':
        writer.writerow(['ID','Name','Email','Role','Phone','Approved','Created'])
        for u in User.query.all():
            writer.writerow([u.id, u.name, u.email, u.role, u.phone or '', u.is_approved, u.created_at])
    elif table == 'lots':
        writer.writerow(['ID','Name','City','Address','Total Slots','Rate 2W','Rate 4W','Active','Owner'])
        for l in ParkingLot.query.all():
            writer.writerow([l.id, l.name, l.city, l.address, l.total_slots, l.rate_2w, l.rate_4w, l.is_active, l.owner.email])
    elif table == 'reservations':
        writer.writerow(['ID','Customer','Vehicle No','Type','Lot','Slot','Entry','Exit','Amount','Status','Payment'])
        for r in Reservation.query.order_by(Reservation.created_at.desc()).all():
            writer.writerow([r.id, r.customer.name, r.vehicle_no, r.vehicle_type,
                             r.slot.lot.name, r.slot.label, r.entry_time,
                             r.exit_time or '', r.amount_paid or 0, r.status,
                             r.payment_method or 'cash'])
    else:
        return "Unknown table", 404
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename=spoteasy_{table}.csv'
    return response

# ── Favicon ───────────────────────────────────────────────────────────────────
@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static/icons', 'icon-96.png',
                               mimetype='image/png')

# ── Loading / Splash Page ─────────────────────────────────────────────────────
@app.route('/loading')
def loading():
    return send_from_directory('static', 'loading.html')

# ── Terms of Use ──────────────────────────────────────────────────────────────
@app.route('/terms')
def terms():
    return render_template('terms.html')

# ── PWA Routes ────────────────────────────────────────────────────────────────
@app.route('/sw.js')
def service_worker():
    resp = make_response(send_from_directory('static', 'sw.js'))
    resp.headers['Content-Type'] = 'application/javascript'
    resp.headers['Cache-Control'] = 'no-cache'
    return resp

@app.route('/offline')
def offline():
    return render_template('offline.html')


@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    db.session.rollback()
    try:
        return render_template('500.html'), 500
    except Exception:
        return "<h1>500 - Server Error</h1><a href='/'>Go Home</a>", 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
