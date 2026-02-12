"""
Test Workflow Runner
=====================
Execute browser test workflows from YAML configuration.
"""

import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .browser import BrowserManager, BrowserConfig, PageAction, ActionResult
from .network_inspector import CDPNetworkInspector, NetworkLog, create_url_filter


@dataclass
class TestStep:
    """Single step in a test workflow."""
    name: str
    action: str
    selector: Optional[str] = None
    value: Optional[str] = None
    timeout: Optional[int] = None
    optional: bool = False
    capture_network: bool = False
    assert_condition: Optional[str] = None
    assert_value: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestStep":
        return cls(
            name=data.get("name", data.get("action", "")),
            action=data.get("action", ""),
            selector=data.get("selector"),
            value=data.get("value") or data.get("url") or data.get("text"),
            timeout=data.get("timeout"),
            optional=data.get("optional", False),
            capture_network=data.get("capture_network", False),
            assert_condition=data.get("assert"),
            assert_value=data.get("expected"),
        )


@dataclass
class TestWorkflow:
    """Test workflow configuration."""
    name: str
    description: str = ""
    base_url: str = ""
    steps: List[TestStep] = field(default_factory=list)
    variables: Dict[str, str] = field(default_factory=dict)
    browser_config: Optional[BrowserConfig] = None
    network_filter: Optional[List[str]] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestWorkflow":
        steps = [TestStep.from_dict(s) for s in data.get("steps", [])]
        
        browser_config = None
        if "browser" in data:
            bc = data["browser"]
            browser_config = BrowserConfig(
                headless=bc.get("headless", True),
                slow_mo=bc.get("slow_mo", 0),
                timeout=bc.get("timeout", 30000),
            )
        
        return cls(
            name=data.get("name", "unnamed"),
            description=data.get("description", ""),
            base_url=data.get("base_url", ""),
            steps=steps,
            variables=data.get("variables", {}),
            browser_config=browser_config,
            network_filter=data.get("network_filter"),
        )
    
    @classmethod
    def from_yaml(cls, path: Path) -> "TestWorkflow":
        """Load workflow from YAML file."""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data)


@dataclass
class StepResult:
    """Result of a test step."""
    step_name: str
    success: bool
    output: str = ""
    error: Optional[str] = None
    network_log: Optional[NetworkLog] = None
    screenshot_path: Optional[str] = None
    assertion_passed: Optional[bool] = None


@dataclass
class TestResult:
    """Result of complete test run."""
    workflow_name: str
    success: bool
    step_results: List[StepResult] = field(default_factory=list)
    total_time_ms: float = 0
    network_logs: List[NetworkLog] = field(default_factory=list)
    failed_step: Optional[str] = None
    error_message: Optional[str] = None


