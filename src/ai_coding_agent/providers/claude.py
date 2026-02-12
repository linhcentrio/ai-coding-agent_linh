"""
Claude Provider
================
Anthropic Claude API provider implementation.
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


class ClaudeProvider(BaseProvider):
    """
    Anthropic Claude API provider.
    
    Supports Claude 3 Opus, Sonnet, Haiku models.
    Uses anthropic library.
    """
    
    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        api_key: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs
    ):
        api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        super().__init__(model, api_key, temperature, max_tokens, **kwargs)
        self._client = None
    
    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.CLAUDE
    
    def _get_client(self):
        """Lazy initialize Anthropic client."""
        if self._client is None:
            import anthropic
            self._client = anthropic.AsyncAnthropic(api_key=self.api_key)
        return self._client
    
    def _convert_messages(self, messages: List[Message]) -> tuple[str, List[Dict[str, Any]]]:
        """Convert messages to Anthropic format. Returns (system, messages)."""
        system = ""
        anthropic_messages = []
        
        for msg in messages:
            if msg.role == "system":
                system = msg.content
            elif msg.role == "user":
                anthropic_messages.append({
                    "role": "user",
                    "content": msg.content
                })
            elif msg.role == "assistant":
                content = []
                if msg.content:
                    content.append({"type": "text", "text": msg.content})
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        content.append({
                            "type": "tool_use",
                            "id": tc["id"],
                            "name": tc["name"],
                            "input": tc["arguments"]
                        })
                anthropic_messages.append({
                    "role": "assistant",
                    "content": content if content else msg.content
                })
            elif msg.role == "tool":
                anthropic_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id,
                        "content": msg.content
                    }]
                })
        
        return system, anthropic_messages
    
    def _convert_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert OpenAI function format to Anthropic format."""
        anthropic_tools = []
        
        for tool in tools:
            if tool.get("type") == "function":
                func = tool["function"]
                anthropic_tools.append({
                    "name": func["name"],
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {"type": "object", "properties": {}})
                })
        
        return anthropic_tools
    
    async def complete(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> CompletionResponse:
        """Generate completion using Claude API."""
        client = self._get_client()
        
        system, anthropic_messages = self._convert_messages(messages)
        anthropic_tools = self._convert_tools(tools) if tools else None
        
        params = {
            "model": self.model,
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", self.temperature),
            "messages": anthropic_messages,
        }
        
        if system:
            params["system"] = system
        if anthropic_tools:
            params["tools"] = anthropic_tools
        
        response = await client.messages.create(**params)
        
        # Parse response
        content = ""
        tool_calls = []
        
        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input
                ))
        
        return CompletionResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason="tool_use" if tool_calls else response.stop_reason,
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
            model=self.model,
            provider="claude",
        )
    
    async def stream(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> AsyncIterator[StreamChunk]:
        """Stream completion using Claude API."""
        client = self._get_client()
        
        system, anthropic_messages = self._convert_messages(messages)
        anthropic_tools = self._convert_tools(tools) if tools else None
        
        params = {
            "model": self.model,
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", self.temperature),
            "messages": anthropic_messages,
        }
        
        if system:
            params["system"] = system
        if anthropic_tools:
            params["tools"] = anthropic_tools
        
        async with client.messages.stream(**params) as stream:
            current_tool = None
            
            async for event in stream:
                if event.type == "content_block_delta":
                    if hasattr(event.delta, "text"):
                        yield StreamChunk(content=event.delta.text)
                    elif hasattr(event.delta, "partial_json"):
                        # Tool input being streamed
                        pass
                elif event.type == "content_block_start":
                    if event.content_block.type == "tool_use":
                        current_tool = {
                            "id": event.content_block.id,
                            "name": event.content_block.name,
                        }
                elif event.type == "content_block_stop":
                    if current_tool:
                        # Tool call complete
                        current_tool = None
                elif event.type == "message_stop":
                    yield StreamChunk(finish_reason="stop")
    
    async def is_available(self) -> bool:
        """Check if Claude API is available."""
        if not self.api_key:
            return False
        
        try:
            client = self._get_client()
            return client is not None
        except Exception:
            return False
    
    def get_capabilities(self) -> Dict[str, Any]:
        caps = super().get_capabilities()
        caps.update({
            "supports_vision": True,
            "context_window": 200000,
        })
        return caps
