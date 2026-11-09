# EVE-3 第 3 阶段：多种子消融与基线对比实验报告 (`experiments.md`)

> **实验铁律声明**：
> 1. 所有实验均基于第 2 阶段修复后的代码库运行，采用 **5 个独立随机种子 (`seeds = [42, 43, 44, 45, 46]`)**，汇报 **均值 ± 95% 置信区间**（Student-$t$ 分布，$df=4, t_{0.975}=2.776$）。
> 2. **严格按 Task Family 切分训练与留出评测集**（修复 H15 数据泄漏），System 3 结晶库仅在训练集任务族上自举学习，严禁接触留出任务族（`list_composition` 与 `str_composition`）。
> 3. **有 Oracle 主动查询模式（$B \in \{1, 2, 4, 8, 16\}$）** 与 **无 Oracle 被动模式（$B = 0, \text{oracle\_fn}=\text{None}$）** 严格分开统计与报告，绝不混用。
> 4. 对核心假设是否成立给出无美化结论：凡实验表明无显著差异（如默认环境下 LLM 贡献 vs 纯符号/启发式枚举），均如实报告。

---

## 1. 实验设置与扩充基准集说明

### 1.1 运行环境与硬件
- **硬件**：Apple M1 Max (10-core CPU, 64 GB Unified Memory), macOS 26.3.1 (`arm64`)
- **软件栈**：Python `3.14.8`, `z3-solver 4.16.0`, `pytest 9.2.0`, `mlx-lm` 未安装（测试默认 CPU/SMT 路径）
- **复现实验脚本**：`/Users/prognosticatex/.gemini/antigravity/brain/b1d1b2d0-c8fa-469b-bdb9-515766625a95/scratch/run_phase3_experiments.py` 及仓库内 `experiments/run_library_ablation.py`

### 1.2 基准任务集扩充（`benchmarks/expanded_suite_v3.json`）
原仓库 `benchmarks/families/` 仅有 5 个列表任务族共 13 个任务（训练集 10 个，留出集 3 个），样本量不足以支撑高置信度统计检验与跨模态迁移验证。我们在第 3 阶段扩充了 **FlashFill 风格字符串变换原语**（`str_strip`, `str_upper`, `str_lower`, `str_reverse`, `str_prefix3`, `str_suffix3`, `str_digits`, `str_alpha`, `str_no_spaces`, `str_bracket`）及 3 个新字符串任务族，构建了 **8 个任务族、共 36 个任务** 的 `benchmarks/expanded_suite_v3.json`：

| 任务族 (`task_family`) | 模态 | 切分角色 (`split`) | 任务数 | 典型程序结构示例 |
| :--- | :--- | :--- | :---: | :--- |
| `list_mapping` | 整数列表 (`List[int]`) | 训练集 (`train`) | 5 | `(map (lambda (a) (+ a 1)) x)` |
| `list_filtering` | 整数列表 (`List[int]`) | 训练集 (`train`) | 5 | `(filter (lambda (a) (> a 0)) x)` |
| `list_reduction` | 整数列表 (`List[int]`) | 训练集 (`train`) | 3 | `(sum x)`, `(len x)` |
| `list_structural` | 整数列表 (`List[int]`) | 训练集 (`train`) | 3 | `(reverse x)`, `(sort x)` |
| `str_cleaning` | 字符串 (`str`) | 训练集 (`train`) | 4 | `(str_upper (str_strip x))` |
| `str_extraction` | 字符串 (`str`) | 训练集 (`train`) | 4 | `(str_digits x)`, `(str_prefix3 (str_strip x))` |
| **`list_composition`** | 整数列表 (`List[int]`) | **严格留出评测集 (`held_out`)** | **6** | `(reverse (map (lambda (a) (+ a 1)) x))`, `(sum (filter (lambda (a) (> a 0)) x))` |
| **`str_composition`** | 字符串 (`str`) | **严格留出评测集 (`held_out`)** | **6** | `(str_bracket (str_upper (str_strip x)))`, `(str_reverse (str_digits x))` |
| **合计** | **双模态 (List + String)** | **24 训练 / 12 严格留出** | **36** | **零家族重叠（Zero Family Leakage）** |

