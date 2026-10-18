"""
Chat views for the CYOA frontend.
"""
import uuid
import json
import traceback
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, Http404
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required

from .models import ChatConversation, ChatMessage, GameSession, Configuration, AuditLog, ChatSubmission
from .llm_router import call_llm
from .config_utils import conversation_tts_enabled
from .response_format import extract_game_state, is_story_ending, public_metadata, public_content
from .engine.turn_execution import execute_turn
from .engine.nodes import TurnUnavailable
from .refusal_detector import process_potential_refusal
from .judge_pipeline import run_judge_pipeline



@login_required
@require_http_methods(["POST"])
def chat_api_new_conversation(request):
    """
    Create a new conversation and return its UUID.
    Accepts optional config_id in body to use specific configuration.
    """
    try:
        body = json.loads(request.body) if request.body else {}
        config_id = body.get('config_id')
        
        conversation_id = str(uuid.uuid4())
        
        # Get config name for title
        title = "New Adventure"
        if config_id:
            try:
                config = Configuration.objects.get(id=config_id)
                title = config.name
            except Configuration.DoesNotExist:
                pass
        
        conversation = ChatConversation.objects.create(
            user=request.user,
            conversation_id=conversation_id,
            title=title,
            metadata={'config_id': config_id} if config_id else {}
        )
        
        return JsonResponse({
            'conversation_id': conversation.conversation_id,
            'capabilities': {'tts': conversation_tts_enabled(conversation)},
            'title': conversation.title,
            'created_at': conversation.created_at.isoformat()
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def chat_api_send_message(request, *, payload=None, submission_id=None):
    """
    Send a message to the LLM and get a response.
    """
    try:
        body = payload if payload is not None else json.loads(request.body)
        conversation_id = body.get('conversation_id')
        if not submission_id and ChatSubmission.objects.filter(
            conversation__conversation_id=conversation_id, status='pending'
        ).exists():
            return JsonResponse({'error': 'Another action is running; reload before trying again'}, status=409)
        user_message = body.get('message', '').strip()
        
        if not conversation_id or not user_message:
            return JsonResponse({'error': 'conversation_id and message required'}, status=400)
        
        # Get or create conversation (always owned by current user)
        conversation, created = ChatConversation.objects.get_or_create(
            conversation_id=conversation_id,
            user=request.user,
            defaults={'title': 'New Adventure'}
        )
        
        result = execute_turn(
            conversation, user_message, call_llm=call_llm,
            correct_refusal=process_potential_refusal, judge_turn=run_judge_pipeline,
        )
        from .scene_images import illustrate_message
        message = conversation.messages.get(pk=result['message']['id'])
        illustrate_message(message)
        return JsonResponse(result)
    except TurnUnavailable as e:
        return JsonResponse({'error': str(e)}, status=409)
    except Exception as e:
        print(f"[CHAT ERROR] {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def chat_api_get_conversation(request, conversation_id):
    """
    Get conversation history.
    """
    try:
        conversation = get_object_or_404(
            ChatConversation,
            conversation_id=conversation_id,
            user=request.user
        )
        
        messages_data = []
        for msg in conversation.messages.all():
            messages_data.append({
                'id': msg.id,
                'role': msg.role,
                'content': public_content(msg.content, msg.metadata) if msg.role == 'assistant' else msg.content,
                'created_at': msg.created_at.isoformat(),
                'metadata': public_metadata(msg.metadata)
            })
        
        return JsonResponse({
            'conversation_id': conversation.conversation_id,
            'capabilities': {'tts': conversation_tts_enabled(conversation)},
            'title': conversation.title,
            'metadata': conversation.metadata,
            'messages': messages_data,
            'created_at': conversation.created_at.isoformat(),
            'updated_at': conversation.updated_at.isoformat()
        })
    except Http404:
        return JsonResponse({'error': 'Conversation not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def chat_api_list_conversations(request):
    """
    List conversations for the current user.
    """
    try:
        conversations = ChatConversation.objects.filter(user=request.user)[:50]
        
        conversations_data = []
        for conv in conversations:
            message_count = conv.messages.count()
            last_message = conv.messages.last()
            
            conversations_data.append({
                'conversation_id': conv.conversation_id,
                'title': conv.title,
                'message_count': message_count,
                'last_message': last_message.content[:100] if last_message else None,
                'created_at': conv.created_at.isoformat(),
                'updated_at': conv.updated_at.isoformat()
            })
        
        return JsonResponse({'conversations': conversations_data})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def chat_api_rollback_to_message(request, *, payload=None, submission_id=None):
    """
    Roll back a conversation to a specific assistant message.
    Deletes all messages after the target and resets game session state.
    """
    try:
        body = payload if payload is not None else json.loads(request.body)
        conversation_id = body.get('conversation_id')
        if not submission_id and ChatSubmission.objects.filter(
            conversation__conversation_id=conversation_id, status='pending'
        ).exists():
            return JsonResponse({'error': 'Another action is running; reload before trying again'}, status=409)
        message_id = body.get('message_id')
        
        if not conversation_id or not message_id:
            return JsonResponse({'error': 'conversation_id and message_id required'}, status=400)
        
        # Get conversation owned by user
        conversation = get_object_or_404(
            ChatConversation,
            conversation_id=conversation_id,
            user=request.user
        )
        
        # Get target message (must be assistant message in this conversation)
        try:
            target_message = ChatMessage.objects.get(
                id=message_id,
                conversation=conversation,
                role='assistant'
            )
        except ChatMessage.DoesNotExist:
            return JsonResponse({'error': 'Target message not found or not an assistant message'}, status=404)
        
        # Count messages to delete before actually deleting
        # (delete() returns total including cascaded objects, not just ChatMessage count)
        messages_qs = ChatMessage.objects.filter(
            conversation=conversation,
            id__gt=target_message.id
        )
        messages_to_delete = messages_qs.count()
        messages_qs.delete()
        
        print(f"[ROLLBACK] Deleted {messages_to_delete} messages after message {message_id}")
        
        # Reset game session
        try:
            game_session = GameSession.objects.get(
                session_id=conversation.conversation_id,
                user=request.user
            )
            
            # Count completed story turns, excluding refusal error messages.
            new_turn_number = sum(
                not msg.metadata.get('is_error')
                for msg in conversation.messages.filter(role='assistant')
            )

            game_session.turn_number = new_turn_number
            game_session.game_over = bool(target_message.metadata.get('game_over')
                                          or is_story_ending(target_message.content)
                                          or new_turn_number >= game_session.max_turns)
            snapshot = target_message.metadata.get('engine_snapshot', {})
            game_session.hidden_state = snapshot.get('state', {})
            game_session.workflow_snapshot = snapshot.get('workflow', {})
            game_session.random_seed = snapshot.get('seed', '')
            game_session.last_death_roll = snapshot.get('last_death_roll')
            game_session.last_death_probability = snapshot.get('last_death_probability')
            game_session.save()
            
            print(f"[ROLLBACK] Reset game session: turn={new_turn_number}, game_over=False")
            
        except GameSession.DoesNotExist:
            print(f"[ROLLBACK] No game session found for {conversation_id}")
        
        # Return updated conversation
        messages_data = []
        for msg in conversation.messages.all():
            messages_data.append({
                'id': msg.id,
                'role': msg.role,
                'content': public_content(msg.content, msg.metadata) if msg.role == 'assistant' else msg.content,
                'created_at': msg.created_at.isoformat(),
                'metadata': public_metadata(msg.metadata)
            })
        
        # Extract game state from last assistant message
        game_state = {'turn_current': 0, 'turn_max': 20, 'choice1': '', 'choice2': '', 'inventory': []}
        for msg_data in reversed(messages_data):
            if msg_data['role'] == 'assistant':
                game_state = extract_game_state(msg_data['content'])
                break
        
        return JsonResponse({
            'success': True,
            'deleted_count': messages_to_delete,
            'messages': messages_data,
            'state': game_state
        })
        
    except Http404:
        return JsonResponse({'error': 'Conversation not found'}, status=404)
    except json.JSONDecodeError as e:
        # Log malformed request to audit
        AuditLog.objects.create(
            original_text=request.body.decode('utf-8', errors='replace')[:1000],
            refined_text=f"JSON decode error: {str(e)}",
            was_modified=False,
            details={
                'type': 'error',
                'operation': 'rollback',
                'error_type': 'json_decode',
                'user': request.user.username if request.user.is_authenticated else 'anonymous'
            }
        )
        return JsonResponse({'error': 'Invalid request data'}, status=400)
    except Exception as e:
        # Log error to audit for visibility in admin GUI
        request_context = {
            'conversation_id': locals().get('conversation_id', 'unknown'),
            'message_id': locals().get('message_id', 'unknown'),
            'user': request.user.username if request.user.is_authenticated else 'anonymous'
        }
        AuditLog.objects.create(
            original_text=json.dumps(request_context, indent=2),
            refined_text=f"{type(e).__name__}: {str(e)}",
            was_modified=False,
            details={
                'type': 'error',
                'operation': 'rollback',
                'error_type': type(e).__name__,
                'traceback': traceback.format_exc(),
                **request_context
            }
        )
        return JsonResponse({'error': 'Rollback failed'}, status=500)


@login_required
@require_http_methods(["POST"])
def chat_api_delete_conversation(request, conversation_id):
    """
    Delete a conversation by marking its game session as over.
    """
    try:
        # Mark game session as over (scoped to current user)
        game_session = GameSession.objects.get(
            session_id=conversation_id,
            user=request.user
        )
        game_session.game_over = True
        game_session.save()
        
        return JsonResponse({'success': True})
    except GameSession.DoesNotExist:
        return JsonResponse({'error': 'Game not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
