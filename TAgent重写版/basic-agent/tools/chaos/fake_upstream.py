"""可控延迟 / 可控故障的 OpenAI 兼容假上游，只给压测用。

GET  /control?delay=1.5&token_delay=0.03&mode=ok|error|hang|drop&answer=plain|markdown&reset=1   调行为、清计数
GET  /stats                                                                调用计数与最大并发
POST /v1/chat/completions                                                  按 prompt 认出请求类型，回合法 JSON

模拟真实模型的快慢（流式）时再加这几项，不给就和以前一样：
  first_delay=3          答疑第一个字之前等几秒（先思考的模型要等更久）
  qa_chunk=3             答疑每段几个字（真实模型一段一两个到几个字）
  json_first_delay=0.6   出题、批改这类要 JSON 的调用，第一个字之前等几秒（不给就同 first_delay）
  json_token_delay=0.08  它们每 20 个字之间隔几秒（不给就同 token_delay）；0.08 约每秒 250 字
出卷、闪卡的提示词也认得（「出卷助手」），照着要的题量回合法的题，每次的题都不一样，过得了去重。
"""
import itertools
import json
import os
import re
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # basic-agent/
from app.schema.essay import RUBRIC_POINTS  # noqa: E402

STATE = {
    "delay": 1.0, "token_delay": 0.03, "mode": "ok", "answer": "plain",
    "first_delay": 0.0, "qa_chunk": 1, "json_first_delay": None, "json_token_delay": None,
}
DRAFT_SEQ = itertools.count(1)
STATS = {"calls": 0, "active": 0, "max_active": 0, "completed": 0}
LOCK = threading.Lock()
ANSWER = "到达率 λ 指单位时间内到达系统的平均顾客数，是排队模型最基本的输入参数之一。" * 3
# answer=markdown：带公式、中文引号旁的加粗、表格、代码的回答，压前端的流式渲染
MARKDOWN_ANSWER = (
    "这本质上是一个**“分时段到达率 + 多方案窗口数对比”的仿真实验**。\n\n"
    "## 1. 到达率\n\n第 \\(i\\) 个时段的到达率：\n\n\\[\n\\lambda_i = \\frac{N_i}{T_i}\n\\]\n\n"
    "| 时段 | 到达率 \\(\\lambda_i\\) |\n|---|---|\n| 8:00–10:00 | 60 |\n| 10:00–12:00 | 40 |\n\n"
    "服务强度 $\\rho = \\lambda/(c\\mu)$ 必须小于 1，参考文献 \\[1\\]。\n\n"
    "```python\nwait = x**2  # 代码里的 ** 不是加粗\n```\n\n"
    "$$\nW_q = \\frac{L_q}{\\lambda}\n$$\n"
)


def answer_for(prompt: str):
    for name, points in RUBRIC_POINTS.items():
        if points[0] in prompt:
            payload = {"hits": list(points[:3]), "misses": list(points[3:]), "comment": f"{name}：命中前三条，缺第四条。"}
            if "flagged_paragraphs" in prompt:
                payload["flagged_paragraphs"] = [2]
            return payload
    if "逐句批注" in prompt:
        ids = re.findall(r"^(P\d+S\d+) ", prompt, flags=re.M)
        items = []
        if ids:
            items.append({"sentence_id": ids[0], "kind": "issue", "comment": "这句下结论没有给依据。"})
        if len(ids) > 1:
            items.append({"sentence_id": ids[-1], "kind": "praise", "comment": "这句把结论收住了。"})
        return {"items": items}
    if "小论文题" in prompt:
        return {"title": "排队论视角下的银行窗口配置", "requirements": ["用 M/M/c 模型估算平均等待时间", "写明到达与服务的假设"], "suggested_chars": 1000}
    if "出卷助手" in prompt:
        return quiz_draft(prompt)
    return None


