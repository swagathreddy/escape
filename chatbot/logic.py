import spacy
from fuzzywuzzy import fuzz
import time
import unicodedata
from chatbot.models import Theme, Room, Element, Answer
import traceback
import logging
from django.db.models import Prefetch
import base64
import io
from io import BytesIO
from PIL import Image
import os
from PIL import Image    
import requests
import random
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv
from .models import UserGameSession
from datetime import timezone

logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s: %(message)s',
    filename='game_errors.log'
)

class PuzzleLogic:
    _nlp = None  # Class-level caching of NLP model
    

    def __init__(self):
        # Load NLP model only once per class
        load_dotenv()
        self.session_id = None
        self.user_solved_elements = {}
        self.element_images = {}

        if PuzzleLogic._nlp is None:
            PuzzleLogic._nlp = spacy.load("en_core_web_md")
        self.nlp = PuzzleLogic._nlp

        self.hf_api_token = os.getenv("HF_API_TOKEN")
        if not self.hf_api_token:
            logging.error("HF_API_TOKEN is not set in the environment.")
        # Optimize data loading with prefetching
        self.load_data_optimized()
        
        # Reset game state
        self.reset_game_state()
        self.score = 0
        self.hints_used = 0

        
    def set_session(self, session_id):
        """Set the current user session ID"""
        self.session_id = session_id
        # Load or create user session
        try:
            session, created = UserGameSession.objects.get_or_create(
                session_id=session_id,
                defaults={
                    'solved_elements': {},
                    'score': 0,
                    'lives': 3
                }
            )
            self.user_solved_elements = session.solved_elements
            self.score = session.score
            self.lives = session.lives
            self.current_theme = session.current_theme
        except Exception as e:
            logging.error(f"Error setting session: {e}")
            self.reset_game_state()

    def is_element_solved(self, theme, element):
        """Check if element is solved for current user"""
        theme_key = self.normalize_string(theme)
        element_key = self.normalize_string(element)
        return self.user_solved_elements.get(theme_key, {}).get(element_key, False)

    def mark_element_solved(self, theme, element):
        """Mark element as solved for current user"""
        theme_key = self.normalize_string(theme)
        element_key = self.normalize_string(element)
        
        if theme_key not in self.user_solved_elements:
            self.user_solved_elements[theme_key] = {}
        
        self.user_solved_elements[theme_key][element_key] = True
        
        # Update database
        try:
            UserGameSession.objects.filter(session_id=self.session_id).update(
                solved_elements=self.user_solved_elements,
                last_active=timezone.now()
            )
        except Exception as e:
            logging.error(f"Error updating session: {e}")

    def reset_game_state(self):
        self.current_room_index = 0
        self.current_theme = None
        self.current_element = None
        self.last_suggestion = None
        self.room_hint_requests = {}
        self.game_over = False
        self.hint_request_time = {}
        self.score = 0
        self.time_taken = 0
        self.start_time = time.time()
        self.game_started = False
        self.lives = 3
        self.score = 0
        self.hints_used = 0
        if self.session_id:
            UserGameSession.objects.filter(session_id=self.session_id).update(
                solved_elements={},
                score=0,
                lives=3,
                current_theme=None
            )
            self.user_solved_elements = {}

    def normalize_string(self, text):
        return unicodedata.normalize('NFKD', text.lower()).strip() if text else text

    def load_data_optimized(self):
        # Use select_related and prefetch_related to reduce database queries
        rooms = Room.objects.prefetch_related(
            Prefetch('elements', 
                queryset=Element.objects.prefetch_related('answers')
            )
        )

        self.themes = {
            self.normalize_string(room.theme.name): room.theme 
            for room in rooms
        }

        self.rooms = {
            self.normalize_string(room.theme.name): {
                "description": room.description,
                "elements": {
                    self.normalize_string(element.name): {
                        "puzzle": element.puzzle,
                        "hint": element.hint,
                        "answers": [answer.answer for answer in element.answers.all()],
                        "solved": element.solved
                    } for element in room.elements.all()
                },
                "room_name": room.name
            } for room in rooms
        }
        self.room_order = list(self.rooms.keys())

    def start_game(self):
        self.game_started = True
        self.start_time = time.time()
        self.reset_solved_elements_in_database()
        
        # Return two separate messages
        welcome_message = (
            "Welcome to the Escape Room Game! 🏰"
            "You will need to solve puzzles and riddles to progress through different rooms. "
            "Each room has its own challenge. Are you ready to begin your adventure? "
            "Type 'next' to see the available themes or 'exit' to quit."
        )
        
        scoring_rules = (
            "🎯 Scoring Rules:"
            "• For every correct answer: +10 points"
            "• For every hint used: -5 points"
            "Solve puzzles strategically and minimize hint usage!"
        )
        
        return [welcome_message, scoring_rules]

    def reset_solved_elements_in_database(self):
        # Bulk update is much faster than individual saves
        Element.objects.update(solved=False)

    def show_themes(self):
        themes_list = "\n\n".join([f"{i+1}. 🌟 **{theme}**" for i, theme in enumerate(self.themes.keys())])
        return (
            "Choose a theme to start your adventure:\n\n"
            f"{themes_list}\n\n"
            "Type the number of your choice to begin or 'exit' to quit.\n"
        )




    def select_theme(self, user_input):
        try:
            choice = int(user_input) - 1
            theme_name = list(self.themes.keys())[choice]
            self.current_theme = theme_name
            self.lives = 3  # Reset lives when selecting a new theme
            return self.describe_room() + f"\n\n🌟 Lives remaining: {self.lives}"
        except (ValueError, IndexError):
            return "Invalid selection. Please choose a valid theme number."

    def describe_room(self):
        normalized_theme = self.normalize_string(self.current_theme)
        current_room = self.rooms.get(normalized_theme)
    
        if current_room:
            elements = [f"🔍 **{element}**" for element in current_room['elements'].keys()]
            return (
                f"{current_room['description']}\n\n"
                "Interact with: \n"
                f"{', '.join(sorted(elements))}.\n"
                "Type the name of an element to interact with it or 'exit' to quit."
            )
        else:
            return f"Error: Room for theme '{normalized_theme}' not found."


    # def interact_with_element(self, user_input):
    #     normalized_input = self.normalize_string(user_input)
    #     current_room_key = self.normalize_string(self.current_theme)
    #     current_room = self.rooms.get(current_room_key, {})
        
    #     normalized_elements = {self.normalize_string(k): k for k in current_room.get('elements', {}).keys()}

    #     if normalized_input in normalized_elements:
    #         original_element = normalized_elements[normalized_input]
    #         element_data = current_room['elements'][original_element]
            
    #         if element_data['solved']:
    #             return f"The puzzle for the {original_element} is already solved. Please choose another element to interact with."
            
    #         self.current_element = original_element
    #         return f"Your puzzle for the {original_element} is: {element_data['puzzle']}"
    #     else:
    #         return "Invalid element. Please type the name of an available element or ask for a hint."

    def check_element_answer(self, user_input):
        try:
            if not self.session_id:
                return False, "Session not initialized"
            current_room_key = self.normalize_string(self.current_theme)
            current_room = self.rooms.get(current_room_key, {})
            
            # Validate current element exists
            if not self.current_element or self.current_element not in current_room.get('elements', {}):
                return False, "Invalid element. Please choose an available element."

            element_data = current_room['elements'][self.current_element]

            processed_user_input = self.preprocess_input(user_input)
            for correct in element_data.get('answers', []):
                processed_correct_answer = self.preprocess_input(correct)
                if self.is_similar_answer(processed_correct_answer, processed_user_input):
                    # Mark element as solved only if not already solved
                    self.mark_element_solved(current_room_key, self.current_element)
                    self.score += 10

                    UserGameSession.objects.filter(session_id=self.session_id).update(
                        solved_elements=self.user_solved_elements,
                        score=self.score
                    )

                    # Check remaining puzzles for this user's session
                    remaining = sum(
                        1 for elm in current_room['elements'].keys()
                        if not self.is_element_solved(current_room_key, elm)
                    )
                    
                    if remaining == 0:
                        return True, f"🎉 Congratulations! Room completed! Total score: {self.score} points. Type 'next' for a new theme."
                    
                    unsolved = [
                        element for element in current_room['elements'].keys()
                        if not self.is_element_solved(current_room_key, element)
                    ]
                    element_list = ", ".join(f"🔍 **{elem}**" for elem in unsolved)
                    
                    return True, f"🎉 Correct! {remaining} more to solve. Score: {self.score}.\n\nRemaining: {element_list}"
            
            self.lives -= 1
            # Update lives in session
            UserGameSession.objects.filter(session_id=self.session_id).update(lives=self.lives)
            
            if self.lives <= 0:
                self.reset_game_state()
                return False, "❌ Out of lives! Game restarted."
            
            return False, f"Incorrect answer. Lives remaining: {self.lives}. Type 'hint' for help."
            
        except Exception as e:
            logging.error(f"Error in check_element_answer: {e}")
            return False, "An error occurred. Please try again."
                

    def preprocess_input(self, text):
        """
        More robust preprocessing that handles variations of input
        """
        if not text:
            return ""
        
        # Normalize and lowercase
        normalized_text = self.normalize_string(text)
        
        # Use NLP for lemmatization and stop word handling
        doc = self.nlp(normalized_text)
        
        # Keep meaningful tokens, including some stop words that might be crucial
        processed_tokens = [
            token.lemma_ for token in doc 
            if not token.is_stop or token.lemma_ in ["is", "am", "are", "be", "was", "were", "a", "an", "the"]
        ]
        
        return " ".join(processed_tokens)

    def is_similar_answer(self, correct_answer, user_input):
        """
        More precise answer matching with whole word requirements
        """
        # Exact match first
        if correct_answer.lower() == user_input.lower():
            return True
        
        # Split inputs into words
        correct_words = set(correct_answer.lower().split())
        input_words = set(user_input.lower().split())
        
        # Check if the correct answer is a subset of input words
        if correct_words.issubset(input_words):
            return True
        
        # Fuzzy ratio checking with whole word consideration
        fuzz_score = fuzz.token_sort_ratio(correct_answer.lower(), user_input.lower())
        
        # More strict scoring
        return fuzz_score > 90  # Increased from previous threshold

    def restart_game(self):
        self.reset_game_state()
        self.reset_solved_elements_in_database()

    def play_game(self, user_input):
        if self.game_over:
            if user_input.lower() == 'next':
                self.restart_game()
                return True, "Choose a theme to continue your adventure."  # Single, clear message
            elif user_input.lower() == 'exit':
                return False, "Exiting the game. Thank you for playing!"
            else:
                return False, "Game over. Type 'next' to start a new game or 'exit' to quit."
                
        try:
            valid_input, error_message = self.handle_non_alphanumeric_input(user_input)
            if not valid_input:
                return False, error_message

            if not self.game_started:
                if user_input.lower() == 'start':
                    return True, self.start_game()
                elif user_input.lower() == 'exit':
                    self.game_over = True
                    return False, "Exiting the game. Thank you for playing!"
                else:
                    return False, "Invalid input. Type 'start' to begin or 'exit' to quit."
            elif self.current_theme is None:
                if user_input.lower() == 'next':
                    return True, self.show_themes()
                elif user_input.lower() == 'exit':
                    self.game_over = True
                    return False, "Exiting the game. Thank you for playing!"
                else:
                    return True, self.select_theme(user_input)
            elif self.current_element is None:
                if user_input.lower() == 'exit':
                    self.game_over = True
                    return False, "Exiting the game. Thank you for playing!"
                elif user_input.lower() == 'next' and self.game_over:
                    self.restart_game()
                    return True, "Page will reload to start a new game."
                
                return True, self.interact_with_element(user_input)
            
            else:
                if "hint" in user_input.lower():
                    return True, self.provide_hint()
                if user_input.lower() == 'exit':
                    self.game_over = True
                    return False, "Exiting the game. Thank you for playing!"

                correct, response = self.check_element_answer(user_input)
                if correct:
                    self.current_element = None
                    if "Congratulations! You've successfully cracked the room" in response:
                        self.game_over = True
                        return True, response
                    return True, response
                else:
                    return False, response
                
        
        except Exception as e:
            logging.error(f"Game error: {e}")
            logging.error(traceback.format_exc())
            return False, f"An unexpected error occurred: {str(e)}"

    def provide_hint(self):
        current_room_key = self.normalize_string(self.current_theme)
        current_room = self.rooms.get(current_room_key, {})
        
        if self.current_element and self.current_element in current_room.get('elements', {}):
            self.score -= 5
            self.hints_used += 1
            hint = current_room['elements'][self.current_element]['hint']
            return f"Hint for the {self.current_element}: {hint}"
        return "There is no active puzzle to provide a hint for."

    def handle_non_alphanumeric_input(self, user_input):
        if not any(char.isalnum() for char in user_input):
            return False, "Hmm, that doesn't seem like a valid answer. Please try again with a word or phrase!"
        return True, None

    def to_dict(self):
        return {
            "current_room_index": self.current_room_index,
            "current_theme": self.normalize_string(self.current_theme),
            "current_element": self.normalize_string(self.current_element),
            "last_suggestion": self.last_suggestion,
            "room_hint_requests": self.room_hint_requests,
            "game_over": self.game_over,
            "hint_request_time": self.hint_request_time,
            "score": self.score,
            "time_taken": self.time_taken,
            "start_time": self.start_time,
            "game_started": self.game_started,
            "lives": self.lives
        }

    def from_dict(self, data):
        self.current_room_index = data.get("current_room_index", 0)
        self.current_theme = self.normalize_string(data.get("current_theme", None))
        self.current_element = self.normalize_string(data.get("current_element", None))
        self.last_suggestion = data.get("last_suggestion", None)
        self.room_hint_requests = data.get("room_hint_requests", {})
        self.game_over = data.get("game_over", False)
        self.hint_request_time = data.get("hint_request_time", {})
        self.score = data.get("score", 0)
        self.time_taken = data.get("time_taken", 0)
        self.start_time = data.get("start_time", time.time())
        self.game_started = data.get("game_started", False)
        self.lives = data.get("lives", 3)
    
    import requests
    import base64
    import logging
    import io
    from PIL import Image



    def generate_element_image(self, element_name, puzzle_text):
        API_URL = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0"
        headers = {
            "Authorization": f"Bearer {self.hf_api_token}",
            "Content-Type": "application/json"
        }

        # Create a prompt that combines the element name and puzzle
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                prompt = f"Mysterious {element_name} related to the puzzle: {puzzle_text}. Dark, cyberpunk detective style, with dramatic lighting and intrigue"
                
                response = requests.post(
                    API_URL, 
                    headers=headers, 
                    json={
                        "inputs": prompt,
                        "parameters": {
                            "negative_prompt": "blurry, low quality, bad composition",
                            "num_inference_steps": 30,
                            "guidance_scale": 7.5
                        }
                    },
                    timeout=30  # Add timeout
                )

                if response.status_code == 200:
                    image = Image.open(io.BytesIO(response.content))
                    image.thumbnail((400, 400))
                    buffered = io.BytesIO()
                    image.save(buffered, format="PNG")
                    return base64.b64encode(buffered.getvalue()).decode('utf-8')
                
                elif response.status_code == 503:  # Model loading
                    time.sleep(2)  # Wait before retry
                    retry_count += 1
                    continue
                    
                else:
                    logging.error(f"Image generation error: {response.text}")
                    retry_count += 1
                    
            except Exception as e:
                logging.error(f"Image generation exception: {e}")
                retry_count += 1
                time.sleep(1)
                
        return None  # Return None if all r

    def interact_with_element(self, user_input):
        normalized_input = self.normalize_string(user_input)
        current_room_key = self.normalize_string(self.current_theme)
        current_room = self.rooms.get(current_room_key, {})
        
        normalized_elements = {self.normalize_string(k): k for k in current_room.get('elements', {}).keys()}
        
        # Extract potential element names from input
        input_words = set(normalized_input.split())
        element_words = set(normalized_elements.keys())
        
        # Find intersecting words
        matched_elements = input_words.intersection(element_words)
        
        # If no direct match, try fuzzy matching
        if not matched_elements:
            best_match = None
            best_score = 0
            for element in normalized_elements:
                score = fuzz.partial_ratio(normalized_input, element)
                if score > best_score and score > 70:
                    best_match = element
                    best_score = score
            
            if best_match:
                matched_elements = {best_match}
        
        # Process the matched element
        if matched_elements:
            original_element = normalized_elements[list(matched_elements)[0]]
            element_data = current_room['elements'][original_element]
            
            if element_data['solved']:
                return f"The puzzle for the {original_element} is already solved. Please choose another element to interact with."
            
            self.current_element = original_element
            puzzle_text = element_data['puzzle']
            
            # Generate image for the element
            element_key = f"{current_room_key}_{original_element}"
            
            if element_key not in self.element_images:
                # Generate and cache the image
                generated_image = self.generate_element_image(original_element, puzzle_text)
                if generated_image:
                    self.element_images[element_key] = generated_image
            
            # Use cached image if available
            image = self.element_images.get(element_key)
            
            # Only return the puzzle text once we have the image
            if image:
                return {
                    "text": f"Your puzzle for the {original_element} is: {puzzle_text}",
                    "image": image
                }
            else:
                # If image generation failed, retry once
                retry_image = self.generate_element_image(original_element, puzzle_text)
                if retry_image:
                    self.element_images[element_key] = retry_image
                    return {
                        "text": f"Your puzzle for the {original_element} is: {puzzle_text}",
                        "image": retry_image
                    }
                else:
                    # If still no image, show a loading message
                    return {
                        "text": "Preparing your puzzle... Please try again in a moment.",
                        "loading": True
                    }
        
        return "Invalid element. Please type the name of an available element or ask for a hint."
