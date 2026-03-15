"""Runner for the Prompt Review Agent (LLM prompt quality gate).

Local demo (DummyLLMProvider):
    python scripts/run_prompt_review.py

Review prompts in a specific agent file:
    python scripts/run_prompt_review.py --file agent_sdlc/agents/issue_refinement.py

CI / production (requires ANTHROPIC_API_KEY):
    python scripts/run_prompt_review.py --file agent_sdlc/agents/pr_review.py

Exits 0 if no BLOCKER findings; exits 1 if any BLOCKERs exist.

Heuristic extraction
--------------------
The runner extracts prompt strings from Python source without executing it:
  1. Variables named ``prompt`` assigned a string literal or f-string.
  2. Calls to ``llm.ask_text(...)`` or ``self.llm.ask_text(...)`` with a
     string/f-string argument.
Extraction is best-effort; complex multi-line compositions may be partially
captured. Each extracted string is reviewed as a separate PromptReviewInput.
"""

from __future__ import annotations

import argparse
import ast
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

from agent_sdlc.agents.prompt_review import PromptReviewAgent, PromptReviewInput
from agent_sdlc.core.findings import FindingSeverity
from agent_sdlc.core.providers import DummyLLMProvider, ProviderProtocol

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s"
)
logger = logging.getLogger(__name__)

_SEVERITY_SYMBOL = {
    FindingSeverity.BLOCKER: "BLOCKER",
    FindingSeverity.WARNING: "WARNING",
    FindingSeverity.SUGGESTION: "SUGGESTION",
}


# ---------------------------------------------------------------------------
# Heuristic prompt extraction
# ---------------------------------------------------------------------------


def _node_to_str(node: ast.expr) -> str:
    """Return string content from a Constant or JoinedStr (f-string) node."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts: List[str] = []
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                parts.append(v.value)
            else:
                parts.append("{...}")
        return "".join(parts)
    return ""


def _is_ask_text_call(node: ast.Call) -> bool:
    """Return True if the call looks like llm.ask_text(...) or self.llm.ask_text(...)."""
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr == "ask_text":
        return True
    return False


def extract_prompts(source: str, filepath: str) -> List[Tuple[str, str]]:
    """Return list of (prompt_text, location) extracted from Python source.

    Locations are ``filepath:line``.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        logger.warning("Could not parse %s: %s", filepath, exc)
        return []

    results: List[Tuple[str, str]] = []

    for node in ast.walk(tree):
        # Assignment: prompt = "..." or prompt = f"..."
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "prompt":
                    text = _node_to_str(node.value)  # type: ignore[arg-type]
                    if text:
                        loc = f"{filepath}:{node.lineno}"
                        results.append((text, loc))

        # Call: llm.ask_text("...") or self.llm.ask_text(f"...")
        if isinstance(node, ast.Call) and _is_ask_text_call(node):
            if node.args:
                text = _node_to_str(node.args[0])
                if text:
                    loc = f"{filepath}:{node.lineno}"
                    results.append((text, loc))

    return results


# ---------------------------------------------------------------------------
# Heuristic checks (no LLM needed)
# ---------------------------------------------------------------------------


def _heuristic_check(prompt_text: str, location: str) -> List[str]:
    """Return list of warning strings for obvious issues detectable without LLM."""
    warnings: List[str] = []
    lower = prompt_text.lower()

    # format-unspecified: mentions json/array/list but no format instruction
    wants_structured = any(
        kw in lower
        for kw in ("json array", "json object", "return only", "return []", '["', '{"')
    )
    has_format_instruction = any(
        kw in lower
        for kw in (
            "return only",
            "no markdown",
            "no prose",
            "raw json",
            "json array",
            "json object",
        )
    )
    if wants_structured and not has_format_instruction:
        warnings.append(
            f"  [HEURISTIC] Prompt:format-unspecified @ {location}: "
            "Structured output expected but no explicit format instruction found."
        )

    # missing-fallback: says "return" + list but no empty-list fallback
    if "return" in lower and ("[" in prompt_text or "list" in lower):
        if "return []" not in prompt_text and "return [] if" not in prompt_text.lower():
            warnings.append(
                f"  [HEURISTIC] Prompt:missing-fallback @ {location}: "
                "No 'Return []' fallback instruction found for empty results."
            )

    return warnings


# ---------------------------------------------------------------------------
# Provider / result helpers
# ---------------------------------------------------------------------------


def _build_provider() -> ProviderProtocol:
    import os

    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            from agent_sdlc.core.anthropic_provider import AnthropicProvider

            return AnthropicProvider()
        except Exception as exc:
            logger.warning(
                "Could not load AnthropicProvider (%s) — using DummyLLMProvider.", exc
            )
    print("[INFO] No API key — using DummyLLMProvider", file=sys.stderr)
    return DummyLLMProvider(default="[]")


def _print_result(result: object, location: str) -> None:
    from agent_sdlc.agents.prompt_review import PromptReviewResult

    assert isinstance(result, PromptReviewResult)
    print(f"\n{'=' * 70}")
    print(
        f"Prompt Review — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} — {location}"
    )
    print(f"Status: {'APPROVED' if result.approved else 'BLOCKED'}")
    print(
        f"Findings: {result.blocker_count} blocker(s), {result.warning_count} warning(s), "
        f"{result.suggestion_count} suggestion(s)"
    )
    print("=" * 70)
    for f in result.findings:
        sym = _SEVERITY_SYMBOL[f.severity]
        print(f"[{sym}] {f.rule} @ {f.location}: {f.message}")
        if f.suggestion:
            print(f"     -> {f.suggestion}")
    if not result.findings:
        print("  No findings — prompt passes quality check.")
    print("=" * 70)


# ---------------------------------------------------------------------------
# Demo prompt used when no file is specified
# ---------------------------------------------------------------------------

_DEMO_PROMPT = (
    "You are a code reviewer.\n"
    "Review the following diff and return a raw JSON array of findings. "
    'Each element: {"location":"...","severity":"blocker|warning|suggestion",'
    '"rule":"code:<id>","message":"...","suggestion":"..."}.\n'
    "Return [] if no findings."
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the Prompt Review Agent on extracted prompts."
    )
    parser.add_argument(
        "--file",
        metavar="PATH",
        help="Python source file to extract and review prompts from.",
    )
    args = parser.parse_args()

    provider = _build_provider()
    agent = PromptReviewAgent(provider)
    any_blocker = False

    if args.file:
        path = Path(args.file)
        if not path.exists():
            logger.error("File not found: %s", args.file)
            return 1
        source = path.read_text(encoding="utf-8")
        prompts = extract_prompts(source, args.file)
        if not prompts:
            print(f"No prompts extracted from {args.file}.", file=sys.stderr)
            return 0

        for prompt_text, location in prompts:
            # Run heuristic checks first (no LLM)
            heuristic_warnings = _heuristic_check(prompt_text, location)
            for w in heuristic_warnings:
                print(w)

            inp = PromptReviewInput(prompt_text=prompt_text, source_location=location)
            result = agent.run(inp)
            _print_result(result, location)
            if not result.approved:
                any_blocker = True
    else:
        # Demo mode
        inp = PromptReviewInput(
            prompt_text=_DEMO_PROMPT,
            source_location="demo",
            expected_output_format="json",
            agent_name="demo",
        )
        result = agent.run(inp)
        _print_result(result, "demo")
        if not result.approved:
            any_blocker = True

    return 1 if any_blocker else 0


if __name__ == "__main__":
    sys.exit(main())
