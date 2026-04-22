from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Game state
state = {
    "player1": "Player 1",
    "player2": "Player 2", 
    "player3": "Player 3",
    "player4": "Player 4",
    "blue_points": 0,
    "red_points": 0,
    "blue_games": 0,
    "red_games": 0,
    "blue_sets": 0,
    "red_sets": 0,
    "serving": "blue",
    "tiebreak": False,
    "match_over": False,
    "winner": "",
    "history": []
}

POINTS = ["0", "15", "30", "40"]

def get_display_points():
    if state["tiebreak"]:
        return str(state["blue_points"]), str(state["red_points"])
    
    bp = state["blue_points"]
    rp = state["red_points"]
    
    if bp >= 3 and rp >= 3:
        if bp == rp:
            return "40", "40"
        elif bp > rp:
            return "AD", "40"
        else:
            return "40", "AD"
    
    return POINTS[min(bp, 3)], POINTS[min(rp, 3)]

def save_history():
    import copy
    history_entry = {k: v for k, v in state.items() if k != "history"}
    state["history"].append(copy.deepcopy(history_entry))
    if len(state["history"]) > 50:
        state["history"].pop(0)

@app.route('/')
def index():
    return MAIN_HTML

@app.route('/api/score')
def get_score():
    bp, rp = get_display_points()
    return jsonify({
        "player1": state["player1"],
        "player2": state["player2"],
        "player3": state["player3"],
        "player4": state["player4"],
        "blue_points": bp,
        "red_points": rp,
        "blue_games": state["blue_games"],
        "red_games": state["red_games"],
        "blue_sets": state["blue_sets"],
        "red_sets": state["red_sets"],
        "serving": state["serving"],
        "tiebreak": state["tiebreak"],
        "match_over": state["match_over"],
        "winner": state["winner"]
    })

@app.route('/api/point', methods=['POST'])
def add_point():
    team = request.json.get('team')
    if state["match_over"]:
        return jsonify({"status": "match over"})
    
    save_history()
    
    if state["tiebreak"]:
        if team == "blue":
            state["blue_points"] += 1
        else:
            state["red_points"] += 1
        
        # Change serve every 2 points in tiebreak
        total = state["blue_points"] + state["red_points"]
        if total % 2 == 1:
            state["serving"] = "red" if state["serving"] == "blue" else "blue"
        
        # Win tiebreak at 7+ with 2 point lead
        if state["blue_points"] >= 7 and state["blue_points"] - state["red_points"] >= 2:
            state["blue_games"] += 1
            check_set_win("blue")
        elif state["red_points"] >= 7 and state["red_points"] - state["blue_points"] >= 2:
            state["red_games"] += 1
            check_set_win("red")
    else:
        if team == "blue":
            state["blue_points"] += 1
        else:
            state["red_points"] += 1
        
        bp = state["blue_points"]
        rp = state["red_points"]
        
        # Check game win
        if bp >= 4 and bp - rp >= 2:
            state["blue_games"] += 1
            state["blue_points"] = 0
            state["red_points"] = 0
            state["serving"] = "red" if state["serving"] == "blue" else "blue"
            check_set_win("blue")
        elif rp >= 4 and rp - bp >= 2:
            state["red_games"] += 1
            state["blue_points"] = 0
            state["red_points"] = 0
            state["serving"] = "red" if state["serving"] == "blue" else "blue"
            check_set_win("red")
    
    return jsonify({"status": "ok"})

def check_set_win(team):
    bg = state["blue_games"]
    rg = state["red_games"]
    
    # Check for tiebreak at 6-6
    if bg == 6 and rg == 6 and not state["tiebreak"]:
        state["tiebreak"] = True
        state["blue_points"] = 0
        state["red_points"] = 0
        return
    
    # Win set at 6+ with 2 game lead, or 7-5
    if team == "blue":
        if (bg >= 6 and bg - rg >= 2) or bg == 7:
            state["blue_sets"] += 1
            state["blue_games"] = 0
            state["red_games"] = 0
            state["blue_points"] = 0
            state["red_points"] = 0
            state["tiebreak"] = False
            check_match_win("blue")
    else:
        if (rg >= 6 and rg - bg >= 2) or rg == 7:
            state["red_sets"] += 1
            state["blue_games"] = 0
            state["red_games"] = 0
            state["blue_points"] = 0
            state["red_points"] = 0
            state["tiebreak"] = False
            check_match_win("red")

