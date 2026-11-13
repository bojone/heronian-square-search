# 双纤维椭圆辅助搜索

本目录记录构造性路线的研究实验。它**不参与**根边 `1..10000000` 的完整覆盖证明；正式穷举使用 `src/` 中的 CPU v18 和 GPU v42。

## 方法

从两组已知解分别得到曲线上的已知点 $`P`$，并在同一曲线上选取另一个点 $`Q`$。对整数系数 $`n,m`$，枚举 $`nP+mQ`$ 及其与二阶挠点 $`(0,0)`$ 的和，构成两个纤维、每个纤维两个挠点陪集。代码从有理点计算候选比值和 $`r`$，只有相应有理数为平方时才还原整数根边，最后调用本目录的 `verify.py` 做任意精度整数检查。

- $`(n,m)`$ 与 $`(-n,-m)`$ 给出相反点，横坐标不变，因此只枚举一对代表。
- `ELLIPTIC_PREVIOUS_BOUND=B` 时跳过已检查的中心区域，只计算增量壳层。
- 对若干有效模素数计算 Legendre 符号。非平方剩余可以安全排除，剩余者仍需精确有理数和整数验证；模过滤不是接受依据。
- `elliptic_fast_filter.py` 通过 `ctypes` 调用 C++ 位掩码过滤器，两个陪集共享模幂计算。
- 状态保存当前纤维和下一个系数位置；`-hits.jsonl` 记录平方条件命中及其验证状态，不能把所有命中都视为本原海伦三角形。

这里的“200000 阶”是椭圆点倍乘系数和增量壳层的界，**不是**根边只搜索到 200000，也不能代替正式根边穷举。

## 排除条件与未覆盖范围

“被过滤”“因重复而跳过”和“根本没有搜索”是不同概念，不能混为一谈。

### 搜索空间之外的内容

- 实验只从两组已知解分别建立两个纤维模型。每个纤维枚举 $`nP+mQ`$ 以及 $`nP+mQ+(0,0)`$，即两个挠点陪集。这里没有证明 $`P,Q`$ 生成整条曲线的全部有理点，也没有遍历其他曲线、生成元组合或其他挠点陪集。
- 在界 $`B`$ 内枚举 $`-B\le n,m\le B`$。本次最大 $`B=200000`$，界外组合没有计算。这个限制作用于椭圆点的倍乘系数，不限制由点还原出的三角形根边大小。
- 增量运行设置 `ELLIPTIC_PREVIOUS_BOUND=B0` 时，中心区域 $`\max(\lvert n\rvert,\lvert m\rvert)\le B_0`$ 被认为已经由前一阶段搜索而跳过。它不是数学上的无解排除；若前序阶段不完整，不能把后续壳层当作完整结果。

### 不改变目标解集合的约减与模过滤

- 对称性只删除重复代表：$`(n,m)`$ 与 $`(-n,-m)`$ 对应相反点，横坐标不变，所用的 $`r`$ 和 $`q^2`$ 也不变。代码要求 $`n\ge0`$，并在 $`n=0`$ 时要求 $`m\ge0`$。
- 对选定的模素数计算 Legendre 符号。只有参数 $`r`$ 在有效模模型中是非二次剩余时才排除，因为有理平方在任何良好约化下都不能是非二次剩余。二次剩余和零都保留，通过模过滤不等于证明有理平方。
- 模分母不可逆、奇异约化、准备倍点表时遇到无穷远点，或模点加法无法计算时，会放弃相应的**模模型**，而不是删除候选。$`x=0`$、$`h^2=0`$ 等无法应用模公式的情况也保留；没有有效模型时 `passes_modular()` 直接返回真。因此，坏约化只会削弱过滤，不应造成目标解丢失。
- 以精确的 $`(q^2,r)`$ 对识别已经见过的相似类，重复类只验证一次。这里删除的是重复表示，不是按数值大小截断解。

相关实现为 `elliptic_vector_search.py:139-185` 的模型准备和标量必要条件、`elliptic_vector_search.py:350-381` 的对称代表与增量壳层，以及 `elliptic_fast_filter.py:73-80` 和 `elliptic_filter.cpp` 的位掩码过滤。

### 精确检查时的跳过内容