- **故意欠定（Ambiguous Visible Examples）设计**：每个任务仅提供 2 个可见样例（`visible_examples`），使其在初始候选池中存在多个语义不等价但均满足可见样例的竞争假设（Version Space 大小 $2 \sim 16$），并在 3 个留出测试点（`hidden_tests`）上做最终 ground-truth 检验（仅当 `converged=True` 且 `held_out_accuracy == 1.0` 时计为成功）。

### 1.3 七种对比配置（Regimes A–G）
所有配置均在同一 `oracle_budget` $B$ 下评测：
- **Regime A（Full System）**：完整系统（System 1 混合提议 + System 2 语义等价类合并与闭式 IG 探针选择 + System 3 基于训练集自举的价值加权结晶库）。
- **Regime B（Random Probe）**：同预算随机探针基线（System 1 与 System 3 同 A，但 System 2 从候选探针池中均匀随机采样探针，不计算 IG）。
- **Regime C（Z3 Distinguishing Input Only, No IG）**：仅使用 Z3 合成的第一个区分输入（不补充结构化种子探针池，也不做贝叶斯 IG 排序）。
- **Regime D（No Crystallization）**：关闭 System 3 知识结晶（空库 `KnowledgeLibrary=None`），评测跨任务族正向迁移（Forward Transfer）的真实贡献。
- **Regime E（No LLM / Symbolic + Heuristic Only）**：强制关闭神经提议路径（`strategy="symbolic_only"` + 库组合），检验在无本地权重环境下 LLM 的真实边际贡献（对应 H10）。
- **Regime F（Pure LLM / Heuristic Pass@$k$）**：不进行 System 2 主动探针查询，直接对初始候选池（$k=16$）检查是否恰好收敛或统计单轮 pass 表现。
- **Regime G（Bottom-Up Enumerative Search Baseline）**：自底向上 AST 枚举基线（`SymbolicEnumerator` 按深度枚举满足可见样例的候选，每次选前两个未证伪候选的第一个区分输入查询 Oracle）。

---

## 2. 实验一：无 Oracle 被动模式（Passive Mode, $B=0, \text{oracle\_fn}=\text{None}$）

在无外部 Oracle 可供主动查询的设定下，系统仅能依靠任务给定的 2 个可见样例（`visible_examples`）过滤候选。根据第 2 阶段对 H7 的诚实状态修复：若可见样例过滤后仍有 $\ge 2$ 个语义不等价的候选程序存活，系统**绝不猜选 Top-1 冒充验证成功**，而是诚实返回 `VerificationStatus.UNVERIFIED_BUDGET_EXHAUSTED`（`converged=False`）。

数据文件：`/Users/prognosticatex/Desktop/reports/passive_mode_results.csv`（桌面副本：`/Users/prognosticatex/Desktop/passive_mode_results.csv`）

| 配置 (Regime) | 总体成功率 (Overall %, Mean ± 95% CI) | 留出任务族成功率 (Held-Out %, Mean ± 95% CI) | 结晶库规模 (LibSize) | 诚实状态说明 |
| :--- | :---: | :---: | :---: | :--- |
| **A: Full System (Passive)** | **20.00% ± 3.17%** | **35.00% ± 3.27%** | 6.0 | 仅当可见样例唯一锁定单语义等价类时返回 `VERIFIED_CONVERGED` |
| **D: No Crystallization (Passive)** | 13.33% ± 2.04% | 16.67% ± 0.00% | 0.0 | 无结晶库时复合任务候选覆盖下降 |
| **E: No LLM (Passive)** | **18.89% ± 2.04%** | **35.00% ± 3.27%** | 6.0 | 与 Regime A 在置信区间内完全重叠 |
| **F: Passive Pass@$k$ ($k=16$)** | 13.33% ± 2.04% | 16.67% ± 0.00% | 0.0 | 单轮静态过滤无法消解欠定样例歧义 |
| **G: Bottom-Up Enumerator (Passive)** | 8.33% ± 0.00% | 0.00% ± 0.00% | 0.0 | 深度 3 枚举在无 Oracle 消歧时几乎全部处于多解歧义状态 |

**关键发现**：在仅有 2 个可见样例的欠定程序合成任务中，被动模式（$B=0$）只能唯一确定 $8.33\% \sim 20.00\%$ 的任务；其余 $80\%$ 的任务存在多个满足可见样例但行为不同的欺骗性假设（deceptive hypotheses），必须依赖主动探针查询消歧。

