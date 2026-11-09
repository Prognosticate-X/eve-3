# EVE-3 "证据优先" 代码审计报告 (Phase 0 & Phase 1 Audit Report)

> **审计时间**: 2026-11-09  
> **审计对象**: `/Users/prognosticatex/Desktop/eve-3` (`HEAD` @ `main`)  
> **审计准则**: 任何结论均附带 `文件路径:行号` + 关键代码片段（$\le 10$ 行）或实际运行输出；未修改任何源码。

---

## 第 0 阶段：建立基线（未修改任何源码）

### 0.1 文档中列出的"可验证声明"清单

通过对 `README.md`、`docs/ARCHITECTURE.md`、`docs/MATHEMATICS.md`、`docs/ROADMAP.md` 的逐行对照，提取出以下核心可验证声明：

1. **System 1 神经直觉提议 (`README.md:50, 79-81`, `docs/ARCHITECTURE.md:50-52`)**：使用本地 `mlx-lm` (`Qwen2.5-Coder-3B-Instruct-4bit`) 生成候选 DSL 程序，沙箱执行具备墙钟超时（wall-clock timeout）、步数上限与递归深度限制。
2. **System 2 先验分布 (`docs/MATHEMATICS.md:19-24`)**：初始先验遵循 Solomonoff/Occam 最小描述长度（MDL）：$b_i^{(0)} = \frac{2^{-L(P_i)}}{\sum_{j=1}^k 2^{-L(P_j)}}$。
3. **System 2 闭式信息增益 (`README.md:58, 86-87`, `docs/MATHEMATICS.md:30-47`)**：按输出等价类 $G_v(x) = \{i : P_i(x) = v\}$ 计算边际概率 $q_v(x) = \sum_{i \in G_v(x)} b_i$ 与精确互信息 $IG(x) = H(b) - \sum_{v} q_v(x) H(b \mid G_v(x))$。
4. **System 2 确定性更新、Laplace 平滑与塌缩保护 (`README.md:88`, `docs/MATHEMATICS.md:74-85`)**：
   - `MATHEMATICS.md:76` 声明确定性更新下 $P_i(x^*) \neq y_{\text{obs}}$ 时 $b_i \leftarrow 0$；
   - `MATHEMATICS.md:82-84` 同时声明使用 Laplace 平滑 $\mathcal{L}(y_{\text{obs}} \mid P_i, x^*) = (1-\epsilon)\mathbb{I}[P_i(x^*)=y_{\text{obs}}] + \epsilon\mathbb{I}[P_i(x^*)\neq y_{\text{obs}}]$，且当 $\sum_i b_i \mathcal{L}_i < 10^{-12}$ 时回退至均匀分布并调用 System 1 扩展搜索深度重新提议。
5. **System 2 Z3 SMT 区分输入合成 (`README.md:57, 85`, `docs/ARCHITECTURE.md:56`, `docs/MATHEMATICS.md:64-68`)**：对候选对 $(P_i, P_j)$ 编码操作语义至 Z3 求解 $P_i(x) \neq P_j(x)$，并声称结合 `hypothesis` 属性边界测试。
6. **System 2 诚实状态与零假验证率 (`README.md:117, 154, 266`, `docs/PREREGISTRATION.md:19, 34`)**：仅当通过独立留出测试集（`HELD_OUT_TESTS_PASSED`）或形式化证明（`FORMALLY_VERIFIED`）时才标记 `converged = True`，假验证率严格为 $0.0\%$。
7. **System 3 价值加权次模压缩与 $(1-1/e)$ 近似保证 (`README.md:92-94`, `docs/MATHEMATICS.md:104-146`)**：优化 $\text{Benefit}_w(\mathcal{L}) - \gamma \cdot \text{Cost}(\mathcal{L})$，其中 $w_i = |\text{TaskFamilies}(P_i)| \times (1 + \ln(1 + \text{ReuseCount}_i))$；声称 $\text{Benefit}_w(\mathcal{L})$ 具有次模性（边际收益递减），贪心算法保证 $(1 - 1/e)$ 近似比，并将算子晋升回 System 1 提示与原语（`README.md:67`）。
8. **Discovery Tree 零边际成本反事实策略回放 (`README.md:74, 104`, `docs/ARCHITECTURE.md:68`)**：将探索历史记录为有向树，支持零边际环境评估成本的离线反事实策略评估。
9. **多时间尺度可塑性与预注册回归门 (`README.md:110-117`, `docs/PREREGISTRATION.md:23-36`)**：`AdapterBank` 按任务族隔离 LoRA 适配器，`RegressionGate` 强制执行历史族退化 $\le 2\%$、通用探针下降 $\le 3\%$、假验证率 $= 0.0\%$。

---

### 0.2 环境记录

| 环境项 | 实测值 |
| :--- | :--- |
| **硬件** | Apple M1 Max, 64 GB Unified Memory (`hw.memsize = 68719476736`) |
| **操作系统** | macOS 27.0.1 (`BuildVersion: 26A434`) |
| **Python 版本** | `Python 3.14.8` (`/Users/prognosticatex/homebrew/bin/python3`) |
| **z3-solver 版本** | `4.16.0` (已安装) |
| **mlx / mlx-lm** | **未安装** (`No module named 'mlx'`, `No module named 'mlx_lm'`) |
| **hypothesis** | **未安装** (`No module named 'hypothesis'`) |
| **pytest** | `9.2.0` |

---

### 0.3 测试套件基线运行结果

1. **`python3 -m unittest discover -s tests -p "test_*.py" -v`**：
   - **通过 (Passed)**: `80`
   - **失败 (Failed)**: `0`
   - **跳过 (Skipped)**: `0`
   - **耗时**: `5.640s`
2. **`pytest tests/ -q -rs`**：
   - **通过 (Passed)**: `80 passed`
   - **失败 (Failed)**: `0`
   - **跳过 (Skipped)**: `0`
   - **耗时**: `5.91s`
3. **被跳过原因分析**：没有任何测试被 skip（`0 skipped`）。原因是整个 `tests/` 目录下没有任何测试使用 `@unittest.skip` 或 `@pytest.mark.skipif`；即使本地未安装 `mlx-lm` 和 `hypothesis`，代码通过静默异常捕获（`generator.py:76-77`）回退到启发式模板，因此测试不会显示 skip。

---

### 0.4 Benchmark 统计与现有 `experiments/` 脚本完整输出摘要

#### Benchmark 任务统计
仓库 `benchmarks/` 下共有两套部分重叠的数据集文件：
1. **按任务族划分 (`benchmarks/families/*.json`，由 `manifest.json` 索引)**：共 **5 个任务族、13 个任务**：
   - 训练任务族（4 族，共 10 个任务）：
     - `list_mapping`（3 个任务）：`list_increment_all`, `list_double_all`, `list_decrement_all`
     - `list_filtering`（3 个任务）：`filter_evens`, `filter_greater_than_two`, `filter_positive`
     - `list_reduction`（2 个任务）：`list_sum`, `list_length`
     - `list_structural`（2 个任务）：`list_reverse`, `list_tail_elements`
   - 留出任务族（1 族，共 3 个任务）：
     - `list_composition`（3 个任务）：`filter_evens_and_sum`, `filter_positive_and_sum`, `reverse_and_tail`
2. **传统切分文件（与上述 10 个训练族任务完全重复）**：
   - `benchmarks/dev_train.json`（2 个任务）：`list_increment_all` (`list_mapping`), `filter_evens` (`list_filtering`)
   - `benchmarks/dev_eval.json`（2 个任务）：`list_double_all` (`list_mapping`), `list_sum` (`list_reduction`)
   - `benchmarks/held_out_test.json`（3 个任务）：`filter_greater_than_two` (`list_filtering`), `list_reverse` (`list_structural`), `filter_positive` (`list_filtering`)
   - `benchmarks/list_functions.json`（6 个任务）：上述任务的子集
   - `benchmarks/general_coding_probe.json`（5 个非 DSL Python 算法探针）

#### `experiments/` 全部 9 个脚本运行结果汇总

