from flask import Blueprint, request, jsonify
from services.transcription import perform_transcription
from app_utils import validate_payload, queue_task_wrapper
from services.authentication import authenticate
import requests
import logging

transcription_bp = Blueprint('transcription', __name__)
logger = logging.getLogger(__name__)

@transcription_bp.route('/transcribe-media', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "media_url": {"type": "string", "format": "uri"},
        "output": {"type": "string", "enum": ["transcript", "srt"]},
        "webhook_url": {"type": "string", "format": "uri"},
        "id": {"type": "string"}
    },
    "required": ["media_url"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def transcribe(job_id, data):
    media_url = data['media_url']
    output_type = data.get('output', 'transcript')
    webhook_url = data.get('webhook_url')

    try:
        transcription = perform_transcription(media_url)
        result = {
            "message": "Transcription completed",
            "timestamps": transcription['timestamps'],
            "transcription": transcription['text_segments'],
            "durations": transcription['durations'],
            "job_id": job_id
        }

        if webhook_url:
            try:
                webhook_response = requests.post(webhook_url, json=result)
                if webhook_response.status_code == 200:
                    logger.info(f"Job {job_id}: Successfully sent transcription to webhook: {webhook_url}")
                    return jsonify({"message": "Transcription completed and sent to webhook"}), 200
                else:
                    logger.error(f"Job {job_id}: Failed to send transcription to webhook. Status code: {webhook_response.status_code}")
                    return jsonify({"error": "Failed to send transcription to webhook"}), 500
            except Exception as webhook_error:
                logger.error(f"Job {job_id}: Error sending transcription to webhook: {str(webhook_error)}")
                return jsonify({"error": "Error sending transcription to webhook"}), 500
        else:
            return jsonify(result), 200

    except Exception as e:
        error_message = f"Job {job_id}: Transcription error - {str(e)}"
        logger.error(error_message)
        if webhook_url:
            try:
                requests.post(webhook_url, json={"error": error_message, "job_id": job_id})
            except:
                pass
        return jsonify({"error": error_message}), 500