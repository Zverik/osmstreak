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
import logging
import re
import telepot
import time
import ch_util as ch
from datetime import datetime
from db import database, Telegram, User
from telepot.loop import MessageLoop
from telepot.delegate import per_chat_id, create_open, pave_event_space


RE_TIME = re.compile(r'^\d?\d:\d\d$')
last_reminder = None


def desc_to_markdown(task):
    desc = task['t_description'].strip()
    desc = ch.RE_MARKUP_LINK.sub(r'[\2](\1)', desc)
    desc = ch.RE_EM.sub(r'_\1_', desc)
    return desc


def load_language(user):
    lang = ch.load_language_from_user('telegram', user)
    lang['tasks'] = ch.load_language_from_user('tasks', user)
    return lang


class Player(telepot.helper.ChatHandler):
    def __init__(self, *args, **kwargs):
        super(Player, self).__init__(*args, **kwargs)
        tg = self._get_tg()
        self.has_user = tg is not None
        user = None if tg is None else tg.user
        self.lang = load_language(user)

    def t(self, *args):
        d = self.lang
        for k in args:
            d = d[k]
        return d

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
            task = ch.load_task(task_obj.task, self.lang['tasks'])
            self.sender.sendMessage(
                u'{} {}\n\n{}\n\n{}: {}\n\n{}'.format(
                    task['emoji'], task['t_title'], desc_to_markdown(task),
                    self.t('time_left'), ch.time_until_day_ends(self.lang),
                    self.t('post_changeset')), parse_mode='Markdown')

    def _print_score(self):
        user = self._get_tg().user
        self.sender.sendMessage(self.t('n_points').format(
            user.score) + u'\n' + (u'⭐' * user.level))

    def _register_changeset(self, changeset):
        user = self._get_tg().user
        msgs, ok = ch.submit_changeset(user, changeset)
        self.sender.sendMessage('\n\n'.join(msgs))
        if ok:
            self._print_score()

    def _print_reminder(self, tg=None):
        if not tg:
            tg = self._get_tg()
        if tg.remind_on is None:
            self.sender.sendMessage(self.t('no_remind'))
        else:
            self.sender.sendMessage(self.t('remind_on').format(tg.remind_on))

    def _set_reminder(self, rtime):
        if rtime == '':
            rtime = datetime.utcnow().strftime('%H:%M')
        elif rtime and len(rtime) == 4:
            rtime = '0' + rtime
        user = self._get_tg()
        if user.remind_on != rtime:
            user.remind_on = rtime
            user.save()
        self._print_reminder(user)

    def _list_changesets(self):
        user = self._get_tg().user
        changesets = ch.get_user_changesets(user, lang=self.lang)
        if changesets:
            msg = self.t('list_header') + u'\n\n' + u'\n'.join([u'{}: {}, {}'.format(
                c['id'], c['htime'], c['comment']) for c in changesets[:5]])
            self.sender.sendMessage(msg)
        else:
            self.sender.sendMessage(self.t('no_changesets'))

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
            self.lang = load_language(user)
            self.sender.sendMessage(self.t('lang_set'))
        else:
            self.sender.sendMessage(self.t('no_such_lang').format(u', '.join(sorted(supported))))

    def _send_help(self):
        self.sender.sendMessage(self.t('help').format(web=config.BASE_URL))

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
            command[0] = command[0].lower()
        else:
            command = [None]
        if command[0] == '/help':
            self._send_help()
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
            self.lang = load_language(user)
            self.sender.sendMessage(self.t('welcome').format(user.name))
            self._set_reminder('')
            self._print_task()
        else:
            if command[0] == '/task':
                self._print_task()
            elif ch.RE_CHANGESET.match(text):
                self._register_changeset(text)
            elif command[0] == '/list':
                self._list_changesets()
            elif command[0] == '/done':
                self._last_changeset()
            elif command[0] == '/now':
                self._set_reminder('')
            elif command[0] == '/remind':
                if len(command) == 1 or not RE_TIME.match(command[1]):
                    self.sender.sendMessage(self.t('which_utc'))
                else:
                    self._set_reminder(command[1])
            elif RE_TIME.match(text):
                self._set_reminder(text)
            elif command[0] == '/when':
                self._print_reminder()
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
        lang = load_language(tg.user)
        task_obj = ch.get_or_create_task_for_user(tg.user)
        if task_obj.changeset is not None:
            continue
        task = ch.load_task(task_obj.task, lang['tasks'])
        msg = u'{} {}\n\n{}\n\n{}'.format(
                task['emoji'], task['t_title'], desc_to_markdown(task),
                lang['post_changeset'])
        try:
            bot.sendMessage(tg.channel, msg, parse_mode='Markdown')
        except telepot.exception.TelegramError as e:
            try:
                bot.sendMessage(tg.channel, msg)
                logging.error('Failed to send markdown, but text worked. Task %s, msg: %s',
                              task_obj.task, msg)
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
