from flask import Blueprint, render_template, redirect, url_for, request, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, Club, Court
from datetime import datetime, timedelta

auth = Blueprint('auth', __name__)

@auth.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        club_name = request.form.get('club_name')
        email = request.form.get('email')
        password = request.form.get('password')
        phone = request.form.get('phone')
        city = request.form.get('city')
        num_courts = int(request.form.get('num_courts', 1))

        # Check if email already exists
        existing_club = Club.query.filter_by(email=email).first()
        if existing_club:
            flash('Email already registered!', 'error')
            return redirect(url_for('auth.register'))

        # Create new club
        new_club = Club(
            club_name=club_name,
            email=email,
            password=generate_password_hash(password),
            phone=phone,
            city=city,
            is_active=True,
            is_trial=True,
            trial_ends=datetime.utcnow() + timedelta(days=14)  # 14 day free trial
        )

        db.session.add(new_club)
        db.session.flush()  # Get the ID before commit

        # Create courts for this club
        for i in range(1, num_courts + 1):
            court = Court(
                club_id=new_club.id,
                court_name=f'Court {i}',
                is_active=True
            )
            db.session.add(court)

        db.session.commit()

        # Log them in immediately
        session['club_id'] = new_club.id
        session['club_name'] = new_club.club_name

        flash('Welcome! Your 14-day free trial has started!', 'success')
        return redirect(url_for('auth.dashboard'))

    return render_template('register.html')


@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        club = Club.query.filter_by(email=email).first()

        if not club or not check_password_hash(club.password, password):
            flash('Invalid email or password!', 'error')
            return redirect(url_for('auth.login'))

        if not club.is_active:
            flash('Your account is deactivated. Please contact support.', 'error')
            return redirect(url_for('auth.login'))

        # Log them in
        session['club_id'] = club.id
        session['club_name'] = club.club_name

        return redirect(url_for('auth.dashboard'))

    return render_template('login.html')


@auth.route('/dashboard')
def dashboard():
    if 'club_id' not in session:
        return redirect(url_for('auth.login'))

    club = Club.query.get(session['club_id'])
    courts = Court.query.filter_by(club_id=club.id).all()

    # Check trial status
    trial_warning = False
    days_left = 0
    if club.is_trial and club.trial_ends:
        days_left = (club.trial_ends - datetime.utcnow()).days
        if days_left <= 3:
            trial_warning = True

    return render_template('dashboard.html',
                           club=club,
                           courts=courts,
                           trial_warning=trial_warning,
                           days_left=days_left)


@auth.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))
