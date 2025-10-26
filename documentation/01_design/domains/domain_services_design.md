# Domain Services Design

## Overview

Domain services encapsulate business logic that doesn't naturally fit within a single aggregate. They operate on multiple aggregates or implement complex algorithms.

## Core Domain Services

### WorkAssignmentService

```python
from typing import List, Optional
from dataclasses import dataclass

@dataclass
class AssignmentResult:
    """Result of work assignment."""
    agent_id: str
    match_score: float
    reason: str

class WorkAssignmentService:
    """
    Service for assigning work items to agents.

    Coordinates between WorkItem and Agent aggregates.
    """

    def __init__(self,
                 agent_matching_service: 'AgentMatchingService'):
        self.agent_matching = agent_matching_service

    def assign_work(self,
                   work_item: 'WorkItem',
                   available_agents: List['Agent'],
                   requirements: List['Requirement']) -> AssignmentResult:
        """
        Assign work item to best available agent.

        Business logic:
        1. Find agents that can execute in required environment
        2. Calculate match scores for each agent
        3. Select agent with highest score
        4. Assign to work item

        Returns assignment result with agent ID and reasoning.
        """
        # Filter by environment requirements
        capable_agents = [
            agent for agent in available_agents
            if self._can_handle_work_item(agent, work_item)
        ]

        if not capable_agents:
            raise DomainError("No capable agents available")

        # Calculate match scores
        best_agent = None
        best_score = 0.0

        for agent in capable_agents:
            score = self.agent_matching.calculate_match_score(
                agent,
                requirements
            )

            if score > best_score:
                best_score = score
                best_agent = agent

        if not best_agent or best_score < 0.5:
            raise DomainError(f"No suitable agent found (best score: {best_score})")

        # Assign to work item
        reason = self._generate_assignment_reason(best_agent, best_score, requirements)
        work_item.assign_agent(best_agent.id, reason)

        return AssignmentResult(
            agent_id=best_agent.id,
            match_score=best_score,
            reason=reason
        )

    def _can_handle_work_item(self,
                             agent: 'Agent',
                             work_item: 'WorkItem') -> bool:
        """Check if agent can handle work item."""
        # Check Docker requirements
        if agent.requires_docker and not self._has_docker_support():
            return False

        # Check if agent makes code changes matches work type
        if work_item.metadata.get("requires_code_changes") and \
           not agent.makes_code_changes:
            return False

        return True

    def _generate_assignment_reason(self,
                                   agent: 'Agent',
                                   score: float,
                                   requirements: List['Requirement']) -> str:
        """Generate human-readable assignment reasoning."""
        matched_skills = [
            req.skill for req in requirements
            if agent.has_capability(req.skill, req.min_proficiency)
        ]

        return (
            f"Assigned {agent.display_name} (match score: {score:.2f}) "
            f"with matching capabilities: {', '.join(matched_skills)}"
        )

    def _has_docker_support(self) -> bool:
        """Check if environment supports Docker."""
        # Implementation would check actual environment
        return True
```

### AgentMatchingService

```python
class AgentMatchingService:
    """
    Service for matching agents to requirements.

    Pure calculation service with no side effects.
    """

    @staticmethod
    def calculate_match_score(agent: 'Agent',
                             requirements: List['Requirement']) -> float:
        """
        Calculate match score between agent and requirements.

        Returns score from 0.0 (no match) to 1.0 (perfect match).

        Algorithm:
        1. For each requirement, calculate capability ratio
        2. Required skills must be present (0.0 if missing)
        3. Optional skills contribute to score
        4. Average all scores
        """
        if not requirements:
            return 1.0

        required_scores = []
        optional_scores = []

        for requirement in requirements:
            if agent.has_capability(requirement.skill):
                capability_score = agent.get_capability_score(requirement.skill)
                requirement_ratio = min(
                    capability_score / requirement.min_proficiency,
                    1.0
                )

                if requirement.is_required:
                    required_scores.append(requirement_ratio)
                else:
                    optional_scores.append(requirement_ratio)
            else:
                # Missing capability
                if requirement.is_required:
                    return 0.0  # Cannot satisfy required skill
                else:
                    optional_scores.append(0.0)

        # Calculate weighted average
        if not required_scores:
            required_scores = [1.0]  # No required skills

        required_avg = sum(required_scores) / len(required_scores)
        optional_avg = sum(optional_scores) / len(optional_scores) if optional_scores else 1.0

        # Weight required skills more heavily (70/30)
        return 0.7 * required_avg + 0.3 * optional_avg

    @staticmethod
    def find_best_match(agents: List['Agent'],
                       requirements: List['Requirement'],
                       min_score: float = 0.5) -> Optional['Agent']:
        """
        Find agent with highest match score above threshold.

        Returns None if no agent meets minimum score.
        """
        if not agents:
            return None

        best_agent = None
        best_score = 0.0

        for agent in agents:
            score = AgentMatchingService.calculate_match_score(
                agent,
                requirements
            )

            if score > best_score:
                best_score = score
                best_agent = agent

        return best_agent if best_score >= min_score else None

    @staticmethod
    def rank_agents(agents: List['Agent'],
                   requirements: List['Requirement']) -> List[tuple['Agent', float]]:
        """
        Rank all agents by match score.

        Returns list of (agent, score) tuples sorted by score descending.
        """
        scored_agents = [
            (agent, AgentMatchingService.calculate_match_score(agent, requirements))
            for agent in agents
        ]

        return sorted(scored_agents, key=lambda x: x[1], reverse=True)
```

