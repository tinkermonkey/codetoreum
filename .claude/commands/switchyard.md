---
description: Pull and analyze Switchyard pipeline run data to improve Codetoreum simulation scenarios
argument-hint: "[run-id <uuid> | search <terms> | board <name> | project <name> | failed] [--compare] [--broad]"
---

# Switchyard Pipeline Run Analysis

Load the skill file and follow its instructions:

```
/home/austinsand/workspace/orchestrator/codetoreum/.claude/skills/switchyard/SKILL.md
```

## What This Command Does

Queries the Switchyard Elasticsearch instance (`http://localhost:9200`) to pull real pipeline run data and analyze it against the Codetoreum simulation scenarios in `scenarios/`. The goal is to grow the scenarios in both **breadth** (new scenario types) and **depth** (richer edge cases within existing scenarios).

## Usage

```
/switchyard run-id <uuid>              # Analyze a specific run by ID
/switchyard search <terms>             # Search runs by issue title/description
/switchyard board <name>               # Browse recent runs for a specific board
/switchyard project <name>             # Browse recent runs for a specific project
/switchyard failed                     # Analyze all failed runs
/switchyard                            # Broad analysis: sample successful + failed runs across boards/projects
```

**Flags:**
- `--compare` — Explicitly map each run to the most relevant existing scenario and identify gaps
- `--broad` — Sample 3-5 runs across different projects, boards, and outcomes for a panoramic view

## Instructions for Claude Code

When the user runs this command:

1. **Read the skill file** at `.claude/skills/switchyard/SKILL.md` for full context, query patterns, and the analysis framework.

2. **Parse the argument** to determine the query mode:
   - `run-id <uuid>` → fetch that specific run by ID, then fetch its decision and agent events
   - `search <terms>` → full-text search `issue_title` for the terms
   - `board <name>` → filter by board (e.g., `"SDLC Execution"`, `"Planning & Design"`)
   - `project <name>` → filter by project (e.g., `context-library`, `codetoreum`)
   - `failed` → fetch all runs with `outcome: "failed"`
   - No argument or `--broad` → fetch a representative sample: 3 recent successful SDLC runs, 3 Planning & Design runs, and all failed runs

3. **Fetch the data** using `curl` via Bash. For each run:
   - Retrieve the full pipeline run document (includes `summary`, `orchestratorRecommendations`, `projectRecommendations`)
   - If the run has a `summary` field, that is the richest source — read it fully
   - For runs without a summary, fetch decision events and agent events to reconstruct the timeline
   - If `discussion_id` is non-null, note it as a human feedback loop run

4. **Analyze against scenarios** using the framework in the skill:
   - Map the run's board/agent/failure pattern to the closest existing scenario in `scenarios/`
   - Read the relevant `scenario.md` files to compare
   - Identify what the scenario covers well, what it misses, and what new scenarios are warranted

5. **Produce a structured report** with:
   - **Run summaries**: one paragraph per run covering key facts and outcome
   - **Pattern inventory**: table of behaviors observed across all fetched runs
   - **Scenario coverage map**: for each behavior, which scenario (if any) models it
   - **Gaps**: behaviors not covered by any scenario, ranked by frequency/importance
   - **Actionable recommendations**: specific edits to existing scenario YAML/markdown, or new scenario blueprints with proposed board flow

6. **Offer next steps**: ask the user if they want to implement any of the recommended scenario changes.

## Example Queries

```bash
# Fetch specific run
/switchyard run-id 98c78934-54f5-4914-973a-f988fe3e3c78

# Find runs related to review cycles
/switchyard search "review feedback"

# All failed runs with gap analysis
/switchyard failed --compare

# Broad survey across boards
/switchyard --broad
```
