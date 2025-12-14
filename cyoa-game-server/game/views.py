"""
Views for CYOA game server.
Implements dual-LLM approach: storyteller -> judge -> response
"""
import json
import time
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from .file_utils import load_prompt_file
from .anthropic_utils import call_anthropic
from .ollama_utils import call_ollama


def call_llm(messages, system_prompt=None, model="claude-haiku-4-5"):
    """
    Universal LLM caller - routes to appropriate backend based on model name.
    
    Args:
        messages: List of message dicts
        system_prompt: Optional system prompt
        model: Model identifier (claude-*, gameserver-ollama/*, ollama/*, etc.)
    
    Returns:
        String response from the LLM
    """
    # Strip gameserver- prefix if present for routing logic
    routing_model = model
    if routing_model.startswith("gameserver-"):
        routing_model = routing_model[11:]
    
    if routing_model.startswith("ollama/") or routing_model in ["qwen3:30b", "mistral:22b"]:
        return call_ollama(messages, system_prompt, model)
    else:
        return call_anthropic(messages, system_prompt, model)


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
        if "cyoa-test" in model_name:
            print("\n[TEST MODE] Returning hardcoded response (no API calls)")
            test_response = load_prompt_file('test_prompt.txt')
            
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
        
        # Determine which backend model to use
        # Default to claude-haiku-4-5, but allow override
        backend_model = body.get("backend_model", "claude-haiku-4-5")
        
        print(f"\n{'='*60}")
        print(f"CYOA Game Server - Processing Request")
        print(f"{'='*60}")
        print(f"Backend model: {backend_model}")
        print(f"Messages in conversation: {len(filtered_messages)}")
        if system_message:
            print(f"System prompt: {system_message[:100]}...")
        
        # Step 1: Call storyteller LLM
        print(f"\n[STEP 1] Calling storyteller ({backend_model})...")
        story_turn = call_llm(
            messages=filtered_messages,
            system_prompt=system_message,
            model=backend_model
        )
        print(f"Storyteller response length: {len(story_turn)} chars")
        print(f"Preview: {story_turn[:200]}...")
        
        # Step 2: Call judge LLM to validate/improve the story turn
        print(f"\n[STEP 2] Calling judge ({backend_model})...")
        judge_messages = [
            {
                "role": "user",
                "content": f"Review this story turn:\n\n{story_turn}"
            }
        ]
        
        final_turn = call_llm(
            messages=judge_messages,
            system_prompt=load_prompt_file('judge_prompt.txt'),
            model=backend_model
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
        import traceback
        traceback.print_exc()
        return JsonResponse(
            {"error": str(e)},
            status=500
        )
