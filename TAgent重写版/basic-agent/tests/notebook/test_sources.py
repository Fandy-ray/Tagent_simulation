"""来源接口：文本 / 上传 / 网址，同步与异步、状态、重试、下载、删除、排序分页、洞察。"""

from __future__ import annotations

import http.server
import io
import threading

import pytest

from tests.notebook.conftest import new_notebook, text_source, wait_job

LIST_KEYS = {"id", "title", "topics", "asset", "embedded", "embedded_chunks", "insights_count", "created",
             "updated", "file_available", "command_id", "status", "processing_info"}


def make_pdf(text: str) -> bytes:
    content = f"BT /F1 18 Tf 20 100 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return out


def upload(client, notebook_id, name, data: bytes, **extra):
    form = {"type": "upload", "notebook_id": notebook_id, "embed": "true", **extra,
            "file": (io.BytesIO(data), name)}
    return client.post("/api/sources", data=form, content_type="multipart/form-data")


def test_text_source_sync_shape_and_title(client):
    nid = new_notebook(client)
    source = text_source(client, nid, "# 二叉树\n\n二叉树每个节点最多有两个孩子。")
    assert source["title"] == "二叉树"
    assert source["full_text"].startswith("# 二叉树") and source["notebooks"] == [nid]
    assert source["status"] == "completed" and source["embedded"] is True and source["embedded_chunks"] == 1
    assert source["asset"] is None and source["file_available"] is None
    listed = client.get(f"/api/sources?notebook_id={nid}").get_json()
    assert set(listed[0]) == LIST_KEYS
    assert listed[0]["processing_info"]["status"] == "completed"
    named = text_source(client, nid, "正文", title="自己起的标题")
    assert named["title"] == "自己起的标题"


def test_text_source_async_and_status(client):
    nid = new_notebook(client)
    created = client.post("/api/sources", data={"type": "text", "content": "异步处理的内容", "notebook_id": nid,
                                                "async_processing": "true"}).get_json()
    assert created["status"] == "new" and created["processing_info"] == {"async": True, "queued": True}
    assert created["title"] == "Processing..."
    assert wait_job(client, created["command_id"])["status"] == "completed"
    status = client.get(f"/api/sources/{created['id']}/status").get_json()
    assert status["status"] == "completed" and status["message"] == "Source processing completed successfully"
    assert status["processing_info"]["completed_at"]
    detail = client.get(f"/api/sources/{created['id']}").get_json()
    assert detail["title"] == "异步处理的内容" and detail["embedded"] is False


def test_source_validation(client):
    nid = new_notebook(client)
    assert client.post("/api/sources", data={"type": "text", "notebook_id": nid}).status_code == 400
    assert client.post("/api/sources", data={"type": "video"}).status_code == 422
    assert client.post("/api/sources", data={"type": "link"}).status_code == 400
    assert client.post("/api/sources", data={"type": "upload", "notebook_id": nid}).status_code == 400
    assert client.post("/api/sources", data={"type": "text", "content": "x",
                                             "notebook_id": "notebook:none"}).status_code == 404
    assert client.post("/api/sources", data={"type": "text", "content": "x", "notebook_id": nid,
                                             "notebooks": f'["{nid}"]'}).status_code == 422
    assert client.post("/api/sources", data={"type": "text", "content": "x", "notebooks": "not-json"}).status_code == 422
    assert client.post("/api/sources", data={"type": "text", "content": "x", "notebook_id": nid,
                                             "transformations": '["transformation:nope"]'}).status_code == 404
    assert client.post("/api/sources", data={"type": "link", "url": "http://127.0.0.1:5055/api/notebooks",
                                             "notebook_id": nid}).status_code == 400
    assert client.post("/api/sources/json", json={"type": "upload", "file_path": "/etc/passwd",
                                                  "notebook_id": nid}).status_code == 400


