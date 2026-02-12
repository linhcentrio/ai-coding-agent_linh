"""
Code Editing Tools
===================
Tools for editing code files with diffs and replacements.
"""

import difflib
import re
from pathlib import Path
from typing import Optional, List

from .registry import tool, ToolCategory, ToolParameter, ToolResult


@tool(
    name="replace_in_file",
    description="Replace a specific string or pattern in a file. Use for small, targeted edits.",
    category=ToolCategory.EDIT,
    requires_confirmation=True,
    parameters=[
        ToolParameter(
            name="path",
            type="string",
            description="Path to the file to edit",
            required=True,
        ),
        ToolParameter(
            name="old_text",
            type="string",
            description="Exact text to replace (or regex pattern if is_regex=True)",
            required=True,
        ),
        ToolParameter(
            name="new_text",
            type="string",
            description="New text to insert",
            required=True,
        ),
        ToolParameter(
            name="is_regex",
            type="boolean",
            description="Treat old_text as a regex pattern",
            required=False,
            default=False,
        ),
        ToolParameter(
            name="count",
            type="integer",
            description="Maximum number of replacements (0 for all)",
            required=False,
            default=0,
        ),
    ],
)
async def replace_in_file(
    path: str,
    old_text: str,
    new_text: str,
    is_regex: bool = False,
    count: int = 0,
) -> ToolResult:
    """Replace text in a file."""
    try:
        file_path = Path(path).resolve()
        
        if not file_path.exists():
            return ToolResult(success=False, output="", error=f"File not found: {path}")
        
        content = file_path.read_text(encoding="utf-8")
        
        if is_regex:
            if count > 0:
                new_content = re.sub(old_text, new_text, content, count=count)
            else:
                new_content = re.sub(old_text, new_text, content)
            replacements = len(re.findall(old_text, content))
        else:
            if old_text not in content:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Text not found in file: '{old_text[:50]}...'"
                )
            
            if count > 0:
                new_content = content.replace(old_text, new_text, count)
            else:
                new_content = content.replace(old_text, new_text)
            replacements = content.count(old_text)
        
        file_path.write_text(new_content, encoding="utf-8")
        
        return ToolResult(
            success=True,
            output=f"Replaced {replacements} occurrence(s) in {file_path}",
            metadata={"path": str(file_path), "replacements": replacements}
        )
    
    except re.error as e:
        return ToolResult(success=False, output="", error=f"Invalid regex: {e}")
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


@tool(
    name="apply_diff",
    description="Apply a unified diff patch to a file.",
    category=ToolCategory.EDIT,
    requires_confirmation=True,
    parameters=[
        ToolParameter(
            name="path",
            type="string",
            description="Path to the file to patch",
            required=True,
        ),
        ToolParameter(
            name="diff",
            type="string",
            description="Unified diff content to apply",
            required=True,
        ),
    ],
)
async def apply_diff(path: str, diff: str) -> ToolResult:
    """Apply a unified diff to a file."""
    try:
        file_path = Path(path).resolve()
        
        if not file_path.exists():
            # Create new file if diff creates it
            original_lines = []
        else:
            original_lines = file_path.read_text(encoding="utf-8").splitlines(keepends=True)
        
        # Parse diff hunks
        new_lines = list(original_lines)
        diff_lines = diff.splitlines(keepends=True)
        
        # Simple diff application (handles @@ -X,Y +X,Y @@ format)
        offset = 0
        hunk_pattern = re.compile(r'^@@ -(\d+),?\d* \+(\d+),?\d* @@')
        
        i = 0
        while i < len(diff_lines):
            line = diff_lines[i]
            
            match = hunk_pattern.match(line)
            if match:
                start_orig = int(match.group(1)) - 1
                i += 1
                
                # Apply hunk
                while i < len(diff_lines):
                    dline = diff_lines[i]
                    if dline.startswith('@@') or not (dline.startswith('+') or dline.startswith('-') or dline.startswith(' ')):
                        break
                    
                    if dline.startswith('-'):
                        # Remove line
                        if start_orig + offset < len(new_lines):
                            del new_lines[start_orig + offset]
                            offset -= 1
                    elif dline.startswith('+'):
                        # Add line
                        content = dline[1:]
                        if not content.endswith('\n'):
                            content += '\n'
                        new_lines.insert(start_orig + offset + 1, content)
                        offset += 1
                        start_orig += 1
                    else:
                        # Context line
                        start_orig += 1
                    
                    i += 1
            else:
                i += 1
        
        file_path.write_text("".join(new_lines), encoding="utf-8")
        
        return ToolResult(
            success=True,
            output=f"Applied diff to {file_path}",
            metadata={"path": str(file_path)}
        )
    
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


@tool(
    name="insert_lines",
    description="Insert lines at a specific position in a file.",
    category=ToolCategory.EDIT,
    requires_confirmation=True,
    parameters=[
        ToolParameter(
            name="path",
            type="string",
            description="Path to the file to edit",
            required=True,
        ),
        ToolParameter(
            name="line_number",
            type="integer",
            description="Line number to insert at (1-indexed, inserts before this line)",
            required=True,
        ),
        ToolParameter(
            name="content",
            type="string",
            description="Content to insert",
            required=True,
        ),
    ],
)
async def insert_lines(path: str, line_number: int, content: str) -> ToolResult:
    """Insert content at a specific line."""
    try:
        file_path = Path(path).resolve()
        
        if not file_path.exists():
            return ToolResult(success=False, output="", error=f"File not found: {path}")
        
        lines = file_path.read_text(encoding="utf-8").splitlines(keepends=True)
        
        insert_idx = max(0, min(line_number - 1, len(lines)))
        
        new_lines = content.splitlines(keepends=True)
        if new_lines and not new_lines[-1].endswith('\n'):
            new_lines[-1] += '\n'
        
        lines[insert_idx:insert_idx] = new_lines
        
        file_path.write_text("".join(lines), encoding="utf-8")
        
        return ToolResult(
            success=True,
            output=f"Inserted {len(new_lines)} line(s) at line {line_number}",
            metadata={"path": str(file_path), "line": line_number, "lines_inserted": len(new_lines)}
        )
    
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


@tool(
    name="show_diff",
    description="Show unified diff between two strings or file versions.",
    category=ToolCategory.EDIT,
    parameters=[
        ToolParameter(
            name="old_content",
            type="string",
            description="Original content",
            required=True,
        ),
        ToolParameter(
            name="new_content",
            type="string",
            description="New content",
            required=True,
        ),
        ToolParameter(
            name="filename",
            type="string",
            description="Filename for diff header",
            required=False,
            default="file",
        ),
    ],
)
async def show_diff(old_content: str, new_content: str, filename: str = "file") -> ToolResult:
    """Generate a unified diff between two strings."""
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    
    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
    )
    
    diff_str = "".join(diff)
    
    return ToolResult(
        success=True,
        output=diff_str if diff_str else "(no differences)",
    )
