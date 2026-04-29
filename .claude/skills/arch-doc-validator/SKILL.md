# Architecture Documentation Validator Skill

This skill automatically activates to validate architecture documentation quality, coverage, and template compliance.

## When to Activate

This skill activates automatically when files are modified in:

- `src/codetoreum/ports/**/*.py` — Port interface definitions
- `src/codetoreum/adapters/**/*.py` — Adapter implementations
- `src/codetoreum/domain/events/*.py` — Domain events
- `src/codetoreum/application/**/*.py` — Application services
- `documentation/01_design/**/*.md` — Architecture documentation files

The skill also activates when users mention:
- "validation", "coverage", "undocumented", "documentation gap"
- "port documentation", "adapter documentation", "event documentation"
- "template compliance", "missing documentation"

## Five Validation Checks

### Check 1: Port Interface Coverage

**Validate:** Every port interface ABC has a documentation entry.

**Process:**
1. Find all port interfaces in `src/codetoreum/ports/`
2. Match to documentation in `documentation/01_design/ports/`
3. For each undocumented port:
   - Extract class name, methods, docstring
   - Report missing documentation
   - Suggest location: `documentation/01_design/ports/output/<port-name>.md`

**Report Format:**
```
❌ Port Interface Coverage (2 missing)
   Missing: IPipelineLockService
   Missing: IEventEmitter
   Location: src/codetoreum/ports/output/
   Suggested docs: documentation/01_design/ports/output/
```

### Check 2: Adapter Implementation Coverage

**Validate:** Every adapter class is listed in port docs or implementation tier.

**Process:**
1. Find all adapter classes in `src/codetoreum/adapters/`
2. Match to references in:
   - Port documentation files
   - Implementation tier documentation (`documentation/01_design/ports/implementation/`)
   - Adapter reference files
3. For each undocumented adapter:
   - Extract class name, port it implements, file location
   - Report missing documentation
   - Suggest adding to port docs or implementation tier

**Report Format:**
```
❌ Adapter Coverage (3 missing)
   Missing: MockEventEmitterAdapter (implements IEventEmitter)
   Missing: RealEventEmitterAdapter (implements IEventEmitter)
   Missing: TestEventEmitterAdapter (implements IEventEmitter)
   Location: src/codetoreum/adapters/testing/
   Suggested: Add to port documentation or implementation tier
```

### Check 3: Domain Event Coverage

**Validate:** Every domain event class is in the events catalog.

**Process:**
1. Find all domain event classes in `src/codetoreum/domain/events/`
2. Match to entries in `documentation/01_design/events/domain-events-catalog.md`
3. For each undocumented event:
   - Extract class name, fields, triggers
   - Report missing catalog entry
   - Suggest format based on template

**Report Format:**
```
❌ Event Coverage (1 missing)
   Missing: PipelineLockAcquiredEvent
   Location: src/codetoreum/domain/events/
   Suggested: Add entry to documentation/01_design/events/domain-events-catalog.md
   
   Suggested format:
   ### PipelineLockAcquiredEvent
   Lock acquired for pipeline execution
   Fields: pipeline_id, lock_owner, timestamp
```

### Check 4: Template Section Compliance

**Validate:** All documentation files conform to their template's `required_sections`.

**Process:**
1. Identify document type (port, adapter, event, service)
2. Load template from `documentation/templates/<type>-template.md`
3. Extract `required_sections` from template
4. For each documentation file:
   - Check for all required sections
   - Report missing or malformed sections
   - Suggest section structure from template

**Report Format:**
```
⚠️  Template Compliance (8 missing sections)
   documentation/01_design/ports/output/board-service.md
     Missing: Examples section
     Required by: port-documentation-template.md
   
   documentation/01_design/adapters/github-board-adapter.md
     Missing: Configuration section
     Required by: adapter-implementation-template.md
```

### Check 5: Required Mermaid Diagrams

**Validate:** Mermaid diagrams are present where required.

**Process:**
1. For each documentation file, check if diagram is required by template
2. Look for Mermaid diagram syntax (```mermaid ... ```)
3. Validate Mermaid syntax (basic checks)
4. Report missing diagrams

