#!.venv/bin/python
from src.www import app
from src.db import migrate
migrate()
app.run(debug=True)
