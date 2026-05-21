from flask import jsonify, render_template, abort
from ..db import User
from . import app


# API endpoint per ottenere i dati dell'utente (JSON)
@app.route('/api/user/<username>')
def api_user_data(username):
    """
    GET /api/user/<username>
    Restituisce i dati pubblici dell'utente in JSON
    
    Esempio: GET /api/user/MapperName
    Risposta:
    {
        "name": "MapperName",
        "score": 1250,
        "level": 3,
        "streak": 45,
        "uid": 123456
    }
    """
    try:
        user = User.get(User.name == username)
        return jsonify({
            'name': user.name,
            'score': user.score,
            'level': user.level,
            'streak': user.streak,
            'uid': user.uid
        })
    except User.DoesNotExist:
        abort(404)


# Widget HTML per il profilo OSM
@app.route('/widget/<username>')
def user_widget(username):
    """
    GET /widget/<username>
    Restituisce un widget HTML da embeddare nel profilo OSM
    
    Uso: <iframe src="https://tuodominio.com/widget/MapperName" ...></iframe>
    """
    try:
        user = User.get(User.name == username)
        return render_template('widget.html', user=user)
    except User.DoesNotExist:
        abort(404)


# Badge SVG per readme o profilo
@app.route('/badge/<username>')
def user_badge(username):
    """
    GET /badge/<username>
    Restituisce un badge SVG con score e level
    
    Uso: ![OSM Streak](https://tuodominio.com/badge/MapperName)
    """
    try:
        user = User.get(User.name == username)
        return render_template('badge.svg', user=user), 200, {'Content-Type': 'image/svg+xml'}
    except User.DoesNotExist:
        abort(404)
