import os
import whisper
import srt
from datetime import timedelta
import logging
import requests
import nltk
from nltk.tokenize import word_tokenize, sent_tokenize

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Download necessary NLTK data
nltk.download('punkt', quiet=True)
nltk.download('punkt_tab', quiet=True)

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

def split_sentence(sentence, start_time, end_time):
    """Split a sentence into two parts and calculate their durations."""
    words = sentence.split()
    total_duration = end_time - start_time
    mid_point = len(words) // 2

    # Find the best split point
    best_split = mid_point
    for i in range(max(1, mid_point - 3), min(len(words) - 1, mid_point + 4)):
        if words[i].endswith((',', '.', '!', '?')):
            best_split = i + 1
            break

    part1 = ' '.join(words[:best_split])
    part2 = ' '.join(words[best_split:])

    # Calculate durations based on word count ratio
    ratio = len(words[:best_split]) / len(words)
    duration1 = round(total_duration * ratio, 2)
    duration2 = round(total_duration - duration1, 2)

    return part1, part2, duration1, duration2

def create_word_level_srt(segments, words_per_subtitle):
    """Create SRT content with a specified number of words per subtitle."""
    srt_entries = []
    word_count = 0
    current_words = []
    start_time = None
    
    for segment in segments:
        words = segment['text'].split()
        segment_start = segment['start']
        segment_end = segment['end']
        word_duration = (segment_end - segment_start) / len(words)
        
        for word in words:
            if start_time is None:
                start_time = segment_start
            
            current_words.append(word)
            word_count += 1
            
            if word_count == words_per_subtitle:
                end_time = start_time + (word_duration * words_per_subtitle)
                srt_entries.append({
                    'start': start_time,
                    'end': end_time,
                    'text': ' '.join(current_words)
                })
                start_time = None
                current_words = []
                word_count = 0
            
            segment_start += word_duration
    
    # Add any remaining words
    if current_words:
        srt_entries.append({
            'start': start_time,
            'end': segment_end,
            'text': ' '.join(current_words)
        })
    
    # Format SRT content
    srt_content = []
    for i, entry in enumerate(srt_entries, start=1):
        start = format_timestamp(entry['start']).replace('.', ',')
        end = format_timestamp(entry['end']).replace('.', ',')
        srt_content.append(f"{i}\n{start} --> {end}\n{entry['text']}")
    
    return "\n\n".join(srt_content)

def process_transcription(audio_path, output_type, words_per_subtitle=None):
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
            duration_sentences = []
            duration_splitsentence = []
            srt_format = []  # New list for SRT format
            for i, segment in enumerate(result['segments'], start=1):
                start_time = segment['start']
                end_time = segment['end']
                text = segment['text'].strip()
                
                # Split the segment into sentences
                sentences = sent_tokenize(text)
                
                for sentence in sentences:
                    formatted_start = format_timestamp(start_time)
                    formatted_end = format_timestamp(end_time)
                    transcript.append(f"{formatted_start} - {formatted_end}: {sentence}")
                    timestamps.append(f"{formatted_start}-{formatted_end}")
                    text_segments.append(sentence)
                    duration = end_time - start_time
                    duration_sentences.append(str(round(duration, 2)))
                    
                    # Split sentence analysis
                    part1, part2, duration1, duration2 = split_sentence(sentence, start_time, end_time)
                    duration_splitsentence.extend([str(duration1), str(duration2)])
                    
                    # Create SRT format entry
                    srt_entry = f"{i}\n{formatted_start.replace('.', ',')} --> {formatted_end.replace('.', ',')}\n{sentence}"
                    srt_format.append(srt_entry)
                    
                    # Update start_time for the next sentence
                    start_time = end_time
                    i += 1  # Increment counter for next SRT entry
            
            if words_per_subtitle:
                srt_format = create_word_level_srt(result['segments'], words_per_subtitle)
            else:
                srt_format = "\n\n".join(srt_format)

            output = {
                'transcript': "\n".join(transcript),
                'timestamps': timestamps,
                'text_segments': text_segments,
                'duration_sentences': duration_sentences,
                'duration_splitsentence': duration_splitsentence,
                'srt_format': srt_format
            }
            logger.info("Transcript with timestamps, sentence durations, split sentence durations, and SRT format generated")
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

def perform_transcription(audio_file, words_per_subtitle=None):
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
        transcription = process_transcription(audio_file, 'transcript', words_per_subtitle)
        
        # Clean up temporary file if it was created
        if audio_file == 'temp_audio_file':
            os.remove(audio_file)
            logger.info("Temporary file removed")

        logger.info("Transcription completed successfully")
        return {
            'timestamps': transcription['timestamps'],
            'text_segments': transcription['text_segments'],
            'duration_sentences': transcription['duration_sentences'],
            'duration_splitsentence': transcription['duration_splitsentence'],
            'srt_format': transcription['srt_format']
        }
    except Exception as e:
        logger.error(f"Error during transcription: {str(e)}")
        raise
