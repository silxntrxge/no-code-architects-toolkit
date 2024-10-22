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

# Define the font paths
FONT_PATHS = {
    'Arial': '/usr/share/fonts/truetype/custom/Arial.ttf',
    'Libre Baskerville': '/usr/share/fonts/truetype/custom/LibreBaskerville-Regular.ttf',
    'Lobster': '/usr/share/fonts/truetype/custom/Lobster-Regular.ttf',
    'Luckiest Guy': '/usr/share/fonts/truetype/custom/LuckiestGuy-Regular.ttf',
    'Nanum Pen Script': '/usr/share/fonts/truetype/custom/NanumPenScript-Regular.ttf',
    'Nunito': '/usr/share/fonts/truetype/custom/Nunito-Regular.ttf',
    'Pacifico': '/usr/share/fonts/truetype/custom/Pacifico-Regular.ttf',
    'Roboto': '/usr/share/fonts/truetype/custom/Roboto-Regular.ttf',
    'Comic Neue': '/usr/share/fonts/truetype/custom/ComicNeue-Regular.ttf',
    'Oswald': '/usr/share/fonts/truetype/custom/Oswald-Regular.ttf',
    'Oswald Bold': '/usr/share/fonts/truetype/custom/Oswald-Bold.ttf',
    'Shrikhand': '/usr/share/fonts/truetype/custom/Shrikhand-Regular.ttf',
    'Fredericka the Great': '/usr/share/fonts/truetype/custom/FrederickatheGreat-Regular.ttf',
    'Permanent Marker': '/usr/share/fonts/truetype/custom/PermanentMarker-Regular.ttf',
    'Simplified Chinese': '/usr/share/fonts/truetype/custom/SimplifiedChinese.ttf',
    'Traditional Chinese': '/usr/share/fonts/truetype/custom/TraditionalChinese.ttf',
    'Japanese': '/usr/share/fonts/truetype/custom/Japanese.ttf',
    'Korean': '/usr/share/fonts/truetype/custom/Korean.ttf',
    'Korean Bold': '/usr/share/fonts/truetype/custom/Korean-Bold.ttf'
}

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

        srt_path = os.path.join(STORAGE_PATH, f"{job_id}.srt")

        if caption_srt.startswith("https"):
            # Download the file if caption_srt is a URL
            logger.info(f"Job {job_id}: Downloading caption file from {caption_srt}")
            response = requests.get(caption_srt)
            response.raise_for_status()  # Raise an exception for bad status codes
            
            with open(srt_path, 'wb') as srt_file:
                srt_file.write(response.content)
            
            logger.info(f"Job {job_id}: Caption file downloaded to {srt_path}")
        else:
            # Write caption_srt content directly to file
            with open(srt_path, 'w') as srt_file:
                srt_file.write(caption_srt)
        
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

        # Construct FFmpeg filter options for subtitles with detailed styling
        subtitle_filter = f"subtitles={srt_path}:force_style='"
        style_options = {
            'FontFile': ffmpeg_options['font_name'],
            'FontSize': ffmpeg_options['font_size'],
            'PrimaryColour': ffmpeg_options['primary_color'],
            'SecondaryColour': ffmpeg_options['secondary_color'],
            'OutlineColour': ffmpeg_options['outline_color'],
            'BackColour': ffmpeg_options['back_color'],
            'Bold': ffmpeg_options['bold'],
            'Italic': ffmpeg_options['italic'],
            'Underline': ffmpeg_options['underline'],
            'StrikeOut': ffmpeg_options['strikeout'],
            'Alignment': ffmpeg_options['alignment'],
            'MarginV': ffmpeg_options['margin_v'],
            'MarginL': ffmpeg_options['margin_l'],
            'MarginR': ffmpeg_options['margin_r'],
            'Outline': ffmpeg_options['outline'],
            'Shadow': ffmpeg_options['shadow'],
            'Blur': ffmpeg_options['blur'],
            'BorderStyle': ffmpeg_options['border_style'],
            'Encoding': ffmpeg_options['encoding'],
            'Spacing': ffmpeg_options['spacing'],
            'Angle': ffmpeg_options['angle'],
            'UpperCase': ffmpeg_options['uppercase']
        }

        if caption_type == 'ass':
            # Use the subtitles filter without force_style
            subtitle_filter = f"subtitles='{srt_path}'"
            logger.info(f"Job {job_id}: Using ASS subtitle filter: {subtitle_filter}")
            logger.info(f"Job {job_id}: Content of ASS file:")
            with open(srt_path, 'r') as f:
                logger.info(f.read())

        # Add only populated options to the subtitle filter
        subtitle_filter += ','.join(f"{k}={v}" for k, v in style_options.items() if v is not None)
        subtitle_filter += "'"

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
            # Log the FFmpeg stderr output
            error_message = 'Unknown FFmpeg error'
            if e.stderr:
                try:
                    error_message = e.stderr.decode('utf8')
                except AttributeError:
                    error_message = str(e.stderr)
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
    except Exception as e:
        logger.error(f"Job {job_id}: Error in process_captioning: {str(e)}")
        raise

def convert_array_to_collection(options):
    return {item["option"]: item["value"] for item in options}
