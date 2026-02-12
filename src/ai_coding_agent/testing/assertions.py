"""
Test Assertions
================
Assertion helpers for browser testing.
"""

import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from .network_inspector import NetworkRequest, NetworkLog


@dataclass
class AssertionResult:
    """Result of an assertion."""
    passed: bool
    assertion_type: str
    expected: Any
    actual: Any
    message: str = ""


class Assertions:
    """
    Collection of assertion helpers for browser testing.
    
    Provides fluent API for common test assertions.
    """
    
    def __init__(self):
        self.results: List[AssertionResult] = []
    
    def _add_result(self, result: AssertionResult):
        """Add assertion result."""
        self.results.append(result)
        return result
    
    def all_passed(self) -> bool:
        """Check if all assertions passed."""
        return all(r.passed for r in self.results)
    
    def get_failures(self) -> List[AssertionResult]:
        """Get failed assertions."""
        return [r for r in self.results if not r.passed]
    
    def clear(self):
        """Clear assertion results."""
        self.results.clear()
    
    # Text assertions
    
    def text_equals(self, actual: str, expected: str, message: str = "") -> AssertionResult:
        """Assert text equals expected."""
        passed = actual == expected
        return self._add_result(AssertionResult(
            passed=passed,
            assertion_type="text_equals",
            expected=expected,
            actual=actual,
            message=message or f"Expected '{expected}', got '{actual}'"
        ))
    
    def text_contains(self, actual: str, substring: str, message: str = "") -> AssertionResult:
        """Assert text contains substring."""
        passed = substring in actual
        return self._add_result(AssertionResult(
            passed=passed,
            assertion_type="text_contains",
            expected=substring,
            actual=actual,
            message=message or f"Expected '{substring}' in text"
        ))
    
    def text_matches(self, actual: str, pattern: str, message: str = "") -> AssertionResult:
        """Assert text matches regex pattern."""
        passed = bool(re.search(pattern, actual))
        return self._add_result(AssertionResult(
            passed=passed,
            assertion_type="text_matches",
            expected=pattern,
            actual=actual,
            message=message or f"Expected text to match '{pattern}'"
        ))
    
    # Status assertions
    
    def status_ok(self, status: int, message: str = "") -> AssertionResult:
        """Assert HTTP status is 2xx."""
        passed = 200 <= status < 300
        return self._add_result(AssertionResult(
            passed=passed,
            assertion_type="status_ok",
            expected="2xx",
            actual=status,
            message=message or f"Expected 2xx status, got {status}"
        ))
    
    def status_equals(self, actual: int, expected: int, message: str = "") -> AssertionResult:
        """Assert HTTP status equals expected."""
        passed = actual == expected
        return self._add_result(AssertionResult(
            passed=passed,
            assertion_type="status_equals",
            expected=expected,
            actual=actual,
            message=message or f"Expected status {expected}, got {actual}"
        ))
    
    # Network assertions
    
    def request_made(
        self, 
        log: NetworkLog, 
        url_pattern: str,
        method: Optional[str] = None,
        message: str = "",
    ) -> AssertionResult:
        """Assert a request was made matching pattern."""
        matches = [r for r in log.requests if url_pattern in r.url]
        if method:
            matches = [r for r in matches if r.method == method]
        
        passed = len(matches) > 0
        return self._add_result(AssertionResult(
            passed=passed,
            assertion_type="request_made",
            expected=f"{method or 'ANY'} {url_pattern}",
            actual=f"{len(matches)} requests found",
            message=message or f"Expected request to {url_pattern}"
        ))
    
    def no_failed_requests(self, log: NetworkLog, message: str = "") -> AssertionResult:
        """Assert no requests failed."""
        failures = log.filter_errors()
        passed = len(failures) == 0
        
        actual = [f"{r.method} {r.url}: {r.status or r.error}" for r in failures[:3]]
        
        return self._add_result(AssertionResult(
            passed=passed,
            assertion_type="no_failed_requests",
            expected="0 failures",
            actual=f"{len(failures)} failures: {actual}",
            message=message or "Expected no failed requests"
        ))
    
    def response_contains(
        self,
        log: NetworkLog,
        url_pattern: str,
        content: str,
        message: str = "",
    ) -> AssertionResult:
        """Assert response body contains content."""
        matches = [r for r in log.requests if url_pattern in r.url and r.response_body]
        
        found = False
        for req in matches:
            if req.response_body and content in req.response_body:
                found = True
                break
        
        return self._add_result(AssertionResult(
            passed=found,
            assertion_type="response_contains",
            expected=f"'{content}' in response",
            actual=f"Found in {len([m for m in matches if m.response_body and content in m.response_body])}/{len(matches)} responses",
            message=message or f"Expected response to contain '{content}'"
        ))
    
    # Element assertions
    
    def element_exists(self, exists: bool, selector: str, message: str = "") -> AssertionResult:
        """Assert element exists."""
        return self._add_result(AssertionResult(
            passed=exists,
            assertion_type="element_exists",
            expected=True,
            actual=exists,
            message=message or f"Expected element '{selector}' to exist"
        ))
    
    def element_count(
        self,
        actual_count: int,
        expected_count: int,
        selector: str,
        message: str = "",
    ) -> AssertionResult:
        """Assert element count."""
        passed = actual_count == expected_count
        return self._add_result(AssertionResult(
            passed=passed,
            assertion_type="element_count",
            expected=expected_count,
            actual=actual_count,
            message=message or f"Expected {expected_count} elements matching '{selector}'"
        ))
    
    # Value assertions
    
    def is_true(self, value: bool, message: str = "") -> AssertionResult:
        """Assert value is true."""
        return self._add_result(AssertionResult(
            passed=value is True,
            assertion_type="is_true",
            expected=True,
            actual=value,
            message=message
        ))
    
    def is_false(self, value: bool, message: str = "") -> AssertionResult:
        """Assert value is false."""
        return self._add_result(AssertionResult(
            passed=value is False,
            assertion_type="is_false",
            expected=False,
            actual=value,
            message=message
        ))
    
    def equals(self, actual: Any, expected: Any, message: str = "") -> AssertionResult:
        """Assert values are equal."""
        passed = actual == expected
        return self._add_result(AssertionResult(
            passed=passed,
            assertion_type="equals",
            expected=expected,
            actual=actual,
            message=message or f"Expected {expected}, got {actual}"
        ))


