# routes/__init__.py
# This file makes the routes directory a Python package.

from flask import Flask
from routes.transcription import transcription_bp
from routes.video import combine_bp
from routes.media_to_mp3 import convert_bp
# Import other blueprints as needed

def init_app(app):
    app.register_blueprint(transcription_bp)
    app.register_blueprint(combine_bp)
    app.register_blueprint(convert_bp)
    # Register other blueprints as needed