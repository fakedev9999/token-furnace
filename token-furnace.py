#!/usr/bin/env python3
"""
Token Furnace v2 — Self-Evolving Token Burner (토큰 소각로)

An RL-like self-play loop: Generate -> Execute -> Judge -> Improve -> Repeat.
All outputs accumulate into ~/token-furnace-output.md.

Usage:
    python3 ~/token-furnace.py --opus
    python3 ~/token-furnace.py --sonnet --speed 2
"""

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import textwrap
import time
from datetime import datetime, timezone
from pathlib import Path

# ─── Constants ───────────────────────────────────────────────────────────────

VERSION = "2.0"
ARTIFACT_PATH = Path.home() / "token-furnace-output.md"
COMPRESS_EVERY = 5
SUBPROCESS_TIMEOUT = 300

# Rolling window sizes
MAX_FEEDBACKS = 3
MAX_SCORES = 8
MAX_BEST_PATTERNS = 5
MAX_WORST_PATTERNS = 5
MAX_RECURRING_ELEMENTS = 10

# ─── Judge JSON Schema ──────────────────────────────────────────────────────

JUDGE_SCHEMA = json.dumps({
    "type": "object",
    "properties": {
        "scores": {
            "type": "object",
            "properties": {
                "token_burn": {"type": "number", "description": "1-10 how many tokens were burned"},
                "meaningfulness": {"type": "number", "description": "1-10 depth and substance"},
                "weirdness": {"type": "number", "description": "1-10 creative strangeness"}
            },
            "required": ["token_burn", "meaningfulness", "weirdness"]
        },
        "composite_score": {"type": "number", "description": "Weighted average of scores"},
        "feedback": {"type": "string", "description": "2-3 sentences of specific feedback for improvement"},
        "pattern_name": {"type": "string", "description": "Snake_case classification of the prompt pattern used"},
        "pattern_verdict": {"type": "string", "enum": ["REUSE", "EVOLVE", "ABANDON"]},
        "recurring_elements": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Themes, characters, or motifs worth tracking"
        },
        "excerpt": {"type": "string", "description": "Best 1-2 sentence excerpt from the output"}
    },
    "required": ["scores", "composite_score", "feedback", "pattern_name", "pattern_verdict", "recurring_elements", "excerpt"]
})

# ─── Weirdness Tiers ────────────────────────────────────────────────────────

WEIRDNESS_TIERS = {
    (1, 3): "unusual but grounded — surreal touches on real foundations",
    (4, 6): "reality-bending — the rules of the world are negotiable",
    (7, 9): "full surreal — logic is a suggestion, physics is a metaphor",
    (10, float("inf")): "beyond category — language itself is the medium and the subject",
}


def get_weirdness_tier(round_num: int) -> str:
    for (lo, hi), desc in WEIRDNESS_TIERS.items():
        if lo <= round_num <= hi:
            return desc
    return "beyond category"


# ─── FurnaceState ────────────────────────────────────────────────────────────

