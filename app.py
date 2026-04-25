import os
import secrets
import json
from datetime import datetime, timedelta
from flask import (Flask, render_template, request, redirect,
                   url_for, session, jsonify, send_file)
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
import stripe

# ============================================================
# APP INIT
# ============================================================
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-in-prod')

# ============================================================
# DATABASE
# ============================================================
raw_url = os.environ.get('DATABASE_URL', 'sqlite:///padel.db')
if raw_url.startswith('postgres://'):
    raw_url = raw_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = raw_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ============================================================
# STRIPE
# ============================================================
stripe.api_key            = os.environ.get('STRIPE_SECRET_KEY', '')
STRIPE_WEBHOOK_SECRET     = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
STRIPE_PRICE_ID           = os.environ.get('STRIPE_PRICE_ID', '')
BASE_URL                  = os.environ.get('BASE_URL',
                            'https://web-production-c823c.up.railway.app')

# ============================================================
# MODELS
# ============================================================
class Club(db.Model):
    __tablename__ = 'clubs'

    id                  = db.Column(db.Integer, primary_key=True)
    owner_name          = db.Column(db.String(100), nullable=False)
    club_name           = db.Column(db.String(100), nullable=False)
    email               = db.Column(db.String(120), unique=True, nullable=False)
    password_hash       = db.Column(db.String(256), nullable=False)
    created_at          = db.Column(db.DateTime, default=datetime.utcnow)
    trial_ends_at       = db.Column(db.DateTime)
    is_trial            = db.Column(db.Boolean, default=True)
    subscription_id     = db.Column(db.String(200))
    subscription_status = db.Column(db.String(50), default='trialing')

    courts = db.relationship('Court', backref='club', lazy=True,
                             cascade='all, delete-orphan')

    def trial_days_left(self):
        if not self.trial_ends_at:
            return 0
        delta = self.trial_ends_at - datetime.utcnow()
        return max(0, delta.days)

    @property
    def is_active(self):
        if self.is_trial and self.trial_days_left() > 0:
            return True
        if self.subscription_status in ('active', 'trialing'):
            return True
        return False

    def can_access(self):
        return self.is_active


class Court(db.Model):
    __tablename__ = 'courts'

    id           = db.Column(db.Integer, primary_key=True)
    club_id      = db.Column(db.Integer, db.ForeignKey('clubs.id'),
                             nullable=False)
    court_name   = db.Column(db.String(100), nullable=False)
    access_token = db.Column(db.String(64), unique=True, nullable=False)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    state = db.relationship('CourtState', backref='court', uselist=False,
                            cascade='all, delete-orphan')


class CourtState(db.Model):
    __tablename__ = 'court_states'

    id         = db.Column(db.Integer, primary_key=True)
    court_id   = db.Column(db.Integer, db.ForeignKey('courts.id'),
                           nullable=False)
    state_json = db.Column(db.Text, default='{}')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow)


# ============================================================
# DB INIT
# ============================================================
with app.app_context():
    db.create_all()


# ============================================================
# DECORATORS
# ============================================================
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'club_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def subscription_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'club_id' not in session:
            return redirect(url_for('login'))
        club = db.session.get(Club, session['club_id'])
        if not club or not club.can_access():
            return redirect(url_for('inactive'))
        return f(*args, **kwargs)
    return decorated


# ============================================================
# AUTH ROUTES
# ============================================================
@app.route('/')
def index():
    if 'club_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        from werkzeug.security import generate_password_hash

        owner_name = request.form.get('owner_name', '').strip()
        club_name  = request.form.get('club_name',  '').strip()
        email      = request.form.get('email',      '').strip().lower()
        password   = request.form.get('password',   '')

        if not all([owner_name, club_name, email, password]):
            return render_template('register.html',
                                   error='All fields are required.')

        if len(password) < 6:
            return render_template('register.html',
                                   error='Password must be at least 6 characters.')

        if Club.query.filter_by(email=email).first():
            return render_template('register.html',
                                   error='Email already registered.')

        club = Club(
            owner_name          = owner_name,
            club_name           = club_name,
            email               = email,
            password_hash       = generate_password_hash(password),
            trial_ends_at       = datetime.utcnow() + timedelta(days=14),
            is_trial            = True,
            subscription_status = 'trialing'
        )
        db.session.add(club)
        db.session.commit()

        session['club_id'] = club.id
        return redirect(url_for('dashboard'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        from werkzeug.security import check_password_hash

        email    = request.form.get('email',    '').strip().lower()
        password = request.form.get('password', '')

        club = Club.query.filter_by(email=email).first()
        if not club or not check_password_hash(club.password_hash, password):
            return render_template('login.html',
                                   error='Invalid email or password.')

        session['club_id'] = club.id
        return redirect(url_for('dashboard'))

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ============================================================
# DASHBOARD
# ============================================================
@app.route('/dashboard')
@login_required
def dashboard():
    club   = db.session.get(Club, session['club_id'])
    courts = Court.query.filter_by(club_id=club.id)\
                        .order_by(Court.created_at).all()
    return render_template('dashboard.html', club=club, courts=courts)


# ============================================================
# COURT API
# ============================================================
@app.route('/api/court/add', methods=['POST'])
@login_required
def add_court():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data received'})

    name = data.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'Court name required'})

    club  = db.session.get(Club, session['club_id'])
    token = secrets.token_urlsafe(16)

    court = Court(
        club_id      = club.id,
        court_name   = name,
        access_token = token
    )
    db.session.add(court)
    db.session.commit()

    return jsonify({'success': True, 'token': token, 'name': name})


