#!/usr/bin/env python
from www import app
from db import create_tables
create_tables()
app.run(debug=True)