def quiz_draft(prompt: str):
    """出卷、闪卡的一路：照提示词要的题型和题量上限回合法的题（同 tests 里 ExamLLM / ScriptedShardLLM 的写法）。
    编号全局递增：同一张卷的几路、同一组闪卡的几片题目都不一样，去重不会把它们删掉。"""
    tag = next(DRAFT_SEQ)
    if "**填空题**" in prompt:
        count = int(re.search(r"填空题 \d+~(\d+) 道", prompt).group(1))
        return {"title": "排队论与仿真基础", "cloze": [
            {"cue": f"提示 {tag}-{i}", "text": f"第 {tag}-{i} 句的空格填 ____ 即可。", "accept": [f"答案{tag}-{i}"],
             "match_mode": "text", "explanation": "解析", "points": 3}
            for i in range(count)
        ]}
    if "**选择题**" in prompt:
        count = int(re.search(r"选择题 \d+~(\d+) 道", prompt).group(1))
        # 整卷的选择题不收 title（多了会校验失败），卡组标题由填空那几片给
        return {"choice": [
            {"question": f"第 {tag}-{i} 题选哪个？", "options": [f"选项{tag}-{i}", "干扰甲", "干扰乙", "干扰丙"],
             "correct_index": 0, "explanation": "解析", "points": 5}
            for i in range(count)
        ]}
    return {"essay": [{"question": f"论述第 {tag} 题", "reference_answer": "参考答案",
                       "rubric": "①要点一②要点二③要点三", "points": 15}]}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):
        pass

    def _json(self, status, body):
        raw = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        if url.path == "/control":
            for key in ("delay", "token_delay", "first_delay", "json_first_delay", "json_token_delay"):
                if key in query:
                    STATE[key] = float(query[key][0])
            if "qa_chunk" in query:
                STATE["qa_chunk"] = max(1, int(query["qa_chunk"][0]))
            if "mode" in query:
                STATE["mode"] = query["mode"][0]
            if "answer" in query:
                STATE["answer"] = query["answer"][0]
            if "reset" in query:
                with LOCK:
                    STATS.update(calls=0, max_active=0, completed=0)
            return self._json(200, STATE)
        if url.path == "/stats":
            with LOCK:
                return self._json(200, dict(STATS))
        return self._json(404, {})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(length) or b"{}")
        with LOCK:
            STATS["calls"] += 1
            STATS["active"] += 1
            STATS["max_active"] = max(STATS["max_active"], STATS["active"])
        try:
            mode = STATE["mode"]
            if mode == "error":
                return self._json(500, {"error": {"message": "fake upstream error", "type": "server_error"}})
            if mode == "hang":
                time.sleep(3600)
                return
            prompt = data["messages"][-1]["content"]
            if data.get("stream"):
                return self._stream(data, drop=(mode == "drop"))
            time.sleep(STATE["delay"])
            payload = answer_for(prompt)
            content = json.dumps(payload, ensure_ascii=False) if payload is not None else ANSWER
            self._json(200, {
                "id": "chatcmpl-fake", "object": "chat.completion", "created": int(time.time()),
                "model": data.get("model", "fake-model"),
                "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            })
            with LOCK:
                STATS["completed"] += 1
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            with LOCK:
                STATS["active"] -= 1

    def _stream(self, data, *, drop):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

        def frame(delta, finish=None):
            body = {"id": "chatcmpl-fake", "object": "chat.completion.chunk", "created": int(time.time()),
                    "model": data.get("model", "fake-model"),
                    "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
            self.wfile.write(f"data: {json.dumps(body, ensure_ascii=False)}\n\n".encode())
            self.wfile.flush()

        frame({"role": "assistant", "content": ""})
        # 后端的结构化调用（批改、出卷）也走流式（为了认出上游卡住），要的是 JSON：和非流式一样按 prompt 认，
        # 认出来就把 JSON 分块发出去；认不出的才是答疑，发那段固定回答
        payload = answer_for(data["messages"][-1]["content"])
        if payload is not None:
            text = json.dumps(payload, ensure_ascii=False)
            pieces = [text[i:i + 20] for i in range(0, len(text), 20)]
            first_delay = STATE["first_delay"] if STATE["json_first_delay"] is None else STATE["json_first_delay"]
            token_delay = STATE["token_delay"] if STATE["json_token_delay"] is None else STATE["json_token_delay"]
        else:
            text = MARKDOWN_ANSWER if STATE["answer"] == "markdown" else ANSWER
            pieces = [text[i:i + STATE["qa_chunk"]] for i in range(0, len(text), STATE["qa_chunk"])]
            first_delay, token_delay = STATE["first_delay"], STATE["token_delay"]
        time.sleep(first_delay)
        for index, piece in enumerate(pieces):
            if drop and index == 20:
                self.connection.shutdown(socket.SHUT_RDWR)
                return
            frame({"content": piece})
            time.sleep(token_delay)
        frame({}, "stop")
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()
        with LOCK:
            STATS["completed"] += 1


if __name__ == "__main__":
    ThreadingHTTPServer.daemon_threads = True
    ThreadingHTTPServer(("127.0.0.1", int(os.getenv("FAKE_UPSTREAM_PORT", "9100"))), Handler).serve_forever()
