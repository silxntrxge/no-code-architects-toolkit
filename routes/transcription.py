from flask import Blueprint, request, jsonify
from services.transcription import perform_transcription
import requests
import logging

transcription_bp = Blueprint('transcription', __name__)
logger = logging.getLogger(__name__)

@transcription_bp.route('/transcribe', methods=['POST'])
def transcribe():
    data = request.get_json()
    if not data or 'audio_file' not in data or 'webhook' not in data:
        return jsonify({"error": "Missing audio_file or webhook"}), 400
    
    try:
        transcription_result = perform_transcription(data['audio_file'])
        
        # Send the result to the webhook URL
        webhook_response = requests.post(
            data['webhook'],
            json={
                "timestamps": transcription_result['timestamps'],
                "transcription": transcription_result['text_segments']
            }
        )
        
        if webhook_response.status_code == 200:
            logger.info(f"Successfully sent transcription to webhook: {data['webhook']}")
            return jsonify({"message": "Transcription completed and sent to webhook"}), 200
        else:
            logger.error(f"Failed to send transcription to webhook. Status code: {webhook_response.status_code}")
            return jsonify({"error": "Failed to send transcription to webhook"}), 500
    
    except Exception as e:
        logger.error(f"Transcription error: {str(e)}")
        return jsonify({"error": str(e)}), 500