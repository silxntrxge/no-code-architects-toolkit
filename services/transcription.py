import os
import whisper
import srt
from datetime import timedelta
import logging
import requests

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def format_timestamp(seconds):
    """Convert seconds to HH:MM:SS.mmm format."""
    td = timedelta(seconds=seconds)
    milliseconds = int(td.microseconds / 1000)
    return f"{td.seconds // 3600:02d}:{(td.seconds % 3600) // 60:02d}:{td.seconds % 60:02d}.{milliseconds:03d}"

def calculate_duration(start, end):
    """Calculate duration between two timestamps in seconds."""
    start_parts = start.split(':')
    end_parts = end.split(':')
    start_seconds = int(start_parts[0]) * 3600 + int(start_parts[1]) * 60 + float(start_parts[2])
    end_seconds = int(end_parts[0]) * 3600 + int(end_parts[1]) * 60 + float(end_parts[2])
    return round(end_seconds - start_seconds, 2)

def process_transcription(audio_path, output_type):
    """Transcribe audio and return the transcript or SRT content."""
    logger.info(f"Starting transcription for: {audio_path} with output type: {output_type}")

    try:
        model = whisper.load_model("base")
        logger.info("Whisper model loaded successfully")

        result = model.transcribe(audio_path)
        logger.info("Transcription completed successfully")

        if output_type == 'transcript':
            transcript = []
            timestamps = []
            text_segments = []
            durations = []
            for segment in result['segments']:
                start_time = format_timestamp(segment['start'])
                end_time = format_timestamp(segment['end'])
                text = segment['text'].strip()
                transcript.append(f"{start_time} - {end_time}: {text}")
                timestamps.append(f"{start_time}-{end_time}")
                text_segments.append(text)
                durations.append(str(calculate_duration(start_time, end_time)))
            
            output = {
                'transcript': "\n".join(transcript),
                'timestamps': timestamps,
                'text_segments': text_segments,
                'durations': durations
            }
            logger.info("Transcript with timestamps and durations per sentence generated")
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

        logger.info("Transcription process completed successfully")
        return output
    except Exception as e:
        logger.error(f"Error during transcription: {str(e)}")
        raise

def perform_transcription(audio_file):
    logger.info(f"Starting transcription for file: {audio_file}")
    try:
        # Download the file if it's a URL
        if audio_file.startswith('http'):
            logger.info(f"Downloading file from URL: {audio_file}")
            response = requests.get(audio_file)
            if response.status_code == 200:
                temp_file = 'temp_audio_file'
                with open(temp_file, 'wb') as f:
                    f.write(response.content)
                audio_file = temp_file
                logger.info(f"File downloaded successfully to: {temp_file}")
            else:
                raise Exception(f"Failed to download file. Status code: {response.status_code}")

        # Perform transcription
        transcription = process_transcription(audio_file, 'transcript')
        
        # Clean up temporary file if it was created
        if audio_file == 'temp_audio_file':
            os.remove(audio_file)
            logger.info("Temporary file removed")

        logger.info("Transcription completed successfully")
        return transcription
    except Exception as e:
        logger.error(f"Error during transcription: {str(e)}")
        raise