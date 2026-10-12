# SAMPLE_REPORT · 一次真实运行的完整调用链

> 由 `python demo.py` 实际生成（out/run_latest.md 同步留存），数据为合成示例，无隐私。
> 本报告存于项目根目录：out/ 被 .gitignore 忽略，证据文件需被 git 追踪。
> 运行环境：Windows + Python 3.11.7，实测时间 2026-10-11 18:22:46。

- 后端：ScriptedBackend（离线确定性规则，非真实 LLM）
- 轮次：3　耗时：3.7 ms

**用户问题**：帮我搜索历史会话里关于「二元分词」的讨论，然后算一下命中条数乘以 3 等于多少

## 第 1 轮

- 要调工具：search_history　参数：`{"keyword": "二元分词"}`
- 执行 search_history → ok：`{"count": 2, "results": [{"session_id": "s01", "role": "user", "content": "我们讨论一下二元分词的实现思路吧", ...}, {"session_id": "s03", ...}]}`

## 第 2 轮

- 模型拿到搜索结果（count=2），继续要工具：calc　参数：`{"expression": "2*3"}`（**用上了上一轮的返回值**）
- 执行 calc → ok：`{"expression": "2*3", "value": 6, "text": "6"}`

## 第 3 轮

- 模型说：计算结果是 6（不再要工具，循环结束）

## 最终回答

计算结果是 6

---

## 错误回填的实测样例（第二条命令可得）

把问题换成 `计算 1/0`，工具报错**不会**让整个请求失败，而是回填给模型继续回答：

- 第 1 轮：calc `{"expression": "1/0"}` → 报错：`除数为零`
- 第 2 轮模型说：工具 calc 返回错误：除数为零。我先基于已有信息回答到这里。

## 选对工具正确率（验收标准 2 复现）

`python eval_selection.py` 实测输出：**选对 20/20**（用例分布：search_history 7 / calc 5 / read_note 6 / 无需工具 2；
其中 C05、C18 是「故意触发工具报错」的用例，验证错误能回填并被模型复述）。
逐条明细见 out/eval_selection.md。