class FurnaceState:
    def __init__(self):
        self.round_num = 0
        self.total_tokens_burned = 0
        self.scores: list[dict] = []           # [{round, burn, meaning, weird, composite}]
        self.feedbacks: list[str] = []
        self.best_patterns: list[dict] = []    # [{name, score, round}]
        self.worst_patterns: list[dict] = []   # [{name, score, round}]
        self.recurring_elements: list[str] = []
        self.artifact_summary = ""
        self.last_judge_result: dict | None = None
        self.last_prompt = ""
        self.last_excerpt = ""
        self.phase = "IDLE"
        self.start_time = time.time()
        self.session_token_counts: list[int] = []

    def score_trajectory(self) -> str:
        if not self.scores:
            return "No scores yet"
        parts = [f"R{s['round']}[{s['composite']:.1f}]" for s in self.scores[-MAX_SCORES:]]
        if len(self.scores) >= 2:
            recent = [s["composite"] for s in self.scores[-3:]]
            trend = "UP" if recent[-1] > recent[0] else "DOWN" if recent[-1] < recent[0] else "FLAT"
            parts.append(f"trend:{trend}")
        return " ".join(parts)

    def add_score(self, round_num: int, judge: dict):
        s = judge.get("scores", {})
        entry = {
            "round": round_num,
            "burn": s.get("token_burn", 5),
            "meaning": s.get("meaningfulness", 5),
            "weird": s.get("weirdness", 5),
            "composite": judge.get("composite_score", 5.0),
        }
        self.scores.append(entry)
        if len(self.scores) > MAX_SCORES:
            self.scores = self.scores[-MAX_SCORES:]

    def add_feedback(self, feedback: str):
        self.feedbacks.append(feedback)
        if len(self.feedbacks) > MAX_FEEDBACKS:
            self.feedbacks = self.feedbacks[-MAX_FEEDBACKS:]

    def add_pattern(self, name: str, score: float, verdict: str, round_num: int):
        entry = {"name": name, "score": score, "round": round_num}
        if verdict == "REUSE" or (verdict == "EVOLVE" and score >= 6):
            self.best_patterns.append(entry)
            self.best_patterns.sort(key=lambda x: x["score"], reverse=True)
            self.best_patterns = self.best_patterns[:MAX_BEST_PATTERNS]
        if verdict == "ABANDON" or score < 4:
            self.worst_patterns.append(entry)
            self.worst_patterns.sort(key=lambda x: x["score"])
            self.worst_patterns = self.worst_patterns[:MAX_WORST_PATTERNS]

    def add_recurring_elements(self, elements: list[str]):
        for el in elements:
            if el not in self.recurring_elements:
                self.recurring_elements.append(el)
        self.recurring_elements = self.recurring_elements[-MAX_RECURRING_ELEMENTS:]

    def generator_context(self) -> str:
        sections = []
        sections.append(f"ROUND: {self.round_num}")
        sections.append(f"WEIRDNESS TIER: {get_weirdness_tier(self.round_num)}")
        sections.append(f"SCORE TRAJECTORY: {self.score_trajectory()}")
        if self.feedbacks:
            sections.append("RECENT FEEDBACK:\n" + "\n".join(f"  - {f}" for f in self.feedbacks))
        if self.best_patterns:
            pats = ", ".join(f"{p['name']}({p['score']:.1f})" for p in self.best_patterns)
            sections.append(f"BEST PATTERNS: {pats}")
        if self.worst_patterns:
            pats = ", ".join(f"{p['name']}({p['score']:.1f})" for p in self.worst_patterns)
            sections.append(f"WORST PATTERNS (avoid): {pats}")
        if self.recurring_elements:
            sections.append(f"RECURRING ELEMENTS: {', '.join(self.recurring_elements)}")
        if self.artifact_summary:
            sections.append(f"ARTIFACT SUMMARY:\n{self.artifact_summary}")
        return "\n\n".join(sections)


# ─── Terminal UI ─────────────────────────────────────────────────────────────

class TerminalUI:
    def __init__(self, model: str):
        self.model = model
        self.cols = min(os.get_terminal_size().columns, 72)

    def clear(self):
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()

    def bar(self, value: float, max_val: float = 10, width: int = 10) -> str:
        filled = int((value / max_val) * width)
        return "\u2588" * filled + "\u2591" * (width - filled)

    def render(self, state: FurnaceState):
        self.clear()
        w = self.cols
        lines = []

        # Header
        lines.append(f"  TOKEN FURNACE  v{VERSION:<24s} Model: {self.model}")
        lines.append("")
        lines.append(f"  Round {state.round_num:<8d} Total burned: ~{state.total_tokens_burned:,} tokens")
        lines.append("")

        # Phase indicator
        phase_icons = {
            "GENERATOR": "\u25d0 [GENERATOR: Creating prompt...]",
            "EXECUTOR":  "\u25d0 [EXECUTOR: Running prompt...]",
            "JUDGE":     "\u25d0 [JUDGE: Scoring output...]",
            "COMPRESS":  "\u25d0 [COMPRESSOR: Summarizing artifact...]",
            "IDLE":      "  [Idle]",
            "SHUTDOWN":  "  [Shutting down...]",
        }
        lines.append(f"  {phase_icons.get(state.phase, state.phase)}")
        lines.append("")

        # Scores
        if state.last_judge_result:
            s = state.last_judge_result.get("scores", {})
            burn = s.get("token_burn", 0)
            meaning = s.get("meaningfulness", 0)
            weird = s.get("weirdness", 0)
            comp = state.last_judge_result.get("composite_score", 0)
            lines.append(f"  -- Last Round Scores " + "\u2500" * (w - 24))
            lines.append(f"  Burn: {self.bar(burn)} {burn}/10   Meaning: {self.bar(meaning)} {meaning}/10")
            lines.append(f"  Weird: {self.bar(weird)} {weird}/10  Composite: {comp:.1f}")
            lines.append("")

        # Trajectory
        if state.scores:
            lines.append(f"  -- Trajectory " + "\u2500" * (w - 17))
            lines.append(f"  {state.score_trajectory()}")
            lines.append("")

        # Latest excerpt
        if state.last_excerpt:
            lines.append(f"  -- Latest Excerpt " + "\u2500" * (w - 21))
            wrapped = textwrap.fill(f'"{state.last_excerpt}"', width=w - 6, initial_indent="    ", subsequent_indent="     ")
            lines.append(wrapped)
            lines.append("")

        # Judge feedback
        if state.feedbacks:
            lines.append(f"  -- Judge Says " + "\u2500" * (w - 17))
            last_fb = state.feedbacks[-1]
            r = state.scores[-1]["round"] if state.scores else "?"
            sc = state.scores[-1]["composite"] if state.scores else "?"
            wrapped = textwrap.fill(f"Round {r} ({sc}): {last_fb}", width=w - 6, initial_indent="    ", subsequent_indent="    ")
            lines.append(wrapped)
            lines.append("")

        lines.append(f"  [Ctrl+C for graceful shutdown]")

        sys.stdout.write("\n".join(lines) + "\n")
        sys.stdout.flush()


