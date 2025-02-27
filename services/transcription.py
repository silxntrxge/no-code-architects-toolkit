import os
import whisper
import srt
from datetime import timedelta
from whisper.utils import WriteSRT, WriteVTT
from services.file_management import download_file
from services.gcp_toolkit import upload_to_gcs
import logging
import requests
import nltk
from nltk.tokenize import word_tokenize, sent_tokenize
import uuid
import tempfile

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Download necessary NLTK data
nltk.download('punkt', quiet=True)
nltk.download('punkt_tab', quiet=True)

# Set the default local storage directory
STORAGE_PATH = "/tmp/"

def process_transcription(media_url, output_type, max_chars=56, language=None):
    """Transcribe media and return the transcript, SRT or ASS file path."""
    logger.info(f"Starting transcription for media URL: {media_url} with output type: {output_type}")
    input_filename = download_file(media_url, os.path.join(STORAGE_PATH, 'input_media'))
    logger.info(f"Downloaded media to local file: {input_filename}")

    try:
        model = whisper.load_model("base")
        logger.info("Loaded Whisper model")

        if output_type == 'transcript':
            result = model.transcribe(input_filename, language=language)
            output = result['text']
            logger.info("Generated transcript output")
        elif output_type in ['srt', 'vtt']:
            result = model.transcribe(input_filename)
            srt_subtitles = []
            for i, segment in enumerate(result['segments'], start=1):
                start = timedelta(seconds=segment['start'])
                end = timedelta(seconds=segment['end'])
                text = segment['text'].strip()
                srt_subtitles.append(srt.Subtitle(i, start, end, text))
            
            output_content = srt.compose(srt_subtitles)
            
            # Write the output to a file
            output_filename = os.path.join(STORAGE_PATH, f"{uuid.uuid4()}.{output_type}")
            with open(output_filename, 'w') as f:
                f.write(output_content)
            
            output = output_filename
            logger.info(f"Generated {output_type.upper()} output: {output}")

        elif output_type == 'ass':
            result = model.transcribe(
                input_filename,
                word_timestamps=True,
                task='transcribe',
                verbose=False
            )
            logger.info("Transcription completed with word-level timestamps")
            # Generate ASS subtitle content
            ass_content = generate_ass_subtitle(result, max_chars)
            logger.info("Generated ASS subtitle content")
            
            output_content = ass_content

            # Write the ASS content to a file
            output_filename = os.path.join(STORAGE_PATH, f"{uuid.uuid4()}.{output_type}")
            with open(output_filename, 'w') as f:
               f.write(output_content) 
            output = output_filename
            logger.info(f"Generated {output_type.upper()} output: {output}")
        else:
            raise ValueError("Invalid output type. Must be 'transcript', 'srt', or 'vtt'.")

        os.remove(input_filename)
        logger.info(f"Removed local file: {input_filename}")
        logger.info(f"Transcription successful, output type: {output_type}")
        return output
    except Exception as e:
        logger.error(f"Transcription failed: {str(e)}")
        raise

def create_word_limited_captions(words, words_per_line):
    """Create word-limited captions while preserving moving highlight functionality."""
    caption_groups = []
    
    # Group words into chunks of specified size
    for i in range(0, len(words), words_per_line):
        chunk = words[i:i + words_per_line]
        
        # Get timing for the chunk
        start_time = chunk[0]['start']
        end_time = chunk[-1]['end']
        
        # Store the chunk info
        caption_groups.append({
            'words': chunk,
            'start': start_time,
            'end': end_time
        })
    
    return caption_groups

