import os
import io
import secrets
import qrcode
from datetime import datetime, timedelta
from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, jsonify, send_file)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import stripe

# ══════════════════════════════════════════
# APP CONFIG
# ══════════════════════════════════════════
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-me')

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', 'sqlite:///padel.db'
).replace('postgres://', 'postgresql://')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

stripe.api_key = os.environ.get('STRIPE_SECRET_KEY', '')
STRIPE_PRICE_ID       = os.environ.get('STRIPE_PRICE_ID', '')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')

PRICE_PER_COURT_EUR = 29
TRIAL_DAYS          = 14

# ══════════════════════════════════════════
# MODELS
# ══════════════════════════════════════════
class User(db.Model):
    __tablename__ = 'users'
    id                  = db.Column(db.Integer, primary_key=True)
    email               = db.Column(db.String(255), unique=True, nullable=False)
    password_hash       = db.Column(db.String(512), nullable=False)
    club_name           = db.Column(db.String(255), default='')
    stripe_customer_id  = db.Column(db.String(255), default='')
    stripe_sub_id       = db.Column(db.String(255), default='')
    sub_status          = db.Column(db.String(50),  default='trialing')
    trial_end           = db.Column(db.DateTime,    default=lambda: datetime.utcnow() + timedelta(days=TRIAL_DAYS))
    created_at          = db.Column(db.DateTime,    default=datetime.utcnow)
    courts              = db.relationship('Court', backref='owner', lazy=True)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

    @property
    def is_active_subscriber(self):
        if self.sub_status == 'active':
            return True
        if self.sub_status == 'trialing' and self.trial_end and datetime.utcnow() < self.trial_end:
            return True
        return False

    @property
    def trial_days_left(self):
        if self.sub_status == 'trialing' and self.trial_end:
            delta = self.trial_end - datetime.utcnow()
            return max(0, delta.days)
        return 0


class Court(db.Model):
    __tablename__ = 'courts'
    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    court_name   = db.Column(db.String(255), nullable=False)
    access_token = db.Column(db.String(64),  unique=True, nullable=False,
                             default=lambda: secrets.token_urlsafe(24))
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    court_state  = db.Column(db.JSON,     default=dict)


# ══════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════
def current_user():
    uid = session.get('user_id')
    return User.query.get(uid) if uid else None


