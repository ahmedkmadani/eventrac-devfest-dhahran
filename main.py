# main.py
import json
import logging
import os
import tempfile
import time

import cv2
from fastapi import FastAPI, Request
from google.cloud import storage
from google import genai
from google.genai import types

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI()
storage_client = storage.Client()

OUTPUT_BUCKET = os.environ.get("OUTPUT_BUCKET")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Initialize Gemini client
if GEMINI_API_KEY:
    os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY
    genai_client = genai.Client()
    logger.info("Gemini client initialized")
else:
    genai_client = None
    logger.warning("GEMINI_API_KEY not configured - video analysis will be disabled")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/")
async def handle_event(request: Request):
    """
    Entry point for Eventarc -> Cloud Run.
    Downloads video from GCS and uses Gemini Vision to detect when kid saying "67" appears.
    """
    request_body = await request.json()
    logger.info(f"Received event: {json.dumps(request_body, indent=2)}")
    
    # Extract bucket and object name from the request
    bucket_name = request_body.get("bucket")
    object_name = request_body.get("name")
    
    # Try nested "data" field if not found at top level (CloudEvent format)
    if not bucket_name or not object_name:
        data = request_body.get("data", {})
        if isinstance(data, dict):
            bucket_name = data.get("bucket") or bucket_name
            object_name = data.get("name") or object_name
        elif isinstance(data, str):
            import base64
            try:
                decoded_data = json.loads(base64.b64decode(data).decode('utf-8'))
                bucket_name = decoded_data.get("bucket") or bucket_name
                object_name = decoded_data.get("name") or object_name
            except Exception as e:
                logger.error(f"Error decoding base64 data: {str(e)}")
    
    if not bucket_name or not object_name:
        logger.error("Missing bucket or name in request")
        return {"status": "error", "message": "missing bucket or name"}, 400
    
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY not configured")
        return {"status": "error", "message": "GEMINI_API_KEY not configured"}, 500
    
    logger.info(f"Processing video: gs://{bucket_name}/{object_name}")
    
    # Download video to a temp file
    tmp_video = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp_video_name = tmp_video.name
    tmp_video.close()
    
    try:
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        blob.download_to_filename(tmp_video_name)
        logger.info(f"Downloaded video to {tmp_video_name}")
        
        # Process video with Gemini to detect kid saying "67"
        kid_detected, target_second, kid_frame = detect_kid_saying_67_with_gemini(tmp_video_name)
        
        if kid_detected:
            logger.info(f"Kid saying '67' detected at {target_second} seconds")
            
            frame_name = None
            if OUTPUT_BUCKET and kid_frame is not None:
                frame_name = f"{os.path.splitext(object_name)[0]}-kid-67-frame-{target_second:.1f}s.png"
                out_bucket = storage_client.bucket(OUTPUT_BUCKET)
                out_blob = out_bucket.blob(frame_name)
                
                success, buf = cv2.imencode(".png", kid_frame)
                if success:
                    out_blob.upload_from_string(buf.tobytes(), content_type="image/png")
                    logger.info(f"Uploaded frame to gs://{OUTPUT_BUCKET}/{frame_name}")
                else:
                    logger.error("Failed to encode frame as PNG")
            
            return {
                "status": "ok",
                "kid_detected": True,
                "timestamp_seconds": target_second,
                "frame_saved": OUTPUT_BUCKET is not None and frame_name is not None,
                "frame_name": frame_name
            }
        else:
            logger.info("No kid saying '67' detected in video")
            return {
                "status": "ok",
                "kid_detected": False,
                "message": "No kid saying '67' found in video"
            }
    
    except Exception as e:
        logger.error(f"Error processing video: {str(e)}", exc_info=True)
        return {"status": "error", "message": str(e)}, 500
    
    finally:
        # Clean up temp file
        if os.path.exists(tmp_video_name):
            os.unlink(tmp_video_name)


def detect_kid_saying_67_with_gemini(video_path: str):
    """
    Uses Gemini API to detect when a kid saying "67" appears in the video.
    Uploads video to Gemini and uses video analysis to find the timestamp.
    Returns (True/False, target_second float, frame image) if kid saying "67" is found.
    """
    if not genai_client:
        logger.error("Gemini client not initialized")
        return False, None, None
    
    prompt = """
Find the first moment where the kid is saying the number "67" with their hands/fingers.
Return ONLY JSON: {"second": <float>}
"""
    
    video_file = None
    try:
        logger.info("Uploading video to Gemini...")
        video_file = genai_client.files.upload(file=video_path)
        
        logger.info(f"Uploaded file: {video_file.name}, state: {video_file.state.name}")
        while video_file.state.name != "ACTIVE":
            logger.info(f"Waiting for file to be ready... Current state: {video_file.state.name}")
            time.sleep(2)
            video_file = genai_client.files.get(name=video_file.name)
        
        logger.info("File is ready, analyzing video with Gemini...")
        response = genai_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=types.Content(
                parts=[
                    types.Part(
                        file_data=types.FileData(
                            file_uri=video_file.uri,
                            mime_type="video/mp4",
                        )
                    ),
                    types.Part(text=prompt),
                ]
            ),
        )
        
        if not hasattr(response, 'text') or not response.text:
            logger.error("Response has no text content")
            return False, None, None
        
        response_text = response.text.strip()
        
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            if start_idx >= 0 and end_idx > start_idx:
                json_str = response_text[start_idx:end_idx]
                data = json.loads(json_str)
            else:
                logger.error(f"Could not find JSON in response: {response_text}")
                return False, None, None
        
        target_second = float(data["second"])
        logger.info(f"Kid saying '67' detected at: {target_second} seconds")
        
        logger.info(f"Extracting frame at {target_second} seconds...")
        cap = cv2.VideoCapture(video_path)
        
        if not cap.isOpened():
            logger.error(f"Could not open video file {video_path}")
            return False, None, None
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_number = int(target_second * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
        ret, frame = cap.read()
        cap.release()
        
        if ret:
            return True, target_second, frame
        else:
            logger.error(f"Could not read frame at {target_second} seconds")
            return False, None, None
            
    except Exception as e:
        logger.error(f"Error in detect_kid_saying_67_with_gemini: {str(e)}", exc_info=True)
        return False, None, None
    
    finally:
        if video_file:
            try:
                genai_client.files.delete(name=video_file.name)
                logger.info("Cleaned up uploaded video file from Gemini")
            except Exception as e:
                logger.warning(f"Could not delete uploaded file: {str(e)}")
