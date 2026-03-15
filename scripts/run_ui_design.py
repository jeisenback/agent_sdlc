"""Runner for the UI Design Agent (visual consistency and accessibility review).

Local demo (DummyLLMProvider):
    python scripts/run_ui_design.py

Review a file:
    python scripts/run_ui_design.py --file src/components/Button.jsx --type jsx

CI / production (requires ANTHROPIC_API_KEY):
    python scripts/run_ui_design.py --file index.html --type html

Exits 0 if no BLOCKER findings; exits 1 if any BLOCKERs exist.

Heuristic checks (no LLM)
--------------------------
  UI:missing-alt-text  — detects <img> tags without an alt attribute
  UI:hardcoded-color   — detects literal hex/rgb/hsl values outside CSS variables
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

from agent_sdlc.agents.ui_design import UIDesignAgent, UIDesignInput
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

# Heuristic patterns
_IMG_NO_ALT_RE = re.compile(r"<img\b(?![^>]*\balt\s*=)[^>]*>", re.IGNORECASE)
_HARDCODED_COLOR_RE = re.compile(
    r"(?<!\w)(#[0-9a-fA-F]{3,8}|rgb\s*\(|rgba\s*\(|hsl\s*\(|hsla\s*\()",
    re.IGNORECASE,
)
# Exclude CSS variable declarations like --color-primary: #fff
_CSS_VAR_LINE_RE = re.compile(r"--[\w-]+\s*:")


def _heuristic_checks(source: str, filepath: str) -> List[Tuple[str, str]]:
    """Return list of (rule, message) for issues detectable without LLM."""
    issues: List[Tuple[str, str]] = []

    for line_no, line in enumerate(source.splitlines(), 1):
        loc = f"{filepath}:{line_no}"

        if _IMG_NO_ALT_RE.search(line):
            issues.append(
                (
                    "UI:missing-alt-text",
                    f"[HEURISTIC] {loc}: <img> with no alt attribute detected.",
                )
            )

        if _HARDCODED_COLOR_RE.search(line) and not _CSS_VAR_LINE_RE.search(line):
            issues.append(
                (
                    "UI:hardcoded-color",
                    f"[HEURISTIC] {loc}: hardcoded color value detected.",
                )
            )

    return issues


_EXTENSION_TO_TYPE = {
    ".html": "html",
    ".htm": "html",
    ".jsx": "jsx",
    ".tsx": "jsx",
    ".css": "css",
    ".scss": "css",
}

_DEMO_ARTIFACT = """\
<div style="color: #ff0000; width: 800px;">
  <img src="logo.png">
  <button onclick="submit()">Submit</button>
</div>
"""


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


def _print_result(result: object, label: str) -> None:
    from agent_sdlc.agents.ui_design import UIDesignResult

    assert isinstance(result, UIDesignResult)
    print("\n" + "=" * 70)
    print(f"{label} — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Status: {'APPROVED' if result.approved else 'NOT APPROVED'}")
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
        print("  No findings — artifact passes UI review.")
    print("=" * 70 + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the UI Design Agent on a UI source file."
    )
    parser.add_argument("--file", metavar="PATH", help="UI source file to review")
    parser.add_argument(
        "--type",
        dest="artifact_type",
        choices=["html", "jsx", "css", "design_spec", "other"],
        default=None,
        help="Artifact type (inferred from extension if not set)",
    )
    parser.add_argument("--component", default=None, help="Component name")
    parser.add_argument("--design-system", default=None, help="Design system name")
    args = parser.parse_args()

    if args.file:
        path = Path(args.file)
        if not path.exists():
            logger.error("File not found: %s", args.file)
            return 1
        source = path.read_text(encoding="utf-8")
        artifact_type = args.artifact_type or _EXTENSION_TO_TYPE.get(
            path.suffix.lower(), "other"
        )
        label = f"UI Review — {path.name}"

        # Run heuristic checks first
        for rule, msg in _heuristic_checks(source, args.file):
            print(f"  [{rule}] {msg}")
    else:
        source = _DEMO_ARTIFACT
        artifact_type = "html"
        label = "UI Review — Demo"
        for rule, msg in _heuristic_checks(source, "demo"):
            print(f"  [{rule}] {msg}")

    provider = _build_provider()
    agent = UIDesignAgent(provider)
    inp = UIDesignInput(
        artifact=source,
        artifact_type=artifact_type,  # type: ignore[arg-type]
        component_name=args.component,
        design_system=args.design_system,
    )
    result = agent.run(inp)
    _print_result(result, label)

    return 0 if result.approved else 1


if __name__ == "__main__":
    sys.exit(main())