| 脚本路径 | 核心输出指标 |
| :--- | :--- |
| `experiments/run_library_ablation.py` | `dev_train` 训练 2 任务；`dev_eval` 评测 2 任务：`No-Lib` 成功率 `100%` (`avg_probes=4.00`: `list_double_all=0`, `list_sum=8`) vs `With-Lib` 成功率 `100%` (`avg_probes=4.00`: `list_double_all=0`, `list_sum=8`)。**有无库完全无差异**。 |
| `experiments/run_full_ablation.py` | 评测 5 任务 (`dev_eval` + `held_out_test`)，单种子 `[42]`：`Baseline_A_Naive` Pass=`100.0%`, FalseVerif=`0.0%`, AvgProbes=`0.00`；`Baseline_B_FalsifyOnly` / `Baseline_C_Library` / `Full_System` 三者指标**完全一致**：Pass=`100.0%`, FalseVerif=`0.0%`, AvgProbes=`1.60`。 |
| `experiments/run_continual_learning.py` | Cold-start `list_composition` Pass=`0.0% (0/3)`；4 阶段巩固后 BWT=`0.00%`, General Probe Drop=`0.00%`, FWT=`+33.33% (1/3)`, FVR=`0.00%`。 |
| `experiments/run_autonomous_curriculum.py` | Arm A4 训练 10/10，Held-out=`33.3% (1/3)`；Arm A5 探索 13/16，Held-out=`33.3% (1/3)`，Synthetic Ratio=`37.5%`，Entropy=`0.458`。 |
| `experiments/run_memory_consolidation.py` | Policy A (Unbounded): 14/16 solved, Active=14；Policy B (Tiered): 14/16 solved, Hot=7, Cold=7, Episodic Summaries=6。 |
| `experiments/run_env_simulation.py` | L1 Grid Pass=`100.0% (4/4)`，L2 Sim Pass=`100.0%`，Safety Penetration=`0.00%`，Arm S1 ECE=`0.2900` vs Arm S2 ECE=`0.0200`。 |
| `experiments/run_perception_frontend.py` | Clean SceneGraph Pass=`100.0%`，`eps=0.05` Pass: Arm P1=`56.7%` vs Arm P2=`95.0%`，`eps=0.10` Pass: Arm P1=`0.0%` vs Arm P2=`90.0%`。 |
| `experiments/run_policy_evolution.py` | 离线回放 3 个策略 (`conservative`, `balanced`, `verification_first`) 的 `simulated_cost=2.20, steps=4` **完全相同**；在线评测均为 `3/3`。 |
| `experiments/run_autonomous_agi_loop.py` | 3 轮 Wake-Sleep 循环：累计提议 12 任务，解决 11 (`91.7%`)，FVR=`0.00%`，BWT=`0.00%`，FWT=`15.00%`。 |

---

## 第 1 阶段：逐项审计（H1–H18 及横向检查）

---

### H1 先验分布初始化
- **审计问题**：`bayesian_prober.py` 中后验初始化是否均匀？是否使用了 LLM 似然、程序描述长度（MDL）或 task-family 信息？
- **结论**：**CONFIRMED（确认非均匀，仅硬编码使用 AST 节点数 MDL 先验，未使用 LLM 似然或 task-family 信息，且不可配置）**
- **影响等级**：**P1**（影响效果与可配置性；且如 H3 所示，指数级 MDL 先验差距会压倒 Laplace 平滑似然）
- **证据**：
  - `eve3/system2_falsifier/bayesian_prober.py:39-49`：
    ```python
    def initialize_beliefs(self, hypotheses: List[CandidateProgram]) -> List[float]:
        r"""Compute initial Occam/MDL prior: b_i \propto 2^{-L(P_i)}."""
        if not hypotheses:
            return []
        
        # Calculate unnormalized priors
        raw_weights = [2.0 ** (-float(p.description_length)) for p in hypotheses]
        total = sum(raw_weights)
        if total <= 1e-12:
            return [1.0 / len(hypotheses)] * len(hypotheses)
        return [w / total for w in raw_weights]
    ```
  - 实测输出（`scratch/audit_check.py`）：
    ```text
    x                                   DL=1 -> b_0=0.659794
    (reverse x)                         DL=2 -> b_0=0.329897
    (map (lambda (a) (+ a 1)) x)        DL=7 -> b_0=0.010309
    ```

---

### H2 信息增益（Information Gain）实现与语义等价类问题
- **审计问题**：IG 的实现是否真的是 $H(b) - \sum q_v \cdot H(b \mid G_v)$？$q_v$ 如何从后验计算（是否按输出等价类对后验质量求和）？对照 `MATHEMATICS.md` 写一个数值单元测试，手算 3 个候选、2–3 个输出分区的例子，比较实现结果。
- **结论**：**CONFIRMED（数学公式实现与 `MATHEMATICS.md` 完全一致；但未先按语义等价类合并候选，导致语法同义候选扭曲先验分布 $b$ 并阻碍收敛）**
- **影响等级**：**P1**（影响主动探针质量与收敛判定）
- **证据**：
  1. **代码片段**（`eve3/system2_falsifier/bayesian_prober.py:72-90`）：
     ```python
     def compute_information_gain(self, hypotheses, beliefs, probe_input, timeout=0.5) -> float:
         groups = self.group_by_output(hypotheses, probe_input, timeout=timeout)
         h_prior = entropy(beliefs)
         conditional_entropy = 0.0
         for idxs in groups.values():
             q_v = sum(beliefs[i] for i in idxs)
             sub_dist = renormalize(beliefs, idxs)
             conditional_entropy += q_v * entropy(sub_dist)
         ig = h_prior - conditional_entropy
         return max(0.0, ig)
     ```
  2. **手算 vs 实现数值检验**（3 个候选 $P_1=\texttt{(+ x 1)}, P_2=\texttt{(+ x 2)}, P_3=\texttt{(* x 2)}$，描述长度均为 3，故先验 $b = [1/3, 1/3, 1/3]$，$H(b) = \log_2 3 \approx 1.5849625007$）：
     - **2 个输出分区（探针 $x=1$）**：$P_1(1)=2, P_2(1)=3, P_3(1)=2$。分区 $G_2=\{0,2\}$ ($q_2=2/3, H(b\mid G_2)=1.0$)，$G_3=\{1\}$ ($q_3=1/3, H(b\mid G_3)=0.0$)。手算 $IG(1) = \log_2 3 - \frac{2}{3}(1) = 0.9182958341$。
     - **3 个输出分区（探针 $x=0$）**：$P_1(0)=1, P_2(0)=2, P_3(0)=0$。三个单元素分区，$H(b\mid G_v)=0$。手算 $IG(0) = \log_2 3 = 1.5849625007$。
     - **实测输出**（`scratch/audit_check.py`）：
       ```text
       Case A (2 partitions, x=1): impl=0.9182958341, hand=0.9182958341, diff=0.00e+00
       Case B (3 partitions, x=0): impl=1.5849625007, hand=1.5849625007, diff=0.00e+00
       ```
  3. **未合并语义等价类导致的缺陷**：当候选集中同时存在语法不同但语义完全等价的候选（例如 `(map (lambda (a) (+ a 1)) x)` 与 `(map (lambda (a) (inc a)) x)`，或 `(sum x)` 与 `(fold (lambda (acc item) (+ acc item)) 0 x)`）时，它们被赋予多份先验质量（实测 `(+ x 1)` 与 `(inc x)` 占据 $0.75$ 先验质量），且永远无法被任何探针区分，导致 `CEGISLoop` 无法满足 `len(hypotheses) == 1` 提前终止条件。

---

