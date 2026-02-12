"""
CDP Network Inspector
======================
Chrome DevTools Protocol network traffic capture and analysis.
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from enum import Enum


class ResourceType(Enum):
    """HTTP resource types."""
    DOCUMENT = "Document"
    STYLESHEET = "Stylesheet"
    IMAGE = "Image"
    MEDIA = "Media"
    FONT = "Font"
    SCRIPT = "Script"
    XHR = "XHR"
    FETCH = "Fetch"
    WEBSOCKET = "WebSocket"
    OTHER = "Other"


@dataclass
class NetworkRequest:
    """Captured network request."""
    request_id: str
    url: str
    method: str
    resource_type: str
    headers: Dict[str, str] = field(default_factory=dict)
    post_data: Optional[str] = None
    timestamp: str = ""
    
    # Response data (filled when response arrives)
    status: Optional[int] = None
    status_text: Optional[str] = None
    response_headers: Dict[str, str] = field(default_factory=dict)
    response_body: Optional[str] = None
    response_size: int = 0
    response_time_ms: float = 0
    
    # Error info
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "request_id": self.request_id,
            "url": self.url,
            "method": self.method,
            "resource_type": self.resource_type,
            "headers": self.headers,
            "post_data": self.post_data,
            "timestamp": self.timestamp,
            "status": self.status,
            "status_text": self.status_text,
            "response_headers": self.response_headers,
            "response_body": self.response_body[:1000] if self.response_body else None,
            "response_size": self.response_size,
            "response_time_ms": self.response_time_ms,
            "error": self.error,
        }


@dataclass
class NetworkLog:
    """Collection of network requests."""
    requests: List[NetworkRequest] = field(default_factory=list)
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    
    def filter_by_type(self, resource_type: str) -> List[NetworkRequest]:
        """Filter requests by resource type."""
        return [r for r in self.requests if r.resource_type == resource_type]
    
    def filter_by_url(self, pattern: str) -> List[NetworkRequest]:
        """Filter requests by URL pattern."""
        return [r for r in self.requests if pattern in r.url]
    
    def filter_api_calls(self) -> List[NetworkRequest]:
        """Get only API calls (XHR/Fetch)."""
        return [r for r in self.requests if r.resource_type in ("XHR", "Fetch")]
    
    def filter_errors(self) -> List[NetworkRequest]:
        """Get failed requests."""
        return [r for r in self.requests if r.error or (r.status and r.status >= 400)]
    
    def to_json(self, path: str):
        """Export to JSON file."""
        data = {
            "start_time": self.start_time,
            "end_time": self.end_time,
            "total_requests": len(self.requests),
            "requests": [r.to_dict() for r in self.requests],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


class CDPNetworkInspector:
    """
    Capture network traffic using Chrome DevTools Protocol.
    
    Works with Playwright's CDP session to capture:
    - Request/response headers
    - Request bodies
    - Response bodies
    - Timing information
    """
    
    def __init__(
        self,
        page,  # Playwright page
        url_filter: Optional[Callable[[str], bool]] = None,
        capture_body: bool = True,
        max_body_size: int = 100000,  # 100KB
    ):
        self.page = page
        self.url_filter = url_filter
        self.capture_body = capture_body
        self.max_body_size = max_body_size
        
        self._client = None
        self._requests: Dict[str, NetworkRequest] = {}
        self._log = NetworkLog()
        self._is_capturing = False
    
    async def start(self):
        """Start capturing network traffic."""
        # Get CDP session
        self._client = await self.page.context.new_cdp_session(self.page)
        
        # Enable network domain
        await self._client.send("Network.enable")
        
        # Set up event handlers
        self._client.on("Network.requestWillBeSent", self._on_request)
        self._client.on("Network.responseReceived", self._on_response)
        self._client.on("Network.loadingFinished", self._on_loading_finished)
        self._client.on("Network.loadingFailed", self._on_loading_failed)
        
        self._log.start_time = datetime.now().isoformat()
        self._is_capturing = True
    
    async def stop(self) -> NetworkLog:
        """Stop capturing and return log."""
        self._is_capturing = False
        self._log.end_time = datetime.now().isoformat()
        self._log.requests = list(self._requests.values())
        
        if self._client:
            try:
                await self._client.send("Network.disable")
            except Exception:
                pass
        
        return self._log
    
    def _on_request(self, event: Dict[str, Any]):
        """Handle request event."""
        if not self._is_capturing:
            return
        
        request_id = event.get("requestId", "")
        request_data = event.get("request", {})
        url = request_data.get("url", "")
        
        # Apply URL filter
        if self.url_filter and not self.url_filter(url):
            return
        
        self._requests[request_id] = NetworkRequest(
            request_id=request_id,
            url=url,
            method=request_data.get("method", "GET"),
            resource_type=event.get("type", "Other"),
            headers=request_data.get("headers", {}),
            post_data=request_data.get("postData"),
            timestamp=datetime.now().isoformat(),
        )
    
    def _on_response(self, event: Dict[str, Any]):
        """Handle response event."""
        if not self._is_capturing:
            return
        
        request_id = event.get("requestId", "")
        if request_id not in self._requests:
            return
        
        response = event.get("response", {})
        req = self._requests[request_id]
        
        req.status = response.get("status")
        req.status_text = response.get("statusText")
        req.response_headers = response.get("headers", {})
    
    def _on_loading_finished(self, event: Dict[str, Any]):
        """Handle loading finished event."""
        if not self._is_capturing:
            return
        
        request_id = event.get("requestId", "")
        if request_id not in self._requests:
            return
        
        req = self._requests[request_id]
        req.response_size = event.get("encodedDataLength", 0)
        
        # Capture response body if enabled
        if self.capture_body and req.response_size <= self.max_body_size:
            asyncio.create_task(self._capture_body(request_id))
    
    def _on_loading_failed(self, event: Dict[str, Any]):
        """Handle loading failed event."""
        if not self._is_capturing:
            return
        
        request_id = event.get("requestId", "")
        if request_id not in self._requests:
            return
        
        req = self._requests[request_id]
        req.error = event.get("errorText", "Unknown error")
    
    async def _capture_body(self, request_id: str):
        """Capture response body."""
        if request_id not in self._requests:
            return
        
        try:
            result = await self._client.send(
                "Network.getResponseBody",
                {"requestId": request_id}
            )
            
            body = result.get("body", "")
            if result.get("base64Encoded"):
                # Don't store binary content
                self._requests[request_id].response_body = "[Binary content]"
            else:
                self._requests[request_id].response_body = body
        except Exception:
            # Body may not be available
            pass
    
    def get_api_calls(self) -> List[NetworkRequest]:
        """Get captured API calls."""
        return [
            r for r in self._requests.values()
            if r.resource_type in ("XHR", "Fetch")
        ]
    
    def get_failed_requests(self) -> List[NetworkRequest]:
        """Get failed requests."""
        return [
            r for r in self._requests.values()
            if r.error or (r.status and r.status >= 400)
        ]
    
    def clear(self):
        """Clear captured requests."""
        self._requests.clear()
        self._log = NetworkLog()


def create_url_filter(
    include_patterns: Optional[List[str]] = None,
    exclude_patterns: Optional[List[str]] = None,
) -> Callable[[str], bool]:
    """
    Create a URL filter function.
    
    Args:
        include_patterns: URL patterns to include (if set, only these are captured)
        exclude_patterns: URL patterns to exclude
    
    Returns:
        Filter function
    """
    def filter_fn(url: str) -> bool:
        # Check excludes first
        if exclude_patterns:
            for pattern in exclude_patterns:
                if pattern in url:
                    return False
        
        # Check includes
        if include_patterns:
            for pattern in include_patterns:
                if pattern in url:
                    return True
            return False
        
        return True
    
    return filter_fn
