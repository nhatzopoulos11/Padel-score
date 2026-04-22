from flask import Flask, jsonify, request, render_template_string
import time

app = Flask(__name__)

# Game state
state = {
    "players": {"blue1": "", "blue2": "", "red1": "", "red2": ""},
    "serving_order": [],  # [player_name, player_name, player_name, player_name]
    "current_server_index": 0,
    "scores": {"blue": 0, "red": 0},
    "sets": {"blue": 0, "red": 0},
    "set_history": [],
    "games": {"blue": 0, "red": 0},
    "in_tiebreak": False,
    "deuce_count": 0,
    "golden_point": False,
    "phase": "setup",  # setup -> serving1 -> serving2 -> playing
    "court_duration": 90,
    "match_start_time": None,
    "history": []
}

POINTS = ["0", "15", "30", "40", "AD", "GP"]

def get_remaining_time():
    if state["match_start_time"] is None:
        return state["court_duration"] * 60
    elapsed = time.time() - state["match_start_time"]
    remaining = (state["court_duration"] * 60) - elapsed
    return max(0, remaining)

def get_timer_color(remaining_seconds):
    minutes = remaining_seconds / 60
    if minutes > 10:
        return "green"
    elif minutes > 5:
        return "yellow"
    else:
        return "red"

def get_current_server():
    if not state["serving_order"]:
        return ""
    idx = state["current_server_index"] % len(state["serving_order"])
    return state["serving_order"][idx]

def advance_server():
    state["current_server_index"] += 1

def save_history():
    import copy
    state["history"].append(copy.deepcopy({
        "scores": state["scores"],
        "sets": state["sets"],
        "set_history": state["set_history"],
        "games": state["games"],
        "in_tiebreak": state["in_tiebreak"],
        "deuce_count": state["deuce_count"],
        "golden_point": state["golden_point"],
        "current_server_index": state["current_server_index"]
    }))
    if len(state["history"]) > 50:
        state["history"].pop(0)

def add_point(team):
    save_history()

    other = "red" if team == "blue" else "blue"

    # TIEBREAK LOGIC
    if state["in_tiebreak"]:
        state["scores"][team] += 1
        t = state["scores"][team]
        o = state["scores"][other]

        # Serve changes every 2 points in tiebreak (after first point)
        total = t + o
        if total == 1 or (total > 1 and total % 2 == 0):
            advance_server()

        # Win tiebreak
        if t >= 7 and t - o >= 2:
            state["sets"][team] += 1
            state["set_history"].append({
                "blue": state["games"]["blue"],
                "red": state["games"]["red"],
                "tiebreak": f"{state['scores']['blue']}-{state['scores']['red']}"
            })
            state["scores"] = {"blue": 0, "red": 0}
            state["games"] = {"blue": 0, "red": 0}
            state["in_tiebreak"] = False
            state["deuce_count"] = 0
            state["golden_point"] = False
            advance_server()
            check_match_win()
        return

    # NORMAL GAME LOGIC
    b = state["scores"]["blue"]
    r = state["scores"]["red"]

    # GOLDEN POINT
    if state["golden_point"]:
        # One point wins the game
        win_game(team)
        return

    # Both at 40 (deuce territory)
    if b == 3 and r == 3:
        # Already at deuce - handle advantage
        state["scores"][team] += 1
        new_b = state["scores"]["blue"]
        new_r = state["scores"]["red"]

        if new_b == 5 or new_r == 5:
            # Someone had AD, other team scores -> back to deuce
            state["scores"] = {"blue": 3, "red": 3}
            state["deuce_count"] += 1
            # Check if this is 2nd deuce -> golden point
            if state["deuce_count"] >= 2:
                state["golden_point"] = True
        elif new_b == 4 or new_r == 4:
            # First advantage - do nothing, score shows AD
            pass
        return

    # AD situation (one player at 4)
    if b == 4 or r == 4:
        if state["scores"][team] < state["scores"][other]:
            # Other team had AD, scoring team ties -> back to deuce
            state["scores"] = {"blue": 3, "red": 3}
            state["deuce_count"] += 1
            if state["deuce_count"] >= 2:
                state["golden_point"] = True
        else:
            # Team with AD scores again -> win game
            win_game(team)
        return

    # Normal point progression
    state["scores"][team] += 1
    new_score = state["scores"][team]

    # Win game at 4 (which maps to winning after 40)
    if new_score == 4 and state["scores"][other] < 3:
        win_game(team)
        return

    # 40-40 first time
    if state["scores"]["blue"] == 3 and state["scores"]["red"] == 3:
        state["deuce_count"] = 1

