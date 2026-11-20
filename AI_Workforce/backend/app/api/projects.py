import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..dependencies import get_current_user, get_project_or_404
from ..models import (
    AcceptanceCriteria,
    AgentRun,
    Ambiguity,
    ArchDesign,
    Constraint,
    Dependency,
    Document,
    DocumentChunk,
    NonFunctionalRequirement,
    PMEpic,
    PMMilestone,
    PMPlan,
    PMRisk,
    PMSprint,
    PMTask,
    PMTaskDependency,
    Project,
    Requirement,
    Risk,
    User,
    UserStory,
)
from ..rag.vector_store import ProjectVectorStore
from ..schemas import ProjectCreate, ProjectResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = Project(owner_id=user.id, **payload.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("", response_model=list[ProjectResponse])
def list_projects(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(select(Project).where(Project.owner_id == user.id).order_by(Project.created_at.desc())).all()


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_project_or_404(project_id, user, db)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, user, db)

    # 1. Clean up physical uploaded files on disk
    for doc in project.documents:
        if doc.storage_path:
            try:
                path = Path(doc.storage_path)
                if path.is_file():
                    path.unlink(missing_ok=True)
            except Exception:
                logger.warning("Failed to remove document file %s", doc.storage_path, exc_info=True)

    # 2. Clean up Chroma vector collection
    try:
        store = ProjectVectorStore(get_settings())
        store.delete_project(project.id)
    except Exception:
        logger.warning("Failed to remove vector store collection for project %s", project.id, exc_info=True)

    # 3. Clean up Developer Agent workspace and metadata if present
    try:
        dev_workspace = Path(f"d:/AI-WORKFORCE/Developer_Agent/workspaces/project_{project.id}")
        if dev_workspace.is_dir():
            shutil.rmtree(dev_workspace, ignore_errors=True)
        dev_json = Path(f"d:/AI-WORKFORCE/Developer_Agent/data/projects/{project.id}.json")
        if dev_json.is_file():
            dev_json.unlink(missing_ok=True)
    except Exception:
        logger.warning("Failed to remove developer agent workspace for project %s", project.id, exc_info=True)

    # 4. Explicitly delete child records in strict dependency order
    # (prevents PostgreSQL ForeignKeyViolation e.g. pm_plans referencing agent_runs)
    db.query(PMTaskDependency).filter(PMTaskDependency.project_id == project.id).delete(synchronize_session=False)
    db.query(PMTask).filter(PMTask.project_id == project.id).delete(synchronize_session=False)
    db.query(PMEpic).filter(PMEpic.project_id == project.id).delete(synchronize_session=False)
    db.query(PMSprint).filter(PMSprint.project_id == project.id).delete(synchronize_session=False)
    db.query(PMMilestone).filter(PMMilestone.project_id == project.id).delete(synchronize_session=False)
    db.query(PMRisk).filter(PMRisk.project_id == project.id).delete(synchronize_session=False)
    db.query(PMPlan).filter(PMPlan.project_id == project.id).delete(synchronize_session=False)
    db.query(ArchDesign).filter(ArchDesign.project_id == project.id).delete(synchronize_session=False)
    db.query(AgentRun).filter(AgentRun.project_id == project.id).delete(synchronize_session=False)
    db.query(AcceptanceCriteria).filter(AcceptanceCriteria.project_id == project.id).delete(synchronize_session=False)
    db.query(UserStory).filter(UserStory.project_id == project.id).delete(synchronize_session=False)
    db.query(Requirement).filter(Requirement.project_id == project.id).delete(synchronize_session=False)
    db.query(NonFunctionalRequirement).filter(NonFunctionalRequirement.project_id == project.id).delete(synchronize_session=False)
    db.query(Dependency).filter(Dependency.project_id == project.id).delete(synchronize_session=False)
    db.query(Ambiguity).filter(Ambiguity.project_id == project.id).delete(synchronize_session=False)
    db.query(Constraint).filter(Constraint.project_id == project.id).delete(synchronize_session=False)
    db.query(Risk).filter(Risk.project_id == project.id).delete(synchronize_session=False)
    db.query(DocumentChunk).filter(DocumentChunk.project_id == project.id).delete(synchronize_session=False)
    db.query(Document).filter(Document.project_id == project.id).delete(synchronize_session=False)
    db.query(Project).filter(Project.id == project.id).delete(synchronize_session=False)
    db.commit()
    return None

