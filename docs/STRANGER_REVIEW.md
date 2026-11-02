# 陌生人复验记录（35 号工单 · P2 ai-capability-kit）

> 复验日期：2026-11-02 · 复验人：技术线（Trae）
> 方法：**真 clone**（SSH，非同步工作区文件模拟），严格照 README 命令走。

## 结果

**一次走通，零卡点。** SSH 认证通、目录名正确、三条命令全部出真实结果，未配置任何 key。

## 复验原文（命令 + 目录名，判据要求）

```
PS C:\Users\Administrator\AppData\Local\Temp> git clone git@github.com:gangrenboqe/ai-capability-kit.git
Cloning into 'ai-capability-kit'...
clone 后目录名: ai-capability-kit        ← git 默认取仓名，与 README 的 `cd ai-capability-kit` 一致
README.md 存在: True
```

三条命令（照 README「三步跑起来」原文）：

```
cd agent-tool-loop && python demo.py      → 退出码 0，输出"演示运行记录 · ScriptedBackend · 3 轮 1.3ms"
cd local-retrieval && python demo.py      → 退出码 0，输出"召回 20/20，Top1 20/20；幂等验证 0/12"
cd prompt-eval && python run.py --compare → 退出码 0，输出四版对比表（13→23→18→25）+ 报告写入 out/compare.md
```

完整真实输出片段：[docs/agent-tool-loop_demo.txt](agent-tool-loop_demo.txt) ·
[docs/local-retrieval_demo.txt](local-retrieval_demo.txt) ·
[docs/prompt-eval_compare.txt](prompt-eval_compare.txt)（在开发源目录实跑时存档，与 clone 目录输出一致）。

## 说明

1. 本记录验证的 README 版本是**远端 HEAD（e16cb67）自带的「怎么跑」段**——与新版顶部「三步跑起来」的
   三条命令完全一致（本次改动只是把它提到顶部 + 补输出片段链接），因此 clone 复验对新版同样成立；
   新版推送后建议按同方法再核一次（命令不变，预期零卡点）。
2. 第一次复验尝试时 clone 目标带了自定义目录名（stranger_kit_35）——不算严格照 README，
   已补做默认目录名复验（见上），目录名 = ai-capability-kit。
3. 复验环境：Windows 11，Python 3.11，SSH 认证，未配置任何 API key，未联网调用模型（三个工具全离线）。
