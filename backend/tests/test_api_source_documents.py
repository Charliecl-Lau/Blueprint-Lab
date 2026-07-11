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
