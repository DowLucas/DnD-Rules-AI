# DnD Rules AI API Documentation

This document describes the REST API endpoints available in the DnD Rules AI application.

## Base URL

All API endpoints are accessible under the `/api/` base path.

## Authentication

Currently, the API does not require authentication.

## Recording Sessions

### List all sessions

```
GET /api/sessions/
```

Returns a list of all recording sessions.

### Create a new session

```
POST /api/sessions/
```

**Request Body**:

```json
{
  "name": "Session Name"
}
```

**Response**:

```json
{
  "id": "uuid",
  "name": "Session Name",
  "created_at": "timestamp",
  "latest_insight_text": null,
  "latest_insight_timestamp": null,
  "is_active": true,
  "transcriptions": []
}
```

### Get session details

```
GET /api/sessions/{session_id}/
```

Returns details for a specific session, including associated transcriptions.

### Update a session

```
PUT /api/sessions/{session_id}/
```

**Request Body**:

```json
{
  "name": "Updated Session Name",
  "is_active": false
}
```

### Delete a session

```
DELETE /api/sessions/{session_id}/
```

## Transcriptions

### List all transcriptions

```
GET /api/transcriptions/
```

Returns a list of all transcriptions, ordered by chunk number.

### Filter transcriptions by session

```
GET /api/transcriptions/?session_id={session_id}
```

Returns transcriptions for a specific session, ordered by chunk number.

### Get transcription details

```
GET /api/transcriptions/{transcription_id}/
```

Returns details for a specific transcription.

## Audio Processing & Insights

### Upload Audio Chunk

```
POST /api/sessions/{session_id}/upload_chunk/
```

Uploads a single audio chunk (e.g., a WAV or Blob file recorded by the frontend) for processing.

**Request Body**:

Send as `multipart/form-data`. Include the audio file under the key `audio_chunk`.

**Response**:

On success (status 201), returns the details of the created `Transcription` object:

```json
{
  "id": 123,
  "created_at": "timestamp",
  "text": "Transcribed text from the chunk",
  "chunk_number": 5,
  "language_code": "en",
  "language_probability": 0.99,
  "words_json": [
    /* word details */
  ],
  "generated_insight_text": null, // Insight might be generated later
  "full_text": "Formatted text"
}
```

On failure, returns an error message (e.g., status 400 or 500).

### Get Latest Transcriptions (Polling)

```
GET /api/sessions/{session_id}/latest_transcriptions/
```

Returns the 5 most recent transcriptions for the specified session. Useful for updating the UI in real-time.

### Get Latest Insight (Polling)

```
GET /api/sessions/{session_id}/latest_insight/
```

Returns the latest D&D rule insight generated for the session.

**Response**:

```json
{
  "insight": "Rule explanation text",
  "timestamp": "timestamp"
}
```

### Force Insight Generation

```
POST /api/sessions/{session_id}/force_insight/
```

Forces the generation of a new D&D rule insight based on recent transcriptions for the specified session.

**Response**:

```json
{
  "insight": "Rule explanation text"
}
```
