# SAMPLE_REPORT · 一次真实检索报告（脱敏）

> 由 `python demo.py` 实际生成（out/eval_report.md 同步留存）。
> 语料为 12 篇合成示例文档，无任何真实隐私。运行环境：Windows + Python 3.11.7，2026-10-11。
> 本报告存于项目根目录：out/ 被 .gitignore 忽略，证据文件需被 git 追踪。

## 运行结果

- 建索引第一次：inserted=12 updated=0 empty=0
- 建索引第二次（幂等验证）：inserted=**0** skipped=12
- 召回（期望文档在 Top3）：**20/20**　Top1：**20/20**
- 单次查询耗时：平均 1.4~2.1 ms　最大 2.0~3.8 ms（2026-10-11 同机三次独立实测区间，随负载波动；单次值见 out/eval_report.md）

## 真实命中样例（SPEC 验收 1 要求的一条）

查询：`测试`　→　Top1：

```
doc_id:   d05_testing   source: d05_testing.txt   score: 2.8342
fragment: 单元 元测 [测试] 试要 要覆 覆盖 盖异 异常 常路 路径 径和 和空…
content:  单元测试要覆盖异常路径和空数据，不能只测正常流程。这个测试很好：先写失败用例，再写实现让它通过。
offset:   2（「测试」在原文第 2 个字符处）
```

`[]` 即命中位置。搜「测试」命中「这个测试很好」——默认分词器做不到，bigram 分词做到了。

## 全部 20 条查询

| 查询 | 期望文档 | Top3 实际 | Top1 | Top3 |
|---|---|---|---|---|
| Q01 怎么防止数据库丢数据 | d01_backup | d01_backup > d05_testing > d12_interview | ✔ | ✔ |
| Q02 测试 | d05_testing | d05_testing | ✔ | ✔ |
| Q03 中文没有空格怎么分词 | d02_bigram | d02_bigram > d12_interview > d09_scorer | ✔ | ✔ |
| Q04 全文索引引擎 | d03_fts5 | d03_fts5 > d11_rank > d02_bigram | ✔ | ✔ |
| Q05 搜索结果怎么排序 | d04_bm25 | d04_bm25 > d03_fts5 > d12_interview | ✔ | ✔ |
| Q06 怎么写单元测试 | d05_testing | d05_testing > d12_interview | ✔ | ✔ |
| Q07 怎么防止读文件越界 | d06_path | d06_path > d12_interview > d01_backup | ✔ | ✔ |
| Q08 路径越界要怎么办 | d06_path | d06_path > d12_interview > d05_testing | ✔ | ✔ |
| Q09 错误归一化的顺序 | d07_normalize | d07_normalize | ✔ | ✔ |
| Q10 编号前缀要先剥掉 | d07_normalize | d07_normalize | ✔ | ✔ |
| Q11 评测用例怎么设计 | d08_cases | d08_cases > d12_interview > d05_testing | ✔ | ✔ |
| Q12 对抗用例是干什么的 | d08_cases | d08_cases > d05_testing | ✔ | ✔ |
| Q13 打分为什么不能用主观 | d09_scorer | d09_scorer > d01_backup > d08_cases | ✔ | ✔ |
| Q14 客观断言怎么写 | d09_scorer | d09_scorer > d12_interview | ✔ | ✔ |
| Q15 为什么不用第三方库 | d10_stdlib | d10_stdlib > d09_scorer | ✔ | ✔ |
| Q16 标准库都有什么 | d10_stdlib | d10_stdlib | ✔ | ✔ |
| Q17 索引太大怎么办 | d11_rank | d11_rank > d12_interview > d03_fts5 | ✔ | ✔ |
| Q18 检索怎么优化 | d11_rank | d11_rank > d12_interview | ✔ | ✔ |
| Q19 面试时讲哪些重点 | d12_interview | d12_interview | ✔ | ✔ |
| Q20 虚拟表怎么建 | d03_fts5 | d03_fts5 > d12_interview | ✔ | ✔ |

## 标注口径（诚实说明）

- 语料是合成文档，期望答案按构造标注（每条查询对应写语料时指定的文档）；
  标注后查询措辞与文档措辞刻意不同（如「怎么防止数据库丢数据」→ 备份文），不是原句匹配
- 首轮实测 Top1 为 18/20：Q17/Q18 的关键词（「索引太大」「检索优化」）未在 d11 文中出现，
  被同主题文档压到 Top2；补全 d11 措辞后复测 20/20。这一轮校准只动了语料文字，
  **没有动评分与检索代码**
