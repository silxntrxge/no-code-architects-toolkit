import os
import whisper
import srt
from datetime import timedelta
import logging

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def process_transcription(audio_path, output_type):
    """Transcribe audio and return the transcript or SRT content."""
    logger.info(f"Starting transcription for: {audio_path} with output type: {output_type}")

    try:
        model = whisper.load_model("base")
        logger.info("Whisper model loaded")

        result = model.transcribe(audio_path)
        logger.info("Transcription completed")

        if output_type == 'transcript':
            output = result['text']
            logger.info("Transcript generated")
        elif output_type == 'srt':
            srt_subtitles = []
            for i, segment in enumerate(result['segments'], start=1):
                start = timedelta(seconds=segment['start'])
                end = timedelta(seconds=segment['end'])
                text = segment['text'].strip()
                srt_subtitles.append(srt.Subtitle(i, start, end, text))
            output = srt.compose(srt_subtitles)
            logger.info("SRT content generated")
        else:
            raise ValueError("Invalid output type. Must be 'transcript' or 'srt'.")

        logger.info("Transcription successful")
        return output
    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        raise