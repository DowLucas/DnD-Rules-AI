# DnD Rules AI - REST API

A Django REST API backend for the Session Scribe Dungeon application. This API receives recorded audio chunks from the frontend, transcribes them using either ElevenLabs or OpenAI Whisper, and generates D&D 5e rule insights based on the transcribed content.

## Features

- Accepts audio chunk uploads from a frontend application.
- Transcribes audio using ElevenLabs or OpenAI Whisper.
- Performs D&D 5e rule analysis and generates insights.
- Provides RESTful API endpoints for session management, transcription retrieval, and insight generation.

## Architecture

This project is the **backend** component. It relies on a separate **frontend** application (like `session-scribe-dungeon`) to handle:

1.  Accessing the user's microphone via browser APIs (`MediaRecorder`).
2.  Sending recorded audio chunks to this backend's `/api/sessions/{id}/upload_chunk/` endpoint.
3.  Polling this backend for new transcriptions and insights to display to the user.

## Setup (Backend)

1. Clone this repository (`DnD-Rules-AI`).
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Create a `.env` file in the root directory and add your API keys and settings:
   ```
   ELEVENLABS_API_KEY=your_elevenlabs_api_key_here
   OPENAI_API_KEY=your_openai_api_key_here
   DJANGO_SECRET_KEY=your_django_secret_key_here # Generate a strong secret key!
   DEBUG=True # Set to False in production
   TRANSCRIPTION_MODEL=elevenlabs  # or 'openai'
   ```
5. Run migrations:
   ```bash
   python manage.py migrate
   ```
6. Start the development server:
   ```bash
   python manage.py runserver
   ```

## API Usage

The application provides a RESTful API. See the [API Documentation](API.md) for details on all available endpoints.

### Example Workflow (from Frontend Perspective)

1.  **Create Session:** `POST /api/sessions/` (Body: `{"name": "My Session"}`) -> Get `session_id`.
2.  **Start Recording (Frontend):** Use browser `MediaRecorder`.
3.  **Upload Chunk (Frontend):** `POST /api/sessions/{session_id}/upload_chunk/` (Send audio file in `multipart/form-data` with key `audio_chunk`).
4.  **Repeat Step 3** for each audio chunk.
5.  **Poll for Updates (Frontend):**
    - `GET /api/sessions/{session_id}/latest_transcriptions/`
    - `GET /api/sessions/{session_id}/latest_insight/`
6.  **Stop Recording (Frontend):** Stop `MediaRecorder`.

## Requirements (Backend)

- Python 3.8+
- Django & Django REST Framework
- ElevenLabs API key and/or OpenAI API key
- Appropriate system libraries for transcription dependencies (if any beyond Python packages).
