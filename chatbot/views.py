from django.shortcuts import render
from django.http import JsonResponse
from .logic import PuzzleLogic
import logging
import traceback
from io import BytesIO
from PIL import Image
import requests
from django.views.decorators.csrf import csrf_exempt
from .models import Element
import uuid
# Configure logging
logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s: %(message)s',
    filename='django_errors.log'
)

class EscapeRoomView:  # Changed from object to regular class
    def __init__(self, session=None):  # Added default None parameter
        self.puzzle_logic = PuzzleLogic()
        if session:
            if 'game_session_id' not in session:
                session['game_session_id'] = str(uuid.uuid4())
            self.puzzle_logic.set_session(session['game_session_id'])
            state = session.get('puzzle_logic_state', None)
            if state:
                self.puzzle_logic.from_dict(state)

    def save_session(self, session):
        session['puzzle_logic_state'] = self.puzzle_logic.to_dict()
        session.modified = True

    def get_initial_puzzle(self):
        if not self.puzzle_logic.game_started:
            return self.puzzle_logic.start_game()
        else:
            return self.puzzle_logic.get_puzzle()

@csrf_exempt
def index(request):
    if 'game_session_id' not in request.session:
        request.session['game_session_id'] = str(uuid.uuid4())
    request.session.flush()
    view = EscapeRoomView(request.session)  # Now this will work
    initial_puzzle = view.get_initial_puzzle()
    view.save_session(request.session)
    return render(request, 'index.html', {'initial_puzzle': initial_puzzle})

@csrf_exempt
def chatbot_response(request):
    try:
        view = EscapeRoomView(request.session)
        
        if request.method != 'POST':
            return JsonResponse({"error": "Invalid request method"}, status=405)
        
        user_input = request.POST.get('user_input', '').strip()
        
        if not user_input:
            return JsonResponse({"error": "Empty user input"}, status=400)
        
        response_data = {"response": ""}
        
        try:
            correct, response = view.puzzle_logic.play_game(user_input)
            
            if not correct and "Out of lives!" in response:
                response_data["reload"] = True
                
            if isinstance(response, dict):
                response_data["response"] = response.get("text", "")
                response_data["error"] = response.get("error", False)
                response_data["retry"] = response.get("retry", False)
                
                if response.get("image"):
                    response_data["image"] = response["image"]
                    response_data["success"] = response.get("success", False)
            else:
                response_data["response"] = response
        
        except Exception as game_error:
            logging.error(f"Game logic error: {game_error}")
            return JsonResponse({
                "error": True, 
                "response": "An error occurred. Please try interacting with the element again."
            }, status=500)
        
        view.save_session(request.session)
        return JsonResponse(response_data)
    
    except Exception as e:
        logging.error(f"Detailed Error: {e}")
        return JsonResponse({
            "error": True,
            "response": "An unexpected error occurred. Please try again."
        }, status=500)


@csrf_exempt  # Add this decorator
def fetch_elements(request):
    elements = Element.objects.values_list('name', flat=True)
    return JsonResponse({"elements": list(elements)})
