"""WSGI entry for Gunicorn / Hostinger VPS."""
from server import app

if __name__ == "__main__":
    app.run()
