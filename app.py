from flask import Flask, jsonify, request, render_template_string
from flask_cors import CORS
import json
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Game State
state = {
    "team_a": "Team A",
    "team_b": "Team B",
    "points_a": 0,
    "points_b": 0,
    "games_a": 0,
    "games_b": 0,
    "sets_a": 0,
    "sets_b": 0,
    "sets_history": [],
    "serving": "a",
    "match_active": False,
    "match_over": False,
    "winner": None,
    "last_updated": None
}

history = []

POINTS = [0, 15, 30, 40]

def reset_points():
    state["points_a"] = 0
    state["points_b"] = 0

def reset_games():
    state["games_a"] = 0
    state["games_b"] = 0
    reset_points()

def check_game_won():
    a = state["points_a"]
    b = state["points_b"]
    
    # Both at 40 (index 3) = deuce
    if a == 3 and b == 3:
        return None
    # Advantage A
    if a == 4 and b == 3:
        state["games_a"] += 1
        state["serving"] = "b" if state["serving"] == "a" else "a"
        record_sets()
        reset_points()
        return "a"
    # Advantage B
    if a == 3 and b == 4:
        state["games_b"] += 1
        state["serving"] = "b" if state["serving"] == "a" else "a"
        record_sets()
        reset_points()
        return "b"
    # Normal win
    if a >= 4:
        state["games_a"] += 1
        state["serving"] = "b" if state["serving"] == "a" else "a"
        record_sets()
        reset_points()
        return "a"
    if b >= 4:
        state["games_b"] += 1
        state["serving"] = "b" if state["serving"] == "a" else "a"
        record_sets()
        reset_points()
        return "b"
    return None

def record_sets():
    ga = state["games_a"]
    gb = state["games_b"]
    
    # Win set at 6 with 2 game lead
    if ga >= 6 and ga - gb >= 2:
        state["sets_a"] += 1
        state["sets_history"].append({"a": ga, "b": gb})
        reset_games()
        check_match_won()
    elif gb >= 6 and gb - ga >= 2:
        state["sets_b"] += 1
        state["sets_history"].append({"a": ga, "b": gb})
        reset_games()
        check_match_won()
    # Tiebreak at 6-6
    elif ga == 7 and gb == 6:
        state["sets_a"] += 1
        state["sets_history"].append({"a": ga, "b": gb})
        reset_games()
        check_match_won()
    elif gb == 7 and ga == 6:
        state["sets_b"] += 1
        state["sets_history"].append({"a": ga, "b": gb})
        reset_games()
        check_match_won()

def check_match_won():
    if state["sets_a"] >= 2:
        state["match_over"] = True
        state["match_active"] = False
        state["winner"] = state["team_a"]
    elif state["sets_b"] >= 2:
        state["match_over"] = True
        state["match_active"] = False
        state["winner"] = state["team_b"]

def get_point_label(p):
    labels = {0: "0", 1: "15", 2: "30", 3: "40", 4: "ADV"}
    return labels.get(p, "0")

@app.route("/")
def index():
    return render_template_string(MAIN_HTML)

@app.route("/api/score")
def get_score():
    return jsonify({
        "team_a": state["team_a"],
        "team_b": state["team_b"],
        "points_a": get_point_label(state["points_a"]),
        "points_b": get_point_label(state["points_b"]),
        "games_a": state["games_a"],
        "games_b": state["games_b"],
        "sets_a": state["sets_a"],
        "sets_b": state["sets_b"],
        "sets_history": state["sets_history"],
        "serving": state["serving"],
        "match_active": state["match_active"],
        "match_over": state["match_over"],
        "winner": state["winner"],
        "last_updated": state["last_updated"]
    })

@app.route("/api/point/<team>", methods=["POST"])
def add_point(team):
    if not state["match_active"]:
        return jsonify({"error": "Match not active"}), 400
    
    # Save history for undo
    history.append(json.dumps(state.copy()))
    
    if team == "a":
        state["points_a"] += 1
        # Handle deuce
        if state["points_a"] == 3 and state["points_b"] == 4:
            state["points_b"] = 3
        check_game_won()
    elif team == "b":
        state["points_b"] += 1
        if state["points_b"] == 3 and state["points_a"] == 4:
            state["points_a"] = 3
        check_game_won()
    
    state["last_updated"] = datetime.now().isoformat()
    return jsonify({"success": True})

