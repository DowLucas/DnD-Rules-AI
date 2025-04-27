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

### Ask Rules Question

```
POST /api/sessions/ask_rules_question/
```

Asks a specific D&D rules question and gets an answer using the AI assistant. This endpoint uses the vector database to search for relevant rules first.

**Request Body**:

```

```

## NPC Endpoints

### Get Campaign NPCs

Get all NPCs for a specific campaign.

**URL**: `/api/campaigns/{campaign_id}/npcs/`  
**Method**: `GET`  
**Auth required**: YES  
**Permissions required**: User must own the campaign

#### Success Response

**Code**: `200 OK`  
**Content example**:

```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "campaign": "550e8400-e29b-41d4-a716-446655440001",
    "name": "Gandalf",
    "description": "A wise wizard with a long beard",
    "created_at": "2023-04-20T12:00:00Z",
    "updated_at": "2023-04-20T12:00:00Z"
  },
  {
    "id": "550e8400-e29b-41d4-a716-446655440002",
    "campaign": "550e8400-e29b-41d4-a716-446655440001",
    "name": "Gollum",
    "description": "A corrupted creature obsessed with the Ring",
    "created_at": "2023-04-20T12:30:00Z",
    "updated_at": "2023-04-20T12:30:00Z"
  }
]
```

#### Error Response

**Condition**: If campaign doesn't exist or user doesn't own the campaign  
**Code**: `403 FORBIDDEN`  
**Content**:

```json
{
  "error": "You do not have permission to access this campaign."
}
```

### Create NPC

Create a new NPC for a specific campaign.

**URL**: `/api/campaigns/{campaign_id}/create_npc/`  
**Method**: `POST`  
**Auth required**: YES  
**Permissions required**: User must own the campaign

#### Request Body

```json
{
  "name": "Aragorn",
  "description": "A ranger and the rightful king of Gondor"
}
```

#### Success Response

**Code**: `201 CREATED`  
**Content example**:

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440003",
  "campaign": "550e8400-e29b-41d4-a716-446655440001",
  "name": "Aragorn",
  "description": "A ranger and the rightful king of Gondor",
  "created_at": "2023-04-20T13:00:00Z",
  "updated_at": "2023-04-20T13:00:00Z"
}
```

#### Error Response

**Condition**: If campaign doesn't exist or user doesn't own the campaign  
**Code**: `403 FORBIDDEN`  
**Content**:

```json
{
  "error": "You do not have permission to add NPCs to this campaign."
}
```

**Condition**: If missing required fields  
**Code**: `400 BAD REQUEST`  
**Content**:

```json
{
  "error": "NPC name is required."
}
```

**Condition**: If NPC with same name already exists in campaign  
**Code**: `400 BAD REQUEST`  
**Content**:

```json
{
  "error": "NPC with name \"Aragorn\" already exists in this campaign."
}
```

## Vector Store

### Get Vector Store Information

```
GET /api/documents/vector_store/
```

Returns information about the OpenAI vector store, including a list of files stored in it.

**Response**:

```json
{
  "id": "vs_abc123",
  "name": "My Vector Store",
  "file_count": 2,
  "files": [
    {
      "id": "vsfile_abc123",
      "object": "vector_store.file",
      "created_at": 1689947814,
      "status": "completed",
      "file_id": "file-abc123"
    },
    {
      "id": "vsfile_def456",
      "object": "vector_store.file",
      "created_at": 1689947912,
      "status": "completed",
      "file_id": "file-def456"
    }
  ]
}
```

### Get Vector Store Files with Details

```
GET /api/documents/vector_store_files/
```

Returns detailed information about files in the OpenAI vector store, including linking to local document records.

**Response**:

```json
{
  "vector_store_id": "vs_abc123",
  "vector_store_name": "My Vector Store",
  "file_count": 2,
  "files": [
    {
      "id": "vsfile_abc123",
      "file_id": "file-abc123",
      "filename": "rules_handbook.pdf",
      "status": "completed",
      "created_at": 1689947814,
      "document": {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "title": "DnD Rules Handbook",
        "description": "Official rules for Dungeons and Dragons",
        "created_at": "2023-04-20T12:00:00Z",
        "updated_at": "2023-04-20T12:00:00Z",
        "status": "COMPLETE"
      }
    },
    {
      "id": "vsfile_def456",
      "file_id": "file-def456",
      "filename": "monster_manual.pdf",
      "status": "completed",
      "created_at": 1689947912
    }
  ]
}
```

### Search Vector Store

```
POST /api/documents/vector_store_search/
```

Searches the OpenAI vector store for documents matching the query.

**Request Body**:

```json
{
  "query": "What is the return policy?",
  "filters": {
    "type": "eq",
    "key": "document_type",
    "value": "pdf"
  },
  "max_results": 10,
  "rewrite_query": true
}
```

**Response**:

```json
{
  "object": "vector_store.search_results.page",
  "search_query": "What is the return policy?",
  "data": [
    {
      "file_id": "file-abc123",
      "filename": "policy_document.pdf",
      "score": 0.95,
      "attributes": {
        "author": "Jane Doe",
        "date": "2023-01-10"
      },
      "content": [
        {
          "type": "text",
          "text": "Relevant chunk of text."
        }
      ]
    }
  ],
  "has_more": false,
  "next_page": null
}
```
