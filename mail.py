#!/usr/bin/env python
import os
import sys
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, BASE_DIR)
PYTHON = 'python2.7'
VENV_DIR = os.path.join(BASE_DIR, 'venv', 'lib', PYTHON, 'site-packages')
if os.path.exists(VENV_DIR):
    sys.path.insert(1, VENV_DIR)

import config
import ch_util as ch
import smtplib
from db import database, User
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr


def send_email(user):
    lang = ch.load_language_from_user('', user)
    lang['tasks'] = ch.load_language_from_user('tasks', user)
    task_obj = ch.get_or_create_task_for_user(user)
    task = ch.load_task(task_obj.task, lang['tasks'])
    desc = task['t_description']
    message = u'{hi}\n\n{task}\n\n{emoji} {title}\n\n{desc}\n\n{submit}\n\n{bye}\n{streak}'.format(
        hi=lang['email']['hi'].format(user.name), task=lang['email']['new_task'],
        emoji=task['emoji'], title=task['t_title'], desc=desc,
        submit=lang['email']['to_submit'].format(config.BASE_URL), bye=lang['email']['bye'],
        streak=lang['title']
    )
    msg = MIMEText(message, 'plain', 'utf-8')
    msg['Subject'] = u'[{}] {} {}'.format(lang['title'], task['emoji'], task['title'])
    msg['From'] = formataddr(('OSM Streak', config.EMAIL_FROM))
    msg['To'] = formataddr((user.name, user.email))

    s = smtplib.SMTP('localhost')
    s.sendmail(config.EMAIL_FROM, [user.email], msg.as_string())
    s.quit()


if __name__ == '__main__':
    database.connect()
    query = User.select().where(User.email.is_null(False))
    for user in query:
        send_email(user)
