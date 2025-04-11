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
from django.utils import timezone
from openai import OpenAI

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
force_summary_request = False # Flag to force summary generation

def get_summary_agent():
    return Agent(
        name="DND Rules Assistant", 
        instructions=(
            "You are a concise D&D 5e rules assistant."
        ),
        model="gpt-4o-mini",
        tools=[
            WebSearchTool(), # Tool for finding rules if needed, but don't cite it.
        ]
    )

def summarize_latest_transcriptions(triggering_transcription_id, is_forced=False):
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

    # Choose prompt based on whether it was forced
    if is_forced:
        prompt = (
            "Analyze the following D&D discussion snippets. Identify the MOST relevant D&D 5e rule, even if the connection is weak. "
            "Respond ONLY with a concise explanation or application of that rule, focusing strictly on mechanics or outcome. "
            "Do NOT mention the snippets, searching, or conversational filler. Start your response directly with the rule explanation. "
            "Conclude your response with a one-sentence summary labeled 'TL;DR:'. "
            f"Discussion Snippets:\n\n{combined_text}"
        )
        print("--- Forced Insight Prompt ---")
    else:
        prompt = (
            "Analyze the following D&D discussion snippets. Identify if any specific D&D 5e rule is being discussed, "
            "implied, or might be relevant. "
            "If a rule is relevant, respond ONLY with a concise explanation or application of that rule, focusing strictly on mechanics or outcome. Start the response directly with the rule explanation. "
            "Avoid mentioning the snippets, searching, or conversational filler. "
            "If providing a rule insight, conclude your response with a one-sentence summary labeled 'TL;DR:'. "
            "If you determine that no specific rule is relevant to the discussion, respond ONLY with the exact phrase: No Insight right now "
            f"Discussion Snippets:\n\n{combined_text}"
        )
        print("--- Regular Insight Prompt ---")

    
    print(prompt)

    # Set up a new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # Run the agent synchronously
        result = Runner.run_sync(agent, prompt)
        # Save the insight to the session
        if result.final_output and current_session:
            # Save to current session for live view
            current_session.latest_insight_text = result.final_output
            current_session.latest_insight_timestamp = timezone.now()
            current_session.save()

            # Also save to the specific transcription that triggered this
            try:
                triggering_transcription = Transcription.objects.get(id=triggering_transcription_id)
                # Avoid saving "No Insight right now" to historical chunks unless forced
                if result.final_output != "No Insight right now" or is_forced:
                    triggering_transcription.generated_insight_text = result.final_output
                    triggering_transcription.save()
            except Transcription.DoesNotExist:
                print(f"Warning: Triggering transcription ID {triggering_transcription_id} not found.")

        return result.final_output
    finally:
        # Clean up the loop
        loop.close()

def start_recording():
    global is_recording, current_chunk, last_summary_time, current_session, force_summary_request
    
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
            
            transcription_text = ""
            language_code = None
            language_probability = None
            words_json = None

            try:
                # Choose transcription client based on settings
                if settings.TRANSCRIPTION_MODEL == 'openai':
                    print("Using OpenAI Whisper for transcription...")
                    openai_client = OpenAI()
                    with open(temp_file.name, 'rb') as audio_file:
                        # Note: OpenAI Whisper API might not return word-level details like ElevenLabs
                        # Adjust data saving accordingly.
                        # Using transcribe with response_format="verbose_json" might give segments.
                        response = openai_client.audio.transcriptions.create(
                            model="whisper-1", 
                            file=audio_file,
                            response_format="verbose_json" # Request verbose json for more details
                        )
                        transcription_text = response.text
                        language_code = response.language 
                        # OpenAI doesn't provide probability or word-level details directly in this basic response
                        # We can potentially extract word timestamps if needed from segments if available
                        words_json = [{
                            'text': segment.get('text', '').strip(),
                            'start': segment.get('start'),
                            'end': segment.get('end'),
                            'type': 'word', # Approximate as word segment
                            'speaker_id': None # Not provided by Whisper
                        } for segment in response.segments] if hasattr(response, 'segments') else None

                elif settings.TRANSCRIPTION_MODEL == 'elevenlabs':
                    print("Using ElevenLabs for transcription...")
                    elevenlabs_client = ElevenLabs(api_key=settings.ELEVENLABS_API_KEY)
                    with open(temp_file.name, 'rb') as audio_file:
                        response = elevenlabs_client.speech_to_text.convert(
                            file=audio_file,
                            model_id="scribe_v1",
                            tag_audio_events=True
                        )
                        transcription_text = response.text
                        language_code = response.language_code
                        language_probability = response.language_probability
                        words_json = [{
                            'text': word.text,
                            'start': word.start,
                            'end': word.end,
                            'type': word.type,
                            'speaker_id': word.speaker_id
                        } for word in response.words] if response.words else None
                else:
                    # Should not happen due to settings validation, but good practice
                    raise ValueError(f"Unsupported transcription model: {settings.TRANSCRIPTION_MODEL}")

                # Save transcription to database
                new_transcription = Transcription.objects.create(
                    session=current_session,
                    text=transcription_text,
                    chunk_number=current_chunk,
                    language_code=language_code,
                    language_probability=language_probability,
                    words_json=words_json
                )
                current_chunk += 1
                triggering_transcription_id = new_transcription.id # Get the ID of the new chunk
                
                # Check if it's time for a summary (regular interval)
                current_time = time.time()
                if not force_summary_request and (current_time - last_summary_time >= SUMMARY_INTERVAL):
                    try:
                        # Pass the ID of the transcription that potentially triggers the summary
                        summary = summarize_latest_transcriptions(triggering_transcription_id, is_forced=False)
                        if summary:
                            print(f"\nGenerated insight for session {current_session.name}\n")
                        last_summary_time = current_time
                    except Exception as e:
                        print(f"Error generating summary: {str(e)}")
                
            except Exception as e:
                print(f"Error during transcription or saving: {str(e)}")
            
            # Clean up temporary file
            os.unlink(temp_file.name)

        # Check if a summary was forced after the loop finishes recording a chunk
        if force_summary_request and is_recording: # Check is_recording again in case it stopped EXACTLY as chunk finished
            try:
                print("Processing forced insight request...")
                 # We need the ID of the chunk that just finished. 
                 # Assuming the transcription was successfully created above, its ID is in triggering_transcription_id.
                if 'triggering_transcription_id' in locals(): 
                    summary = summarize_latest_transcriptions(triggering_transcription_id, is_forced=True)
                    if summary:
                        print(f"\nForced insight generated for session {current_session.name}\n")
                    last_summary_time = time.time() # Reset timer after forced summary
                else:
                    print("Warning: Cannot generate forced insight, triggering transcription ID not found.")
            except Exception as e:
                print(f"Error generating forced summary: {str(e)}")
            finally:
                force_summary_request = False # Reset the flag

