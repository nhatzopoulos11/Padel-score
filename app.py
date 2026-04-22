from flask import Flask, jsonify, request, render_template_string
import time
from datetime import datetime, timedelta

app = Flask(__name__)

state = {
    "players": {"blue1": "", "blue2": "", "red1": "", "red2": ""},
    "serving_order": [],
    "current_server_index": 0,
    "scores": {"blue": 0, "red": 0},
    "sets": {"blue": 0, "red": 0},
    "set_history": [],
    "games": {"blue": 0, "red": 0},
    "in_tiebreak": False,
    "deuce_count": 0,
    "golden_point": False,
    "phase": "setup",
    "court_end_time": None,
    "history": []
}

def get_remaining_time():
    if state["court_end_time"] is None:
        return 9999
    remaining = state["court_end_time"] - time.time()
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

    if state["in_tiebreak"]:
        state["scores"][team] += 1
        t = state["scores"][team]
        o = state["scores"][other]
        total = t + o
        if total == 1 or (total > 1 and total % 2 == 0):
            advance_server()
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

    if state["golden_point"]:
        win_game(team)
        return

    b = state["scores"]["blue"]
    r = state["scores"]["red"]

    if b == 3 and r == 3:
        state["scores"][team] += 1
        new_b = state["scores"]["blue"]
        new_r = state["scores"]["red"]
        if new_b == 5 or new_r == 5:
            state["scores"] = {"blue": 3, "red": 3}
            state["deuce_count"] += 1
            if state["deuce_count"] >= 2:
                state["golden_point"] = True
        return

    if b == 4 or r == 4:
        if state["scores"][team] < state["scores"][other]:
            state["scores"] = {"blue": 3, "red": 3}
            state["deuce_count"] += 1
            if state["deuce_count"] >= 2:
                state["golden_point"] = True
        else:
            win_game(team)
        return

    state["scores"][team] += 1
    new_score = state["scores"][team]

    if new_score == 4 and state["scores"][other] < 3:
        win_game(team)
        return

    if state["scores"]["blue"] == 3 and state["scores"]["red"] == 3:
        state["deuce_count"] = 1

def win_game(team):
    state["games"][team] += 1
    state["scores"] = {"blue": 0, "red": 0}
    state["deuce_count"] = 0
    state["golden_point"] = False
    advance_server()

    bg = state["games"]["blue"]
    rg = state["games"]["red"]

    if bg == 6 and rg == 6:
        state["in_tiebreak"] = True
        return

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

    end_display = ""
    if state["court_end_time"]:
        dt = datetime.fromtimestamp(state["court_end_time"])
        end_display = dt.strftime("%H:%M")

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
            "minutes": mins,
            "end_time": end_display
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

    # Convert end time string "HH:MM" to timestamp
    end_time_str = data["end_time"]
    now = datetime.now()
    end_hour, end_min = map(int, end_time_str.split(":"))
    end_dt = now.replace(hour=end_hour, minute=end_min, second=0, microsecond=0)
    if end_dt <= now:
        end_dt += timedelta(days=1)
    state["court_end_time"] = end_dt.timestamp()

    state["phase"] = "serving1"
    state["history"] = []
    return jsonify({"ok": True})

@app.route('/api/set_server1', methods=['POST'])
def set_server1():
    data = request.json
    state["serving_order"] = [data["player"]]
    state["phase"] = "serving2"
    return jsonify({"ok": True})

