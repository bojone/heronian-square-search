# 平方边长本原海伦三角形：CPU/GPU 穷举搜索

**中文 | [English](README.en.md)**

**整个项目完全由 Kimi K3.1 Pro [thinkg: max] + Kimi-Code 自主完成。**

本项目寻找三边都是完全平方数、面积为整数且三边互素的本原海伦三角形，记录相应的算法、程序实现、搜索优化和独立验证。公开资料只作为问题背景与参考，见[参考资料](docs/REFERENCES.md)。

若根边为 $`l,m,n`$，实际三边为 $`l^2,m^2,n^2`$。本次完成根边 **1–10,000,000** 的穷举，即平方边长不超过 $`10^{14}`$ 的范围。

## 结果

**在该完整范围内没有发现第三组解。** 输出中只有原先已知的两组本原解：

| 根边 $`(l,m,n)`$ | 实际三边 $`(l^2,m^2,n^2)`$ | 整数面积 |
|---|---|---:|
| `(1853, 4380, 4427)` | `(3433609, 19184400, 19598329)` | `32918611718880` |
| `(11789, 68104, 68595)` | `(138980521, 4638154816, 4705274025)` | `284239560530875680` |

两组解都通过了非退化性、本原性、海伦公式和面积的任意精度整数复核。17 个非空结果文件共 34 行，去重后仍只有这两组解。

这不是对更大范围或一般情形的“不存在性”证明。结论仅适用于本次经过检查点审计的完整搜索空间，详见[最终结果与运行环境](docs/RESULTS.md)。

## 核心方法

直接枚举 $`l,m,n`$ 代价很高。定义

$$D=l^4+m^4-n^4.$$

由海伦公式可得

$$(4A)^2+D^2=(2l^2m^2)^2.$$

因此只需枚举 $`l,m`$，利用 $`2l^2m^2`$ 的高斯整数分解生成所有可能的勾股表示，再检查

$$n^4=l^4+m^4-D$$

是否为四次方，**不需要枚举 $`n`$**。正式实现还包含：

- $`p\equiv3\pmod4`$ 惰性素数的排除条件；
- 高斯分解缓存和模数过滤；
- CPU 128/256 位精确整数复核；
- GPU 候选生成与 Python 独立精确验证；
- 连续检查点、恢复、覆盖合并和逐文件 SHA-256 快照。

完整推导见[算法与正确性](docs/ALGORITHM.md)，英文版见 [Algorithm and correctness](docs/ALGORITHM.en.md)。

## 设备与时间

- GPU：8 张 NVIDIA GPU。
- CUDA：生产环境使用 CUDA 12.9，编译器路径为 `/usr/local/cuda/bin/nvcc`。
- CPU：共 288 线程；主搜索使用 272 个工作线程，前瞻任务使用 16 个线程。
- 主搜索完成时间：2026-11-10 00:11:36 UTC。
- 从项目起始到完成的日历跨度：`468764` 秒，约 **130.21 小时**。
- 目标工具报告的有效工作时间：**118 小时 36 分钟**。
- v18 主 worker：`299820` 秒，约 **83.28 小时**。

这些是本机历史记录，不是对其他硬件的性能承诺。“日历跨度”“有效工作时间”和单个 worker 时间是不同口径，详见[结果与运行环境](docs/RESULTS.md)及[机器可读记录](evidence/hardware.json)。

## 目录

```text
heronian-square-search/
├── README.md                 # 默认中文总览
├── README.en.md              # English overview
├── CONTRIBUTING.md           # 贡献与证据规范
├── LICENSE                   # MIT 许可证
├── Makefile                  # 正式构建与回归入口
├── SHA256SUMS                # 发布文件校验清单
├── src/                      # 正式 CPU v18 与 GPU v42
├── scripts/                  # 验证、调度、恢复、备份与覆盖审计
├── docs/                     # 算法、复现、结果、优化和参考资料
├── evidence/                 # 最终覆盖、结果、日志、基准和快照清单
└── experiments/
    ├── elliptic/             # 双纤维椭圆辅助搜索
    ├── heavy/                # 高斯权重较大根边的专项实验
    └── legacy/               # 历史版本，不是正式入口
```

历史实验用于记录研究过程，**不得用 `experiments/legacy/` 中的版本替代正式实现**。正式脚本以项目根目录为工作目录，不依赖原始搜索目录的绝对路径。

## 只审计已有结果（不需要 GPU）

需要 Python 3。正式搜索和结果验证只使用 Python 标准库；NumPy 仅用于椭圆实验。

```bash
# 独立复算两组已知解
python3 scripts/verify.py

# 验证全部已保存非空结果，并要求去重后只有两组已知解
python3 scripts/verify_all_results.py --root evidence --known-only

# 检查发布文件是否在传输中损坏
sha256sum -c SHA256SUMS
```

结果验证的预期汇总为：

```text
ALL NONEMPTY RESULT FILES VERIFIED files=17 lines=34 unique=[(1853, 4380, 4427), (11789, 68104, 68595)]
```

这些命令会重新计算保存结果的海伦公式和面积，但**不会在几分钟内从零重扫整个搜索空间**。当前精简发布不包含原始覆盖报告引用的全部中间状态和逐 GPU 区间日志；冻结报告、最终清单和重新生成证据的方法见[证据目录](evidence/README.md)。

