#!/usr/bin/env python
from .www import app
from .db import migrate
migrate()
app.run(debug=True)
