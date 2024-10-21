from flask import Blueprint, current_app, jsonify
from app_utils import *
import logging
from services.caption_video import process_captioning
from services.authentication import authenticate
from services.gcp_toolkit import upload_to_gcs
import requests

caption_bp = Blueprint('caption', __name__)
logger = logging.getLogger(__name__)

@caption_bp.route('/caption-video', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "video_url": {"type": "string", "format": "uri"},
        "srt": {"type": "string"},
        "ass": {"type": "string"},
        "options": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "option": {"type": "string"},
                    "value": {}  # Allow any type for value
                },
                "required": ["option", "value"]
            }
        },
        "webhook_url": {"type": "string", "format": "uri"},
        "id": {"type": "string"}
    },
    "required": ["video_url"],
    "oneOf": [
        {"required": ["srt"]},
        {"required": ["ass"]}
    ],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def caption_video(job_id, data):
    video_url = data['video_url']
    caption_srt = data.get('srt')
    caption_ass = data.get('ass')
    options = data.get('options', [])
    webhook_url = data.get('webhook_url')
    id = data.get('id', job_id)

    logger.info(f"Job {id}: Received captioning request for {video_url}")
    logger.info(f"Job {id}: Options received: {options}")

    if caption_ass is not None:
        captions = caption_ass
        caption_type = "ass"
    else:
        captions = caption_srt
        caption_type = "srt"

    try:
        output_filename = process_captioning(video_url, captions, caption_type, options, id)
        logger.info(f"Job {id}: Captioning process completed successfully")

        result = {
            "message": "Captioning completed",
            "gcs_url": output_filename,  # This is the GCS URL returned by process_captioning
            "job_id": id
        }

        if webhook_url:
            try:
                webhook_response = requests.post(webhook_url, json=result)
                if webhook_response.status_code == 200:
                    logger.info(f"Job {id}: Successfully sent result to webhook: {webhook_url}")
                    return jsonify({"message": "Captioning completed and sent to webhook"}), 200
                else:
                    logger.error(f"Job {id}: Failed to send result to webhook. Status code: {webhook_response.status_code}")
                    return jsonify({"error": "Failed to send result to webhook"}), 500          
            except Exception as webhook_error:
                logger.error(f"Job {id}: Error sending result to webhook: {str(webhook_error)}")
                return jsonify({"error": "Error sending result to webhook"}), 500
        else:
            return jsonify(result), 200
        
    except Exception as e:
        error_message = f"Job {id}: Error during captioning process - {str(e)}"
        logger.error(error_message, exc_info=True)
        if webhook_url:
            try:
                requests.post(webhook_url, json={"error": error_message, "job_id": id})
            except:
                pass
        return jsonify({"error": error_message}), 500
