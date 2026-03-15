"""Runner for the UX Agent (user flow friction and usability review).

Local demo (DummyLLMProvider):
    python scripts/run_ux.py

Review a flow from a file:
    python scripts/run_ux.py --flow-file docs/flows/checkout.md \\
        --goal "Complete a purchase" --user-type "mobile user"

CI / production (requires ANTHROPIC_API_KEY):
    python scripts/run_ux.py --flow-file specs/onboarding.md \\
        --goal "Sign up and complete onboarding"

Exits 0 if no BLOCKER findings; exits 1 if any BLOCKERs exist.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from agent_sdlc.agents.ux import UXAgent, UXInput
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

_DEMO_FLOW = """\
1. User clicks "Buy Now" on the product page.
2. User fills in shipping address form and clicks "Submit".
3. Payment is processed.
4. Order is placed.
"""

_DEMO_GOAL = "Purchase a product and receive an order confirmation"


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
    from agent_sdlc.agents.ux import UXResult

    assert isinstance(result, UXResult)
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
        print("  No findings — flow passes UX review.")
    print("=" * 70 + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the UX Agent on a user flow description."
    )
    parser.add_argument(
        "--flow-file", metavar="PATH", help="Path to flow description file"
    )
    parser.add_argument("--goal", default=_DEMO_GOAL, help="User goal for this flow")
    parser.add_argument(
        "--user-type", default=None, help="User type (e.g. 'mobile user')"
    )
    parser.add_argument(
        "--flow-context", default=None, help="Flow context (e.g. 'checkout')"
    )
    args = parser.parse_args()

    if args.flow_file:
        path = Path(args.flow_file)
        if not path.exists():
            logger.error("Flow file not found: %s", args.flow_file)
            return 1
        flow_description = path.read_text(encoding="utf-8")
        label = f"UX Review — {path.name}"
    else:
        flow_description = _DEMO_FLOW
        label = "UX Review — Demo Flow"

    provider = _build_provider()
    agent = UXAgent(provider)
    inp = UXInput(
        flow_description=flow_description,
        user_goal=args.goal,
        user_type=args.user_type,
        flow_context=args.flow_context,
    )
    result = agent.run(inp)
    _print_result(result, label)

    return 0 if result.approved else 1


if __name__ == "__main__":
    sys.exit(main())
