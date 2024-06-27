import os
from ..db import database, User
from . import app
from .. import ch_util as ch
from flask import (
    session, url_for, redirect, request,
    render_template, g, flash, jsonify
)
from authlib.integrations.flask_client import OAuth
from authlib.common.errors import AuthlibBaseError
from xml.etree import ElementTree as etree


oauth = OAuth(app)
oauth.register(
    'openstreetmap',
    api_base_url='https://api.openstreetmap.org/api/0.6/',
    access_token_url='https://www.openstreetmap.org/oauth2/token',
    authorize_url='https://www.openstreetmap.org/oauth2/authorize',
    client_id=app.config['OAUTH_KEY'] or '123',
    client_secret=app.config['OAUTH_SECRET'] or '123',
    client_kwargs={'scope': 'read_prefs write_api'},
)


@app.before_request
def before_request():
    database.connect()
    load_user_language()


@app.teardown_request
def teardown(exception):
    if not database.is_closed():
        database.close()


def dated_url_for(endpoint, **values):
    if endpoint == 'static':
        filename = values.get('filename', None)
        if filename:
            file_path = os.path.join(app.root_path,
                                     endpoint, filename)
            values['q'] = int(os.stat(file_path).st_mtime)
    return url_for(endpoint, **values)


app.jinja_env.globals['dated_url_for'] = dated_url_for


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
    g.supported_languages = ch.get_supported_languages()
    user = get_user()
    if user:
        lang = user.lang
    else:
        lang = get_language_from_request()
    data = ch.load_language('', lang)
    tasks = ch.load_language('tasks', lang)
    data['tasks'] = tasks
    g.lang = data


def html_esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


@app.route('/login')
def login():
    if 'osm_token2' not in session:
        session['objects'] = request.args.get('objects')
        return oauth.openstreetmap.authorize(
            callback=url_for('oauth_callback'))
    return login()


@app.route('/oauth')
def oauth_callback():
    try:
        token = oauth.openstreetmap.authorize_access_token()
    except AuthlibBaseError:
        return 'Denied. <a href="' + url_for('login') + '">Try again</a>.'

    session['osm_token2'] = token

    response = oauth.openstreetmap.get('user/details')
    user_details = etree.fromstring(response.content)
    name = user_details[0].get('display_name')
    session['osm_uid'] = int(user_details[0].get('id'))
    user, created = User.get_or_create(uid=session['osm_uid'],
                                       defaults={'name': name})
    if user.name != name or created:
        user.name = name
        user.lang = get_language_from_request()
        user.save()
    # Use the same task a user has seen when not logged in
    ch.get_or_create_task_for_user(user, ip=get_ip())

    if session.get('next'):
        redir = session['next']
        del session['next']
    else:
        redir = url_for('front')
    return redirect(redir)


@app.route('/logout')
def logout():
    if 'osm_token2' in session:
        del session['osm_token2']
    if 'osm_uid' in session:
        del session['osm_uid']
    return redirect(url_for('front'))


def render_task(task):
    desc = task['t_description'].strip()
    desc = html_esc(desc)
    desc = desc.replace('\n', '<br>')
    desc = ch.RE_MARKUP_LINK.sub(r'<a href="\1">\2</a>', desc)
    desc = ch.RE_EM.sub(r'<i>\1</i>', desc)
    return render_template('task.html', task=task, desc=desc, lang=g.lang)


def get_user():
    if 'osm_uid' in session:
        return User.get(User.uid == session['osm_uid'])
    return None


def get_ip():
    if 'X-Forwarded-For' in request.headers:
        return request.headers.getlist(
            "X-Forwarded-For")[0].rpartition(' ')[-1]
    return request.remote_addr or 'unknown'


@app.route('/')
def front():
    user = get_user()
    if not user:
        task = ch.load_task(ch.random_task_for_ip(get_ip()), g.lang['tasks'])
        msg = html_esc(g.lang['please_sign_in']).replace(
            '[', '<a href="' + html_esc(url_for('login')) + '">').replace(
                ']', '</a>')
        return render_template('index.html', task=render_task(task),
                               msg=msg, lang=g.lang)

    task_obj = ch.get_or_create_task_for_user(user)
    task = ch.load_task(task_obj.task, g.lang['tasks'])
    return render_template('front.html', task=render_task(task),
                           user=user, tobj=task_obj, lang=g.lang,
                           timeleft=ch.time_until_day_ends(g.lang))


@app.route('/user/<uid>')
def userinfo(uid):
    user = get_user()
    try:
        quser = User.get(User.name == uid)
        return render_template('userinfo.html', user=user,
                               quser=quser, lang=g.lang)
    except User.DoesNotExist:
        return 'Wrong user id'


@app.route('/changeset')
def changeset():
    if 'osm_token2' not in session:
        redirect(url_for('front'))

    cs_data = request.args.get('changeset')
    if not cs_data.strip():
        return redirect(url_for('front'))
    user = get_user()
    msgs, _ = ch.submit_changeset(user, cs_data, session['osm_token2'])
    for m in msgs:
        flash(m)
    return redirect(url_for('front'))


@app.route('/changesets')
def get_changesets():
    if 'osm_token2' not in session:
        return jsonify(error='Log in please')
    user = User.get(User.uid == session['osm_uid'])
    try:
        result = ch.get_user_changesets(
            user, session['osm_token2'], lang=g.lang)
    except Exception as e:
        import logging
        logging.error('Error getting user changesets: %s', e)
        return jsonify(error='Error connecting to OSM API')
    return jsonify(changesets=result[:10])


@app.route('/about')
def about():
    return render_template(
        'about.html', user=get_user(), levels=app.config['LEVELS'],
        lang=g.lang)


@app.route('/settings')
def settings():
    user = get_user()
    if not user:
        return redirect(url_for('login', next=request.path))
    if user:
        code = user.generate_code()
    else:
        code = ''
    return render_template('connect.html', user=user, code=code,
                           lang=g.lang)


@app.route('/set-email', methods=['POST'])
def set_email():
    user = get_user()
    if not user:
        return redirect(url_for('front'))
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
    if not user:
        return redirect(url_for('front'))
    new_lang = request.form['lang']
    if new_lang != user.lang and new_lang in ch.get_supported_languages():
        user.lang = new_lang
        user.save()
    return redirect(request.form.get('redirect', url_for('settings')))