### ReviewCycleService

```python
class ReviewCycleService:
    """
    Service for orchestrating review cycles.

    Coordinates review iterations between maker and reviewer agents.
    """

    def __init__(self,
                 agent_executor: 'ILLMProvider'):
        self.agent_executor = agent_executor

    async def execute_review_cycle(self,
                                   review_cycle: 'ReviewCycle',
                                   initial_prompt: str,
                                   context: 'ExecutionContext') -> 'ReviewCycle':
        """
        Execute complete review cycle.

        Business logic:
        1. Maker produces output
        2. Reviewer evaluates output
        3. If changes requested, repeat (up to max iterations)
        4. If approved or max iterations, complete
        5. If escalated, trigger human review

        Returns completed review cycle.
        """
        current_prompt = initial_prompt

        while not review_cycle.is_complete():
            # Maker iteration
            maker_result = await self._execute_maker(
                review_cycle,
                current_prompt,
                context
            )

            review_cycle.start_iteration(
                maker_output=maker_result.output,
                maker_execution_id=maker_result.execution_id
            )

            # Reviewer evaluation
            reviewer_result = await self._execute_reviewer(
                review_cycle,
                maker_result.output,
                context
            )

            # Parse reviewer feedback
            feedback = self._parse_reviewer_feedback(reviewer_result.output)

            review_cycle.submit_review(
                decision=feedback.decision,
                comment=feedback.comment,
                reviewer_execution_id=reviewer_result.execution_id,
                issues=feedback.issues,
                suggestions=feedback.suggestions
            )

            # Prepare next iteration prompt if needed
            if review_cycle.needs_maker_revision():
                current_prompt = self._build_revision_prompt(
                    original_prompt=initial_prompt,
                    previous_output=maker_result.output,
                    feedback=feedback
                )

        return review_cycle

    async def _execute_maker(self,
                            review_cycle: 'ReviewCycle',
                            prompt: str,
                            context: 'ExecutionContext') -> 'ExecutionResult':
        """Execute maker agent."""
        result = await self.agent_executor.execute_agent(
            agent_id=review_cycle.maker_agent_id,
            prompt=prompt,
            context=context
        )
        return result

    async def _execute_reviewer(self,
                               review_cycle: 'ReviewCycle',
                               maker_output: str,
                               context: 'ExecutionContext') -> 'ExecutionResult':
        """Execute reviewer agent."""
        review_prompt = self._build_review_prompt(maker_output)

        result = await self.agent_executor.execute_agent(
            agent_id=review_cycle.reviewer_agent_id,
            prompt=review_prompt,
            context=context
        )
        return result

    def _build_review_prompt(self, maker_output: str) -> str:
        """Build prompt for reviewer agent."""
        return f"""
Review the following output and provide feedback:

{maker_output}

Provide your review as:
DECISION: [APPROVE | REQUEST_CHANGES | ESCALATE]
COMMENT: Your overall feedback
ISSUES: List any issues found
SUGGESTIONS: List suggestions for improvement
"""

    def _build_revision_prompt(self,
                              original_prompt: str,
                              previous_output: str,
                              feedback: 'ReviewFeedback') -> str:
        """Build prompt for maker revision."""
        issues_text = "\n".join(f"- {issue}" for issue in feedback.issues)
        suggestions_text = "\n".join(f"- {sug}" for sug in feedback.suggestions)

        return f"""
Original task:
{original_prompt}

Your previous attempt:
{previous_output}

Reviewer feedback:
{feedback.comment}

Issues to address:
{issues_text}

Suggestions:
{suggestions_text}

Please revise your work addressing the feedback above.
"""

    def _parse_reviewer_feedback(self, output: str) -> 'ReviewFeedback':
        """Parse reviewer output into structured feedback."""
        # Implementation would parse structured output
        # This is simplified
        if "APPROVE" in output:
            decision = ReviewDecision.APPROVE
        elif "ESCALATE" in output:
            decision = ReviewDecision.ESCALATE
        else:
            decision = ReviewDecision.REQUEST_CHANGES

        return ReviewFeedback(
            decision=decision,
            comment=self._extract_comment(output),
            issues=self._extract_issues(output),
            suggestions=self._extract_suggestions(output),
            timestamp=datetime.utcnow()
        )
```

