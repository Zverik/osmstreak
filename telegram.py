#!/usr/bin/env python
# coding: utf-8
import os
import sys
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, BASE_DIR)
PYTHON = 'python2.7'
VENV_DIR = os.path.join(BASE_DIR, 'venv', 'lib', PYTHON, 'site-packages')
if os.path.exists(VENV_DIR):
    sys.path.insert(1, VENV_DIR)

import config
import telepot
from datetime import datetime
import time
import re
import logging
import ch_util as ch
from db import database, Telegram, User
from telepot.loop import MessageLoop
from telepot.delegate import per_chat_id, create_open, pave_event_space


RE_TIME = re.compile(r'^\d\d:\d\d$')
RE_CHANGESET = re.compile(r'^(?:https.*/changeset/)?(\d{8,})/?$')
last_reminder = None


class Player(telepot.helper.ChatHandler):
    def __init__(self, *args, **kwargs):
        super(Player, self).__init__(*args, **kwargs)
        tg = self._get_tg()
        self.has_user = tg is not None
        self.lang = ch.load_language_from_user('telegram', None if tg is None else tg.user)

    def t(self, *args):
        d = self.lang
        for k in args:
            d = d[k]
        return d.encode('utf-8')

    def _get_tg(self):
        try:
            return Telegram.get(Telegram.channel == self.id)
        except Telegram.DoesNotExist:
            return None

    def _find_user_by_code(self, code):
        for u in User.select():
            if u.generate_code() == code:
                return u
        return None

    def _print_task(self):
        tg = self._get_tg()
        task_obj = ch.get_or_create_task_for_user(tg.user)
        if task_obj.changeset:
            self.sender.sendMessage(self.t('task_complete'))
        else:
            task = ch.load_task(task_obj.task)
            # TODO: Format description
            self.sender.sendMessage(
                '{} {}\n\n{}\n\n{}: {}\n\n{}'.format(
                    task['emoji'].encode('utf-8'), task['title'], task['description'],
                    self.t('time_left'), ch.time_until_day_ends(),
                    self.t('post_changeset')))

    def _print_score(self):
        user = self._get_tg().user
        self.sender.sendMessage(self.t('n_points').format(
            user.score) + '\n' + ('⭐' * user.level))

    def _register_changeset(self, changeset):
        user = self._get_tg().user
        msgs, ok = ch.submit_changeset(user, changeset)
        self.sender.sendMessage('\n\n'.join(msgs))
        if ok:
            self._print_score()

    def _set_reminder(self, rtime):
        user = self._get_tg()
        user.remind_on = rtime
        user.save()
        if rtime is None:
            self.sender.sendMessage(self.t('no_remind'))
        else:
            self.sender.sendMessage(self.t('remind_on').format(rtime))

    def _list_changesets(self):
        user = self._get_tg().user
        changesets = ch.get_user_changesets(user)
        if changesets:
            msg = '\n'.join(['{}: {}, {}'.format(
                c['id'], c['htime'], c['comment']) for c in changesets[:5]])
            self.sender.sendMessage(msg)
        else:
            self.sender.sendMessage(self.r('no_changesets'))

    def _last_changeset(self):
        user = self._get_tg().user
        changesets = ch.get_user_changesets(user)
        if changesets:
            self._register_changeset(changesets[0]['id'])
        else:
            self.sender.sendMessage(self.r('no_changesets'))

    def _set_lang(self, lang):
        supported = ch.get_supported_languages()
        if lang in supported:
            user = self._get_tg().user
            user.lang = lang
            user.save()
            self.lang = ch.load_language_from_user('telegram', user)
            self.sender.sendMessage(self.t('lang_set'))
        else:
            self.sender.sendMessage(self.t('no_such_lang').format(', '.join(sorted(supported))))

    def on_chat_message(self, msg):
        flavor, info = telepot.flance(msg)
        if flavor == 'chat' and info[0] != 'text':
            self.sender.sendMessage(self.t('only_text'))
            return
        text = msg.get('text', '').strip()
        if not text:
            return
        if text[0] == '/':
            command = text.split()
        else:
            command = [None]
        if command[0] == '/help':
            self.sender.sendMessage(self.t('help').format(web=config.BASE_URL))
        elif not self.has_user:
            no_code_msg = self.t('no_code')
            if command[0] == '/start':
                if len(command) == 1:
                    self.sender.sendMessage(no_code_msg.format(config.BASE_URL))
                    return
                hashcode = command[1]
            else:
                hashcode = text.strip()
            if len(hashcode) != 64:
                self.sender.sendMessage(no_code_msg.format(config.BASE_URL))
                return
            user = self._find_user_by_code(hashcode)
            if not user:
                self.sender.sendMessage(
                    self.t('wrong_code') + '\n' +
                    no_code_msg.format(config.BASE_URL))
                return
            Telegram.create(channel=self.id, user=user)
            self.lang = ch.load_language_from_user('telegram', user)
            self.sender.sendMessage(self.t('welcome').format(user.name))
            self._set_reminder(datetime.utcnow().strftime('%H:%M'))
            self._print_task()
        else:
            if command[0] == '/task':
                self._print_task()
            elif RE_CHANGESET.match(text):
                self._register_changeset(text)
            elif command[0] == '/list':
                self._list_changesets()
            elif command[0] == '/done':
                self._last_changeset()
            elif command[0] == '/now':
                self._set_reminder(datetime.utcnow().strftime('%H:%M'))
            elif command[0] == '/remind':
                if len(command) == 1 or not RE_TIME.match(command[1]):
                    self.sender.sendMessage(self.t('which_utc'))
                else:
                    self._set_reminder(command[1])
            elif RE_TIME.match(text):
                self._set_reminder(text)
            elif command[0] == '/stop':
                self._set_reminder(None)
            elif command[0] == '/start':
                self.sender.sendMessage(self.t('already_logged').format(self._get_tg().user.name))
            elif command[0] == '/whoami':
                self.sender.sendMessage(self.t('you_are').format(self._get_tg().user.name))
            elif command[0] == '/score':
                self._print_score()
            elif command[0] == '/lang':
                self._set_lang(None if len(command) < 2 else command[1])
            else:
                self.sender.sendMessage(self.t('unknown_cmd'))


