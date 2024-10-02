from flask import Blueprint, request, jsonify
from services.transcription import process_transcription
import base64
import requests
import os

transcription = Blueprint('transcription', __name__)

@transcription.route('/transcribe', methods=['POST'])
def transcribe_audio_route():
    try:
        data = request.get_json()
        audio_file = data.get('audio_file')
        webhook_url = data.get('webhook')

        if not audio_file or not webhook_url:
            return jsonify({'error': 'Missing audio_file or webhook URL'}), 400

        # Decode the base64-encoded audio file
        audio_data = base64.b64decode(audio_file)
        
        # Save the audio file temporarily
        temp_audio_path = 'temp_audio.wav'
        with open(temp_audio_path, 'wb') as f:
            f.write(audio_data)

        # Process transcription
        srt_content = process_transcription(temp_audio_path, 'srt')

        # Send SRT to the webhook
        response = requests.post(webhook_url, json={'srt': srt_content})
        if response.status_code == 200:
            return jsonify({'status': 'success'}), 200
        else:
            return jsonify({'error': 'Failed to send data to webhook'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        # Clean up the temporary audio file
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)