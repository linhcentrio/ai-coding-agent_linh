"""
Browser Testing Tool
=====================
Tool for AI agent to run browser tests.
"""

import asyncio
from pathlib import Path
from typing import Optional

from ..tools.registry import tool, ToolCategory, ToolParameter, ToolResult
from .workflow_runner import TestWorkflowRunner, TestWorkflow


@tool(
    name="run_browser_test",
    description="Run a browser test workflow to test web application functionality. Captures network traffic and screenshots.",
    category=ToolCategory.BROWSER,
    requires_confirmation=True,
    parameters=[
        ToolParameter(
            name="workflow_path",
            type="string",
            description="Path to YAML workflow file, or inline YAML content",
            required=True,
        ),
        ToolParameter(
            name="base_url",
            type="string",
            description="Base URL for the web application",
            required=False,
        ),
        ToolParameter(
            name="variables",
            type="object",
            description="Variables to substitute in workflow (e.g., username, password)",
            required=False,
        ),
    ],
)
async def run_browser_test(
    workflow_path: str,
    base_url: Optional[str] = None,
    variables: Optional[dict] = None,
) -> ToolResult:
    """Run a browser test workflow."""
    try:
        runner = TestWorkflowRunner()
        
        path = Path(workflow_path)
        if path.exists():
            # Load from file
            workflow = TestWorkflow.from_yaml(path)
        else:
            # Try parsing as inline YAML
            import yaml
            data = yaml.safe_load(workflow_path)
            workflow = TestWorkflow.from_dict(data)
        
        # Override base_url if provided
        if base_url:
            workflow.base_url = base_url
        
        result = await runner.run(workflow, extra_variables=variables or {})
        
        # Format output
        output_lines = [
            f"Test: {result.workflow_name}",
            f"Status: {'✅ PASSED' if result.success else '❌ FAILED'}",
            f"Time: {result.total_time_ms:.0f}ms",
            f"Steps: {len(result.step_results)}",
            "",
        ]
        
        for step in result.step_results:
            status = "✅" if step.success else "❌"
            output_lines.append(f"  {status} {step.step_name}")
            if step.error:
                output_lines.append(f"     Error: {step.error}")
        
        if result.network_logs:
            total_requests = sum(len(log.requests) for log in result.network_logs)
            output_lines.append(f"\nNetwork: {total_requests} requests captured")
        
        return ToolResult(
            success=result.success,
            output="\n".join(output_lines),
            error=result.error_message,
            metadata={
                "workflow": result.workflow_name,
                "passed": result.success,
                "failed_step": result.failed_step,
                "time_ms": result.total_time_ms,
            }
        )
    
    except ImportError:
        return ToolResult(
            success=False,
            output="",
            error="Playwright not installed. Run: pip install playwright && playwright install"
        )
    except Exception as e:
        return ToolResult(
            success=False,
            output="",
            error=str(e)
        )


@tool(
    name="capture_network",
    description="Navigate to a URL and capture all network requests for analysis.",
    category=ToolCategory.BROWSER,
    requires_confirmation=True,
    parameters=[
        ToolParameter(
            name="url",
            type="string",
            description="URL to navigate to",
            required=True,
        ),
        ToolParameter(
            name="wait_seconds",
            type="integer",
            description="Seconds to wait for network activity (default: 5)",
            required=False,
            default=5,
        ),
        ToolParameter(
            name="filter_pattern",
            type="string",
            description="URL pattern to filter (only capture matching requests)",
            required=False,
        ),
    ],
)
async def capture_network(
    url: str,
    wait_seconds: int = 5,
    filter_pattern: Optional[str] = None,
) -> ToolResult:
    """Capture network traffic from a URL."""
    try:
        from .browser import BrowserManager
        from .network_inspector import CDPNetworkInspector, create_url_filter
        
        browser = BrowserManager()
        await browser.start()
        
        try:
            # Create filter
            url_filter = None
            if filter_pattern:
                url_filter = create_url_filter(include_patterns=[filter_pattern])
            
            inspector = CDPNetworkInspector(browser.page, url_filter=url_filter)
            await inspector.start()
            
            # Navigate
            await browser.navigate(url)
            
            # Wait for network activity
            await asyncio.sleep(wait_seconds)
            
            # Stop capture
            log = await inspector.stop()
            
            # Format output
            output_lines = [
                f"URL: {url}",
                f"Requests: {len(log.requests)}",
                "",
            ]
            
            api_calls = log.filter_api_calls()
            if api_calls:
                output_lines.append("API Calls:")
                for req in api_calls[:10]:
                    status = req.status or "pending"
                    output_lines.append(f"  {req.method} {req.url[:80]} [{status}]")
            
            errors = log.filter_errors()
            if errors:
                output_lines.append(f"\nErrors: {len(errors)}")
                for req in errors[:5]:
                    output_lines.append(f"  ❌ {req.method} {req.url[:60]}: {req.error or req.status}")
            
            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata={
                    "total_requests": len(log.requests),
                    "api_calls": len(api_calls),
                    "errors": len(errors),
                }
            )
        
        finally:
            await browser.stop()
    
    except ImportError:
        return ToolResult(
            success=False,
            output="",
            error="Playwright not installed. Run: pip install playwright && playwright install"
        )
    except Exception as e:
        return ToolResult(
            success=False,
            output="",
            error=str(e)
        )
