# Agent 工具调用循环（agent-tool-loop）

> 把「只能聊天」变成「能动手干活」：模型自主选工具 → 执行 → 结果回填 → 继续回答，直到不再要工具。
> **零第三方依赖**，只用 Python 标准库。**依赖：无**（测试也是标准库 `unittest`）。

---

## 快速开始（三条命令都能直接复制跑通）

```bash
python -m unittest discover -s tests    # 一条命令跑测试：70 项
python demo.py                          # 一条命令看完整调用链（自动建示例库）
python eval_selection.py                # 一条命令跑 20 条用例的选对率
```

- 演示输出写入 `out/run_latest.md`；评测明细写入 `out/eval_selection.md`
- 想换问题：`python demo.py --question "帮我读一下「todo.txt"`
- 只重建示例库：`python demo.py --seed`

---

## 实测数字（2026-10-11，Windows + Python 3.11.7）

| 项 | 数字 | 复现命令 |
|---|---|---|
| 测试 | **70/70 通过**（正常/异常/空数据三类分支都覆盖） | `python -m unittest discover -s tests` |
| 选对工具正确率 | **20/20**（固定用例，非随机） | `python eval_selection.py` |
| 演示调用链 | **3 轮**（search_history → calc → 最终回答），3.7 ms | `python demo.py` |

⚠️ **诚实声明（避免把推断写成实测）**：上面的 20/20 是 **ScriptedBackend（离线确定性规则后端）** 跑出来的数字，
验证的是**循环 + 注册表 + 参数校验 + 错误回填**这条工程链路，不是某个真实大模型的选工具能力。

**真模型已实测（2026-10-29）**：`OpenAICompatBackend` 直连 `deepseek-ai/DeepSeek-V3.2`（经本机 OmniRoute 网关），
20 条**完全通过 5 条**。但这 5 条**不能读成「模型只会选对 25%」**——把 15 条失败拆开看：

| 失败类型 | 条数 | 含义 |
|---|---|---|
| **判据与措辞不匹配** | **12** | 模型**确实调了工具、也给了正确答案**，只是说法不是判据要的那句。例：C11 问 `7 % 3`，模型答「7 除以 3 余 1」，判据要的是字面「计算结果是 1」 → 子串不命中 |
| **模型真的没调工具** | **3**（C05 / C07 / C18） | 🔴 **这 3 条才是真实的能力差距**（3/20） |

→ **所以这个数字衡量的是「关键词判据在真模型上的通过率」，不是「模型会不会用工具」。**
→ **下一步**（已在 README 记为未完成）：判据从「子串命中」升级成更稳的客观检查（结构化字段 / 结果等价性判断）。
（这一条 10-28 就预判过，实测证实了。）

---

## 三个真实工具（SPEC 要求 ≥3，每个一个文件）

| 工具 | 干什么 | 演示能力 |
|---|---|---|
| `search_history` | 按关键词查本地 SQLite 历史会话（LIKE 特殊字符做了转义） | 与项目②检索联动；空命中返回 0 条而不是报错 |
| `calc` | 安全算术求值：AST 白名单（数字/括号/+ - * / // % **），**不用 eval** | 参数校验：`1+`、`abc`、`1/0`、`9**99999`、超长表达式全部明确报错 |
| `read_note` | 读取 notes 目录下的文本文件 | 安全边界：绝对路径、`..` 上跳、逃出白名单目录一律拦截 |

---

## 关键设计

- **错误绝不向上抛**：工具内部报错（除零/文件不存在/路径越界）以
  `{"ok": false, "error": "..."}` 回填给模型继续回答——整个循环不会因为一个工具挂掉而失败（有测试守着）
- **root/db_path 不给模型设**：`read_note` 的白名单目录、`search_history` 的库路径都在程序侧绑定，
  模型只能传 `name`/`keyword`，否则等于给模型开了改路径的口子
- **max_rounds 兜底**：模型若一直要工具，5 轮后停止并明确标注 `stopped: max_rounds`，不会死循环
- **调用链可复现**：`run_loop` 返回每一轮的「模型说了什么 / 要调什么 / 参数 / 返回了什么」

---

## 接真实模型（可选，密钥只走环境变量）

| 环境变量 | 作用 | 默认 |
|---|---|---|
| `AGENT_API_KEY`（或 `OPENAI_API_KEY`） | API 密钥，**必须**，不写代码不落盘 | 无 |
| `AGENT_BASE_URL`（或 `OPENAI_BASE_URL`） | OpenAI 兼容接口基地址 | `https://api.openai.com/v1` |
| `AGENT_MODEL` | 模型名 | `gpt-4o-mini` |

```python
from agent_loop import OpenAICompatBackend, run_loop
from tools import build_registry
result = run_loop(OpenAICompatBackend(), build_registry(), "你的问题")
```

✅ 此后端**已于 2026-10-29 真调用实测**（`deepseek-ai/DeepSeek-V3.2`，经本机网关）。
🔴 **接真后端时才会暴露的三类问题（离线全绿测不出来）**：
1. **请求格式**：发回上游的 `assistant.tool_calls` 必须用 OpenAI 原生格式（`arguments` 是 **JSON 字符串**、带 `type`/`function` 嵌套），内部简化格式会被上游拒（400 "Input should be a valid string"）。
2. **本机代理**：`urllib` 在 Windows 上默认读注册表代理 → 本地回环请求被丢给代理 → 502。**必须绕开代理**（`ProxyHandler({})`）。
3. **超时与重试**：多轮调用时网关本地队列上限 15 秒 → 504。**按项目约束 `timeout=180s / retries=2`**（只对超时/5xx/429/504 重试）。

---

## 已知边界（不做什么）

- 不做多 Agent 协作、记忆系统、向量库（SPEC 边界）
- ScriptedBackend 是**关键词规则路由**，只覆盖演示/评测里的问法，不等于真实模型的语言理解
- 工具结果回填不做截断（read_note 上限 64KB，量级可控）
- CI：本仓库无远程仓库，SPEC 的「CI Ubuntu+Windows 绿」以两次本地 Windows 实测代替（README 与 out/ 数字均来自实际运行），Linux 侧待有仓库后由 CI 覆盖

---

## 交回数字汇总

- 测试通过：**70/70**
- 选对工具：**20/20**（用例集 `eval_cases.json`，可复算）
- 演示调用链：**3 轮，3.7 ms**（SAMPLE_REPORT.md 有完整记录，位于项目根目录）
- 真实 LLM 后端：**已实测**（2026-10-29，`deepseek-ai/DeepSeek-V3.2`）—— 完全通过 5/20，其中**真实能力差距是 3 条**（模型没调工具），其余 12 条是关键词判据与自由措辞不匹配
