# Workflow Template Domain Design

## Overview

Workflow Template is an entity defining reusable workflow structures and patterns that can be instantiated into concrete workflows.

## Domain Model

```python
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
from uuid import uuid4

@dataclass
class StageTemplate:
    """Template for a pipeline stage."""
    name: str
    agent_id: str
    stage_type: str  # "sequential", "parallel", "review"
    dependencies: List[str]
    is_parallel: bool
    requires_review: bool
    maker_agent_id: Optional[str]
    reviewer_agent_id: Optional[str]
    max_review_iterations: int
    metadata: Dict[str, Any]

@dataclass
class WorkflowTemplate:
    """
    Workflow Template entity.

    Defines the structure of a workflow that can be instantiated.
    """

    # Identity
    id: str
    name: str
    display_name: str
    description: str

    # Template definition
    stage_templates: List[StageTemplate]

    # Configuration
    version: int
    is_default: bool
    applicable_labels: List[str]  # Which work item labels trigger this template

    # Metadata
    metadata: Dict[str, Any]

    # Timestamps
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(cls,
               name: str,
               display_name: str,
               description: str = "",
               is_default: bool = False) -> 'WorkflowTemplate':
        """Create new workflow template."""
        return cls(
            id=str(uuid4()),
            name=name,
            display_name=display_name,
            description=description,
            stage_templates=[],
            version=1,
            is_default=is_default,
            applicable_labels=[],
            metadata={},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

    def add_stage(self,
                  name: str,
                  agent_id: str,
                  stage_type: str = "sequential",
                  dependencies: Optional[List[str]] = None,
                  is_parallel: bool = False,
                  requires_review: bool = False,
                  maker_agent_id: Optional[str] = None,
                  reviewer_agent_id: Optional[str] = None) -> 'StageTemplate':
        """Add stage to template."""
        stage = StageTemplate(
            name=name,
            agent_id=agent_id,
            stage_type=stage_type,
            dependencies=dependencies or [],
            is_parallel=is_parallel,
            requires_review=requires_review,
            maker_agent_id=maker_agent_id,
            reviewer_agent_id=reviewer_agent_id,
            max_review_iterations=3,
            metadata={}
        )

        self.stage_templates.append(stage)
        self.updated_at = datetime.utcnow()

        return stage

    def build_stages(self) -> List['PipelineStage']:
        """
        Build concrete pipeline stages from template.

        Used when instantiating a workflow.
        """
        from .pipeline_stage_design import PipelineStage, StageType

        stages = []
        for template in self.stage_templates:
            stage = PipelineStage.create(
                name=template.name,
                workflow_id="",  # Set by workflow
                agent_id=template.agent_id,
                stage_type=StageType(template.stage_type),
                dependencies=template.dependencies,
                is_parallel=template.is_parallel,
                requires_review=template.requires_review,
                maker_agent_id=template.maker_agent_id,
                reviewer_agent_id=template.reviewer_agent_id,
                max_review_iterations=template.max_review_iterations
            )
            stages.append(stage)

        return stages

    def validate(self) -> bool:
        """
        Validate template consistency.

        Checks:
        - No circular dependencies
        - All dependencies reference valid stages
        - Review stages have required agents
        """
        stage_names = {st.name for st in self.stage_templates}

        # Check dependencies exist
        for stage in self.stage_templates:
            for dep in stage.dependencies:
                if dep not in stage_names:
                    raise DomainError(f"Invalid dependency: {dep} not found")

        # Check review stages
        for stage in self.stage_templates:
            if stage.requires_review:
                if not stage.maker_agent_id or not stage.reviewer_agent_id:
                    raise DomainError(f"Review stage {stage.name} missing agents")
                if stage.maker_agent_id == stage.reviewer_agent_id:
                    raise DomainError(f"Review stage {stage.name} has same maker and reviewer")

        # Check for cycles
        if self._has_cycles():
            raise DomainError("Template has circular dependencies")

        return True

    def _has_cycles(self) -> bool:
        """Check for circular dependencies."""
        visited = set()
        rec_stack = set()

        def visit(stage_name: str) -> bool:
            visited.add(stage_name)
            rec_stack.add(stage_name)

            stage = next((s for s in self.stage_templates if s.name == stage_name), None)
            if stage:
                for dep in stage.dependencies:
                    if dep not in visited:
                        if visit(dep):
                            return True
                    elif dep in rec_stack:
                        return True

            rec_stack.remove(stage_name)
            return False

        for stage in self.stage_templates:
            if stage.name not in visited:
                if visit(stage.name):
                    return True

        return False
```

## Common Templates

### Basic Sequential Template
```python
template = WorkflowTemplate.create("basic", "Basic Sequential Workflow")
template.add_stage("analysis", "business_analyst")
template.add_stage("coding", "senior_engineer", dependencies=["analysis"])
template.add_stage("testing", "test_engineer", dependencies=["coding"])
```

### Review Cycle Template
```python
template = WorkflowTemplate.create("with-review", "Workflow with Review")
template.add_stage("analysis", "business_analyst")
template.add_stage("coding", "senior_engineer",
                  dependencies=["analysis"],
                  requires_review=True,
                  maker_agent_id="senior_engineer",
                  reviewer_agent_id="tech_lead")
```

### Parallel Stages Template
```python
template = WorkflowTemplate.create("parallel", "Parallel Testing")
template.add_stage("coding", "senior_engineer")
template.add_stage("unit_tests", "test_engineer",
                  dependencies=["coding"], is_parallel=True)
template.add_stage("integration_tests", "test_engineer",
                  dependencies=["coding"], is_parallel=True)
```

## Business Rules

1. Must have at least one stage
2. No circular dependencies
3. All dependencies must reference valid stages
4. Review stages require different maker and reviewer
5. Version incremented on changes

## Testing

```python
def test_template_validation():
    template = WorkflowTemplate.create("test", "Test Template")
    template.add_stage("stage1", "agent1", dependencies=["stage2"])
    template.add_stage("stage2", "agent2", dependencies=["stage1"])

    with pytest.raises(DomainError):
        template.validate()  # Circular dependency

def test_build_stages():
    template = WorkflowTemplate.create("test", "Test")
    template.add_stage("stage1", "agent1")
    template.add_stage("stage2", "agent2", dependencies=["stage1"])

    stages = template.build_stages()
    assert len(stages) == 2
    assert stages[1].dependencies == ["stage1"]
```

## References

- **Workflow**: `workflow_design.md`
- **Pipeline Stage**: `pipeline_stage_design.md`
