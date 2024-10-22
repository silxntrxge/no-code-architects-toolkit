import os
import ffmpeg
import logging
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from services.file_management import download_file
from services.gcp_toolkit import upload_to_gcs, GCP_BUCKET_NAME

# Set the default local storage directory
STORAGE_PATH = "/tmp/"

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add this section to handle fonts correctly
FONTS_DIR = '/usr/share/fonts/truetype/custom'
FONT_PATHS = {}

if os.path.exists(FONTS_DIR):
    for font_file in os.listdir(FONTS_DIR):
        if font_file.endswith('.ttf') or font_file.endswith('.TTF'):
            font_name = os.path.splitext(font_file)[0]
            FONT_PATHS[font_name] = os.path.join(FONTS_DIR, font_file)
else:
    logger.warning(f"Custom fonts directory not found: {FONTS_DIR}")

def generate_style_line(options):
    """Generate ASS style line from options."""
    style_options = {
        'Name': 'Default',
        'Fontname': options.get('font_name', 'Arial'),
        'Fontsize': options.get('font_size', 24),
        'PrimaryColour': options.get('primary_color', '&H00FFFFFF'),
        'OutlineColour': options.get('outline_color', '&H00000000'),
        'BackColour': options.get('back_color', '&H00000000'),
        'Bold': options.get('bold', 0),
        'Italic': options.get('italic', 0),
        'Underline': options.get('underline', 0),
        'StrikeOut': options.get('strikeout', 0),
        'ScaleX': 100,
        'ScaleY': 100,
        'Spacing': 0,
        'Angle': 0,
        'BorderStyle': 1,
        'Outline': options.get('outline', 1),
        'Shadow': options.get('shadow', 0),
        'Alignment': options.get('alignment', 2),
        'MarginL': options.get('margin_l', 10),
        'MarginR': options.get('margin_r', 10),
        'MarginV': options.get('margin_v', 10),
        'Encoding': options.get('encoding', 1)
    }
    return f"Style: {','.join(str(v) for v in style_options.values())}"

