"""
Tool Registry
==============
Central registry for all available tools.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Awaitable, Union
from enum import Enum


class ToolCategory(Enum):
    """Tool categories."""
    FILE = "file"
    EDIT = "edit"
    EXEC = "exec"
    SEARCH = "search"
    GIT = "git"
    WEB = "web"
    BROWSER = "browser"
    SYSTEM = "system"


@dataclass
class ToolParameter:
    """Tool parameter definition."""
    name: str
    type: str  # "string", "integer", "boolean", "array", "object"
    description: str
    required: bool = True
    default: Any = None
    enum: Optional[List[str]] = None


@dataclass
class ToolDefinition:
    """Definition of a tool that can be called by the agent."""
    name: str
    description: str
    category: ToolCategory
    handler: Callable[..., Awaitable[Any]]
    parameters: List[ToolParameter] = field(default_factory=list)
    requires_confirmation: bool = False
    
    def to_openai_format(self) -> Dict[str, Any]:
        """Convert to OpenAI function calling format."""
        properties = {}
        required = []
        
        for param in self.parameters:
            prop = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum
            if param.default is not None:
                prop["default"] = param.default
            
            properties[param.name] = prop
            
            if param.required:
                required.append(param.name)
        
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                }
            }
        }


@dataclass
class ToolResult:
    """Result from tool execution."""
    success: bool
    output: str
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class ToolRegistry:
    """
    Central registry for managing tools.
    
    Provides:
    - Tool registration
    - Tool lookup by name or category
    - Conversion to OpenAI function format
    - Tool execution with validation
    """
    
    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._categories: Dict[ToolCategory, List[str]] = {cat: [] for cat in ToolCategory}
    
    def register(self, tool: ToolDefinition) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool
        self._categories[tool.category].append(tool.name)
    
    def get(self, name: str) -> Optional[ToolDefinition]:
        """Get tool by name."""
        return self._tools.get(name)
    
    def get_by_category(self, category: ToolCategory) -> List[ToolDefinition]:
        """Get all tools in a category."""
        return [self._tools[name] for name in self._categories.get(category, [])]
    
    def list_all(self) -> List[ToolDefinition]:
        """List all registered tools."""
        return list(self._tools.values())
    
    def list_names(self) -> List[str]:
        """List all tool names."""
        return list(self._tools.keys())
    
    def to_openai_format(self, include_categories: Optional[List[ToolCategory]] = None) -> List[Dict[str, Any]]:
        """
        Convert all tools to OpenAI function calling format.
        
        Args:
            include_categories: Optional filter by categories
        
        Returns:
            List of tools in OpenAI format
        """
        tools = []
        
        for tool in self._tools.values():
            if include_categories is None or tool.category in include_categories:
                tools.append(tool.to_openai_format())
        
        return tools
    
    async def execute(
        self,
        name: str,
        arguments: Dict[str, Any],
        confirm_callback: Optional[Callable[[str, Dict], Awaitable[bool]]] = None,
    ) -> ToolResult:
        """
        Execute a tool by name with given arguments.
        
        Args:
            name: Tool name
            arguments: Tool arguments
            confirm_callback: Optional callback for confirmation prompts
        
        Returns:
            ToolResult with output or error
        """
        tool = self.get(name)
        if not tool:
            return ToolResult(
                success=False,
                output="",
                error=f"Unknown tool: {name}"
            )
        
        # Check confirmation if required
        if tool.requires_confirmation and confirm_callback:
            confirmed = await confirm_callback(name, arguments)
            if not confirmed:
                return ToolResult(
                    success=False,
                    output="",
                    error="Tool execution cancelled by user"
                )
        
        try:
            result = await tool.handler(**arguments)
            
            # Normalize result
            if isinstance(result, ToolResult):
                return result
            elif isinstance(result, str):
                return ToolResult(success=True, output=result)
            elif isinstance(result, dict):
                return ToolResult(
                    success=result.get("success", True),
                    output=result.get("output", str(result)),
                    error=result.get("error"),
                    metadata=result.get("metadata", {})
                )
            else:
                return ToolResult(success=True, output=str(result))
        
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Tool execution failed: {str(e)}"
            )


# Global registry instance
registry = ToolRegistry()


def tool(
    name: str,
    description: str,
    category: ToolCategory = ToolCategory.SYSTEM,
    requires_confirmation: bool = False,
    parameters: Optional[List[ToolParameter]] = None,
):
    """
    Decorator to register a function as a tool.
    
    Usage:
        @tool("read_file", "Read file contents", ToolCategory.FILE)
        async def read_file(path: str) -> str:
            ...
    """
    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        tool_def = ToolDefinition(
            name=name,
            description=description,
            category=category,
            handler=func,
            parameters=parameters or [],
            requires_confirmation=requires_confirmation,
        )
        registry.register(tool_def)
        return func
    
    return decorator
