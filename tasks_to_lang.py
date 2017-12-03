#!/usr/bin/env python
import config
import os
import ch_util as ch
from ruamel.yaml import YAML

lang = {}
for t in sorted(ch.get_tasks(100)):
    t_name = t.split('_', 1)[1]
    task = ch.load_task(t)
    lang[t_name] = {'title': task['title'], 'description': task['description']}

yaml = YAML()
with open(os.path.join(config.BASE_DIR, 'lang', 'tasks', 'en.yaml'), 'w') as f:
    yaml.dump(lang, f)
