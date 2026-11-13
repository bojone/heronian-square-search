# 复现指南

**中文 | [English](REPRODUCE.en.md)**

本文给出从源码构建、已知解回归、单区间搜索到完整调度与结果审计的步骤。所有命令均以项目根目录为工作目录。

## 1. 环境要求

正式运行只需要：

- 支持 C++17 的编译器；
- Python 3.12 标准库；
- 可选 CUDA 工具包及 NVIDIA GPU。

本次使用的具体环境：

```text
G++ 11.4
CUDA 12.9
Python 3.12
```

实验目录中的部分椭圆曲线脚本还使用 NumPy，但正式搜索和结果验证不依赖 NumPy。

## 2. 构建

构建 CPU 和 GPU 版本：

```bash
make NVCC=/usr/local/cuda/bin/nvcc all
```

仅构建 CPU：

```bash
make cpu
```

构建产物为：

```text
build/search
build/gpu_search_v42
search -> build/search
search_v13 -> search
gpu_search_v42 -> build/gpu_search_v42
```

可以覆盖编译参数：

```bash
make CXX=g++ CXXFLAGS='-O3 -std=c++17 -march=native' cpu
make NVCC=/usr/local/cuda/bin/nvcc GPU_ARCH=native gpu
```

`native` 让 nvcc 针对当前 GPU 编译。跨机器部署时，请按目标架构调整 `GPU_ARCH`。

## 3. 已知解回归

运行完整回归：

```bash
make NVCC=/usr/local/cuda/bin/nvcc test
```

仅运行 CPU 回归：

```bash
make test-cpu
```

回归脚本 `scripts/smoke_test.py` 检查两个案例：

| 案例 | 范围 | 候选数 | 预期结果 |
|---|---|---:|---|
| `full5000` | `limit=5000, l=1..5000` | `151842556` | `1853 4380 4427 32918611718880` |
| `known2` | `limit=70000, l=11789` | `1194756` | `11789 68104 68595 284239560530875680` |

CPU 还检查逻辑根边对数，分别为 `12502500` 和 `58212`。每个二进制都有独立的状态和结果文件，避免相互复用命中。

再运行最终证据核验：

```bash
python3 scripts/verify_all_results.py --root evidence --known-only
```

预期末尾为：

```text
ALL NONEMPTY RESULT FILES VERIFIED files=17 lines=34 unique=[(1853, 4380, 4427), (11789, 68104, 68595)]
```

## 4. 小区间搜索

CPU 参数：

```text
search LIMIT FIRST_L LAST_L THREADS STATE_FILE [RESULTS_FILE]
```

示例：

```bash
./search 5000 1 5000 2 small-state.txt small-results.txt
python3 scripts/verify.py small-results.txt
```

GPU 参数：

```text
gpu_search_v42 LIMIT FIRST_L LAST_L RESULTS_FILE [GPU [STATE_FILE]]
```

示例：

```bash
./gpu_search_v42 10000000 7500000 7500511 gpu-results.txt 0 gpu-state.txt
python3 scripts/verify.py gpu-results.txt
```

GPU 日志中的每个 `PROGRESS resume` 必须前进 512，最后一批可以小于 512。

## 5. 根边 1–10000000 的完整 CPU 搜索

```bash
./search 10000000 1 10000000 272 main-state.txt main-results.txt
```

完成后应看到：

```text
resume 10000001
```

再用覆盖审计和结果验证：

```bash
python3 scripts/coverage_audit.py
python3 scripts/verify_all_results.py --known-only
```

`coverage-latest.json` 中应出现：

```json
"complete_intervals": [[1, 10000000]]
```

搜索可通过 `SIGTERM` 或 `SIGINT` 正常停止。进程会在安全点保存检查点，随后可用同一命令恢复。不要强制终止正在写状态的进程。

## 6. 多 GPU 与调度器

先设置硬截止对应的 Unix 时间戳：

```bash
export MAIN_FOLLOW_DEADLINE="$(python3 -c 'import datetime; print(datetime.datetime.now(datetime.timezone.utc).timestamp()+604800)')"
```

