# Event-Driven Architecture with Google Cloud Eventarc

## Table of Contents
1. [Introduction to Event-Driven Architecture](#introduction-to-event-driven-architecture)
2. [What is Eventarc?](#what-is-eventarc)
3. [Architecture Overview](#architecture-overview)
4. [Demo Application: Video Processing Pipeline](#demo-application-video-processing-pipeline)
5. [Deep Dive into Eventarc](#deep-dive-into-eventarc)
6. [Implementation Details](#implementation-details)
7. [Best Practices](#best-practices)
8. [Troubleshooting](#troubleshooting)
9. [Conclusion](#conclusion)

---

## Introduction to Event-Driven Architecture

Event-driven architecture (EDA) is a software design pattern where the flow of the application is determined by events. Instead of components directly calling each other, they communicate through events—asynchronous messages that indicate something has happened.

### Key Benefits

1. **Loose Coupling**: Services don't need to know about each other directly
2. **Scalability**: Components can scale independently based on event volume
3. **Resilience**: If one component fails, others continue operating
4. **Flexibility**: Easy to add new event consumers without modifying producers
5. **Real-time Processing**: Events are processed as they occur

### Common Use Cases

- File upload processing
- Real-time data pipelines
- Microservices communication
- IoT data processing
- Automated workflows

---

## What is Eventarc?

**Eventarc** is Google Cloud's event routing service that delivers events from various sources to destinations like Cloud Run, Cloud Functions, or GKE services. It acts as a managed event bus that handles event delivery, retries, and routing.

### Key Features

1. **Multiple Event Sources**: 
   - Cloud Storage (object creation, deletion)
   - Pub/Sub topics
   - Cloud Audit Logs
   - Custom events

2. **Multiple Destinations**:
   - Cloud Run services
   - Cloud Functions
   - GKE services
   - Workflows

3. **Managed Service**: 
   - Automatic retries
   - Dead letter queues
   - Event filtering
   - IAM-based security

### How Eventarc Works

```
Event Source → Eventarc Trigger → Destination Service
     ↓              ↓                    ↓
  GCS Upload    Filter & Route      Cloud Run
  Pub/Sub Msg   Transform Event     Process Event
  Audit Log     Retry on Failure    Return Response
```

1. **Event Generation**: An event occurs (e.g., file uploaded to GCS)
2. **Event Capture**: Eventarc captures the event
3. **Filtering**: Event filters determine if the event matches
4. **Routing**: Event is routed to the configured destination
5. **Delivery**: HTTP POST request sent to destination service
6. **Retry**: Automatic retries on failure

---

## Architecture Overview

### Our Demo Application

```
┌─────────────┐
│   User      │
│  Uploads    │
│  Video      │
└──────┬──────┘
       │
       ▼
┌─────────────────┐
│  GCS Bucket     │
│  (video-raw-*)  │
└──────┬──────────┘
       │
       │ Event: Object Finalized
       ▼
┌─────────────────┐
│   Eventarc      │
│   Trigger       │
└──────┬──────────┘
       │
       │ HTTP POST
       ▼
┌─────────────────┐
│  Cloud Run      │
│  Service        │
│  (video-processor)│
└──────┬──────────┘
       │
       ├─► Download Video
       ├─► Upload to Gemini API
       ├─► Analyze Video
       ├─► Extract Frame
       └─► Upload Frame
           │
           ▼
    ┌──────────────┐
    │  GCS Bucket  │
    │ (video-frames)│
    └──────────────┘
```

### Components

1. **Source Bucket**: Where videos are uploaded
2. **Eventarc Trigger**: Listens for `object.finalized` events
3. **Cloud Run Service**: Processes videos using Gemini AI
4. **Destination Bucket**: Stores extracted frames

---

## Demo Application: Video Processing Pipeline

### Use Case

Automatically detect when a child says "67" using hand gestures in uploaded videos, extract that frame, and save it to a separate bucket.

### Technology Stack

- **FastAPI**: Web framework for the Cloud Run service
- **Google Cloud Storage**: File storage
- **Eventarc**: Event routing
- **Cloud Run**: Serverless container platform
- **Gemini API**: AI video analysis
- **OpenCV**: Video frame extraction

### Workflow

1. User uploads video to source bucket
2. Eventarc detects the upload event
3. Cloud Run service is triggered via HTTP POST
4. Service downloads video from GCS
5. Video is uploaded to Gemini API for analysis
6. Gemini identifies timestamp when "67" is shown
7. Frame is extracted at that timestamp
8. Frame is saved to destination bucket

---

## Deep Dive into Eventarc

### Event Types

#### Cloud Storage Events

```yaml
google.cloud.storage.object.v1.finalized
  - Triggered when object upload completes
  - Contains: bucket, name, size, contentType, etc.

google.cloud.storage.object.v1.archived
  - Triggered when object moved to archive storage

google.cloud.storage.object.v1.deleted
  - Triggered when object is deleted

google.cloud.storage.object.v1.metadataUpdated
  - Triggered when object metadata changes
```

### Event Format

Eventarc sends events in CloudEvents format:

```json
{
  "specversion": "1.0",
  "type": "google.cloud.storage.object.v1.finalized",
  "source": "//storage.googleapis.com/buckets/my-bucket",
  "id": "1234567890",
  "time": "2025-11-19T00:00:00Z",
  "datacontenttype": "application/json",
  "data": {
    "bucket": "my-bucket",
    "name": "video.mp4",
    "contentType": "video/mp4",
    "size": "3525834",
    "timeCreated": "2025-11-19T00:00:00Z"
  }
}
```

However, in our implementation, Eventarc sends the GCS object metadata directly:

```json
{
  "kind": "storage#object",
  "id": "bucket/object/123456",
  "bucket": "video-raw-project-id",
  "name": "67.mp4",
  "contentType": "video/mp4",
  "size": "3525834"
}
```

### Event Filtering

Eventarc supports filtering to route only specific events:

```bash
# Filter by bucket
--event-filters="bucket=my-bucket"

# Filter by object prefix
--event-filters="prefix=uploads/"

# Filter by content type
--event-filters="contentType=video/mp4"

# Multiple filters (AND logic)
--event-filters="bucket=my-bucket" \
--event-filters="prefix=videos/"
```

### Trigger Configuration

```bash
gcloud eventarc triggers create video-upload-trigger \
  --location=us-central1 \
  --destination-run-service=video-processor \
  --destination-run-region=us-central1 \
  --event-filters="type=google.cloud.storage.object.v1.finalized" \
  --event-filters="bucket=video-raw-${PROJECT_ID}" \
  --service-account=service-${PROJECT_NUMBER}@gs-project-accounts.iam.gserviceaccount.com
```

**Key Parameters:**
- `location`: Region where trigger is created
- `destination-run-service`: Cloud Run service to invoke
- `event-filters`: Conditions for event matching
- `service-account`: IAM account for authentication

### IAM Requirements

Eventarc needs specific permissions:

1. **Service Account**: Must have `roles/pubsub.publisher` to publish events
2. **Cloud Run**: Must allow Eventarc to invoke it (authenticated requests)
3. **Eventarc Service**: Needs `roles/eventarc.eventReceiver` on the destination

---

## Implementation Details

### Request Handling

Our Cloud Run service receives HTTP POST requests from Eventarc:

```python
@app.post("/")
async def handle_event(request: Request):
    request_body = await request.json()
    
    # Extract bucket and object name
    bucket_name = request_body.get("bucket")
    object_name = request_body.get("name")
    
    # Process the video
    # ...
```

### Event Parsing

We handle multiple event formats for compatibility:

```python
# Try top-level fields first (most common)
bucket_name = request_body.get("bucket")
object_name = request_body.get("name")

# Fallback to nested data field (CloudEvent format)
if not bucket_name or not object_name:
    data = request_body.get("data", {})
    if isinstance(data, dict):
        bucket_name = data.get("bucket")
        object_name = data.get("name")
    elif isinstance(data, str):
        # Handle base64-encoded data
        decoded_data = json.loads(base64.b64decode(data).decode('utf-8'))
        bucket_name = decoded_data.get("bucket")
        object_name = decoded_data.get("name")
```

### Video Processing Flow

```python
def detect_kid_saying_67_with_gemini(video_path: str):
    # 1. Upload video to Gemini API
    video_file = genai_client.files.upload(file=video_path)
    
    # 2. Wait for file to be ACTIVE
    while video_file.state.name != "ACTIVE":
        time.sleep(2)
        video_file = genai_client.files.get(name=video_file.name)
    
    # 3. Analyze with Gemini
    response = genai_client.models.generate_content(
        model="gemini-2.0-flash",
        contents=types.Content(parts=[...])
    )
    
    # 4. Extract timestamp
    target_second = float(data["second"])
    
    # 5. Extract frame
    cap = cv2.VideoCapture(video_path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
    ret, frame = cap.read()
    
    return True, target_second, frame
```

### Error Handling

```python
try:
    # Process video
    kid_detected, target_second, kid_frame = detect_kid_saying_67_with_gemini(tmp_video_name)
except Exception as e:
    logger.error(f"Error processing video: {str(e)}", exc_info=True)
    return {"status": "error", "message": str(e)}, 500
finally:
    # Cleanup
    if os.path.exists(tmp_video_name):
        os.unlink(tmp_video_name)
```

---

## Best Practices

### 1. Idempotency

**Problem**: Events can be delivered multiple times.

**Solution**: Make handlers idempotent—processing the same event multiple times should produce the same result.

```python
# Example: Check if frame already exists
frame_name = f"{object_name}-kid-67-frame-{target_second:.1f}s.png"
if out_blob.exists():
    logger.info(f"Frame already exists: {frame_name}")
    return {"status": "ok", "message": "already processed"}
```

### 2. Error Handling and Retries

**Best Practices:**
- Return appropriate HTTP status codes
- Log errors with context
- Use structured logging
- Implement exponential backoff for external APIs

```python
# Good: Structured error response
return {
    "status": "error",
    "message": str(e),
    "error_code": "PROCESSING_FAILED",
    "timestamp": datetime.utcnow().isoformat()
}, 500

# Good: Retry logic for external APIs
max_retries = 3
for attempt in range(max_retries):
    try:
        response = genai_client.models.generate_content(...)
        break
    except Exception as e:
        if attempt == max_retries - 1:
            raise
        time.sleep(2 ** attempt)  # Exponential backoff
```

### 3. Resource Cleanup

**Always clean up resources:**
- Temporary files
- Uploaded files to external services
- Database connections
- Memory-intensive objects

```python
video_file = None
try:
    video_file = genai_client.files.upload(file=video_path)
    # ... process ...
finally:
    if video_file:
        try:
            genai_client.files.delete(name=video_file.name)
        except Exception as e:
            logger.warning(f"Cleanup failed: {str(e)}")
```

### 4. Timeout Management

**Set appropriate timeouts:**
- Cloud Run default timeout: 300 seconds
- For long-running tasks, consider:
  - Increasing timeout
  - Using async processing
  - Breaking into smaller tasks

```python
# Set timeout in Cloud Run deployment
gcloud run deploy video-processor \
  --timeout=600  # 10 minutes
```

### 5. Logging and Monitoring

**Structured Logging:**
```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Use appropriate log levels
logger.info("Processing started")
logger.warning("Retry attempt")
logger.error("Processing failed", exc_info=True)
```

**Key Metrics to Monitor:**
- Event processing latency
- Error rates
- Success/failure counts
- Resource usage (CPU, memory)

### 6. Security

**IAM Best Practices:**
- Use service accounts with least privilege
- Don't use default service accounts
- Rotate credentials regularly
- Use Secret Manager for sensitive data

```bash
# Use Secret Manager instead of environment variables
gcloud run deploy video-processor \
  --update-secrets=GEMINI_API_KEY=gemini-api-key:latest
```

**Input Validation:**
```python
# Validate file type
allowed_extensions = ['.mp4', '.mov', '.avi']
if not any(object_name.lower().endswith(ext) for ext in allowed_extensions):
    return {"status": "error", "message": "Invalid file type"}, 400

# Validate file size
MAX_SIZE = 100 * 1024 * 1024  # 100MB
if blob.size > MAX_SIZE:
    return {"status": "error", "message": "File too large"}, 400
```

### 7. Event Filtering

**Filter at the trigger level to reduce unnecessary invocations:**
```bash
# Only process videos
--event-filters="contentType=video/mp4"

# Only process files in specific folder
--event-filters="prefix=videos/"

# Combine filters
--event-filters="bucket=my-bucket" \
--event-filters="prefix=videos/" \
--event-filters="contentType=video/mp4"
```

### 8. Scalability

**Design for horizontal scaling:**
- Stateless services
- No shared state
- Use external storage (GCS, databases)
- Handle concurrent requests

**Cloud Run Auto-scaling:**
```bash
# Configure scaling
gcloud run deploy video-processor \
  --min-instances=0 \
  --max-instances=10 \
  --concurrency=80 \
  --cpu=2 \
  --memory=4Gi
```

### 9. Cost Optimization

**Strategies:**
- Use appropriate instance sizes
- Set min-instances=0 for low traffic
- Use regional buckets (cheaper than multi-regional)
- Clean up temporary files promptly
- Monitor and optimize API calls

### 10. Testing

**Test Event Format Locally:**
```python
# Create test event
test_event = {
    "bucket": "test-bucket",
    "name": "test-video.mp4",
    "contentType": "video/mp4"
}

# Test handler
response = await handle_event(Request({"json": lambda: test_event}))
```

**Integration Testing:**
- Test with actual GCS events
- Verify error handling
- Test retry scenarios
- Validate cleanup

---

## Troubleshooting

### Common Issues

#### 1. Events Not Triggering

**Symptoms**: No logs, service not invoked

**Solutions:**
- Check trigger configuration: `gcloud eventarc triggers describe TRIGGER_NAME`
- Verify IAM permissions
- Check service account has `roles/pubsub.publisher`
- Verify event filters match your events
- Check Cloud Run service is deployed and healthy

```bash
# Verify trigger
gcloud eventarc triggers list --location=us-central1

# Check IAM
gcloud projects get-iam-policy $PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:service-*"
```

#### 2. 403 Forbidden Errors

**Symptoms**: `Permission denied` in logs

**Solutions:**
- Verify service account permissions
- Check Cloud Run allows authenticated invocations
- Ensure Eventarc service agent has proper roles

```bash
# Grant Eventarc permission
gcloud run services add-iam-policy-binding video-processor \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gs-project-accounts.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
```

#### 3. Timeout Errors

**Symptoms**: `Request timeout` after 300 seconds

**Solutions:**
- Increase Cloud Run timeout
- Optimize processing time
- Use async processing for long tasks
- Break into smaller operations

```bash
# Increase timeout
gcloud run deploy video-processor --timeout=600
```

#### 4. Event Format Mismatch

**Symptoms**: `missing bucket or name` errors

**Solutions:**
- Log the actual event structure
- Handle multiple event formats
- Check Eventarc documentation for format changes

```python
# Always log received events
logger.info(f"Received event: {json.dumps(request_body, indent=2)}")
```

#### 5. Resource Exhaustion

**Symptoms**: Out of memory, CPU throttling

**Solutions:**
- Increase Cloud Run resources
- Optimize code (clean up resources)
- Process in batches
- Use streaming for large files

```bash
# Increase resources
gcloud run deploy video-processor \
  --memory=4Gi \
  --cpu=2
```

### Debugging Commands

```bash
# View recent logs
gcloud logging read \
  "resource.type=cloud_run_revision AND resource.labels.service_name=video-processor" \
  --limit=50 \
  --format=json

# Check trigger status
gcloud eventarc triggers describe video-upload-trigger \
  --location=us-central1

# Test service directly
curl -X POST https://video-processor-xxx.run.app/ \
  -H "Content-Type: application/json" \
  -d '{"bucket":"test","name":"test.mp4"}'

# Monitor in real-time
gcloud logging tail "resource.type=cloud_run_revision"
```

---

## Conclusion

Event-driven architecture with Eventarc provides a powerful, scalable way to build reactive systems. Key takeaways:

1. **Eventarc simplifies event routing** - No need to manage message queues manually
2. **Loose coupling enables flexibility** - Easy to add new consumers
3. **Automatic retries improve reliability** - Built-in resilience
4. **Serverless scales automatically** - Pay only for what you use
5. **Best practices ensure production readiness** - Idempotency, error handling, monitoring

### Next Steps

- Explore other event sources (Pub/Sub, Audit Logs)
- Implement dead letter queues for failed events
- Add monitoring dashboards
- Implement event replay for reprocessing
- Consider event sourcing patterns

### Resources

- [Eventarc Documentation](https://cloud.google.com/eventarc/docs)
- [Cloud Events Specification](https://cloudevents.io/)
- [Cloud Run Best Practices](https://cloud.google.com/run/docs/tips)
- [Event-Driven Architecture Patterns](https://martinfowler.com/articles/201701-event-driven.html)

---

**Author**: Generated for DevFest Event-Driven Architecture Demo  
**Last Updated**: November 2025

