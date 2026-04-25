@app.route('/api/court/<token>/state', methods=['GET'])
def get_court_state(token):
    """Return current court state as JSON"""
    court = Court.query.filter_by(access_token=token).first()
    if not court:
        return jsonify({'error': 'Court not found'}), 404

    try:
        if court.state and court.state.state_json:
            data = json.loads(court.state.state_json)
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

        # Add server timestamp
        data['serverTime'] = int(datetime.utcnow().timestamp() * 1000)

        # Use CourtState relationship — NOT court.match_state
        if court.state:
            court.state.state_json = json.dumps(data)
            court.state.updated_at = datetime.utcnow()
        else:
            new_state = CourtState(
                court_id=court.id,
                state_json=json.dumps(data)
            )
            db.session.add(new_state)

        db.session.commit()
        return jsonify({'ok': True, 'syncTime': data.get('syncTime', 0)})

    except Exception as e:
        print(f"POST state error: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/court/<token>/test')
def test_court_api(token):
    """Debug route — remove before production"""
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