def assert_api_response(
    request: NetworkRequest,
    status: Optional[int] = None,
    contains: Optional[str] = None,
    json_path: Optional[str] = None,
    json_value: Optional[Any] = None,
) -> AssertionResult:
    """
    Assert API response meets criteria.
    
    Args:
        request: NetworkRequest to check
        status: Expected status code
        contains: String that should be in response body
        json_path: JSONPath to check (simple dot notation)
        json_value: Expected value at json_path
    
    Returns:
        AssertionResult
    """
    # Check status
    if status is not None:
        if request.status != status:
            return AssertionResult(
                passed=False,
                assertion_type="api_status",
                expected=status,
                actual=request.status,
                message=f"Expected status {status}, got {request.status}"
            )
    
    # Check contains
    if contains is not None:
        if not request.response_body or contains not in request.response_body:
            return AssertionResult(
                passed=False,
                assertion_type="api_contains",
                expected=contains,
                actual=request.response_body[:100] if request.response_body else None,
                message=f"Expected response to contain '{contains}'"
            )
    
    # Check JSON path
    if json_path is not None and json_value is not None:
        import json
        try:
            body = json.loads(request.response_body or "{}")
            
            # Simple dot notation navigation
            parts = json_path.split(".")
            value = body
            for part in parts:
                if isinstance(value, dict):
                    value = value.get(part)
                elif isinstance(value, list) and part.isdigit():
                    value = value[int(part)]
                else:
                    value = None
                    break
            
            if value != json_value:
                return AssertionResult(
                    passed=False,
                    assertion_type="api_json",
                    expected=f"{json_path} = {json_value}",
                    actual=f"{json_path} = {value}",
                    message=f"Expected {json_path} to be {json_value}"
                )
        except json.JSONDecodeError:
            return AssertionResult(
                passed=False,
                assertion_type="api_json",
                expected="valid JSON",
                actual="invalid JSON",
                message="Response is not valid JSON"
            )
    
    return AssertionResult(
        passed=True,
        assertion_type="api_response",
        expected="all checks passed",
        actual="all checks passed"
    )