def test_upload_formats_and_filename_safety(client, app):
    nid = new_notebook(client)
    upload_dir = app.extensions["notebook_services"].settings.upload_dir
    md = upload(client, nid, "../../笔记.md", "# 标题\n\n内容 Markdown".encode()).get_json()
    assert md["asset"]["file_path"] == str(upload_dir / "笔记.md")
    assert md["title"] == "笔记" and "内容 Markdown" in md["full_text"] and md["file_available"] is True
    again = upload(client, nid, "笔记.md", b"second").get_json()
    assert again["asset"]["file_path"].endswith("笔记 (1).md")

    pdf = upload(client, nid, "paper.pdf", make_pdf("Hello PDF World")).get_json()
    assert "Hello PDF World" in pdf["full_text"]
    html = upload(client, nid, "page.html", "<title>网页标题</title><p>网页正文</p>".encode()).get_json()
    assert html["title"] == "网页标题" and "网页正文" in html["full_text"]

    response = upload(client, nid, "song.mp3", b"ID3")
    assert response.status_code == 415
    assert not (upload_dir / "song.mp3").exists()
    broken = upload(client, nid, "broken.pdf", b"%PDF-garbage")
    assert broken.status_code == 400
    assert not (upload_dir / "broken.pdf").exists()


def test_upload_too_large(client):
    nid = new_notebook(client)
    assert upload(client, nid, "big.txt", b"x" * (6 * 1024 * 1024)).status_code == 413


def test_download_delete_and_file_cleanup(client, app):
    nid = new_notebook(client)
    source = upload(client, nid, "资料.txt", "下载测试".encode()).get_json()
    response = client.get(f"/api/sources/{source['id']}/download")
    assert response.status_code == 200 and response.data == "下载测试".encode()
    assert "attachment" in response.headers["Content-Disposition"]
    assert client.head(f"/api/sources/{source['id']}/download").status_code == 200
    text_only = text_source(client, nid, "没有文件")
    assert client.get(f"/api/sources/{text_only['id']}/download").status_code == 404

    path = app.extensions["notebook_services"].settings.upload_dir / "资料.txt"
    assert path.exists()
    assert client.delete(f"/api/sources/{source['id']}").status_code == 200
    assert not path.exists()
    assert client.get(f"/api/sources/{source['id']}").status_code == 404
    assert client.delete(f"/api/sources/{source['id']}").status_code == 404


def test_update_retry_and_listing(client):
    nid = new_notebook(client)
    first = text_source(client, nid, "第一份资料 alpha")
    second = text_source(client, nid, "第二份资料 beta")
    updated = client.put(f"/api/sources/{first['id']}", json={"title": "改名后的标题", "topics": ["树", " "]}).get_json()
    assert updated["title"] == "改名后的标题" and updated["topics"] == ["树"]
    assert client.put(f"/api/sources/{first['id']}", json={"title": " "}).status_code == 400
    hits = client.post("/api/search", json={"query": "改名", "type": "text"}).get_json()["results"]
    assert hits and hits[0]["id"] == first["id"]

    titles = [s["title"] for s in client.get(f"/api/sources?notebook_id={nid}&sort_by=title&sort_order=asc").get_json()]
    assert titles == sorted(titles, key=str.lower)
    page = client.get(f"/api/sources?notebook_id={nid}&limit=1&offset=1").get_json()
    assert len(page) == 1
    assert client.get("/api/sources?sort_by=hack").status_code == 400
    assert client.get("/api/sources?limit=101").status_code == 422

    retried = client.post(f"/api/sources/{second['id']}/retry").get_json()
    assert retried["status"] == "queued"
    assert wait_job(client, retried["command_id"])["status"] == "completed"
    assert client.get(f"/api/sources/{second['id']}").get_json()["embedded"] is True

    client.delete(f"/api/notebooks/{nid}/sources/{second['id']}")
    assert client.post(f"/api/sources/{second['id']}/retry").status_code == 400


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/page")
            self.end_headers()
            return
        if self.path == "/missing":
            self.send_response(404)
            self.end_headers()
            return
        body = "<html><head><title>本地网页</title></head><body><p>网页里的知识点</p></body></html>".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def local_site():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_link_source_follows_redirect_and_reports_failures(make_app, local_site):
    client = make_app(allow_private_urls=True).test_client()
    nid = new_notebook(client)
    source = client.post("/api/sources", data={"type": "link", "url": f"{local_site}/redirect",
                                               "notebook_id": nid}).get_json()
    assert source["title"] == "本地网页" and "网页里的知识点" in source["full_text"]
    assert source["asset"]["url"] == f"{local_site}/redirect"

    failed = client.post("/api/sources", data={"type": "link", "url": f"{local_site}/missing",
                                               "notebook_id": nid, "async_processing": "true"}).get_json()
    job = wait_job(client, failed["command_id"])
    assert job["status"] == "failed" and "不存在" in job["error_message"]
    listed = {s["id"]: s for s in client.get("/api/sources").get_json()}
    assert listed[failed["id"]]["status"] == "failed"
    assert "不存在" in listed[failed["id"]]["processing_info"]["error"]
    sync_fail = client.post("/api/sources", data={"type": "link", "url": f"{local_site}/missing", "notebook_id": nid})
    assert sync_fail.status_code == 400
    assert len(client.get("/api/sources").get_json()) == 2


