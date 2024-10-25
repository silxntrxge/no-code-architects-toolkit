from flask import Blueprint, request, jsonify
from services.transcription import process_transcription  # Ensure correct import
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
        "audio_file": {"type": "string", "format": "uri"},
        "webhook": {"type": "string", "format": "uri"},
        "id": {"type": "string"},
        "option": {"type": ["string", "integer"]},
        "output": {"type": "string", "enum": ["transcript", "srt", "vtt", "ass"]}
    },
    "required": ["audio_file"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def transcribe(job_id, data):
    audio_file = data['audio_file']
    webhook_url = data.get('webhook')
    id = data.get('id', job_id)
    words_per_subtitle = data.get('option')
    output_type = data.get('output', 'transcript')

    logger.info(f"Job {id}: Received transcription request for {audio_file}")

    try:
        if words_per_subtitle:
            words_per_subtitle = int(words_per_subtitle)
        else:
            words_per_subtitle = None

        transcription = process_transcription(audio_file, output_type, words_per_subtitle=words_per_subtitle)

        if output_type in ['srt', 'vtt', 'ass']:
            # Handle the case where transcription is a file path
            gcs_url = upload_to_gcs(transcription)
            os.remove(transcription)  # Remove the temporary file after uploading
            
            # Get additional transcription details
            transcript_details = process_transcription(audio_file, 'transcript', words_per_subtitle=words_per_subtitle)
            
            result = {
                "message": f"Transcription {output_type.upper()} completed.",
                f"{output_type}_file_url": gcs_url,
                "timestamps": transcript_details['timestamps'],
                "transcription": transcript_details['text_segments'],
                "durations": transcript_details['duration_sentences'],
                "split_sentence_durations": transcript_details['duration_splitsentence'],
                "srt_format": transcript_details['srt_format'],
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
        # Print all relevant parameters in the error message
        error_details = {
            "error": str(e),
            "job_id": id,
            "audio_file": audio_file,
            "output_type": output_type,
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
        return jsonify({"error": error_message}), 500