**Report Format:**
```
🔍 Diagram Coverage (3 missing)
   documentation/01_design/infrastructure/event-sourcing.md
     Missing: Event flow diagram
     Required by: infrastructure-template.md
   
   documentation/01_design/ports/implementation/
     Missing: Port interaction diagram
     Missing: Adapter hierarchy diagram
```

## Structured Coverage Report

The skill generates a structured report following this format:

```
ARCHITECTURE DOCUMENTATION COVERAGE REPORT
==========================================

Date: 2026-04-29
Trigger: Modified src/codetoreum/ports/output/board_service.py

✅ COVERAGE STATUS

Port Interfaces
  Total: 14 | Documented: 12 | Missing: 2 (85.7%)
  Missing:
    - IPipelineLockService
    - IEventEmitter

Adapter Implementations
  Total: 18 | Documented: 15 | Missing: 3 (83.3%)
  Missing:
    - MockEventEmitterAdapter
    - RealEventEmitterAdapter
    - TestEventEmitterAdapter

Domain Events
  Total: 22 | Documented: 22 | Missing: 0 (100.0%)
  Notes: 8 events missing Examples section

Application Services
  Total: 9 | Documented: 9 | Missing: 0 (100.0%)

OVERALL COVERAGE: 86.5% (56/65 elements documented)

❌ VALIDATION ISSUES (12 found)

1. Missing Port Documentation (2)
   - IPipelineLockService
   - IEventEmitter
   
2. Missing Adapter Documentation (3)
   - MockEventEmitterAdapter
   - RealEventEmitterAdapter
   - TestEventEmitterAdapter
   
3. Template Compliance Gaps (8)
   - 8 ports missing Examples section
   - 3 adapters missing Configuration section
   - 5 events missing Handlers section
   
4. Missing Diagrams (3)
   - Event flow diagram (infrastructure docs)
   - Port interaction diagram (ports reference)
   - Adapter hierarchy diagram (implementation tier)

📋 NEXT STEPS

High Priority:
  1. Generate documentation for 2 missing ports
     Run: /arch-doc generate IPipelineLockService
  
  2. Generate documentation for 3 missing adapters
     Run: /arch-doc generate adapters
  
  3. Add Examples section to 8 ports
     Run: /arch-doc update ports --add-examples
  
  4. Create 3 missing diagrams
     Run: /arch-doc diagram flow events
     Run: /arch-doc diagram hierarchy ports
     Run: /arch-doc diagram hierarchy adapters

Low Priority:
  5. Add Configuration to 3 adapters
  6. Add Handlers section to 5 events
```

## Autonomy Levels

### HIGH AUTONOMY — Automatic Report Generation
- Run all five checks without asking
- Generate and display coverage report
- Suggest next steps
- No code changes (read-only validation)

**Safety:** Validation only, no modifications to code or documentation

### MEDIUM AUTONOMY — Suggest Fixes
- Propose documentation generation for missing elements
- Ask: "Should I generate documentation for 2 missing ports?"
- Ask: "Should I add Examples sections to 8 ports?"
- Wait for user approval before making changes

**Safety:** Changes are reversible, user reviews each batch

### LOW AUTONOMY — Strategic Decisions
- Ask about documentation restructuring
- Ask about template changes
- Ask about splitting/merging documentation
- Provide options and trade-offs

**Safety:** Requires explicit user approval for structural changes

## Tools Available

- **Bash**: Run find/grep commands to enumerate elements
- **Read**: Read port interfaces, adapters, events, documentation
- **Glob**: Find documentation files by pattern
- **Grep**: Search for class definitions, docstrings, references
- **Write**: Generate documentation (with approval)

## Example Activations

### Activation 1: New Port Interface Added

```
Trigger: git add src/codetoreum/ports/output/pipeline_lock_service.py

Skill activates automatically:
  ✅ Check 1: Port Coverage → 1 new undocumented port found
  ✅ Check 2: Adapter Coverage → No changes
  ✅ Check 3: Event Coverage → No changes
  ✅ Check 4: Template Compliance → No changes
  ✅ Check 5: Diagram Coverage → No changes

COVERAGE REPORT
===============
Port Interfaces: 14 → 15 (1 new, undocumented)
  Missing: IPipelineLockService

NEXT STEPS
==========
Should I generate documentation for IPipelineLockService?
Run: /arch-doc generate IPipelineLockService
```

