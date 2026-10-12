"""Agent 工具调用循环（Function Calling 的最小可用实现）。

流程：用户消息 → 模型 → 返回 tool_calls → 执行工具 → 结果回填 → 模型继续
→ 直到模型不再要求工具，输出最终回答。

设计要点
- 模型后端可插拔：ScriptedBackend（离线确定性，测试/演示/评测用）与
  OpenAICompatBackend（真实调用，密钥只走环境变量，本仓库开发环境未实测）。
- 工具报错绝不向上抛：错误以 {"ok": false, "error": ...} 回填给模型继续对话，
  而不是让整个请求失败。
- 参数校验失败 / 未知工具 / 路径越界都产生明确错误信息，不崩、不静默。

零第三方依赖：只用 Python 标准库。Python 3.11 / 3.13 均可运行。
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable


class ToolError(Exception):
    """工具参数/业务错误：会被回填给模型，而不是让整个请求失败。"""


class BackendError(Exception):
    """模型后端错误（网络/鉴权/响应格式）。"""


# ---------------------------------------------------------------- 工具注册表


@dataclass
class Tool:
    """一个可被模型调用的工具。

    parameters 是简化版 schema：{参数名: {"type", "required", "description"}}，
    type 支持 string / integer / number / boolean。
    """

    name: str
    description: str
    parameters: dict[str, dict[str, Any]]
    func: Callable[..., dict]

    _TYPE_CHECKS = {
        "string": lambda v: isinstance(v, str),
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "boolean": lambda v: isinstance(v, bool),
    }

    def validate(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """校验并过滤参数。缺必填 / 类型错 → ToolError（明确报错，不静默）。"""
        if not isinstance(arguments, dict):
            raise ToolError(f"参数必须是对象，收到 {type(arguments).__name__}")
        out: dict[str, Any] = {}
        for pname, spec in self.parameters.items():
            if pname not in arguments or arguments[pname] is None:
                if spec.get("required", False):
                    raise ToolError(f"缺少必填参数: {pname}")
                continue
            value = arguments[pname]
            ptype = spec.get("type", "string")
            check = self._TYPE_CHECKS.get(ptype)
            if check is None:
                raise ToolError(f"工具 {self.name} 的参数 {pname} 声明了未知类型: {ptype}")
            if not check(value):
                raise ToolError(f"参数 {pname} 类型应为 {ptype}，收到 {type(value).__name__}")
            out[pname] = value
        return out

    def openai_schema(self) -> dict[str, Any]:
        """转成 OpenAI tools 字段格式（供真实后端使用）。"""
        props = {
            pname: {"type": spec.get("type", "string"), "description": spec.get("description", "")}
            for pname, spec in self.parameters.items()
        }
        required = [pname for pname, spec in self.parameters.items() if spec.get("required", False)]
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {"type": "object", "properties": props, "required": required},
            },
        }


@dataclass
class ToolRegistry:
    tools: dict[str, Tool] = field(default_factory=dict)

    def register(self, tool: Tool) -> None:
        if tool.name in self.tools:
            raise ValueError(f"工具重复注册: {tool.name}")
        self.tools[tool.name] = tool

    def spec_list(self) -> list[dict[str, Any]]:
        return [t.openai_schema() for t in self.tools.values()]

    def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """执行工具。未知工具 / 参数不合法 → ToolError（调用方决定如何回填）。"""
        tool = self.tools.get(name)
        if tool is None:
            available = ", ".join(sorted(self.tools)) or "无"
            raise ToolError(f"未知工具: {name}（可用: {available}）")
        if not isinstance(arguments, dict):
            raise ToolError(f"参数必须是对象，收到 {type(arguments).__name__}")
        kwargs = tool.validate(dict(arguments))
        return tool.func(**kwargs)


# ---------------------------------------------------------------- 模型后端


@dataclass
class BackendResponse:
    content: str
    tool_calls: list[dict[str, Any]]  # 每项: {"id", "name", "arguments"}


class ModelBackend:
    """模型后端协议：输入 messages + 工具清单，输出 BackendResponse。"""

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> BackendResponse:
        raise NotImplementedError


class ScriptedBackend(ModelBackend):
    """离线确定性后端：用固定规则模拟「模型选工具 → 用结果回答」。

    它**不是真实大模型**。README / SAMPLE_REPORT 里由它跑出的数字
    （选对工具 x/20 等）都是这套确定性规则的实测结果，与真实 LLM 无关。

    规则（对输入文本做确定性路由）：
    - 含「算/计算」且有含运算符的数字串 → calc
    - 含「算/计算」且提到「命中条数乘以 N」且有前一步搜索结果 → calc(count*N)
    - 含「搜索/查/历史/会话/聊过」→ search_history（关键词取引号内或动词后）
    - 含「读/打开/看看」→ read_note（文件名取引号内或动词后）
    - 都不匹配 → 不调工具，直接回答
    - 上一轮工具报错 → 不再继续调工具，把错误复述给用户
    """

    _QUOTED = re.compile(r"[“\"'「‘]([^”\"'」’]{1,60})[”\"'」’]")
    _SEGMENT_SPLIT = re.compile(r"[，,；;]?\s*(?:然后|再|接着)[，,]?\s*")
    _EXPR = re.compile(r"[0-9(][0-9+\-*/%. ()]*")
    _TIMES_N = re.compile(r"乘以\s*(\d+)")
    _LIMIT_N = re.compile(r"(?:最多|只)(?:返回)?\s*(\d+)\s*条")
    _SEARCH_VERB = re.compile(r"搜索|检索|查一下|查查|查|历史|会话|聊过|找")
    _SEARCH_KW = re.compile(
        r"(?:搜索|检索|查一下|查查|查|找找|找)\s*(?:一下)?(?:关于)?"
        r"(.+?)(?:[。！？.!?]|的讨论|的记录|的会话|$)"
    )
    _NOTE_VERB = re.compile(r"读|打开|看看|笔记")

    def __init__(self) -> None:
        self._call_seq = 0

    def _next_id(self) -> str:
        self._call_seq += 1
        return f"call_{self._call_seq}"

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> BackendResponse:
        user_text = next(
            (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), ""
        )
        last = messages[-1]
        if last.get("role") == "tool":
            payload = json.loads(last.get("content") or "{}")
            if not payload.get("ok"):
                return BackendResponse(content=self._final_answer(last), tool_calls=[])
            nxt = self._next_pending(str(user_text), messages, payload.get("data"))
            if nxt is not None:
                return BackendResponse(content="", tool_calls=[nxt])
            return BackendResponse(content=self._final_answer(last), tool_calls=[])
        call = self._next_pending(str(user_text), messages, None)
        if call is not None:
            return BackendResponse(content="", tool_calls=[call])
        return BackendResponse(content=f"这个问题不需要工具，我直接回答：{user_text}", tool_calls=[])

    # -- 内部 -----------------------------------------------------------

    def _next_pending(
        self, user_text: str, messages: list[dict[str, Any]], prior_data: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        done = {m.get("name") for m in messages if m.get("role") == "tool"}
        segments = [s for s in self._SEGMENT_SPLIT.split(user_text) if s.strip()]
        for segment in segments:
            call = self._pick_tool(segment, prior_data)
            if call is not None and call["name"] not in done:
                return call
        return None

    def _pick_tool(self, segment: str, prior_data: dict[str, Any] | None) -> dict[str, Any] | None:
        expr: str | None = None
        m = self._EXPR.search(segment)
        if m:
            candidate = m.group(0).strip()
            if any(op in candidate for op in "+-*/%"):
                expr = candidate
        if ("算" in segment or "计算" in segment or "等于多少" in segment):
            if expr:
                return {"id": self._next_id(), "name": "calc", "arguments": {"expression": expr}}
            if prior_data is not None:
                m2 = self._TIMES_N.search(segment)
                if m2:
                    count = prior_data.get("count", 0)
                    return {
                        "id": self._next_id(),
                        "name": "calc",
                        "arguments": {"expression": f"{count}*{m2.group(1)}"},
                    }
        if self._SEARCH_VERB.search(segment):
            quoted = self._QUOTED.search(segment)
            if quoted:
                keyword = quoted.group(1).strip()
            else:
                m3 = self._SEARCH_KW.search(segment)
                keyword = m3.group(1).strip(" 的。") if m3 else ""
            arguments: dict[str, Any] = {"keyword": keyword}
            m4 = self._LIMIT_N.search(segment)
            if m4:
                arguments["limit"] = int(m4.group(1))
            return {"id": self._next_id(), "name": "search_history", "arguments": arguments}
        if self._NOTE_VERB.search(segment):
            quoted = self._QUOTED.search(segment)
            if quoted:
                name = quoted.group(1).strip()
            else:
                m5 = re.search(r"(?:读一下|读读|读|打开|看看)\s*(?:一下)?(.+?)(?=[。！？!?]|的|看看|$)", segment)
                name = m5.group(1).strip() if m5 else ""
            return {"id": self._next_id(), "name": "read_note", "arguments": {"name": name}}
        return None

    def _final_answer(self, last_tool_msg: dict[str, Any]) -> str:
        payload = json.loads(last_tool_msg.get("content") or "{}")
        name = last_tool_msg.get("name", "")
        if not payload.get("ok"):
            return f"工具 {name} 返回错误：{payload.get('error')}。我先基于已有信息回答到这里。"
        data = payload.get("data") or {}
        if name == "search_history":
            items = data.get("results") or []
            brief = "；".join(
                f"「{it.get('session_id')}」{str(it.get('content'))[:40]}" for it in items[:3]
            )
            return f"在历史会话里找到 {data.get('count', 0)} 条相关记录：{brief or '（无内容）'}"
        if name == "calc":
            return f"计算结果是 {data.get('text')}"
        if name == "read_note":
            preview = str(data.get("content"))[:50]
            return (
                f"已读取笔记「{data.get('name')}」，共 {data.get('chars')} 字、"
                f"{data.get('lines')} 行，开头是：{preview}"
            )
        return f"工具 {name} 返回：{json.dumps(data, ensure_ascii=False)[:200]}"


class OpenAICompatBackend(ModelBackend):
    """OpenAI 兼容 /chat/completions 后端（urllib 实现，零第三方依赖）。

    配置只走环境变量（密钥不写代码、不落盘、不进 commit）：
      AGENT_API_KEY / OPENAI_API_KEY   —— API 密钥（必须）
      AGENT_BASE_URL / OPENAI_BASE_URL —— 接口基地址，默认 https://api.openai.com/v1
      AGENT_MODEL                      —— 模型名，默认 gpt-4o-mini

    ⚠️ 诚实声明：本仓库开发环境没有配置密钥，此后端**未经真实调用实测**。
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 30,
    ) -> None:
        self.api_key = (
            api_key
            or os.environ.get("AGENT_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or ""
        )
        self.base_url = (
            base_url
            or os.environ.get("AGENT_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or "https://api.openai.com/v1"
        ).rstrip("/")
        self.model = model or os.environ.get("AGENT_MODEL") or "gpt-4o-mini"
        self.timeout = timeout
        if not self.api_key:
            raise BackendError(
                "缺少 API Key：请设置环境变量 AGENT_API_KEY（或 OPENAI_API_KEY）。"
                "密钥只走环境变量，不写进代码。"
            )

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> BackendResponse:
        body: dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            body["tools"] = tools
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise BackendError(f"模型接口返回 HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise BackendError(f"无法连接模型接口: {exc.reason}") from exc
        try:
            message = payload["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise BackendError(f"模型接口响应格式异常: {json.dumps(payload, ensure_ascii=False)[:300]}") from exc
        calls: list[dict[str, Any]] = []
        for tc in message.get("tool_calls") or []:
            fn = tc.get("function") or {}
            try:
                arguments = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError as exc:
                raise BackendError(
                    f"工具 {fn.get('name')} 的参数不是合法 JSON: {str(fn.get('arguments'))[:200]}"
                ) from exc
            calls.append(
                {
                    "id": tc.get("id") or f"call_{len(calls)}",
                    "name": fn.get("name", ""),
                    "arguments": arguments,
                }
            )
        return BackendResponse(content=message.get("content") or "", tool_calls=calls)


# ---------------------------------------------------------------- 调用循环


def run_loop(
    backend: ModelBackend,
    registry: ToolRegistry,
    user_message: str,
    system: str | None = None,
    max_rounds: int = 5,
) -> dict[str, Any]:
    """跑一次完整调用循环。

    返回 {"answer", "round_count", "stopped", "rounds"}：
    - answer: 模型最终回答（stopped="max_rounds" 时为空串）
    - rounds: 每轮记录（模型说了什么、要调什么、参数、返回了什么），可复现调用链
    """
    messages: list[dict[str, Any]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user_message})
    rounds: list[dict[str, Any]] = []
    for round_no in range(1, max_rounds + 1):
        resp = backend.chat(messages, registry.spec_list())
        if not resp.tool_calls:
            rounds.append(
                {"round": round_no, "model_content": resp.content, "tool_calls": [], "tool_results": []}
            )
            return {"answer": resp.content, "round_count": round_no, "stopped": "", "rounds": rounds}
        messages.append(
            {"role": "assistant", "content": resp.content, "tool_calls": resp.tool_calls}
        )
        results: list[dict[str, Any]] = []
        for call in resp.tool_calls:
            try:
                data = registry.execute(str(call.get("name", "")), call.get("arguments") or {})
                payload: dict[str, Any] = {"ok": True, "data": data}
            except ToolError as exc:
                payload = {"ok": False, "error": str(exc)}
            except Exception as exc:  # 工具内部意外错误也回填，不让整个请求失败
                payload = {"ok": False, "error": f"工具内部异常 {type(exc).__name__}: {exc}"}
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": str(call.get("id", "")),
                    "name": str(call.get("name", "")),
                    "content": json.dumps(payload, ensure_ascii=False),
                }
            )
            results.append(
                {
                    "id": call.get("id", ""),
                    "name": call.get("name", ""),
                    "arguments": call.get("arguments"),
                    "ok": payload["ok"],
                    "result": payload.get("data"),
                    "error": payload.get("error"),
                }
            )
        rounds.append(
            {"round": round_no, "model_content": resp.content, "tool_calls": resp.tool_calls, "tool_results": results}
        )
    return {"answer": "", "round_count": max_rounds, "stopped": "max_rounds", "rounds": rounds}
