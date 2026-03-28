from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import secrets

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id           = db.Column(db.Integer, primary_key=True)
    name         = db.Column(db.String(100), nullable=False)
    email        = db.Column(db.String(150), unique=True, nullable=False)
    password_hash= db.Column(db.String(256), nullable=False)
    role         = db.Column(db.String(20), nullable=False, default='customer')
    phone        = db.Column(db.String(15))
    is_approved  = db.Column(db.Boolean, default=True)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    fcm_token    = db.Column(db.String(512))  # Firebase push token

    lots         = db.relationship('ParkingLot', backref='owner', lazy=True, cascade='all, delete-orphan')
    reservations = db.relationship('Reservation', backref='customer', lazy=True, cascade='all, delete-orphan')

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

    def to_dict(self):
        return {'id': self.id, 'name': self.name, 'email': self.email, 'role': self.role}


class ParkingLot(db.Model):
    __tablename__ = 'parking_lots'
    id          = db.Column(db.Integer, primary_key=True)
    owner_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name        = db.Column(db.String(150), nullable=False)
    address     = db.Column(db.String(300), nullable=False)
    city        = db.Column(db.String(100), nullable=False)
    latitude    = db.Column(db.Float, nullable=False)
    longitude   = db.Column(db.Float, nullable=False)
    total_slots = db.Column(db.Integer, nullable=False)
    rate_2w     = db.Column(db.Numeric(8,2), nullable=False)
    rate_4w     = db.Column(db.Numeric(8,2), nullable=False)
    is_active   = db.Column(db.Boolean, default=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    slots = db.relationship('ParkingSlot', backref='lot', lazy=True, cascade='all, delete-orphan')

    @property
    def available_count(self):
        return sum(1 for s in self.slots if s.status == 'available')

    @property
    def occupied_count(self):
        return sum(1 for s in self.slots if s.status == 'occupied')

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'address': self.address,
            'city': self.city, 'lat': self.latitude, 'lng': self.longitude,
            'total': self.total_slots, 'available': self.available_count,
            'occupied': self.occupied_count,
            'rate_2w': float(self.rate_2w), 'rate_4w': float(self.rate_4w),
        }


class ParkingSlot(db.Model):
    __tablename__ = 'parking_slots'
    id        = db.Column(db.Integer, primary_key=True)
    lot_id    = db.Column(db.Integer, db.ForeignKey('parking_lots.id'), nullable=False)
    label     = db.Column(db.String(10), nullable=False)
    status    = db.Column(db.String(20), nullable=False, default='available')
    slot_type = db.Column(db.String(5), default='4w')

    reservations = db.relationship('Reservation', backref='slot', lazy=True)

    def to_dict(self):
        return {'id': self.id, 'label': self.label, 'status': self.status, 'type': self.slot_type}


class Reservation(db.Model):
    __tablename__ = 'reservations'
    id           = db.Column(db.Integer, primary_key=True)
    customer_id  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    slot_id      = db.Column(db.Integer, db.ForeignKey('parking_slots.id'), nullable=False)
    vehicle_no   = db.Column(db.String(20), nullable=False)
    vehicle_type = db.Column(db.String(5), nullable=False)
    entry_time   = db.Column(db.DateTime, default=datetime.utcnow)
    exit_time    = db.Column(db.DateTime)
    amount_paid  = db.Column(db.Numeric(10,2), default=0)
    status       = db.Column(db.String(20), default='active')
    qr_token      = db.Column(db.String(64), unique=True, default=lambda: secrets.token_hex(32))
    payment_method = db.Column(db.String(20), default='cash')  # cash / upi / card
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    fcm_token    = db.Column(db.String(512))  # Firebase push token