### H3 噪声一致性与 Laplace 平滑反例复活缺陷
- **审计问题**：程序是确定性的，却使用 Laplace 平滑。请说明平滑参数的作用，写一个测试检验：当某候选被一次反例证伪后，其后验是否降为 0、接近 0，还是被平滑抬高？这是否会让已被证伪的程序重新进入 top-1？
- **结论**：**CONFIRMED（被证伪候选的后验不为 0，而是乘上 $\epsilon = 10^{-6}$；这在两种确定性场景下会导致已被反例证伪的错误程序保持或重新进入 top-1）**
- **影响等级**：**P0**（阻塞结论可信度：违反确定性程序合成的基本逻辑一致性，且与 `docs/MATHEMATICS.md:76` 公式 $b_i \leftarrow 0$ 自相矛盾）
- **证据**：
  1. **代码片段**（`eve3/system2_falsifier/bayesian_prober.py:129-140`）：
     ```python
     for p in hypotheses:
         try:
             actual_out = p.evaluate(probe_input, timeout=timeout)
             if actual_out == observed_output:
                 likelihoods.append(1.0 - self.smoothing_epsilon)
             else:
                 likelihoods.append(self.smoothing_epsilon)
         except Exception:
             likelihoods.append(self.smoothing_epsilon)
     new_beliefs = [b * l for b, l in zip(beliefs, likelihoods)]
     ```
  2. **场景 A（MDL 先验不对称导致被证伪程序在单次反例后仍霸占 top-1）**：
     - 设短程序 $P_{\text{short}} = \texttt{x}$ ($\text{DL}=1$)，长程序 $P_{\text{long}}$ ($\text{DL}=23$)，初始先验比 $2^{22} \approx 4.19 \times 10^6$。
     - 给定反例探针 `[1, 2] -> [2, 3]`：$P_{\text{short}}([1,2]) = [1,2] \neq [2,3]$（**被证伪**），$P_{\text{long}}([1,2]) = [2,3]$（**完全匹配**）。
     - 由于平滑参数 $\epsilon = 10^{-6}$，$P_{\text{short}}$ 的后验为 $\frac{2^{-1} \cdot 10^{-6}}{2^{-1} \cdot 10^{-6} + 2^{-23} \cdot (1 - 10^{-6})} = \mathbf{0.8075} > 0.1925$，且 $0.8075 > 10^{-4}$ 不会被 `cegis_loop.py:177` 剪枝！
  3. **场景 B（多步更新中已证伪程序重新夺回 top-1）**：
     - 设 $P_1 = \texttt{(+ x 1)}$，$P_3 = \texttt{(* x 2)}$。
     - 第 1 步探针 $x=0, y_{\text{obs}}=1$：$P_3(0)=0 \neq 1$ 被证伪，后验变为 $[0.999999, 10^{-6}]$。
     - 若后续探针 $x=2, y_{\text{obs}}=4$ 及 $x=3, y_{\text{obs}}=6$ 上 $P_1$ 不匹配而已被证伪的 $P_3$ 恰好匹配，则 $P_3$ 的后验从 $10^{-6} \to 0.5000 \to \mathbf{0.999999}$ 重新成为 top-1！
  4. **实测输出**（`scratch/audit_check.py`）：
     ```text
     P1 vs P3 after x=0, obs=1 (P3 falsified): P1=0.99999900, P3=0.00000100
     P1 vs P3 after x=2, obs=4 (P3 was already falsified at x=0!): P1=0.50000000, P3=0.50000000
     P1 vs P3 after x=3, obs=6 (P3 regains top-1 despite being falsified at x=0!): P1=0.00000100, P3=0.99999900
     After probe [1,2]->[2,3] (p_short FALSIFIED, p_long MATCHES): b_short=0.80748158, b_long=0.19251842
     Falsified p_short remains top-1: True (and b_short > 1e-4 so not pruned in CEGIS!)
     ```

---

### H4 假设空间塌缩保护（Hypothesis Collapse Protection）失效
- **审计问题**：找出 "hypothesis collapse protection" 的实现，说明它在什么条件下触发、触发后做什么。构造"真程序不在候选集内"的任务，观察系统是返回错误的 top-1、报告失败，还是触发重新提议。
- **结论**：**CONFIRMED（塌缩保护在默认配置下是死代码：当所有候选均被同一探针证伪时，每个候选似然同乘 $\epsilon=10^{-6}$，归一化后后验分布保持原样不变，无一候选被剪枝，不触发重新提议，最终返回已被证伪的错误 top-1）**
- **影响等级**：**P0**（阻塞结论可信度：真程序不在候选集内时，系统不会报告 `COLLAPSED`，若无留出集则直接将已被 Oracle 证伪的程序标记为 `CONSISTENT_WITH_OBSERVATIONS` 返回）
- **证据**：
  1. **代码片段 1**（`eve3/system2_falsifier/bayesian_prober.py:139-147`）：
     ```python
     new_beliefs = [b * l for b, l in zip(beliefs, likelihoods)]
     total = sum(new_beliefs)
     # Hypothesis space collapse protection
     if total <= 1e-12:
         return [1.0 / len(hypotheses)] * len(hypotheses)
     return [b / total for b in new_beliefs]
     ```
     **数学缺陷**：因为 $\sum_i b_i = 1$，当没有任何候选匹配 $y_{\text{obs}}$ 时，所有 $l_i = \epsilon = 10^{-6}$，故 $\text{total} = \sum_i b_i \cdot 10^{-6} = 10^{-6} > 10^{-12}$！`if total <= 1e-12` 永远不触发，且 `b / total` 等于 $\frac{b_i \cdot 10^{-6}}{10^{-6}} = b_i$（后验丝毫未变）！
  2. **代码片段 2**（`eve3/system2_falsifier/cegis_loop.py:173-187`）：
     ```python
     survivors = []
     survivor_beliefs = []
     for h, b in zip(hypotheses, beliefs):
         if b > 1e-4:
             survivors.append(h)
             survivor_beliefs.append(b)
     if not survivors:
         # Version space collapse: re-generate hypotheses with updated examples
     ```
     由于全军覆没时 `beliefs` 原封不动（所有 $b_i > 10^{-4}$），`survivors` 保留了全部已被证伪的候选，`if not survivors:` **永远不会触发**！
  3. **实测输出**（构造真程序不在候选集内的任务：初始样例 `([1, 2], [2, 3])`，真实 Oracle 对长度 $\neq 2$ 的列表返回 `[999]`）：
     ```text
     All hypotheses falsified (obs=999): prior=[0.5, 0.3, 0.2] -> posterior=[0.5, 0.3, 0.2]
     Out-of-hypothesis-space (held_out=None): status=consistent_with_observations, prog=(map (lambda (a) (inc a)) x), rounds=5, probes=5
     Out-of-hypothesis-space (with held_out): status=exhausted_unverified, prog=(map (lambda (a) (inc a)) x), rounds=5, survivors=3
     ```

---

### H5 SMT 区分器（`smt_distinguisher.py`）编码覆盖度、崩溃与 $O(k^2)$ 复杂度
- **审计问题**：`smt_distinguisher.py` 对哪些 DSL 原语有编码？fold/递归/高阶函数是否有界展开（展开深度是多少）？超时如何处理？区分候选时是 $O(k^2)$ 两两求解还是更优？对 $k=5/10/20/40$ 测量求解耗时和超时率。
- **结论**：**CONFIRMED（存在 3 处严重不实/缺陷：① `check_ast_support` 声称支持 `eq/gt/lt/head/reverse/map/filter/lambda`，但实际 `_ast_to_z3_int` 与 `_ast_to_z3_seq` 完全未实现它们；② 根本不存在任何高阶函数/fold 的有界展开；③ 在线性偏移 `(+ x 1)` vs `(+ x 2)` 上 `_z3_solve_integer_distinguishing` 因 `m[x]` 为 `None` 抛出 `AttributeError` 崩溃并静默退回固定启发式探针；④ 候选池生成采用 $O(k^2)$ 两两组合）**
- **影响等级**：**P0**（阻塞结论可信度：所有列表 `map`/`filter`/`reverse` 任务和常数偏移整数任务在现有实验中实际上**从未成功使用过 Z3 求解**，全部静默退化成了扫描 21 个硬编码默认探针！）
- **证据**：
  1. **支持矩阵声明 vs 实际编码实现对照**（`eve3/system2_falsifier/smt_distinguisher.py:68-69` vs `204-250`）：
     ```python
     # smt_distinguisher.py:68-69 (声明支持)
     arithmetic_ops = {"+", "-", "*", "inc", "dec", "neg", "eq", "gt", "lt"}
     list_bounded_ops = {"length", "tail", "head", "map", "filter", "reverse"}
     ```
     但在 `_ast_to_z3_int` (`204-228`) 中只实现了 `+`, `-`, `*`, `inc`, `dec`, `neg`（不含 `eq`, `gt`, `lt`）；在 `_ast_to_z3_seq` (`230-250`) 中**只实现了 `length` 和 `tail`**：
     ```python
     if ast_node.op_name == "length" and len(ast_node.args) == 1:
         ...
     if ast_node.op_name == "tail" and len(ast_node.args) == 1:
         ...
     return None
     ```
     `head`, `reverse`, `map`, `filter`, `fold`, `LambdaNode`, `IfElseNode` 在 Z3 编码中全部返回 `None`！所谓"高阶函数有界展开"（`smt_distinguisher.py:65`）在代码中完全不存在（仅在 `_z3_solve_list_distinguishing:181` 写了 `z3.Length(x) <= 6`）。
  2. **`m[x].as_long()` 崩溃缺陷**（`eve3/system2_falsifier/smt_distinguisher.py:154-156`）：
     ```python
     if s.check() == z3.sat:
         m = s.model()
         val = m[x].as_long()
     ```
     当求解 `(+ x 1) != (+ x 2)` 时，Z3 将公式化简为恒真 `True`，模型 `m` 中不包含自由变量 `x`，因此 `m[x]` 返回 `None`，`m[x].as_long()` 抛出 `AttributeError: 'NoneType' object has no attribute 'as_long'`，被 `find_distinguishing_input:122` 的 `except Exception: pass` 静默吞掉后回退到 `_heuristic_distinguishing`！
  3. **$O(k^2)$ 求解耗时与超时率实测**（`scratch/audit_check.py`，`timeout_ms=500`）：
     ```text
     (+ x 1) vs (+ x 2) find_distinguishing_input: <Probe 0 (heuristic_boundary, bounded_support)> (Z3 crashed with m[x]=None and fell back to heuristic!)
     k= 5 ( 10 pairs): int_Z3=  16.91ms (sat=10/10, timeout=0%), list_find_dist=   8.27ms
     k=10 ( 45 pairs): int_Z3=  71.27ms (sat=45/45, timeout=0%), list_find_dist=  35.50ms
     k=20 (190 pairs): int_Z3= 299.68ms (sat=190/190, timeout=0%), list_find_dist= 143.85ms
     k=40 (780 pairs): int_Z3=1201.60ms (sat=780/780, timeout=0%), list_find_dist= 571.70ms
     ```
     耗时随 $\binom{k}{2} = \frac{k(k-1)}{2}$ 呈严格二次方增长（$10 \to 45 \to 190 \to 780$ 对，耗时 $16.9\text{ms} \to 71.3\text{ms} \to 299.7\text{ms} \to 1201.6\text{ms}$）。

