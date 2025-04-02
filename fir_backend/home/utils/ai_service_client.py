import requests
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

class AIServiceClient:
    def __init__(self):
        self.base_url = getattr(settings, 'AI_SERVICE_URL', 'http://localhost:5001')
    
    def predict_ipc_sections(self, text):
        """Predict IPC sections from text"""
        try:
            response = requests.post(
                f"{self.base_url}/predict",
                json={'text': text}
            )
            response.raise_for_status()
            return response.json().get('predicted_sections', [])
        except Exception as e:
            logger.error(f"Error predicting IPC sections: {str(e)}")
            return []
    
    def process_audio(self, audio_file, language='en-US'):
        """Process audio file through the AI service"""
        try:
            files = {'file': audio_file}
            data = {'language': language}
            response = requests.post(
                f"{self.base_url}/upload",
                files=files,
                data=data
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error processing audio: {str(e)}")
            return None

ai_client = AIServiceClient()