def check_match_win(team):
    if state["blue_sets"] >= 2:
        state["match_over"] = True
        state["winner"] = "blue"
    elif state["red_sets"] >= 2:
        state["match_over"] = True
        state["winner"] = "red"

@app.route('/api/undo', methods=['POST'])
def undo():
    if len(state["history"]) == 0:
        return jsonify({"status": "nothing to undo"})
    
    last = state["history"].pop()
    for key in last:
        state[key] = last[key]
    
    return jsonify({"status": "ok"})

@app.route('/api/start', methods=['POST'])
def start_match():
    data = request.json
    state["player1"] = data.get("player1", "Player 1")
    state["player2"] = data.get("player2", "Player 2")
    state["player3"] = data.get("player3", "Player 3")
    state["player4"] = data.get("player4", "Player 4")
    state["blue_points"] = 0
    state["red_points"] = 0
    state["blue_games"] = 0
    state["red_games"] = 0
    state["blue_sets"] = 0
    state["red_sets"] = 0
    state["serving"] = "blue"
    state["tiebreak"] = False
    state["match_over"] = False
    state["winner"] = ""
    state["history"] = []
    return jsonify({"status": "ok"})

MAIN_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <title>Padel Score</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: Arial, sans-serif;
            height: 100vh;
            overflow: hidden;
            background: #111;
        }

        /* SETUP SCREEN */
        #setup-screen {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100vh;
            background: #111;
            padding: 30px;
            gap: 20px;
        }

        #setup-screen h1 {
            color: white;
            font-size: 28px;
            margin-bottom: 10px;
        }

        .setup-teams {
            display: flex;
            gap: 20px;
            width: 100%;
            max-width: 500px;
        }

        .setup-team {
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }

        .setup-team h2 {
            text-align: center;
            font-size: 18px;
            padding: 8px;
            border-radius: 8px;
        }

        .blue-title { background: #1a6bb5; color: white; }
        .red-title { background: #b51a1a; color: white; }

        .setup-team input {
            padding: 12px;
            border-radius: 8px;
            border: 2px solid #444;
            background: #222;
            color: white;
            font-size: 16px;
            text-align: center;
        }

        .setup-team input:focus {
            outline: none;
            border-color: #888;
        }

        #start-btn {
            background: #27ae60;
            color: white;
            border: none;
            padding: 16px 60px;
            font-size: 22px;
            border-radius: 12px;
            cursor: pointer;
            margin-top: 10px;
        }

        /* GAME SCREEN */
        #game-screen {
            display: none;
            height: 100vh;
            flex-direction: column;
        }

        /* TOP: Names */
        #names-row {
            display: flex;
            height: 15vh;
        }

        .blue-names {
            flex: 1;
            background: #1a6bb5;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 4px;
        }

        .red-names {
            flex: 1;
            background: #b51a1a;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 4px;
        }

        .player-name {
            color: white;
            font-size: 18px;
            font-weight: bold;
            text-shadow: 1px 1px 3px rgba(0,0,0,0.5);
        }

        /* MIDDLE: Tap zones */
        #tap-row {
            display: flex;
            height: 45vh;
        }

        .blue-tap {
            flex: 1;
            background: #1565c0;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            user-select: none;
            -webkit-tap-highlight-color: transparent;
            transition: background 0.1s;
        }

        .blue-tap:active { background: #0d47a1; }

        .red-tap {
            flex: 1;
            background: #c62828;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            user-select: none;
            -webkit-tap-highlight-color: transparent;
            transition: background 0.1s;
        }

        .red-tap:active { background: #b71c1c; }

        .tap-text {
            color: white;
            font-size: 22px;
            font-weight: bold;
            text-align: center;
            pointer-events: none;
            opacity: 0.8;
        }

        /* UNDO BAR */
        #undo-bar {
            height: 8vh;
            background: #f39c12;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            user-select: none;
            -webkit-tap-highlight-color: transparent;
        }

        #undo-bar:active { background: #e67e22; }

        #undo-bar span {
            color: white;
            font-size: 20px;
            font-weight: bold;
        }

        /* BOTTOM: Scores */
        #score-row {
            display: flex;
            height: 32vh;
        }

        .blue-score {
            flex: 1;
            background: #0d47a1;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 6px;
        }

        .red-score {
            flex: 1;
            background: #b71c1c;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 6px;
        }

        .score-sets {
            color: rgba(255,255,255,0.8);
            font-size: 16px;
            letter-spacing: 3px;
        }

        .score-games {
            color: white;
            font-size: 52px;
            font-weight: bold;
            line-height: 1;
        }

        .score-points {
            color: rgba(255,255,255,0.9);
            font-size: 28px;
            font-weight: bold;
        }

        .serving-dot {
            width: 14px;
            height: 14px;
            background: #f1c40f;
            border-radius: 50%;
            display: inline-block;
            margin-left: 8px;
            vertical-align: middle;
        }

        /* OVERLAY */
        #overlay {
            display: none;
            position: fixed;
            top: 0; left: 0;
            width: 100%; height: 100%;
            background: rgba(0,0,0,0.85);
            z-index: 100;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 20px;
        }

        #overlay h2 {
            color: white;
            font-size: 36px;
            text-align: center;
        }

        #overlay p {
            color: #ccc;
            font-size: 22px;
            text-align: center;
        }

        #overlay button {
            background: #27ae60;
            color: white;
            border: none;
            padding: 16px 50px;
            font-size: 22px;
            border-radius: 12px;
            cursor: pointer;
            margin-top: 10px;
        }

        .tiebreak-badge {
            background: #f39c12;
            color: white;
            padding: 6px 16px;
            border-radius: 20px;
            font-size: 14px;
            font-weight: bold;
            position: absolute;
            top: 15vh;
            left: 50%;
            transform: translateX(-50%);
            z-index: 10;
        }
    </style>
