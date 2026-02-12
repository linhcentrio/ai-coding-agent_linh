"""
Base Provider Interface
========================
Abstract base class for all LLM providers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional
from enum import Enum


class ProviderType(Enum):
    """Supported provider types."""
    GEMINI = "gemini"
    CODEX = "codex"
    CLAUDE = "claude"
    LOCAL = "local"


@dataclass
class Message:
    """Chat message."""
    role: str  # "user", "assistant", "system", "tool"
    content: str
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None


@dataclass
class ToolCall:
    """Tool call from LLM."""
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class CompletionResponse:
    """Response from LLM completion."""
    content: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: Dict[str, int] = field(default_factory=dict)
    model: str = ""
    provider: str = ""


@dataclass
class StreamChunk:
    """Streaming response chunk."""
    content: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    finish_reason: Optional[str] = None


class BaseProvider(ABC):
    """
    Abstract base class for LLM providers.
    
    All providers must implement:
    - complete(): Synchronous completion
    - stream(): Streaming completion
    - is_available(): Check if provider is ready
    """
    
    def __init__(
        self,
        model: str,
        api_key: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs
    ):
        self.model = model
        self.api_key = api_key
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.config = kwargs
    
    @property
    @abstractmethod
    def provider_type(self) -> ProviderType:
        """Return the provider type."""
        pass
    
    @abstractmethod
    async def complete(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> CompletionResponse:
        """
        Generate a completion for the given messages.
        
        Args:
            messages: List of conversation messages
            tools: Optional list of available tools (OpenAI function format)
            **kwargs: Additional provider-specific options
        
        Returns:
            CompletionResponse with content and optional tool calls
        """
        pass
    
    @abstractmethod
    async def stream(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream a completion for the given messages.
        
        Args:
            messages: List of conversation messages
            tools: Optional list of available tools
            **kwargs: Additional provider-specific options
        
        Yields:
            StreamChunk objects with partial content
        """
        pass
    
    @abstractmethod
    async def is_available(self) -> bool:
        """
        Check if this provider is available and configured.
        
        Returns:
            True if provider can be used, False otherwise
        """
        pass
    
    def get_capabilities(self) -> Dict[str, Any]:
        """Return provider capabilities."""
        return {
            "provider": self.provider_type.value,
            "model": self.model,
            "supports_tools": True,
            "supports_streaming": True,
            "supports_vision": False,
            "max_tokens": self.max_tokens,
        }
