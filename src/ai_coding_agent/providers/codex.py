"""
Codex Provider (OpenAI OAuth)
==============================
OpenAI Codex provider using OAuth tokens from Codex CLI.
Based on litellm-codex-oauth-provider pattern.
"""

import os
import json
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from .base import (
    BaseProvider,
    ProviderType,
    Message,
    ToolCall,
    CompletionResponse,
    StreamChunk,
)


class CodexProvider(BaseProvider):
    """
    OpenAI Codex provider using OAuth authentication.
    
    Uses tokens from Codex CLI (~/.codex/auth.json) or direct API key.
    Supports GPT-4, GPT-4-turbo, and other OpenAI models.
    """
    
    # Standard Codex CLI token paths
    TOKEN_PATHS = [
        Path.home() / ".codex" / "auth.json",
        Path.home() / ".config" / "codex" / "auth.json",
    ]
    
    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        use_oauth: bool = True,
        **kwargs
    ):
        # Try OAuth token first, then API key
        if use_oauth and not api_key:
            api_key = self._get_oauth_token()
        
        if not api_key:
            api_key = os.getenv("OPENAI_API_KEY")
        
        super().__init__(model, api_key, temperature, max_tokens, **kwargs)
        self._client = None
        self._base_url = kwargs.get("base_url", "https://api.openai.com/v1")
    
    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.CODEX
    
    def _get_oauth_token(self) -> Optional[str]:
        """Read OAuth token from Codex CLI auth file."""
        for token_path in self.TOKEN_PATHS:
            if token_path.exists():
                try:
                    auth_data = json.loads(token_path.read_text())
                    access_token = auth_data.get("access_token")
                    if access_token:
                        return access_token
                except Exception:
                    continue
        return None
    
    def _get_client(self):
        """Lazy initialize OpenAI client."""
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=120.0,
            )
        return self._client
    
    def _convert_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Convert messages to OpenAI format."""
        openai_messages = []
        
        for msg in messages:
            message = {"role": msg.role, "content": msg.content}
            
            if msg.name:
                message["name"] = msg.name
            if msg.tool_calls:
                message["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["arguments"])
                        }
                    }
                    for tc in msg.tool_calls
                ]
            if msg.tool_call_id:
                message["tool_call_id"] = msg.tool_call_id
            
            openai_messages.append(message)
        
        return openai_messages
    
    async def complete(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> CompletionResponse:
        """Generate completion using OpenAI API."""
        client = self._get_client()
        
        payload = {
            "model": self.model,
            "messages": self._convert_messages(messages),
            "temperature": kwargs.get("temperature", self.temperature),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
        }
        
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = kwargs.get("tool_choice", "auto")
        
        response = await client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()
        
        choice = data["choices"][0]
        message = choice["message"]
        
        # Parse tool calls
        tool_calls = []
        if message.get("tool_calls"):
            for tc in message["tool_calls"]:
                tool_calls.append(ToolCall(
                    id=tc["id"],
                    name=tc["function"]["name"],
                    arguments=json.loads(tc["function"]["arguments"])
                ))
        
        return CompletionResponse(
            content=message.get("content", "") or "",
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", "stop"),
            usage=data.get("usage", {}),
            model=self.model,
            provider="codex",
        )
    
    async def stream(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> AsyncIterator[StreamChunk]:
        """Stream completion using OpenAI API."""
        client = self._get_client()
        
        payload = {
            "model": self.model,
            "messages": self._convert_messages(messages),
            "temperature": kwargs.get("temperature", self.temperature),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "stream": True,
        }
        
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = kwargs.get("tool_choice", "auto")
        
        async with client.stream("POST", "/chat/completions", json=payload) as response:
            response.raise_for_status()
            
            tool_calls_buffer = {}
            
            async for line in response.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                
                data_str = line[6:]  # Remove "data: " prefix
                if data_str == "[DONE]":
                    yield StreamChunk(finish_reason="stop")
                    break
                
                try:
                    data = json.loads(data_str)
                    choice = data["choices"][0]
                    delta = choice.get("delta", {})
                    
                    # Content
                    if delta.get("content"):
                        yield StreamChunk(content=delta["content"])
                    
                    # Tool calls
                    if delta.get("tool_calls"):
                        for tc in delta["tool_calls"]:
                            idx = tc["index"]
                            if idx not in tool_calls_buffer:
                                tool_calls_buffer[idx] = {
                                    "id": tc.get("id", ""),
                                    "name": "",
                                    "arguments": ""
                                }
                            if tc.get("id"):
                                tool_calls_buffer[idx]["id"] = tc["id"]
                            if tc.get("function", {}).get("name"):
                                tool_calls_buffer[idx]["name"] = tc["function"]["name"]
                            if tc.get("function", {}).get("arguments"):
                                tool_calls_buffer[idx]["arguments"] += tc["function"]["arguments"]
                    
                    # Finish
                    if choice.get("finish_reason"):
                        if tool_calls_buffer:
                            tool_calls = []
                            for tc in tool_calls_buffer.values():
                                try:
                                    args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                                except json.JSONDecodeError:
                                    args = {}
                                tool_calls.append(ToolCall(
                                    id=tc["id"],
                                    name=tc["name"],
                                    arguments=args
                                ))
                            yield StreamChunk(tool_calls=tool_calls, finish_reason="tool_calls")
                        else:
                            yield StreamChunk(finish_reason=choice["finish_reason"])
                        break
                
                except json.JSONDecodeError:
                    continue
    
    async def is_available(self) -> bool:
        """Check if OpenAI/Codex API is available."""
        if not self.api_key:
            return False
        
        try:
            client = self._get_client()
            response = await client.get("/models")
            return response.status_code == 200
        except Exception:
            return False
    
    def get_capabilities(self) -> Dict[str, Any]:
        caps = super().get_capabilities()
        caps.update({
            "supports_vision": "vision" in self.model or "gpt-4o" in self.model,
            "context_window": 128000 if "gpt-4" in self.model else 16000,
            "uses_oauth": bool(self._get_oauth_token()),
        })
        return caps
