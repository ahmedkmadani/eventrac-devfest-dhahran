# Setup: Create .env file
# 1. Copy the example file and fill in your values:
#    cp .env.example .env
# 2. Edit .env and set your values:
#    - PROJECT_ID: Your GCP project ID
#    - REGION: Your preferred region (e.g., us-central1)
#    - GEMINI_API_KEY: Your Gemini API key from https://ai.google.dev/

# Load environment variables from .env file
# Option 1: Use the helper script (recommended)
source ./load-env.sh

# Option 2: Or load manually
# export $(cat .env | grep -v '^#' | grep -v '^$' | xargs)
# export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")
# export RAW_BUCKET="video-raw-${PROJECT_ID}"
# export FRAMES_BUCKET="video-frames-${PROJECT_ID}"

gsutil mb -l $REGION gs://$RAW_BUCKET
gsutil mb -l $REGION gs://$FRAMES_BUCKET

# Make frames bucket publicly readable (optional - for accessing images via public URLs)
gsutil iam ch allUsers:objectViewer gs://$FRAMES_BUCKET


# Enable API
gcloud services enable \
  run.googleapis.com \
  eventarc.googleapis.com \
  storage.googleapis.com


# Deploy Cloud run service
# Make sure you've loaded .env file first (run: source ./load-env.sh)
gcloud run deploy video-processor \
  --source . \
  --region $REGION \
  --platform managed \
  --no-allow-unauthenticated \
  --set-env-vars OUTPUT_BUCKET=$FRAMES_BUCKET,GEMINI_API_KEY=$GEMINI_API_KEY


gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:service-$PROJECT_NUMBER@gs-project-accounts.iam.gserviceaccount.com" \
  --role="roles/pubsub.publisher"


# Create Eventarc trigger
gcloud eventarc triggers create video-upload-trigger \
  --location=$REGION \
  --destination-run-service=video-processor \
  --destination-run-region=$REGION \
  --event-filters="type=google.cloud.storage.object.v1.finalized" \
  --event-filters="bucket=${RAW_BUCKET}" \
  --service-account=service-$PROJECT_NUMBER@gs-project-accounts.iam.gserviceaccount.com



# Test the pipeline
- Upload the file
gsutil cp 67.mp4 gs://$RAW_BUCKET

- Checking the Logs
gcloud logging read \
  "resource.type=cloud_run_revision AND resource.labels.service_name=video-processor AND resource.labels.location=$REGION" \
  --project=$PROJECT_ID \
  --limit=50 \
  --format="value(textPayload)"

- List the frame bucket
gsutil ls gs://$FRAMES_BUCKET

- Get public URL for a frame (after making bucket public)
# Format: https://storage.googleapis.com/BUCKET_NAME/OBJECT_NAME
# Example:
echo "https://storage.googleapis.com/$FRAMES_BUCKET/67-kid-67-frame-3.8s.png"
