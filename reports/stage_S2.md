# EVE-3 阶段报告：Stage S2 System 2 数学与流程正确性实证验收

> **报告日期**：2026-11-10  
> **运行环境**：Windows, Python 3.12.8 (x64), z3-solver 5.3.3.0, pytest 9.2.0, hypothesis 6.170.15, pydantic 2.14.3  
> **报告原则**：严格基于实测数据与代码实现，拒绝推测；全量测试遵循 TDD（先红后绿）、棘轮不退、AST 静态零宽泛异常。

---

## 1. 阶段概述与 Commit 记录

Stage S2 聚焦于修复 System 2（Bayesian Active Falsifier & SMT Distinguisher）在前期审计中确认的核心数学缺陷与流程空桩（H3, H4, H5, H2），并引入了真实的随机探针（Random Probes）对照臂以解除基线对照的 `INVALID_PENDING_RANDOM_CONTROL` 状态。

本阶段全部交付均通过独立的原子 commit 落地，各 commit 记录如下：

| Commit | 修复范围 / 目标 | 关联假设与证据行 | 关键成果 |
| :--- | :--- | :--- | :--- |
| `9438d69` | **S2-H3**：噪声模型与确定性后验归零 | H3 (`audit.md:156-191`) | 引入 `noise_model: "deterministic" \| "noisy(eps)"`；确定性模式下反例证伪候选后验严格置 0 并打标 `falsified=True`；`test_h3` 转绿 |
| `f8d6cb6` | **S2-H4**：假设空间塌缩保护与重提议闭环 | H4 (`audit.md:193-210`) | 修复空桩；全候选证伪时触发主动重提议（以历史反例为约束），上限 `max_repropose_rounds=3` 耗尽后明确返回 `COLLAPSED`；`test_h4` 转绿 |
| `184802f` | **S2-H5**：SMT 形式化区分器有界展开与健壮化 | H5 (`audit.md:213-232`) | 实现了列表原语（`map`, `reverse`, `tail`, `head`, `sum`, `length`）的有界符号展开与 Z3 模型求解；精确累加 `z3_calls`；`test_h5` 转绿 |
| `e87715b` | **S2-H2**：互信息闭式计算手算单测 | H2 (`audit.md:126-154`) | 严格对照 $IG(x) = H(b) - \sum_v q_v H(b \mid G_v)$ 实现；手算 3 候选、2/3 等价分区及非均匀先验，实测与代码误差 $< 10^{-6}$ |
| `3b4f610` | **S2-Control**：随机探针（Random Probes）对照臂 | H2, S2.5 (`audit.md:88-102`) | `cegis_loop` 增加 `probe_strategy: "bayesian_ig" \| "random" \| "none"`；实现真实的无 IG 随机探针采样对照臂 |

---

## 2. H3 噪声模型与确定性后验归零（Deterministic Falsification）

### 2.1 问题机理与修复前状态
- **缺陷**：此前 `BayesianProber.update_beliefs` 对所有任务无差别施加 Laplace 平滑（`likelihood = smoothing_epsilon = 1e-6`），导致被反例明确证伪的确定性程序后验仍为正值，在 MDL 先验不平衡或多步探针后可能重新被抬入 top-1 误判为正确程序。
- **修复前失败输出**：
  ```text
  AssertionError: 0.001994015956119673 != 0.0 : Falsified program posterior should be 0.0, but got 0.001994015956119673 (remains top-1!)
  ```

### 2.2 修复方案与代码落地
1. 在 `EveConfig` 与 `BayesianProber` 中增加 `noise_model: str = "deterministic"`（支持 `"deterministic"` 与 `"noisy(eps)"` 格式）。
2. 在确定性模式下：
   - 当 $P_i(x) \neq y_{\text{obs}}$ 或抛出执行异常时，$\mathcal{L}(y_{\text{obs}} \mid P_i, x) = 0.0$，标记 `P_i.falsified = True`，`status = CandidateStatus.REJECTED`；
   - Laplace 平滑仅在显式声明 `"noisy(eps)"` 时生效；
   - 若全部候选均被证伪（$\sum b_i l_i \le 10^{-12}$），后验严格返回全零分布 `[0.0] * N`，绝不伪造均匀分布。
