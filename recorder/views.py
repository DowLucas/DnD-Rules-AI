import json
import os
import tempfile
import time
import asyncio
from threading import Thread
from django.utils import timezone
from django.conf import settings
from django.http import JsonResponse
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from elevenlabs import ElevenLabs
from openai import OpenAI
from agents import Agent, Runner, WebSearchTool, FileSearchTool

# Import pydub for audio conversion
try:
    from pydub import AudioSegment
    ffmpeg_check = True
    # Basic check if ffmpeg might be available (pydub will raise specific error if not)
    if os.system('ffmpeg -version > /dev/null 2>&1') != 0:
         print("WARNING: ffmpeg command not found. Audio conversion might fail. Please install ffmpeg.")
except ImportError:
    print("WARNING: pydub not installed. Audio conversion will be skipped. Run: pip install pydub")
    AudioSegment = None
    ffmpeg_check = False

from .models import Transcription, RecordingSession
from .serializers import TranscriptionSerializer, RecordingSessionSerializer

if not os.environ.get("OPENAI_API_KEY"):
    print("OPENAI_API_KEY is not set")
    exit()

# Global variables - Removed recording state vars
current_session = None # Kept for insight generation context
SUMMARY_INTERVAL = 20 # Interval still relevant for automated insights
last_summary_time = 0 # Keep track of summary timing

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

# is_forced is now only triggered by the dedicated force_insight endpoint
def summarize_latest_transcriptions(triggering_transcription_id, is_forced=False):
    # Find the session associated with the triggering transcription
    try:
        triggering_transcription = Transcription.objects.get(id=triggering_transcription_id)
        session_for_summary = triggering_transcription.session
    except Transcription.DoesNotExist:
        print(f"Error: Triggering transcription ID {triggering_transcription_id} not found for summary.")
        return None

    if not session_for_summary:
         print(f"Error: Transcription {triggering_transcription_id} has no associated session.")
         return None

    # Get the 6 most recent transcriptions for the relevant session
    latest_transcriptions = Transcription.objects.filter(session=session_for_summary).order_by('-created_at')[:6]

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
        if result.final_output and session_for_summary:
            # Save to current session for live view
            session_for_summary.latest_insight_text = result.final_output
            session_for_summary.latest_insight_timestamp = timezone.now()
            session_for_summary.save()

            # Also save to the specific transcription that triggered this
            # Avoid saving "No Insight right now" to historical chunks unless forced
            if result.final_output != "No Insight right now" or is_forced:
                triggering_transcription.generated_insight_text = result.final_output
                triggering_transcription.save()
            else:
                print("Skipping update of transcription insight for 'No Insight right now'.")

        return result.final_output
    except Exception as e:
        print(f"Error running summary agent: {e}")
        return None # Ensure None is returned on agent error
    finally:
        # Clean up the loop
        loop.close()


# Removed start_recording function


