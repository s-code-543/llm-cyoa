"""
Views for CYOA game server.
Implements dual-LLM approach: storyteller -> judge -> response
"""
import json
import requests
import time
import os
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings


def load_judge_prompt():
    """Load judge system prompt from file."""
    prompt_path = os.path.join(os.path.dirname(__file__), 'judge_prompt.txt')
    with open(prompt_path, 'r') as f:
        return f.read().strip()


def call_anthropic(messages, system_prompt=None, model="claude-haiku-4-5"):
    """
    Call Anthropic API with the given messages.
    Returns the text response.
    """
    # Process messages into Anthropic format
    processed_messages = []
    for message in messages:
        if isinstance(message.get("content"), list):
            # Handle multipart content (text + images potentially)
            processed_content = []
            for item in message["content"]:
                if item["type"] == "text":
                    processed_content.append({"type": "text", "text": item["text"]})
            processed_messages.append({
                "role": message["role"],
                "content": processed_content
            })
        else:
            # Simple text content
            processed_messages.append({
                "role": message["role"],
                "content": [{"type": "text", "text": message.get("content", "")}]
            })

    payload = {
        "model": model,
        "messages": processed_messages,
        "max_tokens": 4096,
        "temperature": 0.8,
    }

    if system_prompt:
        payload["system"] = system_prompt

    headers = {
        "x-api-key": settings.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    url = "https://api.anthropic.com/v1/messages"

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=(3.05, 60))
        
        if response.status_code != 200:
            raise Exception(f"HTTP Error {response.status_code}: {response.text}")

        res = response.json()
        return res["content"][0]["text"] if "content" in res and res["content"] else ""
    
    except requests.exceptions.RequestException as e:
        print(f"Anthropic API request failed: {e}")
        raise


@csrf_exempt
@require_http_methods(["POST"])
def chat_completions(request):
    """
    OpenAI-compatible chat completions endpoint.
    Implements dual-LLM logic: storyteller -> judge -> response
    
    TEST MODE: Use model name 'cyoa-test' to get hardcoded response without API calls
    """
    try:
        body = json.loads(request.body)
        
        # Check for test mode
        model_name = body.get("model", "")
        if model_name == "cyoa-test" or model_name.endswith("/cyoa-test"):
            print("\n[TEST MODE] Returning hardcoded response (no API calls)")
            test_response = """Ahoy there, matey! This be a TEST response from yer CYOA Game Server.

Ye've successfully connected Open WebUI to yer custom Django server! The integration be workin' perfectly.

Since this be test mode, no API calls were made to Claude. When ye're ready for the real dual-LLM magic, just use a different model name (or 'cyoa-dual-claude').

Now, what be yer next move, captain?
1. Set sail for adventure (switch to production mode)
2. Check the server logs to see this message was generated locally
3. Continue testin' the connection

Choose wisely!"""
            
            return JsonResponse({
                "id": f"test-{int(time.time())}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model_name,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": test_response,
                        },
                        "finish_reason": "stop"
                    }
                ],
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0
                }
            })
        
        # Production mode - proceed with dual-LLM logic
        # Extract system message if present
        messages = body.get("messages", [])
        system_message = None
        filtered_messages = []
        
        for msg in messages:
            if msg.get("role") == "system":
                system_message = msg.get("content", "")
            else:
                filtered_messages.append(msg)
        
        print(f"\n{'='*60}")
        print(f"CYOA Game Server - Processing Request")
        print(f"{'='*60}")
        print(f"Messages in conversation: {len(filtered_messages)}")
        if system_message:
            print(f"System prompt: {system_message[:100]}...")
        
        # Step 1: Call storyteller Claude
        print(f"\n[STEP 1] Calling storyteller Claude...")
        story_turn = call_anthropic(
            messages=filtered_messages,
            system_prompt=system_message,
            model="claude-haiku-4-5"
        )
        print(f"Storyteller response length: {len(story_turn)} chars")
        print(f"Preview: {story_turn[:200]}...")
        
        # Step 2: Call judge Claude to validate/improve the story turn
        print(f"\n[STEP 2] Calling judge Claude...")
        judge_messages = [
            {
                "role": "user",
                "content": f"Review this story turn:\n\n{story_turn}"
            }
        ]
        
        final_turn = call_anthropic(
            messages=judge_messages,
            system_prompt=load_judge_prompt(),
            model="claude-haiku-4-5"
        )
        print(f"Judge response length: {len(final_turn)} chars")
        print(f"Preview: {final_turn[:200]}...")
        
        # Step 3: Return OpenAI-compatible response
        print(f"\n[STEP 3] Returning final response to Open WebUI")
        print(f"{'='*60}\n")
        
        response_data = {
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": body.get("model", "cyoa-dual-claude"),
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": final_turn,
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        }
        
        return JsonResponse(response_data)
    
    except Exception as e:
        print(f"ERROR in chat_completions: {e}")
        return JsonResponse(
            {"error": str(e)},
            status=500
        )


@require_http_methods(["GET"])
def list_models(request):
    """
    OpenAI-compatible models endpoint.
    """
    return JsonResponse({
        "object": "list",
        "data": [
            {
                "id": "cyoa-dual-claude",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "cyoa-game-server",
                "description": "Dual-LLM: Storyteller + Judge (uses Claude API)"
            },
            {
                "id": "cyoa-test",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "cyoa-game-server",
                "description": "Test mode - hardcoded response (no API calls)"
            }
        ]
    })


@csrf_exempt
@require_http_methods(["POST", "GET"])
def test_endpoint(request):
    """
    Test endpoint that returns hardcoded response.
    Use this to verify Open WebUI connectivity without burning API calls.
    """
    if request.method == "GET":
        return JsonResponse({
            "status": "ok",
            "message": "CYOA Game Server is running!",
            "endpoints": {
                "test": "/v1/test",
                "models": "/v1/models",
                "chat": "/v1/chat/completions"
            }
        })
    
    # POST request - return as if it's a chat completion
    try:
        body = json.loads(request.body) if request.body else {}
        
        test_response = """Ahoy there, matey! This be a test response from yer CYOA Game Server.

If ye be seein' this message, it means the connection between Open WebUI and yer custom Django server be workin' just fine!

Now ye have three choices:
1. Test the real dual-LLM endpoint
2. Check the server logs
3. Continue testin' this endpoint

What'll it be, captain?"""
        
        return JsonResponse({
            "id": f"test-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": body.get("model", "cyoa-test"),
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": test_response,
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        })
    
    except Exception as e:
        return JsonResponse(
            {"error": str(e)},
            status=500
        )
