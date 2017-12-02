import config
import math
import re
import ch_util as ch
from db import database, User, Task
from www import app
from flask import (
    session, url_for, redirect, request,
    render_template, g, flash, jsonify
)
from flask_oauthlib.client import OAuth
from datetime import datetime


oauth = OAuth()
openstreetmap = oauth.remote_app(
    'OpenStreetMap',
    base_url='https://api.openstreetmap.org/api/0.6/',
    request_token_url='https://www.openstreetmap.org/oauth/request_token',
    access_token_url='https://www.openstreetmap.org/oauth/access_token',
    authorize_url='https://www.openstreetmap.org/oauth/authorize',
    consumer_key=app.config['OAUTH_KEY'] or '123',
    consumer_secret=app.config['OAUTH_SECRET'] or '123'
)


@app.before_request
def before_request():
    database.connect()
    load_user_language()


@app.teardown_request
def teardown(exception):
    if not database.is_closed():
        database.close()


def get_language_from_request():
    supported = ch.get_supported_languages()
    accepted = request.headers.get('Accept-Language', '')
    lang = 'en'
    for lpart in accepted.split(','):
        if ';' in lpart:
            lpart = lpart[:lpart.index(';')]
        pieces = lpart.strip().split('-')
        if len(pieces) >= 2:
            testlang = '{}_{}'.format(pieces[0].lower(), pieces[1].upper())
            if testlang in supported:
                lang = testlang
                break
        if len(pieces) == 1 and pieces[0].lower() in supported:
            lang = pieces[0].lower()
            break
    return lang


def load_user_language():
    user = get_user()
    data = ch.load_language_from_user('', user)
    tasks = ch.load_language_from_user('tasks', user)
    data['tasks'] = tasks
    g.lang = data


@app.route('/login')
def login():
    if 'osm_token' not in session:
        session['objects'] = request.args.get('objects')
        return openstreetmap.authorize(callback=url_for('oauth'))
    return login()


@app.route('/oauth')
def oauth():
    resp = openstreetmap.authorized_response()
    if resp is None:
        return 'Denied. <a href="' + url_for('login') + '">Try again</a>.'
    session['osm_token'] = (
            resp['oauth_token'],
            resp['oauth_token_secret']
    )
    user_details = openstreetmap.get('user/details').data
    session['osm_uid'] = int(user_details[0].get('id'))
    name = user_details[0].get('display_name')
    user, created = User.get_or_create(uid=session['osm_uid'],
                                       defaults={'name': name})
    if user.name != name or created:
        user.name = name
        user.lang = get_language_from_request()
        user.save()
    # Use the same task a user has seen when not logged in
    ch.get_or_create_task_for_user(user, ip=get_ip())
    return redirect(url_for('front'))


@app.route('/logout')
def logout():
    if 'osm_token' in session:
        del session['osm_token']
    if 'osm_uid' in session:
        del session['osm_uid']
    return redirect(url_for('front'))


@openstreetmap.tokengetter
def get_token(token='user'):
    if token == 'user' and 'osm_token' in session:
        return session['osm_token']
    return None


RE_MARKUP_LINK = re.compile(r'\[(http[^ \]]+) +([^\]]+)\]')
RE_EM = re.compile(r'\'\'(.*?)\'\'')


def render_task(task):
    desc = task['description'].strip()
    desc = desc.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    desc = desc.replace('\n', '<br>')
    desc = RE_MARKUP_LINK.sub(r'<a href="\1">\2</a>', desc)
    desc = RE_EM.sub(r'<i>\1</i>', desc)
    return render_template('task.html', task=task, desc=desc)


def get_user():
    if 'osm_uid' in session:
        return User.get(User.uid == session['osm_uid'])
    return None


def get_ip():
    if 'X-Forwarded-For' in request.headers:
        return request.headers.getlist("X-Forwarded-For")[0].rpartition(' ')[-1]
    return request.remote_addr or 'unknown'


@app.route('/')
def front():
    if 'osm_token' in session:
        return front_osm()
    task = ch.load_task(ch.random_task_for_ip(get_ip()))
    return render_template('index.html', task=render_task(task))


def front_osm():
    if 'osm_token' not in session:
        redirect(url_for('login'))
    user = get_user()
    task_obj = ch.get_or_create_task_for_user(user)
    task = ch.load_task(task_obj.task)
    return render_template('front.html', task=render_task(task),
                           user=user, tobj=task_obj,
                           timeleft=ch.time_until_day_ends())


@app.route('/user/<uid>')
def userinfo(uid):
    user = get_user()
    if user and user.name == uid:
        return redirect(url_for('front'))
    try:
        quser = User.get(User.name == uid)
        return render_template('userinfo.html', user=user, quser=quser)
    except User.DoesNotExist:
        return 'Wrong user id'


@app.route('/changeset')
def changeset():
    if 'osm_token' not in session:
        redirect(url_for('login'))

    cs_data = request.args.get('changeset')
    if not cs_data.strip():
        return redirect(url_for('front'))
    user = get_user()
    msgs, _ = ch.submit_changeset(user, cs_data, openstreetmap)
    for m in msgs:
        flash(m)
    return redirect(url_for('front'))


@app.route('/changesets')
def get_changesets():
    if 'osm_token' not in session:
        return jsonify(error='Log in please')
    user = User.get(User.uid == session['osm_uid'])
    try:
        result = ch.get_user_changesets(user)
    except Exception:
        return jsonify(error='Error connecting to OSM API')
    return jsonify(changesets=result)


@app.route('/about')
def about():
    return render_template('about.html', user=get_user(), levels=config.LEVELS)


@app.route('/settings')
def settings():
    user = get_user()
    if user:
        code = user.generate_code()
    else:
        code = ''
    return render_template('connect.html', user=user, code=code,
                           langs=ch.get_supported_languages())


@app.route('/set-email', methods=['POST'])
def set_email():
    user = get_user()
    email = request.form['email']
    if not email or '@' not in email:
        new_email = None
    else:
        new_email = email
    if user.email != new_email:
        user.email = new_email
        user.save()
    return redirect(url_for('settings'))


@app.route('/set-lang', methods=['POST'])
def set_lang():
    user = get_user()
    new_lang = request.form['lang']
    if new_lang != user.lang and new_lang in ch.get_supported_languages():
        user.lang = new_lang
        user.save()
    return redirect(url_for('settings'))
