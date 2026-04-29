---
description: Architecture documentation agent. Comprehensive architect for architecture documentation workflows - generation, validation, updates, diagrams, and audits.
argument-hint: "<intent> [target]"
---

# Architecture Documentation Command

Comprehensive architecture documentation management through intelligent intent-based routing. Generate, validate, update, diagram, and audit documentation with adaptive autonomy.

## Usage

```
/arch-doc <intent> [target]
```

## Intents

### Generate Intent

Create new documentation for code elements.

```
/arch-doc generate IBoardService         # Generate port interface docs
/arch-doc generate adapters              # Generate stubs for all adapters
/arch-doc generate events                # Generate event documentation
/arch-doc generate services              # Generate service documentation
```

**When to use:** Creating documentation for undocumented code elements, new ports, new adapters

### Validate Intent

Check that documentation matches templates and covers all code elements.

```
/arch-doc validate ports                 # Validate all port documentation
/arch-doc validate adapters              # Validate all adapter documentation
/arch-doc validate events                # Validate event documentation
/arch-doc validate all                   # Full documentation validation
/arch-doc validate templates             # Check template compliance
```

**When to use:** Before committing, after code changes, in PR reviews, checking template compliance

### Update Intent

Modify existing documentation to reflect code or architectural changes.

```
/arch-doc update IBoardService           # Update specific port documentation
/arch-doc update GitHubBoardAdapter      # Update specific adapter docs
/arch-doc update WorkItemColumnChangedEvent  # Update event documentation
/arch-doc update all signatures          # Update all method signatures
/arch-doc update references              # Update cross-references
```

**When to use:** Code interface changes, architectural updates, broken references, documentation improvements

### Diagram Intent

Generate Mermaid diagrams for documentation.

```
/arch-doc diagram sequence <workflow>    # Sequence diagram for workflow
/arch-doc diagram class <layer>          # Class diagram for layer
/arch-doc diagram flow events            # Event flow diagram
/arch-doc diagram hierarchy ports        # Port hierarchy diagram
/arch-doc diagram er data-model          # Entity relationship diagram
```

**When to use:** Creating or updating architecture diagrams, documenting interactions, showing flows

### Audit Intent

Comprehensive documentation coverage analysis.

```
/arch-doc audit                          # Full system audit
/arch-doc audit ports                    # Port documentation coverage
/arch-doc audit adapters                 # Adapter documentation coverage
/arch-doc audit events                   # Event documentation coverage
/arch-doc audit coverage                 # Coverage report
/arch-doc audit gaps                     # Identify documentation gaps
```

**When to use:** Quarterly reviews, release checklists, identifying documentation debt, coverage analysis

## Intent Keywords Reference

### Generate Keywords
"create", "generate", "write", "new", "stub"

### Validate Keywords
"check", "validate", "audit", "verify", "conform"

### Update Keywords
"update", "modify", "change", "fix", "refactor"

### Diagram Keywords
"diagram", "visualize", "draw", "mermaid", "flow", "sequence", "class"

### Audit Keywords
"audit", "coverage", "gap", "undocumented", "missing"

## Examples

### Example 1: Generate Port Documentation

```
User: /arch-doc generate IPipelineLockService

Agent:
  1. Introspects src/codetoreum/ports/output/pipeline_lock_service.py
  2. Loads documentation/templates/port-documentation-template.md
  3. Generates documentation with:
     - Purpose section (from interface docstring)
     - Method Signatures (from @abstractmethod)
     - Adapter Implementations (skeleton)
     - Usage Examples (from docstrings)
  4. Writes to documentation/01_design/ports/output/pipeline-lock-service.md
  5. Commits: "Generate documentation for IPipelineLockService port"
```

### Example 2: Validate Documentation Compliance

```
User: /arch-doc validate ports

Agent:
  1. Finds all ports in src/codetoreum/ports/
  2. Loads port documentation template
  3. For each port:
     - Checks required_sections compliance
     - Verifies method documentation
     - Reports missing sections
  4. Generates report:
     ✅ 12 ports fully documented
     ⚠️  3 ports missing Examples section
     ❌ 2 ports undocumented (IPipelineLockService, IEventEmitter)
  5. Suggests: "Should I generate docs for 2 missing ports?"
```

### Example 3: Update After Interface Change

```
User: /arch-doc update IBoardService

Agent:
  1. Detects MEDIUM autonomy (architectural change)
  2. Proposes: "Should I update documentation from code changes?"
  3. Upon approval:
     - Introspects updated method signatures
     - Updates Method Signatures section
     - Updates Usage Examples
     - Validates template compliance
  4. Commits: "Update IBoardService documentation with method signature changes"
```

### Example 4: Create Event Flow Diagram

```
User: /arch-doc diagram flow events

Agent:
  1. Introspects event handlers in src/codetoreum/application/event_handlers/
  2. Traces event types and handler chains
  3. Generates Mermaid flowchart showing:
     DomainEvent → EventBus → Handlers → SideEffects
  4. Adds to documentation/01_design/infrastructure/event-sourcing.md
  5. Commits: "Add event flow diagram to event sourcing documentation"
```

### Example 5: Run Comprehensive Audit

```
User: /arch-doc audit

Agent:
  1. Enumerates all code elements:
     - Ports: IBoardService, ICodeReviewService, IPipelineLockService, ...
     - Adapters: GitHubBoardAdapter, MockBoardAdapter, ...
     - Events: WorkItemColumnChangedEvent, ReviewStatusChangedEvent, ...
  2. Cross-references with documentation/01_design/
  3. Generates structured report:
     
     DOCUMENTATION COVERAGE REPORT
     =============================
     
     ✅ Port Interfaces (12/14 documented)
        Missing: IPipelineLockService, IEventEmitter
     
     ✅ Adapters (15/18 documented)
        Missing: MockEventEmitterAdapter, RealEventEmitterAdapter
     
     ⚠️  Domain Events (22/22 documented, 8 missing Examples)
     
     ⚠️  Template Compliance
        8 ports missing Examples section
        3 adapters missing Configuration section
     
     🔍 Diagram Status
        6 diagrams present, 3 missing (event flows, adapter hierarchy)
  
  4. Suggests next steps:
     "Should I generate docs for 2 missing ports?
      Should I add Examples to 8 ports?
      Should I create 3 diagrams?"
```

## Related Agents

- `/arch-doc` - This agent (architecture documentation)
- `/dr-architect` - DR model architect (documentation robotics)
- `/dr-validate` - DR model validation
- `/dr-model` - DR model elements

## Activation Triggers

The architecture documentation agent activates automatically when:
- User runs `/arch-doc <intent> [target]`
- User mentions "architecture documentation", "doc template", "doc validation"
- Files in these paths are modified:
  - `src/codetoreum/ports/`
  - `src/codetoreum/adapters/`
  - `src/codetoreum/domain/`
  - `src/codetoreum/application/`
  - `documentation/01_design/`

## Tips

1. **Be specific with targets** - `/arch-doc generate IBoardService` is more precise than `/arch-doc generate`
2. **Use validate before committing** - Catch documentation drift early
3. **Batch updates** - `/arch-doc update all signatures` is more efficient than updating individually
4. **Review audit reports** - Run `/arch-doc audit coverage` quarterly
5. **Let the agent propose** - Say "check if port docs are correct" rather than "update these three ports"

## See Also

- Agent definition: `.claude/agents/arch-doc.md`
- Skill validation: `.claude/skills/arch-doc-validator/SKILL.md`
- Design docs: `documentation/01_design/`
- Templates: `documentation/templates/`
