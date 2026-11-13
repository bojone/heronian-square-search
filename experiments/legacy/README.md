# 历史实验归档

本目录保存搜索过程中的旧 CPU/GPU 版本、性能试验和早期椭圆过滤器，用于解释优化选择和复现历史对比，不是正式搜索入口。

正式版本只有：

- `src/search_v18.cpp`：CPU v18；
- `src/gpu_search_v42.cu`：GPU v42；
- `scripts/` 中的验证、调度、恢复和覆盖审计脚本。

## 为什么不能直接选用旧版

文件名中的 `search_v*`、`gpu_search_v*` 表示研究迭代，不代表更高编号一定更快或更安全。这里包含 `_debug`、`_check`、`_tune` 和 `_base` 等专门用途版本；部分程序可能依赖当时的目录布局、固定 GPU 参数、临时状态格式或尚未完成验证的过滤条件。

例如：

- v19 的额外模过滤在同负载比较中没有收益，未采用；
- v37、v41、v43 和 v45 的同负载测试不占优；
- v44 的 32 位缓存坐标范围不足，不能保留第二组已知解；
- `elliptic_filter_single.cpp` 与 `elliptic_filter_pair.cpp` 的早期路径已由 `experiments/elliptic/elliptic_filter.cpp` 的成对过滤实验取代。

详细取舍和测量见 `docs/OPTIMIZATION.md` 与 `evidence/benchmarks/`。

## 使用约定

如需编译历史版本，请使用独立构建目录、独立状态和结果文件，先运行两组已知解回归，再与正式版比较同一区间。不要覆盖正式检查点，不要把旧版输出未经 `scripts/verify.py` 验证就计入结果，也不要仅凭旧版 `resume` 推断覆盖完整。

本目录未提供逐一适配所有旧程序的构建目标；`make` 只构建正式版本。保留这些文件的目的，是让研究过程可检查，而不是鼓励从未验证版本继续大规模计算。