---

## 3. 实验二：主动 Oracle 查询预算对比（Active Mode, $B \in \{1, 2, 4, 8, 16\}$）

数据文件：`/Users/prognosticatex/Desktop/reports/phase3_results_summary.csv`（桌面副本：`/Users/prognosticatex/Desktop/phase3_results_summary.csv`）
可视化图表：
- 成功率 vs 查询预算曲线：`/Users/prognosticatex/Desktop/reports/success_vs_budget.png`（桌面副本：`/Users/prognosticatex/Desktop/success_vs_budget.png`）
- $B=4$ 总体与留出族消融柱状图：`/Users/prognosticatex/Desktop/reports/ablation_comparison.png`（桌面副本：`/Users/prognosticatex/Desktop/ablation_comparison.png`）

### 3.1 总体成功率（Overall Success Rate %, 36 Tasks, 5 Seeds Mean ± 95% CI）

| Oracle 预算 $B$ | A: Full System | B: Random Probe | C: Z3-Only (No IG) | D: No Crystallization | E: No LLM | F: Passive Pass@$k$ | G: Bottom-Up Enum |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **$B = 1$** | **83.33% ± 1.72%** | 46.67% ± 2.67% | 34.44% ± 4.42% | 75.00% ± 0.00% | **82.78% ± 1.09%** | 15.56% ± 2.18% | 33.33% ± 4.87% |
| **$B = 2$** | **86.11% ± 0.00%** | 57.22% ± 7.62% | 38.89% ± 2.98% | 76.67% ± 1.33% | **86.11% ± 0.00%** | 15.00% ± 2.18% | 40.56% ± 1.33% |
| **$B = 4$** | **86.11% ± 0.00%** | 77.22% ± 8.33% | 38.33% ± 5.55% | 78.89% ± 1.33% | **86.11% ± 0.00%** | 15.56% ± 2.18% | 41.67% ± 0.00% |
| **$B = 8$** | **91.67% ± 0.00%** | 88.33% ± 2.67% | 38.89% ± 2.98% | 82.22% ± 1.33% | **91.67% ± 0.00%** | 13.33% ± 2.04% | 41.67% ± 0.00% |
| **$B = 16$** | **94.44% ± 0.00%** | 92.78% ± 2.78% | 35.56% ± 5.28% | 82.22% ± 1.33% | **94.44% ± 0.00%** | 15.00% ± 1.33% | 41.67% ± 0.00% |

### 3.2 严格留出任务族成功率（Held-Out Compositional Families: `list_composition` + `str_composition`, 12 Tasks）

| Oracle 预算 $B$ | A: Full System | B: Random Probe | C: Z3-Only (No IG) | D: No Crystallization | E: No LLM | F: Passive Pass@$k$ | G: Bottom-Up Enum |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **$B = 1$** | **91.67% ± 0.00%** | 56.67% ± 6.11% | 43.33% ± 6.11% | 50.00% ± 0.00% | **91.67% ± 0.00%** | 16.67% ± 0.00% | 0.00% ± 0.00% |
| **$B = 2$** | **91.67% ± 0.00%** | 58.33% ± 7.30% | 45.00% ± 4.00% | 58.33% ± 0.00% | **91.67% ± 0.00%** | 16.67% ± 0.00% | 0.00% ± 0.00% |
| **$B = 4$** | **91.67% ± 0.00%** | 71.67% ± 9.80% | 38.33% ± 6.53% | 56.67% ± 3.27% | **91.67% ± 0.00%** | 16.67% ± 0.00% | 0.00% ± 0.00% |
| **$B = 8$** | **91.67% ± 0.00%** | 85.00% ± 6.11% | 41.67% ± 5.17% | 56.67% ± 3.27% | **91.67% ± 0.00%** | 16.67% ± 0.00% | 0.00% ± 0.00% |
| **$B = 16$** | **91.67% ± 0.00%** | 88.33% ± 4.00% | 40.00% ± 6.11% | 55.00% ± 4.00% | **91.67% ± 0.00%** | 16.67% ± 0.00% | 0.00% ± 0.00% |

### 3.3 每任务平均资源消耗（Oracle 查询数、Z3 求解时间与调用数、LLM 调用数、库规模）

以代表性预算 **$B = 2$** 与 **$B = 16$** 为例（全量预算明细见 `phase3_results_summary.csv`）：

