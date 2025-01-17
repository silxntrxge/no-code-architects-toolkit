from flask import Blueprint
from app_utils import *
import logging
from services.v1.video.concatenate import process_video_concatenate
from services.authentication import authenticate
from services.cloud_storage import upload_file

v1_video_concatenate_bp = Blueprint('v1_video_concatenate', __name__)
logger = logging.getLogger(__name__)

@v1_video_concatenate_bp.route('/v1/video/concatenate', methods=['POST'])
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
    media_urls = data['video_urls']
    webhook_url = data.get('webhook_url')
    id = data.get('id')

    logger.info(f"Job {job_id}: Received combine-videos request for {len(media_urls)} videos")

    try:
        output_file = process_video_concatenate(media_urls, job_id)
        logger.info(f"Job {job_id}: Video combination process completed successfully")

        cloud_url = upload_file(output_file)
        logger.info(f"Job {job_id}: Combined video uploaded to cloud storage: {cloud_url}")

        return cloud_url, "/v1/video/concatenate", 200

    except Exception as e:
        logger.error(f"Job {job_id}: Error during video combination process - {str(e)}")
        return str(e), "/v1/video/concatenate", 500