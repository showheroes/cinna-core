"""
Service layer for knowledge source management.

This service provides CRUD operations for Git-based knowledge repositories.
Git operations, parsing, and embedding generation will be implemented in a later phase.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlmodel import Session, select, func

from app.models.knowledge import (
    AIKnowledgeGitRepo,
    AIKnowledgeGitRepoCreate,
    AIKnowledgeGitRepoPublic,
    AIKnowledgeGitRepoUpdate,
    AIKnowledgeGitRepoWorkspace,
    KnowledgeArticle,
    SourceStatus,
    WorkspaceAccessType,
    CheckAccessResponse,
    RefreshKnowledgeResponse,
)


def create_source(
    *,
    session: Session,
    user_id: uuid.UUID,
    data: AIKnowledgeGitRepoCreate,
) -> AIKnowledgeGitRepoPublic:
    """
    Create a new knowledge source.

    Args:
        session: Database session
        user_id: ID of the user creating the source
        data: Source creation data

    Returns:
        Created knowledge source with public schema
    """
    # Create the main source record
    source = AIKnowledgeGitRepo(
        user_id=user_id,
        name=data.name,
        description=data.description,
        git_url=data.git_url,
        branch=data.branch,
        ssh_key_id=data.ssh_key_id,
        workspace_access_type=data.workspace_access_type,
        status=SourceStatus.pending,
    )
    session.add(source)
    session.flush()  # Get the source ID

    # Create workspace permissions if specific workspaces selected
    if data.workspace_access_type == WorkspaceAccessType.specific and data.workspace_ids:
        for workspace_id in data.workspace_ids:
            permission = AIKnowledgeGitRepoWorkspace(
                git_repo_id=source.id,
                user_workspace_id=workspace_id,
            )
            session.add(permission)

    session.commit()
    session.refresh(source)

    # Get article count (will be 0 initially)
    article_count = get_article_count(session=session, source_id=source.id)

    return AIKnowledgeGitRepoPublic(
        **source.model_dump(),
        article_count=article_count,
    )


def get_user_sources(
    *,
    session: Session,
    user_id: uuid.UUID,
    workspace_id: Optional[uuid.UUID] = None,
    skip: int = 0,
    limit: int = 100,
) -> list[AIKnowledgeGitRepoPublic]:
    """
    Get all knowledge sources for a user, optionally filtered by workspace.

    Args:
        session: Database session
        user_id: ID of the user
        workspace_id: Optional workspace ID to filter by
        skip: Number of records to skip
        limit: Maximum number of records to return

    Returns:
        List of knowledge sources
    """
    query = select(AIKnowledgeGitRepo).where(
        AIKnowledgeGitRepo.user_id == user_id
    )

    if workspace_id:
        # Filter by workspace permissions
        query = query.where(
            (AIKnowledgeGitRepo.workspace_access_type == WorkspaceAccessType.all)
            | (
                AIKnowledgeGitRepo.id.in_(
                    select(AIKnowledgeGitRepoWorkspace.git_repo_id).where(
                        AIKnowledgeGitRepoWorkspace.user_workspace_id == workspace_id
                    )
                )
            )
        )

    query = query.offset(skip).limit(limit)
    sources = session.exec(query).all()

    # Add article counts
    result = []
    for source in sources:
        article_count = get_article_count(session=session, source_id=source.id)
        result.append(
            AIKnowledgeGitRepoPublic(
                **source.model_dump(),
                article_count=article_count,
            )
        )

    return result


def get_source_by_id(
    *,
    session: Session,
    source_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Optional[AIKnowledgeGitRepoPublic]:
    """
    Get a knowledge source by ID.

    Args:
        session: Database session
        source_id: ID of the source
        user_id: ID of the user (for ownership check)

    Returns:
        Knowledge source or None if not found or not owned by user
    """
    source = session.get(AIKnowledgeGitRepo, source_id)
    if not source or source.user_id != user_id:
        return None

    article_count = get_article_count(session=session, source_id=source.id)
    return AIKnowledgeGitRepoPublic(
        **source.model_dump(),
        article_count=article_count,
    )


def update_source(
    *,
    session: Session,
    source_id: uuid.UUID,
    user_id: uuid.UUID,
    data: AIKnowledgeGitRepoUpdate,
) -> Optional[AIKnowledgeGitRepoPublic]:
    """
    Update a knowledge source.

    Args:
        session: Database session
        source_id: ID of the source
        user_id: ID of the user (for ownership check)
        data: Update data

    Returns:
        Updated knowledge source or None if not found or not owned by user
    """
    source = session.get(AIKnowledgeGitRepo, source_id)
    if not source or source.user_id != user_id:
        return None

    # Check if Git config changed (requires re-verification)
    git_config_changed = False
    if data.git_url is not None or data.branch is not None or data.ssh_key_id is not None:
        git_config_changed = True

    # Update fields
    update_data = data.model_dump(exclude_unset=True, exclude={"workspace_ids"})
    for field, value in update_data.items():
        setattr(source, field, value)

    # If Git config changed, mark as pending
    if git_config_changed:
        source.status = SourceStatus.pending
        source.status_message = "Configuration updated. Please check access."

    source.updated_at = datetime.utcnow()

    # Update workspace permissions if changed
    if data.workspace_ids is not None and data.workspace_access_type == WorkspaceAccessType.specific:
        # Delete existing permissions
        session.exec(
            select(AIKnowledgeGitRepoWorkspace).where(
                AIKnowledgeGitRepoWorkspace.git_repo_id == source_id
            )
        )
        for perm in session.exec(
            select(AIKnowledgeGitRepoWorkspace).where(
                AIKnowledgeGitRepoWorkspace.git_repo_id == source_id
            )
        ).all():
            session.delete(perm)

        # Create new permissions
        for workspace_id in data.workspace_ids:
            permission = AIKnowledgeGitRepoWorkspace(
                git_repo_id=source_id,
                user_workspace_id=workspace_id,
            )
            session.add(permission)

    session.commit()
    session.refresh(source)

    article_count = get_article_count(session=session, source_id=source.id)
    return AIKnowledgeGitRepoPublic(
        **source.model_dump(),
        article_count=article_count,
    )


def delete_source(
    *,
    session: Session,
    source_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    """
    Delete a knowledge source.

    Args:
        session: Database session
        source_id: ID of the source
        user_id: ID of the user (for ownership check)

    Returns:
        True if deleted, False if not found or not owned by user
    """
    source = session.get(AIKnowledgeGitRepo, source_id)
    if not source or source.user_id != user_id:
        return False

    session.delete(source)
    session.commit()
    return True


def enable_source(
    *,
    session: Session,
    source_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Optional[AIKnowledgeGitRepoPublic]:
    """
    Enable a knowledge source.

    Args:
        session: Database session
        source_id: ID of the source
        user_id: ID of the user (for ownership check)

    Returns:
        Updated knowledge source or None if not found or not owned by user
    """
    source = session.get(AIKnowledgeGitRepo, source_id)
    if not source or source.user_id != user_id:
        return None

    source.is_enabled = True
    source.updated_at = datetime.utcnow()
    session.commit()
    session.refresh(source)

    article_count = get_article_count(session=session, source_id=source.id)
    return AIKnowledgeGitRepoPublic(
        **source.model_dump(),
        article_count=article_count,
    )


def disable_source(
    *,
    session: Session,
    source_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Optional[AIKnowledgeGitRepoPublic]:
    """
    Disable a knowledge source.

    Args:
        session: Database session
        source_id: ID of the source
        user_id: ID of the user (for ownership check)

    Returns:
        Updated knowledge source or None if not found or not owned by user
    """
    source = session.get(AIKnowledgeGitRepo, source_id)
    if not source or source.user_id != user_id:
        return None

    source.is_enabled = False
    source.updated_at = datetime.utcnow()
    session.commit()
    session.refresh(source)

    article_count = get_article_count(session=session, source_id=source.id)
    return AIKnowledgeGitRepoPublic(
        **source.model_dump(),
        article_count=article_count,
    )


def check_access(
    *,
    session: Session,
    source_id: uuid.UUID,
    user_id: uuid.UUID,
) -> CheckAccessResponse:
    """
    Check if the Git repository is accessible.

    NOTE: This is a stub implementation. Actual Git operations will be implemented later.

    Args:
        session: Database session
        source_id: ID of the source
        user_id: ID of the user (for ownership check)

    Returns:
        Access check response
    """
    source = session.get(AIKnowledgeGitRepo, source_id)
    if not source or source.user_id != user_id:
        return CheckAccessResponse(
            accessible=False,
            message="Source not found or access denied",
        )

    # TODO: Implement actual Git access check
    # For now, just update the status to connected
    source.status = SourceStatus.connected
    source.status_message = "Access check not yet implemented. Marked as connected."
    source.last_checked_at = datetime.utcnow()
    source.updated_at = datetime.utcnow()
    session.commit()

    return CheckAccessResponse(
        accessible=True,
        message="Access check not yet implemented. Source marked as connected.",
    )


def refresh_knowledge(
    *,
    session: Session,
    source_id: uuid.UUID,
    user_id: uuid.UUID,
) -> RefreshKnowledgeResponse:
    """
    Trigger knowledge refresh from Git repository.

    NOTE: This is a stub implementation. Actual Git operations, parsing,
    and embedding generation will be implemented later.

    Args:
        session: Database session
        source_id: ID of the source
        user_id: ID of the user (for ownership check)

    Returns:
        Refresh response
    """
    source = session.get(AIKnowledgeGitRepo, source_id)
    if not source or source.user_id != user_id:
        return RefreshKnowledgeResponse(
            status="error",
            message="Source not found or access denied",
        )

    if not source.is_enabled:
        return RefreshKnowledgeResponse(
            status="error",
            message="Source is disabled. Enable it first to refresh knowledge.",
        )

    # TODO: Implement actual Git clone, parse, and embedding generation
    # For now, just update the last sync timestamp
    source.last_sync_at = datetime.utcnow()
    source.updated_at = datetime.utcnow()
    session.commit()

    return RefreshKnowledgeResponse(
        status="success",
        message="Knowledge refresh not yet implemented. Timestamp updated.",
    )


def get_article_count(
    *,
    session: Session,
    source_id: uuid.UUID,
) -> int:
    """
    Get the count of articles for a knowledge source.

    Args:
        session: Database session
        source_id: ID of the source

    Returns:
        Number of articles
    """
    count = session.exec(
        select(func.count()).select_from(KnowledgeArticle).where(
            KnowledgeArticle.git_repo_id == source_id
        )
    ).one()
    return count


def get_source_articles(
    *,
    session: Session,
    source_id: uuid.UUID,
    user_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100,
) -> Optional[list[KnowledgeArticle]]:
    """
    Get articles for a knowledge source.

    Args:
        session: Database session
        source_id: ID of the source
        user_id: ID of the user (for ownership check)
        skip: Number of records to skip
        limit: Maximum number of records to return

    Returns:
        List of articles or None if source not found or not owned by user
    """
    source = session.get(AIKnowledgeGitRepo, source_id)
    if not source or source.user_id != user_id:
        return None

    articles = session.exec(
        select(KnowledgeArticle)
        .where(KnowledgeArticle.git_repo_id == source_id)
        .offset(skip)
        .limit(limit)
    ).all()

    return list(articles)
