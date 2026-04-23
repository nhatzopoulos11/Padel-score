from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class Club(db.Model):
    __tablename__ = 'clubs'
    
    id = db.Column(db.Integer, primary_key=True)
    club_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)  # False = payment failed
    is_trial = db.Column(db.Boolean, default=True)   # True = free trial
    trial_ends = db.Column(db.DateTime, nullable=True)
    
    # Relationship to courts
    courts = db.relationship('Court', backref='club', lazy=True)
    
    def __repr__(self):
        return f'<Club {self.club_name}>'


class Court(db.Model):
    __tablename__ = 'courts'
    
    id = db.Column(db.Integer, primary_key=True)
    club_id = db.Column(db.Integer, db.ForeignKey('clubs.id'), nullable=False)
    court_name = db.Column(db.String(50), nullable=False)  # e.g. "Court 1"
    qr_code = db.Column(db.String(200), nullable=True)     # path to QR image
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Court {self.court_name}>'
