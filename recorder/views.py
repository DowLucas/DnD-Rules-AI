import json
import os
import tempfile
import time
import asyncio
from threading import Thread
from django.utils import timezone
from django.conf import settings
from django.http import JsonResponse
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from elevenlabs import ElevenLabs
from openai import OpenAI
from agents import Agent, Runner, WebSearchTool, FileSearchTool
from agents.items import ToolCallItem, ToolCallOutputItem # Import specific item types
import requests

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

from .models import Transcription, RecordingSession, Campaign
from .serializers import (
    TranscriptionSerializer, 
    RecordingSessionSerializer,
    CampaignSerializer,
    CampaignListSerializer
)

if not os.environ.get("OPENAI_API_KEY"):
    print("OPENAI_API_KEY is not set")
    exit()

# Global variables - Removed recording state vars
current_session = None # Kept for insight generation context
SUMMARY_INTERVAL = 20 # Interval still relevant for automated insights
last_summary_time = 0 # Keep track of summary timing

def get_summary_agent():
    # Get the vector store ID from .env
    vector_store_id = os.environ.get('VECTOR_STORE_ID')
    
    # Create tools list, filtering out None values
    tools = [
        # WebSearchTool()]  # Tool for finding rules if needed, but don't cite it
    ]
    if vector_store_id:
        # Add FileSearchTool with include_search_results for debugging
        tools.append(FileSearchTool(
            vector_store_ids=[vector_store_id],
            include_search_results=True,
            max_num_results=5 # Optionally limit results
        ))
    
    return Agent(
        name="DND Rules Assistant",
        instructions=(
            "You are a concise D&D 5e rules assistant. "
            "First use the FileSearchTool to search the vector database of D&D rules when identifying relevant rules. "
            "If you can't find what you need in the vector database, fall back to the WebSearchTool. "
            "Provide clear, accurate rules information without citing your sources."
        ),
        model="gpt-4o-mini",
        tools=tools
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

    # Check for the most recent existing insight (other than "No Insight right now" responses)
    previous_insight = None
    # Look for insights in transcriptions first (excluding the current one)
    transcriptions_with_insights = Transcription.objects.filter(
        session=session_for_summary,
        generated_insight_text__isnull=False
    ).exclude(
        id=triggering_transcription_id
    ).exclude(
        generated_insight_text="No Insight right now"
    ).order_by('-created_at')
    
    if transcriptions_with_insights.exists():
        previous_insight = transcriptions_with_insights.first().generated_insight_text
    # If no insight found in transcriptions, check session's latest insight
    elif session_for_summary.latest_insight_text and session_for_summary.latest_insight_text != "No Insight right now":
        previous_insight = session_for_summary.latest_insight_text

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
            "Use the FileSearchTool to search the vector database for relevant rules first. "
            "Respond ONLY with a concise explanation or application of that rule, focusing strictly on mechanics or outcome. "
            "Do NOT mention the snippets, searching, or conversational filler. Start your response directly with the rule explanation. "
            "Conclude your response with a one-sentence summary labeled 'TL;DR:'. "
        )
        if previous_insight:
            prompt += (
                f"Previously, you identified this insight: \"{previous_insight}\"\n"
                "If the same rule is still relevant, elaborate on it rather than repeating information. "
                "If a completely different rule is now more relevant, focus on that instead.\n\n"
            )
        prompt += f"Discussion Snippets:\n\n{combined_text}"
        print("--- Forced Insight Prompt ---")
    else:
        prompt = (
            "Analyze the following D&D discussion snippets. Identify if any specific D&D 5e rule is being discussed, "
            "implied, or might be relevant. "
            "Use the FileSearchTool to search the vector database for relevant rules first. "
            "If a rule is relevant, respond ONLY with a concise explanation or application of that rule, focusing strictly on mechanics or outcome. Start the response directly with the rule explanation. "
            "Avoid mentioning the snippets, searching, or conversational filler. "
            "If providing a rule insight, conclude your response with a one-sentence summary labeled 'TL;DR:'. "
            "If you determine that no specific rule is relevant to the discussion, respond ONLY with the exact phrase: No Insight right now "
        )
        if previous_insight:
            prompt += (
                f"Previously, you identified this insight: \"{previous_insight}\"\n"
                "Only provide a new insight if the discussion has moved to a different rule or aspect. "
                "If there's nothing significantly new to add, respond with 'No Insight right now'.\n\n"
            )
        prompt += f"Discussion Snippets:\n\n{combined_text}"
        print("--- Regular Insight Prompt ---")

    print(prompt)

    # Set up a new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        # Run the agent synchronously
        result = Runner.run_sync(agent, prompt)

        # Print run items for debugging
        print_run_items(result)

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
class CampaignViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows campaigns to be viewed or edited.
    """
    queryset = Campaign.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'list':
            return CampaignListSerializer
        return CampaignSerializer

    def get_queryset(self):
        """
        This view should return a list of all the campaigns
        for the currently authenticated user.
        """
        user = self.request.user
        if user.is_authenticated:
            return Campaign.objects.filter(user=user).prefetch_related('sessions')
        return Campaign.objects.none()

    def perform_create(self, serializer):
        """
        Associate the campaign with the logged-in user upon creation.
        """
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def create_session(self, request, pk=None):
        """
        Creates a new RecordingSession associated with this campaign.
        Does not require any body data, just starts a new session.
        """
        campaign = self.get_object()

        # Ensure the user creating the session owns the campaign
        if campaign.user != request.user:
            return Response({'error': 'You do not have permission to add sessions to this campaign.'},
                            status=status.HTTP_403_FORBIDDEN)

        # Create a new session linked to this campaign
        new_session = RecordingSession.objects.create(campaign=campaign, is_active=True)
        serializer = RecordingSessionSerializer(new_session, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def upload_document(self, request, pk=None):
        """
        Upload a document associated with this campaign.
        
        Expects multipart/form-data with:
        - file: The document file
        - title: Document title
        - description: (optional) Document description
        """
        campaign = self.get_object()

        # Ensure the user uploading the document owns the campaign
        if campaign.user != request.user:
            return Response({'error': 'You do not have permission to add documents to this campaign.'},
                            status=status.HTTP_403_FORBIDDEN)
        
        # Get required fields
        file = request.FILES.get('file')
        title = request.data.get('title')
        description = request.data.get('description', '')
        
        if not file:
            return Response({'error': 'Document file is required.'},
                            status=status.HTTP_400_BAD_REQUEST)
        
        if not title:
            return Response({'error': 'Document title is required.'},
                            status=status.HTTP_400_BAD_REQUEST)
        
        from documents.services import DocumentService
        
        try:
            # Create the document with campaign association
            document = DocumentService.upload_document(
                file=file,
                title=title,
                description=description,
                user=request.user,
                campaign=campaign
            )
            
            from documents.serializers import DocumentSerializer
            serializer = DocumentSerializer(document)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        except Exception as e:
            return Response({'error': f'Error uploading document: {str(e)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class RecordingSessionViewSet(viewsets.ModelViewSet):
    queryset = RecordingSession.objects.all()
    serializer_class = RecordingSessionSerializer
    parser_classes = (MultiPartParser, FormParser, JSONParser)
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Filter sessions to only show those belonging to the user's campaigns.
        """
        user = self.request.user
        if user.is_authenticated:
            return RecordingSession.objects.filter(campaign__user=user).select_related('campaign').prefetch_related('transcriptions')
        return RecordingSession.objects.none()

    # Removed toggle_recording action - Recording is handled by frontend

    @action(detail=True, methods=['post'])
    def upload_chunk(self, request, pk=None):
        global last_summary_time # Need to update this
        session = self.get_object()  # Now filtered by user via get_queryset

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

    @action(detail=False, methods=['post'])
    def ask_rules_question(self, request):
        """
        Endpoint to ask manual D&D rules questions using the agent.
        Not tied to a specific session.
        
        Expected POST payload:
        {
            "question": "What are the rules for advantage and disadvantage?"
        }
        """
        # session = self.get_object() # No longer needed
        question = request.data.get('question')
        
        if not question:
            return Response({'error': 'Question is required'}, status=status.HTTP_400_BAD_REQUEST)
            
        # Create the summary agent
        agent = get_summary_agent()
        
        # Create a prompt for the rules question
        prompt = (
            "You are a D&D 5e rules assistant. Answer the following question clearly and concisely. "
            "Use the FileSearchTool to search the vector database of D&D rules first. "
            "If you can't find what you need in the vector database, use the WebSearchTool. "
            "Focus strictly on the rules mechanics or outcomes. "
            "Provide a comprehensive answer but avoid unnecessary verbosity.\n\n"
            f"Question: {question}"
        )
        
        # Set up a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Run the agent synchronously
            result = Runner.run_sync(agent, prompt)
            
            if result.final_output:
                return Response({'answer': result.final_output})
            else:
                return Response({'error': 'Failed to generate an answer'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            print(f"Error running agent for rules question: {e}")
            return Response({'error': f'Failed to answer question: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        finally:
            # Clean up the loop
            loop.close()

class TranscriptionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Transcription.objects.all()
    serializer_class = TranscriptionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Filter transcriptions to only show those belonging to sessions
        owned by the user's campaigns.
        Optionally filter by session ID if provided in query params.
        """
        user = self.request.user
        if not user.is_authenticated:
            return Transcription.objects.none()

        queryset = Transcription.objects.filter(session__campaign__user=user).select_related('session', 'session__campaign')

        # Allow filtering by session_id if provided in query params
        session_id = self.request.query_params.get('session_id')
        if session_id:
            # Ensure the session actually belongs to the user before filtering
            if RecordingSession.objects.filter(pk=session_id, campaign__user=user).exists():
                 queryset = queryset.filter(session_id=session_id)
            else:
                # Prevent filtering by session_id if it doesn't belong to user
                return Transcription.objects.none()

        return queryset.order_by('-created_at')

# Spotify API integration
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def spotify_token(request):
    """Exchange authorization code for access token"""
    code = request.data.get('code')
    
    if not code:
        return Response({'error': 'Authorization code is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Get Spotify credentials from environment variables
    client_id = os.environ.get('SPOTIFY_CLIENT_ID')
    client_secret = os.environ.get('SPOTIFY_CLIENT_SECRET')
    redirect_uri = os.environ.get('SPOTIFY_REDIRECT_URI')
    
    if not client_id or not client_secret:
        return Response({'error': 'Spotify API credentials not configured'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    # Exchange code for token
    token_url = 'https://accounts.spotify.com/api/token'
    payload = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri,
    }
    
    # Make request to Spotify API
    response = requests.post(
        token_url,
        data=payload,
        auth=(client_id, client_secret)
    )
    
    if response.status_code != 200:
        return Response({'error': 'Failed to exchange code for token', 'details': response.json()}, 
                        status=status.HTTP_400_BAD_REQUEST)
    
    # Return the access token and related data
    return Response(response.json())

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def spotify_refresh(request):
    """Refresh Spotify access token"""
    refresh_token = request.data.get('refresh_token')
    
    if not refresh_token:
        return Response({'error': 'Refresh token is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Get Spotify credentials from environment variables
    client_id = os.environ.get('SPOTIFY_CLIENT_ID')
    client_secret = os.environ.get('SPOTIFY_CLIENT_SECRET')
    
    if not client_id or not client_secret:
        return Response({'error': 'Spotify API credentials not configured'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    # Exchange refresh token for new access token
    token_url = 'https://accounts.spotify.com/api/token'
    payload = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
    }
    
    # Make request to Spotify API
    response = requests.post(
        token_url,
        data=payload,
        auth=(client_id, client_secret)
    )
    
    if response.status_code != 200:
        return Response({'error': 'Failed to refresh token', 'details': response.json()}, 
                        status=status.HTTP_400_BAD_REQUEST)
    
    # Return the new access token and related data
    return Response(response.json())
