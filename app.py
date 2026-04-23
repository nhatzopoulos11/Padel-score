from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from models import db, Club, Court
from auth import auth
import os

app = Flask(__name__)

# Secret key for sessions
app.secret_key = os.environ.get('SECRET_KEY', 'padel-secret-key-2024')

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///padel.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db.init_app(app)

# Register auth blueprint
app.register_blueprint(auth)

# Create tables on startup
with app.app_context():
    db.create_all()

# ============================================================
# SCORE KEEPER ROUTES (existing functionality)
# ============================================================

# Game state (in memory - per session)
game_state = {
    'score': {'team1': 0, 'team2': 0},
    'games': {'team1': 0, 'team2': 0},
    'sets': {'team1': 0, 'team2': 0},
    'serving': None,
    'serving_player': None,
    'rotation': 0,
    'history': [],
    'tiebreak': False,
    'golden_point': False,
    'game_over': False,
    'winner': None,
    'court_end_time': None,
    'phase': 'select_server'
}

def get_score_display(score, tiebreak, golden_point):
    if tiebreak or golden_point:
        return str(score)
    score_map = {0: '0', 1: '15', 2: '30', 3: '40'}
    return score_map.get(score, str(score))

def check_game_winner(state):
    s1 = state['score']['team1']
    s2 = state['score']['team2']

    if state['golden_point']:
        if s1 >= 1:
            return 'team1'
        elif s2 >= 1:
            return 'team2'
        return None

    if state['tiebreak']:
        if s1 >= 7 and s1 - s2 >= 2:
            return 'team1'
        if s2 >= 7 and s2 - s1 >= 2:
            return 'team2'
        return None

    if s1 >= 4 and s1 - s2 >= 2:
        return 'team1'
    if s2 >= 4 and s2 - s1 >= 2:
        return 'team2'
    if s1 == 3 and s2 == 3:
        return None
    return None

def check_set_winner(state):
    g1 = state['games']['team1']
    g2 = state['games']['team2']

    if g1 >= 6 and g1 - g2 >= 2:
        return 'team1'
    if g2 >= 6 and g2 - g1 >= 2:
        return 'team2'
    if g1 == 7:
        return 'team1'
    if g2 == 7:
        return 'team2'
    return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/court/<int:court_id>')
def court(court_id):
    court = Court.query.get_or_404(court_id)
    club = Club.query.get(court.club_id)
    if not club.is_active or not court.is_active:
        return "This court is not active.", 403
    return render_template('index.html', court=court, club=club)

@app.route('/api/state')
def get_state():
    state = game_state.copy()
    t1 = state['score']['team1']
    t2 = state['score']['team2']
    state['display_score'] = {
        'team1': get_score_display(t1, state['tiebreak'], state['golden_point']),
        'team2': get_score_display(t2, state['tiebreak'], state['golden_point'])
    }
    return jsonify(state)

@app.route('/api/select_server', methods=['POST'])
def select_server():
    data = request.json
    team = data.get('team')
    player = data.get('player')

    if player:
        game_state['serving'] = team
        game_state['serving_player'] = player
        game_state['phase'] = 'playing'
    else:
        game_state['serving'] = team
        game_state['phase'] = 'select_player'

    return jsonify(game_state)

@app.route('/api/point', methods=['POST'])
def add_point():
    data = request.json
    team = data.get('team')
    other = 'team2' if team == 'team1' else 'team1'

    # Save state to history
    import copy
    history_entry = copy.deepcopy(game_state)
    history_entry.pop('history', None)
    game_state['history'].append(history_entry)
    if len(game_state['history']) > 50:
        game_state['history'].pop(0)

    game_state['score'][team] += 1

    # Check deuce
    s1 = game_state['score']['team1']
    s2 = game_state['score']['team2']
    if not game_state['tiebreak'] and not game_state['golden_point']:
        if s1 == 3 and s2 == 3:
            pass  # deuce
        elif s1 >= 4 and s2 >= 4:
            pass  # advantage

    winner = check_game_winner(game_state)
    if winner:
        game_state['games'][winner] += 1
        game_state['score'] = {'team1': 0, 'team2': 0}
        game_state['tiebreak'] = False
        game_state['golden_point'] = False

        # Rotate server
        serving_teams = ['team1', 'team2']
        current = serving_teams.index(game_state['serving'])
        game_state['serving'] = serving_teams[(current + 1) % 2]

        # Check tiebreak
        g1 = game_state['games']['team1']
        g2 = game_state['games']['team2']
        if g1 == 6 and g2 == 6:
            game_state['tiebreak'] = True

        # Check set winner
        set_winner = check_set_winner(game_state)
        if set_winner:
            game_state['sets'][set_winner] += 1
            game_state['games'] = {'team1': 0, 'team2': 0}
            game_state['tiebreak'] = False

            # Check match winner (first to 2 sets)
            if game_state['sets'][set_winner] >= 2:
                game_state['game_over'] = True
                game_state['winner'] = set_winner

    return jsonify(game_state)

@app.route('/api/undo', methods=['POST'])
def undo():
    if game_state['history']:
        import copy
        last = game_state['history'].pop()
        game_state.update(last)
        game_state['history'] = game_state.get('history', [])
    return jsonify(game_state)

@app.route('/api/reset', methods=['POST'])
def reset():
    game_state.update({
        'score': {'team1': 0, 'team2': 0},
        'games': {'team1': 0, 'team2': 0},
        'sets': {'team1': 0, 'team2': 0},
        'serving': None,
        'serving_player': None,
        'rotation': 0,
        'history': [],
        'tiebreak': False,
        'golden_point': False,
        'game_over': False,
        'winner': None,
        'court_end_time': None,
        'phase': 'select_server'
    })
    return jsonify(game_state)

@app.route('/api/set_end_time', methods=['POST'])
def set_end_time():
    data = request.json
    game_state['court_end_time'] = data.get('end_time')
    return jsonify(game_state)

if __name__ == '__main__':
    app.run(debug=True)
