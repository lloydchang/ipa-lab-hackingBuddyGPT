import unittest
from unittest.mock import patch, MagicMock
from hackingBuddyGPT.capabilities.gemini_request import GeminiRequest

class TestGeminiRequest(unittest.TestCase):

    def setUp(self):
        self.gemini_request = GeminiRequest()

    def test_describe(self):
        description = self.gemini_request.describe()
        self.assertEqual(description, "Handles requests to the Gemini API.")

    @patch('requests.post')
    def test_call(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"key": "value"}
        mock_post.return_value = mock_response

        endpoint = "test_endpoint"
        payload = {"data": "test"}

        response = self.gemini_request(endpoint, payload)
        self.assertEqual(response, {"key": "value"})
        mock_post.assert_called_once_with(f"https://api.gemini.com/v1/{endpoint}", json=payload)

if __name__ == '__main__':
    unittest.main()
