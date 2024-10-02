from flask import Blueprint, request, jsonify
from services.transcription import perform_transcription
from app_utils import validate_payload, queue_task_wrapper
from services.authentication import authenticate
import requests
import logging

transcription_bp = Blueprint('transcription', __name__)
logger = logging.getLogger(__name__)

@transcription_bp.route('/transcribe', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "audio_file": {"type": "string", "format": "uri"},
        "webhook": {"type": "string", "format": "uri"},
        "id": {"type": "string"}
    },
    "required": ["audio_file"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def transcribe(job_id, data):
    audio_file = data['audio_file']
    webhook_url = data.get('webhook')
    id = data.get('id', job_id)

    logger.info(f"Job {id}: Received transcription request for {audio_file}")

    try:
        transcription = perform_transcription(audio_file)
        result = {
            "message": "Transcription completed",
            "timestamps": transcription['timestamps'],
            "transcription": transcription['text_segments'],
            "durations": transcription['durations'],
            "job_id": id
        }

        if webhook_url:
            try:
                webhook_response = requests.post(webhook_url, json=result)
                if webhook_response.status_code == 200:
                    logger.info(f"Job {id}: Successfully sent transcription to webhook: {webhook_url}")
                    return jsonify({"message": "Transcription completed and sent to webhook"}), 200
                else:
                    logger.error(f"Job {id}: Failed to send transcription to webhook. Status code: {webhook_response.status_code}")
                    return jsonify({"error": "Failed to send transcription to webhook"}), 500
            except Exception as webhook_error:
                logger.error(f"Job {id}: Error sending transcription to webhook: {str(webhook_error)}")
                return jsonify({"error": "Error sending transcription to webhook"}), 500
        else:
            return jsonify(result), 200

    except Exception as e:
        error_message = f"Job {id}: Transcription error - {str(e)}"
        logger.error(error_message)
        if webhook_url:
            try:
                requests.post(webhook_url, json={"error": error_message, "job_id": id})
            except:
                pass
        return jsonify({"error": error_message}), 500