def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user():
            flash('Please log in.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def subscription_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        user = current_user()
        if not user:
            return redirect(url_for('login'))
        if not user.is_active_subscriber:
            flash('Your trial has ended. Please subscribe to continue.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated


# ══════════════════════════════════════════
# AUTH ROUTES
# ══════════════════════════════════════════
@app.route('/')
def index():
    user = current_user()
    if user:
        return redirect(url_for('dashboard'))
    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email     = request.form.get('email', '').strip().lower()
        password  = request.form.get('password', '')
        club_name = request.form.get('club_name', '').strip()

        if not email or not password:
            flash('Email and password are required.', 'danger')
            return redirect(url_for('register'))

        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return redirect(url_for('register'))

        user = User(email=email, club_name=club_name)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        session['user_id'] = user.id
        flash(f'Welcome! You have {TRIAL_DAYS} days free trial.', 'success')
        return redirect(url_for('dashboard'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user     = User.query.filter_by(email=email).first()

        if not user or not user.check_password(password):
            flash('Invalid email or password.', 'danger')
            return redirect(url_for('login'))

        session['user_id'] = user.id
        return redirect(url_for('dashboard'))

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ══════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════
@app.route('/dashboard')
@login_required
def dashboard():
    user   = current_user()
    courts = Court.query.filter_by(user_id=user.id).order_by(Court.created_at).all()
    monthly_cost = len(courts) * PRICE_PER_COURT_EUR
    return render_template('dashboard.html',
                           user=user,
                           courts=courts,
                           monthly_cost=monthly_cost,
                           trial_days=user.trial_days_left)


@app.route('/court/add', methods=['POST'])
@login_required
def add_court():
    user       = current_user()
    court_name = request.form.get('court_name', '').strip()

    if not court_name:
        flash('Court name cannot be empty.', 'danger')
        return redirect(url_for('dashboard'))

    court = Court(user_id=user.id, court_name=court_name, court_state={})
    db.session.add(court)
    db.session.commit()
    flash(f'Court "{court_name}" added!', 'success')
    return redirect(url_for('dashboard'))


@app.route('/court/delete/<int:court_id>', methods=['POST'])
@login_required
def delete_court(court_id):
    user  = current_user()
    court = Court.query.filter_by(id=court_id, user_id=user.id).first_or_404()
    db.session.delete(court)
    db.session.commit()
    flash('Court deleted.', 'success')
    return redirect(url_for('dashboard'))


# ══════════════════════════════════════════
# SCORING ROUTES
# ══════════════════════════════════════════
@app.route('/court/<token>/play')
def play(token):
    """Operator scoring screen — full interactive UI."""
    court = Court.query.filter_by(access_token=token).first_or_404()
    return render_template('play.html', court=court)


@app.route('/court/<token>')
def scoreboard(token):
    """Public viewer / scoreboard screen — auto-refreshing display."""
    court = Court.query.filter_by(access_token=token).first_or_404()
    return render_template('scoreboard.html', court=court)


# ══════════════════════════════════════════
# STATE API
# ══════════════════════════════════════════
@app.route('/api/court/<token>/state', methods=['GET'])
def get_state(token):
    court = Court.query.filter_by(access_token=token).first_or_404()
    state = court.court_state or {}
    return jsonify(state)


@app.route('/api/court/<token>/state', methods=['POST'])
def set_state(token):
    court = Court.query.filter_by(access_token=token).first_or_404()
    data  = request.get_json(force=True, silent=True) or {}
    court.court_state = data
    db.session.commit()
    return jsonify({'ok': True})


# ══════════════════════════════════════════
# QR CODE  →  points to SCOREBOARD
# ══════════════════════════════════════════
@app.route('/qr/<token>')
def qr_code(token):
    court = Court.query.filter_by(access_token=token).first_or_404()

    # QR takes viewers to the PUBLIC scoreboard, not the operator screen
    board_url = url_for('scoreboard', token=token, _external=True)

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(board_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#1a1a2e", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)

    return send_file(buf, mimetype='image/png')


# ══════════════════════════════════════════
# STRIPE
# ══════════════════════════════════════════
@app.route('/subscribe')
@login_required
def subscribe():
    user   = current_user()
    courts = Court.query.filter_by(user_id=user.id).count()

    if not stripe.api_key:
        flash('Stripe not configured.', 'danger')
        return redirect(url_for('dashboard'))

    try:
        # Create or retrieve Stripe customer
        if not user.stripe_customer_id:
            customer = stripe.Customer.create(
                email=user.email,
                name=user.club_name or user.email,
                metadata={'user_id': user.id}
            )
            user.stripe_customer_id = customer.id
            db.session.commit()

        checkout = stripe.checkout.Session.create(
            customer=user.stripe_customer_id,
            payment_method_types=['card'],
            line_items=[{
                'price'    : STRIPE_PRICE_ID,
                'quantity' : max(courts, 1),
            }],
            mode='subscription',
            success_url=url_for('subscribe_success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=url_for('dashboard', _external=True),
            metadata={'user_id': user.id}
        )
        return redirect(checkout.url, code=303)

    except stripe.error.StripeError as e:
        flash(f'Stripe error: {e.user_message}', 'danger')
        return redirect(url_for('dashboard'))


@app.route('/subscribe/success')
@login_required
def subscribe_success():
    flash('Subscription activated! Welcome aboard 🎾', 'success')
    return redirect(url_for('dashboard'))


@app.route('/subscribe/cancel')
@login_required
def subscribe_cancel():
    user = current_user()
    if not user.stripe_sub_id:
        flash('No active subscription found.', 'warning')
        return redirect(url_for('dashboard'))

    try:
        stripe.Subscription.modify(
            user.stripe_sub_id,
            cancel_at_period_end=True
        )
        user.sub_status = 'cancel_at_period_end'
        db.session.commit()
        flash('Subscription will cancel at end of billing period.', 'info')
    except stripe.error.StripeError as e:
        flash(f'Error: {e.user_message}', 'danger')

    return redirect(url_for('dashboard'))


@app.route('/stripe/webhook', methods=['POST'])
def stripe_webhook():
    payload   = request.data
    sig_header = request.headers.get('Stripe-Signature', '')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        return 'Bad signature', 400

    ev_type = event['type']
    obj     = event['data']['object']

    if ev_type == 'customer.subscription.created':
        _handle_sub_update(obj, 'active')

    elif ev_type == 'customer.subscription.updated':
        _handle_sub_update(obj, obj.get('status', 'active'))

    elif ev_type == 'customer.subscription.deleted':
        _handle_sub_update(obj, 'canceled')

    elif ev_type == 'invoice.payment_succeeded':
        cus_id = obj.get('customer')
        user   = User.query.filter_by(stripe_customer_id=cus_id).first()
        if user:
            user.sub_status = 'active'
            db.session.commit()

    elif ev_type == 'invoice.payment_failed':
        cus_id = obj.get('customer')
        user   = User.query.filter_by(stripe_customer_id=cus_id).first()
        if user:
            user.sub_status = 'past_due'
            db.session.commit()

    return jsonify({'received': True})


def _handle_sub_update(sub_obj, status):
    cus_id = sub_obj.get('customer')
    sub_id = sub_obj.get('id')
    user   = User.query.filter_by(stripe_customer_id=cus_id).first()
    if user:
        user.stripe_sub_id = sub_id
        user.sub_status    = status
        db.session.commit()


# ══════════════════════════════════════════
# ACCOUNT
# ══════════════════════════════════════════
@app.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    user = current_user()
    if request.method == 'POST':
        club_name = request.form.get('club_name', '').strip()
        new_pw    = request.form.get('new_password', '')
        if club_name:
            user.club_name = club_name
        if new_pw:
            user.set_password(new_pw)
        db.session.commit()
        flash('Account updated.', 'success')
        return redirect(url_for('account'))
    return render_template('account.html', user=user)


# ══════════════════════════════════════════
# DB INIT & RUN
# ══════════════════════════════════════════
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