def test_insights_generate_list_save_delete(client, llm):
    nid = new_notebook(client)
    source = text_source(client, nid, "快速排序用分治法，平均复杂度 n log n。")
    transformations = client.get("/api/transformations").get_json()
    assert len(transformations) == 6 and {"id", "name", "title", "prompt", "apply_default"} <= set(transformations[0])
    pending = client.post(f"/api/sources/{source['id']}/insights",
                          json={"transformation_id": "transformation:simple_summary"})
    assert pending.status_code == 202 and pending.get_json()["status"] == "pending"
    assert wait_job(client, pending.get_json()["command_id"])["status"] == "completed"
    insights = client.get(f"/api/sources/{source['id']}/insights").get_json()
    assert len(insights) == 1 and insights[0]["insight_type"] == "简要摘要"
    assert insights[0]["content"].startswith("模拟回答")
    assert client.get(f"/api/sources?notebook_id={nid}").get_json()[0]["insights_count"] == 1

    insight_id = insights[0]["id"]
    assert client.get(f"/api/insights/{insight_id}").get_json()["source_id"] == source["id"]
    note = client.post(f"/api/insights/{insight_id}/save-as-note", json={"notebook_id": nid}).get_json()
    assert note["note_type"] == "ai" and "简要摘要" in note["title"]
    assert client.get(f"/api/notebooks/{nid}").get_json()["note_count"] == 1
    assert client.post(f"/api/insights/{insight_id}/save-as-note").status_code == 200
    assert client.delete(f"/api/insights/{insight_id}").status_code == 200
    assert client.get(f"/api/insights/{insight_id}").status_code == 404
    assert client.post(f"/api/sources/{source['id']}/insights", json={"transformation_id": "x"}).status_code == 404

    llm.fail = True
    failing = client.post(f"/api/sources/{source['id']}/insights",
                          json={"transformation_id": "transformation:dense_summary"}).get_json()
    assert wait_job(client, failing["command_id"])["status"] == "failed"


def test_transformations_applied_during_processing(client):
    nid = new_notebook(client)
    source = client.post("/api/sources", data={
        "type": "text", "content": "图的广度优先搜索。", "notebook_id": nid,
        "transformations": '["transformation:key_insights", "transformation:reflections"]',
    }).get_json()
    assert len(client.get(f"/api/sources/{source['id']}/insights").get_json()) == 2


def test_embed_endpoint(client, disabled_client):
    nid = new_notebook(client)
    source = client.post("/api/sources", data={"type": "text", "content": "没嵌入的来源", "notebook_id": nid}).get_json()
    assert source["embedded"] is False
    result = client.post("/api/embed", json={"item_id": source["id"], "item_type": "source"}).get_json()
    assert result["success"] is True and result["chunks_created"] == 1
    note = client.post("/api/notes", json={"content": "笔记"}).get_json()
    assert client.post("/api/embed", json={"item_id": note["id"], "item_type": "note"}).get_json()["success"]
    assert client.post("/api/embed", json={"item_id": "source:none", "item_type": "source"}).status_code == 404

    other = new_notebook(disabled_client)
    plain = disabled_client.post("/api/sources", data={"type": "text", "content": "x", "notebook_id": other}).get_json()
    assert disabled_client.post("/api/embed", json={"item_id": plain["id"], "item_type": "source"}).status_code == 400
