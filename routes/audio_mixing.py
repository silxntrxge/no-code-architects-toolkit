from flask import Blueprint, request, jsonify
from flask import current_app
from app_utils import *
import logging
from services.audio_mixing import process_audio_mixing
from services.authentication import authenticate
import requests

from services.gcp_toolkit import upload_to_gcs  # Ensure this import is present

audio_mixing_bp = Blueprint('audio_mixing', __name__)
logger = logging.getLogger(__name__)

@audio_mixing_bp.route('/audio-mixing', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "video_url": {"type": "string", "format": "uri"},
        "audio_url": {"type": "string", "format": "uri"},
        "video_vol": {"type": "number", "minimum": 0, "maximum": 100},
        "audio_vol": {"type": "number", "minimum": 0, "maximum": 100},
        "output_length": {"type": "string", "enum": ["video", "audio"]},
        "webhook_url": {"type": "string", "format": "uri"},
        "id": {"type": "string"}
    },
    "required": ["video_url", "audio_url"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def audio_mixing(job_id, data):
    
    video_url = data.get('video_url')
    audio_url = data.get('audio_url')
    video_vol = data.get('video_vol', 100)
    audio_vol = data.get('audio_vol', 100)
    output_length = data.get('output_length', 'video')
    webhook_url = data.get('webhook_url')
    id = data.get('id')

    logger.info(f"Job {job_id}: Received audio mixing request for {video_url} and {audio_url}")

    try:
        output_filename = process_audio_mixing(
            video_url, audio_url, video_vol, audio_vol, output_length, job_id, webhook_url
        )
        gcs_url = upload_to_gcs(output_filename)

        result = {
            "message": "Audio mixing completed",
            "gcs_url": gcs_url,
            "job_id": job_id
        }

        if webhook_url:
            try:
                webhook_response = requests.post(webhook_url, json=result)
                if webhook_response.status_code == 200:
                    logger.info(f"Job {job_id}: Successfully sent result to webhook: {webhook_url}")
                    return jsonify({"message": "Audio mixing completed and sent to webhook"}), 200
                else:
                    logger.error(f"Job {job_id}: Failed to send result to webhook. Status code: {webhook_response.status_code}")
                    return jsonify({"error": "Failed to send result to webhook"}), 500
            except Exception as webhook_error:
                logger.error(f"Job {job_id}: Error sending result to webhook: {str(webhook_error)}")
                return jsonify({"error": "Error sending result to webhook"}), 500
        else:
            return jsonify(result), 200
        
    except Exception as e:
        error_message = f"Job {job_id}: Error during audio mixing process - {str(e)}"
        logger.error(error_message)
        if webhook_url:
            try:
                requests.post(webhook_url, json={"error": error_message, "job_id": job_id})
            except:
                pass
        return jsonify({"error": error_message}), 500

