# File: src/hackingBuddyGPT/utils/openai/openai_llm.py
import requests
import tiktoken
import time
from os import getenv

from dataclasses import dataclass
from vertexai.preview.tokenization import get_tokenizer_for_model

from hackingBuddyGPT.utils.configurable import configurable, parameter
from hackingBuddyGPT.utils.llm_util import LLMResult, LLM

# Uncomment the following to log debug output
import logging
logging.basicConfig(level=logging.DEBUG)

@configurable("openai-compatible-llm-api", "OpenAI-compatible LLM API")
@dataclass
class OpenAIConnection(LLM):
    """
    While the OpenAIConnection is a configurable, it is not exported by this packages __init__.py on purpose. This is
    due to the fact, that it usually makes more sense for a finished UseCase to specialize onto one specific version of
    an OpenAI API compatible LLM.
    If you really must use it, you can import it directly from the utils.openai.openai_llm module, which will later on
    show you, that you did not specialize yet.
    """
    api_key: str = parameter(desc="OpenAI API Key")
    model: str = parameter(desc="OpenAI model name")
    context_size: int = parameter(
        desc="Maximum context size for the model, only used internally for things like trimming to the context size")
    use_openrouter: bool = parameter(desc="Use OpenRouter API", default=False)
    openrouter_base_url: str = parameter(desc="Base URL for OpenRouter API", default="https://openrouter.ai/api/v1")
    api_url: str = parameter(desc="URL of the OpenAI API", default="https://api.openai.com")
    api_path: str = parameter(desc="Path to the OpenAI API", default="/v1/chat/completions")
    api_timeout: int = parameter(desc="Timeout for the API request", default=240)
    api_backoff: int = parameter(desc="Backoff time in seconds when running into rate-limits", default=60)
    api_retries: int = parameter(desc="Number of retries when running into rate-limits", default=3)

    _tokenizer = None

    def get_response(self, prompt, *, retry: int = 0, **kwargs) -> LLMResult:
        if retry >= self.api_retries:
            raise Exception("Failed to get response from OpenAI API")

        if hasattr(prompt, "render"):
            prompt = prompt.render(**kwargs)

        # Prioritize api_key from kwargs if provided
        api_key = kwargs.get("api_key", self.api_key)  

        url = self.openrouter_base_url if self.use_openrouter else f'{self.api_url}{self.api_path}'  # Use OpenRouter URL if needed
        headers = {"Authorization": f"Bearer {api_key}"} # Use the potentially overridden api_key
        data = {'model': self.model, 'messages': [{'role': 'user', 'content': prompt}]}

        # Log the request payload
        logging.debug(f"Request payload: {data}")

        try:
            tic = time.perf_counter()
            response = requests.post(url, headers=headers, json=data, timeout=self.api_timeout)

            # Log response headers, status, and body
            logging.debug(f"Response Headers: {response.headers}")
            logging.debug(f"Response Status: {response.status_code}")
            logging.debug(f"Response Body: {response.text}")

            if response.status_code == 429:
                print(f"[RestAPI-Connector] running into rate-limits, waiting for {self.api_backoff} seconds")
                time.sleep(self.api_backoff)
                return self.get_response(prompt, retry=retry + 1, **kwargs) # Pass kwargs in recursive call

            if response.status_code != 200:
                gateway_name = "OpenRouter" if self.use_openrouter else "OpenAI Gateway"
                raise Exception(f"Error from {gateway_name} ({response.status_code}): {response.text}") 

        except requests.exceptions.ConnectionError:
            print("Connection error! Retrying in 5 seconds..")
            time.sleep(5)
            return self.get_response(prompt, retry=retry + 1, **kwargs) # Pass kwargs in recursive call

        except requests.exceptions.Timeout:
            print("Timeout while contacting LLM REST endpoint")
            return self.get_response(prompt, retry=retry + 1, **kwargs) # Pass kwargs in recursive call

        toc = time.perf_counter()
        response = response.json()
        result = response['choices'][0]['message']['content']

        if self.use_openrouter and any(
            gemini_or_gemma_model in self.model
            for gemini_or_gemma_model in ["google/gemini-flash-1.5-8b-exp",
                                         "google/gemini-flash-1.5-exp",
                                         "google/gemini-pro-1.5-exp",
                                         "google/gemma-2-9b-it:free"]
        ):
            self._tokenizer = get_tokenizer_for_model(self.model.replace("google/", ""))
            tok_query = self._tokenizer.count_tokens(prompt).total_tokens
            tok_res = self._tokenizer.count_tokens(result).total_tokens
        else:
            tok_query = response.get('usage', {}).get('prompt_tokens', 0)  # Handle missing 'usage'
            tok_res = response.get('usage', {}).get('completion_tokens', 0)  # Handle missing 'usage'
        return LLMResult(result, prompt, result, toc - tic, tok_query, tok_res)


    def encode(self, query) -> list[int]:
        if self.use_openrouter and any(
                gemini_or_gemma_model in self.model
                for gemini_or_gemma_model in ["google/gemini-flash-1.5-8b-exp",
                                             "google/gemini-flash-1.5-exp",
                                             "google/gemini-pro-1.5-exp",
                                             "google/gemma-2-9b-it:free"]
        ):
            self._tokenizer = get_tokenizer_for_model(self.model.replace("google/", ""))
            return self._tokenizer.encode(query).tokens
        elif self.model.startswith("gpt-"):
            encoding = tiktoken.encoding_for_model(self.model)
            return encoding.encode(query)
        else:
            encoding = tiktoken.encoding_for_model("gpt-3.5-turbo") # Default
            return encoding.encode(query)


