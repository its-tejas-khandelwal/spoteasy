import os, base64, io, threading, time, csv
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory, make_response
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask_login import LoginManager, login_user, logout_user, login_required, current_user

def _keep_alive():
    time.sleep(60)
    app_url = os.environ.get('RENDER_EXTERNAL_URL', '')
    if not app_url:
        return
    import requests as _req
    while True:
        try:
            r = _req.get(f"{app_url}/health", timeout=10)
            print(f"[KeepAlive] {r.status_code}")
        except Exception as e:
            print(f"[KeepAlive] Failed: {e}")
        time.sleep(13 * 60)

_ping_thread = threading.Thread(target=_keep_alive, daemon=True)
_ping_thread.start()

from dotenv import load_dotenv
from models import db, User, ParkingLot, ParkingSlot, Reservation

load_dotenv()

IST = timezone(timedelta(hours=5, minutes=30))

def now_ist():
    return datetime.now(IST).replace(tzinfo=None)

def to_ist(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST).replace(tzinfo=None)

def get_db_url():
    url = os.environ.get('DATABASE_URL', '').strip()
    if not url:
        return 'sqlite:///parksmart.db'
    if url.startswith('postgres://'):
        url = 'postgresql://' + url[len('postgres://'):]
    if 'sslmode' not in url:
        sep = '&' if '?' in url else '?'
        url = url + sep + 'sslmode=require'
    return url

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = get_db_url()
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['VENDOR_UPI_ID'] = os.environ.get('VENDOR_UPI_ID', 'spoteasy@upi')
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_recycle': 280, 'pool_pre_ping': True}

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to continue.'

@login_manager.user_loader
def load_user(uid):
    try:
        return db.session.get(User, int(uid))
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
        print("[DB] Ready")
    except Exception as e:
        print(f"[DB] WARNING: {e}")

def _safe_decimal(val, default=0):
    try:
        return Decimal(str(val).replace(',', '').strip())
    except Exception:
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
    except Exception:
        try:
            import qrcode as qr2
            img2 = qr2.make(token)
            buf2 = io.BytesIO()
            img2.save(buf2, format='PNG')
            buf2.seek(0)
            return base64.b64encode(buf2.read()).decode()
        except Exception as e2:
            print(f"[QR] Failed: {e2}")
            return ''

def build_whatsapp_url(res):
    lot = res.slot.lot
    ist_time = to_ist(res.entry_time)
    rate = f"Rs.{lot.rate_2w}/hr" if res.vehicle_type == '2w' else f"Rs.{lot.rate_4w}/hr"
    msg = (f"SpotEasy Booking Confirmed!%0ALot: {lot.name}%0ASlot: {res.slot.label}"
           f"%0AVehicle: {res.vehicle_no}%0AEntry: {ist_time.strftime('%d %b %Y, %I:%M %p')} IST"
           f"%0ARate: {rate}%0AFREE if exit within 15 mins!")
    return f"https://wa.me/?text={msg}"

def redirect_by_role():
    if current_user.role == 'admin':  return redirect(url_for('admin_dashboard'))
    if current_user.role == 'vendor': return redirect(url_for('vendor_dashboard'))
    return redirect(url_for('customer_dashboard'))

@app.context_processor
def inject_helpers():
    return {'to_ist': to_ist, 'now_ist': now_ist()}

