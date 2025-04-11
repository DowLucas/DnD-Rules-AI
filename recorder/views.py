import json
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from .models import Transcription, RecordingSession
import sounddevice as sd
import scipy.io.wavfile as wav
import numpy as np
import tempfile
import os
from elevenlabs import ElevenLabs
from threading import Thread
import time
from agents import Agent, Runner, WebSearchTool, FileSearchTool
import getpass
import asyncio

if not os.environ.get("OPENAI_API_KEY"):
  print("OPENAI_API_KEY is not set")
  exit()

# Global variables for recording state
is_recording = False
current_chunk = 0
CHUNK_DURATION = 10  # 10 seconds for development
SAMPLE_RATE = 44100
last_summary_time = 0
SUMMARY_INTERVAL = 20  # 30 seconds between summaries
current_session = None

def get_summary_agent():
    return Agent(
        name="DND Rules Master", 
        instructions="You are a professional DND 5e Dungeon Master.",
        model="gpt-4o-mini",
        tools=[
            WebSearchTool(),
        ]
    )

def summarize_latest_transcriptions():
    if not current_session:
        return None
    
    # Get the 6 most recent transcriptions for the current session
    latest_transcriptions = Transcription.objects.filter(session=current_session).order_by('-created_at')[:6]
    
    if not latest_transcriptions:
        return None
        
    # Combine the transcriptions into a single text
    combined_text = "\n".join([
        f"Chunk {t.chunk_number}: {t.text}"
        for t in latest_transcriptions
    ])
    
    # Create the summary agent and run it
    agent = get_summary_agent()
    prompt = f"You are tasked with searching the web based on the latest transcriptions. Focus on if there is a particular rule that is related to the latest transcriptions, and if so, provide the rule. Transcriptions:\n\n{combined_text}"
    
    print(prompt)

    # Set up a new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # Run the agent synchronously
        result = Runner.run_sync(agent, prompt)
        return result.final_output
    finally:
        # Clean up the loop
        loop.close()

def start_recording():
    global is_recording, current_chunk, last_summary_time, current_session
    
    if not current_session:
        return
        
    while is_recording:
        # Create a temporary file for the audio chunk
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
            # Record audio for the specified duration
            audio_data = sd.rec(int(CHUNK_DURATION * SAMPLE_RATE),
                              samplerate=SAMPLE_RATE,
                              channels=1,
                              dtype=np.int16)
            sd.wait()
            
            # Save the audio to the temporary file
            wav.write(temp_file.name, SAMPLE_RATE, audio_data)
            
            # Transcribe the audio using ElevenLabs
            client = ElevenLabs(api_key=settings.ELEVENLABS_API_KEY)
            try:
                with open(temp_file.name, 'rb') as audio_file:
                    transcription = client.speech_to_text.convert(
                        file=audio_file,
                        model_id="scribe_v1",
                        tag_audio_events=True  # Include audio events like mouse clicks
                    )
                
                # Save transcription to database with additional information
                Transcription.objects.create(
                    session=current_session,
                    text=transcription.text,
                    chunk_number=current_chunk,
                    language_code=transcription.language_code,
                    language_probability=transcription.language_probability,
                    words_json=[{
                        'text': word.text,
                        'start': word.start,
                        'end': word.end,
                        'type': word.type,
                        'speaker_id': word.speaker_id
                    } for word in transcription.words] if transcription.words else None
                )
                current_chunk += 1
                
                # Check if it's time for a summary
                current_time = time.time()
                if current_time - last_summary_time >= SUMMARY_INTERVAL:
                    try:
                        summary = summarize_latest_transcriptions()
                        if summary:
                            print(f"\nSummary of latest transcriptions (Session: {current_session.name}):\n{summary}\n")
                        last_summary_time = current_time
                    except Exception as e:
                        print(f"Error generating summary: {str(e)}")
                
            except Exception as e:
                print(f"Error during transcription: {str(e)}")
            
            # Clean up temporary file
            os.unlink(temp_file.name)

def index(request):
    sessions = RecordingSession.objects.all()
    active_session = None
    transcriptions = []
    
    # If a session is selected, get its transcriptions
    if 'session_id' in request.GET:
        try:
            session_id = int(request.GET['session_id'])
            active_session = RecordingSession.objects.get(id=session_id)
            transcriptions = Transcription.objects.filter(session=active_session)
        except (ValueError, RecordingSession.DoesNotExist):
            pass
    
    return render(request, 'recorder/index.html', {
        'sessions': sessions,
        'active_session': active_session,
        'transcriptions': transcriptions
    })

@csrf_exempt
def create_session(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        session_name = data.get('name', f"Session {RecordingSession.objects.count() + 1}")
        
        # Create a new session
        session = RecordingSession.objects.create(name=session_name)
        
        return JsonResponse({
            'status': 'success',
            'session': {
                'id': session.id,
                'name': session.name,
                'created_at': session.created_at.strftime('%Y-%m-%d %H:%M:%S')
            }
        })
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'})

@csrf_exempt
def toggle_recording(request):
    global is_recording, current_chunk, current_session
    
    if request.method == 'POST':
        data = json.loads(request.body)
        action = data.get('action')
        session_id = data.get('session_id')
        
        # Validate session
        try:
            current_session = RecordingSession.objects.get(id=session_id)
        except RecordingSession.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Invalid session'})
        
        # Reset chunk counter for the session
        if action == 'start' and not is_recording:
            # Get the highest chunk number for this session
            highest_chunk = Transcription.objects.filter(session=current_session).order_by('-chunk_number').first()
            current_chunk = (highest_chunk.chunk_number + 1) if highest_chunk else 0
            
            is_recording = True
            # Start recording in a separate thread
            recording_thread = Thread(target=start_recording)
            recording_thread.start()
            return JsonResponse({'status': 'started'})
            
        elif action == 'stop' and is_recording:
            is_recording = False
            return JsonResponse({'status': 'stopped'})
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request'})

def get_latest_transcriptions(request):
    session_id = request.GET.get('session_id')
    
    if not session_id:
        return JsonResponse({'transcriptions': []})
    
    try:
        session = RecordingSession.objects.get(id=session_id)
        transcriptions = Transcription.objects.filter(session=session)[:5]  # Get the 5 most recent transcriptions
        data = [{
            'text': t.text,
            'chunk_number': t.chunk_number,
            'created_at': t.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'language_code': t.language_code,
            'language_probability': t.language_probability,
            'words': t.words_json
        } for t in transcriptions]
        return JsonResponse({'transcriptions': data})
    except RecordingSession.DoesNotExist:
        return JsonResponse({'transcriptions': []})