---

### H6 候选探针池来源与覆盖限制
- **审计问题**：最大化 IG 的候选探针从哪里来（仅来自 Z3 的区分输入，还是也包含随机/枚举输入）？如果只来自两两区分输入，说明这对"最优探针"的覆盖有何限制。
- **结论**：**CONFIRMED（来自两两区分输入 + 21 个硬编码静态边界探针，无随机/动态枚举输入；且两两区分输入无法保证覆盖全局多路划分最优探针）**
- **影响等级**：**P1**（限制最大信息增益探针的理论与实际覆盖度）
- **证据**：
  - `eve3/system2_falsifier/smt_distinguisher.py:284-300`：
    ```python
    for p1, p2 in itertools.combinations(hypotheses, 2):
        diff = self.find_distinguishing_input(p1, p2)
        if diff is not None:
            add_probe(diff)
        if len(probes) >= max_pool_size:
            break
    for default_p in self.generate_default_probes():
        if len(probes) >= max_pool_size:
            break
        add_probe(ProbeCandidate(default_p, source="heuristic_boundary", ...))
    ```
  - **覆盖限制分析**：
    1. **两两区分 $\neq$ 全局多路分割**：对单对 $(P_i, P_j)$ 求解 $P_i(x) \neq P_j(x)$ 仅能保证 $x$ 将该二元对分开（可能對其余 $k-2$ 个候选产生相同输出，仅提供 $\ll 1$ bit 信息增益），而能同时将 $k$ 个候选划分为多个等价类（提供高达 $\log_2 k$ bits 信息增益）的输入 $x^*$ 未必是任何单对求解器返回的第一个 witness。
    2. **池截断挤占**：当 $\binom{k}{2}$ 产生的两两探针达到 `max_pool_size=32` 时，后面的候选对与默认边界探针被直接丢弃。
    3. **文档不符**：`docs/ARCHITECTURE.md:56` 与 `docs/ROADMAP.md:47` 声称使用 property-based boundary testing (`hypothesis`)，但代码中既未导入 `hypothesis`，也无任何随机生成逻辑，仅有 21 个固定常数（`generate_default_probes:305-329`）。

---

### H7 CEGIS 循环状态完整性、留出集隔离与耗尽诚实性
- **审计问题**：逐一列出 `VerificationStatus` 的所有取值与触发条件；检查 held-out 测试是否可能泄漏进探针选择或候选过滤；检查 `max_falsification_rounds` 耗尽时的返回状态是否诚实（不得在未收敛时标记为成功）。
- **结论**：**CONFIRMED（held-out 测试未泄漏进探针选择；但 6 个状态中有 2 个从未实现，且在 `max_falsification_rounds` 耗尽或零信息增益探针下存在不诚实状态转换）**
- **影响等级**：**P0**（阻塞结论可信度：未消歧收敛而耗尽轮数时，仍将模糊 top-1 送去终验并可标记为 `HELD_OUT_TESTS_PASSED` 或 `CONSISTENT_WITH_OBSERVATIONS`）
- **证据**：
  1. **`VerificationStatus` 全部 6 个取值的触发条件核查**（`eve3/system2_falsifier/cegis_loop.py:17-25`）：
     | 状态枚举值 | `converged` 属性 | 实际代码中的触发条件 | 审计发现 |
     | :--- | :---: | :--- | :--- |
     | `CANDIDATE_FOUND` | `False` | **无任何代码返回该状态** | 死枚举值 |
     | `FORMALLY_VERIFIED` | `True` | **无任何代码返回该状态** | 死枚举值（从未做全定义域 SMT 等价性证明） |
     | `CONSISTENT_WITH_OBSERVATIONS` | `False` | `_finalize_result:283` 当 `held_out_tests` 为空/未提供时无条件返回 | **不诚实**：即使所有候选均已被 Oracle 反例证伪（见 H4）或轮数耗尽仍有多个竞争候选，只要未传 `held_out_tests` 就返回 `CONSISTENT_WITH_OBSERVATIONS` |
     | `HELD_OUT_TESTS_PASSED` | `True` | `_finalize_result:257` 当 `held_out_tests` 非空且被选出的单个 `candidate` 在 `held_out_tests` 上准确率 $=1.0$ | **耗尽时仍可触发**：见下方第 3 点 |
     | `EXHAUSTED_UNVERIFIED` | `False` | `_finalize_result:267` 当 `held_out_tests` 非空且被选出的单个 `candidate` 在 `held_out_tests` 上准确率 $<1.0$ | 仅在留出集测试失败时触发 |
     | `COLLAPSED` | `False` | `run_synthesis:101, 190` 当 `propose_candidates` 返回空列表 `[]` | 当探针证伪全部候选时因 H4 缺陷无法触发 |
  2. **Held-out 测试泄漏检查**：在 `cegis_loop.py:79-213` 中，`held_out_tests` 仅作为参数透传给 `_finalize_result`（第 121、143、157、211 行），未参与候选提议或主动探针选择，**确认无数据泄漏**。
  3. **`max_falsification_rounds` 耗尽时的行为**（`eve3/system2_falsifier/cegis_loop.py:203-213`）：
     ```python
     # Max rounds reached
     best_idx = max(range(len(beliefs)), key=lambda i: beliefs[i])
     return self._finalize_result(
         candidate=hypotheses[best_idx],
         rounds=self.config.max_falsification_rounds,
         ...
     ```
     当 `max_falsification_rounds` 耗尽且版本空间仍未收敛（或所有候选均被证伪）时，代码并未返回 `EXHAUSTED_UNVERIFIED`，而是直接取 `hypotheses[best_idx]` 调用 `_finalize_result`：若无 `held_out_tests` 则返回 `CONSISTENT_WITH_OBSERVATIONS`；若有 `held_out_tests` 且该候选碰巧通过留出测试，则直接标记 `HELD_OUT_TESTS_PASSED` (`converged = True`)！

---

