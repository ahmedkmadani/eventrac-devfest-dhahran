#!/bin/bash
# Load environment variables from .env file

if [ ! -f .env ]; then
    echo "Error: .env file not found!"
    echo "Please create .env file from .env.example"
    exit 1
fi

# Load environment variables from .env file
export $(cat .env | grep -v '^#' | grep -v '^$' | xargs)

# Auto-generate PROJECT_NUMBER and bucket names (always override to ensure correct values)
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")
export RAW_BUCKET="video-raw-${PROJECT_ID}"
export FRAMES_BUCKET="video-frames-${PROJECT_ID}"

# Verify variables are set
echo "✅ Environment variables loaded:"
echo "   PROJECT_ID: $PROJECT_ID"
echo "   REGION: $REGION"
echo "   PROJECT_NUMBER: $PROJECT_NUMBER"
echo "   RAW_BUCKET: $RAW_BUCKET"
echo "   FRAMES_BUCKET: $FRAMES_BUCKET"
echo "   GEMINI_API_KEY: ${GEMINI_API_KEY:0:10}..."
echo ""

