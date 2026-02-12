"""
Async Executor
===============
Execute agents in parallel, sequential, or round-robin modes.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TypeVar, Awaitable

from ..providers.base import BaseProvider, Message, CompletionResponse


T = TypeVar("T")


class ExecutionMode(Enum):
    """Workflow execution modes."""
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    ROUND_ROBIN = "round_robin"
    CONTINUOUS = "continuous"


@dataclass
class AgentRole:
    """Agent role configuration."""
    name: str
    provider: BaseProvider
    role: str  # "implement", "review", "refine"
    prompt_template: str = "{task}"
    next_agent: Optional[str] = None  # For continuous mode


@dataclass
class ExecutionResult:
    """Result from agent execution."""
    agent_name: str
    role: str
    success: bool
    content: str
    error: Optional[str] = None
    iteration: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowResult:
    """Result from workflow execution."""
    success: bool
    results: List[ExecutionResult] = field(default_factory=list)
    final_output: str = ""
    total_iterations: int = 0


class AsyncOrchestrator:
    """
    Orchestrate multiple AI agents with different execution modes.
    
    Supports:
    - Sequential: Agents run one after another
    - Parallel: All agents run simultaneously
    - Round-Robin: Agents take turns refining
    - Continuous: Pipeline with task queue
    """
    
    def __init__(
        self,
        agents: Dict[str, AgentRole],
        max_workers: int = 3,
        max_iterations: int = 10,
    ):
        self.agents = agents
        self.max_workers = max_workers
        self.max_iterations = max_iterations
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        
        # Queues for continuous mode
        self.task_queue: asyncio.Queue = asyncio.Queue()
        self.result_queue: asyncio.Queue = asyncio.Queue()
    
    async def execute_sequential(
        self,
        task: str,
        agent_order: List[str],
        context: Optional[Dict[str, Any]] = None,
    ) -> WorkflowResult:
        """
        Execute agents sequentially, passing output to next agent.
        
        Args:
            task: Initial task description
            agent_order: List of agent names in execution order
            context: Optional shared context
        
        Returns:
            WorkflowResult with all outputs
        """
        results = []
        current_input = task
        ctx = context or {}
        
        for i, agent_name in enumerate(agent_order):
            if agent_name not in self.agents:
                results.append(ExecutionResult(
                    agent_name=agent_name,
                    role="unknown",
                    success=False,
                    content="",
                    error=f"Agent not found: {agent_name}"
                ))
                continue
            
            agent = self.agents[agent_name]
            
            # Build prompt from template
            prompt = agent.prompt_template.format(
                task=current_input,
                previous_output=ctx.get("previous_output", ""),
                **ctx
            )
            
            try:
                response = await agent.provider.complete([
                    Message(role="user", content=prompt)
                ])
                
                results.append(ExecutionResult(
                    agent_name=agent_name,
                    role=agent.role,
                    success=True,
                    content=response.content,
                    iteration=i
                ))
                
                # Update context for next agent
                current_input = response.content
                ctx["previous_output"] = response.content
                
            except Exception as e:
                results.append(ExecutionResult(
                    agent_name=agent_name,
                    role=agent.role,
                    success=False,
                    content="",
                    error=str(e)
                ))
                break
        
        return WorkflowResult(
            success=all(r.success for r in results),
            results=results,
            final_output=results[-1].content if results and results[-1].success else "",
            total_iterations=len(results)
        )
    
    async def execute_parallel(
        self,
        task: str,
        agent_names: List[str],
        merge_strategy: str = "combine",  # "combine", "vote", "best"
    ) -> WorkflowResult:
        """
        Execute multiple agents in parallel on the same task.
        
        Args:
            task: Task for all agents
            agent_names: List of agents to run
            merge_strategy: How to combine results
        
        Returns:
            WorkflowResult with merged output
        """
        async def run_agent(name: str) -> ExecutionResult:
            if name not in self.agents:
                return ExecutionResult(
                    agent_name=name,
                    role="unknown",
                    success=False,
                    content="",
                    error=f"Agent not found: {name}"
                )
            
            agent = self.agents[name]
            prompt = agent.prompt_template.format(task=task)
            
            try:
                response = await agent.provider.complete([
                    Message(role="user", content=prompt)
                ])
                return ExecutionResult(
                    agent_name=name,
                    role=agent.role,
                    success=True,
                    content=response.content
                )
            except Exception as e:
                return ExecutionResult(
                    agent_name=name,
                    role=agent.role,
                    success=False,
                    content="",
                    error=str(e)
                )
        
        # Run all agents in parallel
        tasks = [run_agent(name) for name in agent_names]
        results = await asyncio.gather(*tasks)
        
        # Merge results
        successful = [r for r in results if r.success]
        
        if merge_strategy == "combine":
            merged = "\n\n---\n\n".join([
                f"**{r.agent_name} ({r.role}):**\n{r.content}"
                for r in successful
            ])
        elif merge_strategy == "best":
            # Use longest response as "best"
            merged = max(successful, key=lambda r: len(r.content)).content if successful else ""
        else:
            merged = successful[0].content if successful else ""
        
        return WorkflowResult(
            success=len(successful) > 0,
            results=list(results),
            final_output=merged,
            total_iterations=1
        )
    
    async def execute_round_robin(
        self,
        task: str,
        agent_order: List[str],
        max_rounds: int = 3,
        stop_condition: Optional[Callable[[ExecutionResult], bool]] = None,
    ) -> WorkflowResult:
        """
        Execute agents in round-robin fashion until completion.
        
        Args:
            task: Initial task
            agent_order: Order of agents per round
            max_rounds: Maximum number of complete rounds
            stop_condition: Optional function to check if should stop
        
        Returns:
            WorkflowResult with all iterations
        """
        results = []
        current_input = task
        history = []
        
        for round_num in range(max_rounds):
            for agent_name in agent_order:
                if agent_name not in self.agents:
                    continue
                
                agent = self.agents[agent_name]
                
                # Build context with history
                history_text = "\n".join([
                    f"[{h['agent']}]: {h['output'][:200]}..."
                    for h in history[-3:]  # Last 3 interactions
                ])
                
                prompt = agent.prompt_template.format(
                    task=task,
                    current_state=current_input,
                    history=history_text,
                    round=round_num + 1
                )
                
                try:
                    response = await agent.provider.complete([
                        Message(role="user", content=prompt)
                    ])
                    
                    result = ExecutionResult(
                        agent_name=agent_name,
                        role=agent.role,
                        success=True,
                        content=response.content,
                        iteration=len(results)
                    )
                    results.append(result)
                    
                    current_input = response.content
                    history.append({
                        "agent": agent_name,
                        "role": agent.role,
                        "output": response.content
                    })
                    
                    # Check stop condition
                    if stop_condition and stop_condition(result):
                        return WorkflowResult(
                            success=True,
                            results=results,
                            final_output=response.content,
                            total_iterations=len(results)
                        )
                    
                except Exception as e:
                    results.append(ExecutionResult(
                        agent_name=agent_name,
                        role=agent.role,
                        success=False,
                        content="",
                        error=str(e)
                    ))
        
        return WorkflowResult(
            success=any(r.success for r in results),
            results=results,
            final_output=current_input,
            total_iterations=len(results)
        )
    
    async def execute_continuous(
        self,
        initial_task: str,
        stop_condition: Callable[[ExecutionResult], bool],
        timeout: float = 300,
    ) -> WorkflowResult:
        """
        Execute agents continuously in a pipeline.
        
        Each agent passes its output to the next agent (based on next_agent config).
        Continues until stop_condition is met or timeout.
        
        Args:
            initial_task: Starting task
            stop_condition: Function to determine when to stop
            timeout: Maximum execution time in seconds
        
        Returns:
            WorkflowResult with all iterations
        """
        results = []
        
        # Find first agent (one with role "implement" or first in list)
        first_agent = None
        for name, agent in self.agents.items():
            if agent.role == "implement":
                first_agent = name
                break
        if not first_agent:
            first_agent = list(self.agents.keys())[0]
        
        # Start with initial task
        await self.task_queue.put({
            "task": initial_task,
            "target_agent": first_agent,
            "iteration": 0
        })
        
        async def process_queue():
            while True:
                try:
                    item = await asyncio.wait_for(
                        self.task_queue.get(),
                        timeout=5.0
                    )
                except asyncio.TimeoutError:
                    if self.task_queue.empty():
                        break
                    continue
                
                agent_name = item["target_agent"]
                if agent_name not in self.agents:
                    continue
                
                agent = self.agents[agent_name]
                prompt = agent.prompt_template.format(
                    task=item["task"],
                    iteration=item["iteration"]
                )
                
                try:
                    response = await agent.provider.complete([
                        Message(role="user", content=prompt)
                    ])
                    
                    result = ExecutionResult(
                        agent_name=agent_name,
                        role=agent.role,
                        success=True,
                        content=response.content,
                        iteration=item["iteration"]
                    )
                    results.append(result)
                    
                    # Check stop condition
                    if stop_condition(result):
                        return
                    
                    # Queue next agent
                    if agent.next_agent and item["iteration"] < self.max_iterations:
                        await self.task_queue.put({
                            "task": response.content,
                            "target_agent": agent.next_agent,
                            "iteration": item["iteration"] + 1
                        })
                    
                except Exception as e:
                    results.append(ExecutionResult(
                        agent_name=agent_name,
                        role=agent.role,
                        success=False,
                        content="",
                        error=str(e)
                    ))
        
        try:
            await asyncio.wait_for(process_queue(), timeout=timeout)
        except asyncio.TimeoutError:
            pass
        
        return WorkflowResult(
            success=any(r.success for r in results),
            results=results,
            final_output=results[-1].content if results and results[-1].success else "",
            total_iterations=len(results)
        )
    
    def shutdown(self):
        """Shutdown executor."""
        self.executor.shutdown(wait=True)