### H8 Oracle 预算计数与"样本效率"指标定义
- **审计问题**：`oracle_fn` 被调用的次数是否被计数并暴露？"样本效率"指标当前如何定义（样例数、oracle 查询数、还是迭代轮数）？
- **结论**：**CONFIRMED（未设置独立的 `oracle_queries` 计数器；异常时漏计且死循环重试同一探针；且当剩余候选语义等价导致 $IG(x)=0$ 时，仍白白耗尽全部 Oracle 查询预算）**
- **影响等级**：**P0**（直接扭曲"样本效率"核心实验指标）
- **证据**：
  1. **Oracle 调用与异常漏计**（`eve3/system2_falsifier/cegis_loop.py:161-168`）：
     ```python
     # Query Oracle
     try:
         oracle_y = oracle_fn(best_x)
     except Exception:
         continue
     current_examples.append((best_x, oracle_y))
     probes_used.append((best_x, oracle_y))
     ```
     若 `oracle_fn(best_x)` 抛出异常，Oracle 已被调用但未计入 `probes_used`，且因 `best_x` 未加入 `current_examples`，下一轮 `novel_probes` 仍会选出同一个 `best_x` 重复调用直到耗尽轮数。此外 `CEGISResult` 未统计或暴露 `oracle_queries`、`z3_calls`、`llm_calls`。
  2. **零信息增益（$IG=0$）探针浪费全部 Oracle 预算**：
     - 在 `bayesian_prober.py:107-116` 中，即使所有候选探针的 $IG(x) = 0.0$，`score = 0.0 - 0.05 * 1.0 = -0.05 > -inf`，`select_best_probe` 依然返回一个毫无区分力的探针 `best_x`！
     - 在 `experiments/run_library_ablation.py` 的 `list_sum` 任务中，候选集包含 `(sum x)` 与 `(fold (lambda (acc item) (+ acc item)) 0 x)`。二者语义完全等价，所有探针 $IG(x)=0$，但 `CEGISLoop` 连续查询了 **8 次 Oracle**（耗尽 `max_falsification_rounds=8`），导致 `list_sum` 的 `probes=8`！
  3. **当前"样本效率"指标定义**：在 `experiments/run_full_ablation.py:109, 217` 与 `experiments/run_library_ablation.py:88, 127` 中，样本效率定义为 `len(res.probes_used)` 的均值（即成功返回值的 Oracle 探针数，不含 `initial_examples` 样例数）。

---

### H9 System 1 候选多样性与去重机制
- **审计问题**：`generator.py` 如何去重（字符串、AST、还是语义等价）？候选 $k$ 如何设定？温度/采样策略是什么？
- **结论**：**CONFIRMED（仅按字符串精确匹配去重，未做 AST $\alpha$-等价或语义等价去重；提示词硬编码生成 5 个候选而配置为 10/16；MLX 采样仅单次调用 `mlx_lm.generate`）**
- **影响等级**：**P1**（同义冗余候选污染 System 2 先验与停止条件）
- **证据**：
  1. **去重方式**：
     - `eve3/system1_proposer/sandbox.py:53`：`if matches_all and candidate not in valid_candidates:`，调用 `CandidateProgram.__eq__`（`eve3/models.py:126-129`）：
       ```python
       def __eq__(self, other: object) -> bool:
           if not isinstance(other, CandidateProgram):
               return False
           return self.code_str == other.code_str
       ```
     - `eve3/search/controller.py:57`：`if c.code_str not in seen_codes and len(proposals) < max_candidates:`。
     - 因此去重**完全基于字符串相等**（`code_str`），不仅无法去除 `(map (lambda (a) (+ a 1)) x)` 与 `(map (lambda (a) (inc a)) x)` 等语义等价程序，甚至无法去除 `(map (lambda (a) (+ a 1)) x)` 与 `(map (lambda (b) (+ b 1)) x)` 等 AST $\alpha$-等价程序。
  2. **候选数 $k$ 与温度/采样策略**（`eve3/config.py:15-16`, `eve3/system1_proposer/generator.py:43, 55, 104-112`）：
     - `EveConfig.max_hypotheses_per_round = 16`，`generate_hypotheses` 默认 `max_candidates = 10`，但 `build_prompt` 第 43 行硬编码写着 `"generate 5 candidate DSL programs"`！
     - `_generate_with_mlx` (`104-110`) 调用 `mlx_lm.generate(..., temp=self.config.generation_temperature, max_tokens=256)`（默认 `generation_temperature = 0.7`）。注意：新版 `mlx_lm.generate` 已移除 `temp` 关键字参数（改用 `sampler`），若安装新版 `mlx-lm` 调用会抛出 `TypeError` 并被 `generator.py:76` 的 `except Exception: pass` 静默吞掉！

---

### H10 LLM 真实贡献审计与消融实验
- **审计问题**：`generator` 里"heuristic synthesizer"和 LLM 的调用比例如何？在 benchmark 上若完全关闭 LLM，只用启发式或枚举，成功率差多少？（这是判断"神经部分是否有用"的关键实验，必须跑。）
- **结论**：**CONFIRMED（当前工作区与 CI 中 LLM 调用比例为 0%：100% 依赖硬编码模板与符号枚举器；关闭 LLM 后 benchmark 成功率差异为 0.0%）**
- **影响等级**：**P0**（阻塞"神经符号（Neurosymbolic）"核心声明的可信度：所有现有实验报告中的结果均在无 LLM 的纯符号/硬编码模板下产生）
- **证据**：
  1. **代码路径证据**（`eve3/search/controller.py:61-78` 与 `eve3/system1_proposer/generator.py:71-89`）：
     - 在 `SearchController.propose_candidates` 中，默认 `strategy="hybrid"` **首先调用 `SymbolicEnumerator`**（`controller.py:62-68`），然后才调用 `HypothesisGenerator.generate_hypotheses`（`controller.py:71-77`）。
     - 在 `HypothesisGenerator._generate_raw_proposals` 中，由于 `mlx` 与 `mlx_lm` 在 `pyproject.toml:25-27` 和 `requirements.txt:11-12` 中均被注释掉未安装，`_can_use_mlx()` 返回 `False`，100% 走 `_heuristic_synthesizer`（27 个硬编码 S-表达式模板，恰好包含 benchmark 的全部参考答案）。
  2. **对照实验输出**（在全部 13 个任务族 benchmark 上对比 `hybrid`、`neural_only`（实际回退到 `_heuristic_synthesizer`）、`symbolic_only`）：
     - 训练族（10 个任务）：关闭 LLM（仅用 `_heuristic_synthesizer` 或 `SymbolicEnumerator`）成功率为 **10/10 (100.0%)**，与默认配置相差 **0.0%**；
     - 留出族 `list_composition`（3 个任务）：`SymbolicEnumerator` 含 `(filter (lambda (a) (is_even a)) (map (lambda (a) (+ a 1)) x))` 等硬编码深度 3 模板，`_heuristic_synthesizer` 含 `(sum (filter (lambda (a) (is_even a)) x))`（1/3 任务），有无 LLM 成功率相差 **0.0%**。

---

### H11 沙箱可靠性与绕过漏洞（`sandbox.py` / `interpreter.py`）
- **审计问题**：`sandbox.py` 的超时、步数预算、异常处理是否可靠？能否被构造的程序（死循环、巨大输出、深递归）绕过？
- **结论**：**CONFIRMED（存在 3 个可验证的沙箱漏洞：① `ThreadPoolExecutor` 上下文管理器在退出时调用 `shutdown(wait=True)`，导致超时抛出前仍阻塞等待后台线程执行完毕；② 可通过 `fold` 重复平方/倍增拼接在 $<500$ 步内构造百万级元素列表或数万位大整数绕过 `step_budget=20000`；③ `ProgramSandbox` 从未传入 `max_depth`，且结晶算子因未注入 `DSLInterpreter.base_env` 在沙箱中 100% 报 `NameError` 被静默丢弃）**
- **影响等级**：**P0 / P1**（结晶算子在沙箱中 100% 报 `NameError` 直接导致 System 3 $\to$ System 1 闭环断裂，属 P0；超时阻塞与内存炸弹属 P1）
- **证据**：
  1. **漏洞 1：`ThreadPoolExecutor` 超时无法真正中断/返回**（`eve3/dsl/interpreter.py:207-214`）：
     ```python
     with ThreadPoolExecutor(max_workers=1) as executor:
         future = executor.submit(_execute_sync)
         try:
             return future.result(timeout=timeout_seconds)
         except FuturesTimeoutError:
             raise ExecutionTimeoutError(
                 f"Execution exceeded hard timeout budget of {timeout_seconds}s"
             )
     ```
     Python 标准库 `ThreadPoolExecutor.__exit__` 无条件执行 `executor.shutdown(wait=True)`。即使 `future.result(timeout=0.0001)` 触发 `FuturesTimeoutError`，离开 `with` 块时主线程仍会阻塞等待 `_execute_sync` 跑完！
  2. **漏洞 2：`fold` 倍增绕过 `step_budget` 制造巨型输出**（`scratch/audit_check.py` 实测）：
     ```text
     Fold repeated squaring: input len=14, step_budget=100 -> result bit_length=54427 bits in <100 steps!
     Fold memory bomb: input len=20, step_budget=500 -> output list length=1048576 in 7.4ms!
     ```
     程序 `(fold (lambda (acc item) (concat acc acc)) [1] x)` 在长度 20 的输入上仅消耗约 100 个 AST 步数（远低于默认 `step_budget=20000`），瞬间生成长度为 $2^{20} = 1,048,576$ 的列表；若输入长度为 30，仅消耗 150 步即可耗尽数 GB 内存触发 OOM。
  3. **漏洞 3：System 3 结晶算子在沙箱中 100% 因 `NameError` 被过滤**（`eve3/system1_proposer/sandbox.py:15, 36`）：
     `ProgramSandbox.__init__` 创建 `self.interpreter = DSLInterpreter()` 时未传入任何 `extra_primitives`（全仓 grep `extra_primitives` 仅出现在 `interpreter.py:174` 定义处，调用次数为 0）。当 `SearchController` 或 `HypothesisGenerator` 生成 `(map_add 1 x)` 时，`self.interpreter.run` 抛出 `NameError: Unknown primitive or function 'map_add'`，被 `sandbox.py:40` 的 `except Exception:` 捕获并静默判为 `matches_all = False`！