def process_captioning(file_url, caption_srt, caption_type, options, job_id):
    """Process video captioning using FFmpeg."""
    try:
        logger.info(f"Job {job_id}: Starting download of file from {file_url}")
        video_path = download_file(file_url, STORAGE_PATH)
        logger.info(f"Job {job_id}: File downloaded to {video_path}")

        subtitle_extension = '.ass'
        srt_path = os.path.join(STORAGE_PATH, f"{job_id}{subtitle_extension}")

        caption_style = ""
        if caption_type == 'ass':
            style_string = generate_style_line(options)
            caption_style = f"""
[Script Info]
Title: Highlight Current Word
ScriptType: v4.00+
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{style_string}
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
            logger.info(f"Job {job_id}: Generated ASS style string: {style_string}")
            logger.info(f"Job {job_id}: Full ASS header: {caption_style}")

        if caption_srt.startswith("https"):
            # Download the file if caption_srt is a URL
            logger.info(f"Job {job_id}: Downloading caption file from {caption_srt}")
            response = requests.get(caption_srt)
            response.raise_for_status()  # Raise an exception for bad status codes
            
            if caption_type == 'ass':
                subtitle_content = caption_style + response.text
                with open(srt_path, 'w', encoding='utf-8') as srt_file:
                    srt_file.write(subtitle_content)
            else:
                with open(srt_path, 'wb') as srt_file:
                    srt_file.write(response.content)
            
            logger.info(f"Job {job_id}: Caption file downloaded to {srt_path}")
        else:
            # Write caption_srt content directly to file
            subtitle_content = caption_style + caption_srt if caption_type == 'ass' else caption_srt
            with open(srt_path, 'w', encoding='utf-8') as srt_file:
                srt_file.write(subtitle_content)

        logger.info(f"Job {job_id}: SRT file created at {srt_path}")

        output_path = os.path.join(STORAGE_PATH, f"{job_id}_captioned.mp4")

        options = convert_array_to_collection(options)

        # Default FFmpeg options
        ffmpeg_options = {
            'font_name': None,
            'font_size': 12,
            'primary_color': None,
            'secondary_color': None,
            'outline_color': None,
            'back_color': None,
            'bold': None,
            'italic': None,
            'underline': None,
            'strikeout': None,
            'alignment': None,
            'margin_v': None,
            'margin_l': None,
            'margin_r': None,
            'outline': None,
            'shadow': None,
            'blur': None,
            'border_style': None,
            'encoding': None,
            'spacing': None,
            'angle': None,
            'uppercase': None
        }

        # Update ffmpeg_options with provided options
        ffmpeg_options.update(options)

        # Handle downloadable font
        font_url = ffmpeg_options['font_name']
        if font_url and font_url.startswith('http'):
            try:
                temp_font_file = download_file(font_url, STORAGE_PATH, suffix='.ttf')
                if temp_font_file:
                    ffmpeg_options['font_name'] = temp_font_file
                    logger.info(f"Job {job_id}: Successfully downloaded font: {temp_font_file}")
            except Exception as e:
                logger.error(f"Job {job_id}: Error downloading font: {str(e)}")

        if caption_type == 'ass':
            subtitle_filter = f"subtitles='{srt_path}'"
        else:
            subtitle_filter = f"subtitles={srt_path}:force_style='"
            style_options = {
                'FontName': options.get('font_name', 'Arial'),
                'FontSize': options.get('font_size', 24),
                'PrimaryColour': options.get('primary_color', '&H00FFFFFF'),
                'SecondaryColour': options.get('secondary_color', '&H00000000'),
                'OutlineColour': options.get('outline_color', '&H00000000'),
                'BackColour': options.get('back_color', '&H00000000'),
                'Bold': options.get('bold', 0),
                'Italic': options.get('italic', 0),
                'Underline': options.get('underline', 0),
                'StrikeOut': options.get('strikeout', 0),
                'Alignment': options.get('alignment', 2),
                'MarginV': options.get('margin_v', 10),
                'MarginL': options.get('margin_l', 10),
                'MarginR': options.get('margin_r', 10),
                'Outline': options.get('outline', 1),
                'Shadow': options.get('shadow', 0),
                'Blur': options.get('blur', 0),
                'BorderStyle': options.get('border_style', 1),
                'Encoding': options.get('encoding', 1),
                'Spacing': options.get('spacing', 0),
                'Angle': options.get('angle', 0)
            }

            # Add only populated options to the subtitle filter
            subtitle_filter += ','.join(f"{k}={v}" for k, v in style_options.items() if v is not None)
            subtitle_filter += "'"

        logger.info(f"Job {job_id}: Using subtitle filter: {subtitle_filter}")

        try:
            # Log the FFmpeg command for debugging
            logger.info(f"Job {job_id}: Running FFmpeg with filter: {subtitle_filter}")

            # Run FFmpeg to add subtitles to the video
            ffmpeg.input(video_path).output(
                output_path,
                vf=subtitle_filter,
                acodec='copy'
            ).run(capture_stdout=True, capture_stderr=True)
            logger.info(f"Job {job_id}: FFmpeg processing completed, output file at {output_path}")
        except ffmpeg.Error as e:
            if e.stderr:
                error_message = e.stderr.decode('utf8')
            else:
                error_message = 'Unknown FFmpeg error'
            logger.error(f"Job {job_id}: FFmpeg error: {error_message}")
            raise

        # Upload the output video to GCP Storage
        output_filename = upload_to_gcs(output_path, GCP_BUCKET_NAME)
        logger.info(f"Job {job_id}: File uploaded to GCS at {output_filename}")

        # Clean up local files
        os.remove(video_path)
        os.remove(srt_path)
        os.remove(output_path)
        if font_url and font_url.startswith('http'):
            os.remove(temp_font_file)
        logger.info(f"Job {job_id}: Local files cleaned up")
        return output_filename
    except requests.RequestException as e:
        logger.error(f"Job {job_id}: Error downloading caption file: {str(e)}")
        raise
    except IOError as e:
        logger.error(f"Job {job_id}: Error writing caption file: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Job {job_id}: Unexpected error in process_captioning: {str(e)}")
        raise

def convert_array_to_collection(options):
    return {item["option"]: item["value"] for item in options}
