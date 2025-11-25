# Event-Driven Architecture with Eventarc

A serverless video processing pipeline that uses Google Cloud Eventarc to automatically process videos uploaded to Cloud Storage and extract frames using Gemini AI Vision API.

## Overview

This project demonstrates an event-driven architecture using:
- **Google Cloud Storage** - for video storage
- **Eventarc** - to trigger events on file uploads
- **Cloud Run** - for serverless video processing
- **Gemini AI** - for intelligent video frame extraction

## Prerequisites

- Google Cloud Platform account
- `gcloud` CLI installed and configured
- Python 3.x
- Gemini API key from [https://ai.google.dev/](https://ai.google.dev/)

## Setup

### 1. Create `.env` file

Copy the example file and fill in your values:

```bash
cp .env.example .env
```

Edit `.env` and set your values:
- `PROJECT_ID`: Your GCP project ID
- `REGION`: Your preferred region (e.g., `us-central1`)
- `GEMINI_API_KEY`: Your Gemini API key from [https://ai.google.dev/](https://ai.google.dev/)

### 2. Load environment variables

**Option 1: Use the helper script (recommended)**

```bash
source ./load-env.sh
```

**Option 2: Load manually**

```bash
export $(cat .env | grep -v '^#' | grep -v '^$' | xargs)
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")
export RAW_BUCKET="video-raw-${PROJECT_ID}"
export FRAMES_BUCKET="video-frames-${PROJECT_ID}"
```

### 3. Create Cloud Storage buckets

```bash
gsutil mb -l $REGION gs://$RAW_BUCKET
gsutil mb -l $REGION gs://$FRAMES_BUCKET
```

**Optional:** Make frames bucket publicly readable (for accessing images via public URLs)

```bash
gsutil iam ch allUsers:objectViewer gs://$FRAMES_BUCKET
```

### 4. Enable required APIs

```bash
gcloud services enable \
  run.googleapis.com \
  eventarc.googleapis.com \
  storage.googleapis.com
```

### 5. Deploy Cloud Run service

Make sure you've loaded `.env` file first (`source ./load-env.sh`):

```bash
gcloud run deploy video-processor \
  --source . \
  --region $REGION \
  --platform managed \
  --no-allow-unauthenticated \
  --set-env-vars OUTPUT_BUCKET=$FRAMES_BUCKET,GEMINI_API_KEY=$GEMINI_API_KEY
```

### 6. Configure IAM permissions

```bash
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:service-$PROJECT_NUMBER@gs-project-accounts.iam.gserviceaccount.com" \
  --role="roles/pubsub.publisher"
```

### 7. Create Eventarc trigger

```bash
gcloud eventarc triggers create video-upload-trigger \
  --location=$REGION \
  --destination-run-service=video-processor \
  --destination-run-region=$REGION \
  --event-filters="type=google.cloud.storage.object.v1.finalized" \
  --event-filters="bucket=${RAW_BUCKET}" \
  --service-account=service-$PROJECT_NUMBER@gs-project-accounts.iam.gserviceaccount.com
```

## Testing the Pipeline

### Upload a video file

```bash
gsutil cp 67.mp4 gs://$RAW_BUCKET
```

### Check the logs

```bash
gcloud logging read \
  "resource.type=cloud_run_revision AND resource.labels.service_name=video-processor AND resource.labels.location=$REGION" \
  --project=$PROJECT_ID \
  --limit=50 \
  --format="value(textPayload)"
```

### List frames in the bucket

```bash
gsutil ls gs://$FRAMES_BUCKET
```

### Get public URL for a frame

Format: `https://storage.googleapis.com/BUCKET_NAME/OBJECT_NAME`

Example:
```bash
echo "https://storage.googleapis.com/$FRAMES_BUCKET/67-kid-67-frame-3.8s.png"
```

## Project Structure

```
.
├── main.py              # FastAPI service with Eventarc handler
├── requirements.txt     # Python dependencies
├── Dockerfile          # Container configuration
├── load-env.sh         # Environment variable loader script
├── .env.example        # Environment variables template
└── README.md           # This file
```

## License

MIT