| 预算 $B$ | 配置 (Regime) | 平均 Oracle 查询数 | 平均 Z3 耗时 (ms) | 平均 Z3 调用数 | 平均 LLM 调用数 | 结晶库规模 (LibSize) |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: |
| **$B = 2$** | **A: Full System** | **1.32** | **1.14 ms** | **1.90** | 0.00 | 6.0 |
| $B = 2$ | B: Random Probe | 1.73 | 1.40 ms | 2.40 | 0.00 | 6.0 |
| $B = 2$ | C: Z3-Only (No IG) | 0.29 | 1.14 ms | 1.90 | 0.00 | 6.0 |
| $B = 2$ | D: No Crystallization | 1.14 | 5.52 ms | 7.20 | 0.00 | 0.0 |
| $B = 2$ | E: No LLM | **1.35** | **1.34 ms** | **1.60** | 0.00 | 6.0 |
| $B = 2$ | F: Passive Pass@$k$ | 0.00 | 0.00 ms | 0.00 | 0.00 | 0.0 |
| $B = 2$ | G: Bottom-Up Enum | 1.27 | 0.00 ms | 0.00 | 0.00 | 0.0 |
| **$B = 16$** | **A: Full System** | **2.28** | **1.73 ms** | **2.50** | 0.00 | 6.0 |
| $B = 16$ | B: Random Probe | 4.77 | 1.63 ms | 3.00 | 0.00 | 6.0 |
| $B = 16$ | C: Z3-Only (No IG) | 0.30 | 1.14 ms | 2.00 | 0.00 | 6.0 |
| $B = 16$ | D: No Crystallization | 1.60 | 7.91 ms | 10.40 | 0.00 | 0.0 |
| $B = 16$ | E: No LLM | **2.33** | **1.88 ms** | **2.30** | 0.00 | 6.0 |
| $B = 16$ | F: Passive Pass@$k$ | 0.00 | 0.00 ms | 0.00 | 0.00 | 0.0 |
| $B = 16$ | G: Bottom-Up Enum | 2.14 | 0.00 ms | 0.00 | 0.00 | 0.0 |

---

## 4. 实验三：SMT 输出签名聚类消融与System 3 穷举对比

### 4.1 SMT 候选集规模 $k \in \{5, 10, 20, 40\}$ 求解耗时与调用数对比（对应 H5/H6）
在未加输出签名聚类前，`SMTDistinguisher` 对候选池做两两组合 $\binom{k}{2}$ 调用 Z3；引入种子输入签名预聚类（`generate_candidate_probe_pool`）后，仅在跨签名簇代表元间调用 Z3：

| 候选集规模 $k$ | 朴素两两求解对数 $\binom{k}{2}$ | 朴素 Z3 耗时 (ms) | 签名聚类后 Z3 调用数 | 签名聚类后耗时 (ms) | 加速比 | 超时率 (`timeout_ms=500`) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| $k = 5$ | 10 | 45.8 ms | 3 | 12.4 ms | **3.7×** | 0.0% |
| $k = 10$ | 45 | 178.9 ms | 6 | 24.1 ms | **7.4×** | 0.0% |
| $k = 20$ | 190 | 786.1 ms | 15 | 58.3 ms | **13.5×** | 0.0% |
| $k = 40$ | 780 | 3285.9 ms | 28 | 109.2 ms | **30.1×** | 0.0% |

### 4.2 System 3 贪心启发式 vs 穷举最优解（$2^{10}=1024$ 子集）与次模性检验（对应 H12）
在 $n=10$ 个候选抽象的基准实例上对比 `ValueCompressor.select_optimal_library` 与 $2^{10}=1024$ 子集暴力穷举：
- **重叠子表达式非次模性（Non-Submodularity）**：当两个候选抽象 $a_1, a_2$ 存在 AST 包含/重叠关系时，先进行最长匹配重写（修复了原顺序依赖 bug）会产生边际收益交互，在 200 次随机三元组 $(S, T, x)$ 检验中观测到边际收益并非恒定单调递减，证实该目标函数是**贪心启发式（Greedy Heuristic）**而非严格次模函数（已在文档与注释中移除 $(1 - 1/e)$ 理论近似比声明）。
- **经验近似质量**：在 $n=10$ 穷举基准上，最长匹配一致化后的贪心启发式所选库净收益达到全局穷举最优解的 **$98.4\%$**，耗时 `0.8 ms`（穷举耗时 `42.5 ms`）。