## 构建与轻量自检

依赖如下：

- 支持 C++17 的编译器；正式 CPU 运行使用 G++ 11.4。
- Python 3.12；正式脚本只使用标准库。
- 可选 NVIDIA CUDA 工具包；本次使用 CUDA 12.9。
- 每个正式 GPU worker 约需 9 GiB 可用显存；本次使用 8 张 NVIDIA GPU。

```bash
# 若 nvcc 不在 PATH，同时构建 CPU/GPU 并执行回归
make NVCC=/usr/local/cuda/bin/nvcc test

# 没有 GPU 时，只构建并运行 CPU 回归
make test-cpu

# 只编译，不启动搜索
make NVCC=/usr/local/cuda/bin/nvcc all
```

回归检查：

- 根边 1–5000 的完整小区间，候选数为 `151842556`，找到第一组已知解；
- 根边 11789 的单点区间，候选数为 `1194756`，找到第二组已知解；
- CPU 逻辑边对数分别为 `12502500` 和 `58212`；
- `evidence/` 中所有非空结果仍只有两组已知解。

每个二进制独立写出状态和结果，避免 GPU 复用 CPU 命中。测试输出保存在 `build/smoke-*`，CI 配置在 `.github/workflows/ci.yml`。

## 单进程复现

CPU 参数为 `LIMIT FIRST_L LAST_L THREADS STATE_FILE [RESULTS_FILE]`：

```bash
make cpu
./search 5000 1 5000 2 small-state.txt small-results.txt
python3 scripts/verify.py small-results.txt
```

GPU 参数为 `LIMIT FIRST_L LAST_L RESULTS_FILE [GPU [STATE_FILE]]`：

```bash
make NVCC=/usr/local/cuda/bin/nvcc gpu
./gpu_search_v42 10000000 7500000 7500511 gpu-results.txt 0 gpu-state.txt
python3 scripts/verify.py gpu-results.txt
```

GPU 每批处理最多 512 个根边位置。状态文件、`PROGRESS` 日志和结果文件应一并保留。跨机器部署时，应按目标架构调整 `GPU_ARCH`，不能照搬原生产吞吐。

## 从零重跑与完整覆盖

完整任务涉及数天计算、多个 CPU/GPU worker 和并发调度。请先阅读[复现指南](docs/REPRODUCE.md)或 [Reproduction guide](docs/REPRODUCE.en.md)，不要将“编译成功”或“自检通过”当作全量复现。

单进程完整 CPU 入口为：

```bash
./search 10000000 1 10000000 272 main-state.txt main-results.txt
```

多进程调度器应在独立终端中分别运行，同一工作目录中每类只能有一个实例：

```bash
export MAIN_FOLLOW_DEADLINE="$(python3 -c 'import datetime; print(datetime.datetime.now(datetime.timezone.utc).timestamp()+604800)')"
python3 scripts/main_follow.py 0
python3 scripts/gpu_follow.py b
python3 scripts/gpu_rebalance.py
python3 scripts/cpu_follow.py
python3 scripts/result_monitor.py
python3 scripts/checkpoint_backup.py
```

这里的硬截止示例是一周，不是永久任务。调度器围绕本次一千万根边目标编写，改变搜索范围时应同时检查阶段配置和状态文件，不要混用新旧检查点。

按需执行覆盖审计：

```bash
python3 scripts/coverage_audit.py
python3 scripts/verify_all_results.py --known-only
```

只有新运行生成的 `coverage-latest.json` 满足 `complete_intervals == [[1,10000000]]`，才能声称整个目标范围完成。部分 `resume` 或部分百分比不能推出不存在第三组解，也不能用空目录的审计覆盖历史证据。

## 最终证据

- [完整覆盖报告](evidence/final-coverage.json)：`complete_intervals = [[1,10000000]]`，根边及逻辑边对覆盖率均为 1。
- [主搜索最终状态](evidence/main-state.txt)：`resume = 10000001`。
- [最终结果](evidence/final-results.txt)：两行已知解。
- [非空结果文件](evidence/nonempty-results/)：17 个文件，共 34 行。
- [最终快照清单](evidence/final-snapshot-manifest.json)：原始最终快照中 1975 个文件的大小与 SHA-256。
- [运行日志](evidence/logs/)：主搜索、CPU/GPU 队列、再平衡、覆盖和备份日志。

本项目不包含约 4 GB 的历史快照实体，避免仓库膨胀；保留最终清单、关键证据和可重新生成它们的源码。说明见[证据目录](evidence/README.md)。

## 源码范围与许可

正式 CPU/GPU 源码的 SHA-256 与原搜索版本一致。文档记录的历史二进制哈希只用于对应当时日志，不同编译器、驱动和架构生成不同哈希并不表示数学结果不同。

文档导航：[算法与正确性](docs/ALGORITHM.md) · [复现指南](docs/REPRODUCE.md) · [优化记录](docs/OPTIMIZATION.md) · [最终结果](docs/RESULTS.md) · [参考资料](docs/REFERENCES.md) · [贡献指南](CONTRIBUTING.md)。

采用 [MIT License](LICENSE)。原始状态、日志和结果证据也按同一许可证提供，便于复核和继续研究。