def send_email(to_email, subject, html_body):
    try:
        smtp_user = os.environ.get('EMAIL_FROM', '')
        smtp_pass = os.environ.get('EMAIL_KEY', '')
        if not smtp_user or not smtp_pass:
            print(f"[Email] No credentials - skipping")
            return False
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From']    = f"SpotEasy India <{smtp_user}>"
        msg['To']      = to_email
        msg.attach(MIMEText(html_body, 'html'))
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, to_email, msg.as_string())
        print(f"[Email] Sent to {to_email}")
        return True
    except Exception as e:
        print(f"[Email] Failed: {e}")
        return False

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
        user = User(name=name, email=email, role=role, phone=phone, is_approved=(role == 'customer'))
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

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if current_user.role != 'admin': return redirect(url_for('index'))
    vendors      = User.query.filter_by(role='vendor').all()
    customers    = User.query.filter_by(role='customer').all()
    lots         = ParkingLot.query.all()
    reservations = Reservation.query.order_by(Reservation.created_at.desc()).limit(20).all()
    return render_template('dashboard_admin.html', vendors=vendors, customers=customers,
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
        site_url = os.environ.get('RENDER_EXTERNAL_URL', 'https://www.spoteasy.in')
        html = f'<div style="font-family:Inter,sans-serif;padding:24px;"><div style="background:#16a34a;border-radius:16px;padding:24px;text-align:center;"><h1 style="color:white;">You are Approved!</h1></div><div style="background:white;padding:20px;border-radius:12px;margin-top:16px;"><p>Hi <b>{user.name}</b>, your SpotEasy vendor account is now active!</p><a href="{site_url}/login" style="display:block;background:#16a34a;color:white;text-align:center;padding:12px;border-radius:10px;margin-top:16px;text-decoration:none;font-weight:800;">Login to SpotEasy</a></div></div>'
        send_email(user.email, 'Your SpotEasy Vendor Account is Approved!', html)
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
        Reservation.query.filter_by(customer_id=uid).delete()
        if user.role == 'vendor':
            lots = ParkingLot.query.filter_by(owner_id=uid).all()
            for lot in lots:
                Reservation.query.filter(Reservation.slot_id.in_([s.id for s in lot.slots])).delete(synchronize_session=False)
                ParkingSlot.query.filter_by(lot_id=lot.id).delete()
            ParkingLot.query.filter_by(owner_id=uid).delete()
        db.session.delete(user)
        db.session.commit()
        flash(f'User {user.name} deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
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
        Reservation.query.filter(Reservation.slot_id.in_([s.id for s in lot.slots])).delete(synchronize_session=False)
        ParkingSlot.query.filter_by(lot_id=lid).delete()
        db.session.delete(lot)
        db.session.commit()
        flash(f'Lot "{lot.name}" deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
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
        if res.slot and res.status == 'active':
            res.slot.status = 'available'
        db.session.delete(res)
        db.session.commit()
        flash('Reservation deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/db')
@login_required
def admin_db_view():
    if current_user.role != 'admin': return redirect(url_for('index'))
    users        = User.query.all()
    lots         = ParkingLot.query.all()
    reservations = Reservation.query.order_by(Reservation.created_at.desc()).all()
    return render_template('db_view.html', users=users, lots=lots, reservations=reservations)

@app.route('/admin/notify', methods=['GET', 'POST'])
@login_required
def admin_notify():
    if current_user.role != 'admin': return redirect(url_for('index'))
    if request.method == 'POST':
        title  = request.form.get('title', '').strip()
        body   = request.form.get('body', '').strip()
        target = request.form.get('user_id', 'all')
        users  = User.query.all() if target == 'all' else User.query.filter_by(id=int(target)).all()
        sent = 0
        for u in users:
            if u.email:
                html = f'<div style="font-family:Inter,sans-serif;padding:24px;"><h2 style="color:#16a34a;">{title}</h2><p>{body}</p><p style="color:#9ca3af;font-size:11px;">SpotEasy India 2026</p></div>'
                if send_email(u.email, f'SpotEasy: {title}', html):
                    sent += 1
        flash(f'Notification sent to {sent} users.', 'success')
        return redirect(url_for('admin_notify'))
    all_users = User.query.all()
    return render_template('admin_notify.html', users=all_users, all_users=all_users)

@app.route('/api/admin/stats')
@login_required
def api_admin_stats():
    if current_user.role != 'admin': return jsonify({'error': 'Forbidden'}), 403
    pending_vendors = User.query.filter_by(role='vendor', is_approved=False).count()
    pending_lots    = ParkingLot.query.filter_by(is_active=False).count()
    total_users     = User.query.filter(User.role != 'admin').count()
    total_lots      = ParkingLot.query.count()
    active_bookings = Reservation.query.filter_by(status='active').count()
    total_revenue   = db.session.query(db.func.sum(Reservation.amount_paid)).scalar() or 0
    new_vendors = [{'id': u.id, 'name': u.name, 'email': u.email} for u in
                   User.query.filter_by(role='vendor', is_approved=False).order_by(User.id.desc()).limit(5).all()]
    new_lots = [{'id': l.id, 'name': l.name, 'city': l.city} for l in
                ParkingLot.query.filter_by(is_active=False).order_by(ParkingLot.id.desc()).limit(5).all()]
    return jsonify({'pending_vendors': pending_vendors, 'pending_lots': pending_lots,
                    'total_users': total_users, 'total_lots': total_lots,
                    'active_bookings': active_bookings, 'total_revenue': float(total_revenue),
                    'new_vendors': new_vendors, 'new_lots': new_lots})

@app.route('/api/vendor/stats/<int:vid>')
@login_required
def api_vendor_stats(vid):
    if current_user.role != 'vendor' or current_user.id != vid:
        return jsonify({'error': 'Forbidden'}), 403
    lots = ParkingLot.query.filter_by(owner_id=vid).all()
    total_slots    = sum(lot.total_slots for lot in lots)
    occupied_slots = sum(lot.occupied_count for lot in lots)
    active_bookings = Reservation.query.join(ParkingSlot).join(ParkingLot)\
                      .filter(ParkingLot.owner_id==vid, Reservation.status=='active').count()
    total_revenue = db.session.query(db.func.sum(Reservation.amount_paid))\
                    .join(ParkingSlot).join(ParkingLot).filter(ParkingLot.owner_id==vid).scalar() or 0
    return jsonify({'total_slots': total_slots, 'occupied_slots': occupied_slots,
                    'free_slots': total_slots - occupied_slots, 'active_bookings': active_bookings,
                    'total_revenue': float(total_revenue),
                    'lots': [{'id': l.id, 'name': l.name, 'free': l.available_count, 'occupied': l.occupied_count} for l in lots]})

@app.route('/api/customer/stats')
@login_required
def api_customer_stats():
    if current_user.role != 'customer': return jsonify({}), 403
    reservations = Reservation.query.filter_by(customer_id=current_user.id).all()
    total_spent  = sum(float(r.amount_paid or 0) for r in reservations if r.status == 'completed')
    return jsonify({'total_bookings': len(reservations),
                    'active': sum(1 for r in reservations if r.status == 'active'),
                    'completed': sum(1 for r in reservations if r.status == 'completed'),
                    'total_spent': int(round(total_spent))})

@app.route('/api/lot/<int:lid>/slots')
@login_required
def api_lot_slots(lid):
    lot = db.session.get(ParkingLot, lid)
    if not lot: return jsonify({'error': 'Not found'}), 404
    return jsonify({'slots': [s.to_dict() for s in lot.slots], 'available': lot.available_count,
                    'occupied': lot.occupied_count, 'total': lot.total_slots,
                    'avail_2w': sum(1 for s in lot.slots if s.slot_type=='2w' and s.status=='available'),
                    'avail_4w': sum(1 for s in lot.slots if s.slot_type=='4w' and s.status=='available')})

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
            name     = request.form.get('name', '').strip()
            address  = request.form.get('address', '').strip()
            city     = request.form.get('city', '').strip()
            lat_str  = request.form.get('latitude', '').strip()
            lng_str  = request.form.get('longitude', '').strip()
            slots_2w = request.form.get('slots_2w', '0').strip()
            slots_4w = request.form.get('slots_4w', '0').strip()
            r2w      = request.form.get('rate_2w', '').strip()
            r4w      = request.form.get('rate_4w', '').strip()
            if not all([name, address, city, lat_str, lng_str, r2w, r4w]):
                flash('All fields are required.', 'danger')
                return render_template('add_lot.html')
            lat   = float(lat_str); lng = float(lng_str)
            n_2w  = int(slots_2w) if slots_2w else 0
            n_4w  = int(slots_4w) if slots_4w else 0
            total = n_2w + n_4w
            if total < 1:
                flash('Total slots must be at least 1.', 'danger')
                return render_template('add_lot.html')
            rate_2w = _safe_decimal(r2w); rate_4w = _safe_decimal(r4w)
            if rate_2w <= 0 or rate_4w <= 0:
                flash('Rates must be greater than zero.', 'danger')
                return render_template('add_lot.html')
            lot = ParkingLot(owner_id=current_user.id, name=name, address=address, city=city,
                             latitude=lat, longitude=lng, total_slots=total,
                             rate_2w=rate_2w, rate_4w=rate_4w, is_active=False)
            db.session.add(lot); db.session.flush()
            for i in range(1, n_2w + 1):
                db.session.add(ParkingSlot(lot_id=lot.id, label=f'2W-{i:03d}', status='available', slot_type='2w'))
            for i in range(1, n_4w + 1):
                db.session.add(ParkingSlot(lot_id=lot.id, label=f'4W-{i:03d}', status='available', slot_type='4w'))
            db.session.commit()
            flash(f'Lot "{name}" added! Awaiting admin approval.', 'success')
            return redirect(url_for('vendor_dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'danger')
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
    if current_user.role not in ('vendor', 'admin'): return jsonify({'error': 'Forbidden'}), 403
    slot = db.session.get(ParkingSlot, sid)
    if not slot: return jsonify({'error': 'Not found'}), 404
    slot.status = 'occupied' if slot.status == 'available' else 'available'
    db.session.commit()
    return jsonify({'id': slot.id, 'status': slot.status})

@app.route('/customer/dashboard')
@login_required
def customer_dashboard():
    if current_user.role != 'customer': return redirect(url_for('index'))
    reservations = Reservation.query.filter_by(customer_id=current_user.id).order_by(Reservation.created_at.desc()).all()
    return render_template('dashboard_customer.html', reservations=reservations)

@app.route('/lots')
def lots_list():
    lots = ParkingLot.query.filter_by(is_active=True).all()
    return render_template('lots_list.html', lots=lots, lots_json=[l.to_dict() for l in lots])

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
            flash('Slot no longer available.', 'warning')
            return redirect(url_for('book_slot', lid=lid))
        slot.status = 'occupied'
        res = Reservation(customer_id=current_user.id, slot_id=slot.id,
                          vehicle_no=vehicle_no, vehicle_type=vehicle_type, entry_time=now_ist())
        db.session.add(res); db.session.commit()
        flash('Booking confirmed!', 'success')
        try:
            site_url = os.environ.get('RENDER_EXTERNAL_URL', 'https://www.spoteasy.in')
            rate = lot.rate_2w if slot.slot_type == '2w' else lot.rate_4w
            html = f'<div style="font-family:Inter,sans-serif;padding:24px;"><div style="background:#16a34a;border-radius:16px;padding:20px;text-align:center;"><h1 style="color:white;margin:0;">Booking Confirmed!</h1></div><div style="background:white;padding:20px;border-radius:12px;margin-top:12px;border:1px solid #e5e7eb;"><p>Hi <b>{current_user.name}</b>,</p><p><b>Slot:</b> {slot.label}</p><p><b>Lot:</b> {lot.name}, {lot.city}</p><p><b>Vehicle:</b> {res.vehicle_no}</p><p><b>Entry:</b> {res.entry_time.strftime("%d %b %Y, %I:%M %p")} IST</p><p><b>Rate:</b> Rs.{rate}/hr</p><p style="color:#dc2626;"><b>First 15 minutes FREE!</b></p><a href="{site_url}/reservation/{res.id}/pass" style="display:block;background:#16a34a;color:white;text-align:center;padding:12px;border-radius:10px;margin-top:12px;text-decoration:none;font-weight:800;">View QR Pass</a></div></div>'
            send_email(current_user.email, f'Booking Confirmed - {slot.label} | SpotEasy', html)
            vendor = lot.owner
            if vendor and vendor.email:
                vhtml = f'<div style="font-family:Inter,sans-serif;padding:24px;"><div style="background:#2563eb;border-radius:16px;padding:20px;text-align:center;"><h1 style="color:white;margin:0;">New Booking!</h1></div><div style="background:white;padding:20px;border-radius:12px;margin-top:12px;border:1px solid #e5e7eb;"><p><b>Customer:</b> {current_user.name}</p><p><b>Lot:</b> {lot.name}</p><p><b>Slot:</b> {slot.label}</p><p><b>Vehicle:</b> {res.vehicle_no}</p><p><b>Entry:</b> {res.entry_time.strftime("%d %b %Y, %I:%M %p")} IST</p></div></div>'
                send_email(vendor.email, f'New Booking at {lot.name} | SpotEasy', vhtml)
        except Exception as e:
            print(f'[Email] Failed: {e}')
        return redirect(url_for('digital_pass', rid=res.id))
    return render_template('book_slot.html', lot=lot, slots=available_slots)

@app.route('/reservation/<int:rid>/pass')
@login_required
def digital_pass(rid):
    res = db.session.get(Reservation, rid)
    if not res or res.customer_id != current_user.id:
        flash('Pass not found.', 'danger')
        return redirect(url_for('customer_dashboard'))
    return render_template('digital_pass.html', res=res,
                           qr_b64=generate_qr_base64(res.qr_token),
                           wa_url=build_whatsapp_url(res))

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
    payment_method = request.form.get('payment_method', 'cash')
    exit_time      = now_ist()
    res.exit_time  = exit_time
    res.status     = 'completed'
    raw_amount     = calculate_bill(res.entry_time, exit_time, res.vehicle_type,
                                    res.slot.lot.rate_2w, res.slot.lot.rate_4w)
    res.amount_paid    = Decimal(str(round(float(raw_amount))))
    res.payment_method = payment_method
    res.slot.status    = 'available'
    db.session.commit()
    flash(f'Checkout done! Amount: Rs.{res.amount_paid} ({payment_method})', 'success')
    try:
        site_url = os.environ.get('RENDER_EXTERNAL_URL', 'https://www.spoteasy.in')
        mins = int((exit_time - res.entry_time).total_seconds() / 60)
        dur  = f"{mins//60}h {mins%60}m" if mins >= 60 else f"{mins} minutes"
        html = f'<div style="font-family:Inter,sans-serif;padding:24px;"><div style="background:#111827;border-radius:16px;padding:20px;text-align:center;"><h1 style="color:white;margin:0;">Checkout Complete!</h1></div><div style="background:white;padding:20px;border-radius:12px;margin-top:12px;border:1px solid #e5e7eb;"><p>Hi <b>{current_user.name}</b>,</p><p><b>Slot:</b> {res.slot.label}</p><p><b>Lot:</b> {res.slot.lot.name}</p><p><b>Vehicle:</b> {res.vehicle_no}</p><p><b>Duration:</b> {dur}</p><p><b>Payment:</b> {payment_method.upper()}</p><p style="font-size:18px;font-weight:900;color:#16a34a;"><b>Total: Rs.{res.amount_paid}</b></p><a href="{site_url}/customer/dashboard" style="display:block;background:#111827;color:white;text-align:center;padding:12px;border-radius:10px;margin-top:12px;text-decoration:none;font-weight:800;">View History</a></div></div>'
        send_email(current_user.email, f'Bill Receipt - Rs.{res.amount_paid} | SpotEasy', html)
    except Exception as e:
        print(f'[Checkout Email] Failed: {e}')
    return redirect(url_for('digital_pass', rid=rid))

@app.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'update_profile':
            name = request.form.get('name', '').strip()
            if name and len(name) >= 3:
                current_user.name  = name
                current_user.phone = request.form.get('phone', '').strip()
                db.session.commit()
                flash('Profile updated!', 'success')
            else:
                flash('Name must be at least 3 characters.', 'danger')
        elif action == 'change_password':
            old_pw = request.form.get('old_password', '')
            new_pw = request.form.get('new_password', '')
            if not current_user.check_password(old_pw):
                flash('Current password is incorrect.', 'danger')
            elif len(new_pw) < 8:
                flash('New password must be at least 8 characters.', 'danger')
            elif new_pw != request.form.get('confirm_password', ''):
                flash('Passwords do not match.', 'danger')
            else:
                current_user.set_password(new_pw)
                db.session.commit()
                flash('Password changed!', 'success')
        return redirect(url_for('account'))
    if current_user.role == 'customer':
        reservations = Reservation.query.filter_by(customer_id=current_user.id).order_by(Reservation.created_at.desc()).all()
        total_spent  = sum(float(r.amount_paid or 0) for r in reservations if r.status == 'completed')
        stats = {'total_bookings': len(reservations),
                 'active': sum(1 for r in reservations if r.status == 'active'),
                 'completed': sum(1 for r in reservations if r.status == 'completed'),
                 'total_spent': round(total_spent, 2), 'recent': reservations[:5]}
    elif current_user.role == 'vendor':
        lots  = ParkingLot.query.filter_by(owner_id=current_user.id).all()
        stats = {'total_lots': len(lots), 'total_slots': sum(l.total_slots for l in lots),
                 'active_lots': sum(1 for l in lots if l.is_active)}
    else:
        stats = {}
    return render_template('account.html', stats=stats)

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

@app.route('/admin/export/<string:table>')
@login_required
def export_csv(table):
    if current_user.role != 'admin': return redirect(url_for('index'))
    output = io.StringIO()
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
                             r.exit_time or '', r.amount_paid or 0, r.status, r.payment_method or 'cash'])
    else:
        return "Unknown table", 404
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename=spoteasy_{table}.csv'
    return response

@app.route('/health')
def health():
    try:
        db_type = 'postgresql' if 'postgresql' in app.config['SQLALCHEMY_DATABASE_URI'] else 'sqlite'
        return jsonify({'status': 'ok', 'db': f'connected ({db_type})',
                        'time_ist': now_ist().strftime('%d %b %Y %I:%M %p IST'),
                        'users': User.query.count(), 'lots': ParkingLot.query.count(),
                        'reservations': Reservation.query.count()})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static/icons', 'icon-96.png', mimetype='image/png')

@app.route('/loading')
def loading():
    return send_from_directory('static', 'loading.html')

@app.route('/terms')
def terms():
    return render_template('terms.html')

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
