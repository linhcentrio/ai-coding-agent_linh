"""
Workflow Engine
================
Load and execute workflows from YAML configuration.
"""

import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .async_executor import (
    AsyncOrchestrator,
    AgentRole,
    ExecutionMode,
    ExecutionResult,
    WorkflowResult,
)
from ..providers.base import BaseProvider


@dataclass
class WorkflowStep:
    """Single step in a workflow."""
    agent: str
    role: str
    prompt_template: str = "{task}"
    timeout: int = 300
    optional: bool = False
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowStep":
        return cls(
            agent=data.get("agent", ""),
            role=data.get("role", data.get("task", "")),
            prompt_template=data.get("prompt_template", "{task}"),
            timeout=data.get("timeout", 300),
            optional=data.get("optional", False),
        )


@dataclass
class StopCondition:
    """Condition to stop workflow execution."""
    type: str  # "keyword", "no_suggestions", "max_iterations", "approval"
    value: Any = None
    agent: Optional[str] = None
    
    def check(self, result: ExecutionResult) -> bool:
        """Check if stop condition is met."""
        if self.type == "keyword":
            return self.value.lower() in result.content.lower()
        elif self.type == "no_suggestions":
            # Count suggestion indicators
            indicators = ["should", "could", "recommend", "suggest", "consider"]
            count = sum(1 for ind in indicators if ind in result.content.lower())
            return count < (self.value or 2)
        elif self.type == "approval":
            return "approved" in result.content.lower() or "lgtm" in result.content.lower()
        elif self.type == "max_iterations":
            return result.iteration >= (self.value or 10)
        return False
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StopCondition":
        return cls(
            type=data.get("type", ""),
            value=data.get("value") or data.get("threshold") or data.get("keyword"),
            agent=data.get("agent"),
        )


@dataclass 
class WorkflowConfig:
    """Complete workflow configuration."""
    name: str
    description: str = ""
    mode: ExecutionMode = ExecutionMode.SEQUENTIAL
    steps: List[WorkflowStep] = field(default_factory=list)
    stop_conditions: List[StopCondition] = field(default_factory=list)
    max_rounds: int = 3
    merge_strategy: str = "combine"
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowConfig":
        mode_str = data.get("mode", "sequential").lower()
        mode = ExecutionMode(mode_str) if mode_str in [m.value for m in ExecutionMode] else ExecutionMode.SEQUENTIAL
        
        steps = [WorkflowStep.from_dict(s) for s in data.get("steps", data.get("agents", []))]
        conditions = [StopCondition.from_dict(c) for c in data.get("stop_conditions", [])]
        
        return cls(
            name=data.get("name", "unnamed"),
            description=data.get("description", ""),
            mode=mode,
            steps=steps,
            stop_conditions=conditions,
            max_rounds=data.get("max_rounds", 3),
            merge_strategy=data.get("merge_strategy", "combine"),
        )


class WorkflowEngine:
    """
    Engine for loading and executing workflows.
    
    Loads workflow definitions from YAML and executes them
    using the AsyncOrchestrator.
    """
    
    def __init__(self, providers: Dict[str, BaseProvider]):
        """
        Initialize workflow engine.
        
        Args:
            providers: Dict mapping provider names to instances
        """
        self.providers = providers
        self.workflows: Dict[str, WorkflowConfig] = {}
    
    def load_workflow(self, path: Path) -> WorkflowConfig:
        """Load workflow from YAML file."""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        
        config = WorkflowConfig.from_dict(data)
        self.workflows[config.name] = config
        return config
    
    def load_workflows_dir(self, directory: Path):
        """Load all workflows from a directory."""
        for yaml_file in directory.glob("*.yaml"):
            try:
                self.load_workflow(yaml_file)
            except Exception as e:
                print(f"Failed to load {yaml_file}: {e}")
        
        for yml_file in directory.glob("*.yml"):
            try:
                self.load_workflow(yml_file)
            except Exception as e:
                print(f"Failed to load {yml_file}: {e}")
    
    def get_workflow(self, name: str) -> Optional[WorkflowConfig]:
        """Get workflow by name."""
        return self.workflows.get(name)
    
    def list_workflows(self) -> List[str]:
        """List all loaded workflow names."""
        return list(self.workflows.keys())
    
    def _build_agent_roles(self, workflow: WorkflowConfig) -> Dict[str, AgentRole]:
        """Build AgentRole objects from workflow steps."""
        roles = {}
        
        for i, step in enumerate(workflow.steps):
            # Find provider for this agent
            provider = self.providers.get(step.agent)
            if not provider:
                # Try to match by name pattern
                for pname, prov in self.providers.items():
                    if step.agent.lower() in pname.lower():
                        provider = prov
                        break
            
            if not provider:
                continue
            
            # Determine next agent for continuous mode
            next_agent = None
            if i < len(workflow.steps) - 1:
                next_agent = workflow.steps[i + 1].agent
            elif workflow.mode == ExecutionMode.CONTINUOUS:
                next_agent = workflow.steps[0].agent  # Loop back
            
            roles[step.agent] = AgentRole(
                name=step.agent,
                provider=provider,
                role=step.role,
                prompt_template=step.prompt_template,
                next_agent=next_agent,
            )
        
        return roles
    
    async def execute(
        self,
        workflow_name: str,
        task: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> WorkflowResult:
        """
        Execute a workflow by name.
        
        Args:
            workflow_name: Name of the workflow to execute
            task: Task description
            context: Optional additional context
        
        Returns:
            WorkflowResult with execution results
        """
        workflow = self.get_workflow(workflow_name)
        if not workflow:
            return WorkflowResult(
                success=False,
                final_output=f"Workflow not found: {workflow_name}"
            )
        
        return await self.execute_workflow(workflow, task, context)
    
    async def execute_workflow(
        self,
        workflow: WorkflowConfig,
        task: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> WorkflowResult:
        """
        Execute a workflow configuration.
        
        Args:
            workflow: WorkflowConfig object
            task: Task description
            context: Optional additional context
        
        Returns:
            WorkflowResult with execution results
        """
        # Build agent roles
        roles = self._build_agent_roles(workflow)
        
        if not roles:
            return WorkflowResult(
                success=False,
                final_output="No valid agents found for workflow"
            )
        
        # Create orchestrator
        orchestrator = AsyncOrchestrator(agents=roles)
        
        # Build stop condition checker
        def check_stop(result: ExecutionResult) -> bool:
            return any(cond.check(result) for cond in workflow.stop_conditions)
        
        try:
            # Execute based on mode
            if workflow.mode == ExecutionMode.SEQUENTIAL:
                agent_order = [step.agent for step in workflow.steps]
                return await orchestrator.execute_sequential(task, agent_order, context)
            
            elif workflow.mode == ExecutionMode.PARALLEL:
                agent_names = [step.agent for step in workflow.steps]
                return await orchestrator.execute_parallel(
                    task, agent_names, workflow.merge_strategy
                )
            
            elif workflow.mode == ExecutionMode.ROUND_ROBIN:
                agent_order = [step.agent for step in workflow.steps]
                return await orchestrator.execute_round_robin(
                    task, agent_order, workflow.max_rounds,
                    stop_condition=check_stop if workflow.stop_conditions else None
                )
            
            elif workflow.mode == ExecutionMode.CONTINUOUS:
                return await orchestrator.execute_continuous(
                    task, stop_condition=check_stop
                )
            
            else:
                return WorkflowResult(
                    success=False,
                    final_output=f"Unknown execution mode: {workflow.mode}"
                )
        
        finally:
            orchestrator.shutdown()