@app.route('/api/court/<token>/delete', methods=['POST'])
@login_required
def delete_court(token):
    court = Court.query.filter_by(access_token=token).first()
    if not court:
        return jsonify({'success': False, 'error': 'Court not found'})

    club = db.session.get(Club, session['club_id'])
    if court.club_id != club.id:
        return jsonify({'success': False, 'error': 'Unauthorized'})

    db.session.delete(court)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/court/<token>/state', methods=['GET'])
def get_court_state(token):
    court = Court.query.filter_by(access_token=token).first()
    if not court:
        return jsonify({'error': 'Court not found'}), 404

    state = CourtState.query.filter_by(court_id=court.id).first()
    if not state:
        return jsonify({})

    try:
        return jsonify(json.loads(state.state_json))
    except Exception:
        return jsonify({})


@app.route('/api/court/<token>/state', methods=['POST'])
def save_court_state(token):
    court = Court.query.filter_by(access_token=token).first()
    if not court:
        return jsonify({'error': 'Court not found'}), 404

    data  = request.get_json()
    state = CourtState.query.filter_by(court_id=court.id).first()

    if state:
        state.state_json = json.dumps(data)
        state.updated_at = datetime.utcnow()
    else:
        state = CourtState(
            court_id   = court.id,
            state_json = json.dumps(data)
        )
        db.session.add(state)

    db.session.commit()
    return jsonify({'success': True})


# ============================================================
# SCOREBOARD PAGE
# ============================================================
@app.route('/court/<token>')
def scoreboard(token):
    court = Court.query.filter_by(access_token=token).first()
    if not court:
        return render_template('404.html'), 404

    club = db.session.get(Club, court.club_id)
    if not club or not club.can_access():
        return render_template('inactive.html', club=club)

    return render_template('scoreboard.html', court=court, club=club)


# ============================================================
# QR CODE
# ============================================================
@app.route('/qr/<token>')
@login_required
def qr_code(token):
    import qrcode
    import io

    court = Court.query.filter_by(access_token=token).first()
    if not court:
        return 'Not found', 404

    club = db.session.get(Club, session['club_id'])
    if court.club_id != club.id:
        return 'Unauthorized', 403

    url = f'{BASE_URL}/court/{token}'
    qr  = qrcode.make(url)
    buf = io.BytesIO()
    qr.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')


# ============================================================
# SUBSCRIPTION
# ============================================================
@app.route('/subscribe')
@login_required
def subscribe():
    club        = db.session.get(Club, session['club_id'])
    courts      = Court.query.filter_by(club_id=club.id).all()
    court_count = max(len(courts), 1)

    try:
        checkout = stripe.checkout.Session.create(
            payment_method_types = ['card'],
            mode                 = 'subscription',
            line_items           = [{
                'price'    : STRIPE_PRICE_ID,
                'quantity' : court_count,
            }],
            customer_email = club.email,
            metadata       = {'club_id': str(club.id)},
            success_url    = BASE_URL +
                             '/subscribe/success?session_id={CHECKOUT_SESSION_ID}',
            cancel_url     = BASE_URL + '/dashboard',
        )
        return redirect(checkout.url)
    except Exception as e:
        return f'Stripe error: {str(e)}', 500


@app.route('/subscribe/success')
@login_required
def subscribe_success():
    session_id = request.args.get('session_id')
    if session_id:
        try:
            checkout = stripe.checkout.Session.retrieve(session_id)
            club     = db.session.get(Club, session['club_id'])
            if club:
                club.subscription_id     = checkout.subscription
                club.subscription_status = 'active'
                club.is_trial            = False
                db.session.commit()
        except Exception:
            pass
    return redirect(url_for('dashboard'))


@app.route('/inactive')
def inactive():
    club = None
    if 'club_id' in session:
        club = db.session.get(Club, session['club_id'])
    return render_template('inactive.html', club=club)


# ============================================================
# STRIPE WEBHOOK
# ============================================================
@app.route('/stripe/webhook', methods=['POST'])
def stripe_webhook():
    payload    = request.get_data()
    sig_header = request.headers.get('Stripe-Signature', '')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        return 'Invalid signature', 400
    except Exception:
        return 'Webhook error', 400

    etype = event['type']

    if etype == 'customer.subscription.updated':
        sub  = event['data']['object']
        club = Club.query.filter_by(subscription_id=sub['id']).first()
        if club:
            club.subscription_status = sub['status']
            db.session.commit()

    elif etype == 'customer.subscription.deleted':
        sub  = event['data']['object']
        club = Club.query.filter_by(subscription_id=sub['id']).first()
        if club:
            club.subscription_status = 'canceled'
            db.session.commit()

    elif etype == 'invoice.payment_failed':
        invoice = event['data']['object']
        club    = Club.query.filter_by(
                      subscription_id=invoice.get('subscription')).first()
        if club:
            club.subscription_status = 'past_due'
            db.session.commit()

    elif etype == 'checkout.session.completed':
        checkout = event['data']['object']
        club_id  = checkout.get('metadata', {}).get('club_id')
        if club_id:
            club = db.session.get(Club, int(club_id))
            if club:
                club.subscription_id     = checkout.get('subscription')
                club.subscription_status = 'active'
                club.is_trial            = False
                db.session.commit()

    return jsonify({'status': 'ok'})


# ============================================================
# DEBUG / HEALTH
# ============================================================
@app.route('/test')
def test_db():
    try:
        club_count  = Club.query.count()
        court_count = Court.query.count()
        return jsonify({
            'status' : 'ok',
            'clubs'  : club_count,
            'courts' : court_count,
            'db'     : str(app.config['SQLALCHEMY_DATABASE_URI'])[:50]
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/health')
def health():
    return jsonify({'status': 'ok'}), 200


# ============================================================
# RUN
# ============================================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
