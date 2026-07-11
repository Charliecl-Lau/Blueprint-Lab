from sqlalchemy.exc import IntegrityError


def fields(version="v1"):
    return {"name": "Syllabus", "document_type": "course_syllabus", "version": version, "description": "Current"}


def test_upload_metadata_excludes_content_and_download_returns_original(client):
    content = b"exact source bytes"
    response = client.post("/source-documents", data=fields(), files={"file": ("course.txt", content, "text/plain")})
    assert response.status_code == 201
    metadata = response.json()
    assert "content" not in metadata and metadata["original_filename"] == "course.txt"
    assert client.get(f"/source-documents/{metadata['id']}").json() == metadata
    download = client.get(f"/source-documents/{metadata['id']}/download")
    assert download.content == content
    assert 'filename="course.txt"' in download.headers["content-disposition"]


def test_identical_metadata_and_hash_is_conflict_but_other_version_is_separate(client):
    upload = lambda version: client.post("/source-documents", data=fields(version), files={"file": ("course.txt", b"same", "text/plain")})
    assert upload("v1").status_code == 201
    duplicate = upload("v1")
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "duplicate_source_version"
    assert upload("v2").status_code == 201


def test_validation_error_has_stable_code(client):
    response = client.post("/source-documents", data=fields(), files={"file": ("x.png", b"x", "image/png")})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "unsupported_source_document_media_type"


def test_oversized_upload_has_stable_code(client):
    response = client.post("/source-documents", data=fields(),
        files={"file": ("huge.txt", b"x" * (20 * 1024 * 1024 + 1), "text/plain")})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "source_document_too_large"


def test_integrity_race_returns_duplicate_and_rolls_back(client, test_db, monkeypatch):
    import backend.api.source_documents as api
    rolled_back = False
    original = test_db.rollback
    def rollback():
        nonlocal rolled_back
        rolled_back = True
        original()
    monkeypatch.setattr(test_db, "rollback", rollback)
    monkeypatch.setattr(api, "create_source_document", lambda *args, **kwargs:
        (_ for _ in ()).throw(IntegrityError("insert", {}, Exception("unique"))))
    response = client.post("/source-documents", data=fields(), files={"file": ("x.txt", b"x", "text/plain")})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "duplicate_source_version"
    assert rolled_back


def test_download_filename_cannot_inject_headers(client):
    filename = 'evil"\r\nX-Injected: yes\u2603.txt'
    upload = client.post("/source-documents", data=fields(), files={"file": (filename, b"safe", "text/plain")})
    assert upload.status_code == 201
    response = client.get(f"/source-documents/{upload.json()['id']}/download")
    disposition = response.headers["content-disposition"]
    assert "\r" not in disposition and "\n" not in disposition
    assert "%0D" not in disposition.split("filename*=", 1)[0]
    assert "%0A" not in disposition.split("filename*=", 1)[0]
    assert "filename*=UTF-8''" in disposition