---

### H12 System 3 目标函数、动态模式挖掘崩溃与次模性检验
- **审计问题**：`value_compressor.py` 实际优化的是什么？是否与 README 中的公式一致（$w_i$ 的定义、$\gamma \cdot \text{Cost}$）？是否使用了贪心，是否声明了近似保证？用小规模穷举（$\le 12$ 个候选抽象）对比贪心解与最优解，经验检验"次模"是否成立（至少检验边际收益递减在你的实例中是否被违反）。
- **结论**：**CONFIRMED（存在 3 个关键问题：① 代码注释与文档声称 $\text{Benefit}_w(L) - \gamma |L|$，但实际代码计算的是 $\text{Benefit}_w(L) - \gamma \sum_{a \in L} \text{Cost}(a)$；② 动态 AST 模式挖掘 `_extract_generalized_subpatterns` 因 `patterns = []` 调 `.add()` 及未导入 `LambdaNode` 而在 100% 程序上崩溃，全靠 `except Exception: continue` 掩盖并退回 3 个硬编码种子模式；③ `compute_weighted_benefit` 按列表顺序依次做正则替换，导致目标函数甚至不是集合函数（依赖元素顺序）、违反单调性与次模性，贪心解严格劣于穷举最优解）**
- **影响等级**：**P0**（阻塞 System 3 理论声明与实验可信度）
- **证据**：
  1. **动态模式挖掘 100% 崩溃**（`eve3/system3_crystallizer/value_compressor.py:13, 110-115, 148-161`）：
     ```python
     # value_compressor.py:13 — 未导入 LambdaNode！
     from eve3.dsl.ast import ASTNode, ApplyNode, ConstNode, VarNode
     ...
     # value_compressor.py:150-160
     def _extract_generalized_subpatterns(self, node: ASTNode) -> Set[str]:
         patterns: Set[str] = []
         if node.depth >= 2:
             generalized = self._generalize_node(node)
             patterns.add(generalized.to_sexpr())  # AttributeError: 'list' object has no attribute 'add'
     ```
     同时第 159 行和第 173 行使用 `isinstance(node, LambdaNode)` 触发 `NameError`，全被第 114 行 `except Exception: continue` 吞掉！且 `apply_compression` (`37-64`) 仅用 `if/elif` 硬编码了 4 条正则表达式，任何其他模式收益恒为 `0`。
  2. **顺序依赖、非单调与贪心次优实测**（`eve3/system3_crystallizer/value_compressor.py:194-196` 及 `scratch/audit_check.py`）：
     ```python
     for ab in selected_library:
         current_code, savings = ab.apply_compression(current_code)
         total_savings += savings
     ```
     设候选抽象 $c_1 = \texttt{map\_add}$ (`cost=2`)，$c_2 = \texttt{rev\_map\_add}$ (`cost=1`)，程序集为 2 个 `(reverse (map (lambda (a) (+ a k)) x))`（权重 $0.95$）和 1 个 `(map (lambda (a) (+ a 3)) x)`（权重 $1.0$），$\gamma = 1.2$：
     - 若先应用 $c_1$，它将前两个程序改写为 `(reverse (c1_map_add k x))`，破坏了 $c_2$ 的外层正则匹配，导致 $c_2$ 的边际收益变为 $0$！
     - 实测输出（`scratch/audit_check.py`）：
       ```text
       f([c1])=12.00, f([c2])=10.00
       f([c1, c2])=12.00 vs f([c2, c1])=14.00
       Library ['c1_map_add']: Benefit=11.60, CostPenalty=2.40, NetObj=9.20
       Library ['c2_rev_map_add']: Benefit=9.50, CostPenalty=1.20, NetObj=8.30
       Library ['c1_map_add', 'c2_rev_map_add']: Benefit=11.60, CostPenalty=3.60, NetObj=8.00
       Library ['c2_rev_map_add', 'c1_map_add']: Benefit=13.50, CostPenalty=3.60, NetObj=9.90
       ```
       在第 1 步贪心选择 `c1_map_add`（净收益 $9.20 > 8.30$），第 2 步评估 `['c1_map_add', 'c2_rev_map_add']` 时净收益降至 $8.00 < 9.20$，贪心终止并输出 `['c1_map_add']`（净目标值 **$9.20$**），而穷举最优解 `['c2_rev_map_add', 'c1_map_add']` 的净目标值为 **$9.90$**！文档（`MATHEMATICS.md:121`）声称的 $(1-1/e)$ 近似保证不成立（且对于带线性成本惩罚的目标 $g(S) - \gamma c(S)$，即使 $g$ 单调次模，无约束差函数也可能取负值，不具备标准 $(1-1/e)$ 保证）。

---

### H13 权重正反馈锁定（Positive Feedback Lock-in）
- **审计问题**：$w_i$ 含 $\ln(1+\text{ReuseCount})$，检验是否存在正反馈锁定：模拟早期一个偶然抽象被多次复用后，是否压制了后来更优的抽象。
- **结论**：**CONFIRMED（`calculate_program_weight` 对 `reuse_count` 无饱和上限或时间衰减，且 `library.py:132, 215` 按 `reuse_count DESC` 排序，早期偶然高频程序/算子会显著压制后续结构压缩率更高的新抽象）**
- **影响等级**：**P1**（影响长期库学习质量）
- **证据**：
  - `eve3/system3_crystallizer/value_compressor.py:86-94`：
    ```python
    def calculate_program_weight(self, prog_meta: Dict[str, Any]) -> float:
        """Compute value weight: w_i = |{task_family}| * (1 + log(1 + reuse_count))."""
        reuse = prog_meta.get("reuse_count", 0)
        ...
        return task_diversity * (1.0 + math.log(1.0 + reuse))
    ```
  - 模拟输出（`scratch/audit_check.py`）：早期抽象 $A_{\text{early}}$ 仅节省 4 个 AST 节点，但因早期复用 `reuse_count=5/20/100`，其加权收益从 $4.00$ 膨胀至 **$11.17 / 16.18 / 22.46$**，完全压制了单次节省 6 个 AST 节点的新抽象 $A_{\text{better}}$（加权收益 $6.00$）：
    ```text
    reuse_early=  0 -> w_early=1.000 (4*w_e=4.00) vs w_better=1.000 (6*w_b=6.00)
    reuse_early=  5 -> w_early=2.792 (4*w_e=11.17) vs w_better=1.000 (6*w_b=6.00)
    reuse_early= 20 -> w_early=4.045 (4*w_e=16.18) vs w_better=1.000 (6*w_b=6.00)
    reuse_early=100 -> w_early=5.615 (4*w_e=22.46) vs w_better=1.000 (6*w_b=6.00)
    ```

---