### WorkflowValidationService

```python
class WorkflowValidationService:
    """
    Service for validating workflow configurations.

    Pure validation logic with no side effects.
    """

    @staticmethod
    def validate_workflow_template(template: 'WorkflowTemplate') -> List[str]:
        """
        Validate workflow template.

        Returns list of validation errors (empty if valid).
        """
        errors = []

        # Must have at least one stage
        if not template.stage_templates:
            errors.append("Workflow must have at least one stage")
            return errors

        stage_names = {st.name for st in template.stage_templates}

        # Check dependencies
        for stage in template.stage_templates:
            for dep in stage.dependencies:
                if dep not in stage_names:
                    errors.append(
                        f"Stage '{stage.name}' has invalid dependency '{dep}'"
                    )

        # Check for cycles
        if WorkflowValidationService._has_circular_dependencies(template):
            errors.append("Workflow has circular dependencies")

        # Check review stages
        for stage in template.stage_templates:
            if stage.requires_review:
                if not stage.maker_agent_id:
                    errors.append(
                        f"Review stage '{stage.name}' missing maker agent"
                    )
                if not stage.reviewer_agent_id:
                    errors.append(
                        f"Review stage '{stage.name}' missing reviewer agent"
                    )
                if stage.maker_agent_id == stage.reviewer_agent_id:
                    errors.append(
                        f"Review stage '{stage.name}' has same maker and reviewer"
                    )

        # Check parallel stages limit
        parallel_count = sum(1 for st in template.stage_templates if st.is_parallel)
        if parallel_count > 10:
            errors.append(f"Too many parallel stages ({parallel_count}), max is 10")

        return errors

    @staticmethod
    def _has_circular_dependencies(template: 'WorkflowTemplate') -> bool:
        """Check for circular dependencies using DFS."""
        visited = set()
        rec_stack = set()

        def visit(stage_name: str) -> bool:
            visited.add(stage_name)
            rec_stack.add(stage_name)

            stage = next(
                (s for s in template.stage_templates if s.name == stage_name),
                None
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

        for stage in template.stage_templates:
            if stage.name not in visited:
                if visit(stage.name):
                    return True

        return False
```

## Service Characteristics

### 1. Stateless
Domain services have no internal state - they operate on passed parameters.

### 2. Pure Functions (where possible)
Services like AgentMatchingService use pure functions with no side effects.

### 3. Coordinate Aggregates
Services orchestrate operations across multiple aggregates.

### 4. Express Domain Logic
Services contain domain rules that don't belong to a single aggregate.

## Testing

```python
def test_agent_matching():
    agent = Agent.create(
        name="senior_engineer",
        display_name="Senior Engineer",
        agent_type=AgentType.MAKER,
        role_description="Coding",
        model="claude-sonnet-4-5",
        capabilities={
            "python": AgentCapability("python", 0.9),
            "testing": AgentCapability("testing", 0.7)
        }
    )

    requirements = [
        Requirement("python", 0.8, is_required=True),
        Requirement("testing", 0.6, is_required=True)
    ]

    score = AgentMatchingService.calculate_match_score(agent, requirements)

    assert score > 0.8  # Should have high score

def test_workflow_validation():
    template = WorkflowTemplate.create("test", "Test Template")
    template.add_stage("stage1", "agent1", dependencies=["stage2"])
    template.add_stage("stage2", "agent2", dependencies=["stage1"])

    errors = WorkflowValidationService.validate_workflow_template(template)

    assert "circular dependencies" in " ".join(errors).lower()
```

## References

- **Agent**: `agent_design.md`
- **Work Item**: `work_item_design.md`
- **Workflow**: `workflow_design.md`
- **Review Cycle**: `review_cycle_design.md`
