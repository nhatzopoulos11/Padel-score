from flask import Flask, render_template, request, redirect, session, send_file, jsonify
from models import db, Club, Court, CourtState
from auth import hash_password, check_password
from datetime import datetime
import os
import qrcode
import io
import json

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Database config
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///padel.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# Create tables on startup
with app.app_context():
    db.create_all()

# ─────────────────────────────────────────
# HOME
# ─────────────────────────────────────────
@app.route('/')
def home():
    if 'club_id' in session:
        return redirect('/dashboard')
    return redirect('/login')

# ─────────────────────────────────────────
# REGISTER
# ─────────────────────────────────────────
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email', '').lower().strip()
        password = request.form.get('password', '')
        club_name = request.form.get('club_name', '').strip()
        owner_name = request.form.get('owner_name', '').strip()
        num_courts = int(request.form.get('num_courts', 1))

        if Club.query.filter_by(email=email).first():
            return render_template('register.html', error='Email already registered')

        club = Club(
            email=email,
            password_hash=hash_password(password),
            club_name=club_name,
            owner_name=owner_name
        )
        db.session.add(club)
        db.session.flush()

        for i in range(1, num_courts + 1):
            court = Court(
                club_id=club.id,
                court_name=f'Court {i}'
            )
            db.session.add(court)

        db.session.commit()
        session['club_id'] = club.id
        return redirect('/dashboard')

    return render_template('register.html')

# ─────────────────────────────────────────
# LOGIN
# ─────────────────────────────────────────
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').lower().strip()
        password = request.form.get('password', '')

        club = Club.query.filter_by(email=email).first()

        if not club or not check_password(password, club.password_hash):
            return render_template('login.html', error='Invalid email or password')

        session['club_id'] = club.id
        return redirect('/dashboard')

    return render_template('login.html')

# ─────────────────────────────────────────
# LOGOUT
# ─────────────────────────────────────────
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

# ─────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────
@app.route('/dashboard')
def dashboard():
    if 'club_id' not in session:
        return redirect('/login')

    club = Club.query.get(session['club_id'])
    if not club:
        session.clear()
        return redirect('/login')

    courts = Court.query.filter_by(club_id=club.id).all()
    return render_template('dashboard.html', club=club, courts=courts)

# ─────────────────────────────────────────
# ADD COURT
# ─────────────────────────────────────────
@app.route('/court/add', methods=['POST'])
def add_court():
    if 'club_id' not in session:
        return redirect('/login')

    club = Club.query.get(session['club_id'])
    if not club:
        session.clear()
        return redirect('/login')

    court_name = request.form.get('court_name', '').strip()
    if not court_name:
        existing_count = Court.query.filter_by(club_id=club.id).count()
        court_name = f'Court {existing_count + 1}'

    court = Court(
        club_id=club.id,
        court_name=court_name
    )
    db.session.add(court)
    db.session.commit()

    return redirect('/dashboard')

# ─────────────────────────────────────────
# RENAME COURT
# ─────────────────────────────────────────
@app.route('/court/<int:court_id>/rename', methods=['POST'])
def rename_court(court_id):
    if 'club_id' not in session:
        return redirect('/login')

    court = Court.query.filter_by(id=court_id, club_id=session['club_id']).first()
    if not court:
        return "Court not found or access denied", 404

    new_name = request.form.get('court_name', '').strip()
    if new_name:
        court.court_name = new_name
        db.session.commit()

    return redirect('/dashboard')

# ─────────────────────────────────────────
# DELETE COURT
# ─────────────────────────────────────────
@app.route('/court/<int:court_id>/delete', methods=['POST'])
def delete_court(court_id):
    if 'club_id' not in session:
        return redirect('/login')

    court = Court.query.filter_by(id=court_id, club_id=session['club_id']).first()
    if not court:
        return "Court not found or access denied", 404

    db.session.delete(court)
    db.session.commit()

    return redirect('/dashboard')

# ─────────────────────────────────────────
# COURT SCOREBOARD (by UUID token)
# ─────────────────────────────────────────
@app.route('/court/<token>')
def court(token):
    court = Court.query.filter_by(access_token=token).first()

    # Fallback: try numeric ID for old links
    if not court:
        try:
            court = Court.query.get(int(token))
        except (ValueError, TypeError):
            pass

    if not court:
        return "Court not found", 404

    club = court.club

    if not club.can_access():
        return render_template('inactive.html', club=club)

    return render_template('scoreboard.html', court=court, club=club)

# ─────────────────────────────────────────
# API: GET COURT STATE
# ─────────────────────────────────────────
@app.route('/api/court/<token>/state', methods=['GET'])
def get_court_state(token):
    court = Court.query.filter_by(access_token=token).first()
    if not court:
        return jsonify({'error': 'Court not found'}), 404

    if not court.club.can_access():
        return jsonify({'error': 'Subscription inactive'}), 403

    court_state = CourtState.query.filter_by(court_id=court.id).first()

    if not court_state:
        return jsonify({'state': {}, 'updated_at': None})

    return jsonify({
        'state': json.loads(court_state.state_json),
        'updated_at': court_state.updated_at.isoformat() if court_state.updated_at else None
    })

# ─────────────────────────────────────────
# API: SAVE COURT STATE
# ─────────────────────────────────────────
@app.route('/api/court/<token>/state', methods=['POST'])
def save_court_state(token):
    court = Court.query.filter_by(access_token=token).first()
    if not court:
        return jsonify({'error': 'Court not found'}), 404

    if not court.club.can_access():
        return jsonify({'error': 'Subscription inactive'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    court_state = CourtState.query.filter_by(court_id=court.id).first()

    if court_state:
        court_state.state_json = json.dumps(data)
        court_state.updated_at = datetime.utcnow()
    else:
        court_state = CourtState(
            court_id=court.id,
            state_json=json.dumps(data)
        )
        db.session.add(court_state)

    db.session.commit()

    return jsonify({
        'success': True,
        'updated_at': court_state.updated_at.isoformat()
    })

# ─────────────────────────────────────────
# QR CODE GENERATOR
# ─────────────────────────────────────────
@app.route('/qr/<token>')
def qr_code(token):
    court = Court.query.filter_by(access_token=token).first()

    if not court:
        try:
            court = Court.query.get(int(token))
        except (ValueError, TypeError):
            return "Court not found", 404

    if not court:
        return "Court not found", 404

    url = f"https://web-production-c823c.up.railway.app/court/{court.access_token}"

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)

    return send_file(buf, mimetype='image/png')

# ─────────────────────────────────────────
# SUBSCRIBE (Stripe - placeholder)
# ─────────────────────────────────────────
@app.route('/subscribe')
def subscribe():
    if 'club_id' not in session:
        return redirect('/login')
    # Stripe checkout will go here
    return render_template('subscribe.html')

# ─────────────────────────────────────────
# RUN
# ─────────────────────────────────────────
if __name__ == '__main__':
    app.run(debug=False)
