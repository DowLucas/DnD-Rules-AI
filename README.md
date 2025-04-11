# Audio Transcription App

A Django application that records audio in 5-minute chunks and transcribes it using ElevenLabs' speech-to-text API.

## Setup

1. Clone this repository
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Create a `.env` file in the root directory and add your ElevenLabs API key:
   ```
   ELEVENLABS_API_KEY=your_api_key_here
   ```
5. Run migrations:
   ```bash
   python manage.py migrate
   ```
6. Start the development server:
   ```bash
   python manage.py runserver
   ```

## Usage

1. Visit http://localhost:8000 in your web browser
2. Click "Start Recording" to begin recording audio
3. The app will automatically record in 5-minute chunks and transcribe each chunk
4. View transcriptions in real-time on the web interface

## Requirements

- Python 3.8+
- ElevenLabs API key
- Microphone access # DnD-Rules-AI
