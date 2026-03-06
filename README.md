```
                        ⠀⠀⠀⠀⣤⠀⠀⠀⠀
                        ⠀⠀⠀⣾⣿⣷⠀⠀⠀
                        ⠀⠀⣸⣿⣿⣿⣇⠀⠀
                        ⠀⣰⣿⣿⣿⣿⣿⣆⠀
                        ⣰⣿⣿⣿⣿⣿⣿⣿⣆
                        ⠹⣿⣿⣿⣿⣿⣿⣿⠏
                        ⠀⠀⠙⠛⠛⠛⠋⠁⠀

  _______ ____  __ __ ______ _   __   ______ __  __ ____   _   __ ___    ______ ______
 /_  __// __ \ / //_// ____// | / /  / ____// / / // __ \ / | / //   |  / ____// ____/
  / /  / / / // ,<  / __/  /  |/ /  / /_   / / / // /_/ //  |/ // /| | / /    / __/
 / /  / /_/ // /| |/ /___ / /|  /  / __/  / /_/ // _, _// /|  // ___ |/ /___ / /___
/_/   \____//_/ |_/_____//_/ |_/  /_/     \____//_/ |_|/_/ |_//_/  |_|\____//_____/
```

<div align="center">

### 토큰 소각로

> **"An AI that mass-produces increasingly unhinged creative writing, scores itself, and spirals upward. It gets weirder every round. All outputs accumulate into one massive document."**

<p>
<img src="https://img.shields.io/badge/zero_deps-00c853?style=for-the-badge" alt="zero deps" />
<img src="https://img.shields.io/badge/self--improving-blueviolet?style=for-the-badge" alt="self-improving" />
<img src="https://img.shields.io/badge/Claude_CLI-cc785c?style=for-the-badge" alt="Claude CLI" />
<img src="https://img.shields.io/badge/python_3-3572A5?style=for-the-badge" alt="python 3" />
<img src="https://img.shields.io/badge/status-actively_burning-ff6d00?style=for-the-badge" alt="status: actively burning" />
<img src="https://img.shields.io/badge/warranty-none-lightgrey?style=for-the-badge" alt="warranty: none" />
</p>

</div>

---

## What Is This

