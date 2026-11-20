from pathlib import Path
from sqlalchemy import select

from app.models import Document, Project, Requirement


def test_delete_project_requires_authentication(client, make_user, make_project):
    user = make_user()
    project_id = make_project(user, name="To Delete Unauth")
    res = client.delete(f"/api/projects/{project_id}")
    assert res.status_code == 401


def test_delete_project_not_found(client, make_user):
    user = make_user()
    res = client.delete("/api/projects/99999", headers=user["headers"])
    assert res.status_code == 404


def test_delete_other_user_project_forbidden(client, make_user, make_project):
    user1 = make_user()
    user2 = make_user()
    project_id = make_project(user1, name="User1 Project")
    res = client.delete(f"/api/projects/{project_id}", headers=user2["headers"])
    assert res.status_code == 404


def test_delete_project_cascades_and_removes_records(client, db, make_user, make_project, seed_requirements, tmp_path):
    user = make_user()
    project_id = make_project(user, name="Project with Data")
    seed_requirements(project_id)

    # Add a document with a temporary file on disk
    test_file = tmp_path / "test_srs.pdf"
    test_file.write_bytes(b"%PDF-1.4 test content")

    doc = Document(
        project_id=project_id,
        filename="test_srs.pdf",
        file_type="application/pdf",
        file_size=len(test_file.read_bytes()),
        storage_path=str(test_file),
        processing_status="COMPLETED",
    )
    db.add(doc)
    db.commit()

    assert test_file.exists()
    assert db.scalar(select(Project).where(Project.id == project_id)) is not None
    assert len(db.scalars(select(Requirement).where(Requirement.project_id == project_id)).all()) > 0
    assert len(db.scalars(select(Document).where(Document.project_id == project_id)).all()) > 0

    # Delete the project
    res = client.delete(f"/api/projects/{project_id}", headers=user["headers"])
    assert res.status_code == 204

    # Verify project is gone via API
    get_res = client.get(f"/api/projects/{project_id}", headers=user["headers"])
    assert get_res.status_code == 404

    # Verify cascades in DB
    assert db.scalar(select(Project).where(Project.id == project_id)) is None
    assert len(db.scalars(select(Requirement).where(Requirement.project_id == project_id)).all()) == 0
    assert len(db.scalars(select(Document).where(Document.project_id == project_id)).all()) == 0

    # Verify disk file was deleted
    assert not test_file.exists()