def index(request):
    sessions = RecordingSession.objects.all()
    active_session = None
    transcriptions = []
    
    # If a session is selected, get its transcriptions
    if 'session_id' in request.GET:
        try:
            session_id = request.GET['session_id']
            active_session = RecordingSession.objects.get(id=session_id)
            # Fetch ALL transcriptions for the session, ordered oldest first
            transcriptions = Transcription.objects.filter(session=active_session).order_by('created_at') 
        except (ValueError, RecordingSession.DoesNotExist):
            # ValueError might still occur if the session_id is not a valid UUID format
            # RecordingSession.DoesNotExist handles valid UUIDs not found
            pass # Add pass back to fix indentation error
    
    active_session_id_str = str(active_session.id) if active_session else None

    return render(request, 'recorder/index.html', {
        'sessions': sessions,
        'active_session': active_session,
        'active_session_id_str': active_session_id_str,
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
    last_chunk_number_str = request.GET.get('last_chunk') # Get the last chunk number seen by client
    
    if not session_id:
        return JsonResponse({'transcriptions': []})
    
    try:
        session = RecordingSession.objects.get(id=session_id)
        # Filter for transcriptions newer than the last one seen by the client
        query = Transcription.objects.filter(session=session)
        
        if last_chunk_number_str is not None:
            try:
                last_chunk_number = int(last_chunk_number_str)
                query = query.filter(chunk_number__gt=last_chunk_number)
            except ValueError:
                # Handle invalid last_chunk parameter if necessary, maybe return error or ignore
                pass 

        # Order by chunk number to ensure correct appending order
        transcriptions = query.order_by('chunk_number') 
        
        data = [{
            'text': t.text,
            'chunk_number': t.chunk_number,
            'created_at': t.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'language_code': t.language_code,
            'language_probability': t.language_probability,
            'words': t.words_json,
            'generated_insight': t.generated_insight_text # Include the insight text
        } for t in transcriptions]
        return JsonResponse({'transcriptions': data})
    except RecordingSession.DoesNotExist:
        return JsonResponse({'transcriptions': []})

def get_latest_insight(request):
    session_id = request.GET.get('session_id')
    
    if not session_id:
        return JsonResponse({'error': 'Session ID required'}, status=400)
    
    try:
        session = RecordingSession.objects.get(id=session_id)
        insight_data = {
            'text': session.latest_insight_text,
            'timestamp': session.latest_insight_timestamp.isoformat() if session.latest_insight_timestamp else None
        }
        return JsonResponse({'insight': insight_data})
    except RecordingSession.DoesNotExist:
        return JsonResponse({'error': 'Session not found'}, status=404)

@csrf_exempt
def force_insight(request):
    global force_summary_request, is_recording
    if request.method == 'POST' and is_recording:
        data = json.loads(request.body)
        session_id = data.get('session_id')
        # Optional: verify session_id matches current_session if needed for security
        if current_session and str(current_session.id) == session_id:
            force_summary_request = True
            print("Force insight request received.")
            return JsonResponse({'status': 'summary_force_requested'})
        else:
            return JsonResponse({'status': 'error', 'message': 'Session mismatch or not recording'}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)