# ─── Claude CLI Calls ────────────────────────────────────────────────────────

def call_claude(
    prompt: str,
    model: str,
    system_prompt: str = "",
    json_schema: str = "",
    timeout: int = SUBPROCESS_TIMEOUT,
) -> str:
    """Call claude CLI with -p flag and return output text."""
    cmd = ["claude", "-p", "--output-format", "json", "--model", model, "--no-session-persistence", "--tools", ""]
    if system_prompt:
        cmd += ["--system-prompt", system_prompt]
    if json_schema:
        cmd += ["--json-schema", json_schema]

    env = os.environ.copy()
    env.pop("CLAUDE_CODE_ENTRYPOINT", None)
    env.pop("CLAUDECODE", None)

    proc = subprocess.run(
        cmd,
        input=prompt,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )

    if proc.returncode != 0:
        stderr = proc.stderr.strip()
        raise RuntimeError(f"claude CLI error (rc={proc.returncode}): {stderr[:500]}")

    raw = proc.stdout.strip()

    # --output-format json wraps result; extract the text
    try:
        envelope = json.loads(raw)
        # Handle the JSON output format from claude CLI
        if isinstance(envelope, dict):
            # Try common keys
            for key in ("result", "text", "content", "response", "output"):
                if key in envelope:
                    val = envelope[key]
                    if isinstance(val, str):
                        return val
                    if isinstance(val, list):
                        # content blocks
                        parts = []
                        for block in val:
                            if isinstance(block, dict) and block.get("type") == "text":
                                parts.append(block["text"])
                            elif isinstance(block, str):
                                parts.append(block)
                        if parts:
                            return "\n".join(parts)
            # Fallback: return the whole JSON as string
            return json.dumps(envelope, indent=2)
        return raw
    except json.JSONDecodeError:
        return raw


