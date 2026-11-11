"""内容抽取：替代原版的 content-core。

只保留用得上的几种：纯文本、txt/md/csv/json/xml/html、PDF（pypdf）、docx（直接读里面的 XML）、
普通网页。音视频转写、YouTube 字幕、docling、crawl4ai 都不要了。
失败一律抛 ExtractionFailed，消息是给人看的固定文案，不把底层异常（可能带路径）透出去。
"""

from __future__ import annotations

import io
import logging
import pathlib
import re
import zipfile
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin
from xml.etree import ElementTree

import httpx

from app.errors.notebook import ExtractionFailed
from app.infra.notebook.url_guard import validate_url

log = logging.getLogger(__name__)

TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".xml", ".log", ".rst", ".tex"}
HTML_EXTENSIONS = {".html", ".htm", ".xhtml"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | HTML_EXTENSIONS | {".pdf", ".docx"}

MAX_FETCH_BYTES = 10 * 1024 * 1024
MAX_REDIRECTS = 5
USER_AGENT = "Mozilla/5.0 (compatible; OpenNotebookLite/0.1)"


@dataclass(frozen=True)
class Extraction:
    title: str | None
    content: str


def is_supported_file(name: str) -> bool:
    return pathlib.Path(name).suffix.lower() in SUPPORTED_EXTENSIONS


def decode_bytes(data: bytes, declared: str | None = None) -> str:
    for encoding in [declared, "utf-8-sig", "gb18030", "big5"]:
        if not encoding:
            continue
        try:
            return data.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("utf-8", errors="replace")


def _tidy(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = re.sub(r"[ \t\f\v]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class _HTMLText(HTMLParser):
    SKIP = {"script", "style", "noscript", "template", "svg", "iframe", "head"}
    BLOCK = {
        "p", "div", "br", "li", "ul", "ol", "tr", "table", "section", "article", "header",
        "footer", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "blockquote", "hr", "dd", "dt",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        elif tag in self.SKIP:
            self._skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag in self.SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title_parts.append(data)
        elif not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> Extraction:
    parser = _HTMLText()
    try:
        parser.feed(html)
        parser.close()
    except Exception as exc:  # noqa: BLE001 - HTMLParser 遇到很烂的页面也可能抛
        log.warning("HTML 解析失败：%s", exc)
    title = re.sub(r"\s+", " ", "".join(parser.title_parts)).strip() or None
    lines = [re.sub(r"[ \t ]+", " ", line).strip() for line in "".join(parser.parts).split("\n")]
    return Extraction(title=title, content=_tidy("\n".join(lines)))


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception as exc:  # noqa: BLE001 - 单页坏了不影响别的页
            log.warning("PDF 某页抽取失败：%s", exc)
    return "\n\n".join(pages)


_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _docx_text(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        xml = archive.read("word/document.xml")
    root = ElementTree.fromstring(xml)
    paragraphs = []
    for paragraph in root.iter(f"{_W}p"):
        pieces = []
        for node in paragraph.iter():
            if node.tag == f"{_W}t" and node.text:
                pieces.append(node.text)
            elif node.tag == f"{_W}tab":
                pieces.append("\t")
            elif node.tag in {f"{_W}br", f"{_W}cr"}:
                pieces.append("\n")
        paragraphs.append("".join(pieces))
    return "\n".join(paragraphs)


def extract_bytes(data: bytes, *, suffix: str, content_type: str = "") -> Extraction:
    suffix = suffix.lower()
    try:
        if suffix == ".pdf" or "application/pdf" in content_type:
            return Extraction(title=None, content=_tidy(_pdf_text(data)))
        if suffix == ".docx" or "officedocument.wordprocessingml" in content_type:
            return Extraction(title=None, content=_tidy(_docx_text(data)))
        if suffix in HTML_EXTENSIONS or "html" in content_type:
            return html_to_text(decode_bytes(data))
        if suffix in TEXT_EXTENSIONS or content_type.startswith("text/") or "json" in content_type:
            return Extraction(title=None, content=_tidy(decode_bytes(data)))
    except ExtractionFailed:
        raise
    except Exception as exc:  # noqa: BLE001
        log.warning("文件抽取失败（%s）：%s", suffix or content_type, exc)
        raise ExtractionFailed("文件读不出来，可能已损坏或格式不受支持。") from exc
    raise ExtractionFailed("不支持这种文件类型。")


def extract_file(path: pathlib.Path) -> Extraction:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ExtractionFailed("上传的文件找不到了，请重新上传。") from exc
    extraction = extract_bytes(data, suffix=path.suffix)
    return Extraction(title=extraction.title or path.stem, content=extraction.content)


def fetch_url(url: str, *, allow_private: bool, timeout: float = 20.0) -> Extraction:
    current = validate_url(url, allow_private=allow_private)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False, headers={"User-Agent": USER_AGENT}) as client:
            for _ in range(MAX_REDIRECTS + 1):
                with client.stream("GET", current) as response:
                    if response.is_redirect:
                        location = response.headers.get("location", "")
                        current = validate_url(urljoin(current, location), allow_private=allow_private)
                        continue
                    if response.status_code == 404:
                        raise ExtractionFailed("网页不存在（可能已删除或移动），请检查网址。")
                    if response.status_code >= 400:
                        raise ExtractionFailed(f"网页打不开（HTTP {response.status_code}）。")
                    chunks = []
                    total = 0
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > MAX_FETCH_BYTES:
                            raise ExtractionFailed("网页太大（超过 10 MB）。")
                        chunks.append(chunk)
                    content_type = (response.headers.get("content-type") or "").lower()
                    data = b"".join(chunks)
                    suffix = pathlib.PurePosixPath(httpx.URL(current).path).suffix.lower()
                    if "html" in content_type or (not content_type and suffix in HTML_EXTENSIONS | {""}):
                        return html_to_text(decode_bytes(data, response.charset_encoding))
                    return extract_bytes(data, suffix=suffix, content_type=content_type)
            raise ExtractionFailed("网页跳转次数太多。")
    except ExtractionFailed:
        raise
    except httpx.HTTPError as exc:
        log.warning("抓取网页失败：%s", exc)
        raise ExtractionFailed("连不上这个网址（连接、超时或域名解析出错），请检查后重试。") from exc
