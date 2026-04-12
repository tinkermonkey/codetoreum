---
description: Analyze a Switchyard pipeline run and replicate it as a Codetoreum simulation scenario — creating or updating scenario YAML, filling simulation gaps, and verifying the scenario passes
argument-hint: "<pipeline-run-id>"
---

# Switchyard Mimic

Load the skill file and follow its instructions:

```
/home/austinsand/workspace/orchestrator/codetoreum/.claude/skills/switchyard-mimic/SKILL.md
```

## What This Command Does

Bridges real Switchyard production runs into the Codetoreum simulation framework.
Given a pipeline run ID it will:

1. Fetch and analyze the run from the Switchyard Elasticsearch instance
2. Map it to the closest existing simulation scenario (or decide a new one is needed)
3. Create or update scenario YAML files and the scenario description
4. Analyze whether the simulation system can faithfully replicate the run — and add
   capabilities where it cannot
5. Escalate any architectural or functional gaps to you before touching application code
6. Write a pytest simulation test and run it
7. Iterate up to five fix cycles until the scenario is fully green

## Usage

```
/switchyard-mimic <pipeline-run-id>
```

The `pipeline-run-id` argument is **required**. The command will ask for it if omitted.

## Example

```
/switchyard-mimic 98c78934-54f5-4914-973a-f988fe3e3c78
```
