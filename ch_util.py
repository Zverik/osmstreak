# Changeset utils

import config
import datetime
import logging
import math
import os
import re
import requests
from db import User, Task
from random import Random, choice
from ruamel.yaml import YAML
from xml.etree import ElementTree as etree


def today():
    return datetime.datetime.utcnow().date()


def yesterday():
    return today() - datetime.date.resolution


def time_until_day_ends():
    tomorrow = today() + datetime.timedelta(days=1)
    midnight = datetime.datetime(
        tomorrow.year, tomorrow.month, tomorrow.day, 0, 0, 0, 0)
    left = int((midnight - datetime.datetime.utcnow()).total_seconds())
    halfhours = left // 1800
    if halfhours > 2:
        if halfhours % 2 == 0:
            return '{} hours'.format(halfhours/2)
        else:
            return '{} hours'.format(halfhours/2.0)
    elif halfhours == 2:
        return 'an hour'
    return '{} minutes'.format(left // 60)


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


def load_task(name):
    filename = os.path.join(config.BASE_DIR, 'tasks', name+'.yaml')
    if not os.path.exists(filename):
        return None
    with open(filename, 'r') as f:
        yaml = YAML()
        data = yaml.load(f)
    if 'title' in data and 'emoji' in data:
        return data
    return None


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
    last_tasks = set([x[0] for x in User.select(Task.task).join(Task).order_by(
        Task.day.desc()).limit(int(len(tasks) * 0.7)).tuples()])
    return choice(list(tasks - last_tasks))


def get_or_create_task_for_user(user, date=None):
    if not date:
        date = today()
    try:
        task_obj = Task.get(Task.user == user, Task.day == date)
    except Task.DoesNotExist:
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


def parse_changeset_id(changeset):
    if isinstance(changeset, basestring):
        m = re.search(r'/changeset/(\d+)', changeset)
        if not m:
            m = re.match(r'^\s*(\d+)\s*$', changeset)
            if not m:
                raise ValueError('Wrong changeset id: {}'.format(changeset))
        return int(m.group(1))
    return changeset


def validate_changeset(user, changeset, task_name=None, req=None):
    if not req:
        req = RequestsWrapper()
    resp = req.get('changeset/{}'.format(changeset))
    if resp.status != 200:
        raise Exception('Error connecting to OSM API')
    ch = resp.data[0]
    uid = int(ch.get('uid'))
    if uid != user.uid:
        raise ValueError('Please add only your changesets')
    date_str = ch.get('created_at')[:10]
    date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
    if date != today():  # and date + date.resolution != today:
        raise ValueError('Changeset is too old')

    try:
        if not task_name:
            task_obj = Task.get(Task.user == user, Task.day == date)
            task_name = task_obj.task
    except Task.DoesNotExist:
        raise ValueError('Task was not given, please visit the front page')
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
                    raise Exception('Error connecting to OSM API')
                changes = resp.data
                if changes.tag != 'osmChange':
                    raise Exception('OSM API returned {} for the root xml'.format(changes.tag))

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


def submit_changeset(user, changeset, req=None):
    changeset = parse_changeset_id(changeset)
    cs_date, conforms = validate_changeset(user, changeset, req)
    if not cs_date:
        return 'Date of the changeset is wrong'
    try:
        task = Task.get(Task.user == user, Task.day == cs_date)
    except Task.DoesNotExist:
        return 'Task was not given, please visit the front page'
    task.changeset = changeset
    task.correct = False
    task.save()
    user.streak += 1
    user.score += int(math.log(user.streak+1, 2))
    if conforms:
        user.score += 1
    if user.level < len(config.LEVELS) + 1:
        if user.score >= config.LEVELS[user.level-1]:
            user.level += 1
    user.save()