</head>
<body>

<!-- SETUP SCREEN -->
<div id="setup-screen">
    <h1>🏓 Padel Score</h1>
    <div class="setup-teams">
        <div class="setup-team">
            <h2 class="blue-title">🔵 Blue Team</h2>
            <input type="text" id="p1" placeholder="Player 1" />
            <input type="text" id="p2" placeholder="Player 2" />
        </div>
        <div class="setup-team">
            <h2 class="red-title">🔴 Red Team</h2>
            <input type="text" id="p3" placeholder="Player 3" />
            <input type="text" id="p4" placeholder="Player 4" />
        </div>
    </div>
    <button id="start-btn" onclick="startMatch()">▶ Start Match</button>
</div>

<!-- GAME SCREEN -->
<div id="game-screen">

    <!-- Names Row -->
    <div id="names-row">
        <div class="blue-names">
            <div class="player-name" id="name1">Player 1</div>
            <div class="player-name" id="name2">Player 2</div>
        </div>
        <div class="red-names">
            <div class="player-name" id="name3">Player 3</div>
            <div class="player-name" id="name4">Player 4</div>
        </div>
    </div>

    <!-- Tap Row -->
    <div id="tap-row">
        <div class="blue-tap" onclick="addPoint('blue')">
            <div class="tap-text">TAP FOR<br>BLUE POINT</div>
        </div>
        <div class="red-tap" onclick="addPoint('red')">
            <div class="tap-text">TAP FOR<br>RED POINT</div>
        </div>
    </div>

    <!-- Undo Bar -->
    <div id="undo-bar" onclick="undoPoint()">
        <span>↩ UNDO LAST POINT</span>
    </div>

    <!-- Score Row -->
    <div id="score-row">
        <div class="blue-score">
            <div class="score-sets" id="blue-sets">● ● ●</div>
            <div class="score-games" id="blue-games">0</div>
            <div class="score-points" id="blue-points">0</div>
        </div>
        <div class="red-score">
            <div class="score-sets" id="red-sets">● ● ●</div>
            <div class="score-games" id="red-games">0</div>
            <div class="score-points" id="red-points">0</div>
        </div>
    </div>

    <!-- Tiebreak badge -->
    <div class="tiebreak-badge" id="tiebreak-badge" style="display:none">TIEBREAK</div>

