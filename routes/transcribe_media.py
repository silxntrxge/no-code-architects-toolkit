from flask import Blueprint, request, jsonify
from services.transcription import process_transcription
from app_utils import validate_payload, queue_task_wrapper
from services.authentication import authenticate
from services.gcp_toolkit import upload_to_gcs
import requests
import logging
import os

transcribe_bp = Blueprint('transcribe', __name__)
logger = logging.getLogger(__name__)

@transcribe_bp.route('/transcribe-media', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "media_url": {"type": "string", "format": "uri"},
        "webhook_url": {"type": "string", "format": "uri"},
        "id": {"type": "string"},
        "option": {"type": ["string", "integer"]},
        "output": {"type": "string", "enum": ["transcript", "srt", "vtt", "ass"]}
    },
    "required": ["media_url"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def transcribe_media(job_id, data):
    media_url = data['media_url']
    webhook_url = data.get('webhook_url')
    id = data.get('id', job_id)
    words_per_subtitle = data.get('option')
    output = data.get('output', 'transcript')

    logger.info(f"Job {id}: Received transcription request for {media_url}")

    try:
        if words_per_subtitle:
            words_per_subtitle = int(words_per_subtitle)
        else:
            words_per_subtitle = None

        # Get transcription result
        transcription = process_transcription(media_url, output, words_per_subtitle=words_per_subtitle)
        
        # Initialize result dictionary
        result = {
            "job_id": id,
            "message": f"Transcription {output.upper() if output != 'transcript' else ''} completed."
        }

        if output in ['srt', 'vtt', 'ass']:
            # Handle subtitle file outputs
            cloud_url = upload_to_gcs(transcription)
            os.remove(transcription)  # Remove the temporary file after uploading
            
            # Get additional transcription details
            transcript_details = process_transcription(media_url, 'transcript', words_per_subtitle=words_per_subtitle)
            
            # Add subtitle specific information
            result.update({
                f"{output}_file_url": cloud_url,
                "timestamps": transcript_details['timestamps'],
                "transcription": transcript_details['text_segments'],
                "durations": transcript_details['duration_sentences'],
                "split_sentence_durations": transcript_details['duration_splitsentence'],
                "split_sentences": transcript_details['split_sentences'],
                "srt_format": transcript_details['srt_format']
            })
        else:
            # Handle transcript output
            result.update({
                "timestamps": transcription['timestamps'],
                "transcription": transcription['text_segments'],
                "durations": transcription['duration_sentences'],
                "split_sentence_durations": transcription['duration_splitsentence'],
                "split_sentences": transcription['split_sentences'],
                "srt_format": transcription['srt_format']
            })

        logger.info(f"Job {id}: Successfully processed transcription")

        if webhook_url:
            try:
                webhook_response = requests.post(webhook_url, json=result)
                if webhook_response.status_code == 200:
                    logger.info(f"Job {id}: Successfully sent transcription to webhook: {webhook_url}")
                    return "Transcription completed and sent to webhook", "/transcribe-media", 200
                else:
                    logger.error(f"Job {id}: Failed to send transcription to webhook. Status code: {webhook_response.status_code}")
                    return "Failed to send transcription to webhook", "/transcribe-media", 500
            except Exception as webhook_error:
                logger.error(f"Job {id}: Error sending transcription to webhook: {str(webhook_error)}")
                return "Error sending transcription to webhook", "/transcribe-media", 500
        
        return result, "/transcribe-media", 200

    except Exception as e:
        error_details = {
            "error": str(e),
            "job_id": id,
            "media_url": media_url,
            "output": output,
            "webhook_url": webhook_url,
            "words_per_subtitle": words_per_subtitle
        }
        error_message = f"Job {id}: Transcription error - {error_details}"
        logger.error(error_message)
        if webhook_url:
            try:
                requests.post(webhook_url, json={"error": error_message, "job_id": id})
            except:
                pass
        return error_message, "/transcribe-media", 500