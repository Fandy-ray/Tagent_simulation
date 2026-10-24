"""集中式配置：所有环境变量与数据文件路径在此收口。

分层规则：任何层都可以 import 本模块；本模块不 import 任何业务模块。
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


# basic-agent/ 的绝对路径。本文件在 basic-agent/app/config.py，故上溯两级。
#
# 数据文件（config/、text_db/、book1.md）都挂在 basic-agent/ 根下。
# 不要在其他模块里用 Path(__file__).parent 去定位它们——模块一旦下移一层，
# 相对路径就会指向错误目录，而且服务照样能起、测试也未必报错，
# 只是知识库变成空的。一律从这里取。
BASE_DIR = Path(__file__).resolve().parent.parent

DEFAULT_MODEL_PROVIDERS_PATH = BASE_DIR / "config" / "model_providers.json"
DEFAULT_TEXT_DB_DIR = BASE_DIR / "text_db"
DEFAULT_KNOWLEDGE_FILE = BASE_DIR / "book1.md"
# 参考文献（《系统仿真学报》等论文）：全文不入库，由 tools/fetch_references.py 下载到这里
DEFAULT_REFERENCES_DIR = BASE_DIR / "references"

LEARNING_DB_FILENAME = "tagent.sqlite3"


def default_data_dir() -> Path:
    """各系统放应用数据的标准位置（学习记录库默认放这里）。

    刻意不放在项目目录里：项目常在桌面上，而 macOS 的桌面经常开着 iCloud 同步——
    正在写的 SQLite 文件被同步，轻则生成「tagent 2.sqlite3」冲突副本，重则把库弄坏。
    Windows 上同理避开 OneDrive 接管的「文档 / 桌面」，用 LOCALAPPDATA（不漫游、不同步）。
    """
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "TAgent"
    if os.name == "nt":
        return Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "TAgent"
    return Path(os.getenv("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "tagent"


def _env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


# OpenNotebook 起的是两个进程：8502 是 Streamlit 页面，5055 才是 REST API。
# app/rag/opennotebook_kb.py 打的全是 /api/*，只有 5055 认。
NOTEBOOK_UI_PORT = 8502
NOTEBOOK_API_PORT = 5055


def normalize_notebook_url(raw: str, *, rewrite_ui_port: bool = True) -> str:
    """把人从浏览器里抄来的地址换算成 OpenNotebook 的接口基址。

    要纠正两件事：
    1. `/notebooks` 是页面路径，接口基址不带它；
    2. 8502 是 Streamlit 页面端口，拿它打 /api/* 会收到一坨 HTML。

    第 2 条尤其要命：CompositeKnowledgeBase 遇到失败的来源是**静默跳过**的，
    配错端口的表现不是报错，而是"答疑一切正常，但笔记本里的内容一条都检索不到"。
    所以这里直接把 8502 改写成 5055。已经明确给了 API 地址的走
    rewrite_ui_port=False，不猜。
    """
    value = (raw or "").strip().rstrip("/")
    if not value:
        return ""

    lowered = value.lower()
    for suffix in ("/notebooks", "/notebook"):
        if lowered.endswith(suffix):
            value = value[: -len(suffix)]
            break

    value = value.rstrip("/")
    if not value:
        return ""

    # 没写 scheme 时 urlsplit 会把 "localhost:8502" 的 localhost 当成 scheme。
    parts = urlsplit(value if "://" in value else f"http://{value}")
    try:
        port = parts.port
    except ValueError:
        return value
    if not parts.hostname:
        return value

    if rewrite_ui_port and port == NOTEBOOK_UI_PORT:
        port = NOTEBOOK_API_PORT

    # hostname 已经去掉了 IPv6 的方括号，拼回去要补上。
    netloc = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
    if port is not None:
        netloc = f"{netloc}:{port}"
    # 别把 URL 里的账号密码悄悄丢了。
    if parts.username:
        credentials = parts.username
        if parts.password:
            credentials = f"{credentials}:{parts.password}"
        netloc = f"{credentials}@{netloc}"

    return urlunsplit((parts.scheme or "http", netloc, parts.path.rstrip("/"), "", ""))


@dataclass(frozen=True)
class AgentConfig:
    """服务级配置。由 from_env() 在启动时构造一次，之后只读。"""

    host: str = "127.0.0.1"
    port: int = 5000
    use_waitress: bool = True
    # 流式回答整段占一个线程。8 个线程时 12 人同时提问，后 4 人的首字要等 6 秒多，
    # 连 /health 都跟着卡住（压测 S7）。这些线程都在等网络，多开很便宜。
    # 32 → 100（2026-10-11 压测，回答约 18 秒）：32 个占满后所有请求都排队，50 人同时提问后 18 人首字要等 18.7 秒；
    # 100 个时 50 人全部 0.8 秒内出字，内存只多十几 MB。代价是同时打到模型的请求上限跟着变成 100。
    waitress_threads: int = 100

    admin_token: str = ""
    internal_token: str = ""
    max_content_length: int = 1024 * 1024

    model_providers_path: Path = DEFAULT_MODEL_PROVIDERS_PATH
    text_db_dir: Path = DEFAULT_TEXT_DB_DIR
    knowledge_file: Path = DEFAULT_KNOWLEDGE_FILE
    # 参考文献目录。None = 不用（TAGENT_REFERENCES=0，或单测）
    references_dir: Path | None = None

    # local = 只读 book1.md；notebook = 只读 OpenNotebook；
    # composite = 两边一起检索。没配 OPEN_NOTEBOOK_URL 时一律 local。
    knowledge_source: str = "local"
    # 已经过 normalize_notebook_url，指向 REST API（默认 5055），不是 Streamlit 页面。
    notebook_url: str = ""
    notebook_token: str = ""

    # 出卷、批改同时跑几份（并发闸门容量）。2 → 5（2026-10-11 压测，一次批改约 15 秒）：10 人同时交稿，
    # 容量 2 有 6 人等满 30 秒被拒，容量 5 全部批完。上游并发峰值：批改 = 容量 × 3 = 15，
    # 出整卷 = 容量 × 7 = 35（整卷七路同时发，见 app/agent/graphs/exam.py）。
    exam_max_concurrent_llm: int = 5
    llm_max_orphan_tasks: int = 2

    # 向量索引的磁盘缓存目录。None = 不缓存（TAGENT_VECTOR_CACHE=0，或单测）
    vector_cache_dir: Path | None = None
    retrieval_cache_enabled: bool = True
    retrieval_cache_max_entries: int = 128
    retrieval_cache_ttl_seconds: int = 60

    # 学习记录库（SQLite）。None = 用 default_data_dir() 下的默认文件。
    learning_store_enabled: bool = True
    learning_db_path: Path | None = None
    learning_backup_keep: int = 7

    @classmethod
    def from_env(cls) -> "AgentConfig":
        # 显式给了 API 地址就照用；只给了浏览器地址才去猜端口。
        notebook_url = normalize_notebook_url(
            _env("OPEN_NOTEBOOK_API_URL", "NOTEBOOK_API_URL"), rewrite_ui_port=False
        ) or normalize_notebook_url(_env("OPEN_NOTEBOOK_URL", "NOTEBOOK_URL"))
        requested = _env("KNOWLEDGE_SOURCE").strip().lower()
        if requested in {"local", "notebook", "composite"}:
            knowledge_source = requested
        elif notebook_url:
            knowledge_source = "composite"
        else:
            knowledge_source = "local"
        if knowledge_source in {"notebook", "composite"} and not notebook_url:
            knowledge_source = "local"
        return cls(
            host=_env("BASIC_AGENT_HOST", "AGENT_HOST", default="127.0.0.1"),
            port=int(_env("BASIC_AGENT_PORT", "AGENT_PORT", default="5000")),
            use_waitress=os.getenv("USE_WAITRESS", "1") == "1",
            waitress_threads=int(os.getenv("WAITRESS_THREADS", "100")),
            admin_token=os.getenv("AGENT_ADMIN_TOKEN", ""),
            internal_token=os.getenv("AGENT_INTERNAL_TOKEN", ""),
            model_providers_path=Path(
                os.getenv("MODEL_PROVIDERS_PATH") or DEFAULT_MODEL_PROVIDERS_PATH
            ),
            text_db_dir=DEFAULT_TEXT_DB_DIR,
            knowledge_file=DEFAULT_KNOWLEDGE_FILE,
            references_dir=(
                None
                if os.getenv("TAGENT_REFERENCES", "1") == "0"
                else Path(os.getenv("TAGENT_REFERENCES_DIR") or DEFAULT_REFERENCES_DIR)
            ),
            knowledge_source=knowledge_source,
            notebook_url=notebook_url,
            notebook_token=_env(
                "OPEN_NOTEBOOK_PASSWORD", "OPEN_NOTEBOOK_TOKEN", "NOTEBOOK_TOKEN"
            ),
            exam_max_concurrent_llm=int(os.getenv("EXAM_MAX_CONCURRENT_LLM", "5")),
            llm_max_orphan_tasks=int(os.getenv("LLM_MAX_ORPHAN_TASKS", "2")),
            vector_cache_dir=(
                None
                if os.getenv("TAGENT_VECTOR_CACHE", "1") == "0"
                else Path(cache_dir).expanduser() if (cache_dir := _env("RAG_INDEX_CACHE_DIR"))
                else default_data_dir() / "vector-cache"
            ),
            retrieval_cache_enabled=os.getenv("RAG_RETRIEVAL_CACHE", "1") != "0",
            retrieval_cache_max_entries=max(1, min(1024, int(os.getenv("RAG_RETRIEVAL_CACHE_MAX_ENTRIES", "128")))),
            retrieval_cache_ttl_seconds=max(0, min(3600, int(os.getenv("RAG_RETRIEVAL_CACHE_TTL_SECONDS", "60")))),
            learning_store_enabled=os.getenv("LEARNING_STORE", "1") != "0",
            learning_db_path=Path(db_path).expanduser() if (db_path := _env("TAGENT_DB_PATH")) else None,
            learning_backup_keep=max(1, int(os.getenv("LEARNING_BACKUP_KEEP", "7"))),
        )

    def resolved_learning_db_path(self) -> Path:
        return self.learning_db_path or default_data_dir() / LEARNING_DB_FILENAME


# ====================== LLM 调用超时与预算（压测所得，勿凭直觉改） ======================
#
# 以下数值全部来自 A/B 压测，改动前先看注释里的实测数据。
#
# ！！读这一段之前先看清楚数据的出处 ！！
#
# 本段及出卷代码（app/agent/graphs/exam.py）里带具体秒数的结论，都来自**交接包导入之前**的一轮压测
# （各 3~5 轮 A/B，同材料同模型）。那轮用的是哪个模型、什么时候测的，仓库里没记——
# git 历史在 d8cf81a 被压成了一次性导入，查不回去。所以这些秒数只能当**相对结论**
# 用（并行快过串行、长上下文更慢、精简 prompt 反而更慢），不能当**绝对水位**用。
#
# 2026-09-11 在 DeepSeek（deepseek-chat）上复测的绝对值，比老数据快一个数量级：
#     整卷出卷 8~9s（老数据并行中位 68.4s）
#     闪卡出卷 6~10s
#     整卷判卷 ~11s
# 样本只有 2 轮，不足以取代上面那轮 3~5 轮的 A/B，**没有**据此改任何超时与预算：
# 超时是给尾部留的余量，按快的那次收紧只会在慢的那次炸掉。
#
# 但下面这些按老数据定的尺寸，前提已经不一定成立，后来人要调时心里有数：
#     EXAM_LLM_TIMEOUT / EXAM_LLM_BUDGET、FLASH_*_SHARDS 的分片数、
#     app/agent/graphs/exam.py 里出卷各段的 max_tokens
# 真要重新定尺寸，请照老注释的做法重跑 A/B（同材料同模型、各 3~5 轮取中位），
# 把模型名和日期一起写进注释——别再留一组无出处的秒数给下一个人。

QUIZ_GENERATION_TIMEOUT_SECONDS = 20
EXAM_SAMPLE_K = 10

# ---- 出卷取材的来源配比（修「出的题全是论文细节」）----
#
# 索引里是「教材 + 14 篇论文」。论文按检索窗口切（WINDOW_SIZE=200），一篇就能
# 切出上百个窗口，总量远超教材；加上 MMR 默认偏多样，填「排队论」这种短主题时，
# 候选池会被只沾边的论文片段占满（实测出的 21 题里 20 题来自论文，考的是
# 「主路常数 m 值为多少」这类细节）。
#
# 两手一起治：
#   1. 配额——教材至少占这么多，论文只做补充。学生读过的是教材。
#   2. MMR 偏相关一点，别为了「多样」把不相关的也拉进来。
# ---- 填空、选择不再先定考点 ----
#
# 各路同时出题、彼此看不见，同一个考点会被问好几遍。以前的做法是先调一次模型定考点、
# 切成互不相交的几份分给各路（2026-10-24 那轮：每卷撞考点 1.83 → 1.13，代价 1.6 秒）。
#
# 整卷压到 5 秒以内之后，这 1.5 秒放不下了（它挡在填空、选择前面）。现在的做法不调
# 模型：每路一片不同的材料，第一路专管核心概念、其余各路明确避开（见
# exam_prompts._lane_block）。同一时段用模型当评委统计每卷撞考点（这位评委比上面
# 那轮严，数字不能和 1.13 直接比）：
#                                          每卷撞考点   论文细节题   出卷中位
#   以前（一路三道 + 先定考点）              8.7 对       0.3 道      8.8 秒
#   先定考点 + 填空选择各三路               10.3~12.8 对     —        4.6 秒
#   只分材料                                13.3 对        —        4.3 秒
#   分材料 + 核心概念只由第一路考            8.4 对       2.1 道      4.0 秒
#   只分教材片段（论文只给大题）+ 同上        8.4 对        0 道      4.2 秒  ← 现在
#
# 「论文细节题」那一列是这么来的：材料切得小，分到论文片段的那一路只能从论文里挑，
# 出来的是「小区开放后改善率怎么定义」这种论文独有的细节。所以填空、选择只分教材。
#
# 踩过的坑（定考点那会儿的，换了做法仍然要防）：考点文字或提示语一出现在题干里，
# 要填的词就露了，整道题被泄题检查删掉——所以填空也不再让模型写 cue。

EXAM_TEXTBOOK_MIN_SHARE = 0.6
# lambda_mult：1.0=只看相关，0.0=只看多样。langchain 默认 0.5，对短主题太散。
EXAM_MMR_LAMBDA = 0.7
# 候选池。要先捞够，配额才有的挑；这步是本地向量运算，不调模型，贵不到哪去。
EXAM_MMR_FETCH_K = 40

# 分三段出卷后同一份参考材料要发三次，上下文越长每段前置处理越久。
# 实测 6000 字上下文时单段要 ~58s，压到 4500 字可明显回落。
EXAM_CONTEXT_CHAR_LIMIT = 4500

# 单段耗时波动近 1.8 倍（同 prompt 同输出量重复 4 次：46.0/46.0/54.9/83.5s），
# 按单次测量定超时必然时好时坏，故按尾部再留余量：
# 单段 150s，总预算 480s（3 段最坏 3×155=465s）。
#
# 别再想着"精简 prompt 提速"——A/B 压测（各 3 轮）结果是反的：
#   填空 55.3s → 87.0s，选择 31.8s → 69.4s，解答 18.2s → 33.8s
#   且填空的考点重复从 0 涨到 2.67（10 道里近 3 道撞车）
# 详细的规则收窄了模型的搜索空间，反而更快也更稳；压成干条目后它要自己揣摩。
# 三段中位合计约 105s，真要提速应从"三段并行"入手，不是改 prompt。
EXAM_LLM_TIMEOUT = 150
EXAM_LLM_BUDGET = 480
EXAM_MIN_ATTEMPT_TIMEOUT = 30

GRADE_LLM_TIMEOUT = 55
GRADE_LLM_BUDGET = 190
# 判分分批上限。一次只让模型面对少量同类题：ID 集合小、评分准则单一，
# 比"一次评十几道混合题"稳得多。最坏 3 批（2 批解答 + 1 批填空复核）。
GRADE_ESSAY_BATCH = 2
GRADE_CLOZE_BATCH = 10
GRADE_MIN_ATTEMPT_TIMEOUT = 20


# ====================== 闪卡（填空 + 选择，分片并发） ======================
#
# 闪卡不是"整卷的填空段"，而是把那一段再拆细：整卷的填空段一次要 8~10 张、
# 配 4500 字上下文（老那轮压测里中位 55.3s，出处见本段开头的警示）；闪卡把
# 两个变量同时砍到三分之一——每片 3~4 张卡配 ~1600 字材料，三片并发发出。
#
# 分片数是按那组老数据定的。2026-09-11 在 DeepSeek 上实测，闪卡 6~10s、整卷
# 8~9s，两者已经拉不开差距——**拆闪卡的理由现在是交互形态（只出能本地判定的
# 题型、随时开随时停），不再是快**。前端文案已据此去掉了所有秒数，这里同理：
# 不要再把"目标 20~30s"当成对用户的承诺写进 UI。
#
# 依据与整卷"三段并行"是同一条：单次调用的输出 token 量与上下文长度才是
# 主要耗时来源（见上面 EXAM_CONTEXT_CHAR_LIMIT 的注释：6000 字上下文单段
# 要 ~58s，压到 4500 明显回落）。不要靠精简 prompt 提速，那条路已经被证伪。
# 闪卡一组里两种卡：填空（打字或翻面自评）+ 选择（点一下当场判）。
# 两类各自占几片 —— 加起来就是并发数，和整卷的三段并行同一个量级。
FLASH_CLOZE_SHARDS = 2
FLASH_CHOICE_SHARDS = 1
FLASH_SHARD_COUNT = FLASH_CLOZE_SHARDS + FLASH_CHOICE_SHARDS
FLASH_SHARD_CARD_RANGE = (3, 4)
# 三片并发看不到彼此，撞考点在所难免，去重后张数会掉。低于这个数才算失败，
# 不要设成 shard_count * card_range[0]，那样一旦去掉两张就整次报错。
# 只管一次拿完的接口；边写边给的发出去就在学生手上了，一张没有才算失败。
FLASH_DECK_MIN_CARDS = 6
FLASH_CONTEXT_CHAR_LIMIT = 1600  # 每片
FLASH_LLM_TIMEOUT = 90
FLASH_LLM_BUDGET = 200
FLASH_MIN_ATTEMPT_TIMEOUT = 25

# 三个知识库实现拼接出卷上下文时用的分隔符。闪卡要按它把整段上下文切回
# 独立片段再分发给各片，所以提到这里共享，而不是各自硬编码。
EXAM_CONTEXT_SEPARATOR = "\n\n---\n\n"


# ====================== 小论文批改 / 逐句批注 ======================
#
# 三个维度（切题与内容 / 论证与结构 / 语言与规范）并发发出，和出卷三段并行
# 同一个量级；闸门按"一次批改"计名额，所以上游峰值 = 闸门容量 × 3。
#
# 逐句批注是**条件触发**的第四轮：只有当论证维度点名了可疑段落才发，批注目标
# 限于这些段落，同时提供全文以核对前后文。整卷大题批注根本不进判卷流程，
# 学生点开某道题才单独发一轮，不点就一轮都不花。
ESSAY_DIMENSION_COUNT = 3
ESSAY_CONTEXT_CHAR_LIMIT = 1800
ESSAY_LLM_TIMEOUT = 90
ESSAY_LLM_BUDGET = 220
ESSAY_MIN_ATTEMPT_TIMEOUT = 25

# 正文长度闸。上限是为了别让一篇长文顶穿预算；下限是因为太短的东西没什么
# 可批的，与其给一堆空泛评语不如直接告诉学生写够了再来。
ESSAY_MAX_CHARS = 6000
ESSAY_MIN_CHARS = 100

# 被点名的段落最多下钻这么多段，再多就失去"渐进式披露"的意义了
ESSAY_MAX_FLAGGED_PARAGRAPHS = 3

# 整卷大题的逐句批注：答案本来就短，一轮足够，名额也比论文那边紧
ANNOTATE_LLM_TIMEOUT = 45
ANNOTATE_LLM_BUDGET = 70
ANNOTATE_MIN_ATTEMPT_TIMEOUT = 20
ANNOTATE_MIN_ANSWER_CHARS = 40

# 答疑论文模式的「出题」：只出一道题，输出很短，一轮足够，名额与逐句批注同量级
ESSAY_TOPIC_LLM_TIMEOUT = 45
ESSAY_TOPIC_LLM_BUDGET = 70
ESSAY_TOPIC_MIN_ATTEMPT_TIMEOUT = 20
# 建议篇幅夹在这个区间：方案文档定的就是 500~2000 字的小作文。模型给的数只是建议，
# 夹一下即可，不值得为它判不合格再重试一轮
ESSAY_TOPIC_MIN_SUGGESTED_CHARS = 500
ESSAY_TOPIC_MAX_SUGGESTED_CHARS = 2000

# 文件编辑的修改建议（app/agent/graphs/edit.py，这一轮只铺路、还没接路由）。
# 下面是**初值，没有实测过**：比批注多写一整句改写，超时和输出额度给宽一点。
# 下一轮接上界面时照上面几段的做法实测再定，把模型和日期写进来。
EDIT_LLM_TIMEOUT = 60
EDIT_MIN_ATTEMPT_TIMEOUT = 20
EDIT_MAX_SUGGESTIONS = 5


# ====================== LLM 闸门的排队 ======================
#
# 闸门满了先排队，排不上才 429（见 app/repository/exam_cache.py 的 LLMGate）。
# 等多久必须短于「前端超时 − 后端预算」的余量：整卷 540−480=60、闪卡 240−200=40、
# 论文批改 260−220=40 秒，取 30 秒，排到之后还够一次完整的预算。
# 队长上限：排队的人各占一个 waitress 线程干等（共 32 个），给流式答疑留足。
LLM_GATE_WAIT_SECONDS = 30.0
LLM_GATE_MAX_WAITING = 8


# ====================== 请求合并 / 上游连接 ======================
#
# 同样内容的批改、判卷、批注请求，跑完之后这么多秒内直接重放那份结果
# （见 app/util/singleflight.py）。只在内存里、按内容哈希索引、过期即删，不落盘；
# 设成 0 就只合并「正在跑的」、不重放。
IDEMPOTENT_REPLAY_SECONDS = 90

# 连上游时 TCP/TLS 握手单独限时。断网但包被丢弃（不报错）时，不必等满整段读超时
# （最长 90 秒）才发现连不上；已经连上、只是生成得慢的请求不受影响。
UPSTREAM_CONNECT_TIMEOUT = 10

# 配着系统代理时，连模型服务先直连，直连不通才走代理（见 app/infra/upstream_http.py）。
# 2026-10-24 实测（DeepSeek，本机代理）：小请求首字 2.5s → 0.7s；同一套出卷流程整卷 9.3s → 7.2s；
# 多路同时发时也不再互相拖慢——整卷能拆成七路同时写，靠的就是这一条。
# 直连握手只等这么多秒，被防火墙丢包的网络第一次最多多等这么久，之后记住改走代理。
# 设 UPSTREAM_DIRECT_FIRST=0 回到「有代理就一律走代理」。
UPSTREAM_DIRECT_FIRST = os.getenv("UPSTREAM_DIRECT_FIRST", "1") != "0"
UPSTREAM_DIRECT_CONNECT_TIMEOUT = 3


# ====================== 学习记录库（SQLite） ======================
#
# 写库时遇到别的线程正占着写锁，最多等这么久。记录是尽力而为的（存不进去只记日志），
# 所以宁可丢一条记录也不让学生的请求多卡几秒。压测里单条写入 0.1 毫秒量级，
# 2 秒足够排过几千个排队的写入。
LEARNING_BUSY_TIMEOUT_MS = 2000
# 备份线程多久看一次「距上次备份满一天没有」
LEARNING_BACKUP_CHECK_SECONDS = 3600
LEARNING_BACKUP_EVERY_SECONDS = 86_400
