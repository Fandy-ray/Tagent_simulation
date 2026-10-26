"""参考文献：《系统仿真学报》等论文的下载、抽文字、切块。

出题、答疑、论文批改检索材料时，除了教材 book1.md，还会用到 references/ 目录里的论文。

全文**不进仓库**：仓库是公开的，期刊论文的版权在期刊，不能转载。仓库里只有
references/manifest.json 这份篇目清单；启动脚本运行 tools/fetch_references.py，
从期刊官网把还没有的论文下到本机、抽成同名 .md，知识库只读 .md / .txt。
抽文字放在下载这一步做一次，不在每次启动建索引时做：14 篇 PDF 每次都抽要多花十几秒。
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from app.rag.citations import split_reference_source

if TYPE_CHECKING:
    from langchain_core.documents import Document


log = logging.getLogger(__name__)

MANIFEST_NAME = "manifest.json"
# 知识库只读这两种；PDF 由 tools/fetch_references.py 先抽成 .md
TEXT_SUFFIXES = (".md", ".txt")
# 抽出来不到这么多字，多半是扫描版（整页是图片），不当论文用
MIN_TEXT_CHARS = 300
# 论文切块的写法一变就改这个值：它会进向量索引的缓存键（见 KnowledgeBase._index_cache_path）
REFERENCE_CHUNK_FORMAT = "refs-800-50-windows-200-30-label-at-end"
# 检索用的小窗口：嵌入模型只读每段的前 128 个字左右，800 字一块的话后面大半块检索时根本看不到。
# 每块再切成 200 字的小窗口去匹配，命中了返回它所在的那整块 800 字（回答、批改要的上下文不变）。
# 112 道按论文正文出的题：800 字一块第一条找对 81 道，200 字窗口 93 道（前三条 99 → 106）。
WINDOW_SIZE = 200
WINDOW_OVERLAP = 30
# 论文按 800 字一块、重叠 50 字切（和教材一样大）；改了要同时改上面 REFERENCE_CHUNK_FORMAT 里的数字
REFERENCE_CHUNK_SIZE = 800
REFERENCE_CHUNK_OVERLAP = 50
# 抽文字的规则一变就加一：.md 里记着版本，旧版本的下次启动时从本机的 PDF / 网页重新抽，不用重新下载
EXTRACT_VERSION = 3
_EXTRACT_MARK = re.compile(r"^<!--\s*抽取\s*v(\d+)")

_CJK = r"\u4e00-\u9fff"
_CJK_CHAR = re.compile(f"[{_CJK}]")
_CJK_PUNCT = "，。、；：？！“”‘’（）《》【】"
# 期刊每页的页眉页脚：出现在很多页上的行按频次去掉，下面这些即使只出现一次也去掉
_RUNNING_HEADER = re.compile(
    r"^(第\s*\d+\s*卷第\s*\d+\s*期|\d{4}\s*年\s*\d+\s*月|V\s?ol\.\s*\d+|[A-Z][a-z]{2}\.\s*\d{4}"
    r"|系统仿真学报\s*©?|Journal of System Simulation|http\S*|\d{1,4})$"
)
# 首页的出版信息与页脚：分类号、DOI、收稿日期、基金、作者简介、邮箱
_META_LINE = re.compile(
    r"^(中图分类号|文献标志码|文章编号|DOI|doi|收稿日期|修回日期|基金项目|第一作者|通讯作者|通信作者|作者简介|E-?mail|Email)"
)
# 另起一段的地方：摘要、关键词，以及只剩一个词的节标题（「0」常被当成页码去掉，只剩「引言」）
_PARAGRAPH_START = re.compile(r"^(摘\s*要|关键词)\s*[:：]|^(引言|前言|结论|结束语|结语|总结)$")
# 正文里的引用标记：[5]、[7-8]、[2,13]
_CITE_MARK = re.compile(r"\[\d+(?:\s*[-–,，]\s*\d+)*\]")
# PDF 里引用标记常常单独占一行（上标），会和段尾的短行凑成「碎片」，先去掉
_CITE_ONLY = re.compile(r"^\[\d+(?:\s*[-–,，]\s*\d+)*\]$")
# PDF 里加粗的字常被抽成两遍：「摘要摘要：：」「1 引言引言」
_DOUBLED = re.compile(f"([{_CJK}]{{2,40}})\\1")
# 节标题：「1 引言」「2.1 模型建立」「0 引言」。编号后面得是中文：表格里「1 09:00—12:00」这种行不算
_SECTION_HEADING = re.compile(f"^\\d+(?:\\.\\d+)*\\s*[{_CJK}]")
# 表题 / 图题：「表 1  订单基本数据」「图 4  数据拟合结果」，下一行多半是英文题「Tab. 1 …」「Fig. 4 …」
_TABLE_CAPTION = re.compile(r"^表\s*(\d+)[\s\u3000]+(\S.*)$")
_FIGURE_CAPTION = re.compile(r"^图\s*(\d+)[\s\u3000]+(\S.*)$")
_EN_TABLE = re.compile(r"^(Tab\.?|Table)\s*\d+", re.IGNORECASE)
_EN_FIGURE = re.compile(r"^(Fig\.?|Figure)\s*\d+", re.IGNORECASE)
# 被换行折断的正文也会以「表 3 所示」开头，这种不是表题
_NOT_A_TITLE = re.compile(r"^(所示|中|的|和|与|及|为|是|列|给出|可知|可以|表明|说明|[，。、；：])")
# 整行公式末尾的式号「(18)」
_EQUATION_NUMBER = re.compile(r"\(\s*\d{1,3}\s*\)\s*$")
_SENTENCE_END = "。！？；："
# 表题、图题换成的占位行（单独成段，不和正文接在一起）
_PLACEHOLDER = "（原文"


@dataclass(frozen=True)
class Reference:
    key: str
    title: str
    citation: str
    page: str
    pdf: str
    # 官网的网页版全文（有的话优先用它：表格、公式都完整）；2022 年以前的文章没有
    html: str = ""


def load_manifest(directory: Path) -> list[Reference]:
    """读篇目清单。清单坏了直接抛：那是仓库里的文件写错了，要让人看见。"""
    data = json.loads((directory / MANIFEST_NAME).read_text(encoding="utf-8"))
    papers = []
    for item in data.get("papers", []):
        key = str(item["key"]).strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", key):
            raise ValueError(f"manifest.json 里的 key 只能用英文、数字、点、下划线和连字符：{key!r}")
        papers.append(
            Reference(
                key=key,
                title=str(item["title"]).strip(),
                citation=str(item.get("citation", "")).strip(),
                page=str(item.get("page", "")).strip(),
                pdf=str(item["pdf"]).strip(),
                html=str(item.get("html", "")).strip(),
            )
        )
    return papers


def extract_pdf_pages(path: Path) -> list[str]:
    from pypdf import PdfReader

    # pypdf 遇到这本刊物字体字典里的重复键会刷一堆警告，内容本身抽得出来
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    reader = PdfReader(str(path))
    return [page.extract_text() or "" for page in reader.pages]


def clean_paper_text(pages: list[str]) -> str:
    """把 PDF 逐页抽出的文字整理成能检索的正文。

    去掉页眉页脚、英文摘要和参考文献列表、引用标记、加粗重复，再把被排版折断的行接回去，
    每句一行（切块时按行切，块的边界就落在句子之间）。
    """
    page_lines = [[line.strip() for line in page.splitlines() if line.strip()] for page in pages]
    # 在三成以上的页上都出现的行是页眉页脚（单页的文章不做这一步）
    seen_on = Counter(line for lines in page_lines for line in set(lines))
    repeated = {
        line
        for line, count in seen_on.items()
        if len(page_lines) >= 3 and count >= max(2, len(page_lines) * 0.3)
    }

    candidates: list[str] = []
    for lines in page_lines:
        for line in lines:
            if line in repeated:
                continue
            line = _DOUBLED.sub(r"\1", line).replace("：：", "：")
            if _RUNNING_HEADER.match(line) or _META_LINE.match(line) or _CITE_ONLY.match(line):
                continue
            candidates.append(line)

    # 这本刊也登英文正文的论文（只有摘要是中文）：那种不能把英文行当噪声扔掉
    chinese_paper = sum(bool(_CJK_CHAR.search(line)) for line in candidates) >= len(candidates) * 0.4
    candidates = _drop_tables_and_formulas(candidates)
    kept = [
        line
        for line in candidates
        # 中文论文里纯英文的长行：英文摘要、英文图题、英文参考文献，检索用不上
        if not chinese_paper or _CJK_CHAR.search(line) or len(re.findall(r"[A-Za-z]", line)) < 20
    ]
    if chinese_paper:
        # 没有中文、几乎全是数字和符号的行：表格里的一行数据（「Δps /% 1.39 2.01 3.67」），拆开了没法读
        kept = [line for line in kept if not _numeric_row(line)]

    # 参考文献列表在文末，从最后一个「参考文献」标题处截断（只认后半篇里的，免得正文提到就截）
    for index in range(len(kept) - 1, len(kept) // 2 - 1, -1):
        if re.match(r"^(参考文献|References)\s*[:：]?\s*$", kept[index], re.IGNORECASE):
            kept = kept[:index]
            break

    paragraphs: list[str] = []
    current = ""
    for line in kept:
        if line.startswith(_PLACEHOLDER):
            if current:
                paragraphs.append(current)
            paragraphs.append(line)
            current = ""
            continue
        if (_SECTION_HEADING.match(line) and len(line) <= 40) or _PARAGRAPH_START.match(line):
            if current:
                paragraphs.append(current)
            if _PARAGRAPH_START.match(line) and not re.search(r"[:：]", line):
                paragraphs.append(line)  # 「引言」这类单独成行的标题
                current = ""
            elif _SECTION_HEADING.match(line):
                paragraphs.append(line)
                current = ""
            else:
                current = line  # 「摘要：……」开头的一段
            continue
        current = _join(current, line)
    if current:
        paragraphs.append(current)

    body = "\n\n".join(_tidy(paragraph) for paragraph in paragraphs if paragraph.strip())
    return body.strip()


def _cjk_count(text: str) -> int:
    return len(_CJK_CHAR.findall(text))


def _is_prose(line: str) -> bool:
    """像正文的一行：中文够多，而且要么够长（双栏排版一行 18～25 个字），要么以句末标点收尾。"""
    return _cjk_count(line) >= 8 and (len(line) >= 15 or line[-1] in _SENTENCE_END)


def _is_fragment(line: str, previous: str = "") -> bool:
    """碎片：行间公式被拆成的短行（「Δps」「=」「ì」「(1)」）、表格里一格一行的内容。

    段落最后一截正文也很短（「心值取最小值」「，因此」），不能当碎片：以中文标点开头的、
    紧跟在一行正文后面且带中文的，都算正文的收尾。
    """
    if len(line) > 14 or _cjk_count(line) > 6 or line[-1] in _SENTENCE_END:
        return False
    if line[0] in _CJK_PUNCT:
        return False
    return not (_cjk_count(line) >= 2 and _is_prose(previous))


def _numeric_row(line: str) -> bool:
    if _CJK_CHAR.search(line) or len(line) < 6:
        return False
    return len(re.findall(r"[\d.%+\-−±×/=]", line)) >= len(line) * 0.4


def _caption(line: str, next_line: str, pattern: re.Pattern, english: re.Pattern) -> tuple[str, str] | None:
    match = pattern.match(line)
    if not match:
        return None
    title = match.group(2).strip()
    if _NOT_A_TITLE.match(title):
        return None
    # 有英文题跟着最可靠；没有的话，表题得短、不带句中标点
    if not english.match(next_line) and (len(line) > 30 or re.search(r"[，。；]", title)):
        return None
    # 表题和首行单元格偶尔抽在同一行：只取开头那段像标题的文字
    short = re.match(f"[{_CJK}A-Za-z0-9（）()、/·\\-]+(?:\\s[{_CJK}A-Za-z0-9（）()、/·\\-]+)*", title)
    return match.group(1), (short.group(0) if short else title)[:30].strip()


def _table_placeholder(number: str, title: str, body: list[str]) -> str:
    """表格换成一行：表题 + 表里出现过的中文项目名称（「重拨概率、服务率……」）。

    数字拆开以后对不上行列，留着会误导；项目名称不会，而且问到表里的东西时靠它们才查得到
    （只留表题时，按表格内容出的题有三道找不到那篇了，2026-10-03 实测）。
    """
    names: list[str] = []
    for cell in body:
        for word in re.findall(f"[{_CJK}][{_CJK}A-Za-z0-9/（）()·]*[{_CJK}）)]", cell):
            # 单元格被拆行时会留下半个括号：「出口引导)」
            if word.count("(") + word.count("（") < word.count(")") + word.count("）"):
                word = word.rstrip(")）")
            if len(word) >= 2 and word not in names and word not in title:
                names.append(word)
    listed = f"，涉及：{'、'.join(names[:30])}" if names else ""
    return f"{_PLACEHOLDER}表 {number}：{title}{listed}，数据见原文）"


def _drop_tables_and_formulas(lines: list[str]) -> list[str]:
    """表格整块换成一行占位，图题单独成段，成串的公式碎片去掉。

    PDF 里表格的行列关系、公式的上下标都抽不出来，留着只会让检索和回答带上一串看不懂的数字。
    表格只留「原文表 N：表题」，告诉读的人这里有张表、讲的是什么。
    """
    marked: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        following = lines[index + 1] if index + 1 < len(lines) else ""
        table = _caption(line, following, _TABLE_CAPTION, _EN_TABLE)
        figure = None if table else _caption(line, following, _FIGURE_CAPTION, _EN_FIGURE)
        if not (table or figure):
            marked.append(line)
            index += 1
            continue
        number, title = table or figure
        index += 1
        if index < len(lines) and (_EN_TABLE if table else _EN_FIGURE).match(lines[index]):
            index += 1  # 英文表题 / 图题
        if not table:
            marked.append(f"{_PLACEHOLDER}图 {number}：{title}）")
            continue
        if table:
            # 表体：一直到下一段正文、下一个表题图题或节标题为止（最多 120 行，认错了也不至于吞掉整篇）
            start = index
            while index < len(lines) and index - start < 120:
                cell = lines[index]
                nxt = lines[index + 1] if index + 1 < len(lines) else ""
                if (
                    # 表格行也可能中文多、又长；正文行要么带中文标点，要么不像空格隔开的一排格子
                    (_is_prose(cell) and (re.search(r"[，。；：]", cell) or len(cell.split()) <= 3))
                    or _caption(cell, nxt, _TABLE_CAPTION, _EN_TABLE)
                    or _caption(cell, nxt, _FIGURE_CAPTION, _EN_FIGURE)
                    # 节标题是「编号 + 一段中文」；「1 无引导 正常情况 正常」这种多格的是表格行
                    or (_SECTION_HEADING.match(cell) and len(cell) <= 25 and cell.count(" ") <= 1)
                ):
                    break
                index += 1
            marked.append(_table_placeholder(number, title, lines[start:index]))

    # 连续 3 行以上的碎片：行间公式被拆成的一串短行，或没认出表题的表格。单独一两行多半是正文里折行的变量名，留着
    result: list[str] = []
    run: list[str] = []

    def flush() -> None:
        if len(run) < 3:
            result.extend(run)
        run.clear()

    previous = ""
    for line in marked:
        if not line.startswith(_PLACEHOLDER) and _is_fragment(line, previous) and not _SECTION_HEADING.match(line):
            run.append(line)
            previous = line
            continue
        flush()
        previous = line
        if _EQUATION_NUMBER.search(line) and _cjk_count(line) <= len(line) * 0.2:
            continue  # 带式号的整行公式：「im ), i ∈ 1,2,⋯,n (18)」
        result.append(line)
    flush()
    return result


def _join(left: str, right: str) -> str:
    if not left:
        return right
    # 中文之间直接接上；两边都是英文 / 数字才补空格
    if _CJK_CHAR.match(left[-1]) or left[-1] in _CJK_PUNCT or _CJK_CHAR.match(right[0]) or right[0] in _CJK_PUNCT:
        return left + right
    return f"{left} {right}"


def _tidy(paragraph: str) -> str:
    text = _CITE_MARK.sub("", paragraph)
    text = re.sub(r"•+\s*\d*", "", text)  # 页脚的「•• 1659」
    # 排版留下的空格：中文与中文标点之间不该有空格
    text = re.sub(f"\\s+([{_CJK_PUNCT}])", r"\1", text)
    text = re.sub(f"([{_CJK_PUNCT}])\\s+", r"\1", text)
    text = re.sub(f"([{_CJK}])\\s+([{_CJK}])", r"\1\2", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    # 每句一行：切块时按行切，块的边界落在句子之间
    return re.sub(r"([。！？；])(?=\S)", "\\1\n", text).strip()


def reference_markdown(reference: Reference, body: str, *, origin: str = "pdf") -> str:
    source = f"{reference.citation}。{reference.page}" if reference.page else reference.citation
    mark = f"<!-- 抽取 v{EXTRACT_VERSION}（{origin}） -->"
    return f"# {reference.title}\n\n> 来源：{source}\n\n{mark}\n\n{body.strip()}\n"


def has_extract_mark(text: str) -> bool:
    """是本脚本抽的（带版本标记），不是自己手写的。"""
    return any(_EXTRACT_MARK.match(line.strip()) for line in text.splitlines()[:8])


def extract_version(text: str) -> int:
    """.md 是哪一版规则抽的；没记版本（第一版，或自己写的）算 0。"""
    for line in text.splitlines()[:8]:
        match = _EXTRACT_MARK.match(line.strip())
        if match:
            return int(match.group(1))
    return 0


def parse_reference_markdown(text: str, fallback_title: str) -> tuple[str, str, str]:
    """（题目, 出处, 正文）。第一行 `# 题目`、紧跟的 `> 来源：…` 是可选的，没有就用文件名。"""
    lines = text.strip().splitlines()
    title, citation = fallback_title, ""
    if lines and lines[0].startswith("# "):
        title = lines[0][2:].strip() or fallback_title
        lines = lines[1:]
    while lines and not lines[0].strip():
        lines = lines[1:]
    if lines and lines[0].startswith(">"):
        citation = re.sub(r"^>\s*(来源[:：])?\s*", "", lines[0]).strip()
        lines = lines[1:]
    lines = [line for line in lines if not _EXTRACT_MARK.match(line.strip())]
    return title, citation, "\n".join(lines).strip()


def reference_files(directory: Path | None) -> list[Path]:
    """知识库要读的文字稿，按文件名排好（缓存键要用，顺序必须稳定）。"""
    if directory is None or not directory.is_dir():
        return []
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file()
        and path.suffix.lower() in TEXT_SUFFIXES
        and path.name.lower() != "readme.md"
        and not path.name.startswith(".")
    )


def reference_documents(directory: Path | None) -> list[Document]:
    """切成和教材一样大小的块，每块**末尾**带上「——摘自《题目》（出处）」，回答时知道出自哪篇。

    放末尾不放开头：嵌入模型只读每块的前 128 个字，标签放开头要占掉将近一半，
    按内容找论文就不准了。12 个按内容提问的实测：开头 10/12 题第一条找对，末尾 11/12（前三条 11/12 → 12/12）。
    """
    # 放在函数里导入：启动脚本每次都跑 tools/fetch_references.py，论文都在时它应当一眨眼就结束，
    # 顶层导入 langchain 要多花 4 秒
    from langchain_core.documents import Document
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=REFERENCE_CHUNK_SIZE,
        chunk_overlap=REFERENCE_CHUNK_OVERLAP,
        separators=["\n\n", "\n", "。", "，", " ", ""],
    )
    documents: list[Document] = []
    for path in reference_files(directory):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            log.warning("参考文献读不了，跳过：%s（%s）", path.name, exc)
            continue
        title, citation, body = parse_reference_markdown(text, path.stem)
        if len(body) < MIN_TEXT_CHARS:
            log.warning("参考文献正文太短，跳过：%s", path.name)
            continue
        source, href = split_reference_source(citation)
        label = f"——摘自《{title}》" + (f"（{source}）" if source else "")
        for index, chunk in enumerate(splitter.split_text(body)):
            documents.append(
                Document(
                    page_content=f"{chunk}\n{label}",
                    metadata={
                        "h1": "参考文献",
                        "h2": title,
                        "source": "reference",
                        "file": path.name,
                        # 同一块切出的几个检索窗口都指回这里，检索结果按它去重
                        "parent": f"{path.name}#{index}",
                        "body": chunk,
                        # 答疑返回出处时用（app/rag/citations.py）
                        "citation": source,
                        "href": href,
                    },
                )
            )
    return documents


def retrieval_windows(document: Document) -> list[str]:
    """一块论文切成几个 200 字的检索窗口（只拿正文切，不带末尾的出处标签）。"""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=WINDOW_SIZE,
        chunk_overlap=WINDOW_OVERLAP,
        separators=["\n\n", "\n", "。", "，", " ", ""],
    )
    body = document.metadata.get("body") or document.page_content
    return splitter.split_text(body) or [body]


def write_text_atomically(path: Path, text: str) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def write_bytes_atomically(path: Path, data: bytes) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
