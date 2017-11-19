import os
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

DEBUG = True

DATABASE_URI = 'sqlite:///' + os.path.join(BASE_DIR, 'streak.db')
# DATABASE_URI = 'postgresql://localhost/osmstreak'

LEVELS = [10, 70, 500, 2700]

# Override these (and anything else) in config_local.py
OAUTH_KEY = ''
OAUTH_SECRET = ''
SECRET_KEY = 'sdkjfhsfljhsadf'

try:
    from config_local import *
except ImportError:
    pass
