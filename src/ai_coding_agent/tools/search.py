"""
Search Tools
=============
Tools for searching files and content.
"""

import os
import re
import subprocess
from pathlib import Path
from typing import Optional, List

from .registry import tool, ToolCategory, ToolParameter, ToolResult


@tool(
    name="grep",
    description="Search for a pattern in files. Returns matching lines with file paths and line numbers.",
    category=ToolCategory.SEARCH,
    parameters=[
        ToolParameter(
            name="pattern",
            type="string",
            description="Search pattern (regex supported)",
            required=True,
        ),
        ToolParameter(
            name="path",
            type="string",
            description="File or directory to search in",
            required=True,
        ),
        ToolParameter(
            name="include",
            type="string",
            description="File pattern to include (e.g., '*.py')",
            required=False,
        ),
        ToolParameter(
            name="case_sensitive",
            type="boolean",
            description="Case-sensitive search",
            required=False,
            default=True,
        ),
        ToolParameter(
            name="max_results",
            type="integer",
            description="Maximum number of results (default: 50)",
            required=False,
            default=50,
        ),
    ],
)
async def grep(
    pattern: str,
    path: str,
    include: Optional[str] = None,
    case_sensitive: bool = True,
    max_results: int = 50,
) -> ToolResult:
    """Search for pattern in files."""
    try:
        search_path = Path(path).resolve()
        
        if not search_path.exists():
            return ToolResult(success=False, output="", error=f"Path not found: {path}")
        
        flags = 0 if case_sensitive else re.IGNORECASE
        
        try:
            regex = re.compile(pattern, flags)
        except re.error as e:
            return ToolResult(success=False, output="", error=f"Invalid regex: {e}")
        
        results = []
        
        # Get files to search
        if search_path.is_file():
            files = [search_path]
        else:
            if include:
                files = list(search_path.rglob(include))
            else:
                files = [f for f in search_path.rglob("*") if f.is_file()]
        
        for file_path in files:
            if len(results) >= max_results:
                break
            
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                
                for i, line in enumerate(content.splitlines(), 1):
                    if regex.search(line):
                        rel_path = file_path.relative_to(search_path) if search_path.is_dir() else file_path.name
                        results.append(f"{rel_path}:{i}: {line.strip()}")
                        
                        if len(results) >= max_results:
                            break
            
            except (UnicodeDecodeError, PermissionError):
                continue
        
        output = "\n".join(results) if results else f"No matches found for: {pattern}"
        
        return ToolResult(
            success=True,
            output=output,
            metadata={"matches": len(results), "pattern": pattern}
        )
    
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


@tool(
    name="find_files",
    description="Find files by name or pattern.",
    category=ToolCategory.SEARCH,
    parameters=[
        ToolParameter(
            name="path",
            type="string",
            description="Directory to search in",
            required=True,
        ),
        ToolParameter(
            name="name",
            type="string",
            description="File name pattern (glob, e.g., '*.py')",
            required=True,
        ),
        ToolParameter(
            name="type",
            type="string",
            description="Type filter: 'file', 'dir', or 'any'",
            required=False,
            default="file",
            enum=["file", "dir", "any"],
        ),
        ToolParameter(
            name="max_results",
            type="integer",
            description="Maximum number of results",
            required=False,
            default=50,
        ),
    ],
)
async def find_files(
    path: str,
    name: str,
    type: str = "file",
    max_results: int = 50,
) -> ToolResult:
    """Find files by name pattern."""
    try:
        search_path = Path(path).resolve()
        
        if not search_path.exists():
            return ToolResult(success=False, output="", error=f"Path not found: {path}")
        
        if not search_path.is_dir():
            return ToolResult(success=False, output="", error=f"Not a directory: {path}")
        
        matches = list(search_path.rglob(name))
        
        # Filter by type
        if type == "file":
            matches = [m for m in matches if m.is_file()]
        elif type == "dir":
            matches = [m for m in matches if m.is_dir()]
        
        # Limit results
        matches = matches[:max_results]
        
        results = []
        for match in matches:
            rel_path = match.relative_to(search_path)
            size = match.stat().st_size if match.is_file() else None
            if size is not None:
                results.append(f"{rel_path} ({size} bytes)")
            else:
                results.append(f"{rel_path}/")
        
        output = "\n".join(results) if results else f"No matches found for: {name}"
        
        return ToolResult(
            success=True,
            output=output,
            metadata={"matches": len(results), "pattern": name}
        )
    
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


@tool(
    name="ripgrep",
    description="Fast search using ripgrep (rg) if available, falls back to grep.",
    category=ToolCategory.SEARCH,
    parameters=[
        ToolParameter(
            name="pattern",
            type="string",
            description="Search pattern",
            required=True,
        ),
        ToolParameter(
            name="path",
            type="string",
            description="Path to search",
            required=True,
        ),
        ToolParameter(
            name="file_type",
            type="string",
            description="File type filter (e.g., 'py', 'js')",
            required=False,
        ),
    ],
)
async def ripgrep(
    pattern: str,
    path: str,
    file_type: Optional[str] = None,
) -> ToolResult:
    """Fast search using ripgrep."""
    try:
        search_path = Path(path).resolve()
        
        # Try ripgrep first
        cmd = ["rg", "--line-number", "--no-heading", pattern, str(search_path)]
        
        if file_type:
            cmd.extend(["-t", file_type])
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(search_path) if search_path.is_dir() else str(search_path.parent),
            )
            
            output = result.stdout.strip() if result.stdout else "No matches found"
            
            return ToolResult(
                success=True,
                output=output,
                metadata={"tool": "ripgrep"}
            )
        
        except FileNotFoundError:
            # Fall back to Python grep
            include = f"*.{file_type}" if file_type else None
            return await grep(pattern, path, include=include)
    
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))
