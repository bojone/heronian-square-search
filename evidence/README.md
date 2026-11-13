# 证据目录

本目录保存原始搜索的关键结果和运行记录，不把内部候选当作数学结论。机器可读的环境与时间摘要见 [`hardware.json`](hardware.json)，正式文件及文档的当前哈希见项目根目录的 [`SHA256SUMS`](../SHA256SUMS)。

## 最终覆盖与计数

- `final-coverage.json`：2026-11-10 00:45:06 UTC 的原始覆盖审计报告。`complete_intervals` 为 `[[1,10000000]]`，根边覆盖率和逻辑边对覆盖率均为 `1.0`。
- `main-state.txt`：主 CPU 的最后检查点，`resume=10000001`，`pairs=38895816330946`，`candidates=1501947057268700`。
- 主状态从 `begin=1180045` 接续，且调度器会跳过其他 worker 已完成的区间。因此这里的 `pairs` 和 `candidates` 是主进程的工程计数，**不是整个搜索空间的全局总数**。全局完成性看合并区间，不看单个状态文件。

## 结果验证

`final-results.txt` 只有：

```text
1853 4380 4427 32918611718880
11789 68104 68595 284239560530875680
```

`nonempty-results/` 保存去重收集的 17 个非空结果文件，共 34 行。不同前瞻 worker 可能重复输出同一个已知解；逐文件验证并去重后只有上述两组根边。运行：

```bash
python3 scripts/verify_all_results.py --root evidence --known-only
```

预期汇总：

```text
ALL NONEMPTY RESULT FILES VERIFIED files=17 lines=34 unique=[(1853, 4380, 4427), (11789, 68104, 68595)]
```

项目根目录的 `full100k-results.txt` 是给前瞻 worker 初始化结果文件所用的已知解种子，不是额外搜索结果。

## 日志、基准与快照清单

- `logs/main.log`、`logs/main-follow.log`：主 worker 与接续器记录，含最终完成时间和 worker 秒数。
- `logs/gpu-queue.log`、`logs/gpu-rebalance.log`、`logs/cpu-follow-stages.log`：GPU 队列、再平衡和 CPU 前瞻阶段记录。
- `logs/coverage.log`：覆盖增长与最终区间；`logs/deadline-guard.log`：截止保护确认。
- `logs/checkpoint-backup.log`：原子快照的文件数、字节数和写入后校验结果。
- `benchmarks/`：CPU/GPU 优化、恢复部署和重权重实验的原始 JSON。局部秒数受区间和同机负载影响。
- `final-snapshot-manifest.json`：原始快照 `snapshots/20261110T004658.514678Z` 的 1975 个文件、总计 40947002 字节及逐文件 SHA-256。清单中的文件名属于**原始扁平工作目录**，不是当前开源目录的相对路径。

## 未发布的历史快照与可复核范围

原工作目录约 4 GB 的历史 `snapshots/` 实体没有复制到本项目。它们包含大量重复状态、日志和源码；本目录只保留最终清单及上述关键证据。`build/` 的二进制和回归输出也可以重新生成，不作为发布证据。

因此需注意：**当前目录不包含原始覆盖报告引用的全部中间状态和逐 GPU 区间日志，不能只在 `evidence/` 上重新执行完整覆盖合并。** 清单用于核对原快照中记录了哪些文件及其哈希；保留下来的最终状态和结果是另一组可独立检查的证据。若要重新建立完整覆盖链，请按 `docs/REPRODUCE.md` 从源码运行新区间或完整搜索。

`scripts/coverage_audit.py` 针对新运行的工作目录生成根目录 `coverage-latest.json`。新目录没有原始状态时，它报告空覆盖是正常行为，并不推翻冻结的 `final-coverage.json`。请勿把历史报告复制成新运行报告，或用新运行的部分覆盖改写历史报告。

## 校验当前项目文件

在项目根目录执行：

```bash
sha256sum -c SHA256SUMS
```

清单包含当前项目中的正式源码、脚本、文档和证据文件，不包含 `build/`、`snapshots/`、`.git/`、Python 缓存及清单自身。历史正式二进制的 SHA-256 单独记录在 `docs/RESULTS.md` 和 `hardware.json`；重新编译的二进制不保证逐字相同。
