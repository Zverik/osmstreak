from flask import Flask

app = Flask(__name__)
app.config.from_object('config')

try:
    from flask_compress import Compress
    Compress(app)
except ImportError:
    pass

import www.streak