各调度器应在独立终端中启动，且**同一工作目录中每类只能有一个实例**：

```bash
python3 scripts/main_follow.py 0
python3 scripts/gpu_follow.py b
python3 scripts/gpu_rebalance.py
python3 scripts/cpu_follow.py
python3 scripts/result_monitor.py
python3 scripts/checkpoint_backup.py
```

`main_follow.py 0` 表示从已有主状态启动或接续；没有状态时会从根边 1 开始。`gpu_follow.py b` 是全新调度示例，不表示重放本项目的全部历史。

GPU 数量可用环境变量控制：

```bash
GPU_IDS=0,1,2,3 python3 scripts/gpu_follow.py b
```

若系统 CUDA 驱动位于非标准位置，请设置：

```bash
export LD_LIBRARY_PATH="/usr/local/nvidia/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
```

原生产环境另有 `cuda-driver/` 兼容目录；该目录不是开源复现的必要条件。

## 7. 截止保护

`search_deadline_guard.py` 与主接续器共用 `MAIN_FOLLOW_DEADLINE`：

```bash
python3 scripts/search_deadline_guard.py
```

它会分阶段停止辅助任务、直接 worker 和主搜索。找到经过独立验证的新解，或覆盖达到 `[[1,10000000]]` 时，保护器会提前退出而不发送停止信号。

`cpu_follow.py` 和 GPU 调度器也会根据覆盖审计跳过已完成区间，避免重复工作。

## 8. 原子备份

立即生成一个校验快照：

```bash
BACKUP_ONCE=1 BACKUP_INTERVAL=3600 python3 scripts/checkpoint_backup.py
```

持续每小时备份：

```bash
BACKUP_INTERVAL=3600 python3 scripts/checkpoint_backup.py
```

快照保存在 `snapshots/<UTC时间>/`，其中：

- `files/` 保存状态、日志、结果与源码；
- `manifest.json` 记录每个文件的字节数和 SHA-256；
- 先写临时目录，再原子重命名；
- 写入后重新读取并逐文件校验。

开源项目不包含历史 `snapshots/` 实体。最终原始快照的清单见 `evidence/final-snapshot-manifest.json`。

## 9. 状态和结果格式

CPU 状态示例：

```text
version 1
limit 10000000
begin 1180045
end 10000000
resume 10000001
pairs 38895816330946
candidates 1501947057268700
```

GPU 状态没有 `pairs` 字段，但必须有连续的 `PROGRESS resume` 日志。

结果文件每行：

```text
l m n area
```

示例：

```text
1853 4380 4427 32918611718880
11789 68104 68595 284239560530875680
```

候选计数在每次进程启动时重新开始，不能盲目跨日志相加，也不能跨过滤版本直接比较。

## 10. 常见问题

### `nvcc: command not found`

使用：

```bash
make NVCC=/usr/local/cuda/bin/nvcc gpu
```

或把 CUDA 的 `bin` 加入 `PATH`。

### `Permission denied`（脚本）

项目脚本带有 shebang。可以直接运行：

```bash
python3 scripts/verify.py
```

或赋予执行位：

```bash
chmod +x scripts/*.py
```

### 覆盖比例没有增长

先检查状态与日志是否处于长批次中。CPU 的 `pairs` 或 `candidates` 增长、GPU 的下一条 `PROGRESS` 出现都说明仍在工作，不应仅因 `resume` 暂时不变而重启。

### 结果验证失败

保留对应状态、日志和结果文件，执行：

```bash
python3 scripts/verify.py 结果文件路径
```

不要把未通过精确验证的内部候选当成最终解。

## 11. 原始源码校验

原始正式源码 SHA-256：

```text
search_v18.cpp:
523ca758c71d7dd0cb3dd4c3f61f2d02f710aa1c2892aee8dfca294d0afffffc

gpu_search_v42.cu:
a4cfcccba18582c6526d56aaec3e7ad202f4d9bca029b6f944b70973388a27c6
```

正式生产二进制的历史哈希记录在 `evidence/benchmarks/gpu-opt-benchmark.json`。新编译的二进制哈希可能随工具链和架构参数变化，不要求与历史二进制逐字一致。
