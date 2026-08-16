"""V2.1 文档解析、幂等导入与 Story Worker 测试。"""
from __future__ import annotations

from io import BytesIO
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import CreativeJob, SourceChapter, SourceDocument, SourceParagraph
from app.short_drama.parsers import parse_document
from app.short_drama.worker import story_worker

client = TestClient(app)


def _zip(files: dict[str, str]) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


def _login(username: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _new_user() -> dict[str, str]:
    admin = _login("admin", "admin123")
    username = f"import-{uuid4().hex[:12]}"
    response = client.post("/api/v1/users", headers=admin, json={"username": username, "password": "user12345", "role": "user"})
    assert response.status_code == 201
    return _login(username, "user12345")


def _project(headers: dict[str, str]) -> int:
    response = client.post("/api/v2/short-drama/projects", headers=headers, json={"name": "导入测试", "source_type": "novel"})
    assert response.status_code == 201
    return response.json()["id"]


def test_standard_library_parsers_cover_txt_docx_and_epub() -> None:
    txt = parse_document("作品名\n\n第一章 开端\n\n第一段。\n\n第二段。".encode(), "story.txt")
    assert txt.source_format == "txt"
    assert txt.total_paragraphs == 2

    docx = _zip({
        "word/document.xml": """<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>第一章</w:t></w:r></w:p><w:p><w:r><w:t>DOCX 正文。</w:t></w:r></w:p></w:body></w:document>""",
        "docProps/core.xml": """<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>DOCX 作品</dc:title></cp:coreProperties>""",
    })
    parsed_docx = parse_document(docx, "story.docx")
    assert parsed_docx.title == "DOCX 作品"
    assert parsed_docx.chapters[0].paragraphs == ["DOCX 正文。"]

    epub = _zip({
        "META-INF/container.xml": """<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>""",
        "OEBPS/content.opf": """<package xmlns:dc="http://purl.org/dc/elements/1.1/"><metadata><dc:title>EPUB 作品</dc:title></metadata><manifest><item id="c1" href="c1.xhtml"/></manifest><spine><itemref idref="c1"/></spine></package>""",
        "OEBPS/c1.xhtml": "<html><body><h1>第一章</h1><p>EPUB 正文。</p></body></html>",
    })
    parsed_epub = parse_document(epub, "story.epub")
    assert parsed_epub.title == "EPUB 作品"
    assert parsed_epub.chapters[0].title == "第一章"


def test_document_import_is_idempotent_and_worker_persists_structure() -> None:
    headers = _new_user()
    project_id = _project(headers)
    content = "测试小说\n\n第一章 相遇\n\n清晨，两人在车站相遇。\n\n第二段。".encode()
    first = client.post(
        f"/api/v2/short-drama/projects/{project_id}/imports",
        headers=headers,
        files={"file": ("novel.txt", content, "text/plain")},
    )
    assert first.status_code == 202, first.text
    second = client.post(
        f"/api/v2/short-drama/projects/{project_id}/imports",
        headers=headers,
        files={"file": ("novel.txt", content, "text/plain")},
    )
    assert second.status_code == 202
    assert second.json()["document"]["id"] == first.json()["document"]["id"]
    assert second.json()["job"]["id"] == first.json()["job"]["id"]

    job_id = first.json()["job"]["id"]
    with SessionLocal() as db:
        job = db.get(CreativeJob, job_id)
        assert job is not None
        job.status = "running"
        db.commit()
    story_worker._process(job_id)

    result = client.get(f"/api/v2/short-drama/jobs/{job_id}", headers=headers)
    assert result.status_code == 200
    assert result.json()["status"] == "succeeded"
    assert result.json()["progress"] == 100
    documents = client.get(f"/api/v2/short-drama/projects/{project_id}/documents", headers=headers).json()
    assert documents[0]["status"] == "ready"
    assert documents[0]["total_chapters"] == 1
    assert documents[0]["total_paragraphs"] == 2
    with SessionLocal() as db:
        assert db.query(SourceDocument).filter(SourceDocument.id == documents[0]["id"]).count() == 1
        assert db.query(SourceChapter).filter(SourceChapter.document_id == documents[0]["id"]).count() == 1
        assert db.query(SourceParagraph).count() >= 2


def test_creative_job_cancel_retry_and_owner_isolation() -> None:
    owner = _new_user()
    stranger = _new_user()
    project_id = _project(owner)
    response = client.post(
        f"/api/v2/short-drama/projects/{project_id}/imports",
        headers=owner,
        files={"file": ("cancel.txt", "一段待取消内容。".encode(), "text/plain")},
    )
    job_id = response.json()["job"]["id"]
    assert client.get(f"/api/v2/short-drama/jobs/{job_id}", headers=stranger).status_code == 404
    cancelled = client.post(f"/api/v2/short-drama/jobs/{job_id}/cancel", headers=owner)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    retried = client.post(f"/api/v2/short-drama/jobs/{job_id}/retry", headers=owner)
    assert retried.status_code == 200
    assert retried.json()["status"] == "queued"
    assert retried.json()["retries"] == 1
    blocked_delete = client.delete(f"/api/v2/short-drama/projects/{project_id}", headers=owner)
    assert blocked_delete.status_code == 409