---

## 5. 对核心假设的明确结论（Supported vs Refuted）

1. **核心假设 1（System 2 贝叶斯信息增益探针优于随机探针与单纯 Z3 区分输入）**：**SUPPORTED（在低查询预算 $B \in \{1, 2, 4\}$ 下高度显著；高预算下优势体现为查询样本效率）**
   - **证据**：在 $B=1$ 时，Regime A（IG 探针）总体成功率为 **`83.33% ± 1.72%`**，显著高于同预算的 Regime B 随机探针（**`46.67% ± 2.67%`**，高出 $+36.66$ 个百分点）和 Regime C 单纯 Z3 探针（**`34.44% ± 4.42%`**，高出 $+48.89$ 个百分点）。
   - **适用范围说明**：当查询预算放宽至 $B=16$ 时，随机探针（Regime B）靠暴力多次查询可将成功率追至 `92.78% ± 2.78%`（接近 Regime A 的 `94.44% ± 0.00%`），但 **Regime B 平均每任务消耗 `4.77` 次 Oracle 查询，是 Regime A（`2.28` 次）的 $2.09$ 倍**。此外，Regime C（仅依赖 Z3 区分输入）在所有预算下均停滞在 `34.44% ~ 38.89%`，因为 Z3 仅覆盖有界整数/列表一阶片段，无法为字符串变换和复杂高阶组合生成探针，证明**“Z3 区分输入 + 多样化种子探针池 + 闭式 IG 排序”缺一不可**。

2. **核心假设 2（System 3 价值加权知识结晶提升留出任务族正向迁移率）**：**SUPPORTED**
   - **证据**：对比 Regime A（启用结晶库，在训练族自举出 6 个算子）与 Regime D（无结晶库）：在留出复合任务族（`list_composition` + `str_composition`）上，成功率从 **`50.00% ~ 58.33%`（Regime D）大幅提升至 `91.67% ± 0.00%`（Regime A）**，正向迁移增益达 **$+33.34 \sim +41.67$ 个百分点**；同时平均每任务 Z3 求解耗时从 `5.52 ms`（7.2 次调用）降至 `1.14 ms`（1.9 次调用）。这是因为结晶出的高阶原语将原本深度为 4 的复合 AST 压缩为深度为 2 的算子调用，直接落入 System 1 的浅层搜索半径内。

3. **核心假设 3（System 1 神经 LLM 提议器相比纯符号/启发式枚举具有显著贡献）**：**REFUTED（在未配置 MLX 本地大模型权重的默认环境中完全无贡献）**
   - **证据**：在全部预算 $B \in \{0, 1, 2, 4, 8, 16\}$ 下，**Regime A（完整系统）与 Regime E（关闭 LLM，仅用符号枚举 + 启发式规则 + 结晶库）的留出集成功率完全一致（均为 `91.67% ± 0.00%`），总体成功率在 $B \ge 2$ 时完全一致（`86.11%`, `86.11%`, `91.67%`, `94.44%`）**，且 `Avg LLM Calls = 0.0`。
   - **原因剖析**：当 `mlx-lm` 未安装或未加载本地 Qwen 权重时，`HypothesisGenerator` 自动退化为手工编写的 `_heuristic_synthesizer` 模板库，与 `SymbolicEnumerator` 及结晶算子 1-step 组合完全覆盖了基准任务空间。因此，当前仓库的实验收益来自**符号搜索 + 贝叶斯主动探针 + 知识库结晶**，而非神经大模型。我们已在 `README.md` 与 `README_zh.md` 中如实写明这一事实。

4. **核心假设 4（主动交互式合成相比静态 Pass@$k$ 与自底向上枚举的必要性）**：**SUPPORTED**
   - **证据**：静态 Pass@$k$（Regime F）总体成功率仅为 `13.33% ~ 15.56%`，自底向上无库枚举（Regime G）在留出复合任务族上成功率为 `0.00%`（总体 `33.33% ~ 41.67%`），证明在欠定 I/O 规范与组合深度增加时，单纯增加静态采样或浅层枚举无法替代主动探针证伪与高阶原语结晶。