3. 测试验收：`tests/test_audit_p0_regressions.py::test_h3_laplace_smoothing_must_not_promote_falsified_program` 移除 `xfail` 并正常 PASS；新增 `tests/test_stage_s2_bayesian.py` 覆盖 3 项细分用例。

---

## 3. H4 假设空间塌缩保护与主动重提议（Active Re-proposal）

### 3.1 问题机理与修复前状态
- **缺陷**：此前 CEGIS 循环在面对"真程序不在初始候选集"的任务时，当候选全部被反例证伪，由于 Laplace 平滑未清零，循环未触发剪枝，耗尽轮数后在 `_finalize_result` 中直接交付 `verified_program=candidate`（将已知错误程序标记为交付成果）。
- **修复前失败输出**：
  ```text
  AssertionError: <VerificationStatus.HELD_OUT_TESTS_PASSED> != <VerificationStatus.COLLAPSED> : Expected status COLLAPSED when candidates fail
  ```

### 3.2 修复方案与代码落地
1. 真实闭环重提议机制：
   - 在 `cegis_loop.py` 中，当 `survivors` 过滤后为空时（全被证伪），递增 `repropose_count`；
   - 携带历史累积的反例集合 `current_examples = [ex_0, ex_1, ..., probe_k]` 作为硬约束，调用 `search_controller.propose_candidates` 重新提议；
   - 若新候选成功生成，重新初始化信念继续探针辨识；
   - 若重提议无法生成有效候选，或重提议轮数达到上限 `max_repropose_rounds=3`，循环坚决终止并返回 `VerificationStatus.COLLAPSED`，`verified_program=None`。
2. 铁律保护：在 `_finalize_result` 中，若留出测试未全部通过（`is_verified == False`），`verified_program` 严格置为 `None`，杜绝交付任何已知未验证/错误程序。
3. 测试验收：`test_h4_hypothesis_collapse_must_report_collapsed_when_all_falsified` 移除 `xfail` 并正常 PASS；新增 `tests/test_stage_s2_collapse.py` 验证重提议成功恢复与重提议耗尽塌缩。

---

## 4. H5 SMT 形式化区分器有界展开与健壮化

### 4.1 问题机理与修复前状态
- **缺陷**：此前 `SMTDistinguisher._ast_to_z3_seq` 仅编码了 `length` 与 `tail`，对 `map`、`reverse`、`head` 等列表高阶原语完全无 SMT 求解支持，全部静默回退至启发式边界测试（`heuristic_boundary`），导致求解器调用计数 `z3_calls == 0`。
- **修复前失败输出**：
  ```text
  AssertionError: 'heuristic_boundary' != 'smt_symbolic'
  - heuristic_boundary
  + smt_symbolic
   : Expected probe from Z3 SMT symbolic solve, got heuristic_boundary
  ```

### 4.2 修复方案与代码落地
1. 实现了基于有界长度展开（Bounded Unrolling）的符号解释器 `_eval_ast_bounded(ast_node, env, z3)`：
   - 对长度 $k \in \{1, 2, 3, 0\}$ 构造符号输入向量 $[x_{k,0}, x_{k,1}, \dots, x_{k,k-1}]$；
   - 支持对 `map`（符号展开 lambda 表达式应用）、`reverse`、`tail`、`head`、`length`、`sum` 以及代数运算（`+`, `-`, `*`, `inc`, `dec`, `neg`, `eq`, `gt`, `lt`）的完全符号化求值；
   - 列表输出间施加符号异或约束 `z3.Or([e1 != e2 for e1, e2 in zip(expr1, expr2)])`，调用 Z3 求解模型；
   - 提取模型解并通过解释器求值校验，确保输出输入确实区分了两候选。
