#!/usr/bin/env python
from db import User
import ch_util
import sys

if len(sys.argv) < 2:
    print 'This script runs a changeset agains all the tasks, to test these.'
    print 'Usage: {} <changeset>'.format(sys.argv[0])
    sys.exit(1)

user = User.select().get()

tasks = sorted(ch_util.get_tasks(100))
for task_name in tasks:
    try:
        date, passed = ch_util.validate_changeset(
            user, ch_util.parse_changeset_id(sys.argv[1]), task_name)
        print 'Task {}: {}'.format(task_name, passed)
    except Exception as e:
        print 'Error on task {}: {}'.format(task_name, e)
        raise e
