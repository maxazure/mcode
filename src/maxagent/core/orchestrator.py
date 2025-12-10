"""Agent Orchestrator for multi-agent task execution"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from maxagent.config import Config
from maxagent.llm import LLMClient, LLMConfig, Message
from maxagent.tools import ToolRegistry, create_default_registry

from .agent import Agent, AgentConfig, create_agent


@dataclass
class TaskResult:
    """Result of task execution"""
    
    success: bool
    output: str
    patches: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    summary: Optional[str] = None
    agent_outputs: dict[str, str] = field(default_factory=dict)


@dataclass
class OrchestratorConfig:
    """Orchestrator configuration"""
    
    enable_architect: bool = True
    enable_tester: bool = True
    max_retries: int = 3
    parallel_agents: bool = False  # Future: parallel execution


class Orchestrator:
    """
    Agent Orchestrator for coordinating multiple specialized agents.
    
    Workflow:
    1. Architect analyzes requirements and creates implementation plan
    2. Coder generates code based on the plan
    3. Tester creates tests for the code changes (optional)
    """
    
    def __init__(
        self,
        config: Config,
        project_root: Optional[Path] = None,
        orchestrator_config: Optional[OrchestratorConfig] = None,
        llm_client: Optional[LLMClient] = None,
        tool_registry: Optional[ToolRegistry] = None,
    ) -> None:
        self.config = config
        self.project_root = project_root or Path.cwd()
        self.orchestrator_config = orchestrator_config or OrchestratorConfig()
        
        # Create LLM client if not provided
        if llm_client is None:
            llm_config = LLMConfig(
                base_url=config.litellm.base_url,
                api_key=config.litellm.api_key,
                model=config.model.default,
                temperature=config.model.temperature,
                max_tokens=config.model.max_tokens,
            )
            self.llm = LLMClient(llm_config)
        else:
            self.llm = llm_client
            
        # Create tool registry if not provided
        if tool_registry is None:
            self.tools = create_default_registry(self.project_root)
        else:
            self.tools = tool_registry
            
        # Agent cache
        self._agents: dict[str, Agent] = {}
        
        # Progress callback
        self._progress_callback: Optional[Callable[[str, str], None]] = None
        
    def set_progress_callback(
        self, 
        callback: Callable[[str, str], None]
    ) -> None:
        """
        Set progress callback for status updates.
        
        Args:
            callback: Function(agent_name, status) called on progress
        """
        self._progress_callback = callback
        
    def _report_progress(self, agent_name: str, status: str) -> None:
        """Report progress through callback"""
        if self._progress_callback:
            self._progress_callback(agent_name, status)
            
    def _get_agent(self, agent_name: str) -> Agent:
        """Get or create an agent by name"""
        if agent_name not in self._agents:
            self._agents[agent_name] = create_agent(
                config=self.config,
                project_root=self.project_root,
                agent_name=agent_name,
                llm_client=self.llm,
                tool_registry=self.tools,
            )
        return self._agents[agent_name]
    
    async def execute_task(self, task: str) -> TaskResult:
        """
        Execute a complex task with multi-agent collaboration.
        
        Workflow:
        1. Architect: Analyze requirements, identify files, create plan
        2. Coder: Generate code patches based on plan
        3. Tester: Generate tests for the changes (if enabled)
        
        Args:
            task: Task description
            
        Returns:
            TaskResult with all outputs
        """
        agent_outputs: dict[str, str] = {}
        
        # Phase 1: Architecture analysis
        analysis = ""
        if self.orchestrator_config.enable_architect:
            self._report_progress("architect", "Analyzing requirements...")
            architect = self._get_agent("architect")
            
            analysis = await architect.run(f"""
Analyze the following task and create an implementation plan:

## Task
{task}

## Instructions
Please provide:
1. **Requirements Understanding**: What needs to be done
2. **Files Involved**: List files that need to be read or modified
3. **Implementation Steps**: Detailed step-by-step plan
4. **Potential Risks**: Things to watch out for
5. **Testing Strategy**: How to verify the changes work

Use the available tools to explore the project structure and understand the codebase first.
""")
            agent_outputs["architect"] = analysis
            
        # Phase 2: Code generation
        self._report_progress("coder", "Generating code...")
        coder = self._get_agent("coder")
        
        coder_prompt = f"""
Generate code changes for the following task:

## Original Task
{task}
"""
        if analysis:
            coder_prompt += f"""
## Architecture Analysis
{analysis}
"""
        coder_prompt += """
## Instructions
1. Read the relevant files first using the read_file tool
2. Generate all required code changes
3. Output each change as a unified diff format patch
4. Ensure the code follows project conventions
5. Add helpful comments where appropriate

Format your patches like this:
```diff
--- a/path/to/file.py
+++ b/path/to/file.py
@@ -10,6 +10,8 @@
 existing line
+new line
 existing line
```
"""
        code_result = await coder.run(coder_prompt)
        agent_outputs["coder"] = code_result
        
        # Extract patches from code result
        patches = self._extract_patches(code_result)
        
        # Phase 3: Test generation (optional)
        tests: list[str] = []
        if self.orchestrator_config.enable_tester and patches:
            self._report_progress("tester", "Generating tests...")
            tester = self._get_agent("tester")
            
            test_result = await tester.run(f"""
Generate tests for the following code changes:

## Task Description
{task}

