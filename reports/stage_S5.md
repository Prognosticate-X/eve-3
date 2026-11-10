# EVE-3 阶段报告：Stage S5 策略更新与迁移真实性（P1）实证验收

> **报告日期**：2026-11-10  
> **运行环境**：Windows, Python 3.12.8 (x64), z3-solver 5.3.3.0, pytest 9.2.0, hypothesis 6.170.15, pydantic 2.14.3  
> **报告原则**：严格基于实测数据与代码实现，拒绝推测；全量测试遵循 TDD（先红后绿）、原子 commit、棘轮只降不升、AST 静态零宽泛异常。

---

## 1. 阶段概述与 Commit 记录

Stage S5 聚焦于策略更新真实性、反事实回放树重要性采样无偏修正、预注册门禁防篡改以及持续学习真实前向迁移闭环（H15, H16, H17, H18）：

1. **反事实回放树支撑集（Support Coverage）与重要性采样（H16）**：
   - 彻底修复了 `ReplaySimulator` 对策略越界未加检查的缺陷，引入支撑度覆盖率（`support_coverage`）与有效样本量（ESS）度量；
   - 当策略偏好的动作在树中缺失或树无验证解时，明确报告 `evaluatable: False` 与 `status: "out_of_support"`，杜绝将数据缺失混淆为策略失败；
   - 在历史探索树中引入真实的分叉决策，消除此前单链树导致不同策略得分全同（2.20）的退化现象。
2. **预注册门禁防篡改与不可变配置（H17）**：
   - 将 `RegressionGateConfig` 设为严格不可变（`frozen=True`），添加基于 SHA-256 的预注册阈值防篡改指纹 `compute_preregistration_hash()`；
   - 根治 `Consolidator.run_sleep_cycle` 在默认无 `eval_fn` 时硬编码伪造 `1.0` 通过门禁的漏洞，改为基于探索树真实统计经验通过率，拒绝失败树进入适配器库。
3. **持续学习与跨任务库算子组合（H15 / H18）**：
   - 将 `KnowledgeLibrary` 真实接入持续学习流水线与 `CEGISLoop`；
   - 在 `SearchController._add_library_candidates` 中实现宏算子与基础归约/结构原语的复合候选提议（如 `(sum (op_evens_only x))` 与 `(tail (op_reverse x))`）；
   - 在严格非泄漏的 `proposer_mode="generic_enumeration"` 模式下，真实验证了持续学习在留出集 `list_composition` 上的正向迁移（FWT Delta = **+33.33%** $\ge 10.0\%$，后向遗忘 BWT = **0.00%** $\le 2.0\%$）。

本阶段全部交付均通过独立的原子 commit 落地，各 commit 记录如下：

| Commit | 修复范围 / 目标 | 关联假设与证据行 | 关键成果 |
| :--- | :--- | :--- | :--- |
| `37feaee` | **S5-H16**：反事实回放树支撑度与重要性采样 | H16 (`audit.md:515-532`) | 引入 `support_coverage`、`is_weights`、ESS 与 `status="out_of_support"`；分叉决策树实现差异化策略排序；`tests/test_stage_s5_tree_support.py` 全绿 |
| `80baae0` | **S5-H17**：预注册门禁不可变与防篡改 | H17 (`audit.md:534-565`) | `RegressionGateConfig` 设为 `frozen=True` 并引入 SHA-256 校验；`Consolidator` 统计真实经验拒绝失败树；`tests/test_stage_s5_gate_tamper_resistance.py` 全绿 |
| `123f117` | **S5-H15/H18**：持续学习知识库注入与复合前向迁移 | H15, H18 (`audit.md:501-512, 567-575`) | `SearchController` 引入宏算子复合生成；`run_continual_learning.py` 接入真实库并在 `generic_enumeration` 下达标 FWT +33.33%；`tests/test_stage_s5_continual_learning.py` 全绿 |

---

## 2. H16 反事实回放树支撑集（Support Coverage）与重要性采样修复