@app.route('/api/set_server2', methods=['POST'])
def set_server2():
    data = request.json
    player = data["player"]
    first_server = state["serving_order"][0]

    blue_players = [state["players"]["blue1"], state["players"]["blue2"]]

    if first_server in blue_players:
        first_partner = (state["players"]["blue2"]
                        if first_server == state["players"]["blue1"]
                        else state["players"]["blue1"])
        second_partner = (state["players"]["red2"]
                         if player == state["players"]["red1"]
                         else state["players"]["red1"])
    else:
        first_partner = (state["players"]["red2"]
                        if first_server == state["players"]["red1"]
                        else state["players"]["red1"])
        second_partner = (state["players"]["blue2"]
                         if player == state["players"]["blue1"]
                         else state["players"]["blue1"])

    state["serving_order"] = [first_server, player, first_partner, second_partner]
    state["current_server_index"] = 0
    state["phase"] = "playing"
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
    state["court_end_time"] = None
    state["history"] = []
    state.pop("winner", None)
    return jsonify({"ok": True})

@app.route('/api/end_times')
def get_end_times():
    """Generate smart end time options based on current time"""
    now = datetime.now()
    options = []

    # Round up to next :00 or :30
    if now.minute < 30:
        start = now.replace(minute=30, second=0, microsecond=0)
    else:
        start = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

    # Generate 6 options every 30 minutes
    for i in range(6):
        slot = start + timedelta(minutes=30 * i)
        options.append(slot.strftime("%H:%M"))

    return jsonify({"options": options})

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
    -webkit-user-select: none;
  }

  /* ===== SCREENS ===== */
  #setup-screen, #serving1-screen, #serving2-screen, #finished-screen {
    display: none;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100vh;
    padding: 20px;
    overflow-y: auto;
  }

  .screen-title {
    font-size: 26px;
    font-weight: bold;
    margin-bottom: 25px;
    color: #FFD700;
    text-align: center;
    letter-spacing: 1px;
  }

  /* ===== SETUP FORM ===== */
  .names-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
    width: 100%;
    max-width: 420px;
    margin-bottom: 25px;
  }

  .team-col { display: flex; flex-direction: column; gap: 10px; }

  .team-label {
    text-align: center;
    font-size: 15px;
    font-weight: bold;
    padding: 6px;
    border-radius: 6px;
  }

  .team-label.blue { background: #1565C0; }
  .team-label.red  { background: #B71C1C; }

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

  /* ===== END TIME PICKER ===== */
  .section-label {
    color: #aaa;
    font-size: 14px;
    margin-bottom: 10px;
    text-align: center;
  }

  .time-slots {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    justify-content: center;
    margin-bottom: 25px;
    max-width: 420px;
  }

  .time-slot-btn {
    padding: 12px 20px;
    border-radius: 10px;
    border: 2px solid #444;
    background: #2a2a4e;
    color: white;
    font-size: 18px;
    font-weight: bold;
    cursor: pointer;
    transition: all 0.2s;
    min-width: 90px;
    text-align: center;
  }

  .time-slot-btn.selected {
    border-color: #FFD700;
    background: #3d3a10;
    color: #FFD700;
  }

  .time-slot-btn:active { transform: scale(0.95); }

  /* ===== BUTTONS ===== */
  .start-btn {
    padding: 15px 50px;
    border-radius: 12px;
    border: none;
    background: #FFD700;
    color: #1a1a2e;
    font-size: 20px;
    font-weight: bold;
    cursor: pointer;
  }

  .start-btn:active { background: #e6c200; transform: scale(0.97); }

  /* ===== SERVE SELECTION ===== */
  .player-btn-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 15px;
    width: 100%;
    max-width: 400px;
    margin-bottom: 25px;
  }

  .player-serve-btn {
    padding: 25px 15px;
    border-radius: 12px;
    border: 3px solid transparent;
    font-size: 20px;
    font-weight: bold;
    cursor: pointer;
    color: white;
    transition: all 0.2s;
    letter-spacing: 1px;
  }

  .player-serve-btn.blue-player { background: #1565C0; }
  .player-serve-btn.red-player  { background: #B71C1C; }
  .player-serve-btn:active { transform: scale(0.95); opacity: 0.85; }

  /* ===== GAME SCREEN ===== */
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
    padding: 10px;
    font-size: 24px;
    font-weight: bold;
    gap: 10px;
    transition: background 0.5s;
    flex-shrink: 0;
  }

  #timer-bar.green  { background: #1b5e20; color: #69f0ae; }
  #timer-bar.yellow { background: #e65100; color: #fff9c4; }
  #timer-bar.red    {
    background: #b71c1c;
    color: white;
    animation: flash 0.8s infinite;
  }

  @keyframes flash {
    0%,100% { background: #b71c1c; }
    50%      { background: #ff1744; }
  }

  .timer-end-label {
    font-size: 14px;
    opacity: 0.8;
    font-weight: normal;
  }

  /* Sets bar */
  #sets-bar {
    background: #0d0d1a;
    padding: 5px 10px;
    text-align: center;
    font-size: 15px;
    color: #aaa;
    min-height: 26px;
    flex-shrink: 0;
  }

  /* Play area */
  #play-area {
    display: flex;
    flex: 1;
    overflow: hidden;
    min-height: 0;
  }

  .team-zone {
    flex: 1;
    display: flex;
    flex-direction: column;
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
    position: relative;
    overflow: hidden;
  }

  .team-zone.blue { background: #0d47a1; }
  .team-zone.red  { background: #b71c1c; }
  .team-zone.blue:active { background: #1565c0; }
  .team-zone.red:active  { background: #c62828; }

  /* Player names - 3x bigger! */
  .players-section {
    padding: 14px 8px 6px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
    pointer-events: none;
    flex-shrink: 0;
  }

  .player-name-row {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .player-name-text {
    font-size: 22px;        /* was ~8px equivalent, now 3x bigger */
    font-weight: 900;
    letter-spacing: 1px;
    text-shadow: 1px 1px 4px rgba(0,0,0,0.6);
    line-height: 1.1;
  }

  .serve-icon {
    font-size: 20px;
    line-height: 1;
  }

  /* Score section - 2x bigger */
  .score-section {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    pointer-events: none;
    gap: 4px;
  }

  .point-score {
    font-size: 110px;     /* was 55px, now 2x */
    font-weight: 900;
    line-height: 1;
    text-shadow: 3px 3px 10px rgba(0,0,0,0.5);
  }

  .point-score.golden { color: #FFD700; }

  .game-score {
    font-size: 52px;      /* was 26px, now 2x */
    font-weight: bold;
    opacity: 0.9;
    line-height: 1;
  }

  .set-score {
    font-size: 36px;      /* was 18px, now 2x */
    font-weight: bold;
    opacity: 0.75;
    line-height: 1;
  }

  /* Divider */
  .divider {
    width: 5px;
    background: #FFD700;
    position: relative;
    z-index: 5;
    flex-shrink: 0;
  }

  .mid-label {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    background: #FFD700;
    color: #1a1a2e;
    padding: 5px 8px;
    border-radius: 8px;
    font-size: 11px;
    font-weight: 900;
    white-space: nowrap;
    text-align: center;
    line-height: 1.3;
    pointer-events: none;
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
    min-height: 50px;
    flex-shrink: 0;
  }

  #undo-bar:active { background: #e6c200; }

  /* ===== FINISHED SCREEN ===== */
  .winner-trophy { font-size: 80px; margin-bottom: 15px; }
  .winner-text   { font-size: 30px; font-weight: bold; margin-bottom: 8px; }
  .winner-names  { font-size: 20px; margin-bottom: 20px; opacity: 0.85; }
  .final-sets    { font-size: 36px; font-weight: bold; margin-bottom: 15px; color: #FFD700; }
  .final-history { font-size: 15px; color: #aaa; margin-bottom: 25px; text-align: center; }

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
</style>
</head>
<body>

<!-- ======= SETUP SCREEN ======= -->
<div id="setup-screen">
  <div class="screen-title">🎾 PADEL SCORE KEEPER</div>

  <div class="names-grid">
    <div class="team-col">
      <div class="team-label blue">🔵 BLUE TEAM</div>
      <input type="text" id="blue1" placeholder="Player 1" maxlength="12">
      <input type="text" id="blue2" placeholder="Player 2" maxlength="12">
    </div>
    <div class="team-col">
      <div class="team-label red">🔴 RED TEAM</div>
      <input type="text" id="red1" placeholder="Player 1" maxlength="12">
      <input type="text" id="red2" placeholder="Player 2" maxlength="12">
    </div>
  </div>

  <div class="section-label">🏟️ Court booking ends at:</div>
  <div class="time-slots" id="time-slots-container">
    <div style="color:#aaa;">Loading times...</div>
  </div>

  <button class="start-btn" onclick="submitSetup()">NEXT →</button>
</div>

<!-- ======= SERVING 1 SCREEN ======= -->
<div id="serving1-screen">
  <div class="screen-title">🎾 WHO SERVES FIRST?</div>
  <div class="player-btn-grid" id="serving1-grid"></div>
</div>

<!-- ======= SERVING 2 SCREEN ======= -->
<div id="serving2-screen">
  <div class="screen-title">🎾 WHO SERVES SECOND?</div>
  <div class="section-label">(from the opposing team)</div>
  <div class="player-btn-grid" id="serving2-grid"></div>
</div>

<!-- ======= GAME SCREEN ======= -->
<div id="game-screen">

  <div id="timer-bar" class="green">
    <span id="timer-icon">⏱️</span>
    <span id="timer-display">--:--</span>
    <span class="timer-end-label" id="timer-end-label"></span>
  </div>

  <div id="sets-bar">-</div>

  <div id="play-area">

    <!-- BLUE -->
    <div class="team-zone blue" onclick="addPoint('blue')">
      <div class="players-section">
        <div class="player-name-row">
          <span class="serve-icon" id="serve-blue1"></span>
          <span class="player-name-text" id="name-blue1">PLAYER 1</span>
        </div>
        <div class="player-name-row">
          <span class="serve-icon" id="serve-blue2"></span>
          <span class="player-name-text" id="name-blue2">PLAYER 2</span>
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
      <div class="mid-label" id="mid-label" style="display:none;"></div>
    </div>

    <!-- RED -->
    <div class="team-zone red" onclick="addPoint('red')">
      <div class="players-section">
        <div class="player-name-row">
          <span class="serve-icon" id="serve-red1"></span>
          <span class="player-name-text" id="name-red1">PLAYER 3</span>
        </div>
        <div class="player-name-row">
          <span class="serve-icon" id="serve-red2"></span>
          <span class="player-name-text" id="name-red2">PLAYER 4</span>
        </div>
      </div>
      <div class="score-section">
        <div class="point-score" id="red-points">0</div>
        <div class="game-score" id="red-games">0</div>
        <div class="set-score" id="red-sets">0</div>
      </div>
    </div>

  </div>

  <div id="undo-bar" onclick="undoPoint()">
    <span>↩️ UNDO</span>
    <span id="undo-count">0 moves</span>
    <span onclick="event.stopPropagation(); resetMatch()"
          style="font-size:13px; opacity:0.7;">🔄 NEW MATCH</span>
  </div>
</div>

<!-- ======= FINISHED SCREEN ======= -->
<div id="finished-screen">
  <div class="winner-trophy">🏆</div>
  <div class="winner-text" id="winner-text">BLUE WINS!</div>
  <div class="winner-names" id="winner-names"></div>
  <div class="final-sets" id="final-sets"></div>
  <div class="final-history" id="final-set-history"></div>
  <button class="new-match-btn" onclick="resetMatch()">🎾 NEW MATCH</button>
</div>

<script>
  let selectedEndTime = null;
  let pollingInterval = null;

  // ===== LOAD END TIMES =====
  function loadEndTimes() {
    fetch('/api/end_times')
      .then(r => r.json())
      .then(data => {
        const container = document.getElementById('time-slots-container');
        container.innerHTML = '';
        data.options.forEach((t, i) => {
          const btn = document.createElement('button');
          btn.className = 'time-slot-btn' + (i === 0 ? ' selected' : '');
          btn.textContent = t;
          if (i === 0) selectedEndTime = t;
          btn.onclick = () => {
            document.querySelectorAll('.time-slot-btn')
              .forEach(b => b.classList.remove('selected'));
            btn.classList.add('selected');
            selectedEndTime = t;
          };
          container.appendChild(btn);
        });
      });
  }

  // ===== SETUP SUBMIT =====
  function submitSetup() {
    const blue1 = document.getElementById('blue1').value.trim();
    const blue2 = document.getElementById('blue2').value.trim();
    const red1  = document.getElementById('red1').value.trim();
    const red2  = document.getElementById('red2').value.trim();

    if (!blue1 || !blue2 || !red1 || !red2) {
      alert('Please enter all 4 player names!');
      return;
    }
    if (!selectedEndTime) {
      alert('Please select court end time!');
      return;
    }

    fetch('/api/setup', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        blue1, blue2, red1, red2,
        end_time: selectedEndTime
      })
    }).then(() => pollState());
  }

  // ===== SERVE SELECTION =====
  function buildServing1Grid(players) {
    const grid = document.getElementById('serving1-grid');
    grid.innerHTML = '';
    [
      {name: players.blue1, team: 'blue'},
      {name: players.blue2, team: 'blue'},
      {name: players.red1,  team: 'red'},
      {name: players.red2,  team: 'red'}
    ].forEach(p => {
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
    const redTeam  = [players.red1,  players.red2];
    const isBlue   = blueTeam.includes(server1);
    const others   = isBlue ? redTeam : blueTeam;
    const color    = isBlue ? 'red'   : 'blue';

    others.forEach(name => {
      const btn = document.createElement('button');
      btn.className = `player-serve-btn ${color}-player`;
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

  // ===== GAME ACTIONS =====
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
      .then(() => {
        loadEndTimes();
        pollState();
      });
  }

  // ===== SCREEN SWITCHER =====
  function showScreen(id) {
    ['setup-screen','serving1-screen','serving2-screen',
     'game-screen','finished-screen'].forEach(s => {
      document.getElementById(s).style.display = 'none';
    });
    document.getElementById(id).style.display = 'flex';
  }

  // ===== TIMER UPDATE =====
  function updateTimer(timer) {
    const bar   = document.getElementById('timer-bar');
    const disp  = document.getElementById('timer-display');
    const icon  = document.getElementById('timer-icon');
    const label = document.getElementById('timer-end-label');

    disp.textContent  = timer.display;
    label.textContent = timer.end_time ? `(ends ${timer.end_time})` : '';

    bar.className = `${timer.color}`;
    bar.id = 'timer-bar';

    if (timer.color === 'red')         icon.textContent = '🚨';
    else if (timer.color === 'yellow') icon.textContent = '⚠️';
    else                               icon.textContent = '⏱️';
  }

  // ===== SERVE INDICATORS =====
  function updateServeIndicators(server, players) {
    ['serve-blue1','serve-blue2','serve-red1','serve-red2']
      .forEach(id => document.getElementById(id).textContent = '');

    if (!server) return;
    if (server === players.blue1) document.getElementById('serve-blue1').textContent = '🎾';
    if (server === players.blue2) document.getElementById('serve-blue2').textContent = '🎾';
    if (server === players.red1)  document.getElementById('serve-red1').textContent  = '🎾';
    if (server === players.red2)  document.getElementById('serve-red2').textContent  = '🎾';
  }

  // ===== SETS HISTORY =====
  function updateSetsBar(history) {
    const el = document.getElementById('sets-bar');
    if (!history || history.length === 0) { el.textContent = '-'; return; }
    el.innerHTML = history.map((s, i) => {
      const tb = s.tiebreak ? ` <small>(${s.tiebreak})</small>` : '';
      return `Set ${i+1}: <span style="color:#64b5f6">${s.blue}</span>` +
             `-<span style="color:#ef9a9a">${s.red}</span>${tb}`;
    }).join('&nbsp;&nbsp;|&nbsp;&nbsp;');
  }

  // ===== MAIN POLL =====
  function pollState() {
    fetch('/api/state')
      .then(r => r.json())
      .then(d => {

        if (d.phase === 'setup') {
          showScreen('setup-screen');
          stopPolling();

        } else if (d.phase === 'serving1') {
          showScreen('serving1-screen');
          buildServing1Grid(d.players);
          startPolling();

        } else if (d.phase === 'serving2') {
          showScreen('serving2-screen');
          buildServing2Grid(d.players, d.serving_order[0]);
          startPolling();

        } else if (d.phase === 'playing') {
          showScreen('game-screen');

          // Names
          document.getElementById('name-blue1').textContent = d.players.blue1;
          document.getElementById('name-blue2').textContent = d.players.blue2;
          document.getElementById('name-red1').textContent  = d.players.red1;
          document.getElementById('name-red2').textContent  = d.players.red2;

          // Serve indicators
          updateServeIndicators(d.current_server, d.players);

          // Points
          const bp = document.getElementById('blue-points');
          const rp = document.getElementById('red-points');
          bp.textContent = d.scores.blue;
          rp.textContent = d.scores.red;
          bp.className = 'point-score' + (d.golden_point ? ' golden' : '');
          rp.className = 'point-score' + (d.golden_point ? ' golden' : '');

          // Games & Sets
          document.getElementById('blue-games').textContent = d.games.blue;
          document.getElementById('red-games').textContent  = d.games.red;
          document.getElementById('blue-sets').textContent  = d.sets.blue;
          document.getElementById('red-sets').textContent   = d.sets.red;

          // Mid label (tiebreak / golden point)
          const midLabel = document.getElementById('mid-label');
          if (d.golden_point) {
            midLabel.style.display = 'block';
            midLabel.textContent = '🥇 GOLDEN POINT';
          } else if (d.in_tiebreak) {
            midLabel.style.display = 'block';
            midLabel.textContent = '⚡ TIEBREAK';
          } else {
            midLabel.style.display = 'none';
          }

          // Sets history bar
          updateSetsBar(d.set_history);

          // Timer
          updateTimer(d.timer);

          // Undo count
          document.getElementById('undo-count').textContent =
            `${d.history_count} moves`;

          startPolling();

        } else if (d.phase === 'finished') {
          showScreen('finished-screen');

          const wt   = d.winner;
          const names = wt === 'blue'
            ? `${d.players.blue1} & ${d.players.blue2}`
            : `${d.players.red1} & ${d.players.red2}`;

          const el = document.getElementById('winner-text');
          el.textContent = `${wt.toUpperCase()} TEAM WINS! 🎉`;
          el.style.color = wt === 'blue' ? '#64b5f6' : '#ef9a9a';

          document.getElementById('winner-names').textContent = names;
          document.getElementById('final-sets').textContent =
            `${d.sets.blue} - ${d.sets.red}`;

          if (d.set_history && d.set_history.length) {
            document.getElementById('final-set-history').textContent =
              d.set_history.map((s, i) => {
                const tb = s.tiebreak ? ` (TB: ${s.tiebreak})` : '';
                return `Set ${i+1}: ${s.blue}-${s.red}${tb}`;
              }).join('  |  ');
          }

          startPolling();
        }
      })
      .catch(e => console.log('poll error:', e));
  }

  function startPolling() {
    if (!pollingInterval)
      pollingInterval = setInterval(pollState, 2000);
  }

  function stopPolling() {
    if (pollingInterval) {
      clearInterval(pollingInterval);
      pollingInterval = null;
    }
  }

  // ===== INIT =====
  loadEndTimes();
  pollState();
  startPolling();
</script>
</body>
</html>
"""

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
