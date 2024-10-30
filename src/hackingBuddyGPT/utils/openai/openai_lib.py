# File: src/hackingBuddyGPT/utils/openai/openai_lib.py
import instructor
from typing import Dict, Union, Iterable, Optional
from os import getenv

from rich.console import Console
from openai.types import CompletionUsage
from openai.types.chat import ChatCompletionChunk, ChatCompletionMessage, ChatCompletionMessageParam, \
    ChatCompletionMessageToolCall
from openai.types.chat.chat_completion_message_tool_call import Function
import openai
import tiktoken
import time
from dataclasses import dataclass

from hackingBuddyGPT.utils import LLM, configurable, LLMResult
from hackingBuddyGPT.utils.configurable import parameter
from hackingBuddyGPT.capabilities import Capability
from hackingBuddyGPT.capabilities.capability import capabilities_to_tools

from vertexai.preview.tokenization import get_tokenizer_for_model

# Uncomment the following to log debug output
# import logging
# logging.basicConfig(level=logging.DEBUG)

@configurable("openai-lib", "OpenAI Library based connection")
@dataclass
class OpenAILib(LLM):
    api_key: str = parameter(desc="OpenAI API Key")
    model: str = parameter(desc="OpenAI model name")
    context_size: int = parameter(desc="OpenAI model context size")
    use_openrouter: bool = parameter(desc="Use OpenRouter API", default=False)
    openrouter_base_url: str = parameter(desc="Base URL for OpenRouter API", default="https://openrouter.ai/api/v1")
    api_url: str = parameter(desc="URL of the OpenAI API", default="https://api.openai.com/v1")
    api_timeout: int = parameter(desc="Timeout for the API request", default=60)
    api_retries: int = parameter(desc="Number of retries when running into rate-limits", default=3)

    _client: openai.OpenAI = None
    _tokenizer = None

    def init(self):
        base_url = self.openrouter_base_url if self.use_openrouter else self.api_url
        self._client = openai.OpenAI(api_key=self.api_key, base_url=base_url, timeout=self.api_timeout, max_retries=self.api_retries)

        if self.use_openrouter and self.model.startswith("google/"):
            self._tokenizer = get_tokenizer_for_model(self.model.replace("google/", ""))
        elif not self.use_openrouter and self.model.startswith("gpt-"):
            self._tokenizer = tiktoken.encoding_for_model(self.model)

    @property
    def client(self) -> openai.OpenAI:
        return self._client

    @property
    def instructor(self) -> instructor.Instructor:
        return instructor.from_openai(self.client)

    def get_response(self, prompt, *, capabilities: Dict[str, Capability]=None, **kwargs) -> LLMResult:
        """  # TODO: re-enable compatibility layer
        if isinstance(prompt, str) or hasattr(prompt, "render"):
            prompt = {"role": "user", "content": prompt}

        if isinstance(prompt, dict):
            prompt = [prompt]

        for i, v in enumerate(prompt):
            if hasattr(v, "content") and hasattr(v["content"], "render"):
                prompt[i]["content"] = v.render(**kwargs)
        """

        tools = None
        if capabilities:
            tools = capabilities_to_tools(capabilities)

        tic = time.perf_counter()

        # Log the request payload
        #
        # Uncomment the following to log debug output
        # logging.debug(f"Request payload: {data}")

        response = self._client.chat.completions.create(
            model=self.model,
            messages=prompt,
            tools=tools,
        )

        # Log response headers, status, and body
        #
        # Uncomment the following to log debug output
        # logging.debug(f"Response Headers: {response.headers}")
        # logging.debug(f"Response Status: {response.status_code}")
        # logging.debug(f"Response Body: {response.text}")

        toc = time.perf_counter()
        message = response.choices[0].message

        if self._tokenizer:
            if self.use_openrouter and self.model.startswith("google/"):
                tokens_query = self._tokenizer.count_tokens(prompt).total_tokens
                tokens_response = self._tokenizer.count_tokens(message.content).total_tokens
            elif not self.use_openrouter and self.model.startswith("gpt-"):
                tokens_query = len(self._tokenizer.encode(prompt))
                tokens_response = len(self._tokenizer.encode(message.content))
            else:
                tokens_query = 0  # Fallback if no tokenizer configured
                tokens_response = 0
        else:
            tokens_query = 0
            tokens_response = 0

        return LLMResult(
            message,
            str(prompt),
            message.content,
            toc - tic,
            tokens_query,
            tokens_response,
        )

    def stream_response(self, prompt: Iterable[ChatCompletionMessageParam], console: Console, capabilities: Dict[str, Capability] = None) -> Iterable[Union[ChatCompletionChunk, LLMResult]]:
        tools = None
        if capabilities:
            tools = capabilities_to_tools(capabilities)

        tic = time.perf_counter()
        chunks = self._client.chat.completions.create(
            model=self.model,
            messages=prompt,
            tools=tools,
            stream=True,
            stream_options={"include_usage": True},
        )

        state = None
        message = ChatCompletionMessage(role="assistant", content="", tool_calls=[])
        usage: Optional[CompletionUsage] = None

        for chunk in chunks:
            outputs = 0
            if len(chunk.choices) > 0:
                if len(chunk.choices) > 1:
                    print("WARNING: Got more than one choice in the stream response")

                delta = chunk.choices[0].delta
                if delta.role is not None and delta.role != message.role:
                    print(f"WARNING: Got a role change to '{delta.role}' in the stream response")

                if delta.content is not None:
                    message.content += delta.content
                    if state != "content":
                        state = "content"
                        console.print("\n\n[bold blue]ASSISTANT:[/bold blue]")
                    console.print(delta.content, end="")
                    outputs += 1

                if delta.tool_calls is not None and len(delta.tool_calls) > 0:
                    if state != "tool_call":
                        state = "tool_call"
                    for tool_call in delta.tool_calls:
                        if len(message.tool_calls) <= tool_call.index:
                            if len(message.tool_calls) != tool_call.index:
                                print(
                                    f"WARNING: Got a tool call with index {tool_call.index} but expected {len(message.tool_calls)}")
                                return
                            console.print(
                                f"\n\n[bold red]TOOL CALL - {tool_call.function.name}:[/bold red]")
                            message.tool_calls.append(ChatCompletionMessageToolCall(id=tool_call.id,
                                                                                 function=Function(
                                                                                     name=tool_call.function.name,
                                                                                     arguments=tool_call.function.arguments),
                                                                                 type="function"))
                        console.print(tool_call.function.arguments, end="")
                        message.tool_calls[tool_call.index].function.arguments += tool_call.function.arguments
                        outputs += 1

            if chunk.usage is not None:
                usage = chunk.usage

            if outputs > 1:
                print("WARNING: Got more than one output in the stream response")
            yield chunk

        console.print()
        if usage is None:
            print("WARNING: Did not get usage information in the stream response")
            usage = CompletionUsage(completion_tokens=0, prompt_tokens=0, total_tokens=0)

        if len(message.tool_calls) == 0:  # the openAI API does not like getting empty tool call lists
            message.tool_calls = None

        toc = time.perf_counter()

        # Token counting logic in stream_response (identical to get_response)
        if self._tokenizer:
            if self.use_openrouter and self.model.startswith("google/"):
                tokens_query = self._tokenizer.count_tokens(prompt).total_tokens
                tokens_response = self._tokenizer.count_tokens(message.content).total_tokens
            elif not self.use_openrouter and self.model.startswith("gpt-"):
                tokens_query = len(self._tokenizer.encode(prompt))
                tokens_response = len(self._tokenizer.encode(message.content))
            else:
                tokens_query = 0  # Fallback if no tokenizer configured
                tokens_response = 0
        else:
            tokens_query = 0
            tokens_response = 0

        yield LLMResult(
            message,
            str(prompt),
            message.content,
            toc - tic,
            tokens_query,  # Correctly use calculated tokens
            tokens_response,  # Correctly use calculated tokens
        )
        pass

    def encode(self, query) -> list[int]:
        if self._tokenizer:
            if self.use_openrouter and self.model.startswith("google/"):
                return self._tokenizer.encode(query).tokens
            elif not self.use_openrouter and self.model.startswith("gpt-"):
                return self._tokenizer.encode(query)
        return []  # Return an empty list if no tokenizer is available

    def count_tokens(self, query) -> int:
        return len(self.encode(query))
