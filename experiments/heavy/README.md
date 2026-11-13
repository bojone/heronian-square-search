# 重权重根边专项实验

“重权重”指根边的分裂素因子给出特别多高斯分支，单个根边因此在 CPU 上成本较高。本目录的 GPU v35/v36 增加最小权重筛选，尝试将这类根边交由 GPU 处理。

本实验只补充经过逐根验收的覆盖，不替代正式 CPU/GPU 搜索，也不意味着高权重区间之外可以跳过。

## 权重与验证

`verify_heavy.py` 独立分解根边。对每个素因子 $`p\equiv1\pmod4`$，若指数为 $`e`$，权重乘以 $`4e+1`$；其余素因子不增加该权重。`.done` 文件必须包含 `limit` 和 `min_weight` 标头，以及完成前缀内所有达到阈值的根边，顺序严格递增且不得重复。

对生成的检查点运行：

```bash
cd experiments/heavy
python3 verify_heavy.py heavy-v36-w100-FIRST-LAST-state.txt
```

若存在对应结果文件，脚本会调用同目录的 `verify.py` 做精确海伦公式、非退化性、本原性和面积检查。仓库保留了验证源码和基准，但没有发布全部 `.done` 文件，所以上述命令应作用于自己生成的状态，而不是把基准 JSON 当作状态文件。

只有状态和 `.done` 均有效时，`scripts/coverage_audit.py` 才把相应单根区间并入覆盖。没有时间戳或候选数但没有完成检查点的任务不计入覆盖。

## 构建与队列

从项目根目录构建实验 GPU v36：

```bash
/usr/local/cuda/bin/nvcc -O3 -std=c++17 -arch=native \
  experiments/heavy/gpu_search_v36.cu -o experiments/heavy/gpu_search_v36
```

`heavy_queue.py` 保留原生产调度约定：以 4096 个根边位置为一批，范围必须整批对齐；需显式给出未来 Unix 截止 `HEAVY_QUEUE_DEADLINE`。用法：

```bash
cd experiments/heavy
HEAVY_QUEUE_DEADLINE='未来Unix时间戳' \
  python3 heavy_queue.py FIRST LAST GPU EXISTING_PID MAX_BATCHES
```

首次启动用 `EXISTING_PID=0`。脚本检查同一 GPU 二进制是否已有其他重权重 worker，支持按 PID 接续正常退出的任务，并对完成状态调用独立验证。GPU 编号保留原环境的 `0..7` 约束；移植到其他机器时应同时检查设备数、CUDA 驱动路径和 `MIN_WEIGHT`，不要盲目复制生产参数。

## 实测结果与未扩大原因

原始 `heavy-benchmark.json` 记录：

| 实验 | 结果 |
|---|---|
| 根边 1116389，CPU 单线程 | 权重 125，443 秒，7175008050 候选，已验证 |
| 166 行 GPU v36 小批次 | 权重至少 100，3131 秒，1105278882993 候选，独立验证通过，无新解 |
| 根边 1447225，GPU v36 | 权重 1125，kernel 1468 秒，41795211005 候选，独立验证通过；主 CPU 已先完成此位置 |
| 680 行 GPU v35 大批次 | 7200 秒硬截止，无检查点，未独立验证，不计覆盖 |

这些 GPU 实验均与正常 GPU worker 共享设备。共享运行降低正常队列的总吞吐，因此没有扩大专项搜索；随后的 128 行批次在启动前取消。这里没有把未运行或未完成的部分写成“无命中”。
