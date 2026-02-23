"""Workflow Template entity and value objects."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from uuid import uuid4

if TYPE_CHECKING:
    from codetoreum.domain.workflow import Workflow

from codetoreum.domain.exceptions import DomainError
from codetoreum.domain.pipeline_stage import PipelineStage, StageType


@dataclass
class StageTemplate:
    """Template for a pipeline stage."""

    name: str
    agent_id: str
    stage_type: str  # "sequential", "parallel", "review"
    dependencies: List[str]
    is_parallel: bool
    maker_agent_id: Optional[str]
    reviewer_agent_id: Optional[str]
    max_review_iterations: int
    metadata: Dict[str, Any] = field(default_factory=dict)


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
    def create(
        cls,
        name: str,
        display_name: str,
        description: str = "",
        is_default: bool = False,
    ) -> "WorkflowTemplate":
        """
        Create new workflow template.

        Args:
            name: Template name (identifier)
            display_name: Human-readable template name
            description: Template description (default: "")
            is_default: Whether this is the default template (default: False)

        Returns:
            Newly created WorkflowTemplate instance
        """
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
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    def add_stage(
        self,
        name: str,
        agent_id: str,
        stage_type: str = "sequential",
        dependencies: Optional[List[str]] = None,
        is_parallel: bool = False,
        maker_agent_id: Optional[str] = None,
        reviewer_agent_id: Optional[str] = None,
    ) -> StageTemplate:
        """
        Add stage to template.

        Args:
            name: Stage name
            agent_id: ID of agent to execute stage
            stage_type: Type of stage (default: "sequential")
            dependencies: List of dependency stage names (default: [])
            is_parallel: Whether stage can run in parallel (default: False)
            maker_agent_id: ID of maker agent for review stages (default: None)
            reviewer_agent_id: ID of reviewer agent for review stages (default: None)

        Returns:
            The created StageTemplate
        """
        stage = StageTemplate(
            name=name,
            agent_id=agent_id,
            stage_type=stage_type,
            dependencies=dependencies or [],
            is_parallel=is_parallel,
            maker_agent_id=maker_agent_id,
            reviewer_agent_id=reviewer_agent_id,
            max_review_iterations=3,
            metadata={},
        )

        self.stage_templates.append(stage)
        self.updated_at = datetime.now(timezone.utc)

        return stage

    def instantiate_workflow(self, work_item_id: str, project_id: str) -> "Workflow":
        """
        Instantiate a workflow from this template.

        Args:
            work_item_id: ID of the work item
            project_id: ID of the project

        Returns:
            Newly created Workflow instance

        Note:
            This method is the primary way to create workflows from templates.
            It handles creating pipeline stages and initializing the workflow.
        """
        from codetoreum.domain.workflow import Workflow

        return Workflow.create(
            work_item_id=work_item_id,
            template=self,
            project_id=project_id,
        )

    def build_stages(self) -> List[PipelineStage]:
        """
        Build concrete pipeline stages from template.

        Internal method used by Workflow.create() to construct stages.

        Returns:
            List of PipelineStage instances
        """
        stages = []
        for template in self.stage_templates:
            stage = PipelineStage.create(
                name=template.name,
                workflow_id="",  # Set by workflow
                agent_config={"agent_id": template.agent_id},
                stage_type=StageType(template.stage_type),
                dependencies=template.dependencies,
                is_parallel=template.is_parallel,
                maker_agent_id=template.maker_agent_id,
                reviewer_agent_id=template.reviewer_agent_id,
                max_review_iterations=template.max_review_iterations,
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

        Returns:
            True if template is valid

        Raises:
            DomainError: If template is invalid
        """
        stage_names = {st.name for st in self.stage_templates}

        # Check dependencies exist
        for stage in self.stage_templates:
            for dep in stage.dependencies:
                if dep not in stage_names:
                    raise DomainError(f"Invalid dependency: {dep} not found")

        # Check review stages
        for stage in self.stage_templates:
            if stage.stage_type == "review":
                if not stage.maker_agent_id or not stage.reviewer_agent_id:
                    raise DomainError(
                        f"Review stage {stage.name} missing agents"
                    )
                if stage.maker_agent_id == stage.reviewer_agent_id:
                    raise DomainError(
                        f"Review stage {stage.name} has same maker and reviewer"
                    )

        # Check for cycles
        if self._has_cycles():
            raise DomainError("Template has circular dependencies")

        return True

    def _has_cycles(self) -> bool:
        """
        Check for circular dependencies.

        Returns:
            True if circular dependencies exist
        """
        visited = set()
        rec_stack = set()

        def visit(stage_name: str) -> bool:
            visited.add(stage_name)
            rec_stack.add(stage_name)

            stage = next(
                (s for s in self.stage_templates if s.name == stage_name), None
            )
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