# API Viewsets
class RecordingSessionViewSet(viewsets.ModelViewSet):
    queryset = RecordingSession.objects.all()
    serializer_class = RecordingSessionSerializer
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    # Removed toggle_recording action - Recording is handled by frontend

    @action(detail=True, methods=['post'])
    def upload_chunk(self, request, pk=None):
        global last_summary_time # Need to update this
        session = self.get_object()

        # Get uploaded file - assumes frontend sends it with name 'audio_chunk'
        if 'audio_chunk' not in request.FILES:
            return Response({'error': 'No audio chunk file found in request'}, status=status.HTTP_400_BAD_REQUEST)

        audio_file = request.FILES['audio_chunk']

        # Determine the next chunk number sequentially for this session
        last_chunk = Transcription.objects.filter(session=session).order_by('-chunk_number').first()
        current_chunk_number = (last_chunk.chunk_number + 1) if last_chunk else 0

        # Save the uploaded chunk temporarily (use original extension if possible)
        original_filename = audio_file.name
        _, original_ext = os.path.splitext(original_filename)
        if not original_ext: # Default to .webm if no extension found
            original_ext = '.webm'

        temp_file_path = None
        converted_file_path = None

        try:
            # Save the original uploaded file
            with tempfile.NamedTemporaryFile(suffix=original_ext, delete=False) as temp_file:
                for chunk_content in audio_file.chunks():
                    temp_file.write(chunk_content)
                temp_file_path = temp_file.name
                print(f"Saved original chunk {current_chunk_number} to {temp_file_path}")

            # Attempt conversion to WAV if pydub is available
            if AudioSegment and ffmpeg_check:
                print(f"Attempting to convert {temp_file_path} to WAV...")
                try:
                    audio = AudioSegment.from_file(temp_file_path) # Let pydub detect format
                    # Create a new temporary file for the WAV version
                    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as converted_file:
                        audio.export(converted_file.name, format="wav")
                        converted_file_path = converted_file.name
                    print(f"Successfully converted chunk {current_chunk_number} to {converted_file_path}")
                    # Use the converted file path for transcription
                    transcription_input_path = converted_file_path
                except Exception as conversion_error:
                    print(f"WARNING: Failed to convert {temp_file_path} to WAV: {conversion_error}. Attempting transcription with original file.")
                    # Fallback to original file if conversion fails
                    transcription_input_path = temp_file_path
            else:
                print(f"Skipping audio conversion for chunk {current_chunk_number}. Using original file: {temp_file_path}")
                transcription_input_path = temp_file_path

            # --- Transcription Logic --- (Now uses transcription_input_path)
            if settings.TRANSCRIPTION_MODEL == 'openai':
                print(f"Using OpenAI Whisper ({transcription_input_path}) for chunk {current_chunk_number}...")
                openai_client = OpenAI()
                with open(transcription_input_path, 'rb') as audio_input:
                    response = openai_client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_input,
                        response_format="verbose_json"
                    )
                    transcription_text = response.text
                    language_code = response.language
                    words_json = [{
                        'text': segment.get('text', '').strip(),
                        'start': segment.get('start'),
                        'end': segment.get('end'),
                        'type': 'word',
                        'speaker_id': None
                    } for segment in response.segments] if hasattr(response, 'segments') else None

            elif settings.TRANSCRIPTION_MODEL == 'elevenlabs':
                print(f"Using ElevenLabs ({transcription_input_path}) for chunk {current_chunk_number}...")
                elevenlabs_client = ElevenLabs(api_key=settings.ELEVENLABS_API_KEY)
                with open(transcription_input_path, 'rb') as audio_input:
                    response = elevenlabs_client.speech_to_text.convert(
                        file=audio_input,
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
                raise ValueError(f"Unsupported transcription model: {settings.TRANSCRIPTION_MODEL}")

            # Save transcription to database
            new_transcription = Transcription.objects.create(
                session=session,
                text=transcription_text,
                chunk_number=current_chunk_number,
                language_code=language_code,
                language_probability=language_probability,
                words_json=words_json
            )
            print(f"Chunk {current_chunk_number} transcribed and saved.")

            # --- Automatic Insight Generation Logic ---
            current_time = time.time()
            # Only trigger summary if text exists and interval has passed
            if transcription_text.strip() and (current_time - last_summary_time >= SUMMARY_INTERVAL):
                 print(f"Automatic summary interval reached for session {session.id}")
                 last_summary_time = current_time
                 # Run summary generation in a background thread
                 summary_thread = Thread(target=summarize_latest_transcriptions,
                                         args=(new_transcription.id, False))
                 summary_thread.daemon = True
                 summary_thread.start()
            else:
                 print(f"Skipping automatic summary for chunk {current_chunk_number} (Interval: {current_time - last_summary_time:.1f}s)")

            # Return success response with basic transcription info
            serializer = TranscriptionSerializer(new_transcription)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            print(f"Error processing audio chunk {current_chunk_number}: {e}")
            # Return error response
            return Response({'error': f'Failed to process audio chunk: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        finally:
            # Clean up both temporary files if they exist
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                    print(f"Original temporary file {temp_file_path} deleted.")
                except Exception as unlink_error:
                    print(f"Error deleting original temporary file {temp_file_path}: {unlink_error}")
            if converted_file_path and os.path.exists(converted_file_path):
                 try:
                    os.unlink(converted_file_path)
                    print(f"Converted temporary file {converted_file_path} deleted.")
                 except Exception as unlink_error:
                    print(f"Error deleting converted temporary file {converted_file_path}: {unlink_error}")

    @action(detail=True, methods=['get'])
    def latest_transcriptions(self, request, pk=None):
        session = self.get_object()
        # Get the latest 5 transcriptions
        latest_transcriptions = Transcription.objects.filter(session=session).order_by('-created_at')[:5]
        serializer = TranscriptionSerializer(latest_transcriptions, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def latest_insight(self, request, pk=None):
        session = self.get_object()
        if session.latest_insight_text and session.latest_insight_timestamp:
            return Response({
                'insight': session.latest_insight_text,
                'timestamp': session.latest_insight_timestamp
            })
        else:
            return Response({'insight': None, 'timestamp': None})

    @action(detail=True, methods=['post'])
    def force_insight(self, request, pk=None):
        session = self.get_object()

        # Get the last transcription for this session to use as a trigger point
        last_transcription = Transcription.objects.filter(session=session).order_by('-created_at').first()

        if not last_transcription:
            return Response({'error': 'No transcriptions available to generate insight from'}, status=status.HTTP_400_BAD_REQUEST)

        # Generate insight synchronously for API response
        print(f"Forcing insight generation for session {session.id}")
        insight = summarize_latest_transcriptions(last_transcription.id, is_forced=True)

        if insight is not None: # Check for None specifically in case agent fails
            return Response({'insight': insight})
        else:
            # Check if the session object has the latest insight text even if agent returned None here (race condition?)
            session.refresh_from_db()
            if session.latest_insight_text:
                 return Response({'insight': session.latest_insight_text})
            else:
                 return Response({'error': 'Failed to generate insight or insight was empty'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class TranscriptionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Transcription.objects.all()
    serializer_class = TranscriptionSerializer

    def get_queryset(self):
        queryset = Transcription.objects.all()
        # Filter by session if provided
        session_id = self.request.query_params.get('session_id', None)
        if session_id is not None:
            queryset = queryset.filter(session__id=session_id)
        return queryset.order_by('chunk_number') # Ensure chronological order
