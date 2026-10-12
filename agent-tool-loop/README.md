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
真实 LLM 后端已实现（`OpenAICompatBackend`，urllib 直连 OpenAI 兼容接口），但本机没有配置密钥，
**未经真实调用实测**。配好环境变量后 `demo.py` 无需改代码即可切换。

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

⚠️ 此后端**未经真实调用实测**（本机无密钥）。

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
- 真实 LLM 后端：**未实测**（无密钥，诚实标注）
