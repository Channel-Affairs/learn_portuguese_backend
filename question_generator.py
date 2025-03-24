import json
import uuid
import random
from typing import List, Optional
import openai
from pydantic import BaseModel
from models import QuestionTypes, DifficultyLevel, MultipleChoiceQuestion, FillInTheBlankQuestion, BaseQuestion

class QuestionGenerator:
    """
    Class to generate Portuguese language learning questions using OpenAI
    """
    
    def __init__(self, openai_api_key: str):
        """Initialize the question generator with OpenAI API key"""
        self.openai_api_key = openai_api_key
        self.question_templates = self._load_question_templates()
    
    def _load_question_templates(self):
        """Load question templates for different difficulty levels"""
        # These are example templates - in a real app, you might load from a database or file
        return {
            "multiple_choice": {
                "easy": [
                    {
                        "questionText": "What is the Portuguese word for '{english_word}'?",
                        "options_prompt": "Generate 4 Portuguese words including the correct translation for '{english_word}'."
                    },
                    {
                        "questionText": "Which sentence uses the correct form of the verb '{verb}'?",
                        "options_prompt": "Generate 4 Portuguese sentences using different forms of the verb '{verb}', with only one being correct."
                    }
                ],
                "medium": [
                    {
                        "questionText": "Which of these is the correct translation of '{english_phrase}'?",
                        "options_prompt": "Generate 4 Portuguese translations of '{english_phrase}', with only one being correct."
                    }
                ],
                "hard": [
                    {
                        "questionText": "Which sentence correctly uses the {grammar_concept}?",
                        "options_prompt": "Generate 4 Portuguese sentences demonstrating {grammar_concept}, with only one being correct."
                    }
                ]
            },
            "fill_in_the_blank": {
                "easy": [
                    {
                        "questionText": "Complete the sentence with the correct word:",
                        "sentence_template": "{partial_sentence} ____ {rest_of_sentence}."
                    }
                ],
                "medium": [
                    {
                        "questionText": "Fill in the blank with the correct verb form:",
                        "sentence_template": "{subject} ____ {object}."
                    }
                ],
                "hard": [
                    {
                        "questionText": "Complete the sentence with the correct preposition and article:",
                        "sentence_template": "{subject} {verb} ____ {object}."
                    }
                ]
            }
        }
    
    def _get_openai_completion(self, prompt: str) -> str:
        """Get completion from OpenAI without using async"""
        try:
            # For simplicity, we'll use direct API calls
            import requests
            import json
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.openai_api_key}"
            }
            
            data = {
                "model": "gpt-3.5-turbo",
                "messages": [
                    {"role": "system", "content": "You are a Portuguese language expert."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7
            }
            
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=data
            )
            
            result = response.json()
            
            if "choices" in result and len(result["choices"]) > 0:
                return result["choices"][0]["message"]["content"]
            else:
                print(f"Unexpected OpenAI response: {result}")
                return "Error generating content"
                
        except Exception as e:
            print(f"Error in OpenAI completion: {str(e)}")
            return "Error: " + str(e)
    
    def generate_multiple_choice_question(
        self, 
        difficulty: DifficultyLevel, 
        topic: str = "basic vocabulary"
    ) -> MultipleChoiceQuestion:
        """Generate a multiple choice question about Portuguese"""
        # Select a random template for the difficulty level
        templates = self.question_templates["multiple_choice"][difficulty]
        template = random.choice(templates)
        
        # Generate the question
        if topic == "basic vocabulary":
            # For vocabulary questions, we'll ask about common words
            english_words = ["dog", "cat", "house", "car", "book", "water", "food", "hello", "goodbye", "thank you"]
            english_word = random.choice(english_words)
            
            # Use OpenAI to generate the question
            prompt = f"""Create a Portuguese vocabulary question with the following:
            1. Question should be about the Portuguese word for '{english_word}'
            2. Provide 4 options as a Python list, with the correct answer first
            3. Provide a hint for the correct answer
            
            Format your response as a valid JSON object with these keys:
            - questionText: The full text of the question
            - questionDescription: Brief description of what to do
            - options: A list of 4 options (first one should be correct)
            - correct_answers: A list with just the correct answer as string
            - hint: A subtle hint to help the user
            
            Example format:
            {{
                "questionText": "What is the Portuguese word for 'dog'?",
                "questionDescription": "Choose the correct translation.",
                "options": ["Cachorro", "Gato", "Pássaro", "Peixe"],
                "correct_answers": ["Cachorro"],
                "hint": "It starts with 'C'."
            }}
            """
            
            response_text = self._get_openai_completion(prompt)
            
            try:
                response_json = json.loads(response_text)
                
                # Create a multiple choice question
                question = MultipleChoiceQuestion(
                    id=str(uuid.uuid4()),
                    type=QuestionTypes.MULTIPLE_CHOICE,
                    questionText=response_json["questionText"],
                    questionDescription=response_json["questionDescription"],
                    options=response_json["options"],
                    correct_answers=response_json["correct_answers"],
                    difficulty=difficulty,
                    hint=response_json["hint"]
                )
                
                return question
            except Exception as e:
                print(f"Error parsing JSON from OpenAI: {str(e)}")
                print(f"Response was: {response_text}")
                
                # Fallback to a default question
                return MultipleChoiceQuestion(
                    id=str(uuid.uuid4()),
                    type=QuestionTypes.MULTIPLE_CHOICE,
                    questionText=f"What is '{english_word}' in Portuguese?",
                    questionDescription="Choose the correct translation.",
                    options=["Cachorro", "Gato", "Pássaro", "Peixe"],
                    correct_answers=["Cachorro"],
                    difficulty=difficulty,
                    hint=f"This is a common {topic} word."
                )
        
        # For other topics, we generate appropriate questions
        # ... rest of the existing code ...
    
    def generate_fill_in_blank_question(
        self, 
        difficulty: DifficultyLevel,
        topic: str = "verb conjugation"
    ) -> FillInTheBlankQuestion:
        """Generate a fill-in-the-blank question about Portuguese"""
        # Use OpenAI to generate a question
        prompt = f"""Create a Portuguese fill-in-the-blank question with the following:
        1. Question should be at {difficulty} difficulty level
        2. The topic should be about {topic}
        3. Provide a sentence with a blank for the user to fill in
        4. Provide the correct answer
        
        Format your response as a valid JSON object with these keys:
        - questionText: The full text of the question
        - questionDescription: Brief description of what to do 
        - questionSentence: The sentence with ____ as the blank
        - correct_answers: A list with just the correct answer as string
        - hint: A subtle hint to help the user
        
        Example format:
        {{
            "questionText": "Complete the sentence with the correct verb form:",
            "questionDescription": "Fill in the blank with the correct conjugation of 'falar'.",
            "questionSentence": "Eu ____ português todos os dias.",
            "correct_answers": ["falo"],
            "hint": "The verb is conjugated in the first person singular present tense."
        }}
        """
        
        response_text = self._get_openai_completion(prompt)
        
        try:
            response_json = json.loads(response_text)
            
            # Create a fill-in-the-blank question
            question = FillInTheBlankQuestion(
                id=str(uuid.uuid4()),
                type=QuestionTypes.FILL_IN_THE_BLANKS,
                questionText=response_json["questionText"],
                questionDescription=response_json["questionDescription"],
                questionSentence=response_json["questionSentence"],
                correct_answers=response_json["correct_answers"],
                difficulty=difficulty,
                hint=response_json["hint"],
                blankSeparator="____",
                numberOfBlanks=1
            )
            
            return question
        except Exception as e:
            print(f"Error parsing JSON from OpenAI: {str(e)}")
            print(f"Response was: {response_text}")
            
            # Fallback to a default question
            return FillInTheBlankQuestion(
                id=str(uuid.uuid4()),
                type=QuestionTypes.FILL_IN_THE_BLANKS,
                questionText="Complete the sentence with the correct verb form:",
                questionDescription="Fill in the blank with the correct conjugation of 'falar'.",
                questionSentence="Eu ____ português todos os dias.",
                correct_answers=["falo"],
                difficulty=difficulty,
                hint="The verb is conjugated in the first person singular present tense.",
                blankSeparator="____",
                numberOfBlanks=1
            )
    
    def generate_questions(
        self, 
        num_questions: int = 2,
        difficulty: Optional[DifficultyLevel] = None,
        question_types: Optional[List[QuestionTypes]] = None,
        topic: str = "Portuguese language"
    ) -> List[BaseQuestion]:
        """Generate a list of Portuguese language questions"""
        # Set default difficulty if not provided
        if not difficulty:
            difficulty = DifficultyLevel.MEDIUM
            
        # Set default question types if not provided
        if not question_types:
            question_types = [QuestionTypes.MULTIPLE_CHOICE, QuestionTypes.FILL_IN_THE_BLANKS]
            
        # Convert string types to enum values if needed
        if isinstance(difficulty, str):
            difficulty = DifficultyLevel(difficulty)
            
        if isinstance(question_types, list) and all(isinstance(qt, str) for qt in question_types):
            question_types = [QuestionTypes(qt) for qt in question_types]
            
        # Generate questions
        questions = []
        for i in range(num_questions):
            # Randomly select question type from the provided types
            question_type = random.choice(question_types)
            
            if question_type == QuestionTypes.MULTIPLE_CHOICE:
                questions.append(self.generate_multiple_choice_question(difficulty, topic))
            elif question_type == QuestionTypes.FILL_IN_THE_BLANKS:
                questions.append(self.generate_fill_in_blank_question(difficulty, topic))
                
        return questions 