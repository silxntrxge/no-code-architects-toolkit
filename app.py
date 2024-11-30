from flask import Flask, jsonify
from flask_cors import CORS
from routes.media_to_mp3 import convert_bp
from routes.transcription import transcription_bp
from routes.combine_videos import combine_bp
from routes.audio_mixing import audio_mixing_bp
from routes.gdrive_upload import gdrive_upload_bp
from routes.caption_video import caption_bp
from services.gcp_toolkit import init_storage_client
import logging
import traceback

app = Flask(__name__)
CORS(app)

# Initialize storage clients
init_storage_client()

# Register blueprints
app.register_blueprint(convert_bp)
app.register_blueprint(transcription_bp)
app.register_blueprint(combine_bp)
app.register_blueprint(audio_mixing_bp)
app.register_blueprint(gdrive_upload_bp)
app.register_blueprint(caption_bp)

@app.errorhandler(Exception)
def handle_exception(e):
    # Log the full traceback
    logging.error("Unhandled exception: %s", traceback.format_exc())
    # You can also return a custom error response here if needed
    return {"error": "An unexpected error occurred"}, 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