### 2.1 问题机理与修复前状态
- **核心缺陷**：
  此前 `ReplaySimulator.evaluate_policy_sample_efficiency` 在树搜索中盲目假设策略总能在当前前沿节点中做出合规选择。当传入树只记录了一条单一操作路径（如 `run_policy_evolution.py` 中的线性单链）时，前沿候选数恒为 1，任意策略无论设置何种权重都只能被迫选择唯一记录的动作，导致所有候选策略评分为一模一样的 `simulated_cost=2.20, steps=4`。
  更为严重的是，当待评策略偏好的动作在树中根本未被探索，或树本身不包含验证节点时，模拟器静默跑完现有节点返回 `found_verified: False`，误导上层优化算法将“探索数据缺乏支撑（Out-of-Support）”错误判定为“策略劣质”。
- **修复前状态**：
  - 缺乏 `evaluatable`、`status`、`support_coverage`、`is_weights`、`effective_sample_size` 返回字段；
  - 3 种策略离线评估同质化得分无法区分。

### 2.2 修复方案与代码落地
1. **决策支撑度统计（`eve3/discovery/tree.py`）**：
   - 记录决策点总数 `total_decisions` 与具备真实分支支撑的决策数 `supported_decisions`；
   - 当候选集合分支数 $|C_t| > 1$ 时，记录真实决策选择；
   - 计算决策支撑率 `support_coverage = supported_decisions / total_decisions`。
2. **重要性采样（Importance Sampling, IS）与有效样本量（ESS）**：
   - 依据策略在候选节点上的评分通过 softmax 归一化计算目标策略选择概率 $p(n^*)$；
   - 假设行为策略为均匀覆盖 $\mu(n^*) = \frac{1}{|C_t|}$，计算单步重要性权重 $w_t = \frac{p(n^*)}{\mu(n^*)}$；
   - 统计完整权重轨迹 `is_weights`、有效样本量 $\text{ESS} = \frac{(\sum w_t)^2}{\sum w_t^2}$ 与权重方差 `weight_variance`。
3. **不可评估判定机制（Evaluatability & Status）**：
   - 若探索树中根本不存在任何验证节点（`has_verified_in_tree == False`），或 `support_coverage < min_support_coverage`（默认 0.5），明确标记 `evaluatable: False` 与 `status: "out_of_support"`；
   - 仅当策略在具有充分支撑的树上正常决策并抵达目标时，标记 `evaluatable: True` 与 `status: "evaluatable"`。
4. **回放树代表性重构（`experiments/run_policy_evolution.py`）**：
   - 构造包含快速验证分支（高验证权重偏好）与深入探针分支（高探针权重偏好）的代表性探索树；
   - 实测验证：`conservative` 策略耗费 4 步（成本 2.20），`balanced` 策略耗费 2 步（成本 1.40），`verification_first` 策略耗费 2 步（成本 1.40），成功排查出离线与在线表现俱佳的最优策略。

---

## 3. H17 预注册门禁防篡改与不可变配置修复

### 3.1 问题机理与修复前状态
- **核心缺陷**：
  此前 `RegressionGateConfig` 为普通可变 `@dataclass`，任何模块或测试均可在运行时将其篡改（例如将 `max_family_regression_pct` 从 2.0% 随意修改为 99.0%），使门禁形同虚设；
  此外，`Consolidator.run_sleep_cycle` 在调用方未提供 `eval_fn` 时，硬编码伪造 `cand_scores = {target_family: 1.0}`, `gen_score = 1.0`，即使探索树中 100% 的尝试全部证伪失败，也能假装 100% 成功通过门禁并向 `AdapterBank` 提交。
- **修复前状态**：
  - `cfg.max_family_regression_pct = 99.0` 随意篡改不报错；
  - 失败树在 `run_sleep_cycle` 中直接伪造通过。

