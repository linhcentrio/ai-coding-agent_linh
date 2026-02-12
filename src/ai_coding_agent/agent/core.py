"""
Core Agent
===========
Main agent class that orchestrates LLM interactions and tool execution.
"""

import asyncio
from typing import Any, AsyncIterator, Callable, Dict, List, Optional
from dataclasses import dataclass, field

from ..providers.base import (
    BaseProvider,
    Message,
    ToolCall,
    CompletionResponse,
    StreamChunk,
)
from ..tools.registry import ToolRegistry, ToolResult, registry


@dataclass
class AgentConfig:
    """Agent configuration."""
    system_prompt: str = """You are an expert AI coding assistant. You help users with software development tasks.

You have access to tools for:
- Reading and writing files
- Editing code with diffs and replacements
- Running shell commands
- Searching files and code

When helping users:
1. Understand the task clearly before acting
2. Use tools to inspect the codebase when needed
3. Make precise, targeted changes
4. Explain what you're doing and why
5. Verify your changes when possible

Be concise and helpful. Focus on solving the user's problem efficiently."""
    
    max_iterations: int = 20
    max_tool_calls_per_turn: int = 10
    temperature: float = 0.7
    confirm_dangerous_tools: bool = True


@dataclass
class AgentState:
    """Current agent state."""
    messages: List[Message] = field(default_factory=list)
    iteration: int = 0
    tool_calls_this_turn: int = 0
    is_complete: bool = False
    last_response: Optional[str] = None


class CodingAgent:
    """
    Main AI Coding Agent.
    
    Orchestrates:
    - Conversation with LLM provider
    - Tool execution loop
    - Context management
    - Streaming responses
    """
    
    def __init__(
        self,
        provider: BaseProvider,
        config: Optional[AgentConfig] = None,
        tool_registry: Optional[ToolRegistry] = None,
        confirm_callback: Optional[Callable[[str, Dict], asyncio.Future]] = None,
    ):
        self.provider = provider
        self.config = config or AgentConfig()
        self.tools = tool_registry or registry
        self.confirm_callback = confirm_callback
        self.state = AgentState()
        
        # Initialize with system message
        self._init_conversation()
    
    def _init_conversation(self):
        """Initialize conversation with system prompt."""
        self.state.messages = [
            Message(role="system", content=self.config.system_prompt)
        ]
    
    def get_tools_for_llm(self) -> List[Dict[str, Any]]:
        """Get tools in OpenAI function format for LLM."""
        return self.tools.to_openai_format()
    
    async def process_message(
        self,
        user_message: str,
        stream: bool = True,
    ) -> AsyncIterator[str]:
        """
        Process a user message and yield response chunks.
        
        Args:
            user_message: The user's input
            stream: Whether to stream the response
        
        Yields:
            Response content chunks
        """
        # Add user message
        self.state.messages.append(Message(role="user", content=user_message))
        self.state.iteration = 0
        self.state.tool_calls_this_turn = 0
        self.state.is_complete = False
        
        while not self.state.is_complete and self.state.iteration < self.config.max_iterations:
            self.state.iteration += 1
            
            if stream:
                async for chunk in self._process_turn_streaming():
                    yield chunk
            else:
                response = await self._process_turn()
                if response:
                    yield response
            
            # Check if we should continue (tool calls pending)
            if self.state.is_complete:
                break
    
    async def _process_turn_streaming(self) -> AsyncIterator[str]:
        """Process one turn with streaming."""
        tools = self.get_tools_for_llm()
        
        full_content = ""
        all_tool_calls = []
        
        async for chunk in self.provider.stream(
            messages=self.state.messages,
            tools=tools,
            temperature=self.config.temperature,
        ):
            if chunk.content:
                full_content += chunk.content
                yield chunk.content
            
            if chunk.tool_calls:
                all_tool_calls.extend(chunk.tool_calls)
            
            if chunk.finish_reason:
                break
        
        # Add assistant message
        self.state.messages.append(Message(
            role="assistant",
            content=full_content,
            tool_calls=[{
                "id": tc.id,
                "name": tc.name,
                "arguments": tc.arguments
            } for tc in all_tool_calls] if all_tool_calls else None
        ))
        
        # Process tool calls
        if all_tool_calls:
            async for chunk in self._execute_tools(all_tool_calls):
                yield chunk
        else:
            self.state.is_complete = True
            self.state.last_response = full_content
    
    async def _process_turn(self) -> str:
        """Process one turn without streaming."""
        tools = self.get_tools_for_llm()
        
        response = await self.provider.complete(
            messages=self.state.messages,
            tools=tools,
            temperature=self.config.temperature,
        )
        
        # Add assistant message
        self.state.messages.append(Message(
            role="assistant",
            content=response.content,
            tool_calls=[{
                "id": tc.id,
                "name": tc.name,
                "arguments": tc.arguments
            } for tc in response.tool_calls] if response.tool_calls else None
        ))
        
        # Process tool calls
        if response.tool_calls:
            return await self._execute_tools_sync(response.tool_calls)
        else:
            self.state.is_complete = True
            self.state.last_response = response.content
            return response.content
    
    async def _execute_tools(self, tool_calls: List[ToolCall]) -> AsyncIterator[str]:
        """Execute tool calls and yield status updates."""
        for tc in tool_calls:
            if self.state.tool_calls_this_turn >= self.config.max_tool_calls_per_turn:
                yield "\n[Max tool calls reached for this turn]\n"
                break
            
            self.state.tool_calls_this_turn += 1
            
            yield f"\n🔧 Calling: {tc.name}\n"
            
            result = await self.tools.execute(
                name=tc.name,
                arguments=tc.arguments,
                confirm_callback=self.confirm_callback if self.config.confirm_dangerous_tools else None,
            )
            
            # Add tool result message
            self.state.messages.append(Message(
                role="tool",
                content=result.output if result.success else f"Error: {result.error}",
                name=tc.name,
                tool_call_id=tc.id,
            ))
            
            if result.success:
                yield f"✅ {tc.name}: {result.output[:200]}{'...' if len(result.output) > 200 else ''}\n"
            else:
                yield f"❌ {tc.name}: {result.error}\n"
    
    async def _execute_tools_sync(self, tool_calls: List[ToolCall]) -> str:
        """Execute tool calls and return summary."""
        results = []
        
        for tc in tool_calls:
            if self.state.tool_calls_this_turn >= self.config.max_tool_calls_per_turn:
                results.append("[Max tool calls reached]")
                break
            
            self.state.tool_calls_this_turn += 1
            
            result = await self.tools.execute(
                name=tc.name,
                arguments=tc.arguments,
                confirm_callback=self.confirm_callback if self.config.confirm_dangerous_tools else None,
            )
            
            self.state.messages.append(Message(
                role="tool",
                content=result.output if result.success else f"Error: {result.error}",
                name=tc.name,
                tool_call_id=tc.id,
            ))
            
            status = "✅" if result.success else "❌"
            results.append(f"{status} {tc.name}")
        
        return " | ".join(results)
    
    def reset(self):
        """Reset agent state for new conversation."""
        self.state = AgentState()
        self._init_conversation()
    
    def get_conversation_history(self) -> List[Message]:
        """Get current conversation history."""
        return self.state.messages.copy()
    
    def add_context(self, content: str, role: str = "system"):
        """Add context message to conversation."""
        self.state.messages.append(Message(role=role, content=content))