def win_game(team):
    other = "red" if team == "blue" else "blue"
    state["games"][team] += 1
    state["scores"] = {"blue": 0, "red": 0}
    state["deuce_count"] = 0
    state["golden_point"] = False
    advance_server()

    bg = state["games"]["blue"]
    rg = state["games"]["red"]

    # Check tiebreak at 6-6
    if bg == 6 and rg == 6:
        state["in_tiebreak"] = True
        return

    # Win set
    if (bg >= 6 or rg >= 6) and abs(bg - rg) >= 2:
        state["sets"][team] += 1
        state["set_history"].append({"blue": bg, "red": rg})
        state["games"] = {"blue": 0, "red": 0}
        state["in_tiebreak"] = False
        check_match_win()

def check_match_win():
    if state["sets"]["blue"] >= 2:
        state["phase"] = "finished"
        state["winner"] = "blue"
    elif state["sets"]["red"] >= 2:
        state["phase"] = "finished"
        state["winner"] = "red"

def get_display_score(team):
    other = "red" if team == "blue" else "blue"
    s = state["scores"][team]
    o = state["scores"][other]

    if state["in_tiebreak"]:
        return str(s)

    if state["golden_point"]:
        return "GP"

    point_map = {0: "0", 1: "15", 2: "30", 3: "40"}

    if s == 4:
        return "AD"
    if o == 4:
        return "  "

    return point_map.get(s, str(s))

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/state')
def get_state():
    remaining = get_remaining_time()
    color = get_timer_color(remaining)
    mins = int(remaining // 60)
    secs = int(remaining % 60)

    return jsonify({
        "phase": state["phase"],
        "players": state["players"],
        "serving_order": state["serving_order"],
        "current_server": get_current_server(),
        "scores": {
            "blue": get_display_score("blue"),
            "red": get_display_score("red")
        },
        "games": state["games"],
        "sets": state["sets"],
        "set_history": state["set_history"],
        "in_tiebreak": state["in_tiebreak"],
        "golden_point": state["golden_point"],
        "deuce_count": state["deuce_count"],
        "timer": {
            "remaining_seconds": remaining,
            "display": f"{mins:02d}:{secs:02d}",
            "color": color,
            "minutes": mins
        },
        "winner": state.get("winner", None),
        "history_count": len(state["history"])
    })

@app.route('/api/setup', methods=['POST'])
def setup():
    data = request.json
    state["players"]["blue1"] = data["blue1"].upper()
    state["players"]["blue2"] = data["blue2"].upper()
    state["players"]["red1"] = data["red1"].upper()
    state["players"]["red2"] = data["red2"].upper()
    state["court_duration"] = int(data["duration"])
    state["phase"] = "serving1"
    state["history"] = []
    return jsonify({"ok": True})

@app.route('/api/set_server1', methods=['POST'])
def set_server1():
    data = request.json
    player = data["player"]
    state["serving_order"] = [player]
    state["phase"] = "serving2"
    return jsonify({"ok": True})

@app.route('/api/set_server2', methods=['POST'])
def set_server2():
    data = request.json
    player = data["player"]

    first_server = state["serving_order"][0]

    # Determine teams
    blue_players = [state["players"]["blue1"], state["players"]["blue2"]]
    red_players = [state["players"]["red1"], state["players"]["red2"]]

    if first_server in blue_players:
        first_team = "blue"
        second_team = "red"
    else:
        first_team = "red"
        second_team = "blue"

    # First server's partner
    if first_server == state["players"]["blue1"]:
        first_partner = state["players"]["blue2"]
    elif first_server == state["players"]["blue2"]:
        first_partner = state["players"]["blue1"]
    elif first_server == state["players"]["red1"]:
        first_partner = state["players"]["red2"]
    else:
        first_partner = state["players"]["red1"]

    # Second server's partner
    if player == state["players"]["blue1"]:
        second_partner = state["players"]["blue2"]
    elif player == state["players"]["blue2"]:
        second_partner = state["players"]["blue1"]
    elif player == state["players"]["red1"]:
        second_partner = state["players"]["red2"]
    else:
        second_partner = state["players"]["red1"]

    # Rotation: server1, server2, partner1, partner2
    state["serving_order"] = [first_server, player, first_partner, second_partner]
    state["current_server_index"] = 0
    state["phase"] = "playing"
    state["match_start_time"] = time.time()
    state["scores"] = {"blue": 0, "red": 0}
    state["games"] = {"blue": 0, "red": 0}
    state["sets"] = {"blue": 0, "red": 0}
    state["set_history"] = []
    state["in_tiebreak"] = False
    state["deuce_count"] = 0
    state["golden_point"] = False
    return jsonify({"ok": True})

@app.route('/api/point/<team>', methods=['POST'])
def add_point_route(team):
    if state["phase"] == "playing":
        add_point(team)
    return jsonify({"ok": True})

@app.route('/api/undo', methods=['POST'])
def undo():
    if state["history"]:
        last = state["history"].pop()
        state["scores"] = last["scores"]
        state["sets"] = last["sets"]
        state["set_history"] = last["set_history"]
        state["games"] = last["games"]
        state["in_tiebreak"] = last["in_tiebreak"]
        state["deuce_count"] = last["deuce_count"]
        state["golden_point"] = last["golden_point"]
        state["current_server_index"] = last["current_server_index"]
        state["phase"] = "playing"
    return jsonify({"ok": True})

@app.route('/api/reset', methods=['POST'])
def reset():
    state["players"] = {"blue1": "", "blue2": "", "red1": "", "red2": ""}
    state["serving_order"] = []
    state["current_server_index"] = 0
    state["scores"] = {"blue": 0, "red": 0}
    state["sets"] = {"blue": 0, "red": 0}
    state["set_history"] = []
    state["games"] = {"blue": 0, "red": 0}
    state["in_tiebreak"] = False
    state["deuce_count"] = 0
    state["golden_point"] = False
    state["phase"] = "setup"
    state["court_duration"] = 90
    state["match_start_time"] = None
    state["history"] = []
    state.pop("winner", None)
    return jsonify({"ok": True})

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>Padel Score Keeper</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    font-family: 'Arial', sans-serif;
    background: #1a1a2e;
    color: white;
    height: 100vh;
    overflow: hidden;
    user-select: none;
  }

  /* ========== SETUP SCREEN ========== */
  #setup-screen, #serving1-screen, #serving2-screen, #finished-screen {
    display: none;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100vh;
    padding: 20px;
    background: #1a1a2e;
  }

  .screen-title {
    font-size: 28px;
    font-weight: bold;
    margin-bottom: 30px;
    color: #FFD700;
    text-align: center;
  }

  .names-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 15px;
    width: 100%;
    max-width: 400px;
    margin-bottom: 25px;
  }

  .team-col {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .team-label {
    text-align: center;
    font-size: 14px;
    font-weight: bold;
    padding: 5px;
    border-radius: 5px;
    margin-bottom: 5px;
  }

  .team-label.blue { background: #1565C0; }
  .team-label.red { background: #B71C1C; }

  input[type="text"] {
    width: 100%;
    padding: 12px;
    border-radius: 8px;
    border: 2px solid #444;
    background: #2a2a4e;
    color: white;
    font-size: 16px;
    text-align: center;
    text-transform: uppercase;
  }

  input[type="text"]:focus {
    outline: none;
    border-color: #FFD700;
  }

  .duration-row {
    display: flex;
    gap: 10px;
    margin-bottom: 25px;
    flex-wrap: wrap;
    justify-content: center;
  }

  .duration-btn {
    padding: 10px 20px;
    border-radius: 8px;
    border: 2px solid #444;
    background: #2a2a4e;
    color: white;
    font-size: 16px;
    cursor: pointer;
    transition: all 0.2s;
  }

  .duration-btn.selected {
    border-color: #FFD700;
    background: #3a3a1e;
    color: #FFD700;
  }

  .start-btn {
    padding: 15px 50px;
    border-radius: 12px;
    border: none;
    background: #FFD700;
    color: #1a1a2e;
    font-size: 20px;
    font-weight: bold;
    cursor: pointer;
    transition: all 0.2s;
  }

  .start-btn:hover { background: #FFC000; }

  /* ========== SERVING SCREENS ========== */
  .player-btn-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 15px;
    width: 100%;
    max-width: 400px;
    margin-bottom: 25px;
  }

  .player-serve-btn {
    padding: 20px;
    border-radius: 12px;
    border: 3px solid #444;
    font-size: 18px;
    font-weight: bold;
    cursor: pointer;
    transition: all 0.2s;
    color: white;
  }

  .player-serve-btn.blue-player { background: #1565C0; border-color: #1565C0; }
  .player-serve-btn.red-player { background: #B71C1C; border-color: #B71C1C; }
  .player-serve-btn:active { transform: scale(0.95); }

  /* ========== GAME SCREEN ========== */
  #game-screen {
    display: none;
    flex-direction: column;
    height: 100vh;
  }

  /* Timer bar */
  #timer-bar {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 8px;
    font-size: 22px;
    font-weight: bold;
    transition: background 0.5s, color 0.5s;
    gap: 8px;
  }

  #timer-bar.green { background: #1b5e20; color: #69f0ae; }
  #timer-bar.yellow { background: #f57f17; color: #fff9c4; }
  #timer-bar.red { background: #b71c1c; color: white; animation: flash 1s infinite; }

  @keyframes flash {
    0%, 100% { background: #b71c1c; }
    50% { background: #ff1744; }
  }

  /* Sets history bar */
  #sets-bar {
    display: flex;
    align-items: center;
    justify-content: center;
    background: #0d0d1a;
    padding: 5px;
    gap: 15px;
    font-size: 14px;
    color: #aaa;
    min-height: 28px;
  }

  .set-score-item {
    display: flex;
    gap: 5px;
  }

  .set-score-blue { color: #64b5f6; }
  .set-score-red { color: #ef9a9a; }

  /* Main play area */
  #play-area {
    display: flex;
    flex: 1;
    overflow: hidden;
  }

  .team-zone {
    flex: 1;
    display: flex;
    flex-direction: column;
    position: relative;
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
  }

  .team-zone.blue { background: #0d47a1; }
  .team-zone.red { background: #b71c1c; }
  .team-zone.blue:active { background: #1565c0; }
  .team-zone.red:active { background: #c62828; }

  /* Players names section */
  .players-section {
    padding: 12px 8px 8px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
    pointer-events: none;
  }

  .player-name-row {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 15px;
    font-weight: bold;
  }

  .serve-indicator {
    font-size: 18px;
    line-height: 1;
  }

  /* Score section */
  .score-section {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    pointer-events: none;
  }

  .point-score {
    font-size: 80px;
    font-weight: 900;
    line-height: 1;
    text-shadow: 2px 2px 8px rgba(0,0,0,0.5);
  }

  .point-score.golden { color: #FFD700; }

  .game-score {
    font-size: 36px;
    font-weight: bold;
    margin-top: 8px;
    opacity: 0.9;
  }

  .set-score {
    font-size: 24px;
    font-weight: bold;
    opacity: 0.8;
  }

  /* Tiebreak label */
  .tiebreak-label {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    background: #FFD700;
    color: #1a1a2e;
    padding: 4px 10px;
    border-radius: 10px;
    font-size: 12px;
    font-weight: bold;
    pointer-events: none;
    z-index: 10;
    white-space: nowrap;
  }

  /* Golden point label */
  .golden-label {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    background: #FFD700;
    color: #1a1a2e;
    padding: 4px 10px;
    border-radius: 10px;
    font-size: 11px;
    font-weight: bold;
    pointer-events: none;
    z-index: 10;
    white-space: nowrap;
    text-align: center;
  }

  /* Divider */
  .divider {
    width: 4px;
    background: #FFD700;
    position: relative;
    z-index: 5;
  }

  /* Undo bar */
  #undo-bar {
    background: #FFD700;
    color: #1a1a2e;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 20px;
    cursor: pointer;
    font-weight: bold;
    font-size: 16px;
    min-height: 48px;
  }

  #undo-bar:active { background: #FFC000; }

  /* Finished screen */
  #finished-screen {
    background: #1a1a2e;
  }

  .winner-trophy { font-size: 80px; margin-bottom: 20px; }
  .winner-text { font-size: 32px; font-weight: bold; margin-bottom: 10px; }
  .winner-names { font-size: 22px; margin-bottom: 30px; opacity: 0.8; }
  .final-sets { font-size: 28px; font-weight: bold; margin-bottom: 30px; color: #FFD700; }

  .new-match-btn {
    padding: 15px 40px;
    border-radius: 12px;
    border: none;
    background: #FFD700;
    color: #1a1a2e;
    font-size: 20px;
    font-weight: bold;
    cursor: pointer;
  }

  /* Custom duration input */
  #custom-duration-input {
    display: none;
    padding: 10px;
    border-radius: 8px;
    border: 2px solid #FFD700;
    background: #2a2a4e;
    color: white;
    font-size: 16px;
    text-align: center;
    width: 120px;
    margin-top: 10px;
  }
</style>
</head>
<body>

<!-- ========== SETUP SCREEN ========== -->
<div id="setup-screen">
  <div class="screen-title">🎾 PADEL SCORE KEEPER</div>

  <div class="names-grid">
    <div class="team-col">
      <div class="team-label blue">BLUE TEAM</div>
      <input type="text" id="blue1" placeholder="Player 1" maxlength="12">
      <input type="text" id="blue2" placeholder="Player 2" maxlength="12">
    </div>
    <div class="team-col">
      <div class="team-label red">RED TEAM</div>
      <input type="text" id="red1" placeholder="Player 1" maxlength="12">
      <input type="text" id="red2" placeholder="Player 2" maxlength="12">
    </div>
  </div>

  <div style="color:#aaa; font-size:14px; margin-bottom:10px;">Court Booking Duration:</div>
  <div class="duration-row">
    <button class="duration-btn" onclick="selectDuration(60, this)">60 min</button>
    <button class="duration-btn selected" onclick="selectDuration(90, this)">90 min</button>
    <button class="duration-btn" onclick="selectDuration(120, this)">120 min</button>
    <button class="duration-btn" onclick="selectDuration('custom', this)">Custom</button>
  </div>
  <input type="number" id="custom-duration-input" placeholder="Minutes" min="10" max="300">

  <button class="start-btn" onclick="submitSetup()">NEXT →</button>
</div>

<!-- ========== SERVING 1 SCREEN ========== -->
<div id="serving1-screen">
  <div class="screen-title">🎾 WHO SERVES FIRST?</div>
  <div class="player-btn-grid" id="serving1-grid"></div>
</div>

<!-- ========== SERVING 2 SCREEN ========== -->
<div id="serving2-screen">
  <div class="screen-title" id="serving2-title">WHO SERVES SECOND?</div>
  <div style="color:#aaa; font-size:14px; margin-bottom:20px; text-align:center;">(from the other team)</div>
  <div class="player-btn-grid" id="serving2-grid"></div>
</div>

<!-- ========== GAME SCREEN ========== -->
<div id="game-screen">

  <!-- Timer Bar -->
  <div id="timer-bar" class="green">
    <span>⏱️</span>
    <span id="timer-display">90:00</span>
    <span id="timer-label">remaining</span>
  </div>

  <!-- Sets History Bar -->
  <div id="sets-bar">
    <span style="color:#666;">Sets: </span>
    <span id="sets-history-display">-</span>
  </div>

  <!-- Play Area -->
  <div id="play-area">

    <!-- BLUE ZONE -->
    <div class="team-zone blue" id="blue-zone" onclick="addPoint('blue')">
      <div class="players-section">
        <div class="player-name-row">
          <span class="serve-indicator" id="serve-blue1"></span>
          <span id="name-blue1">PLAYER 1</span>
        </div>
        <div class="player-name-row">
          <span class="serve-indicator" id="serve-blue2"></span>
          <span id="name-blue2">PLAYER 2</span>
        </div>
      </div>
      <div class="score-section">
        <div class="point-score" id="blue-points">0</div>
        <div class="game-score" id="blue-games">0</div>
        <div class="set-score" id="blue-sets">0</div>
      </div>
    </div>

    <!-- DIVIDER -->
    <div class="divider">
      <div id="tiebreak-label" class="tiebreak-label" style="display:none;">TIEBREAK</div>
      <div id="golden-label" class="golden-label" style="display:none;">🥇<br>GOLDEN<br>POINT</div>
    </div>

    <!-- RED ZONE -->
    <div class="team-zone red" id="red-zone" onclick="addPoint('red')">
      <div class="players-section">
        <div class="player-name-row">
          <span class="serve-indicator" id="serve-red1"></span>
          <span id="name-red1">PLAYER 3</span>
        </div>
        <div class="player-name-row">
          <span class="serve-indicator" id="serve-red2"></span>
          <span id="name-red2">PLAYER 4</span>
        </div>
      </div>
      <div class="score-section">
        <div class="point-score" id="red-points">0</div>
        <div class="game-score" id="red-games">0</div>
        <div class="set-score" id="red-sets">0</div>
      </div>
    </div>

  </div>

  <!-- Undo Bar -->
  <div id="undo-bar" onclick="undoPoint()">
    <span>↩️ UNDO</span>
    <span id="undo-count">0 moves</span>
    <span onclick="event.stopPropagation(); resetMatch()" style="font-size:13px; opacity:0.7;">🔄 NEW MATCH</span>
  </div>
</div>

<!-- ========== FINISHED SCREEN ========== -->
<div id="finished-screen">
  <div class="winner-trophy">🏆</div>
  <div class="winner-text" id="winner-text">BLUE TEAM WINS!</div>
  <div class="winner-names" id="winner-names"></div>
  <div class="final-sets" id="final-sets"></div>
  <div id="final-set-history" style="margin-bottom:25px; color:#aaa; font-size:16px;"></div>
  <button class="new-match-btn" onclick="resetMatch()">🎾 NEW MATCH</button>
</div>

<script>
let selectedDuration = 90;
let pollingInterval = null;

function selectDuration(val, btn) {
  document.querySelectorAll('.duration-btn').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');
  const customInput = document.getElementById('custom-duration-input');
  if (val === 'custom') {
    customInput.style.display = 'block';
    selectedDuration = null;
  } else {
    customInput.style.display = 'none';
    selectedDuration = val;
  }
}

function submitSetup() {
  const blue1 = document.getElementById('blue1').value.trim();
  const blue2 = document.getElementById('blue2').value.trim();
  const red1 = document.getElementById('red1').value.trim();
  const red2 = document.getElementById('red2').value.trim();

  if (!blue1 || !blue2 || !red1 || !red2) {
    alert('Please enter all 4 player names!');
    return;
  }

  let duration = selectedDuration;
  if (!duration) {
    duration = parseInt(document.getElementById('custom-duration-input').value);
    if (!duration || duration < 10) {
      alert('Please enter a valid duration!');
      return;
    }
  }

  fetch('/api/setup', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({blue1, blue2, red1, red2, duration})
  }).then(() => pollState());
}

function buildServing1Grid(players) {
  const grid = document.getElementById('serving1-grid');
  grid.innerHTML = '';
  const allPlayers = [
    {name: players.blue1, team: 'blue'},
    {name: players.blue2, team: 'blue'},
    {name: players.red1, team: 'red'},
    {name: players.red2, team: 'red'}
  ];
  allPlayers.forEach(p => {
    const btn = document.createElement('button');
    btn.className = `player-serve-btn ${p.team}-player`;
    btn.textContent = p.name;
    btn.onclick = () => setServer1(p.name);
    grid.appendChild(btn);
  });
}

function buildServing2Grid(players, server1) {
  const grid = document.getElementById('serving2-grid');
  grid.innerHTML = '';

  const blueTeam = [players.blue1, players.blue2];
  const redTeam = [players.red1, players.red2];

  // Show only players from the OTHER team
  const otherTeamPlayers = blueTeam.includes(server1) ? redTeam : blueTeam;
  const otherTeamColor = blueTeam.includes(server1) ? 'red' : 'blue';

  otherTeamPlayers.forEach(name => {
    const btn = document.createElement('button');
    btn.className = `player-serve-btn ${otherTeamColor}-player`;
    btn.textContent = name;
    btn.onclick = () => setServer2(name);
    grid.appendChild(btn);
  });
}

function setServer1(player) {
  fetch('/api/set_server1', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({player})
  }).then(() => pollState());
}

function setServer2(player) {
  fetch('/api/set_server2', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({player})
  }).then(() => pollState());
}

function addPoint(team) {
  fetch(`/api/point/${team}`, {method: 'POST'})
    .then(() => pollState());
}

function undoPoint() {
  fetch('/api/undo', {method: 'POST'})
    .then(() => pollState());
}

function resetMatch() {
  fetch('/api/reset', {method: 'POST'})
    .then(() => pollState());
}

function showScreen(name) {
  ['setup-screen', 'serving1-screen', 'serving2-screen', 'game-screen', 'finished-screen'].forEach(id => {
    document.getElementById(id).style.display = 'none';
  });
  document.getElementById(name).style.display = 'flex';
}

function updateTimer(timer) {
  const bar = document.getElementById('timer-bar');
  const display = document.getElementById('timer-display');

  display.textContent = timer.display;
  bar.className = `timer-bar ${timer.color}`;
  bar.id = 'timer-bar';

  // Update icon based on color
  const icon = bar.querySelector('span:first-child');
  if (timer.color === 'red') icon.textContent = '🚨';
  else if (timer.color === 'yellow') icon.textContent = '⚠️';
  else icon.textContent = '⏱️';
}

function updateServeIndicators(currentServer, players) {
  // Clear all
  ['serve-blue1', 'serve-blue2', 'serve-red1', 'serve-red2'].forEach(id => {
    document.getElementById(id).textContent = '';
  });

  if (!currentServer) return;

  if (currentServer === players.blue1) document.getElementById('serve-blue1').textContent = '🎾';
  else if (currentServer === players.blue2) document.getElementById('serve-blue2').textContent = '🎾';
  else if (currentServer === players.red1) document.getElementById('serve-red1').textContent = '🎾';
  else if (currentServer === players.red2) document.getElementById('serve-red2').textContent = '🎾';
}

function updateSetsHistory(setHistory) {
  const el = document.getElementById('sets-history-display');
  if (!setHistory || setHistory.length === 0) {
    el.textContent = '-';
    return;
  }
  const parts = setHistory.map(s => {
    const tb = s.tiebreak ? ` (${s.tiebreak})` : '';
    return `<span class="set-score-blue">${s.blue}</span>-<span class="set-score-red">${s.red}</span>${tb}`;
  });
  el.innerHTML = parts.join('  |  ');
}

let lastState = null;

function pollState() {
  fetch('/api/state')
    .then(r => r.json())
    .then(data => {
      lastState = data;

      if (data.phase === 'setup') {
        showScreen('setup-screen');
        stopPolling();

      } else if (data.phase === 'serving1') {
        showScreen('serving1-screen');
        buildServing1Grid(data.players);
        startPolling();

      } else if (data.phase === 'serving2') {
        showScreen('serving2-screen');
        buildServing2Grid(data.players, data.serving_order[0]);
        document.getElementById('serving2-title').textContent =
          `${data.serving_order[0]} serves first.\nWHO SERVES SECOND?`;
        startPolling();

      } else if (data.phase === 'playing') {
        showScreen('game-screen');

        // Names
        document.getElementById('name-blue1').textContent = data.players.blue1;
        document.getElementById('name-blue2').textContent = data.players.blue2;
        document.getElementById('name-red1').textContent = data.players.red1;
        document.getElementById('name-red2').textContent = data.players.red2;

        // Serve indicators
        updateServeIndicators(data.current_server, data.players);

        // Scores
        const bluePoints = document.getElementById('blue-points');
        const redPoints = document.getElementById('red-points');
        bluePoints.textContent = data.scores.blue;
        redPoints.textContent = data.scores.red;

        if (data.golden_point) {
          bluePoints.classList.add('golden');
          redPoints.classList.add('golden');
        } else {
          bluePoints.classList.remove('golden');
          redPoints.classList.remove('golden');
        }

        document.getElementById('blue-games').textContent = data.games.blue;
        document.getElementById('red-games').textContent = data.games.red;
        document.getElementById('blue-sets').textContent = data.sets.blue;
        document.getElementById('red-sets').textContent = data.sets.red;

        // Tiebreak / Golden labels
        document.getElementById('tiebreak-label').style.display =
          data.in_tiebreak ? 'block' : 'none';
        document.getElementById('golden-label').style.display =
          data.golden_point ? 'block' : 'none';

        // Sets history
        updateSetsHistory(data.set_history);

        // Timer
        updateTimer(data.timer);

        // Undo count
        document.getElementById('undo-count').textContent = `${data.history_count} moves`;

        startPolling();

      } else if (data.phase === 'finished') {
        showScreen('finished-screen');
        stopPolling();

        const winnerTeam = data.winner;
        const winnerNames = winnerTeam === 'blue'
          ? `${data.players.blue1} & ${data.players.blue2}`
          : `${data.players.red1} & ${data.players.red2}`;

        document.getElementById('winner-text').textContent =
          `${winnerTeam.toUpperCase()} TEAM WINS! 🎉`;
        document.getElementById('winner-text').style.color =
          winnerTeam === 'blue' ? '#64b5f6' : '#ef9a9a';
        document.getElementById('winner-names').textContent = winnerNames;
        document.getElementById('final-sets').textContent =
          `${data.sets.blue} - ${data.sets.red}`;

        // Set history
        const histEl = document.getElementById('final-set-history');
        if (data.set_history && data.set_history.length > 0) {
          histEl.innerHTML = data.set_history.map((s, i) => {
            const tb = s.tiebreak ? ` (TB: ${s.tiebreak})` : '';
            return `Set ${i+1}: ${s.blue}-${s.red}${tb}`;
          }).join(' | ');
        }

        startPolling();
      }
    })
    .catch(err => console.log('Poll error:', err));
}

function startPolling() {
  if (!pollingInterval) {
    pollingInterval = setInterval(pollState, 2000);
  }
}

function stopPolling() {
  if (pollingInterval) {
    clearInterval(pollingInterval);
    pollingInterval = null;
  }
}

// Start
pollState();
startPolling();
</script>
</body>
</html>
"""

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
