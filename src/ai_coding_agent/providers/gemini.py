"""
Gemini Provider
================
Google Gemini API provider implementation.
"""

import os
from typing import Any, AsyncIterator, Dict, List, Optional

from .base import (
    BaseProvider,
    ProviderType,
    Message,
    ToolCall,
    CompletionResponse,
    StreamChunk,
)


class GeminiProvider(BaseProvider):
    """
    Google Gemini API provider.
    
    Supports Gemini Pro, Gemini Flash, and other Gemini models.
    Uses google-generativeai library.
    """
    
    def __init__(
        self,
        model: str = "gemini-2.0-flash",
        api_key: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 8192,
        **kwargs
    ):
        api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        super().__init__(model, api_key, temperature, max_tokens, **kwargs)
        self._client = None
    
    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.GEMINI
    
    def _get_client(self):
        """Lazy initialize Gemini client."""
        if self._client is None:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self._client = genai.GenerativeModel(self.model)
        return self._client
    
    def _convert_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Convert messages to Gemini format."""
        gemini_messages = []
        
        for msg in messages:
            if msg.role == "system":
                # Gemini handles system messages differently
                gemini_messages.append({
                    "role": "user",
                    "parts": [f"System instruction: {msg.content}"]
                })
            elif msg.role == "user":
                gemini_messages.append({
                    "role": "user",
                    "parts": [msg.content]
                })
            elif msg.role == "assistant":
                gemini_messages.append({
                    "role": "model",
                    "parts": [msg.content]
                })
            elif msg.role == "tool":
                # Tool results
                gemini_messages.append({
                    "role": "user",
                    "parts": [f"Tool result ({msg.name}): {msg.content}"]
                })
        
        return gemini_messages
    
    def _convert_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert OpenAI function format to Gemini format."""
        gemini_tools = []
        
        for tool in tools:
            if tool.get("type") == "function":
                func = tool["function"]
                gemini_tools.append({
                    "name": func["name"],
                    "description": func.get("description", ""),
                    "parameters": func.get("parameters", {})
                })
        
        return [{"function_declarations": gemini_tools}] if gemini_tools else None
    
    async def complete(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> CompletionResponse:
        """Generate completion using Gemini API."""
        client = self._get_client()
        
        gemini_messages = self._convert_messages(messages)
        gemini_tools = self._convert_tools(tools) if tools else None
        
        generation_config = {
            "temperature": kwargs.get("temperature", self.temperature),
            "max_output_tokens": kwargs.get("max_tokens", self.max_tokens),
        }
        
        # Create chat and send message
        chat = client.start_chat(history=gemini_messages[:-1] if len(gemini_messages) > 1 else [])
        
        response = await chat.send_message_async(
            gemini_messages[-1]["parts"][0] if gemini_messages else "",
            generation_config=generation_config,
            tools=gemini_tools,
        )
        
        # Parse tool calls if any
        tool_calls = []
        content = ""
        
        for part in response.parts:
            if hasattr(part, "text"):
                content += part.text
            elif hasattr(part, "function_call"):
                fc = part.function_call
                tool_calls.append(ToolCall(
                    id=f"call_{len(tool_calls)}",
                    name=fc.name,
                    arguments=dict(fc.args)
                ))
        
        return CompletionResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason="tool_calls" if tool_calls else "stop",
            model=self.model,
            provider="gemini",
        )
    
    async def stream(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> AsyncIterator[StreamChunk]:
        """Stream completion using Gemini API."""
        client = self._get_client()
        
        gemini_messages = self._convert_messages(messages)
        gemini_tools = self._convert_tools(tools) if tools else None
        
        generation_config = {
            "temperature": kwargs.get("temperature", self.temperature),
            "max_output_tokens": kwargs.get("max_tokens", self.max_tokens),
        }
        
        chat = client.start_chat(history=gemini_messages[:-1] if len(gemini_messages) > 1 else [])
        
        response = await chat.send_message_async(
            gemini_messages[-1]["parts"][0] if gemini_messages else "",
            generation_config=generation_config,
            tools=gemini_tools,
            stream=True,
        )
        
        async for chunk in response:
            for part in chunk.parts:
                if hasattr(part, "text"):
                    yield StreamChunk(content=part.text)
                elif hasattr(part, "function_call"):
                    fc = part.function_call
                    yield StreamChunk(
                        tool_calls=[ToolCall(
                            id=f"call_0",
                            name=fc.name,
                            arguments=dict(fc.args)
                        )]
                    )
        
        yield StreamChunk(finish_reason="stop")
    
    async def is_available(self) -> bool:
        """Check if Gemini API is available."""
        if not self.api_key:
            return False
        
        try:
            client = self._get_client()
            # Quick validation
            return client is not None
        except Exception:
            return False
    
    def get_capabilities(self) -> Dict[str, Any]:
        caps = super().get_capabilities()
        caps.update({
            "supports_vision": "vision" in self.model.lower(),
            "context_window": 1000000 if "1.5" in self.model else 32000,
        })
        return caps
