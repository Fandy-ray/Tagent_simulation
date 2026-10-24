# RAG、出题、判题请求链路

## RAG

1. 浏览器提交 `model + user_question`。
2. WebUI 根据模型前缀选择全局代理或私有内部代理。
3. basic-agent 校验请求与 provider。
4. `LangChainRAGSimulator` 线程安全初始化知识分块、Embedding 与 FAISS。
5. 检索四个相似片段，拼成 reference。
6. 选中 provider 的 ChatOpenAI 客户端生成答案。

## 出题

`generate_quiz()` 随机选择知识片段，要求上游只返回 JSON。`JsonOutputParser + QuizQuestion` 校验标题和问题长度，因此普通 OpenAI Chat Completions 服务即可使用，不要求 tool calling。

## 判题

`review_quiz()` 先按题目检索参考上下文，再要求上游返回 `is_correct`、`score`、`comment`、`correct_answer`。`QuizReview` 限制评分范围 0-100。

## 流式聊天

`stream_answer()` 在检索完成后调用 LangChain `stream()`；`openai_routes.py` 将每个真实 token 封装为 OpenAI SSE chunk，最后发送 stop chunk 与 `[DONE]`。

## 闪卡

接口两个，走同一张图 `app/agent/graphs/flash.py`，只出能本地判定的题型：填空 + 选择。

- `POST /quiz/flash/stream` → `ExamService.stream_flash_deck()`：**边写边给**，前端用的是这个；
- `POST /quiz/flash/generate` → `ExamService.generate_flash_deck()`：一次拿完整组。

**取材**：`nodes.sample_quiz_material()` 调知识库的 `sample_exam_pieces()`，只用教材片段
（论文片段只给整卷大题——材料切得小，分到论文片段的那一片只能去考论文独有的细节）。
`deal_shards()` 把片段轮流发牌成 3 份，三片**并发**各出 3~4 张——每片拿到的材料互不相同，
这是并发分片不撞考点的主要手段（整卷那边实测过「把已考清单塞回 prompt」，结果是重复更多）。

**边写边给**：每片用流式调用（`nodes.json_call_streaming`），`app/util/json_items.py` 在
数组里的一张卡收口（右花括号）时就把它拆出来、用 `DraftFlashCard` / `DraftFlashChoice` 校验，
合格的经 LangGraph 的 custom 流交出去。服务层逐张过泄题检查（`exam_quality.violations`）、
跨片去重（`CardDeduper`）、按到达先后编号 F1..，一行一个 JSON 发出：

```text
{"type": "deck", "deck_id", "title"}      材料已抽到、各片已发出
{"type": "title", "title"}                模型写出了卡组标题
{"type": "card", "card": {...}}           一张公开卡（带答案）
{"type": "done", "total_cards"}
{"type": "error", "message", "code"}      之后出错时的最后一行
```

第一行之前的错误（闸门满、选了空笔记本）照旧是普通的 429 / 422。已经发出卡之后某一片失败，
照常收尾；一张没发出才报错，报上游原话。一片里坏了一张只丢那一张，不让整片重来。

**一次拿完**：各片写完后 `assemble` 删坏卡、`dedupe_cards()` 按归一化答案与挖空句去重、
把选择卡交错进填空卡之间，低于 `FLASH_DECK_MIN_CARDS` 判 502。

出卡 prompt 复用 `build_cloze_prompt(..., count_range=..., deck_mode=True)`，
整卷调用方不传关键字参数，输出与改造前逐字一致。

`to_public_deck()` / `public_card()` 与整卷的 `to_public()` 相反，**故意下发答案**（`accept` /
`accept_normalized` / `explanation`）：翻卡就是给用户看答案，判定也在浏览器本地做，
为此多一次往返只会让「零等待」落空。闪卡是复习工具，没有分数完整性可言。这条取舍只在
闪卡这条路径上成立，`to_public()` 一个字都没改。卡组**不进任何缓存**（服务端没有读者），
更不能借用整卷的 `exam_cache`，免得 `deck_id` 走进 `review_exam` 造成类型混淆。

闪卡**没有判卷接口**：前端 `$lib/data/cloze.ts` 是 `_normalize_text_answer` /
`cloze_matches` 的 TS 版，参考答案那一侧直接用后端下发的 `accept_normalized`，
只归一用户输入。两边的用例表在 `tests/test_flash_schema.py::NORMALIZE_CASES`。

## 整卷测评

`app/schema/exam.py` 定义公开卷、答案卷和评审结构；`app/api/exam.py` 装配出卷/判卷接口；
`app/repository/exam_cache.py` 用线程安全的 TTL/LRU 缓存保存试卷及锁定的 `served_model_id`。

出卷走 `app/agent/graphs/exam.py`：七路同时写——大题三路各一道（计算 / 建模设计 / 分析或对比），
填空两路、选择两路各拿一片不同的教材片段、第一路专管核心概念；组卷时删违规题、填空选择一起去重，
最后 8~10 道填空、6~8 道选择、2~3 道大题，总分归一为 100。

公开响应递归去除答案和 provider 信息。判卷时客观题本地比较，主观题由生成该卷的同一模型批量评审；请求模型不一致返回 422，模型失效返回 410。
