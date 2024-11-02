import requests
from .capability import Capability

class GeminiRequest(Capability):
    def describe(self) -> str:
        return "Handles requests to the Gemini API."

    def __call__(self, endpoint: str, payload: dict) -> dict:
        url = f"https://api.gemini.com/v1/{endpoint}"
        response = requests.post(url, json=payload)
        return response.json()