### H14 库增长、淘汰回滚与提示长度膨胀/模板挤占
- **审计问题**：晋升回 System 1 提示/原语的抽象有无数量上限、淘汰、版本或回滚？提示长度随库增长的曲线是什么？
- **结论**：**CONFIRMED（`KnowledgeLibrary.get_crystallized_operators()` 无数量上限；虽然 Phase 8 `eve3/memory/tiers.py` 实现了带版本快照回滚的 `SemanticMemory`，但 `SearchController` 与 `CEGISLoop` 根本没有接入 `SemanticMemory`！更严重的是，在 `generator.py:168-180` 中，当库中有 $\ge 8$ 个二元算子时，它们通过 `templates.insert(0, ...)` 将原有的 27 个基础启发式模板 100% 挤出前 30 名截断线！）**
- **影响等级**：**P0 / P1**（算子数 $\ge 8$ 时直接挤垮 System 1 基础模板池属 P0；提示词线性无界增长属 P1）
- **证据**：
  1. **代码片段**（`eve3/system1_proposer/generator.py:161-181`）：
     ```python
     if crystallized_operators:
         for op in crystallized_operators:
             ...
             elif arity == 2:
                 for k in (1, 2, 0, -1):
                     templates.insert(0, f"({op_name} {k} x)")
     ...
     for t in templates:
         candidates.append(t)
         if len(candidates) >= max_candidates * 3:
             break
     ```
  2. **提示长度与基础模板挤占实测曲线**（`scratch/audit_check.py`，`max_candidates=10`）：
     ```text
     n_ops=  0 -> prompt_chars=  496, raw_cands_count=27, base_templates_displaced=0/27
     n_ops=  5 -> prompt_chars=  636, raw_cands_count=30, base_templates_displaced=20/30
     n_ops= 10 -> prompt_chars=  776, raw_cands_count=30, base_templates_displaced=30/30
     n_ops= 25 -> prompt_chars= 1211, raw_cands_count=30, base_templates_displaced=30/30
     n_ops= 50 -> prompt_chars= 1936, raw_cands_count=30, base_templates_displaced=30/30
     n_ops=100 -> prompt_chars= 3386, raw_cands_count=30, base_templates_displaced=30/30
     ```
     提示长度呈严格线性无界增长 $\text{len}(\text{prompt}) = 496 + 28.9 \times N_{\text{ops}}$；且当 $N_{\text{ops}} \ge 8$ 时，`raw_cands` 的 30 个名额 **100% 被结晶算子占满**，原有基础模板全军覆没！

---

### H15 库学习的任务族切分与数据泄漏检查
- **审计问题**：library 的学习任务与评测任务是否按 task family 严格切分？检查 `run_library_ablation.py` 的切分逻辑。
- **结论**：**CONFIRMED（`run_library_ablation.py` 与 `run_full_ablation.py` 均未按 task family 严格切分训练与评测集，且手动硬编码注入了目标抽象 `map_add`）**
- **影响等级**：**P1**（违反按任务族隔离评测泛化能力的实验设计原则）
- **证据**：
  1. `experiments/run_library_ablation.py:27-31, 55-63`：
     - `dev_train.json` 包含 `list_increment_all` (**`list_mapping`**) 和 `filter_evens` (**`list_filtering`**)；
     - `dev_eval.json` 包含 `list_double_all` (**`list_mapping`**) 和 `list_sum` (`list_reduction`)；
     - `held_out_test.json`（在 `run_full_ablation.py:46-49` 中与 `dev_eval.json` 合并评测）包含 `filter_greater_than_two` (**`list_filtering`**) 和 `filter_positive` (**`list_filtering`**)。
     - 因此训练集与评测集共享 `list_mapping` 和 `list_filtering` 任务族，**并非按 task family 严格切分**！
  2. 此外，`run_library_ablation.py:55-63` 和 `run_full_ablation.py:69-77` 并不是调用 `ValueCompressor` 从训练任务中自动挖掘抽象，而是**手动硬编码调用 `library.record_learned_abstraction(LearnedAbstraction(name="map_add", ...))`**！

---

### H16 Discovery Tree 反事实回放的支撑集（Support）检查
- **审计问题**：`tree.py` 的反事实评估是否检查"新策略是否走出了已记录的树支撑范围"？走出时如何处理（静默回退、估计、还是标记不可评估）？
- **结论**：**CONFIRMED（完全未检查策略是否走出已记录树的支撑范围：模拟器只允许策略在已记录的树节点上打分排序，若树中未记录新策略倾向的动作或未包含 `verify` 节点，模拟器静默遍历完现有节点后返回 `found_verified: False` 及累计成本，不标记"不可评估"也不报告覆盖率）**
- **影响等级**：**P1**（导致离线策略回放将"超出树支撑范围"静默混淆为"策略失败"或给出退化的同质化评分，如 `run_policy_evolution.py` 中 3 个不同策略得分完全相同均为 `2.20`）
- **证据**：
  - `eve3/discovery/tree.py:209-229`：
    ```python
    while frontier:
        # Policy chooses highest priority node among CURRENTLY REACHABLE frontier nodes
        candidates = [self.tree.nodes[nid] for nid in frontier]
        best_node = max(candidates, key=policy_priority_fn)
        frontier.remove(best_node.node_id)
        explored.add(best_node.node_id)
        ...
    ```
  - 实测证据：在 `experiments/run_policy_evolution.py` 中，由于记录的树是一条单链（每个父节点只有一个子节点，每步 `len(frontier) == 1`），无论传入什么策略，`max(candidates, key=policy_priority_fn)` 别无选择只能走唯一记录的节点，导致 `conservative`、`balanced`、`verification_first` 三个策略的回放结果恒为 `simulated_cost=2.20, steps=4`！

---

### H17 策略版本化与 `regression_gate.py` 预注册防篡改检查
- **审计问题**：`policy.py` 的版本化、`regression_gate.py` 的"预注册"究竟预注册了什么（阈值、指标、数据切分）？能否被事后修改？
- **结论**：**CONFIRMED（预注册了 4 个标量阈值和 `docs/PREREGISTRATION.md` 文档，但 `ExplorationPolicy` 与 `RegressionGateConfig` 均为普通可变 `@dataclass`（未设 `frozen=True`），无哈希校验锁，且 `evaluate_metrics` 接收外部直接传入的字典分数，可在运行时任意事后修改）**
- **影响等级**：**P2**（工程质量与实验审计严肃性）
- **证据**：
  1. `eve3/plasticity/regression_gate.py:17-24`：
     ```python
     @dataclass
     class RegressionGateConfig:
         """Configuration parameters for the regression gate."""
         max_family_regression_pct: float = 2.0     # Max allowable drop per family (%)
         max_general_drop_pct: float = 3.0          # Max allowable drop on general probe (%)
         max_false_verification_rate: float = 0.0   # Strict zero false verification
         min_overall_accuracy: float = 0.80         # Minimum overall accuracy across families
     ```
  2. 并且看 `eve3/plasticity/consolidator.py:277-290`：当 `eval_fn is None`（默认情况，如 `autonomous_engine.py:219` 调用时），`run_sleep_cycle` 直接硬编码伪造分数通过门禁：
     ```python
     if eval_fn is not None:
         cand_scores, gen_score, false_verif_rate = eval_fn()
     else:
         cand_scores = {target_family: 1.0}
         gen_score = 1.0
         false_verif_rate = 0.0
     historical_scores = {target_family: 0.95}
     ```
  3. 实测输出（`scratch/audit_check.py`）：
     ```text
     Gate config before mutation: max_family_regression_pct=2.0
     Gate config after runtime mutation: max_family_regression_pct=99.0 (mutable dataclass!)
     ```

---

### H18 `adapter_bank.py` 与 `controller.py` 真实可运行路径审计
- **审计问题**：`adapter_bank.py` 与 `controller.py`：是否已经有可运行的路径，还是只有骨架？用测试或最小脚本验证，不要凭文件名推断。
- **结论**：**CONFIRMED（二者均有可运行的 Python 代码路径并通过各自单元测试，但存在关键断联：`AdapterBank` 仅在 SQLite 中管理元数据字典，从未加载或切换任何真实 LoRA 权重，也未与 `SearchController` / `HypothesisGenerator` 连接；而 `SearchController` 的 `library_only` 路径因 H11 沙箱未注册结晶算子而永远返回空列表 `[]`）**
- **影响等级**：**P1**（模块级可运行，但端到端神经适配器路由与符号库执行未真正闭环）
- **证据**：
  1. `eve3/plasticity/adapter_bank.py:146-168`：`create()`、`commit()`、`snapshot()`、`rollback()`、`route()` 均基于内存字典和 SQLite 表 `adapters` / `snapshots` 完整实现并可运行（见 `tests/test_adapter_bank_rollback.py`），但 `weights_path` 默认为 `None`，全仓无任何代码讀取 `AdapterBank` 的路由结果去驱动 `mlx_lm`。
  2. `eve3/search/controller.py:33-93`：`propose_candidates` 可运行，但当 `strategy="library_only"` 时（`controller.py:80-91`），生成的 `({op_name} {k} x)` 在 `self.sandbox.filter_valid_candidates` 中因 `NameError` 全部被过滤，导致 `library_only` 恒返回 `[]`。

---

### 横向检查（Tests 与 CI 审计）

