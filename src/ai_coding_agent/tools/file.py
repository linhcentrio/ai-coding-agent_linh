"""
File Operations Tools
======================
Tools for reading, writing, and managing files.
"""

import os
import glob as glob_module
from pathlib import Path
from typing import List, Optional

from .registry import tool, ToolCategory, ToolParameter, ToolResult


@tool(
    name="read_file",
    description="Read the contents of a file. Returns the file content as text.",
    category=ToolCategory.FILE,
    parameters=[
        ToolParameter(
            name="path",
            type="string",
            description="Path to the file to read (absolute or relative to cwd)",
            required=True,
        ),
        ToolParameter(
            name="start_line",
            type="integer",
            description="Start line number (1-indexed, optional)",
            required=False,
        ),
        ToolParameter(
            name="end_line",
            type="integer",
            description="End line number (1-indexed, inclusive, optional)",
            required=False,
        ),
    ],
)
async def read_file(
    path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
) -> ToolResult:
    """Read file contents, optionally with line range."""
    try:
        file_path = Path(path).resolve()
        
        if not file_path.exists():
            return ToolResult(success=False, output="", error=f"File not found: {path}")
        
        if not file_path.is_file():
            return ToolResult(success=False, output="", error=f"Not a file: {path}")
        
        content = file_path.read_text(encoding="utf-8")
        
        # Apply line range if specified
        if start_line is not None or end_line is not None:
            lines = content.splitlines(keepends=True)
            start = (start_line - 1) if start_line else 0
            end = end_line if end_line else len(lines)
            content = "".join(lines[start:end])
        
        return ToolResult(
            success=True,
            output=content,
            metadata={"path": str(file_path), "size": file_path.stat().st_size}
        )
    
    except UnicodeDecodeError:
        return ToolResult(success=False, output="", error=f"Cannot read binary file: {path}")
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


@tool(
    name="write_file",
    description="Write content to a file. Creates the file if it doesn't exist.",
    category=ToolCategory.FILE,
    requires_confirmation=True,
    parameters=[
        ToolParameter(
            name="path",
            type="string",
            description="Path to the file to write",
            required=True,
        ),
        ToolParameter(
            name="content",
            type="string",
            description="Content to write to the file",
            required=True,
        ),
        ToolParameter(
            name="append",
            type="boolean",
            description="Append to file instead of overwriting",
            required=False,
            default=False,
        ),
    ],
)
async def write_file(path: str, content: str, append: bool = False) -> ToolResult:
    """Write content to a file."""
    try:
        file_path = Path(path).resolve()
        
        # Create parent directories if needed
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        mode = "a" if append else "w"
        file_path.write_text(content, encoding="utf-8") if not append else \
            file_path.open(mode, encoding="utf-8").write(content)
        
        return ToolResult(
            success=True,
            output=f"{'Appended to' if append else 'Wrote'} {file_path}",
            metadata={"path": str(file_path), "bytes_written": len(content.encode())}
        )
    
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


@tool(
    name="list_dir",
    description="List contents of a directory.",
    category=ToolCategory.FILE,
    parameters=[
        ToolParameter(
            name="path",
            type="string",
            description="Path to the directory",
            required=True,
        ),
        ToolParameter(
            name="recursive",
            type="boolean",
            description="List recursively",
            required=False,
            default=False,
        ),
        ToolParameter(
            name="pattern",
            type="string",
            description="Glob pattern to filter files",
            required=False,
        ),
    ],
)
async def list_dir(
    path: str,
    recursive: bool = False,
    pattern: Optional[str] = None,
) -> ToolResult:
    """List directory contents."""
    try:
        dir_path = Path(path).resolve()
        
        if not dir_path.exists():
            return ToolResult(success=False, output="", error=f"Directory not found: {path}")
        
        if not dir_path.is_dir():
            return ToolResult(success=False, output="", error=f"Not a directory: {path}")
        
        if pattern:
            if recursive:
                items = list(dir_path.rglob(pattern))
            else:
                items = list(dir_path.glob(pattern))
        else:
            if recursive:
                items = list(dir_path.rglob("*"))
            else:
                items = list(dir_path.iterdir())
        
        # Format output
        lines = []
        for item in sorted(items):
            rel_path = item.relative_to(dir_path)
            if item.is_dir():
                lines.append(f"📁 {rel_path}/")
            else:
                size = item.stat().st_size
                lines.append(f"📄 {rel_path} ({size} bytes)")
        
        return ToolResult(
            success=True,
            output="\n".join(lines) if lines else "(empty directory)",
            metadata={"path": str(dir_path), "count": len(items)}
        )
    
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


@tool(
    name="create_dir",
    description="Create a new directory.",
    category=ToolCategory.FILE,
    parameters=[
        ToolParameter(
            name="path",
            type="string",
            description="Path to the directory to create",
            required=True,
        ),
    ],
)
async def create_dir(path: str) -> ToolResult:
    """Create a directory."""
    try:
        dir_path = Path(path).resolve()
        dir_path.mkdir(parents=True, exist_ok=True)
        
        return ToolResult(
            success=True,
            output=f"Created directory: {dir_path}",
        )
    
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


@tool(
    name="delete_file",
    description="Delete a file or empty directory.",
    category=ToolCategory.FILE,
    requires_confirmation=True,
    parameters=[
        ToolParameter(
            name="path",
            type="string",
            description="Path to the file or directory to delete",
            required=True,
        ),
    ],
)
async def delete_file(path: str) -> ToolResult:
    """Delete a file or empty directory."""
    try:
        file_path = Path(path).resolve()
        
        if not file_path.exists():
            return ToolResult(success=False, output="", error=f"Path not found: {path}")
        
        if file_path.is_dir():
            file_path.rmdir()
        else:
            file_path.unlink()
        
        return ToolResult(
            success=True,
            output=f"Deleted: {file_path}",
        )
    
    except OSError as e:
        return ToolResult(success=False, output="", error=f"Cannot delete: {e}")


@tool(
    name="file_exists",
    description="Check if a file or directory exists.",
    category=ToolCategory.FILE,
    parameters=[
        ToolParameter(
            name="path",
            type="string",
            description="Path to check",
            required=True,
        ),
    ],
)
async def file_exists(path: str) -> ToolResult:
    """Check if path exists."""
    file_path = Path(path).resolve()
    exists = file_path.exists()
    is_file = file_path.is_file() if exists else False
    is_dir = file_path.is_dir() if exists else False
    
    return ToolResult(
        success=True,
        output=f"{'Exists' if exists else 'Does not exist'}: {path}",
        metadata={
            "exists": exists,
            "is_file": is_file,
            "is_dir": is_dir,
        }
    )