def estimate_tokens(text: str) -> int:
    """Rough estimate: ~4 chars per token."""
    return max(1, len(text) // 4)


# ─── Generator ───────────────────────────────────────────────────────────────

GENERATOR_SYSTEM = """\
You are the PROMPT GENERATOR for the Token Furnace — a self-evolving creative engine.

Your job: produce a single creative prompt that will be given to another AI to execute.
The prompt you create should maximize:
1. TOKEN BURN — the resulting output should be long, dense, and exhaustive
2. WEIRDNESS — push creative boundaries according to the current weirdness tier
3. MEANINGFULNESS — it should have substance, depth, and internal logic despite weirdness

You receive context about previous rounds: scores, feedback, patterns to reuse or avoid,
recurring narrative elements, and an artifact summary. Use this to IMPROVE each round.

RULES:
- Output ONLY the prompt text. No meta-commentary, no explanation.
- The prompt should demand a LONG, DETAILED response (aim for 2000+ words of output).
- Incorporate recurring elements to build emergent narrative threads.
- Escalate weirdness according to the tier guidance.
- Vary your approach — don't repeat the same pattern type twice in a row.
- Make it specific. Vague prompts get vague outputs. Give rich constraints and details.
"""


def run_generator(state: FurnaceState, model: str) -> str:
    context = state.generator_context()
    prompt = f"""\
Generate a single creative prompt for Round {state.round_num}.

CONTEXT:
{context}

Remember: Output ONLY the prompt text, nothing else. Make it demand exhaustive output."""

    return call_claude(prompt, model=model, system_prompt=GENERATOR_SYSTEM)


# ─── Executor ────────────────────────────────────────────────────────────────

EXECUTOR_SYSTEM = """\
You are a boundlessly creative writer executing a prompt from the Token Furnace.

RULES:
- Write EXHAUSTIVELY. Never abbreviate, summarize, or cut short.
- Never say "and so on" or "etc" — write it ALL out.
- Never use ellipsis (...) to skip content. Every detail must be rendered.
- Minimum 2000 words. There is no maximum. More is better.
- Embrace the weird. If the prompt asks for surreal content, go ALL IN.
- Maintain internal consistency within the piece, even if the logic is surreal.
- Rich, vivid, specific language. No filler. Every sentence should carry weight.
- Do not add meta-commentary about the prompt or your response.
- If given continuity context, weave those elements naturally into your work.
"""


def get_artifact_tail(max_chars: int = 2000) -> str:
    """Get the tail of the artifact file for continuity context."""
    if not ARTIFACT_PATH.exists():
        return ""
    try:
        text = ARTIFACT_PATH.read_text(encoding="utf-8")
        if len(text) <= max_chars:
            return text
        return text[-max_chars:]
    except Exception:
        return ""


def run_executor(prompt_text: str, model: str) -> str:
    continuity = get_artifact_tail()
    full_prompt = prompt_text
    if continuity:
        full_prompt += f"\n\n---\n[CONTINUITY CONTEXT — recent artifact excerpt for narrative threading:]\n{continuity[-500:]}"

    return call_claude(full_prompt, model=model, system_prompt=EXECUTOR_SYSTEM)


# ─── Judge ───────────────────────────────────────────────────────────────────

JUDGE_SYSTEM = """\
You are the JUDGE of the Token Furnace. You evaluate creative outputs on three axes.

Score each 1-10:
- token_burn: How many tokens were used? Longer, denser = higher score.
- meaningfulness: Depth, substance, internal logic, literary quality.
- weirdness: Creative strangeness, surreal innovation, boundary-pushing.

composite_score = weighted average (burn*0.3 + meaning*0.3 + weird*0.4)

For pattern_name: classify the prompt's approach in snake_case (e.g., surreal_academic_paper,
nested_mythology, recursive_dream_journal, bureaucratic_fantasy).

For pattern_verdict:
- REUSE: This pattern worked great, use it again
- EVOLVE: Good bones, but needs mutation/escalation next time
- ABANDON: This pattern is played out or didn't work

For recurring_elements: extract 2-4 themes, characters, motifs, or concepts worth tracking
across rounds. These create emergent narrative threads.

For excerpt: pick the single best 1-2 sentence passage from the output.

Be honest and critical. High scores must be earned.
"""


def run_judge(prompt_text: str, output_text: str, round_num: int, model: str) -> dict:
    judge_prompt = f"""\
ROUND: {round_num}

THE PROMPT THAT WAS GIVEN:
{prompt_text[:1000]}

THE OUTPUT TO JUDGE:
{output_text[:8000]}

Score this output. Return structured JSON."""

    raw = call_claude(judge_prompt, model=model, system_prompt=JUDGE_SYSTEM, json_schema=JUDGE_SCHEMA)

    # Try to parse JSON from the response
    return parse_judge_json(raw)


def parse_judge_json(raw: str) -> dict:
    """Parse judge output as JSON, with fallback regex extraction."""
    # Direct parse
    try:
        result = json.loads(raw)
        if "scores" in result:
            return result
    except (json.JSONDecodeError, TypeError):
        pass

    # Try to find JSON block in the text
    json_match = re.search(r'\{[\s\S]*"scores"[\s\S]*\}', raw)
    if json_match:
        try:
            result = json.loads(json_match.group())
            if "scores" in result:
                return result
        except json.JSONDecodeError:
            pass

    # Fallback: regex extraction
    def extract_num(pattern: str, default: float = 5.0) -> float:
        m = re.search(pattern, raw)
        return float(m.group(1)) if m else default

    return {
        "scores": {
            "token_burn": extract_num(r"token_burn[\":\s]+(\d+\.?\d*)", 5),
            "meaningfulness": extract_num(r"meaningfulness[\":\s]+(\d+\.?\d*)", 5),
            "weirdness": extract_num(r"weirdness[\":\s]+(\d+\.?\d*)", 5),
        },
        "composite_score": extract_num(r"composite[\":\s]+(\d+\.?\d*)", 5),
        "feedback": "Judge output could not be fully parsed. Continuing with defaults.",
        "pattern_name": "unknown_pattern",
        "pattern_verdict": "EVOLVE",
        "recurring_elements": [],
        "excerpt": "",
    }


# ─── Compressor ──────────────────────────────────────────────────────────────

COMPRESSOR_SYSTEM = """\
Summarize the following creative artifact into ~300 words. Capture:
- Key narrative threads and recurring characters/themes
- The overall tone and trajectory of weirdness
- Memorable images and concepts
- How the pieces connect to each other
Be dense and specific. This summary guides future generation."""


def run_compressor(model: str) -> str:
    if not ARTIFACT_PATH.exists():
        return ""
    text = ARTIFACT_PATH.read_text(encoding="utf-8")
    if len(text) < 500:
        return text

    # Take a representative sample if too long
    if len(text) > 15000:
        # First 3000 + last 8000 chars
        sample = text[:3000] + "\n\n[...middle sections omitted...]\n\n" + text[-8000:]
    else:
        sample = text

    prompt = f"Summarize this creative artifact:\n\n{sample}"
    return call_claude(prompt, model=model, system_prompt=COMPRESSOR_SYSTEM)


# ─── Artifact Writing ────────────────────────────────────────────────────────

def init_artifact():
    """Initialize the artifact file if it doesn't exist."""
    if not ARTIFACT_PATH.exists():
        header = f"""\
# THE TOKEN FURNACE
## An Autonomous Generative Artifact
### Started: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}

"""
        ARTIFACT_PATH.write_text(header, encoding="utf-8")


def append_round_to_artifact(round_num: int, score: float, token_count: int, pattern: str, prompt: str, output: str):
    """Append a round's output to the artifact file."""
    section = f"""
---

## Round {round_num} | Score: {score:.1f} | ~{token_count:,} tokens
*Pattern: {pattern}*
*Prompt: {prompt[:200]}{"..." if len(prompt) > 200 else ""}*

{output}
"""
    with open(ARTIFACT_PATH, "a", encoding="utf-8") as f:
        f.write(section)


def append_shutdown_footer(state: FurnaceState):
    """Append session summary to artifact."""
    elapsed = time.time() - state.start_time
    minutes = elapsed / 60
    avg_score = 0
    if state.scores:
        avg_score = sum(s["composite"] for s in state.scores) / len(state.scores)

    footer = f"""

---
---

## Session Summary
- **Rounds completed**: {state.round_num}
- **Total tokens burned**: ~{state.total_tokens_burned:,}
- **Average composite score**: {avg_score:.1f}
- **Session duration**: {minutes:.1f} minutes
- **Score trajectory**: {state.score_trajectory()}
- **Top patterns**: {', '.join(p['name'] for p in state.best_patterns[:3]) if state.best_patterns else 'N/A'}
- **Recurring elements**: {', '.join(state.recurring_elements[:5]) if state.recurring_elements else 'N/A'}
- **Ended**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
"""
    with open(ARTIFACT_PATH, "a", encoding="utf-8") as f:
        f.write(footer)


# ─── Main Loop ───────────────────────────────────────────────────────────────

shutdown_requested = False


def handle_sigint(sig, frame):
    global shutdown_requested
    shutdown_requested = True


def main():
    global shutdown_requested

    parser = argparse.ArgumentParser(description="Token Furnace v2 — Self-Evolving Token Burner")
    model_group = parser.add_mutually_exclusive_group()
    model_group.add_argument("--opus", action="store_true", help="Use claude-opus-4-6")
    model_group.add_argument("--sonnet", action="store_true", help="Use claude-sonnet-4-6")
    parser.add_argument("--speed", type=float, default=0, help="Delay in seconds between phases (default: 0)")
    parser.add_argument("--rounds", type=int, default=0, help="Max rounds (0 = infinite)")
    args = parser.parse_args()

    if args.opus:
        model = "claude-opus-4-6"
        model_label = "opus"
    elif args.sonnet:
        model = "claude-sonnet-4-6"
        model_label = "sonnet"
    else:
        model = "claude-sonnet-4-6"
        model_label = "sonnet"

    signal.signal(signal.SIGINT, handle_sigint)

    state = FurnaceState()
    ui = TerminalUI(model=model_label)

    init_artifact()

    try:
        while not shutdown_requested:
            state.round_num += 1
            if args.rounds and state.round_num > args.rounds:
                break

            # ── Phase 1: GENERATOR ──
            state.phase = "GENERATOR"
            ui.render(state)
            if args.speed:
                time.sleep(args.speed)

            try:
                prompt_text = run_generator(state, model)
            except Exception as e:
                sys.stderr.write(f"\nGenerator error: {e}\n")
                state.round_num -= 1
                break

            if shutdown_requested:
                state.round_num -= 1
                break

            state.last_prompt = prompt_text
            gen_tokens = estimate_tokens(prompt_text)
            state.total_tokens_burned += gen_tokens

            # ── Phase 2: EXECUTOR ──
            state.phase = "EXECUTOR"
            ui.render(state)
            if args.speed:
                time.sleep(args.speed)

            try:
                output_text = run_executor(prompt_text, model)
            except Exception as e:
                sys.stderr.write(f"\nExecutor error: {e}\n")
                state.round_num -= 1
                break

            if shutdown_requested:
                state.round_num -= 1
                break

            exec_tokens = estimate_tokens(output_text)
            state.total_tokens_burned += exec_tokens
            state.session_token_counts.append(exec_tokens)

            # ── Phase 3: JUDGE ──
            state.phase = "JUDGE"
            ui.render(state)
            if args.speed:
                time.sleep(args.speed)

            try:
                judge_result = run_judge(prompt_text, output_text, state.round_num, model)
            except Exception as e:
                sys.stderr.write(f"\nJudge error: {e}\n")
                # Use defaults
                judge_result = {
                    "scores": {"token_burn": 5, "meaningfulness": 5, "weirdness": 5},
                    "composite_score": 5.0,
                    "feedback": f"Judge failed: {e}",
                    "pattern_name": "unknown",
                    "pattern_verdict": "EVOLVE",
                    "recurring_elements": [],
                    "excerpt": "",
                }

            if shutdown_requested:
                break

            judge_tokens = estimate_tokens(json.dumps(judge_result))
            state.total_tokens_burned += judge_tokens

            # ── Update State ──
            composite = judge_result.get("composite_score", 5.0)
            pattern = judge_result.get("pattern_name", "unknown")
            verdict = judge_result.get("pattern_verdict", "EVOLVE")
            feedback = judge_result.get("feedback", "")
            excerpt = judge_result.get("excerpt", "")
            elements = judge_result.get("recurring_elements", [])

            state.last_judge_result = judge_result
            state.last_excerpt = excerpt
            state.add_score(state.round_num, judge_result)
            state.add_feedback(feedback)
            state.add_pattern(pattern, composite, verdict, state.round_num)
            state.add_recurring_elements(elements)

            # ── Write to Artifact ──
            append_round_to_artifact(state.round_num, composite, exec_tokens, pattern, prompt_text, output_text)

            # ── Phase 4: COMPRESS (every N rounds) ──
            if state.round_num % COMPRESS_EVERY == 0 and not shutdown_requested:
                state.phase = "COMPRESS"
                ui.render(state)
                try:
                    summary = run_compressor(model)
                    compress_tokens = estimate_tokens(summary)
                    state.total_tokens_burned += compress_tokens
                    state.artifact_summary = summary
                except Exception:
                    pass  # Non-critical, continue without

            # ── Render final state for this round ──
            state.phase = "IDLE"
            ui.render(state)
            if args.speed:
                time.sleep(args.speed)

    except KeyboardInterrupt:
        pass

    # ── Shutdown ──
    state.phase = "SHUTDOWN"
    ui.render(state)
    append_shutdown_footer(state)

    # Print final summary to terminal
    elapsed = time.time() - state.start_time
    avg = sum(s["composite"] for s in state.scores) / len(state.scores) if state.scores else 0

    print()
    print(f"  \u2500\u2500 Session Complete " + "\u2500" * 40)
    print(f"  Rounds:        {state.round_num}")
    print(f"  Tokens burned: ~{state.total_tokens_burned:,}")
    print(f"  Avg score:     {avg:.1f}")
    print(f"  Duration:      {elapsed/60:.1f} min")
    print(f"  Artifact:      {ARTIFACT_PATH}")
    print(f"  Trajectory:    {state.score_trajectory()}")
    print()


if __name__ == "__main__":
    main()
