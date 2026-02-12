"""
Browser Automation
===================
Playwright-based browser automation for testing web applications.
"""

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from enum import Enum


class BrowserType(Enum):
    """Supported browser types."""
    CHROMIUM = "chromium"
    FIREFOX = "firefox"
    WEBKIT = "webkit"


@dataclass
class BrowserConfig:
    """Browser configuration."""
    browser_type: BrowserType = BrowserType.CHROMIUM
    headless: bool = True
    slow_mo: int = 0  # Milliseconds
    timeout: int = 30000
    viewport_width: int = 1280
    viewport_height: int = 720
    user_agent: Optional[str] = None
    storage_state: Optional[str] = None  # Path to auth state
    proxy: Optional[Dict[str, str]] = None


@dataclass
class PageAction:
    """Action to perform on a page."""
    action: str  # click, type, navigate, wait, screenshot, etc.
    selector: Optional[str] = None
    value: Optional[str] = None
    timeout: Optional[int] = None
    options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionResult:
    """Result of a page action."""
    success: bool
    action: str
    selector: Optional[str] = None
    output: str = ""
    error: Optional[str] = None
    screenshot_path: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class BrowserManager:
    """
    Manage browser instances for testing.
    
    Provides:
    - Browser lifecycle management
    - Page navigation and interaction
    - Screenshot capture
    - Cookie/storage management
    """
    
    def __init__(self, config: Optional[BrowserConfig] = None):
        self.config = config or BrowserConfig()
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
    
    async def start(self):
        """Start browser instance."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise ImportError("Please install playwright: pip install playwright && playwright install")
        
        self._playwright = await async_playwright().start()
        
        # Get browser launcher
        if self.config.browser_type == BrowserType.CHROMIUM:
            launcher = self._playwright.chromium
        elif self.config.browser_type == BrowserType.FIREFOX:
            launcher = self._playwright.firefox
        else:
            launcher = self._playwright.webkit
        
        # Launch browser
        launch_options = {
            "headless": self.config.headless,
            "slow_mo": self.config.slow_mo,
        }
        
        if self.config.proxy:
            launch_options["proxy"] = self.config.proxy
        
        self._browser = await launcher.launch(**launch_options)
        
        # Create context
        context_options = {
            "viewport": {
                "width": self.config.viewport_width,
                "height": self.config.viewport_height,
            }
        }
        
        if self.config.user_agent:
            context_options["user_agent"] = self.config.user_agent
        
        if self.config.storage_state and Path(self.config.storage_state).exists():
            context_options["storage_state"] = self.config.storage_state
        
        self._context = await self._browser.new_context(**context_options)
        self._page = await self._context.new_page()
        
        # Set default timeout
        self._page.set_default_timeout(self.config.timeout)
    
    async def stop(self):
        """Stop browser instance."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
    
    async def navigate(self, url: str, wait_until: str = "load") -> ActionResult:
        """Navigate to URL."""
        try:
            await self._page.goto(url, wait_until=wait_until)
            return ActionResult(
                success=True,
                action="navigate",
                output=f"Navigated to {url}",
                metadata={"url": self._page.url}
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action="navigate",
                error=str(e)
            )
    
    async def click(self, selector: str, timeout: Optional[int] = None) -> ActionResult:
        """Click an element."""
        try:
            await self._page.click(selector, timeout=timeout)
            return ActionResult(
                success=True,
                action="click",
                selector=selector,
                output=f"Clicked {selector}"
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action="click",
                selector=selector,
                error=str(e)
            )
    
    async def type_text(
        self, 
        selector: str, 
        text: str, 
        clear: bool = True,
        delay: int = 0,
    ) -> ActionResult:
        """Type text into an input."""
        try:
            if clear:
                await self._page.fill(selector, "")
            await self._page.type(selector, text, delay=delay)
            return ActionResult(
                success=True,
                action="type",
                selector=selector,
                output=f"Typed into {selector}"
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action="type",
                selector=selector,
                error=str(e)
            )
    
    async def get_text(self, selector: str) -> ActionResult:
        """Get text content of an element."""
        try:
            text = await self._page.text_content(selector)
            return ActionResult(
                success=True,
                action="get_text",
                selector=selector,
                output=text or ""
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action="get_text",
                selector=selector,
                error=str(e)
            )
    
    async def wait_for_selector(
        self, 
        selector: str, 
        state: str = "visible",
        timeout: Optional[int] = None,
    ) -> ActionResult:
        """Wait for element to appear."""
        try:
            await self._page.wait_for_selector(selector, state=state, timeout=timeout)
            return ActionResult(
                success=True,
                action="wait",
                selector=selector,
                output=f"Element {selector} is {state}"
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action="wait",
                selector=selector,
                error=str(e)
            )
    
    async def screenshot(
        self, 
        path: str, 
        full_page: bool = False,
        selector: Optional[str] = None,
    ) -> ActionResult:
        """Take a screenshot."""
        try:
            if selector:
                element = await self._page.query_selector(selector)
                if element:
                    await element.screenshot(path=path)
                else:
                    return ActionResult(
                        success=False,
                        action="screenshot",
                        selector=selector,
                        error=f"Element not found: {selector}"
                    )
            else:
                await self._page.screenshot(path=path, full_page=full_page)
            
            return ActionResult(
                success=True,
                action="screenshot",
                output=f"Screenshot saved to {path}",
                screenshot_path=path
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action="screenshot",
                error=str(e)
            )
    
    async def evaluate(self, script: str) -> ActionResult:
        """Execute JavaScript in the page."""
        try:
            result = await self._page.evaluate(script)
            return ActionResult(
                success=True,
                action="evaluate",
                output=str(result) if result is not None else ""
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action="evaluate",
                error=str(e)
            )
    
    async def get_cookies(self) -> ActionResult:
        """Get all cookies."""
        try:
            cookies = await self._context.cookies()
            return ActionResult(
                success=True,
                action="get_cookies",
                output=str(cookies),
                metadata={"cookies": cookies}
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action="get_cookies",
                error=str(e)
            )
    
    async def save_storage_state(self, path: str) -> ActionResult:
        """Save authentication state."""
        try:
            await self._context.storage_state(path=path)
            return ActionResult(
                success=True,
                action="save_storage",
                output=f"Storage state saved to {path}"
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action="save_storage",
                error=str(e)
            )
    
    async def execute_action(self, action: PageAction) -> ActionResult:
        """Execute a generic page action."""
        if action.action == "navigate":
            return await self.navigate(
                action.value or "",
                wait_until=action.options.get("wait_until", "load")
            )
        elif action.action == "click":
            return await self.click(action.selector or "", action.timeout)
        elif action.action == "type":
            return await self.type_text(
                action.selector or "",
                action.value or "",
                clear=action.options.get("clear", True),
                delay=action.options.get("delay", 0)
            )
        elif action.action == "wait":
            return await self.wait_for_selector(
                action.selector or "",
                state=action.options.get("state", "visible"),
                timeout=action.timeout
            )
        elif action.action == "screenshot":
            return await self.screenshot(
                action.value or "screenshot.png",
                full_page=action.options.get("full_page", False),
                selector=action.selector
            )
        elif action.action == "evaluate":
            return await self.evaluate(action.value or "")
        elif action.action == "get_text":
            return await self.get_text(action.selector or "")
        else:
            return ActionResult(
                success=False,
                action=action.action,
                error=f"Unknown action: {action.action}"
            )
    
    @property
    def page(self):
        """Get current page."""
        return self._page
    
    @property
    def context(self):
        """Get browser context."""
        return self._context
