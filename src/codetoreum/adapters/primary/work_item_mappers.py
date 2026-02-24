"""
Work Item DTO Mappers

Maps between domain models and API DTOs for work items.
This keeps the domain layer independent of API concerns.
"""


from codetoreum.adapters.primary.work_item_dtos import (
    CreateWorkItemRequest,
    UpdateWorkItemRequest,
    WorkItemCommandResult,
    WorkItemDetailResponse,
    WorkItemListResponse,
    WorkItemResponse,
)
from codetoreum.domain.work_item import WorkItem, WorkItemPriority
from codetoreum.ports.input.work_item_command import (
    CreateWorkItemCommand,
    UpdateWorkItemCommand,
)
from codetoreum.ports.input.work_item_command import (
    WorkItemCommandResult as DomainCommandResult,
)
from codetoreum.ports.input.work_item_query import (
    WorkItemHistory,
    WorkItemListResult,
)


class WorkItemMapper:
    """Maps between Work Item domain models and API DTOs"""

    @staticmethod
    def to_create_command(dto: CreateWorkItemRequest) -> CreateWorkItemCommand:
        """
        Convert CreateWorkItemRequest DTO to CreateWorkItemCommand.

        Args:
            dto: Request DTO from API

        Returns:
            Domain command object
        """
        # Parse priority
        priority = WorkItemPriority[dto.priority.upper()]

        return CreateWorkItemCommand(
            project_id=dto.project_id,
            title=dto.title,
            description=dto.description,
            labels=dto.labels,
            priority=priority,
            external_id=dto.external_id,
            external_url=dto.external_url,
        )

    @staticmethod
    def to_update_command(work_item_id: str, dto: UpdateWorkItemRequest) -> UpdateWorkItemCommand:
        """
        Convert UpdateWorkItemRequest DTO to UpdateWorkItemCommand.

        Args:
            work_item_id: Work item ID
            dto: Request DTO from API

        Returns:
            Domain command object
        """
        # Parse priority if provided
        priority = None
        if dto.priority:
            priority = WorkItemPriority[dto.priority.upper()]

        return UpdateWorkItemCommand(
            work_item_id=work_item_id,
            title=dto.title,
            description=dto.description,
            labels=dto.labels,
            priority=priority,
        )

    @staticmethod
    def to_response(work_item: WorkItem) -> WorkItemResponse:
        """
        Convert WorkItem domain model to WorkItemResponse DTO.

        Args:
            work_item: Domain model

        Returns:
            Response DTO for API
        """
        return WorkItemResponse(
            id=work_item.id,
            project_id=work_item.project_id,
            title=work_item.title,
            description=work_item.description,
            status=work_item.status.value,
            priority=work_item.priority.name,  # Use name for enum
            labels=work_item.labels.copy(),  # Copy to prevent mutation
            external_id=work_item.external_id,
            external_url=work_item.external_url,
            assigned_agent_id=work_item.assigned_agent_id,
            assigned_at=work_item.assigned_at,
            current_workflow_id=work_item.current_workflow_id,
            current_stage=work_item.current_stage,
            created_at=work_item.created_at,
            updated_at=work_item.updated_at,
            completed_at=work_item.completed_at,
        )

    @staticmethod
    def to_detail_response(work_item: WorkItem, history: WorkItemHistory) -> WorkItemDetailResponse:
        """
        Convert WorkItem and history to WorkItemDetailResponse DTO.

        Args:
            work_item: Domain model
            history: Work item history with events

        Returns:
            Detailed response DTO for API
        """
        return WorkItemDetailResponse(
            id=work_item.id,
            project_id=work_item.project_id,
            title=work_item.title,
            description=work_item.description,
            status=work_item.status.value,
            priority=work_item.priority.name,
            labels=work_item.labels.copy(),
            external_id=work_item.external_id,
            external_url=work_item.external_url,
            assigned_agent_id=work_item.assigned_agent_id,
            assigned_at=work_item.assigned_at,
            current_workflow_id=work_item.current_workflow_id,
            current_stage=work_item.current_stage,
            created_at=work_item.created_at,
            updated_at=work_item.updated_at,
            completed_at=work_item.completed_at,
            history_event_count=history.total_events,
            recent_events=history.events[:10],  # Last 10 events
        )

    @staticmethod
    def to_list_response(result: WorkItemListResult) -> WorkItemListResponse:
        """
        Convert WorkItemListResult to WorkItemListResponse DTO.

        Args:
            result: Query result from domain

        Returns:
            List response DTO for API
        """
        return WorkItemListResponse(
            work_items=[
                WorkItemMapper.to_response(wi) for wi in result.work_items
            ],
            total_count=result.total_count,
            page=0,  # Will be set by endpoint based on offset/limit
            page_size=result.limit,
            has_next=result.has_next,
        )

    @staticmethod
    def to_command_result(result: DomainCommandResult) -> WorkItemCommandResult:
        """
        Convert domain command result to API command result.

        Args:
            result: Domain command result

        Returns:
            API command result DTO
        """
        return WorkItemCommandResult(
            success=result.success,
            work_item_id=result.work_item_id,
            message=result.message,
            errors=result.errors,
        )
