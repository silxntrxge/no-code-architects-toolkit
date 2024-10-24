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

# Add this line at the top of the file, after the imports
STORAGE_PATH = '/tmp'  # or any other appropriate temporary directory

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

def generate_ass_subtitle(result, max_chars):
    """Generate ASS subtitle content with highlighted current words, showing the full line each time."""
    logger.info("Generate ASS subtitle content with highlighted current words")
    ass_content = ""

    def format_time(t):
        hours = int(t // 3600)
        minutes = int((t % 3600) // 60)
        seconds = int(t % 60)
        centiseconds = int(round((t - int(t)) * 100))
        return f"{hours:01d}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"

    max_chars_per_line = max_chars  # Maximum characters per line

    for segment in result['segments']:
        words = segment.get('words', [])
        if not words:
            continue  # Skip if no word-level timestamps

        lines = []
        current_line = []
        current_line_length = 0
        for word_info in words:
            word_length = len(word_info['word']) + 1  # +1 for space
            if current_line_length + word_length > max_chars_per_line:
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

                # Build the line text with highlighted current word
                caption_parts = []
                for w in line:
                    word_text = w['word']
                    if w == word_info:
                        # Highlight current word
                        caption_parts.append(r'{\c&H00FFFF&}' + word_text)
                    else:
                        # Default color
                        caption_parts.append(r'{\c&HFFFFFF&}' + word_text)
                caption_with_highlight = ' '.join(caption_parts)

                # Format times
                start = format_time(start_time)
                # End the dialogue event when the next word starts or at the end of the line
                if i + 1 < len(line):
                    end_time = line[i + 1]['start']
                else:
                    end_time = line_end_time
                end = format_time(end_time)

                # Add the dialogue line
                ass_content += f"Dialogue: 0,{start},{end},Default,,0,0,0,,{caption_with_highlight}\n"

    return ass_content

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

            # Generate ASS subtitle content
            ass_content = generate_ass_subtitle(result, max_chars)
            logger.info(f"Generated ASS content length: {len(ass_content)}")
            
            if not ass_content:
                logger.error("Generated ASS content is empty")
                raise ValueError("Empty ASS content generated")

            # Write the ASS content to a temporary file
            temp_ass_filename = os.path.join(STORAGE_PATH, f"{uuid.uuid4()}.ass")
            with open(temp_ass_filename, 'w', encoding='utf-8') as f:
                f.write(ass_content)
            
            # Verify the file was written correctly
            if os.path.getsize(temp_ass_filename) == 0:
                logger.error(f"Failed to write ASS content to {temp_ass_filename}")
                raise IOError(f"Failed to write ASS content to {temp_ass_filename}")
            else:
                logger.info(f"ASS content written to {temp_ass_filename}, size: {os.path.getsize(temp_ass_filename)} bytes")
            
            # Upload the ASS file to GCS and get the URL
            try:
                ass_gcs_url = upload_to_gcs(temp_ass_filename)
                logger.info(f"Uploaded ASS file to GCS: {ass_gcs_url}")
            except Exception as e:
                logger.error(f"Failed to upload ASS file to GCS: {str(e)}")
                raise
            
            # Remove the temporary ASS file only if upload was successful
            if ass_gcs_url:
                os.remove(temp_ass_filename)
                logger.info(f"Removed temporary ASS file: {temp_ass_filename}")
            else:
                logger.warning(f"Keeping temporary ASS file due to upload failure: {temp_ass_filename}")

            output = {
                'transcript': "\n".join(transcript),
                'timestamps': timestamps,
                'text_segments': text_segments,
                'duration_sentences': duration_sentences,
                'duration_splitsentence': duration_splitsentence,
                'srt_format': srt_format,
                'ass_file_url': ass_gcs_url
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
                ass_content = generate_ass_subtitle(result, max_chars)
                logger.info("Generated ASS subtitle content")
                
                with open(output_filename, 'w', encoding='utf-8') as f:
                    f.write(ass_content)
                
                # Verify the file size after writing
                file_size = os.path.getsize(output_filename)
                logger.info(f"ASS file size after writing: {file_size} bytes")
            
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

def perform_transcription(audio_file, words_per_subtitle=None, output_type='transcript'):
    try:
        # Download the audio file
        audio_path = download_file(audio_file)
        
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Downloaded audio file not found: {audio_path}")

        # Load the model and transcribe
        model = whisper.load_model("base")
        result = model.transcribe(audio_path, language=None)

        # Process the transcription result
        transcript = []
        timestamps = []
        text_segments = []
        duration_sentences = []
        duration_splitsentence = []

        for segment in result['segments']:
            start_time = segment['start']
            end_time = segment['end']
            text = segment['text'].strip()
            
            formatted_start = format_timestamp(start_time)
            formatted_end = format_timestamp(end_time)
            transcript.append(f"{formatted_start} - {formatted_end}: {text}")
            timestamps.append(f"{formatted_start}-{formatted_end}")
            text_segments.append(text)
            duration = end_time - start_time
            duration_sentences.append(str(round(duration, 2)))
            
            part1, part2, duration1, duration2 = split_sentence(text, start_time, end_time)
            duration_splitsentence.extend([str(duration1), str(duration2)])

        # Generate SRT format
        srt_format = create_word_level_srt(result['segments'], words_per_subtitle) if words_per_subtitle else "\n\n".join([
            f"{i}\n{format_timestamp(s['start']).replace('.', ',')} --> {format_timestamp(s['end']).replace('.', ',')}\n{s['text']}"
            for i, s in enumerate(result['segments'], start=1)
        ])

        # Generate ASS format
        ass_content = generate_ass_subtitle(result, max_chars=56)

        # Upload ASS file to GCS
        ass_filename = f"transcription_{uuid.uuid4()}.ass"
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.ass') as temp_ass_file:
            temp_ass_file.write(ass_content)
            temp_ass_path = temp_ass_file.name

        ass_gcs_url = upload_to_gcs(temp_ass_path, ass_filename)

        # Clean up temporary files
        os.remove(temp_ass_path)
        os.remove(audio_path)

        # Prepare the result dictionary
        result = {
            'transcript': "\n".join(transcript),
            'timestamps': timestamps,
            'text_segments': text_segments,
            'duration_sentences': duration_sentences,
            'duration_splitsentence': duration_splitsentence,
            'srt_format': srt_format,
            'ass_file_url': ass_gcs_url
        }

        # Add specific output based on output_type
        if output_type == 'srt':
            srt_filename = f"transcription_{uuid.uuid4()}.srt"
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.srt') as temp_srt_file:
                temp_srt_file.write(srt_format)
                temp_srt_path = temp_srt_file.name
            result['srt_file_url'] = upload_to_gcs(temp_srt_path, srt_filename)
            os.remove(temp_srt_path)
        elif output_type == 'vtt':
            vtt_content = generate_vtt(text_segments)
            vtt_filename = f"transcription_{uuid.uuid4()}.vtt"
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.vtt') as temp_vtt_file:
                temp_vtt_file.write(vtt_content)
                temp_vtt_path = temp_vtt_file.name
            result['vtt_file_url'] = upload_to_gcs(temp_vtt_path, vtt_filename)
            os.remove(temp_vtt_path)

        return result

    except Exception as e:
        logger.error(f"Transcription error: {str(e)}")
        raise

def generate_vtt(text_segments):
    vtt_content = "WEBVTT\n\n"
    for i, segment in enumerate(text_segments, start=1):
        start_time = format_timestamp(segment['start']).replace('.', ':')
        end_time = format_timestamp(segment['end']).replace('.', ':')
        vtt_content += f"{start_time} --> {end_time}\n{segment['text']}\n\n"
    return vtt_content
