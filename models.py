from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import uuid

db = SQLAlchemy()

class Club(db.Model):
    __tablename__ = 'clubs'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    club_name = db.Column(db.String(100), nullable=False)
    owner_name = db.Column(db.String(100), nullable=False)
    
    # Subscription
    is_active = db.Column(db.Boolean, default=True)
    trial_end = db.Column(db.DateTime, default=lambda: datetime.utcnow() + timedelta(days=14))
    stripe_customer_id = db.Column(db.String(100), nullable=True)
    stripe_subscription_id = db.Column(db.String(100), nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    courts = db.relationship('Court', backref='club', lazy=True)

    def trial_days_left(self):
        if self.trial_end is None:
            return 0
        delta = self.trial_end - datetime.utcnow()
        return max(0, delta.days)

    def is_in_trial(self):
        return datetime.utcnow() < self.trial_end

    def can_access(self):
        return self.is_active and (self.is_in_trial() or self.stripe_subscription_id is not None)

    def __repr__(self):
        return f'<Club {self.club_name}>'


class Court(db.Model):
    __tablename__ = 'courts'

    id = db.Column(db.Integer, primary_key=True)
    club_id = db.Column(db.Integer, db.ForeignKey('clubs.id'), nullable=False)
    court_name = db.Column(db.String(50), nullable=False)
    access_token = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Court {self.court_name}>'