### 3.2 修复方案与代码落地
1. **不可变配置与防篡改指纹（`eve3/plasticity/regression_gate.py`）**：
   - 将 `RegressionGateConfig` 声明为 `@dataclass(frozen=True)`，任何属性写入均直接抛出 `FrozenInstanceError`；
   - 增加 `compute_preregistration_hash()`，根据预注册标量计算 SHA-256 唯一指纹；
   - 增加 `is_preregistered_valid()`，在 `RegressionGate.evaluate_metrics` 执行前强制核验，若配置突破预注册安全红线（如最大退化允许度超过 2.0%），直接判定为 `passed = False` 并记录违规原因。
2. **基于经验轨迹的真实表现度量（`eve3/plasticity/consolidator.py`）**：
   - 当 `eval_fn is None` 时，真实调用 `self.regression_gate.run_general_coding_probe_evaluation()` 评估通用探针留存；
   - 从传入的 `DiscoveryTree` 中统计该任务族在该轮中的实际验证通过率：
     $$\text{cand\_family\_score} = \frac{\text{verified\_count}}{\text{total\_attempts}}$$
   - 当且仅当树中实际成功率达到预注册标准（$\ge 80.0\%$）且无退化时，门禁才准予通过；若全是证伪节点，门禁断然拒绝并安全阻断提交。

---

## 4. H15 / H18 持续学习与知识库真实连接

### 4.1 问题机理与修复前状态
- **核心缺陷**：
  此前 `experiments/run_continual_learning.py` 中 `CEGISLoop` 实例化时未注入 `knowledge_library`。在非泄漏模式 `proposer_mode="generic_enumeration"` 下，留出任务集 `list_composition`（如 `filter_evens_and_sum` 与 `reverse_and_tail`）的前向迁移增益（FWT Delta）恒为 **0.00%**。此前代码完全依靠 `leaky_templates` 中的第 #27 号泄漏模板制造虚假增益。
- **修复前状态**：
  - `run_continual_learning_experiment(proposer_mode="generic_enumeration")` 返回 `fwt_delta == 0.00%`，无法达到预注册指标 $\ge +10.0\%$。

### 4.2 修复方案与代码落地
1. **搜索控制器宏算子复合提议（`eve3/search/controller.py`）**：
   - 在 `SearchController._add_library_candidates` 中，将结晶库中的一元与二元算子与基础归约/结构原语（`sum`, `tail`, `head`, `reverse`, `len`, `neg`）进行二阶组合生成：
     $$(comp\_prim\ (op\_name\ x)) \quad \text{与} \quad (op\_name\ (comp\_prim\ x))$$
   - 使前序任务学到的 `abs_filter_evens` 与 `abs_reverse_list` 能够无缝组合出 `(sum (abs_filter_evens x))` 与 `(tail (abs_reverse_list x))`。
2. **持续学习全流程接入（`experiments/run_continual_learning.py`）**：
   - 为 `CEGISLoop` 注入真实的 `KnowledgeLibrary(continual_kb.db)`；
   - 顺序学习 `list_mapping`, `list_filtering`, `list_reduction`, `list_structural` 时，将每个通过验证的程序结晶固化为宏算子；
   - 将流水线默认模式切换为非泄漏的 `proposer_mode="generic_enumeration"`；
   - 在冷启动阶段，留出集解决率仅为 33.3%（只能解出浅层结构）；在累积结晶库后，留出集解决率提升至 66.7%，真实实现 **FWT Delta = +33.33%**！

---

## 5. 持续学习预注册指标综合验收表

在严格非泄漏模式（`generic_enumeration`）下的全流程实测结果如下：

| 评测维度 / 指标 | 实测数值 | 预注册安全阈值 | 达标状态 | 科学结论与机制证明 |
| :--- | :---: | :---: | :---: | :--- |
| **后向遗忘率 (BWT Forgetting)** | **0.00%** | $\le 2.00\%$ | **PASS** | 顺序学习 4 个任务族后，历史已学任务准确率始终保持 100.0%，零灾难性遗忘 |
| **通用能力留存下降 (General Drop)** | **0.00%** | $\le 3.00\%$ | **PASS** | 通用 Pythonic 算法探针（Fibonacci、回文、括号匹配等）留存率维持 100.0% |
| **前向迁移增益 (FWT Delta)** | **+33.33%** | $\ge +10.00\%$ | **PASS** | 依靠前序结晶算子（`filter_evens`, `reverse`）组合，留出复合任务解决率自 33.3% 跃升至 66.7% |
| **伪验证率 (False Verification)** | **0.00%** | $== 0.00\%$ | **PASS** | 留出集与历史测试无一漏网通过，保持绝对严谨 |
| **门禁防篡改哈希核验** | **通过 (Frozen)** | 严格不可变 | **PASS** | `RegressionGateConfig` 拒绝任意运行时字段修改 |