@app.route("/api/undo", methods=["POST"])
def undo():
    if not history:
        return jsonify({"error": "Nothing to undo"}), 400
    last = json.loads(history.pop())
    state.update(last)
    return jsonify({"success": True})

@app.route("/api/start", methods=["POST"])
def start_match():
    data = request.json or {}
    global history
    history = []
    
    state["team_a"] = data.get("team_a", "Team A")
    state["team_b"] = data.get("team_b", "Team B")
    state["points_a"] = 0
    state["points_b"] = 0
    state["games_a"] = 0
    state["games_b"] = 0
    state["sets_a"] = 0
    state["sets_b"] = 0
    state["sets_history"] = []
    state["serving"] = data.get("serving", "a")
    state["match_active"] = True
    state["match_over"] = False
    state["winner"] = None
    state["last_updated"] = datetime.now().isoformat()
    
    return jsonify({"success": True})

@app.route("/api/reset", methods=["POST"])
def reset_match():
    global history
    history = []
    state["match_active"] = False
    state["match_over"] = False
    state["winner"] = None
    state["points_a"] = 0
    state["points_b"] = 0
    state["games_a"] = 0
    state["games_b"] = 0
    state["sets_a"] = 0
    state["sets_b"] = 0
    state["sets_history"] = []
    state["last_updated"] = datetime.now().isoformat()
    return jsonify({"success": True})

MAIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>Padel Score</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  
  body {
    font-family: 'Arial', sans-serif;
    background: #0a0a0a;
    color: white;
    height: 100dvh;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  /* SETUP SCREEN */
  #setup-screen {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100dvh;
    padding: 20px;
    gap: 16px;
    background: linear-gradient(135deg, #0a0a0a, #1a1a2e);
  }

  #setup-screen h1 {
    font-size: 2rem;
    color: #4ade80;
    margin-bottom: 10px;
  }

  #setup-screen input {
    width: 100%;
    max-width: 300px;
    padding: 14px;
    font-size: 1.1rem;
    border-radius: 12px;
    border: 2px solid #333;
    background: #1a1a1a;
    color: white;
    text-align: center;
  }

  #setup-screen input:focus {
    outline: none;
    border-color: #4ade80;
  }

  .serve-select {
    display: flex;
    gap: 12px;
    width: 100%;
    max-width: 300px;
  }

  .serve-btn {
    flex: 1;
    padding: 14px;
    border-radius: 12px;
    border: 2px solid #333;
    background: #1a1a1a;
    color: #888;
    font-size: 1rem;
    cursor: pointer;
    transition: all 0.2s;
  }

  .serve-btn.active {
    border-color: #4ade80;
    color: #4ade80;
    background: #0d2818;
  }

  .start-btn {
    width: 100%;
    max-width: 300px;
    padding: 16px;
    font-size: 1.2rem;
    font-weight: bold;
    border-radius: 12px;
    border: none;
    background: #4ade80;
    color: #000;
    cursor: pointer;
    margin-top: 10px;
  }

  .label {
    color: #888;
    font-size: 0.9rem;
    align-self: flex-start;
    margin-left: calc(50% - 150px);
  }

  /* GAME SCREEN */
  #game-screen {
    display: none;
    flex-direction: row;
    height: 100dvh;
    width: 100vw;
  }

  .team-panel {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: space-between;
    padding: 16px 12px;
    position: relative;
    cursor: pointer;
    user-select: none;
    transition: background 0.15s;
  }

  .team-panel:active {
    background: rgba(255,255,255,0.05);
  }

  .team-panel.my-team {
    background: linear-gradient(180deg, #0d1f12 0%, #0a0a0a 100%);
    border-right: 1px solid #1a1a1a;
  }

  .team-panel.enemy-team {
    background: linear-gradient(180deg, #1a0d0d 0%, #0a0a0a 100%);
  }

  .divider {
    width: 2px;
    background: #222;
    flex-shrink: 0;
  }

  .team-name {
    font-size: 1rem;
    font-weight: bold;
    text-transform: uppercase;
    letter-spacing: 2px;
    opacity: 0.7;
  }

  .my-team .team-name { color: #4ade80; }
  .enemy-team .team-name { color: #f87171; }

  .serving-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: #fbbf24;
    margin-top: 4px;
    opacity: 0;
    transition: opacity 0.3s;
  }

  .serving-dot.visible { opacity: 1; }

  .score-section {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
  }

  .sets-display {
    font-size: 1.8rem;
    font-weight: 900;
    opacity: 0.9;
  }

  .my-team .sets-display { color: #4ade80; }
  .enemy-team .sets-display { color: #f87171; }

  .games-display {
    font-size: 3.5rem;
    font-weight: 900;
    line-height: 1;
  }

  .my-team .games-display { color: #86efac; }
  .enemy-team .games-display { color: #fca5a5; }

  .points-display {
    font-size: 2.2rem;
    font-weight: bold;
    opacity: 0.8;
  }

  .sets-history {
    display: flex;
    flex-direction: column;
    gap: 4px;
    align-items: center;
  }

  .set-chip {
    font-size: 0.75rem;
    padding: 2px 8px;
    border-radius: 10px;
    background: #222;
    color: #888;
  }

  /* Bottom buttons */
  .bottom-controls {
    display: flex;
    flex-direction: column;
    gap: 8px;
    width: 100%;
  }

  .add-point-btn {
    width: 100%;
    padding: 18px;
    font-size: 1.3rem;
    font-weight: bold;
    border-radius: 14px;
    border: none;
    cursor: pointer;
    transition: transform 0.1s, opacity 0.1s;
  }

  .add-point-btn:active {
    transform: scale(0.96);
    opacity: 0.8;
  }

  .my-team .add-point-btn {
    background: #4ade80;
    color: #000;
  }

  .enemy-team .add-point-btn {
    background: #f87171;
    color: #000;
  }

  .undo-btn {
    width: 100%;
    padding: 10px;
    font-size: 0.9rem;
    border-radius: 10px;
    border: 1px solid #333;
    background: transparent;
    color: #666;
    cursor: pointer;
  }

  .undo-btn:active { opacity: 0.6; }

  /* OVERLAY */
  #overlay {
    display: none;
    position: fixed;
    top: 0; left: 0;
    width: 100vw;
    height: 100dvh;
    background: rgba(0,0,0,0.85);
    z-index: 100;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    padding: 20px;
  }

  #overlay.show { display: flex; }

  #overlay-emoji { font-size: 4rem; margin-bottom: 16px; }
  #overlay-title { font-size: 2rem; font-weight: 900; margin-bottom: 8px; }
  #overlay-sub { font-size: 1.1rem; color: #888; margin-bottom: 24px; }

  #overlay-close {
    padding: 14px 32px;
    font-size: 1.1rem;
    border-radius: 12px;
    border: none;
    background: #4ade80;
    color: #000;
    font-weight: bold;
    cursor: pointer;
  }

  /* MATCH OVER */
  #match-over-screen {
    display: none;
    position: fixed;
    top: 0; left: 0;
    width: 100vw;
    height: 100dvh;
    background: linear-gradient(135deg, #0a0a0a, #1a1a2e);
    z-index: 200;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    padding: 20px;
    gap: 16px;
  }

  #match-over-screen.show { display: flex; }

  #winner-name {
    font-size: 2.5rem;
    font-weight: 900;
    color: #4ade80;
  }

  .new-match-btn {
    padding: 16px 40px;
    font-size: 1.2rem;
    border-radius: 14px;
    border: none;
    background: #4ade80;
    color: #000;
    font-weight: bold;
    cursor: pointer;
    margin-top: 20px;
  }

  .connection-bar {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    padding: 4px;
    text-align: center;
    font-size: 0.7rem;
    color: #333;
    background: #050505;
    z-index: 50;
  }

  .connection-bar.connected { color: #4ade80; }
  .connection-bar.disconnected { color: #f87171; }
</style>
</head>
<body>

<!-- SETUP SCREEN -->
<div id="setup-screen">
  <h1>🎾 Padel Score</h1>
  
  <span class="label">Your team name</span>
  <input type="text" id="my-team-input" placeholder="Your Team" maxlength="20">
  
  <span class="label">Opponent team name</span>
  <input type="text" id="enemy-team-input" placeholder="Opponents" maxlength="20">

  <span class="label">Who serves first?</span>
  <div class="serve-select">
    <button class="serve-btn active" id="serve-us" onclick="selectServe('us')">We Serve</button>
    <button class="serve-btn" id="serve-them" onclick="selectServe('them')">They Serve</button>
  </div>

  <button class="start-btn" onclick="startMatch()">Start Match 🎾</button>
</div>

<!-- GAME SCREEN -->
<div id="game-screen">
  
  <!-- MY TEAM (LEFT) -->
  <div class="team-panel my-team" id="my-panel">
    <div>
      <div class="team-name" id="my-name">US</div>
      <div class="serving-dot" id="my-serve-dot"></div>
    </div>

    <div class="score-section">
      <div class="sets-display" id="my-sets">0</div>
      <div class="games-display" id="my-games">0</div>
      <div class="points-display" id="my-points">0</div>
      <div class="sets-history" id="my-history"></div>
    </div>

    <div class="bottom-controls">
      <button class="add-point-btn" onclick="addPoint('my')">+ POINT</button>
      <button class="undo-btn" onclick="undoPoint()">↩ Undo</button>
    </div>
  </div>

  <div class="divider"></div>

  <!-- ENEMY TEAM (RIGHT) -->
  <div class="team-panel enemy-team" id="enemy-panel">
    <div>
      <div class="team-name" id="enemy-name">THEM</div>
      <div class="serving-dot" id="enemy-serve-dot"></div>
    </div>

    <div class="score-section">
      <div class="sets-display" id="enemy-sets">0</div>
      <div class="games-display" id="enemy-games">0</div>
      <div class="points-display" id="enemy-points">0</div>
      <div class="sets-history" id="enemy-history"></div>
    </div>

    <div class="bottom-controls">
      <button class="add-point-btn" onclick="addPoint('enemy')">+ POINT</button>
      <button class="undo-btn" onclick="undoPoint()">↩ Undo</button>
    </div>
  </div>

</div>

<!-- OVERLAY (Game/Set won) -->
<div id="overlay">
  <div id="overlay-emoji">🎾</div>
  <div id="overlay-title">Game!</div>
  <div id="overlay-sub"></div>
  <button id="overlay-close" onclick="closeOverlay()">Continue</button>
</div>

<!-- MATCH OVER -->
<div id="match-over-screen">
  <div style="font-size:3rem">🏆</div>
  <div style="font-size:1.2rem; color:#888">Match Winner</div>
  <div id="winner-name">Team A</div>
  <div id="final-score" style="color:#888; font-size:1rem"></div>
  <button class="new-match-btn" onclick="newMatch()">New Match</button>
</div>

<!-- CONNECTION BAR -->
<div class="connection-bar" id="conn-bar">connecting...</div>

<script>
  // Which side am I?
  // 'a' = I am team A, 'b' = I am team B
  let myTeam = 'a';
  let servingFirst = 'a';
  let polling = null;
  let lastScore = null;
  let overlayTimer = null;

  function selectServe(who) {
    document.getElementById('serve-us').classList.toggle('active', who === 'us');
    document.getElementById('serve-them').classList.toggle('active', who === 'them');
    servingFirst = who === 'us' ? 'a' : 'b';
  }

  async function startMatch() {
    const myName = document.getElementById('my-team-input').value.trim() || 'Team A';
    const enemyName = document.getElementById('enemy-team-input').value.trim() || 'Team B';

    // Determine if we are team_a or team_b
    // First person to start = team A
    myTeam = 'a';

    const teamA = myName;
    const teamB = enemyName;

    try {
      const res = await fetch('/api/start', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          team_a: teamA,
          team_b: teamB,
          serving: servingFirst
        })
      });

      if (res.ok) {
        document.getElementById('setup-screen').style.display = 'none';
        document.getElementById('game-screen').style.display = 'flex';
        startPolling();
      }
    } catch(e) {
      alert('Connection error. Check your internet.');
    }
  }

  async function addPoint(side) {
    // side = 'my' or 'enemy'
    const team = side === 'my' ? myTeam : (myTeam === 'a' ? 'b' : 'a');
    
    try {
      await fetch('/api/point/' + team, { method: 'POST' });
      await refreshScore();
    } catch(e) {
      console.log('Error adding point');
    }
  }

  async function undoPoint() {
    try {
      await fetch('/api/undo', { method: 'POST' });
      await refreshScore();
    } catch(e) {}
  }

  function startPolling() {
    refreshScore();
    polling = setInterval(refreshScore, 2000);
  }

  async function refreshScore() {
    try {
      const res = await fetch('/api/score');
      const data = await res.json();
      
      document.getElementById('conn-bar').textContent = '● live';
      document.getElementById('conn-bar').className = 'connection-bar connected';

      updateDisplay(data);
    } catch(e) {
      document.getElementById('conn-bar').textContent = '● disconnected';
      document.getElementById('conn-bar').className = 'connection-bar disconnected';
    }
  }

  function updateDisplay(data) {
    const isA = myTeam === 'a';

    const myName = isA ? data.team_a : data.team_b;
    const enemyName = isA ? data.team_b : data.team_a;
    const mySets = isA ? data.sets_a : data.sets_b;
    const enemySets = isA ? data.sets_b : data.sets_a;
    const myGames = isA ? data.games_a : data.games_b;
    const enemyGames = isA ? data.games_b : data.games_a;
    const myPoints = isA ? data.points_a : data.points_b;
    const enemyPoints = isA ? data.points_b : data.points_a;
    const imServing = data.serving === (isA ? 'a' : 'b');

    document.getElementById('my-name').textContent = myName;
    document.getElementById('enemy-name').textContent = enemyName;
    document.getElementById('my-sets').textContent = mySets;
    document.getElementById('enemy-sets').textContent = enemySets;
    document.getElementById('my-games').textContent = myGames;
    document.getElementById('enemy-games').textContent = enemyGames;
    document.getElementById('my-points').textContent = myPoints;
    document.getElementById('enemy-points').textContent = enemyPoints;

    document.getElementById('my-serve-dot').classList.toggle('visible', imServing);
    document.getElementById('enemy-serve-dot').classList.toggle('visible', !imServing);

    // Sets history
    updateHistory(data.sets_history, isA);

    // Check match over
    if (data.match_over && data.winner) {
      showMatchOver(data);
      return;
    }

    // Detect score change for overlays
    if (lastScore) {
      const prevMySets = isA ? lastScore.sets_a : lastScore.sets_b;
      const prevEnemySets = isA ? lastScore.sets_b : lastScore.sets_a;

      if (mySets > prevMySets) {
        showOverlay('🎉', 'Set Won!', myName + ' wins the set!');
      } else if (enemySets > prevEnemySets) {
        showOverlay('😤', 'Set Lost', enemyName + ' wins the set');
      } else if (myGames > (isA ? lastScore.games_a : lastScore.games_b)) {
        showOverlay('✅', 'Game!', myName + ' wins the game');
      } else if (enemyGames > (isA ? lastScore.games_b : lastScore.games_a)) {
        showOverlay('❌', 'Game Lost', enemyName + ' wins the game');
      }
    }

    lastScore = {...data};
  }

  function updateHistory(history, isA) {
    const myEl = document.getElementById('my-history');
    const enemyEl = document.getElementById('enemy-history');
    myEl.innerHTML = '';
    enemyEl.innerHTML = '';

    history.forEach(set => {
      const myScore = isA ? set.a : set.b;
      const enemyScore = isA ? set.b : set.a;
      
      const myChip = document.createElement('div');
      myChip.className = 'set-chip';
      myChip.textContent = myScore;
      myEl.appendChild(myChip);

      const enemyChip = document.createElement('div');
      enemyChip.className = 'set-chip';
      enemyChip.textContent = enemyScore;
      enemyEl.appendChild(enemyChip);
    });
  }

  function showOverlay(emoji, title, sub) {
    if (overlayTimer) clearTimeout(overlayTimer);
    document.getElementById('overlay-emoji').textContent = emoji;
    document.getElementById('overlay-title').textContent = title;
    document.getElementById('overlay-sub').textContent = sub;
    document.getElementById('overlay').classList.add('show');
    overlayTimer = setTimeout(closeOverlay, 3000);
  }

  function closeOverlay() {
    document.getElementById('overlay').classList.remove('show');
    if (overlayTimer) clearTimeout(overlayTimer);
  }

  function showMatchOver(data) {
    clearInterval(polling);
    document.getElementById('winner-name').textContent = data.winner;
    
    const history = data.sets_history;
    let scoreText = history.map(s => s.a + '-' + s.b).join('  ');
    document.getElementById('final-score').textContent = scoreText;
    
    document.getElementById('match-over-screen').classList.add('show');
  }

  function newMatch() {
    document.getElementById('match-over-screen').classList.remove('show');
    document.getElementById('game-screen').style.display = 'none';
    document.getElementById('setup-screen').style.display = 'flex';
    lastScore = null;
    if (polling) clearInterval(polling);
  }
</script>
</body>
</html>
"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
