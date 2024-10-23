from flask import Blueprint, request, jsonify
from services.transcription import perform_transcription
from app_utils import validate_payload, queue_task_wrapper
from services.authentication import authenticate
from services.gcp_toolkit import upload_to_gcs
import requests
import logging
import os

transcription_bp = Blueprint('transcription', __name__)
logger = logging.getLogger(__name__)

@transcription_bp.route('/transcribe', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "media_url": {"type": "string", "format": "uri"},
        "webhook": {"type": "string", "format": "uri"},
        "id": {"type": "string"},
        "option": {"type": ["string", "integer"]},
        "output": {"type": "string", "enum": ["transcript", "srt", "vtt", "ass"]}
    },
    "required": ["media_url"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def transcribe(job_id, data):
    media_url = data['media_url']
    webhook_url = data.get('webhook')
    id = data.get('id', job_id)
    words_per_subtitle = data.get('option')
    output_type = data.get('output', 'transcript')

    logger.info(f"Job {id}: Received transcription request for {media_url}")

    try:
        if words_per_subtitle:
            words_per_subtitle = int(words_per_subtitle)
        else:
            words_per_subtitle = None

        result = perform_transcription(media_url, words_per_subtitle, output_type)

        if 'ass_file_url' in result:
            return jsonify({'ass_file_url': result['ass_file_url']})
        elif 'srt_file_url' in result:
            return jsonify({'srt_file_url': result['srt_file_url']})
        elif 'vtt_file_url' in result:
            return jsonify({'vtt_file_url': result['vtt_file_url']})
        else:
            return jsonify(result)

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