</div>

<!-- OVERLAY -->
<div id="overlay">
    <h2 id="overlay-title">Game!</h2>
    <p id="overlay-sub"></p>
    <button onclick="closeOverlay()">Continue ▶</button>
</div>

<script>
    let matchStarted = false;
    let lastScore = null;
    let overlayShowing = false;

    function startMatch() {
        const p1 = document.getElementById('p1').value || 'Player 1';
        const p2 = document.getElementById('p2').value || 'Player 2';
        const p3 = document.getElementById('p3').value || 'Player 3';
        const p4 = document.getElementById('p4').value || 'Player 4';

        fetch('/api/start', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({player1: p1, player2: p2, player3: p3, player4: p4})
        }).then(() => {
            document.getElementById('setup-screen').style.display = 'none';
            document.getElementById('game-screen').style.display = 'flex';
            matchStarted = true;
            updateScore();
        });
    }

    function addPoint(team) {
        if (overlayShowing) return;
        fetch('/api/point', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({team: team})
        }).then(() => updateScore());
    }

    function undoPoint() {
        fetch('/api/undo', {method: 'POST'})
            .then(() => updateScore());
    }

    function closeOverlay() {
        document.getElementById('overlay').style.display = 'none';
        overlayShowing = false;
    }

    function setDots(sets) {
        let dots = '';
        for (let i = 0; i < 3; i++) {
            dots += i < sets ? '⬤ ' : '○ ';
        }
        return dots.trim();
    }

    function updateScore() {
        fetch('/api/score').then(r => r.json()).then(data => {
            // Update names
            document.getElementById('name1').textContent = data.player1;
            document.getElementById('name2').textContent = data.player2;
            document.getElementById('name3').textContent = data.player3;
            document.getElementById('name4').textContent = data.player4;

            // Update scores
            const blueServe = data.serving === 'blue' ? ' ●' : '';
            const redServe = data.serving === 'red' ? ' ●' : '';

            document.getElementById('blue-points').textContent = data.blue_points + blueServe;
            document.getElementById('red-points').textContent = data.red_points + redServe;
            document.getElementById('blue-games').textContent = data.blue_games;
            document.getElementById('red-games').textContent = data.red_games;
            document.getElementById('blue-sets').textContent = setDots(data.blue_sets);
            document.getElementById('red-sets').textContent = setDots(data.red_sets);

            // Tiebreak badge
            document.getElementById('tiebreak-badge').style.display = data.tiebreak ? 'block' : 'none';

            // Match over
            if (data.match_over && !overlayShowing) {
                overlayShowing = true;
                const winner = data.winner === 'blue' ? 
                    (data.player1 + ' & ' + data.player2) : 
                    (data.player3 + ' & ' + data.player4);
                const color = data.winner === 'blue' ? '#1a6bb5' : '#b51a1a';
                document.getElementById('overlay-title').textContent = '🏆 Match Over!';
                document.getElementById('overlay-title').style.color = color;
                document.getElementById('overlay-sub').textContent = winner + ' wins!';
                document.getElementById('overlay').style.display = 'flex';
            }

            lastScore = data;
        });
    }

    // Poll every 2 seconds for sync
    setInterval(() => {
        if (matchStarted) updateScore();
    }, 2000);
</script>

</body>
</html>
'''

if __name__ == '__main__':
    app.run(debug=True)
