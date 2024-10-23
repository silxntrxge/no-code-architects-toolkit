import os
import ffmpeg
import logging
import requests
import subprocess
from services.file_management import download_file
from services.gcp_toolkit import upload_to_gcs, GCP_BUCKET_NAME
import mimetypes
import re
from urllib.parse import urlparse, parse_qs
import hashlib

# Set the default local storage directory
STORAGE_PATH = "/tmp/"

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define the path to the fonts directory
FONTS_DIR = '/usr/share/fonts/custom'

# Create the FONT_PATHS dictionary by reading the fonts directory
FONT_PATHS = {}
for font_file in os.listdir(FONTS_DIR):
    if font_file.endswith('.ttf') or font_file.endswith('.TTF') or font_file.endswith('.otf') or font_file.endswith('.woff'):
        font_name = os.path.splitext(font_file)[0]
        FONT_PATHS[font_name] = os.path.join(FONTS_DIR, font_file)

# Create a list of acceptable font names
ACCEPTABLE_FONTS = list(FONT_PATHS.keys())

def match_fonts():
    try:
        result = subprocess.run(['fc-list', ':family'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            fontconfig_fonts = result.stdout.split('\n')
            fontconfig_fonts = list(set(fontconfig_fonts))  # Remove duplicates
            matched_fonts = {}
            for font_file in FONT_PATHS.keys():
                for fontconfig_font in fontconfig_fonts:
                    if font_file.lower() in fontconfig_font.lower():
                        matched_fonts[font_file] = fontconfig_font.strip()

            # Parse and output the matched font names
            unique_font_names = set()
            for font in matched_fonts.values():
                font_name = font.split(':')[1].strip()
                unique_font_names.add(font_name)
            
            # Remove duplicates from font_name and sort them alphabetically
            unique_font_names = sorted(list(set(unique_font_names)))
            
            for font_name in unique_font_names:
                print(font_name)
        else:
            logger.error(f"Error matching fonts: {result.stderr}")
    except Exception as e:
        logger.error(f"Exception while matching fonts: {str(e)}")

match_fonts()

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

def download_and_verify_font(font_url, job_id):
    """Download font file, verify its format, and store it in the custom fonts directory."""
    try:
        logger.info(f"Job {job_id}: Attempting to download font from URL: {font_url}")
        
        # Generate a unique filename based on the URL
        url_hash = hashlib.md5(font_url.encode()).hexdigest()
        
        # Check if a font with this hash already exists
        existing_fonts = [f for f in os.listdir(FONTS_DIR) if f.startswith(url_hash)]
        if existing_fonts:
            font_path = os.path.join(FONTS_DIR, existing_fonts[0])
            logger.info(f"Job {job_id}: Font already exists at {font_path}")
            return font_path
        
        # If not, download the font
        response = requests.get(font_url, allow_redirects=True)
        response.raise_for_status()
        
        # Try to get the filename from the Content-Disposition header
        content_disposition = response.headers.get('Content-Disposition')
        if content_disposition:
            filename = re.findall("filename=(.+)", content_disposition)[0].strip('"')
        else:
            filename = os.path.basename(urlparse(font_url).path)
        
        # Ensure the filename has an extension
        _, ext = os.path.splitext(filename)
        if not ext:
            ext = '.ttf'  # Default to .ttf if no extension
        
        # Create the new filename
        new_filename = f"{url_hash}{ext}"
        font_path = os.path.join(FONTS_DIR, new_filename)
        
        # Write the content to a file
        with open(font_path, 'wb') as f:
            f.write(response.content)
        
        logger.info(f"Job {job_id}: Font downloaded to {font_path}")
        
        # Verify MIME type
        mime_type, _ = mimetypes.guess_type(font_path)
        logger.info(f"Job {job_id}: Detected MIME type: {mime_type}")
        if mime_type not in ['font/otf', 'font/ttf', 'font/woff']:
            os.remove(font_path)
            raise ValueError(f"Unsupported MIME type: {mime_type}")
        
        # Update FONT_PATHS dictionary
        font_name = os.path.splitext(new_filename)[0]
        FONT_PATHS[font_name] = font_path
        ACCEPTABLE_FONTS.append(font_name)
        
        return font_path
    except Exception as e:
        logger.error(f"Job {job_id}: Error downloading or verifying font: {str(e)}")
        raise

def process_captioning(file_url, caption_srt, caption_type, options, job_id):
    """Process video captioning using FFmpeg."""
    try:
        logger.info(f"Job {job_id}: Starting download of file from {file_url}")
        video_path = download_file(file_url, STORAGE_PATH)
        logger.info(f"Job {job_id}: File downloaded to {video_path}")

        subtitle_extension = '.' + caption_type
        srt_path = os.path.join(STORAGE_PATH, f"{job_id}{subtitle_extension}")
        options = convert_array_to_collection(options)
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

        if caption_srt.startswith("https"):
            # Download the file if caption_srt is a URL
            logger.info(f"Job {job_id}: Downloading caption file from {caption_srt}")
            response = requests.get(caption_srt)
            response.raise_for_status()  # Raise an exception for bad status codes
            if caption_type in ['srt','vtt']:
                with open(srt_path, 'wb') as srt_file:
                    srt_file.write(response.content)
            else:
                subtitle_content = caption_style + response.text
                with open(srt_path, 'w') as srt_file:
                    srt_file.write(subtitle_content)
            logger.info(f"Job {job_id}: Caption file downloaded to {srt_path}")
        else:
            # Write caption_srt content directly to file
            subtitle_content = caption_style + caption_srt
            with open(srt_path, 'w') as srt_file:
                srt_file.write(subtitle_content)
            logger.info(f"Job {job_id}: SRT file created at {srt_path}")

        output_path = os.path.join(STORAGE_PATH, f"{job_id}_captioned.mp4")
        logger.info(f"Job {job_id}: Output path set to {output_path}")

        font_path = None
        font_name = options.get('font_name', 'Arial')
        logger.info(f"Job {job_id}: Font name from options: {font_name}")
        if font_name.startswith('http'):
            # Download and verify the font
            logger.info(f"Job {job_id}: Attempting to download font from URL: {font_name}")
            font_path = download_and_verify_font(font_name, job_id)
            font_name = os.path.splitext(os.path.basename(font_path))[0]
            logger.info(f"Job {job_id}: Using downloaded font: {font_name}")
        elif font_name in FONT_PATHS:
            font_path = FONT_PATHS[font_name]
            logger.info(f"Job {job_id}: Font path set to {font_path}")
        else:
            font_path = FONT_PATHS.get('Arial')
            logger.warning(f"Job {job_id}: Font {font_name} not found. Using default font Arial.")

        # For ASS subtitles, we should avoid overriding styles
        if subtitle_extension == '.ass':
            # Use the subtitles filter with fontconfig
            subtitle_filter = f"subtitles='{srt_path}':fontsdir='{os.path.dirname(font_path)}'"
            logger.info(f"Job {job_id}: Using ASS subtitle filter with fontfile: {subtitle_filter}")
        else:
            # Construct FFmpeg filter options for subtitles with detailed styling
            subtitle_filter = f"subtitles={srt_path}:fontsdir='{os.path.dirname(font_path)}':force_style='"
            style_options = {
                'FontName': font_name,
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
                'Angle': options.get('angle', 0),
                'UpperCase': options.get('uppercase', 0)
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
            ).run()
            logger.info(f"Job {job_id}: FFmpeg processing completed, output file at {output_path}")
        except ffmpeg.Error as e:
            # Log the FFmpeg stderr output
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
        logger.info(f"Job {job_id}: Local files cleaned up")
        return output_filename
    except Exception as e:
        logger.error(f"Job {job_id}: Error in process_captioning: {str(e)}")
        raise

def convert_array_to_collection(options):
    logger.info(f"Converting options array to dictionary: {options}")
    return {item["option"]: item["value"] for item in options if isinstance(item, dict) and "option" in item and "value" in item}