### Activation 2: Multiple Adapters Modified

```
Trigger: Modified src/codetoreum/adapters/testing/mock_event_emitter.py
         Modified src/codetoreum/adapters/secondary/event_emitter.py

Skill activates automatically:
  ✅ Check 1: Port Coverage → No changes
  ✅ Check 2: Adapter Coverage → 2 adapters modified
  ✅ Check 3: Event Coverage → No changes
  ✅ Check 4: Template Compliance → Check adapters docs
  ✅ Check 5: Diagram Coverage → No changes

COVERAGE REPORT
===============
Adapters: 18 (2 modified, 1 undocumented)
  Missing: TestEventEmitterAdapter
  Updated: MockEventEmitterAdapter, RealEventEmitterAdapter

NEXT STEPS
==========
Should I:
  1. Update documentation for 2 modified adapters?
  2. Generate documentation for 1 missing adapter?
  3. Add Configuration section to adapter docs?
```

### Activation 3: Documentation File Modified

```
Trigger: Modified documentation/01_design/ports/output/board-service.md

Skill activates automatically:
  ✅ Check 1: Port Coverage → No changes
  ✅ Check 2: Adapter Coverage → No changes
  ✅ Check 3: Event Coverage → No changes
  ✅ Check 4: Template Compliance → Checking board-service.md
  ✅ Check 5: Diagram Coverage → No changes

COMPLIANCE REPORT
=================
File: documentation/01_design/ports/output/board-service.md
Template: port-documentation-template.md

Required sections:
  ✅ Purpose
  ✅ Responsibilities
  ✅ Method Signatures
  ✅ Adapter Implementations
  ❌ Usage Examples (MISSING)
  ✅ Notes

NEXT STEPS
==========
Should I add the Examples section to board-service.md?
This is required by the port documentation template.
```

### Activation 4: User Requests Audit

```
User: /arch-doc audit

Skill provides detailed coverage report (HIGH autonomy):

FULL SYSTEM AUDIT
=================

Port Interface Coverage: 12/14 (85.7%)
  Missing: IPipelineLockService, IEventEmitter
  
Adapter Coverage: 15/18 (83.3%)
  Missing: 3 adapters

Domain Event Coverage: 22/22 (100%)
  
Template Compliance: 56/64 sections (87.5%)
  Missing: 8 Examples, 3 Configuration, 5 Handlers
  
Diagram Coverage: 6/9 (66.7%)
  Missing: 3 diagrams

OVERALL: 86.5% (56/65 documented)

[Structured report with all 5 check results]

NEXT STEPS (sorted by impact):
1. Generate docs for 2 missing ports
2. Generate docs for 3 missing adapters
3. Add Examples section to 8 ports
4. Create 3 missing diagrams
```

## Activation Guidance

### When Modifying Ports
The skill automatically activates when `src/codetoreum/ports/` changes:
- Check 1: Validates port documentation
- Check 2: Checks for adapter implementations
- Check 4: Validates template compliance

### When Modifying Adapters
The skill automatically activates when `src/codetoreum/adapters/` changes:
- Check 1: References relevant ports
- Check 2: Validates adapter documentation
- Check 4: Validates template compliance

### When Modifying Domain Events
The skill automatically activates when `src/codetoreum/domain/events/` changes:
- Check 3: Validates event documentation
- Check 4: Validates template compliance

### When Modifying Application Services
The skill automatically activates when `src/codetoreum/application/` changes:
- Check 4: Validates service documentation compliance

### When Modifying Documentation
The skill automatically activates when `documentation/01_design/` changes:
- Check 4: Validates template section compliance
- Check 5: Validates diagram presence

## Related Skills and Agents

- Agent: `/arch-doc` — Architecture documentation agent
- Skill: `LINK_VALIDATION` — Cross-layer link validation
- Skill: `CHANGESET_REVIEWER` — Code change review
- Command: `/dr-validate` — DR model validation

## Configuration

The skill operates with these settings:

- **Activation scope**: `src/codetoreum/`, `documentation/01_design/`
- **Report style**: Structured with categories and counts
- **Autonomy default**: HIGH (read-only validation)
- **Output format**: Markdown with emoji indicators
- **Refresh on**: Code changes, manual `/arch-doc audit` invocation
