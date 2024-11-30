import os
import requests
import json
from google.oauth2 import service_account
from google.cloud import storage
import boto3
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import settings from environment variables
STORAGE_PATH = "/tmp/"
GCP_SA_CREDENTIALS = os.getenv('GCP_SA_CREDENTIALS')
GDRIVE_USER = os.getenv('GDRIVE_USER')
GCP_BUCKET_NAME = os.getenv('GCP_BUCKET_NAME')

# DigitalOcean Spaces credentials
DO_SPACES_KEY = os.getenv('DO_SPACES_KEY')
DO_SPACES_SECRET = os.getenv('DO_SPACES_SECRET')
DO_SPACES_BUCKET = os.getenv('DO_SPACES_BUCKET', 'your-default-bucket-name')
DO_SPACES_REGION = os.getenv('DO_SPACES_REGION', 'nyc3')  # Default region
DO_SPACES_ENDPOINT = f"https://{DO_SPACES_REGION}.digitaloceanspaces.com"

# Define the required scopes
GCS_SCOPES = ['https://www.googleapis.com/auth/devstorage.full_control']

# Initialize storage client (either GCS or DO Spaces)
gcs_client = None
spaces_client = None

def init_storage_client():
    """Initialize the appropriate storage client based on available credentials"""
    global gcs_client, spaces_client
    
    if GCP_SA_CREDENTIALS:
        try:
            credentials_info = json.loads(GCP_SA_CREDENTIALS)
            gcs_credentials = service_account.Credentials.from_service_account_info(
                credentials_info,
                scopes=GCS_SCOPES
            )
            gcs_client = storage.Client(credentials=gcs_credentials)
            logger.info("Successfully initialized Google Cloud Storage client")
        except Exception as e:
            logger.warning(f"Failed to initialize GCS client: {e}")
            gcs_client = None
    
    if DO_SPACES_KEY and DO_SPACES_SECRET:
        try:
            session = boto3.session.Session()
            spaces_client = session.client('s3',
                region_name=DO_SPACES_REGION,
                endpoint_url=DO_SPACES_ENDPOINT,
                aws_access_key_id=DO_SPACES_KEY,
                aws_secret_access_key=DO_SPACES_SECRET
            )
            logger.info("Successfully initialized DigitalOcean Spaces client")
        except Exception as e:
            logger.warning(f"Failed to initialize DO Spaces client: {e}")
            spaces_client = None

# Initialize clients
init_storage_client()

def upload_to_gcs(file_path, bucket_name=None):
    """Upload file to either GCS or DO Spaces depending on available client"""
    if not bucket_name:
        bucket_name = GCP_BUCKET_NAME or DO_SPACES_BUCKET
    
    file_name = os.path.basename(file_path)
    
    try:
        # Try Google Cloud Storage first
        if gcs_client:
            logger.info(f"Uploading file to Google Cloud Storage: {file_path}")
            bucket = gcs_client.bucket(bucket_name)
            blob = bucket.blob(file_name)
            blob.upload_from_filename(file_path)
            return blob.public_url
        
        # Fall back to DigitalOcean Spaces
        elif spaces_client:
            logger.info(f"Uploading file to DigitalOcean Spaces: {file_path}")
            with open(file_path, 'rb') as data:
                spaces_client.upload_fileobj(
                    data,
                    DO_SPACES_BUCKET,
                    file_name,
                    ExtraArgs={'ACL': 'public-read'}
                )
            url = f"https://{DO_SPACES_BUCKET}.{DO_SPACES_REGION}.digitaloceanspaces.com/{file_name}"
            return url
        
        else:
            raise Exception("No storage client available. Configure either GCS or DO Spaces credentials.")
            
    except Exception as e:
        logger.error(f"Error uploading file: {e}")
        raise
