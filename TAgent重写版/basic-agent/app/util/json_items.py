"""边收边拆模型正在写的 JSON：数组里的一项写完就交出去，不等整段写完。

闪卡要「第一张立马出」：一片四张卡要写两三秒，第一张写完时才过去不到一秒。
等整段 JSON 收齐再解析，第一张就得陪着后面三张一起等。

只认出题用的这种形状：

    {"title": "...", "cloze": [ {...}, {...} ]}

顶层对象里的数组，数组里的对象一收口（右花括号）就把它的原文交出去。字符串里的
括号、转义的引号按 JSON 规则跳过；开头的 ```json 包装、前后的说明文字不碍事。
交出去的只是原文，合不合法由调用方用自己的模型类校验。
"""

from __future__ import annotations

import json
import re

_TITLE = re.compile(r'"title"\s*:\s*("(?:[^"\\]|\\.)*")')


class JsonItemScanner:
    def __init__(self) -> None:
        self._text = ""
        self._pos = 0  # 下一个要看的字符
        self._stack: list[str] = []  # 还没收口的 { 和 [
        self._in_string = False
        self._escaped = False
        self._item_start: int | None = None
        self._top: list[str] = []  # 顶层对象自己的字符（不含各项的内容），找 title 用
        self.title: str | None = None

    def feed(self, piece: str) -> list[str]:
        """喂进新收到的一块，返回这一块里写完的各项原文（可能一项也没有）。"""
        self._text += piece
        items: list[str] = []
        text = self._text
        for index in range(self._pos, len(text)):
            char = text[index]
            if len(self._stack) == 1:
                self._top.append(char)
            if self._in_string:
                if self._escaped:
                    self._escaped = False
                elif char == "\\":
                    self._escaped = True
                elif char == '"':
                    self._in_string = False
                continue
            if not self._stack and char != "{":
                continue  # 第一个 { 之前的包装和说明
            if char == '"':
                self._in_string = True
            elif char in "{[":
                if char == "{" and self._stack == ["{", "["]:
                    self._item_start = index
                self._stack.append(char)
            elif char in "}]":
                if self._stack:
                    self._stack.pop()
                if char == "}" and self._stack == ["{", "["] and self._item_start is not None:
                    items.append(text[self._item_start : index + 1])
                    self._item_start = None
        self._pos = len(text)
        if self.title is None:
            self._find_title()
        return items

    def _find_title(self) -> None:
        match = _TITLE.search("".join(self._top))
        if match:
            try:
                self.title = json.loads(match.group(1))
            except ValueError:
                pass