@configurable("openai/gpt-3.5-turbo", "OpenAI GPT-3.5 Turbo")
@dataclass
class GPT35Turbo(OpenAIConnection):
    model: str = "gpt-3.5-turbo"
    context_size: int = 16385


@configurable("openai/gpt-4", "OpenAI GPT-4")
@dataclass
class GPT4(OpenAIConnection):
    model: str = "gpt-4"
    context_size: int = 8192


@configurable("openai/gpt-4-turbo", "OpenAI GPT-4-turbo (preview)")
@dataclass
class GPT4Turbo(OpenAIConnection):
    model: str = "gpt-4-turbo-preview"
    context_size: int = 128000


@configurable("google/gemini-flash-1.5-8b-exp", "Google Gemini Flash 1.5 8b exp")
@dataclass
class GeminiFlash158bExp(OpenAIConnection):
    model: str = "google/gemini-flash-1.5-8b-exp"
    context_size: int = 1000000
    api_key: str = getenv("OPENROUTER_API_KEY")  # Get API key from environment variable
    use_openrouter: bool = True  # Enable OpenRouter
    # openrouter_base_url: str = "https://custom-openrouter-deployment.com/api/v1"  # Optional custom URL


@configurable("google/gemini-flash-1.5-exp", "Google Gemini Flash 1.5 exp")
@dataclass
class GeminiFlash15Exp(OpenAIConnection):
    model: str = "google/gemini-flash-1.5-exp"
    context_size: int = 1000000
    api_key: str = getenv("OPENROUTER_API_KEY")
    use_openrouter: bool = True  # Enable OpenRouter


@configurable("google/gemini-pro-1.5-exp", "Google Gemini Pro 1.5 exp")
@dataclass
class GeminiPro15Exp(OpenAIConnection):
    model: str = "google/gemini-pro-1.5-exp"
    context_size: int = 2000000
    api_key: str = getenv("OPENROUTER_API_KEY")
    use_openrouter: bool = True  # Enable OpenRouter


@configurable("google/gemma-2-9b-it:free", "Google Gemma 2 9b it:free")
@dataclass
class Gemma29bItFree(OpenAIConnection):
    model: str = "google/gemma-2-9b-it:free"
    context_size: int = 8192
    api_key: str = getenv("OPENROUTER_API_KEY")
    use_openrouter: bool = True  # Enable OpenRouter
