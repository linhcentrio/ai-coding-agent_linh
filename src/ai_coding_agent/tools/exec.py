"""
Command Execution Tools
========================
Tools for running shell commands and scripts.
"""

import asyncio
import os
import sys
import shlex
from pathlib import Path
from typing import Optional

from .registry import tool, ToolCategory, ToolParameter, ToolResult


@tool(
    name="run_command",
    description="Execute a shell command and return its output. Use for running scripts, build commands, etc.",
    category=ToolCategory.EXEC,
    requires_confirmation=True,
    parameters=[
        ToolParameter(
            name="command",
            type="string",
            description="The command to execute",
            required=True,
        ),
        ToolParameter(
            name="cwd",
            type="string",
            description="Working directory for the command",
            required=False,
        ),
        ToolParameter(
            name="timeout",
            type="integer",
            description="Timeout in seconds (default: 60)",
            required=False,
            default=60,
        ),
    ],
)
async def run_command(
    command: str,
    cwd: Optional[str] = None,
    timeout: int = 60,
) -> ToolResult:
    """Execute a shell command."""
    try:
        # Determine working directory
        work_dir = Path(cwd).resolve() if cwd else Path.cwd()
        
        if not work_dir.exists():
            return ToolResult(success=False, output="", error=f"Directory not found: {cwd}")
        
        # Create subprocess
        if sys.platform == "win32":
            # Windows: use cmd.exe
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(work_dir),
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
        else:
            # Unix: use shell
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(work_dir),
            )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            return ToolResult(
                success=False,
                output="",
                error=f"Command timed out after {timeout} seconds"
            )
        
        # Decode output
        stdout_str = stdout.decode("utf-8", errors="replace") if stdout else ""
        stderr_str = stderr.decode("utf-8", errors="replace") if stderr else ""
        
        # Combine output
        output = stdout_str
        if stderr_str:
            output += f"\n--- stderr ---\n{stderr_str}"
        
        success = process.returncode == 0
        
        return ToolResult(
            success=success,
            output=output,
            error=f"Exit code: {process.returncode}" if not success else None,
            metadata={
                "exit_code": process.returncode,
                "cwd": str(work_dir),
            }
        )
    
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


@tool(
    name="run_python",
    description="Execute Python code directly.",
    category=ToolCategory.EXEC,
    requires_confirmation=True,
    parameters=[
        ToolParameter(
            name="code",
            type="string",
            description="Python code to execute",
            required=True,
        ),
    ],
)
async def run_python(code: str) -> ToolResult:
    """Execute Python code."""
    try:
        # Create a temporary namespace
        namespace = {"__builtins__": __builtins__}
        
        # Compile and exec
        exec(code, namespace)
        
        # Check for result variable
        result = namespace.get("result", namespace.get("output", None))
        
        return ToolResult(
            success=True,
            output=str(result) if result is not None else "Code executed successfully",
        )
    
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


@tool(
    name="get_env",
    description="Get environment variable value.",
    category=ToolCategory.EXEC,
    parameters=[
        ToolParameter(
            name="name",
            type="string",
            description="Environment variable name",
            required=True,
        ),
    ],
)
async def get_env(name: str) -> ToolResult:
    """Get environment variable."""
    value = os.environ.get(name)
    
    if value is None:
        return ToolResult(
            success=True,
            output=f"Environment variable '{name}' is not set",
            metadata={"exists": False}
        )
    
    return ToolResult(
        success=True,
        output=value,
        metadata={"exists": True, "name": name}
    )


@tool(
    name="get_cwd",
    description="Get current working directory.",
    category=ToolCategory.EXEC,
    parameters=[],
)
async def get_cwd() -> ToolResult:
    """Get current working directory."""
    cwd = Path.cwd()
    
    return ToolResult(
        success=True,
        output=str(cwd),
    )
