# In app.py — replace your state API routes with these

import json
from datetime import datetime

@app.route('/api/court/<token>/state', methods=['GET'])
def get_court_state(token):
    """Return current court state as JSON"""
    court = Court.query.filter_by(access_token=token).first()
    if not court:
        return jsonify({'error': 'Court not found'}), 404
    
    try:
        if court.match_state:
            data = json.loads(court.match_state)
            return jsonify(data)
        else:
            return jsonify({'state': None})
    except Exception as e:
        print(f"GET state error: {e}")
        return jsonify({'state': None})


@app.route('/api/court/<token>/state', methods=['POST'])
def set_court_state(token):
    """Save court state from any device"""
    court = Court.query.filter_by(access_token=token).first()
    if not court:
        return jsonify({'error': 'Court not found'}), 404
    
    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({'error': 'No data'}), 400
        
        # Add server timestamp for debugging
        data['serverTime'] = int(datetime.utcnow().timestamp() * 1000)
        
        court.match_state = json.dumps(data)
        db.session.commit()
        
        return jsonify({'ok': True, 'syncTime': data.get('syncTime', 0)})
    except Exception as e:
        print(f"POST state error: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