def generate_ass_subtitle(result, max_chars, words_per_line=None):
    """Generate ASS subtitle content with highlighted current words, showing one line at a time."""
    logger.info("Generate ASS subtitle content with highlighted current words")
    ass_content = ""

    def format_time(t):
        hours = int(t // 3600)
        minutes = int((t % 3600) // 60)
        seconds = int(t % 60)
        centiseconds = int(round((t - int(t)) * 100))
        return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"

    for segment in result['segments']:
        words = segment.get('words', [])
        if not words:
            continue

        if words_per_line:
            # Get word-limited groups
            caption_groups = create_word_limited_captions(words, words_per_line)
            
            # Process each group
            for group in caption_groups:
                group_words = group['words']
                
                # Generate moving highlight for each word in the group
                for i, word_info in enumerate(group_words):
                    start_time = word_info['start']
                    
                    # Calculate end time
                    if i + 1 < len(group_words):
                        end_time = group_words[i + 1]['start']
                    else:
                        end_time = group['end']
                    
                    # Build caption with moving highlight
                    caption_parts = []
                    for w in group_words:
                        word_text = w['word']
                        if w == word_info:
                            caption_parts.append(r'{\c&H00FFFF&}' + word_text)
                        else:
                            caption_parts.append(r'{\c&HFFFFFF&}' + word_text)
                    
                    caption_with_highlight = ' '.join(caption_parts)
                    
                    # Format times
                    start = format_time(start_time)
                    end = format_time(end_time)
                    
                    # Add the dialogue line
                    ass_content += f"Dialogue: 0,{start},{end},Default,,0,0,0,,{caption_with_highlight}\n"
        else:
            # Original logic remains unchanged
            lines = []
            current_line = []
            current_line_length = 0
            for word_info in words:
                word_length = len(word_info['word']) + 1
                if current_line_length + word_length > max_chars:
                    lines.append(current_line)
                    current_line = [word_info]
                    current_line_length = word_length
                else:
                    current_line.append(word_info)
                    current_line_length += word_length
            if current_line:
                lines.append(current_line)

            for line in lines:
                line_start_time = line[0]['start']
                line_end_time = line[-1]['end']

                for i, word_info in enumerate(line):
                    start_time = word_info['start']
                    end_time = word_info['end']

                    caption_parts = []
                    for w in line:
                        word_text = w['word']
                        if w == word_info:
                            caption_parts.append(r'{\c&H00FFFF&}' + word_text)
                        else:
                            caption_parts.append(r'{\c&HFFFFFF&}' + word_text)
                    caption_with_highlight = ' '.join(caption_parts)

                    start = format_time(start_time)
                    if i + 1 < len(line):
                        end_time = line[i + 1]['start']
                    else:
                        end_time = line_end_time
                    end = format_time(end_time)

                    ass_content += f"Dialogue: 0,{start},{end},Default,,0,0,0,,{caption_with_highlight}\n"

    return ass_content
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

    return part1, part2, duration1, duration2, [part1, part2]

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

def process_transcription(audio_path, output_type, words_per_subtitle=None, max_chars=56, language=None):
    """Transcribe audio and return the transcript or subtitle content."""
    logger.info(f"Starting transcription for: {audio_path} with output type: {output_type}")

    try:
        model = whisper.load_model("base")
        logger.info("Whisper model loaded successfully")

        result = model.transcribe(audio_path, language=language)
        logger.info("Transcription completed successfully")

        if output_type == 'transcript':
            transcript = []
            timestamps = []
            text_segments = []
            duration_sentences = []
            duration_splitsentence = []
            split_sentences = []  # New list for split sentences
            srt_format = []  # List for SRT format
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
                    part1, part2, duration1, duration2, split_parts = split_sentence(sentence, start_time, end_time)
                    duration_splitsentence.extend([str(duration1), str(duration2)])
                    split_sentences.extend(split_parts)  # Add the split parts
                    
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

            # Generate ASS subtitle content
            ass_content = generate_ass_subtitle(result, max_chars)
            
            # Write the ASS content to a temporary file
            temp_ass_filename = os.path.join(STORAGE_PATH, f"{uuid.uuid4()}.ass")
            with open(temp_ass_filename, 'w', encoding='utf-8') as f:
                f.write(ass_content)
            
            # Upload the ASS file to GCS and get the URL
            ass_cloud_url = upload_to_gcs(temp_ass_filename)
            
            # Remove the temporary ASS file
            os.remove(temp_ass_filename)

            output = {
                'transcript': "\n".join(transcript),
                'timestamps': timestamps,
                'text_segments': text_segments,
                'duration_sentences': duration_sentences,
                'duration_splitsentence': duration_splitsentence,
                'split_sentences': split_sentences,  # Add split sentences to output
                'srt_format': srt_format,
                'ass_content': ass_content,
                'ass_file_url': ass_cloud_url
            }
            logger.info("Transcript with timestamps, sentence durations, split sentence durations, SRT format, and ASS file URL generated")
            return output
        elif output_type in ['srt', 'vtt', 'ass']:
            output_filename = os.path.join(STORAGE_PATH, f"{uuid.uuid4()}.{output_type}")
            
            if output_type == 'srt':
                writer = WriteSRT(output_dir=STORAGE_PATH)
                temp_filename = writer(result, audio_path)
                os.rename(temp_filename, output_filename)
            elif output_type == 'vtt':
                writer = WriteVTT(output_dir=STORAGE_PATH)
                temp_filename = writer(result, audio_path)
                os.rename(temp_filename, output_filename)
            elif output_type == 'ass':
                result = model.transcribe(
                    audio_path,
                    word_timestamps=True,
                    task='transcribe',
                    verbose=False
                )
                logger.info("Transcription completed with word-level timestamps")
                # Pass words_per_subtitle to generate_ass_subtitle
                ass_content = generate_ass_subtitle(result, max_chars, words_per_subtitle)
                logger.info("Generated ASS subtitle content")
                
                with open(output_filename, 'w', encoding='utf-8') as f:
                    f.write(ass_content)
            
            logger.info(f"Generated {output_type.upper()} output: {output_filename}")
            return output_filename
        else:
            raise ValueError(f"Invalid output type: {output_type}")

    except Exception as e:
        logger.error(f"Error during transcription: {str(e)}")
        raise
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)
            logger.info(f"Removed temporary file: {audio_path}")