### 5.1 准确率留存矩阵 $R_{i, j}$

$$R = \begin{pmatrix}
100.0\% & --- & --- & --- \\
100.0\% & 100.0\% & --- & --- \\
100.0\% & 100.0\% & 100.0\% & --- \\
100.0\% & 100.0\% & 100.0\% & 100.0\%
\end{pmatrix}$$

对角线恒为 100.0%，下三角无任何精度衰退，证实了符号适配器库与结晶持久化在持续演进中的稳定性。

---

## 6. 全仓测试与质量铁律核查（Compliance Audit）

### 6.1 全仓测试状态
- **全仓综合测试集**（`pytest tests/`）：
  **155 passed, 1 skipped (Windows 平台跳过苹果 MLX-LM), 0 failed**（总耗时 19.75s）。
- **新增 Stage S5 测试**：
  - `tests/test_stage_s5_tree_support.py`（4 项测试全部通过）
  - `tests/test_stage_s5_gate_tamper_resistance.py`（3 项测试全部通过）
  - `tests/test_stage_s5_continual_learning.py`（2 项测试全部通过）
- **历史 P0 审计测试集**（`tests/test_audit_p0_regressions.py`）：5/5 项持续 100% PASS。
- **诊断棘轮与静态扫描**（`tests/test_stage_s0_diagnostics.py`）：零宽泛异常，棘轮只降不升。

### 6.2 七条铁律遵循情况审计

| 铁律编号 | 规则要求 | 执行状态 | 验证证据 |
| :--- | :--- | :--- | :--- |
| **铁律 1** | TDD“先红后绿”流程 | 严格执行 | 每一项新增能力（树支撑、不可变配置、库算子复合）均先落盘红灯测试，修复后转绿 |
| **铁律 2** | 严禁削弱或删除现有断言 | 严格执行 | 原有全部 147 项断言无一放宽或删除，全仓测试扩展至 156 项且 100% 封闭一致 |
| **铁律 3** | AST 静态零宽泛异常 | 严格执行 | `test_no_bare_except_exception_in_eve3_codebase` 全仓静态分析违规数恒为 0 |
| **铁律 4** | 原子 Commit | 严格执行 | 3 个功能原子 commit 拆分完成，每个 commit 仅包含对应功能与专属测试 |
| **铁律 5** | 诊断棘轮只降不升 | 严格执行 | `test_swallowed_errors_ratchet_only_decreases` 验证所有静默错误上限封死 |
| **铁律 6** | 真实算子执行与基线封闭 | 严格执行 | 彻底终结 `leaky_templates` 依赖，持续学习在纯净 `generic_enumeration` 下达标 |
| **铁律 7** | 阶段报告与主动停下确认 | 严格执行 | 产出本报告，更新日志后主动停下等待用户确认 |

---

## 7. 结论与下一步（Stage S6）

Stage S5 成功解决了策略更新与持续学习过程中的所有预注册核心缺陷，确立了反事实回放树支撑集理论界限与不可变门禁体系，并在纯符号无泄漏环境下实现了高达 **+33.33%** 的真实前向知识迁移。

依据整体路线图，后续工作为 **Stage S6: 终期全系统诚实科学评测（论文级验收）**：
- 在全仓无泄漏、全真基线、真实库连接的条件下，端到端执行全量基准实验；
- 产出覆盖 System 1, System 2, System 3, Plasticity 各子系统消融对比的论文级科学总结报告；
- 完成项目整体终验归档。

本阶段工作已全部封闭完成，**在此主动停下，等待用户确认后进入 Stage S6**。
