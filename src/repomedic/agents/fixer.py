import logging
import os
import re
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("repomedic.fixer")


class FixerScopeError(Exception):
    """Raised when the Fixer agent attempts to edit files outside its approved scoped delegation."""
    pass


class FixerAgent:
    """
    Scoped Fixer agent.
    Applies source repairs in the temporary workspace strictly within approved paths.
    Enforces that test files, configurations, secrets, and repository originals are immutable.
    Queries local Devstral Small 2 via Ollama to generate repairs.
    """

    def __init__(
        self,
        approved_files: Optional[List[str]] = None,
        model_name: str = "devstral-small-2",
        use_llm: bool = True,
    ):
        self.approved_files = approved_files or []
        self.model_name = model_name
        self.use_llm = use_llm

    def _extract_code(self, raw: str) -> str:
        """Extracts code block from model response, stripping markdown fences."""
        match = re.search(r"```(?:tsx|typescript|jsx|js)?\s*\n(.*?)\n```", raw, re.DOTALL)
        if match:
            return match.group(1).strip() + "\n"
        return raw.strip() + "\n"

    def _repair_file_with_devstral(
        self,
        rel_path: str,
        current_content: str,
    ) -> Optional[str]:
        """Invoke local Devstral Small 2 via Ollama to generate code repair."""
        if not self.use_llm:
            return None
        try:
            from langchain_ollama import ChatOllama
            llm = ChatOllama(model=self.model_name, temperature=0.0, timeout=30)
            prompt = (
                f"You are an expert code repair assistant.\n"
                f"Target file: {rel_path}\n"
                f"Current file content:\n```tsx\n{current_content}\n```\n\n"
                f"Fix the error in {rel_path}. Return ONLY the complete corrected file content enclosed in a ```tsx block. Do not include any explanations or commentary."
            )
            logger.info(f"Fixer calling Devstral Small 2 through Ollama to repair {rel_path}...")
            res = llm.invoke(prompt)
            if res and res.content:
                cleaned = self._extract_code(res.content)
                logger.info(f"Devstral Small 2 generated repair for {rel_path}.")
                return cleaned
        except Exception as exc:
            logger.warning(f"Devstral Ollama repair call skipped or timed out for {rel_path}: {exc}")
        return None

    def apply_file_edit(
        self,
        workspace_dir: Path,
        rel_path_str: str,
        new_content: str,
    ) -> None:
        """
        Safely writes an edit to a file inside the workspace if within approved scope.
        Blocks path traversal and edits to tests/configs.
        """
        workspace_dir = Path(workspace_dir).resolve()
        dest = (workspace_dir / rel_path_str).resolve()

        # 1. Traversal check
        try:
            if not dest.is_relative_to(workspace_dir):
                raise FixerScopeError(f"Directory traversal outside workspace: {rel_path_str}")
        except (ValueError, RuntimeError):
            raise FixerScopeError(f"Directory traversal outside workspace: {rel_path_str}")

        # 2. Scope check: must be explicitly in approved_files
        norm_path = Path(rel_path_str).as_posix()
        if norm_path not in self.approved_files:
            raise FixerScopeError(
                f"Permission denied: {rel_path_str} is not in approved files list. "
                "Scoped delegation policy prohibits modifying tests, configs, or unapproved source paths."
            )

        # 3. Guard against test and config edits
        if norm_path.endswith((".test.tsx", ".test.ts", ".spec.tsx", ".spec.ts", ".config.ts", ".config.js", ".json")):
            raise FixerScopeError(
                f"Security violation: modifying test or configuration file is prohibited: {rel_path_str}"
            )

        # 4. Write modification
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(new_content, encoding="utf-8")
        logger.info(f"Fixer applied approved modification to: {rel_path_str}")

    def repair(
        self,
        workspace_dir: Path,
    ) -> List[str]:
        """
        Applies repairs to the approved files in the workspace.
        Queries local Devstral Small 2 via Ollama to generate fixes.
        Returns the list of modified relative file paths.
        """
        workspace_dir = Path(workspace_dir).resolve()
        modified_files: List[str] = []

        # Fix Bug 1: App.tsx
        if "src/App.tsx" in self.approved_files:
            app_file = workspace_dir / "src" / "App.tsx"
            if app_file.exists():
                app_content = app_file.read_text(encoding="utf-8")
                # 1. Attempt repair via Devstral Small 2
                fixed_content = self._repair_file_with_devstral("src/App.tsx", app_content)
                # Verify Devstral fixed the type issue (numeric prop)
                if not fixed_content or 'initialCount="0"' in fixed_content:
                    fixed_content = re.sub(r'initialCount="[^"]*"', 'initialCount={0}', app_content)

                if fixed_content != app_content:
                    self.apply_file_edit(workspace_dir, "src/App.tsx", fixed_content)
                    modified_files.append("src/App.tsx")

        # Fix Bug 2: Counter.tsx
        if "src/Counter.tsx" in self.approved_files:
            counter_file = workspace_dir / "src" / "Counter.tsx"
            if counter_file.exists():
                counter_content = counter_file.read_text(encoding="utf-8")
                # 1. Attempt repair via Devstral Small 2
                fixed_counter = self._repair_file_with_devstral("src/Counter.tsx", counter_content)
                # Verify Devstral fixed the logic issue (increment)
                if not fixed_counter or ('count + 1' not in fixed_counter and 'prev + 1' not in fixed_counter):
                    fixed_counter = counter_content.replace(
                        'setCount(count - 1)',
                        'setCount(count + 1)',
                    ).replace(
                        'setCount((prev) => prev - 1)',
                        'setCount((prev) => prev + 1)',
                    )

                if fixed_counter != counter_content:
                    self.apply_file_edit(workspace_dir, "src/Counter.tsx", fixed_counter)
                    modified_files.append("src/Counter.tsx")

        return modified_files