## Code Changes
{code_result}

## Instructions
1. Create comprehensive test cases covering:
   - Normal/happy path scenarios
   - Edge cases and boundary conditions
   - Error handling
2. Use the project's testing framework (detect from existing tests)
3. Output tests as code that can be directly added to test files
4. Include both unit tests and integration tests where appropriate
""")
            agent_outputs["tester"] = test_result
            tests = self._extract_code_blocks(test_result, "python")
            
        self._report_progress("orchestrator", "Task completed")
        
        return TaskResult(
            success=True,
            output=code_result,
            patches=patches,
            tests=tests,
            summary=analysis if analysis else None,
            agent_outputs=agent_outputs,
        )
        
    async def execute_edit(
        self, 
        file_path: str, 
        instruction: str
    ) -> TaskResult:
        """
        Execute a file edit task.
        
        Args:
            file_path: Path to file to edit
            instruction: Edit instruction
            
        Returns:
            TaskResult with patches
        """
        self._report_progress("coder", f"Editing {file_path}...")
        coder = self._get_agent("coder")
        
        result = await coder.run(f"""
Edit the file at {file_path} according to these instructions:

## Instruction
{instruction}

## Steps
1. First, use read_file to read the current content of {file_path}
2. Understand the current code structure
3. Generate the required changes
4. Output a unified diff format patch

Important:
- Preserve the file's coding style and conventions
- Only change what's necessary for the task
- Add comments if the changes are complex
""")
        
        patches = self._extract_patches(result)
        
        return TaskResult(
            success=True,
            output=result,
            patches=patches,
            agent_outputs={"coder": result},
        )
        
    async def execute_chat(
        self,
        message: str,
        history: Optional[list[Message]] = None,
    ) -> str:
        """
        Execute a chat interaction.
        
        Args:
            message: User message
            history: Optional conversation history
            
        Returns:
            Assistant response
        """
        coder = self._get_agent("coder")
        
        if history:
            coder.messages = history.copy()
            
        return await coder.run(message)
    
    def _extract_patches(self, text: str) -> list[str]:
        """
        Extract unified diff patches from text.
        
        Supports both:
        - Code blocks with ```diff
        - Raw patches starting with --- 
        """
        patches: list[str] = []
        current_patch: list[str] = []
        in_patch = False
        in_diff_block = False
        
        lines = text.split("\n")
        
        for i, line in enumerate(lines):
            # Check for diff code block start
            if line.strip().startswith("```diff"):
                in_diff_block = True
                continue
                
            # Check for code block end
            if line.strip() == "```" and in_diff_block:
                if current_patch:
                    patches.append("\n".join(current_patch))
                    current_patch = []
                in_diff_block = False
                in_patch = False
                continue
                
            # Inside diff code block
            if in_diff_block:
                current_patch.append(line)
                continue
                
            # Check for raw patch start (--- a/path or --- path)
            if line.startswith("--- ") and not in_patch:
                # Save previous patch if exists
                if current_patch:
                    patches.append("\n".join(current_patch))
                    current_patch = []
                in_patch = True
                current_patch.append(line)
                continue
                
            # Continue raw patch
            if in_patch:
                # Patch ends with empty line or non-patch content
                if line.startswith(("diff ", "--- ", "+++ ", "@@ ", " ", "+", "-")):
                    current_patch.append(line)
                elif line.strip() == "":
                    # Empty line might be part of patch or end of patch
                    # Check next line to decide
                    if i + 1 < len(lines):
                        next_line = lines[i + 1]
                        if next_line.startswith(("+", "-", " ", "@@")):
                            current_patch.append(line)
                        else:
                            # End of patch
                            if current_patch:
                                patches.append("\n".join(current_patch))
                                current_patch = []
                            in_patch = False
                else:
                    # End of patch
                    if current_patch:
                        patches.append("\n".join(current_patch))
                        current_patch = []
                    in_patch = False
                    
        # Don't forget the last patch
        if current_patch:
            patches.append("\n".join(current_patch))
            
        return patches
    
    def _extract_code_blocks(
        self, 
        text: str, 
        language: str = ""
    ) -> list[str]:
        """
        Extract code blocks from text.
        
        Args:
            text: Text containing code blocks
            language: Optional language filter (e.g., "python")
            
        Returns:
            List of code block contents
        """
        blocks: list[str] = []
        current_block: list[str] = []
        in_block = False
        block_lang = ""
        
        for line in text.split("\n"):
            if line.strip().startswith("```"):
                if in_block:
                    # End of block
                    if not language or block_lang == language:
                        blocks.append("\n".join(current_block))
                    current_block = []
                    in_block = False
                    block_lang = ""
                else:
                    # Start of block
                    in_block = True
                    block_lang = line.strip()[3:].strip()
            elif in_block:
                current_block.append(line)
                
        return blocks
    
    async def close(self) -> None:
        """Close the orchestrator and cleanup resources"""
        await self.llm.close()


def create_orchestrator(
    config: Config,
    project_root: Optional[Path] = None,
    **kwargs,
) -> Orchestrator:
    """
    Factory function to create an orchestrator.
    
    Args:
        config: Application configuration
        project_root: Project root directory
        **kwargs: Additional arguments for Orchestrator
        
    Returns:
        Configured Orchestrator instance
    """
    return Orchestrator(
        config=config,
        project_root=project_root,
        **kwargs,
    )