- 当前点为无穷远点或 $`x=0`$ 时，后续参数式无定义，跳过该表示。
- $`r`$ 必须为正的有理平方，因为目标中有 $`r=c^2/u^2`$。$`r\le0`$ 或最简分数的分子、分母不是完全平方数时，跳过该候选。
- 对幸存者还原整数根边并除以 gcd 后，仍调用 `verify.py` 检查非退化性、整数面积和本原性。未通过者可以写入 `-hits.jsonl` 作为内部记录，但不会作为新解输出。
- 与当前纤维起点的已知解完全相同者也不计作新解。因此，“无新结果”不等于“没有模过滤幸存者”，也不等于“没有任何平方条件命中”。

以上精确检查见 `elliptic_vector_search.py:51-67`、`elliptic_vector_search.py:387-412`。

## 已完成范围与验证

`elliptic-200000-summary.json` 记录：从 190000 阶增量搜索至 200000 阶，两个纤维状态均为完成，`hits_files=[]`、`new_results=[]`，完成核验时间为 2026-11-07 08:37:00 UTC。该最终壳层无命中，不代表所有中间阶段均无内部平方条件记录；各阶段的 `*-summary.json` 是相应历史记录。

已保存的一致性检查包括：

- `elliptic-symmetry-validation.json`：对称性约简、1000 阶完整结果、两组已知解保留及中断恢复；
- `elliptic-small-prime-validation.json`：较小素数候选的验证记录，状态为未部署；
- `elliptic-medium-prime-validation.json`：最终中等素数集合的标量/向量一致性、已知解保留及部署记录；
- `elliptic-fast-filter-benchmark.json`、`elliptic-fast-filter-deployment.json`：C++ 过滤器的性能与生产部署检查；
- 60000 至 200000 阶的启动、恢复、预检和总结 JSON。

这些记录是原始实验结果，不是在当前开源目录重新运行全部阶段所得。为适配开源目录，新增了同内容的本目录 `verify.py`，并调整了阶段接续器的备份和监控日志路径；核心枚举算法未变。JSON 内的源码与共享库哈希属于原运行环境，路径适配或重新编译后不要求逐字相同。

## 依赖与构建

除 Python 标准库外，本实验使用 **NumPy**。正式搜索不需要 NumPy。可以自行在虚拟环境中安装：

```bash
python3 -m pip install numpy
```

C++ 过滤器共享库不随项目发布，需要在本目录构建：

```bash
cd experiments/elliptic
g++ -O3 -std=c++17 -shared -fPIC elliptic_filter.cpp -o elliptic_filter.so
```

`elliptic_filter_single.cpp` 与 `elliptic_filter_pair.cpp` 保存较早实现；最终 `elliptic_fast_filter.py` 默认加载的是 `elliptic_filter.so`。

## 运行

小规模双纤维运行（会实际计算，不是空检查）：

```bash
cd experiments/elliptic
ELLIPTIC_BOUND=1000 ELLIPTIC_PREVIOUS_BOUND=0 \
  python3 elliptic_high_follow.py 0 0
```

`elliptic_high_follow.py` 启动两个 `elliptic_vector_search.py BOUND` worker。使用 `ELLIPTIC_PREFIX` 指定独立状态前缀，避免不同界或并行实验共享检查点。下面的命令只运行第一纤维，适合单独调试：

```bash
ELLIPTIC_FIBER_STOP=1 ELLIPTIC_PREFIX=elliptic-test-b1000 \
  python3 elliptic_vector_search.py 1000
```

`elliptic_stage_chain.py COMPLETED_BOUND NEXT_BOUND` 是原生产的阶段接续器，不是从零开始的一键复现入口。它要求前一阶段的完整状态、日志和启动记录存在，会调用项目级 `scripts/checkpoint_backup.py`，并检查完成条件后才启动下一阶段。若启用了根目录结果监控，可用 `python3 scripts/result_monitor.py > result-monitor.log 2>&1` 保存其日志；日志不存在或为空时，阶段链记录 `result_monitor_empty=true`。首次复现请使用上面的 `elliptic_high_follow.py`，不要直接运行阶段链。实验中的早期 `*_before_*.py`、其他搜索脚本用于保留演进和比对，不是当前首选入口。

新增输出写在当前实验目录，`.so`、Python 缓存和状态文件不纳入发布。主搜索的结果监控也会检查本目录的 `elliptic-new-results.txt`。
