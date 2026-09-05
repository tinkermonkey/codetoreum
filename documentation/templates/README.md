# Documentation Templates

Documentation templates define the required structure and content for different types of documentation files. Templates use YAML frontmatter to specify:

- **required_sections**: Markdown headings that must be present
- **required_elements**: Content requirements (e.g., "mermaid diagram", "python code block")
- **applies_to**: Glob pattern identifying which documentation files the template governs

## Template Files

### port-template.md
**Applies to**: `documentation/architecture/ports/**/*.md`

Required sections for port documentation files (both input and output):
- **Purpose** — One paragraph describing the port's responsibility
- **Interface Definition** — Python ABC definition with type signatures
- **Methods** — Table of method names, parameters, return types, descriptions
- **Events Emitted** — List of domain events this port may trigger
- **Error Contracts** — Expected exceptions and error conditions
- **Adapter Implementations** — Table of all known adapters
- **Diagram** — Mermaid class diagram showing port and implementations

Required elements:
- Mermaid diagram (classDiagram format)
- Python code block with interface definition
- At least one adapter implementation listed

### adapter-template.md
**Applies to**: `documentation/implementations/**/*adapter*.md`

Required sections for adapter documentation:
- **Purpose** — What port(s) this adapter implements
- **Implementation Strategy** — How it fulfills the port contract
- **Configuration** — Required parameters and environment variables
- **Error Handling** — How errors from the external system are handled
- **Testing** — How this adapter is tested
- **Source** — File path and class name
- **Diagram** — Mermaid diagram showing adapter and its interactions

Required elements:
- Mermaid diagram
- Python code block showing configuration/instantiation
- Link to adapter source code

### service-template.md
**Applies to**: `documentation/architecture/application-services/*.md`

Required sections for application service documentation:
- **Responsibility** — What use case this service implements
- **Dependencies** — What ports and domain objects this service uses
- **Key Methods** — Table of method names, parameters, return types
- **Events Emitted** — Domain events this service publishes
- **Error Handling** — Error scenarios and recovery
- **Sequence Diagram** — Mermaid diagram of typical workflow (if complex)
- **Source** — File path and class name

Required elements:
- Mermaid diagram (flowchart or sequence format)
- Python code block with key method signatures
- List of events emitted

### implementation-template.md
**Applies to**: `documentation/implementations/**/*.md`

Required sections for implementation tier documentation:
- **Purpose** — What this implementation demonstrates
- **Architecture** — How it fulfills architecture contracts
- **Adapter Selections** — Which adapters are used for each port
- **Bootstrap Process** — How components are wired together
- **Configuration** — Environment variables and settings
- **Quick Start** — Steps to run this implementation
- **Limitations** — What this implementation does not support
- **Diagram** — Mermaid diagram showing wiring and architecture

Required elements:
- Mermaid diagram (flowchart format for wiring)
- Python code block showing bootstrap function
- Table of adapter selections
- List of configuration variables

### domain-template.md
**Applies to**: `documentation/architecture/domain/*.md`

Required sections for domain model and event documentation:
- **Overview** — What domain concepts this file covers
- **Model Definitions** — Dataclass or ABC definitions with type signatures
- **Invariants** — Business rules enforced by these models
- **Events** — What events these models may emit
- **Relationships** — How these models interact with other domain concepts
- **Examples** — Code examples of using these models
- **Diagram** — Mermaid diagram showing relationships (if applicable)

Required elements:
- Python code blocks with model definitions
- At least one diagram (entityRelationship or classDiagram format)
- List of invariants and validation rules

## Enforcement

Documentation templates are enforced through:

1. **Manual Review**: During PR review, verify new documentation follows the applicable template
2. **Automated Validation**: The `arch-doc` agent (`.claude/agents/arch-doc.md`) with validation skill (`arch-doc-validator`, `.claude/skills/arch-doc-validator/SKILL.md`) checks:
   - All required sections are present
   - Required elements (diagrams, code blocks) exist
   - Headings match template requirements
   - Cross-references are valid

3. **Coverage Validation**: Agent verifies:
   - Every port interface has documentation
   - Every adapter is listed in at least one documentation file
   - Every domain event is cataloged
   - No undocumented code artifacts

## Using Templates

When adding new documentation:

1. **Identify the Template**: Determine which template applies (port, adapter, service, implementation, or domain)
2. **Use as Checklist**: Read the template to understand required sections
3. **Include Frontmatter** (optional but recommended): Reference the template in a comment
4. **Verify Completeness**: Check that all required sections and elements are present

Example frontmatter:
```markdown
---
template: port-template.md
applies_to: documentation/architecture/ports/output/*.md
---

# Port Documentation
... content ...
```

## Template Structure

Each template file:
- Contains YAML frontmatter with `required_sections`, `required_elements`, and `applies_to`
- Shows the template structure as a markdown skeleton
- Includes brief descriptions for each section
- Provides rationale for why each section is important

## File Naming

All documentation files use lowercase-hyphenated naming (except README.md):
- ✅ `production-bootstrap.md`
- ✅ `event-bus-design.md`
- ❌ `ComprehensivePortsReference.md`
- ❌ `PRODUCTION_BOOTSTRAP_WIRING.md`

## Delivery Status

- **Phase 1** ✅: All 5 template files created with required sections
- **Phase 2** ✅: Agent (`.claude/agents/arch-doc.md`) and skill (`arch-doc-validator`) definitions implemented for enforcement
- **Phase 3+**: Template enforcement as content is generated
- **Phase 8**: Validation pass confirming all documentation conforms to templates

## See Also

- [Architecture Overview](../architecture/)
- [Implementations Overview](../implementations/)
