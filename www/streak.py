import os
import config
import math
from ch_util import (
    load_task, get_or_create_task_for_user, random_task_for_ip,
    validate_changeset, time_until_day_ends,
    parse_changeset_id, today
)
from db import database, User, Task
from ruamel.yaml import YAML
from www import app
from flask import (
    session, url_for, redirect, request, render_template, g, flash, jsonify
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


def merge_dict(target, other):
    for k, v in other.items():
        if isinstance(v, dict):
            node = target.setdefault(k, {})
            merge_dict(node, v)
        else:
            target[k] = v


def load_language(path, lang):
    yaml = YAML()
    with open(os.path.join(config.BASE_DIR, path, 'en.yaml'), 'r') as f:
        data = yaml.load(f)
        data = data[data.keys()[0]]
    lang_file = os.path.join(config.BASE_DIR, path, lang + '.yaml')
    if os.path.exists(lang_file):
        with open(lang_file, 'r') as f:
            lang_data = yaml.load(f)
            merge_dict(data, lang_data[lang_data.keys()[0]])
    return data


def load_user_language():
    # TODO
    return

    supported = set([x[:x.index('.')].decode('utf-8') for x in os.listdir(
        os.path.join(config.BASE_DIR, 'lang')) if '.yaml' in x])
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

    data = load_language('lang', lang)
    tasks = load_language('lang/descriptions', lang)
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
        user.save()
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


def render_task(task):
    return render_template('task.html', task=task)


def get_user():
    if 'osm_uid' in session:
        return User.get(User.uid == session['osm_uid'])
    return None


@app.route('/')
def front():
    if 'osm_token' in session:
        return front_osm()
    if 'X-Forwarded-For' in request.headers:
        ip = request.headers.getlist("X-Forwarded-For")[0].rpartition(' ')[-1]
    else:
        ip = request.remote_addr or 'unknown'
    task = load_task(random_task_for_ip(ip))
    return render_template('index.html', task=render_task(task))


def front_osm():
    if 'osm_token' not in session:
        redirect(url_for('login'))
    user = get_user()
    task_obj = get_or_create_task_for_user(user)
    task = load_task(task_obj.task)
    return render_template('front.html', task=render_task(task),
                           user=user, tobj=task_obj,
                           timeleft=time_until_day_ends())


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
    # TODO: call submit_changeset instead
    try:
        changeset = parse_changeset_id(cs_data)
        cs_date, conforms = validate_changeset(user, changeset, None, openstreetmap)
    except ValueError as e:
        flash(str(e))
        return redirect(url_for('front'))
    if not cs_date or cs_date != today():
        flash('Date of the changeset is wrong')
        return redirect(url_for('front'))
    task = Task.get(Task.user == user, Task.day == cs_date)
    try:
        last_task = Task.select(Task.day).where(
            Task.user == user, Task.changeset.is_null(False)
        ).order_by(Task.day.desc()).get()
        is_streak = last_task.day == cs_date - cs_date.resolution
    except Task.DoesNotExist:
        is_streak = False
    task.changeset = changeset
    task.correct = conforms
    if is_streak:
        user.streak += 1
    else:
        user.streak = 1
    user.score += int(math.log(user.streak+1, 2))
    if conforms:
        flash('An extra point for completing the task')
        user.score += 1
    if user.level < len(config.LEVELS) + 1:
        if user.score >= config.LEVELS[user.level-1]:
            user.level += 1
            flash('Congratulations on gaining a level!')
    with database.atomic():
        task.save()
        user.save()
    flash('Changeset noted, thank you!')
    return redirect(url_for('front'))


@app.route('/changesets')
def get_changesets():
    if 'osm_token' not in session:
        return jsonify(error='Log in please')
    user = User.get(User.uid == session['osm_uid'])
    today = datetime.utcnow().date()
    since = today - today.resolution * 2
    resp = openstreetmap.get('changesets?user={}&time={}'.format(
        user.uid, since.strftime('%Y-%m-%d')))
    if resp.status != 200:
        return jsonify(error='Error connecting to OSM API')
    result = []
    for ch in resp.data:
        chtime = datetime.strptime(ch.get('created_at'), '%Y-%m-%dT%H:%M:%SZ')
        if chtime.date() < today - today.resolution:
            continue
        chdata = {
            'id': int(ch.get('id')),
            'time': ch.get('created_at')
        }
        if chtime.date() == today:
            hdate = 'Today'
        elif chtime.date() == today - today.resolution:
            hdate = 'Yesterday'
        else:
            hdate = chtime.strftime('%d.%m')
        chdata['htime'] = hdate + ' ' + chtime.strftime('%H:%M')
        for tag in ch.findall('tag'):
            if tag.get('k') == 'created_by':
                chdata['editor'] = tag.get('v')
            elif tag.get('k') == 'comment':
                chdata['comment'] = tag.get('v')
        result.append(chdata)
    return jsonify(changesets=result)


@app.route('/about')
def about():
    return render_template('about.html', user=get_user(), levels=config.LEVELS)


@app.route('/settings')
def settings():
    return render_template('connect.html', user=get_user())
