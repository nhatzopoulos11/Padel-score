from flask import Flask, render_template, request, redirect, session, url_for
from models import db, Club, Court
from auth import hash_password, check_password
from datetime import datetime
import os

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

        # Check if email exists
        if Club.query.filter_by(email=email).first():
            return render_template('register.html', error='Email already registered')

        # Create club
        club = Club(
            email=email,
            password_hash=hash_password(password),
            club_name=club_name,
            owner_name=owner_name
        )
        db.session.add(club)
        db.session.flush()  # Get club.id before commit

        # Create courts
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
# COURT SCOREBOARD
# ─────────────────────────────────────────
@app.route('/court/<int:court_id>')
def court(court_id):
    court = Court.query.get_or_404(court_id)
    club = Club.query.get(court.club_id)

    if not club.is_active:
        return render_template('inactive.html', club=club)

    return render_template('scoreboard.html', court=court, club=club)

# ─────────────────────────────────────────
# RUN
# ─────────────────────────────────────────
if __name__ == '__main__':
    app.run(debug=False)