def send_reminder(bot, hm):
    query = Telegram.select().where(Telegram.remind_on == hm)
    for tg in query:
        logging.warning('%s on %s', tg.user.name, hm)
        lang = ch.load_language_from_user('telegram', tg.user)
        task_obj = ch.get_or_create_task_for_user(tg.user)
        task = ch.load_task(task_obj.task)
        msg = '{} {}\n\n{}\n\n{}'.format(
                task['emoji'].encode('utf-8'), task['title'], task['description'],
                lang['post_changeset'].encode('utf-8'))
        try:
            bot.sendMessage(tg.channel, msg)
        except telepot.exception.TelegramError as e:
            logging.error('Could not remind user %s: %s', tg.user.name, e.description)


def send_reminders(bot):
    global last_reminder
    dnow = datetime.utcnow()
    now = [dnow.hour, dnow.minute]
    if not last_reminder:
        if os.path.exists(config.TELEGRAM_STATE):
            with open(config.TELEGRAM_STATE, 'r') as f:
                last_reminder = [int(x) for x in f.read().split(':')]
        else:
            last_reminder = [dnow.hour, dnow.minute-1]
            if last_reminder[1] < 0:
                last_reminder = [dnow.hour-1, 59]
                if last_reminder[0] < 0:
                    last_reminder[0] = 23
    if now == last_reminder:
        return
    while last_reminder != now:
        send_reminder(bot, '{:02}:{:02}'.format(*last_reminder))
        last_reminder[1] += 1
        if last_reminder[1] >= 60:
            last_reminder[0] += 1
            last_reminder[1] -= 60
            if last_reminder[0] >= 24:
                last_reminder[0] -= 24
    try:
        with open(config.TELEGRAM_STATE, 'w') as f:
            f.write('{:02}:{:02}'.format(*last_reminder))
    except IOError as e:
        logging.warn('Could not write state file: %s', e)


if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING, format='%(asctime)s %(message)s', datefmt='%H:%M:%S')
    database.connect()
    bot = telepot.DelegatorBot(config.TELEGRAM_TOKEN, [
        pave_event_space()(per_chat_id(types=['private']), create_open, Player, timeout=10),
    ])
    MessageLoop(bot).run_as_thread()
    while 1:
        send_reminders(bot)
        time.sleep(10)
