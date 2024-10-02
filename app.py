from flask import Flask
from flask_cors import CORS
from routes.media_to_mp3 import convert_bp
from routes.transcribe_media import transcribe_bp
from routes.combine_videos import combine_bp
from routes.audio_mixing import audio_mixing_bp
from routes.gdrive_upload import gdrive_upload_bp
from routes.authentication import auth_bp  # Import the auth_bp blueprint
from routes.caption_video import caption_bp 
from routes.summarize import summarize
from routes.transcription import transcription  # Import the transcription blueprint

app = Flask(__name__)
CORS(app)

# Register blueprints
app.register_blueprint(convert_bp)
app.register_blueprint(transcribe_bp)
app.register_blueprint(combine_bp)
app.register_blueprint(audio_mixing_bp)
app.register_blueprint(gdrive_upload_bp)
app.register_blueprint(auth_bp)  # Register the auth_bp blueprint
app.register_blueprint(caption_bp) 
app.register_blueprint(summarize)
app.register_blueprint(transcription)  # Register the transcription blueprint

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
