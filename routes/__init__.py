# routes/__init__.py
# This file makes the routes directory a Python package.

from flask import Flask
from routes.transcription import transcription_bp
from routes.combine_videos import combine_bp
from routes.media_to_mp3 import convert_bp
from routes.caption_video import caption_bp
from routes.gdrive_upload import gdrive_upload_bp
from routes.audio_mixing import audio_mixing_bp

def init_app(app):
    app.register_blueprint(transcription_bp)
    app.register_blueprint(combine_bp)
    app.register_blueprint(convert_bp)
    app.register_blueprint(caption_bp)
    app.register_blueprint(gdrive_upload_bp)
    app.register_blueprint(audio_mixing_bp)