# Changeset utils

import config
import datetime
import logging
import math
import os
import re
import requests
from db import database, Task
from random import Random, choice
from ruamel.yaml import YAML
from xml.etree import ElementTree as etree


RE_MARKUP_LINK = re.compile(r'\[(http[^ \]]+) +([^\]]+)\]')
RE_EM = re.compile(r'\'\'(.*?)\'\'')
RE_CHANGESET = re.compile(r'^\s*(?:https.*/changeset/)?(\d{8,})/?\s*$')


def today():
    return datetime.datetime.utcnow().date()


def yesterday():
    return today() - datetime.date.resolution


def time_until_day_ends(lang=None):
    tomorrow = today() + datetime.timedelta(days=1)
    midnight = datetime.datetime(
        tomorrow.year, tomorrow.month, tomorrow.day, 0, 0, 0, 0)
    left = int((midnight - datetime.datetime.utcnow()).total_seconds())
    halfhours = left // 1800
    if not lang or 'time' not in lang:
        lang = {'time': {}}
    if halfhours > 2:
        if halfhours % 2 == 0:
            return lang['time'].get('n_hours', '{} hours').format(halfhours/2)
        else:
            return lang['time'].get('n_hours', '{} hours').format(halfhours/2.0)
    elif halfhours == 2:
        return lang['time'].get('hour', 'an hour')
    return lang['time'].get('n_minutes', '{} minutes').format(left // 60)


def merge_dict(target, other):
    for k, v in other.items():
        if isinstance(v, dict):
            node = target.setdefault(k, {})
            merge_dict(node, v)
        else:
            target[k] = v


def to_unicode(d):
    if isinstance(d, dict):
        return {to_unicode(k): to_unicode(v) for k, v in d.iteritems()}
    elif isinstance(d, list):
        return [to_unicode(s) for s in d]
    elif isinstance(d, unicode):
        return d.encode('utf-8')
    else:
        return d


def load_language(path, lang):
    yaml = YAML()
    with open(os.path.join(config.BASE_DIR, 'lang', path or '', 'en.yaml'), 'r') as f:
        data = yaml.load(f)
        data = data[data.keys()[0]]
    lang_file = os.path.join(config.BASE_DIR, 'lang', path or '', lang + '.yaml')
    if os.path.exists(lang_file):
        with open(lang_file, 'r') as f:
            lang_data = yaml.load(f)
            merge_dict(data, lang_data[lang_data.keys()[0]])
    # return to_unicode(data)
    return data


def load_language_from_user(path, user):
    return load_language(path, 'en' if not user else user.lang)


def get_supported_languages():
    return set([x[:x.index('.')].decode('utf-8') for x in os.listdir(
        os.path.join(config.BASE_DIR, 'lang')) if '.yaml' in x])


def get_tasks(max_level=1):
    files = os.listdir(os.path.join(config.BASE_DIR, 'tasks'))
    result = []
    for fn in files:
        if not fn.endswith('.yaml') or fn[0] not in '0123456789':
            continue
        task = os.path.splitext(fn)[0]
        level = int(task[0])
        if level <= max_level:
            result.append(task)
    return result


def load_task(name, lang=None):
    filename = os.path.join(config.BASE_DIR, 'tasks', name+'.yaml')
    if not os.path.exists(filename):
        logging.error('Task %s does not exist', name)
        return None
    with open(filename, 'r') as f:
        yaml = YAML()
        data = yaml.load(f)
    for k in ('title', 'emoji', 'description'):
        if k not in data:
            logging.error('Task %s: key %s not found', name, k)
            return None
    if lang:
        t_name = name.split('_', 1)[1]
        t_trans = lang.get(t_name, {})
        for k in ('title', 'description'):
            if k in t_trans:
                data['t_'+k] = t_trans[k]
    return data


def random_task_for_ip(ip):
    tasks = get_tasks()
    if not tasks:
        return None
    rnd = Random()
    date = datetime.datetime.utcnow().strftime('%y-%m-%d')
    rnd.seed(ip + date)
    return rnd.choice(tasks)


def random_task_for_user(user):
    tasks = set(get_tasks(user.level))
    if not tasks:
        return None
    last_tasks = set([x[0] for x in Task.select(Task.task).where(Task.user == user).order_by(
        Task.day.desc()).limit(int(len(tasks) * 0.7)).tuples()])
    return choice(list(tasks - last_tasks))


def get_or_create_task_for_user(user, date=None, ip=None):
    if not date:
        date = today()
    try:
        task_obj = Task.get(Task.user == user, Task.day == date)
        if task_obj.task not in get_tasks(user.level):
            task_obj.task = random_task_for_user(user)
            task_obj.save()
    except Task.DoesNotExist:
        if ip:
            task_name = random_task_for_ip(ip)
        else:
            task_name = random_task_for_user(user)
        task_obj = Task(user=user, day=date, task=task_name)
        task_obj.save()
    return task_obj


class RequestsWrapper(object):
    def __init__(self):
        self.api = 'https://api.openstreetmap.org/api/0.6/'

    def get(self, url):
        resp = requests.get(self.api + url)
        resp.status = resp.status_code
        if resp.status_code == 200:
            resp.data = etree.fromstring(resp.content)
        return resp


def validate_tags(obj, tagtest):
    # Examples of tags:
    # highway=primary
    # name,i=shell;bp
    # level~^-[1-5]$
    # natural=wood;water
    # name,i~^mcdon
    if isinstance(tagtest, basestring):
        tagtest = [tagtest]
    tags = {}
    for t in obj.findall('tag'):
        tags[t.get('k')] = t.get('v')
    if len(tagtest) == 1 and tagtest[0] == '-':
        return len(tags) == 0
    for tt in tagtest:
        if not tt:
            continue
        p = tt.find('=')
        p2 = tt.find('~')
        if p < 0 or (p2 >= 0 and p2 < p):
            p = p2
        if p < 0:
            logging.error('Failed to parse tag test: %s', tt)
            continue
        k = tt[:p]
        v = tt[p+1:]
        if not v:
            v = '*'
        caseins = k.endswith(',i')
        if caseins:
            k = k[:-2]
            v = v.lower()
        if k not in tags:
            return False
        if tt[p] == '=':
            if v[-1] == '*':
                if len(v) > 1 and v[:-1] != tags[k][:len(v)-1]:
                    if not caseins or v[:-1] != tags[k][:len(v)-1].lower():
                        return False
            elif v != tags[k]:
                if not caseins or v != tags[k].lower():
                    return False
        else:
            if not re.search(v, tags[k]):
                return False
    return True


class ValidationError(ValueError):
    def __init__(self, message, arg=None):
        self.message = message
        self.arg = arg
        super(ValidationError, self).__init__(message, arg)

    def to_lang(self, lang):
        m = lang[self.message]
        if self.arg:
            return m.format(self.arg)
        return m


def parse_changeset_id(changeset):
    if isinstance(changeset, basestring):
        m = RE_CHANGESET.match(changeset)
        if not m:
            raise ValidationError('wrong_id', changeset)
        return int(m.group(1))
    return changeset


def validate_changeset(user, changeset, task_name=None, req=None):
    if not req:
        req = RequestsWrapper()
    resp = req.get('changeset/{}'.format(changeset))
    if resp.status != 200:
        raise ValidationError('api_error')
    ch = resp.data[0]
    uid = int(ch.get('uid'))
    if uid != user.uid:
        raise ValidationError('not_yours')
    date_str = ch.get('created_at')[:10]
    date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
    if date < yesterday():
        raise ValidationError('old_changeset')

    try:
        if not task_name:
            task_obj = Task.get(Task.user == user, Task.day == date)
            task_name = task_obj.task
    except Task.DoesNotExist:
        raise ValidationError('no_task', date.strftime('%d.%m.%Y'))
    task = load_task(task_name)
    if 'test' not in task:
        return date, True
    changes = None
    RE_NUMBER = re.compile(r'^\d+$')
    for t, tagtest in task['test'].items():
        if t == 'changeset':
            if not validate_tags(ch, tagtest):
                return date, False
        else:
            if changes is None:
                resp = req.get('changeset/{}/download'.format(changeset))
                if resp.status != 200:
                    raise ValidationError('api_error')
                changes = resp.data
                if changes.tag != 'osmChange':
                    raise ValidationError('api_strange')

            state_action = True
            actions = set()
            count = 1
            obj_type = None
            for part in t.split('_'):
                if state_action:
                    if part.startswith('create') or part.startswith('add'):
                        actions.add('create')
                    elif part.startswith('modif'):
                        actions.add('modify')
                    elif part.startswith('delete'):
                        actions.add('delete')
                    elif RE_NUMBER.match(part):
                        count = int(part)
                        state_action = False
                if actions:
                    if part.startswith('node'):
                        obj_type = 'node'
                    elif part.startswith('way'):
                        obj_type = 'way'
                    elif part.startswith('rel'):
                        obj_type = 'relation'
                    elif part.startswith('area'):
                        obj_type = 'area'
                    elif part.startswith('obj'):
                        obj_type = 'any'
                    if obj_type:
                        break
            if not obj_type:
                logging.error('Cannot parse a test header: %s', t)
                return date, True

            found_count = 0
            for xaction in changes:
                if xaction.tag not in actions:
                    continue
                for xobj in xaction:
                    if obj_type in ('node', 'way', 'relation') and xobj.tag != obj_type:
                        continue
                    elif obj_type == 'area':
                        if xobj.tag == 'way':
                            if xobj.find('nd[1]').get('ref') != xobj.find('nd[last()]').get('ref'):
                                continue
                        elif xobj.tag == 'relation':
                            xtype = xobj.find("tag[@k='type']")
                            if xtype is None or xtype.get('v') != 'multipolygon':
                                continue
                        else:
                            continue
                    if validate_tags(xobj, tagtest):
                        found_count += 1
            if found_count < count:
                return date, False

    return date, True


def get_last_task_day(user):
    try:
        last_task = Task.select(Task.day).where(
            Task.user == user, Task.changeset.is_null(False)
        ).order_by(Task.day.desc()).get()
        return last_task.day
    except Task.DoesNotExist:
        return None


def submit_changeset(user, changeset, req=None):
    """Validates the changeset, records it and returns a series of messages."""
    lang = load_language_from_user('', user)['validation']
    try:
        changeset = parse_changeset_id(changeset)
        cs_date, conforms = validate_changeset(user, changeset, None, req)

        if not cs_date:
            raise ValidationError('wrong_date')

        last_task_day = get_last_task_day(user)
        if last_task_day and last_task_day >= cs_date:
            raise ValidationError('has_later_changeset')

        if cs_date < yesterday():
            raise ValidationError('old_changeset')
    except ValidationError as e:
        return [e.to_lang(lang)], False

    task = Task.get(Task.user == user, Task.day == cs_date)
    task.changeset = changeset
    task.correct = conforms

    if last_task_day == cs_date - cs_date.resolution:
        user.streak += 1
    else:
        user.streak = 1
    user.score += int(math.log(user.streak+1, 2))
    msgs = [lang['changeset_noted'].format(user.streak)]
    if conforms:
        user.score += 1
        msgs.append('extra_point')
    if user.level < len(config.LEVELS) + 1:
        if user.score >= config.LEVELS[user.level-1]:
            user.level += 1
            msgs.append('gain_level')

    with database.atomic():
        task.save()
        user.save()
    return msgs, True


def get_user_changesets(user, req=None, lang=None):
    if not req:
        req = RequestsWrapper()
    last_task_day = get_last_task_day(user)
    date = today()
    if last_task_day == date:
        # At least show changesets for today
        last_task_day -= last_task_day.resolution
    since = date - date.resolution * 2
    resp = req.get('changesets?user={}&time={}'.format(
        user.uid, since.strftime('%Y-%m-%d')))
    if resp.status != 200:
        raise Exception('Error connecting to OSM API')
    result = []
    if not lang:
        lang = {}
    for chs in resp.data:
        chtime = datetime.datetime.strptime(chs.get('created_at'), '%Y-%m-%dT%H:%M:%SZ')
        if chtime.date() <= last_task_day:
            continue
        chdata = {
            'id': int(chs.get('id')),
            'time': chs.get('created_at')
        }
        if chtime.date() == date:
            hdate = lang.get('today', 'Today')
        elif chtime.date() == date - date.resolution:
            hdate = lang.get('yesterday', 'Yesterday')
        else:
            hdate = chtime.strftime('%d.%m')
        chdata['htime'] = hdate + ' ' + chtime.strftime('%H:%M')
        for tag in chs.findall('tag'):
            if tag.get('k') == 'created_by':
                chdata['editor'] = tag.get('v')
            elif tag.get('k') == 'comment':
                chdata['comment'] = tag.get('v').encode('utf-8')
        result.append(chdata)
    return result
