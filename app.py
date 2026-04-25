# app.py — complete file, replace everything
import os
import json
import uuid
import stripe
from datetime import datetime, timedelta

from flask import (Flask, render_template, request, redirect,
                   url_for, session, jsonify, flash)
from models import db, Club, Court, CourtState
from auth import hash_password, check_password

# ── App & config ──────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-in-prod')

DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///padel.db')
# Railway gives postgres://, SQLAlchemy needs postgresql://
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

stripe.api_key = os.environ.get('STRIPE_SECRET_KEY', '')
STRIPE_PRICE_ID   = os.environ.get('STRIPE_PRICE_ID', '')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')

db.init_app(app)

# ── DB init ───────────────────────────────────────────────────────────────────
with app.app_context():
    db.create_all()

# ── Helpers ───────────────────────────────────────────────────────────────────
def current_club():
    """Return the logged-in Club object or None."""
    club_id = session.get('club_id')
    if not club_id:
        return None
    return db.session.get(Club, club_id)


def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('club_id'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def subscription_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        club = current_club()
        if not club:
            return redirect(url_for('login'))
        if not club.can_access():
            return redirect(url_for('inactive'))
        return f(*args, **kwargs)
    return decorated

# ── Auth routes ───────────────────────────────────────────────────────────────
@app.route('/')
def index():
    if session.get('club_id'):
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email      = request.form['email'].strip().lower()
        password   = request.form['password']
        club_name  = request.form['club_name'].strip()
        owner_name = request.form['owner_name'].strip()

        if Club.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
            return render_template('register.html')

        club = Club(
            email=email,
            password_hash=hash_password(password),
            club_name=club_name,
            owner_name=owner_name
        )
        db.session.add(club)
        db.session.commit()
        session['club_id'] = club.id
        flash(f'Welcome {club_name}! Your 14-day trial has started.', 'success')
        return redirect(url_for('dashboard'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email    = request.form['email'].strip().lower()
        password = request.form['password']
        club     = Club.query.filter_by(email=email).first()

        if club and check_password(password, club.password_hash):
            session['club_id'] = club.id
            return redirect(url_for('dashboard'))

        flash('Invalid email or password.', 'error')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/inactive')
def inactive():
    club = current_club()
    return render_template('inactive.html', club=club)

# ── Dashboard ─────────────────────────────────────────────────────────────────
@app.route('/dashboard')
@login_required
def dashboard():
    club = current_club()
    if not club.can_access():
        return redirect(url_for('inactive'))
    courts = Court.query.filter_by(club_id=club.id).all()
    return render_template('dashboard.html', club=club, courts=courts)

# ── Court management ──────────────────────────────────────────────────────────
@app.route('/court/add', methods=['POST'])
@login_required
@subscription_required
def add_court():
    club = current_club()
    court_name = request.form.get('court_name', '').strip()
    if not court_name:
        flash('Court name is required.', 'error')
        return redirect(url_for('dashboard'))

    court = Court(club_id=club.id, court_name=court_name)
    db.session.add(court)
    db.session.commit()
    flash(f'Court "{court_name}" added.', 'success')
    return redirect(url_for('dashboard'))


@app.route('/court/<int:court_id>/delete', methods=['POST'])
@login_required
def delete_court(court_id):
    club   = current_club()
    court  = Court.query.filter_by(id=court_id, club_id=club.id).first_or_404()
    db.session.delete(court)
    db.session.commit()
    flash(f'Court "{court.court_name}" deleted.', 'success')
    return redirect(url_for('dashboard'))


@app.route('/court/<token>')
def court_view(token):
    """Public scoreboard page served to court tablet/phone."""
    court = Court.query.filter_by(access_token=token).first_or_404()
    club  = court.club
    if not club.can_access():
        return render_template('inactive.html', club=club)
    return render_template('court.html', court=court, club=club)

# ── QR helper ────────────────────────────────────────────────────────────────
@app.route('/court/<int:court_id>/qr')
@login_required
def court_qr(court_id):
    club  = current_club()
    court = Court.query.filter_by(id=court_id, club_id=club.id).first_or_404()
    court_url = url_for('court_view', token=court.access_token, _external=True)
    return render_template('qr.html', court=court, court_url=court_url)

# ── State API ────────────────────────────────────────────────────────────────
@app.route('/api/court/<token>/state', methods=['GET'])
def get_court_state(token):
    court = Court.query.filter_by(access_token=token).first()
    if not court:
        return jsonify({'error': 'Court not found'}), 404

    try:
        if court.state and court.state.state_json:
            data = json.loads(court.state.state_json)
            return jsonify(data)
        return jsonify({'state': None})
    except Exception as e:
        print(f"GET state error: {e}")
        return jsonify({'state': None})


@app.route('/api/court/<token>/state', methods=['POST'])
def set_court_state(token):
    court = Court.query.filter_by(access_token=token).first()
    if not court:
        return jsonify({'error': 'Court not found'}), 404

    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({'error': 'No data'}), 400

        data['serverTime'] = int(datetime.utcnow().timestamp() * 1000)

        if court.state:
            court.state.state_json = json.dumps(data)
            court.state.updated_at = datetime.utcnow()
        else:
            db.session.add(CourtState(
                court_id=court.id,
                state_json=json.dumps(data)
            ))

        db.session.commit()
        return jsonify({'ok': True, 'syncTime': data.get('syncTime', 0)})

    except Exception as e:
        print(f"POST state error: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/court/<token>/test')
def test_court_api(token):
    """Debug route — disable in production."""
    court = Court.query.filter_by(access_token=token).first()
    if not court:
        return jsonify({'error': f'No court for token: {token}'}), 404

    try:
        test_data = json.dumps({'test': True, 'time': str(datetime.utcnow())})
        if court.state:
            court.state.state_json = test_data
        else:
            db.session.add(CourtState(court_id=court.id, state_json=test_data))
        db.session.commit()
        write_ok = True
    except Exception as e:
        db.session.rollback()
        write_ok = str(e)

    return jsonify({
        'court_name':    court.court_name,
        'write_ok':      write_ok,
        'has_state':     court.state is not None,
        'state_preview': court.state.state_json[:100] if court.state else None
    })

# ── Stripe / subscription ─────────────────────────────────────────────────────
@app.route('/subscribe')
@login_required
def subscribe():
    club = current_club()
    try:
        checkout = stripe.checkout.Session.create(
            payment_method_types=['card'],
            mode='subscription',
            line_items=[{'price': STRIPE_PRICE_ID, 'quantity': len(club.courts) or 1}],
            customer_email=club.email,
            metadata={'club_id': club.id},
            success_url=url_for('subscribe_success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=url_for('dashboard', _external=True),
        )
        return redirect(checkout.url)
    except Exception as e:
        flash(f'Stripe error: {e}', 'error')
        return redirect(url_for('dashboard'))


@app.route('/subscribe/success')
@login_required
def subscribe_success():
    flash('Subscription activated! Thank you.', 'success')
    return redirect(url_for('dashboard'))


@app.route('/stripe/webhook', methods=['POST'])
def stripe_webhook():
    payload   = request.data
    sig_header = request.headers.get('Stripe-Signature', '')

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        print(f"Webhook error: {e}")
        return jsonify({'error': str(e)}), 400

    if event['type'] == 'checkout.session.completed':
        sess    = event['data']['object']
        club_id = sess.get('metadata', {}).get('club_id')
        sub_id  = sess.get('subscription')
        if club_id:
            club = db.session.get(Club, int(club_id))
            if club:
                club.stripe_subscription_id = sub_id
                club.stripe_customer_id     = sess.get('customer')
                club.is_active              = True
                db.session.commit()

    elif event['type'] in ('customer.subscription.deleted',
                           'customer.subscription.paused'):
        sub = event['data']['object']
        club = Club.query.filter_by(
            stripe_subscription_id=sub['id']
        ).first()
        if club:
            club.is_active = False
            db.session.commit()

    return jsonify({'ok': True})

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == '__main__':
    app.run(debug=True)
