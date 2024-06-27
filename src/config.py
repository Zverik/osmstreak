import os
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

DEBUG = False

# Override these (and anything else) in config_local.py
TELEGRAM_STATE = os.path.join(BASE_DIR, '..', 'telegram.state')
DATABASE_URI = 'sqlite:///' + os.path.join(BASE_DIR, '..', 'streak.db')
BASE_URL = 'http://localhost:5000'
EMAIL_FROM = 'streak@localhost'

LEVELS = [10, 70, 500, 2700]

OAUTH_KEY = ''
OAUTH_SECRET = ''
TELEGRAM_TOKEN = ''
SECRET_KEY = 'sdkjfhsfljhsadf'

try:
    from .config_local import *
except ImportError:
    pass