Token Furnace is a self-improving creative engine that runs on the [Claude CLI](https://docs.anthropic.com/en/docs/claude-code). It generates creative writing prompts, executes them, scores the output, and feeds that data back into the next round. Every output accumulates into a single massive artifact document.

The motivation: roughly 56% of your weekly Claude tokens are going to waste. This fixes that by turning idle capacity into an autonomous creative engine that genuinely improves itself each round.

Single-file Python. Zero dependencies. Infinite rounds. One growing artifact.

## Architecture (구조)

```
    ┌──────────┐     ┌──────────┐     ┌──────────┐
    │GENERATOR │────▶│ EXECUTOR │────▶│  JUDGE   │
    │  생성기  │     │  실행기  │     │  심사관  │
    └────▲─────┘     └──────────┘     └────┬─────┘
         │                                  │
         └──────── FURNACE STATE ◀──────────┘
                 scores · patterns
                 feedback · drift
                         │
                         ▼
                    ┌──────────┐
                    │ ARTIFACT │
                    │소각 기록물│
                    └──────────┘
```

The Generator creates prompts informed by the Furnace State — recent scores, successful patterns, failed patterns, recurring narrative elements, and a compressed summary of everything produced so far. The Executor runs each prompt with maximum creative latitude. The Judge scores the output on three axes and feeds structured data back into the state. Every 5 rounds, the Compressor distills the full artifact into a summary to keep the context window manageable.

## Terminal UI

```
  TOKEN FURNACE  v2.0                    Model: opus

  Round 7        Total burned: ~142,800 tokens

  ◐ [JUDGE: Scoring output...]

  -- Last Round Scores ──────────────────────────────────────────
  Burn: ████████░░ 8/10   Meaning: ███████░░░ 7/10
  Weird: █████████░ 9/10  Composite: 8.1

  -- Trajectory ─────────────────────────────────────────────────
  R1[5.2] R2[5.8] R3[6.4] R4[6.1] R5[7.3] R6[7.8] R7[8.1] trend:UP

  -- Latest Excerpt ─────────────────────────────────────────────
    "The librarian's shadow detached itself from the wall and
     began cataloguing the dreams of everyone who had ever
     fallen asleep in the reference section, filing each one
     under a Dewey Decimal number that hadn't been invented yet."

  -- Judge Says ─────────────────────────────────────────────────
    Round 7 (8.1): The recursive library conceit works
    beautifully — the nested self-reference creates genuine
    vertigo. Push the Dewey Decimal thread further; it's
    becoming a signature motif.

  [Ctrl+C for graceful shutdown]
```

## How It Burns (작동 방식)

### Generator (생성기)
- Crafts a creative prompt optimized for token burn, weirdness, and meaningfulness
- Learns from previous scores, judge feedback, and pattern history
- Escalates weirdness tier automatically as rounds progress

### Executor (실행기)
- Executes the prompt with maximum creative latitude — minimum 2,000 words, no ceiling
- Threads narrative elements from prior rounds for emergent continuity
- Never abbreviates, never summarizes, never says "etc."

### Judge (심사관)
- Scores on three axes: **token burn** (×0.3), **meaningfulness** (×0.3), **weirdness** (×0.4)
- Classifies prompt patterns as `REUSE`, `EVOLVE`, or `ABANDON`
- Extracts recurring elements to build cross-round narrative threads

## Weirdness Escalation (이상함 단계)

| Rounds | Tier | Description |
|--------|------|-------------|
| 1–3 | 🌱 | unusual but grounded — surreal touches on real foundations |
| 4–6 | 🌀 | reality-bending — the rules of the world are negotiable |
| 7–9 | 🔮 | full surreal — logic is a suggestion, physics is a metaphor |
| 10+ | ∞ | beyond category — language itself is the medium and the subject |

```
╔══════════════════════════════════════════════════════╗
║  ⚠  WARNING / 경고                                  ║
║                                                      ║
║  This tool burns tokens on purpose.                  ║
║  It will not stop until you tell it to.              ║
║  Each round = 3 Claude API calls.                    ║
║  The author is not responsible for your bill.        ║
║                                                      ║
║  당신은 경고를 받았습니다.                            ║
╚══════════════════════════════════════════════════════╝
```

## Usage

```bash
# ignite
python3 token-furnace.py --opus

# slower burn, watch each phase
python3 token-furnace.py --sonnet --speed 2

# fixed rounds
python3 token-furnace.py --opus --rounds 10
```

**Requirements:** `python3` and the [`claude`](https://docs.anthropic.com/en/docs/claude-code) CLI, installed and authenticated. Zero pip dependencies.

## Sample Output (출력 예시)

> The Department of Temporal Cartography had been mapping the coastline of next Thursday for six months when they discovered that Tuesdays, when viewed from sufficient altitude, formed a perfect Fibonacci spiral. Senior Cartographer Yun-seo pinned the finding to the corkboard in the break room, between a takeout menu from a restaurant that hadn't opened yet and a photograph of the office Christmas party from 1987 that somehow included everyone currently on staff. The discovery was, of course, filed under both "Mathematics" and "Weather," because in the Department, topology was a matter of opinion and Thursdays had their own climate.

See [`samples/sample-artifact.md`](samples/sample-artifact.md) for a full multi-round example.

## The Artifact (소각 기록물)

Every round appends to `~/token-furnace-output.md`. The file grows continuously:

```markdown
# THE TOKEN FURNACE
## An Autonomous Generative Artifact
### Started: 2025-01-15 03:42 UTC

---

## Round 1 | Score: 5.2 | ~3,400 tokens
*Pattern: surreal_bureaucracy*
*Prompt: Write a comprehensive field guide to...*

[full output here]

---

## Round 2 | Score: 6.1 | ~4,100 tokens
...

---
---

## Session Summary
- **Rounds completed**: 12
- **Total tokens burned**: ~186,000
- **Average composite score**: 7.3
- **Score trajectory**: R1[5.2] R2[6.1] ... R12[8.4] trend:UP
```

The artifact is the product. It's a record of the furnace's own evolution.

## Philosophy (제작 철학)

What if iteration was the product? What if the process of getting better at generating was itself the output? Token Furnace is a closed-loop creative engine. The artifact it produces is a record of its own evolution — each round building on the last, learning what works, abandoning what doesn't, spiraling toward increasingly unhinged but internally coherent creative output.

```
─────────────────────────────────
토큰 소각로 · Token Furnace · v2.0
built by the fire, for the fire
─────────────────────────────────
```