#### 1. `tests/` 横向检查结果
对 `tests/` 下全部 29 个测试文件（80 个测试用例）逐一排查：
- **弱断言 / 掩盖性断言的测试**：
  - `tests/test_smt_matrix.py:31-37`（`test_unsupported_primitive_graceful_fallback`）：对 `(+ x 1)` 和 `(+ x 2)` 调用 `find_distinguishing_input`，仅断言 `self.assertIn(probe.source, ("smt_symbolic", "heuristic_boundary"))`。如 H5 所证，此处 Z3 实际上因 `m[x].as_long()` 抛出 `AttributeError` 崩溃并回退到了 `heuristic_boundary`，宽泛的 `assertIn` 掩盖了 Z3 求解器崩溃！
  - `tests/test_benchmark_evaluation.py:66-102`（`test_bayesian_active_prober_vs_random_baseline_sample_efficiency`）：名为"对比主动探针与随机基线的样本效率"，但第 88–98 行算出的 `random_probes_count` **根本没有在任何断言中被使用**！最后第 101 行仅断言 `self.assertLessEqual(active_probes_count, config.max_falsification_rounds)`（即 $\le 10$，恒真断言）！
  - `tests/test_prober.py:53-55`（`test_posterior_update_and_collapse_prevention`）：测试塌缩保护时仅断言 `self.assertTrue(math.isclose(sum(collapsed_beliefs), 1.0))`，未检查塌缩分支是否真正触发（实际上因 $\text{total}=10^{-6}>10^{-12}$ 根本未触发）。
- **使用固定随机种子且只有一个种子的测试**：
  - `tests/test_autonomous_agi_loop.py:19`：仅使用 `seed=42`；
  - `tests/test_benchmark_evaluation.py:88`：仅使用 `random.seed(42)`；
  - `tests/test_consolidator.py:102`：仅使用 `random_seed=42`；
  - `tests/test_curriculum_filter.py:25`：仅使用 `seed=123`；
  - `tests/test_safety_and_envs.py:114`：仅使用 `seed=123`；
  - `tests/test_full_ablation.py:11`：调用 `run_full_ablation()` 默认仅跑单种子 `seeds=[42]`（尽管理论预注册协议 `docs/PREREGISTRATION.md:67` 要求必须跑 5 个种子 `[42, 100, 2024, 777, 999]`）。
- **被 skip 的测试**：
  - 全仓 **0 个** skip 测试。当 Z3 或 MLX 不可用时，没有任何测试使用 `skipTest` 标注原因。

#### 2. CI (`.github/workflows/ci.yml`) 审计
- **证据**（`.github/workflows/ci.yml:10-38`）：
  ```yaml
  runs-on: ubuntu-latest
  strategy:
    matrix:
      python-version: ["3.10", "3.11", "3.12"]
  ...
  - name: Install dependencies
    run: |
      python -m pip install --upgrade pip
      pip install -e .
      pip install z3-solver hypothesis pytest
  ```
- **结论**：CI 运行在 Linux (`ubuntu-latest`) 上，仅安装 `z3-solver hypothesis pytest`，**完全未安装 `mlx` 或 `mlx-lm`**（Apple Silicon 专属库也无法在 `ubuntu-latest` 上运行）。因此 CI 中所有测试 100% 走无 MLX 的启发式/枚举回退路径，且没有任何测试报告 `skipped`。

---

## 汇总对照表：README / 文档声明 vs 代码现状

| 声明主题 | README / 文档声明 | 代码现状（证据路径:行号） | 审计状态 | 严重度 |
| :--- | :--- | :--- | :---: | :---: |
| **确定性反例更新与 Laplace 平滑** | `MATHEMATICS.md:76`: $P_i(x^*) \neq y_{\text{obs}}$ 时 $b_i \leftarrow 0$；平滑仅防除零崩溃 | `bayesian_prober.py:135` 赋似然 $\epsilon=10^{-6}$；当先验悬殊或多步更新时，**已被证伪的程序仍可保持或重回 top-1** | **CONFIRMED 缺陷 (H3)** | **P0** |
| **假设空间塌缩保护** | `MATHEMATICS.md:84`: $\sum b_i \mathcal{L}_i < 10^{-12}$ 时触发均匀回退并调用 System 1 扩展深度重提议 | `bayesian_prober.py:143`: 全错时 $\text{total}=10^{-6} > 10^{-12}$，塌缩分支永不触发；后验保持不变，无候选被剪枝，直接返回已证伪的 top-1 | **CONFIRMED 缺陷 (H4)** | **P0** |
| **Z3 SMT 支持矩阵与求解** | `README.md:85`, `smt_distinguisher.py:60-84`: 支持算术、比较及有界列表 `head/map/filter/reverse/lambda` | `_ast_to_z3_int` 缺 `eq/gt/lt`，`_ast_to_z3_seq` **仅实现 `length/tail`**，无高阶函数展开；且 `(+ x 1)` vs `(+ x 2)` 因 `m[x]=None` 抛 `AttributeError` 静默退回静态探针 | **CONFIRMED 缺陷 (H5)** | **P0** |
| **System 3 算子晋升回 System 1 执行** | `README.md:67`: 结晶算子晋升回 System 1 提示与原语并在后续任务中复用 | `sandbox.py:15` 与 `models.py:89` 从未向 `DSLInterpreter` 注入结晶算子，所有 `(op x)` 在沙箱中抛 `NameError` 被 100% 过滤丢弃；且 $\ge 8$ 个算子时挤掉全部基础模板 | **CONFIRMED 缺陷 (H11/H14)** | **P0** |
| **System 3 动态模式挖掘与次模保证** | `README.md:92-94`, `MATHEMATICS.md:121`: 动态挖掘公共子表达式，次模性保证贪心 $(1-1/e)$ 近似比 | `value_compressor.py:150,159` 因 `list.add` 与未导入 `LambdaNode` **100% 崩溃**，仅靠 `except` 返回 3 个硬编码模式；顺序替换导致非单调、非次模，贪心解次优 | **CONFIRMED 缺陷 (H12)** | **P0** |
| **CEGIS 状态与 Oracle 预算** | `README.md:154`: 诚实状态；样本效率显著优于基线 | `CANDIDATE_FOUND` / `FORMALLY_VERIFIED` 未实现；$IG=0$ 时仍盲目消耗全部 Oracle 轮数；轮数耗尽未收敛仍可判 `HELD_OUT_TESTS_PASSED`；无统一预算计数器 | **CONFIRMED 缺陷 (H7/H8)** | **P0** |
| **System 1 本地 LLM 贡献** | `README.md:50, 79`: 基于 `mlx-lm` `Qwen2.5-Coder-3B-Instruct` 生成直觉假设 | `mlx-lm` 未安装，且 `mlx_lm.generate(..., temp=...)` 参数已过时；`SearchController` 优先跑符号枚举，LLM 在所有实验中调用 0 次（贡献 0%） | **CONFIRMED 缺陷 (H10)** | **P0** |
| **System 1 先验与去重** | `MATHEMATICS.md:20`: MDL 先验 | `bayesian_prober.py:39` 仅支持固定 MDL 先验（不可配均匀/LLM）；`sandbox.py:53` 仅按字符串去重，语义等价候选扭曲先验与 IG | **CONFIRMED 缺陷 (H1/H2/H9)** | **P1** |
| **沙箱超时与资源隔离** | `ARCHITECTURE.md:52`: 墙钟超时、步数限制与递归上限 | `interpreter.py:207` `ThreadPoolExecutor` 退出时阻塞等待线程结束；`fold` 重复平方/倍增可在 100 步内产生百万元素列表；`max_ast_depth` 未接入沙箱 | **CONFIRMED 缺陷 (H11)** | **P1** |
| **System 3 权重锁定与训练/评测切分** | `PREREGISTRATION.md:39-56`: 按任务族严格隔离训练与评测 | `w_i` 无饱和上限导致早期复用锁定；`run_library_ablation.py` 跨 `dev_train`/`dev_eval` 共享 `list_mapping` 族且手动硬编码注入 `map_add` | **CONFIRMED 缺陷 (H13/H15)** | **P1** |
| **Discovery Tree 反事实回放** | `README.md:74, 104`: 零边际成本评估替代探索策略 | `tree.py:209` 不检查新策略是否超出已记录树支撑集（Out-of-Support），单链树上所有策略得分恒同 | **CONFIRMED 缺陷 (H16)** | **P1** |
| **AdapterBank 与预注册门禁** | `README.md:116-117`: LoRA 按族隔离，门禁严格阻断退化 | `AdapterBank` 仅存 SQLite 元数据未接入推理；`RegressionGateConfig` 可运行时篡改，且 `consolidator.py:280` 默认硬编码 `1.0` 分数过门禁 | **CONFIRMED 缺陷 (H17/H18)** | **P2** |
