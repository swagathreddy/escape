from django.shortcuts import render
from django.http import JsonResponse
from .logic import PuzzleLogic
import logging
import traceback
from io import BytesIO
from PIL import Image
import requests
from django.views.decorators.csrf import csrf_exempt  # Add this import

# Configure logging
logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s: %(message)s',
    filename='django_errors.log'
)

class EscapeRoomView(object):
    # Your EscapeRoomView class remains the same
    pass

@csrf_exempt  # Add this decorator
def index(request):
    request.session.flush()
    view = EscapeRoomView(request.session)
    initial_puzzle = view.get_initial_puzzle()
    view.save_session(request.session)
    return render(request, 'index.html', {'initial_puzzle': initial_puzzle})

@csrf_exempt  # Add this decorator
def chatbot_response(request):
    try:
        view = EscapeRoomView(request.session)
        
        if request.method != 'POST':
            return JsonResponse({"error": "Invalid request method"}, status=405)
        
        user_input = request.POST.get('user_input', '').strip()
        
        if not user_input:
            return JsonResponse({"error": "Empty user input"}, status=400)
        
        # Rest of your chatbot_response function remains the same
        if view.puzzle_logic.game_over and user_input.lower() == 'next':
            request.session.flush()
            return JsonResponse({"reload": True})
        
        response_data = {"response": ""}
        try:
            correct, response = view.puzzle_logic.play_game(user_input)
            if not correct and "Out of lives!" in response:
                response_data["reload"] = True
            if isinstance(response, dict):
                response_data["response"] = response.get("text", "")
                if response.get("image"):
                    response_data["image"] = response["image"]
            else:
                response_data["response"] = response
        
        except Exception as game_error:
            logging.error(f"Game logic error: {game_error}")
            return JsonResponse({"error": "Internal game error"}, status=500)
        
        view.save_session(request.session)
        return JsonResponse(response_data)
    
    except Exception as e:
        logging.error(f"Detailed Error: {e}")
        return JsonResponse({"error": "Unexpected error"}, status=500)

@csrf_exempt  # Add this decorator
def fetch_elements(request):
    elements = Element.objects.values_list('name', flat=True)
    return JsonResponse({"elements": list(elements)})
