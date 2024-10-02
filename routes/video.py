from flask import Blueprint, jsonify
from app_utils import validate_payload, queue_task_wrapper
import logging
from services.ffmpeg_toolkit import process_video_combination
from services.authentication import authenticate
import requests

combine_bp = Blueprint('combine', __name__)
logger = logging.getLogger(__name__)

@combine_bp.route('/combine-videos', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "video_urls": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "video_url": {"type": "string", "format": "uri"}
                },
                "required": ["video_url"]
            },
            "minItems": 1
        },
        "webhook_url": {"type": "string", "format": "uri"},
        "id": {"type": "string"}
    },
    "required": ["video_urls"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def combine_videos(job_id, data):
    media_urls = [item['video_url'] for item in data['video_urls']]
    webhook_url = data.get('webhook_url')
    id = data.get('id')

    logger.info(f"Job {job_id}: Received combine-videos request for {len(media_urls)} videos")

    try:
        gcs_url = process_video_combination(media_urls, job_id)
        logger.info(f"Job {job_id}: Video combination process completed successfully")

        if webhook_url:
            # Send the result to the webhook URL
            webhook_response = requests.post(webhook_url, json={"gcs_url": gcs_url, "job_id": job_id})

            if webhook_response.status_code == 200:
                logger.info(f"Job {job_id}: Successfully sent result to webhook: {webhook_url}")
            else:
                logger.error(f"Job {job_id}: Failed to send result to webhook. Status code: {webhook_response.status_code}")

        return jsonify({"gcs_url": gcs_url}), 200

    except Exception as e:
        logger.error(f"Job {job_id}: Error during video combination process - {str(e)}")
        return jsonify({"error": str(e)}), 500