class TestWorkflowRunner:
    """
    Execute browser test workflows.
    
    Features:
    - YAML workflow loading
    - Variable substitution
    - Network capture per step
    - Assertions
    - Screenshot on failure
    """
    
    def __init__(
        self,
        output_dir: Optional[Path] = None,
        screenshot_on_failure: bool = True,
    ):
        self.output_dir = output_dir or Path("./test_output")
        self.screenshot_on_failure = screenshot_on_failure
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self._browser: Optional[BrowserManager] = None
        self._inspector: Optional[CDPNetworkInspector] = None
    
    def _substitute_variables(
        self, 
        text: Optional[str], 
        variables: Dict[str, str]
    ) -> Optional[str]:
        """Replace {{variable}} placeholders."""
        if not text:
            return text
        
        result = text
        for key, value in variables.items():
            result = result.replace(f"{{{{{key}}}}}", value)
        
        return result
    
    async def run(
        self, 
        workflow: TestWorkflow,
        extra_variables: Optional[Dict[str, str]] = None,
    ) -> TestResult:
        """
        Execute a test workflow.
        
        Args:
            workflow: TestWorkflow to execute
            extra_variables: Additional variables to substitute
        
        Returns:
            TestResult with all step results
        """
        import time
        start_time = time.time()
        
        # Merge variables
        variables = {**workflow.variables, **(extra_variables or {})}
        
        # Initialize browser
        config = workflow.browser_config or BrowserConfig()
        self._browser = BrowserManager(config)
        
        step_results = []
        network_logs = []
        failed_step = None
        error_message = None
        
        try:
            await self._browser.start()
            
            # Initialize network inspector
            if workflow.network_filter:
                url_filter = create_url_filter(include_patterns=workflow.network_filter)
            else:
                url_filter = None
            
            self._inspector = CDPNetworkInspector(
                self._browser.page,
                url_filter=url_filter,
            )
            
            # Execute steps
            for step in workflow.steps:
                result = await self._execute_step(step, variables, workflow.base_url)
                step_results.append(result)
                
                if result.network_log:
                    network_logs.append(result.network_log)
                
                if not result.success and not step.optional:
                    failed_step = step.name
                    error_message = result.error
                    
                    # Screenshot on failure
                    if self.screenshot_on_failure:
                        screenshot_path = self.output_dir / f"failure_{step.name}.png"
                        await self._browser.screenshot(str(screenshot_path))
                        step_results[-1].screenshot_path = str(screenshot_path)
                    
                    break
        
        except Exception as e:
            error_message = str(e)
        
        finally:
            if self._browser:
                await self._browser.stop()
        
        total_time = (time.time() - start_time) * 1000
        
        return TestResult(
            workflow_name=workflow.name,
            success=failed_step is None and error_message is None,
            step_results=step_results,
            total_time_ms=total_time,
            network_logs=network_logs,
            failed_step=failed_step,
            error_message=error_message,
        )
    
    async def _execute_step(
        self,
        step: TestStep,
        variables: Dict[str, str],
        base_url: str,
    ) -> StepResult:
        """Execute a single test step."""
        # Variable substitution
        selector = self._substitute_variables(step.selector, variables)
        value = self._substitute_variables(step.value, variables)
        
        # Prepend base URL for navigate actions
        if step.action == "navigate" and value and not value.startswith("http"):
            value = base_url.rstrip("/") + "/" + value.lstrip("/")
        
        # Start network capture if requested
        network_log = None
        if step.capture_network and self._inspector:
            await self._inspector.start()
        
        try:
            # Execute action
            action = PageAction(
                action=step.action,
                selector=selector,
                value=value,
                timeout=step.timeout,
            )
            
            result = await self._browser.execute_action(action)
            
            # Stop network capture
            if step.capture_network and self._inspector:
                network_log = await self._inspector.stop()
                self._inspector.clear()
            
            # Check assertion
            assertion_passed = None
            if step.assert_condition and result.success:
                assertion_passed = await self._check_assertion(
                    step.assert_condition,
                    step.assert_value,
                    result,
                    variables,
                )
                
                if not assertion_passed:
                    return StepResult(
                        step_name=step.name,
                        success=False,
                        output=result.output,
                        error=f"Assertion failed: {step.assert_condition}",
                        network_log=network_log,
                        assertion_passed=False,
                    )
            
            return StepResult(
                step_name=step.name,
                success=result.success,
                output=result.output,
                error=result.error,
                network_log=network_log,
                assertion_passed=assertion_passed,
            )
        
        except Exception as e:
            return StepResult(
                step_name=step.name,
                success=False,
                error=str(e),
                network_log=network_log,
            )
    
    async def _check_assertion(
        self,
        condition: str,
        expected: Optional[str],
        result: ActionResult,
        variables: Dict[str, str],
    ) -> bool:
        """Check an assertion condition."""
        expected = self._substitute_variables(expected, variables)
        
        if condition == "text_contains":
            return expected in result.output if expected else False
        
        elif condition == "text_equals":
            return result.output == expected
        
        elif condition == "element_visible":
            return result.success
        
        elif condition == "url_contains":
            url = self._browser.page.url
            return expected in url if expected else False
        
        elif condition == "response_ok":
            # Check if all captured requests succeeded
            if self._inspector:
                failed = self._inspector.get_failed_requests()
                return len(failed) == 0
            return True
        
        return True
    
    async def run_from_yaml(
        self, 
        path: Path,
        extra_variables: Optional[Dict[str, str]] = None,
    ) -> TestResult:
        """Load and run workflow from YAML file."""
        workflow = TestWorkflow.from_yaml(path)
        return await self.run(workflow, extra_variables)
