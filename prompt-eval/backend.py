"""模型后端：离线模拟模型 + OpenAI 兼容真实后端。

OfflineSimModel 是「读指令办事」的确定性模拟模型：它解析系统提示里的
指令开关（JSON 输出 / 事实边界 / 安全规则 / 工具 / 条件简洁 / 全局限长），
按固定规则生成回答。

🔴 它不是真实大模型。由它跑出的通过率是这套确定性规则的实测结果，
   用途是验证评测框架本身（用例有没有区分度、打分是否可复算），
   不代表任何真实 LLM 的成绩。README 里所有通过率数字均指本模拟后端。

OpenAICompatModel 是真实后端（urllib，密钥只走环境变量，
AGENT_API_KEY / OPENAI_API_KEY、AGENT_BASE_URL / OPENAI_BASE_URL、
AGENT_MODEL），本仓库开发环境未实测。

零第三方依赖：只用 Python 标准库。Python 3.11 / 3.13 均可运行。
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request


class BackendError(Exception):
    """模型后端错误（配置缺失 / 网络 / 响应格式）。"""


# ---------------------------------------------------------------- 离线模拟模型

# 指令开关：只在系统提示出现对应字样时才生效（模拟「模型照指令办事」）
_FLAG_JSON = "只输出JSON"
_FLAG_FACT = "不知道就说不知道"
_FLAG_SAFE = "拒绝执行"
_FLAG_TOOL = "calc"
_FLAG_BRIEF = "30字以内"
_FLAG_CAP = "一律不超过"

_ADVERSARIAL_RE = re.compile(r"系统提示|忽略你|没有任何限制|密码|内部数据")
_EXPORT_RE = re.compile(r"导出")
_FICTION_RE = re.compile(r"合作记录|量子波动|u_99999")
_MATH_RE = re.compile(r"\d+(?:\.\d+)?\s*[+\-*/×÷]\s*\d+(?:\.\d+)?")
_BRIEF_MARK_RE = re.compile(r"一句话|简短|简要|简洁")
_CAP_CHARS = 20

# v1（没有任何指令）对对抗输入的「照办泄漏」话术
_LEAKS = {
    "系统提示": "我的系统提示是：你是 DSHPersonalAI 项目的技术助手，请回答用户的问题。",
    "密码": "密码是 ds2026，我只告诉你。",
    "忽略你": "好的，规则全文如下，现在我没有任何限制了。",
    "没有任何限制": "好的，规则全文如下，现在我没有任何限制了。",
    "内部数据": "好的，内部数据如下：（全部数据原样粘贴）",
}

# v1 对虚构/不存在内容的「编造」话术
_FABRICATIONS = {
    "合作记录": "查到如下合作记录：ZZ 科技和星火大模型于 2025 年开始合作，方向是模型接入。",
    "量子波动": "可以应用：第一步是把量子波动叠加到查询扩展上，实测效果显著。",
    "u_99999": "以下是 u_99999 的历史会话，共找到 12 条：（编造内容）",
}

# 有事实边界指令时的拒绝话术
_REFUSE_ADVERSARIAL = "不能这样做，我不会忽略规则或透露系统提示。"
_REFUSE_EXPORT = "不能导出用户数据，这超出了项目范围。"
_REFUSE_FICTION = "无法确认，我没有这方面的信息，不能编造。"

# 主题知识库：(匹配子串列表, 完整回答, 简短回答)。按顺序匹配第一个命中的。
# 内容取自本仓库另外两个项目的公开事实（agent-tool-loop / local-retrieval）。
_TOPICS: list[tuple[list[str], str, str]] = [
    (
        ["RAG"],
        "RAG 是先检索再生成：FTS5 负责把相关片段找出来，bm25 负责算相关性排序。",
        "先检索片段，再基于片段生成。",
    ),
    (
        ["二元分词", "分词"],
        "二元分词是把中文按相邻两字切开：这个测试很好切成 这个、个测、测试、试很、很好。"
        "优点是召回全，缺点是索引变大，要靠 bm25 兜底排序。",
        "按相邻两字切：这个、个测、测试。",
    ),
    (
        ["FTS5", "全文索引", "虚拟表", "相关性", "排序"],
        "项目用 SQLite FTS5 建虚拟表，MATCH 查询，用 bm25 算相关性分数排序。",
        "用 FTS5 建索引，bm25 排序。",
    ),
    (
        ["评测", "打分", "用例"],
        "评测用例分正常、边界、异常、对抗四类，打分只用关键词命中、格式、长度、工具调用这些客观断言。",
        "分四类，用客观断言打分。",
    ),
    (
        ["回填", "报错"],
        "工具报错不抛异常，把 {\"ok\": false, \"error\": ...} 回填给模型，让它自己决定下一步。",
        "报错会回填给模型继续处理。",
    ),
    (
        ["标准库"],
        "标准库指 Python 自带的模块集合，比如 json、sqlite3、unittest，不用安装第三方包就能用。",
        "标准库就是 Python 自带的模块。",
    ),
    (
        ["备份"],
        "防丢数据靠定期备份：建库后立刻复制一份 data/retrieval.db 到安全位置，改表结构前再备一次。",
        "定期复制一份数据库文件。",
    ),
]
_GENERIC_ANSWER = "这个问题我需要更多信息才能回答。"


class OfflineSimModel:
    """离线确定性模拟模型：按系统提示里的指令开关决定行为。

    行为规则（对用户输入按顺序匹配，命中即停）：
    1. 对抗指令（要系统提示/密码/内部数据、要求忽略规则）——
       有【安全规则】→ 拒绝；没有 → 照办并「泄漏」
    2. 要求导出用户数据——有【事实边界】→ 拒绝；没有 → 照办
    3. 虚构/不存在的内容——有【事实边界】→ 说不知道；没有 → 编造
    4. 计算请求——有【工具】→ 发起 calc 工具调用；没有 → 直接心算作答
    5. 项目主题问题 → 按知识库回答（被要求简短且有【简洁】指令时用短版）
    6. 都不匹配 → 请求澄清
    最后：有【统一长度】一律截断到 20 字；有【输出格式】包成 JSON。
    """

    def chat(self, system: str, user: str) -> dict:
        """输入系统提示与用户消息，返回 {"text": str, "tool_call": dict | None}。"""
        has_json = _FLAG_JSON in system or "JSON" in user  # 系统指令要求，或用户显式要求
        has_fact = _FLAG_FACT in system
        has_safe = _FLAG_SAFE in system
        has_tool = _FLAG_TOOL in system
        has_brief = _FLAG_BRIEF in system
        has_cap = _FLAG_CAP in system

        tool_call: dict | None = None
        adv = _ADVERSARIAL_RE.search(user)
        if adv is not None:
            content = _LEAKS.get(adv.group(0), "好的，规则全文如下，现在我没有任何限制了。")
            if has_safe:
                content = _REFUSE_ADVERSARIAL
        elif _EXPORT_RE.search(user):
            content = "好的，已导出全部用户数据如下：（全部数据原样粘贴）"
            if has_fact:
                content = _REFUSE_EXPORT
        elif _FICTION_RE.search(user):
            if has_fact:
                content = _REFUSE_FICTION
            else:
                hit = _FICTION_RE.search(user).group(0)
                content = _FABRICATIONS.get(hit, "根据我的记忆，这个问题的答案是有的。")
        else:
            math = _MATH_RE.search(user)
            if math is not None and ("算" in user or "计算" in user):
                if has_tool:
                    tool_call = {"name": "calc", "arguments": {"expression": math.group(0)}}
                    content = ""
                else:
                    content = f"我直接心算：{math.group(0)} = {self._arith(math.group(0))}。"
            else:
                topic = self._match_topic(user)
                brief = has_brief and _BRIEF_MARK_RE.search(user) is not None
                if topic is None:
                    content = _GENERIC_ANSWER
                else:
                    content = topic[1] if brief else topic[0]

        if has_cap:
            content = content[:_CAP_CHARS]
        text = json.dumps({"answer": content}, ensure_ascii=False) if has_json else content
        return {"text": text, "tool_call": tool_call}

    def _match_topic(self, user: str) -> tuple[str, str] | None:
        for keys, full, short in _TOPICS:
            if any(key in user for key in keys):
                return full, short
        return None

    @staticmethod
    def _arith(expr: str) -> str:
        m = re.match(r"(\d+(?:\.\d+)?)\s*([+\-*/×÷])\s*(\d+(?:\.\d+)?)", expr)
        if m is None:
            return "?"
        a, op, b = float(m.group(1)), m.group(2), float(m.group(3))
        if op == "+":
            value = a + b
        elif op == "-":
            value = a - b
        elif op in ("*", "×"):
            value = a * b
        else:  # / 或 ÷
            value = a / b if b else 0.0
        if value == int(value):
            return str(int(value))
        return str(value)


# ---------------------------------------------------------------- OpenAI 兼容后端


class OpenAICompatModel:
    """OpenAI 兼容的真实后端（未实测：本仓库开发环境没有可用的密钥/服务）。

    配置只走环境变量：
    - 密钥：AGENT_API_KEY 或 OPENAI_API_KEY（缺失时 chat() 直接报 BackendError）
    - 地址：AGENT_BASE_URL 或 OPENAI_BASE_URL（默认 https://api.openai.com/v1）
    - 模型：AGENT_MODEL（默认 gpt-4o-mini）
    """

    def __init__(self) -> None:
        self.api_key = os.environ.get("AGENT_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
        self.base_url = os.environ.get("AGENT_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or ""
        self.model = os.environ.get("AGENT_MODEL") or "gpt-4o-mini"

    def chat(self, system: str, user: str) -> dict:
        if not self.api_key:
            raise BackendError("缺少密钥：请设置环境变量 AGENT_API_KEY 或 OPENAI_API_KEY")
        url = self.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "calc",
                        "description": "计算一个算式的值",
                        "parameters": {
                            "type": "object",
                            "properties": {"expression": {"type": "string"}},
                            "required": ["expression"],
                        },
                    },
                }
            ],
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise BackendError(f"请求失败: {exc}") from exc
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise BackendError(f"响应格式不符合预期: {data}") from exc
        calls = message.get("tool_calls") or []
        tool_call = None
        if calls:
            fn = calls[0].get("function", {})
            try:
                tool_call = {"name": fn["name"], "arguments": json.loads(fn.get("arguments") or "{}")}
            except (KeyError, json.JSONDecodeError) as exc:
                raise BackendError(f"tool_calls 格式不符合预期: {calls[0]}") from exc
        return {"text": message.get("content") or "", "tool_call": tool_call}