2. 健壮遥测：正确记录 `diagnostics.record_z3_call()`, `record_z3_timeout()`, `record_z3_fallback()`。
3. 测试验收：`test_h5_z3_distinguisher_must_symbolically_differentiate_map_programs` 移除 `xfail` 并正常 PASS（实测输出 `<Probe [0] (smt_symbolic, bounded_support)> z3_calls: 1`）。

---

## 5. H2 互信息闭式计算手算单测

对照 `docs/MATHEMATICS.md` 公式：
$$\text{IG}(x) = H(b) - \sum_{v} q_v H(b \mid G_v(x))$$

在 `tests/test_stage_s2_mathematics.py` 中实现了严格的手算数值单测：
- **均匀先验两分区（探针 $x=1$）**：$P_1(1)=2, P_2(1)=3, P_3(1)=2$，$q_2=2/3, q_3=1/3$。
  - 手算理论值：$\text{IG}(1) = \log_2 3 - \frac{2}{3} = \mathbf{0.91829583}$ bits。
  - 代码实测值：$0.91829583$ bits（误差 $< 10^{-8}$）。
- **均匀先验三分区（探针 $x=0$）**：$P_1(0)=1, P_2(0)=2, P_3(0)=0$。
  - 手算理论值：$\text{IG}(0) = \log_2 3 = \mathbf{1.58496250}$ bits。
  - 代码实测值：$1.58496250$ bits（误差 $< 10^{-8}$）。
- **非均匀先验**：$b = [0.6, 0.3, 0.1]$，$q_2 = 0.7, q_3 = 0.3$。
  - 手算理论值：$\text{IG}(1) = \mathbf{0.88129090}$ bits。
  - 代码实测值：$0.88129090$ bits（误差 $< 10^{-8}$）。
- **$q_v$ 概率质量核验**：确认 $q_v$ 严格为输出等价类中候选程序的后验质量求和，而非简单的样本计数算术平均。

---

## 6. 随机探针（Random Probes）对照臂实测对比

在 `EveConfig` 中引入 `probe_strategy: "bayesian_ig" | "random" | "none"`：
- **`none` (Baseline_A)**：不使用主动探针，直接基于初始样例的最高后验程序交付；
- **`random` (Baseline_Random)**：在相同探针域内随机选择有效探针，不进行互信息计算；
- **`bayesian_ig` (Baseline_B)**：依据信息增益最大化与代价惩罚挑选最优探针。

在 `tests/test_stage_s2_random_probes.py` 中完成了三者的横向对比，证实了随机对照臂机制的完整接入，正式解除了前期评测表中的 `INVALID_PENDING_RANDOM_CONTROL` 状态。

---

## 7. 全量回归测试与代码库卫生核验

```text
============================= test session starts =============================
platform win32 -- Python 3.12.8, pytest-9.2.0, pluggy-1.7.0
collected 121 items

118 passed, 1 skipped, 2 xfailed in 10.12s
===============================================================================
```

- **P0 回归项转绿**：
  - `test_h3_laplace_smoothing_must_not_promote_falsified_program`: **PASS**
  - `test_h4_hypothesis_collapse_must_report_collapsed_when_all_falsified`: **PASS**
  - `test_h5_z3_distinguisher_must_symbolically_differentiate_map_programs`: **PASS**
- **剩余 xfail**：仅存 2 项（`test_h11` 算子未注册 与 `test_h12` 模式挖掘），严格按路线图规划留待 **Stage S4（System 3 库学习真实性）** 修复。
- **AST 静态检查**：`test_no_bare_except_exception_in_eve3_codebase` 全量扫描 `eve3/`、`experiments/`、`scripts/`，宽泛异常捕获恒为 0。
- **诊断棘轮约束**：`test_swallowed_errors_ratchet_only_decreases` 保持零被吞异常，完全满足只降不升约束。

---

## 8. 结论与暂停等待

Stage S2 的全部数学与流程缺陷已彻底修复并通过严密实证检验。

根据跨 Agent 交接协议铁律 7：**完成阶段报告后必须立即停下等待用户确认，严禁擅自跨阶段进入下一任务**。
当前代码库已处于绝对干净、绿灯、可验证的状态，等待用户确认后方可开启 Stage S3。
