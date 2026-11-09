# Stage S1 阶段报告：评测完整性与消除模板答案泄漏（H9 / H10）

> **⚠️ 阶段前置声明（按 S1 追加约束 1 & 2）**：
> 1. **本阶段 IG 计算是否已受探针类型修复影响**：**否（UNFIXED_IN_S1，定于 S2/S3 修复）**。在 Stage S1 中，`eve3/system2_falsifier/bayesian_prober.py:124`（`group_by_output`）与 `eve3/system2_falsifier/smt_distinguisher.py:187`（`_heuristic_distinguishing`）尚未修改，仍将硬编码整数探针 `[-2, -1, 0, 1, 2, 3, 5, 10]` 直接传入列表处理候选程序，触发 `TypeError` 并被归入 `"<ERROR>"` 等价类。因此当存活候选数 $>1$ 时，信息增益（IG）与后验更新仍受该探针类型错配影响（见下方各表中的 `swallowed_errors["bayesian_prober.group_by_output"]` 与 `swallowed_errors["smt_distinguisher._heuristic_distinguishing"]` 实测计数）。
> 2. **依赖结晶库（Crystallized Library）的对照臂状态**：因 Stage S0 已实测证实 `KnowledgeLibrary` 提取的结晶算子（`op_cb37` 等）从未注册进 `DSLInterpreter.env`（导致 664 次 `NameError` 沙箱拒绝），本报告中所有依赖结晶库的对照臂（`run_library_ablation.py` 的 `With-Lib`、`run_full_ablation.py` 的 `Baseline_C_Library` 与 `Full_System` 库部分、`run_autonomous_curriculum.py` 与 `run_memory_consolidation.py` 的库结晶复用部分）一律标记为 **`INVALID_PENDING_S4`**，不在 S1 解读其库增益结论；S1 仅对比不依赖结晶库的 `proposer_mode`。

---

## 1. S0.1 收尾项完成情况

在进入 S1 前，已完成 S0.1 全部两项收尾清理：
1. **清理 `value_compressor.py:55` 冗余布尔表达式**：将 `eve3/system3_crystallizer/value_compressor.py:55` 中的 `f"({self.name} {self.name and k_val} x)"` 修正为 `f"({self.name} {k_val} x)"`。
2. **归档 S0 诊断基线 JSON**：已将 `/Users/prognosticatex/.gemini/antigravity/brain/b1d1b2d0-c8fa-469b-bdb9-515766625a95/scratch/s0_diagnostics_output.json` 复制归档至 `/Users/prognosticatex/Desktop/reports/s0_diagnostics_output.json`。

---

## 2. S1 做了什么（代码与测试改动清单）

1. **全量模板泄漏逐项审计（[`reports/template_leakage.md`](file:///Users/prognosticatex/Desktop/reports/template_leakage.md)）**：
   - 编写并运行 `scratch/audit_template_leakage.py`，对 `eve3/system1_proposer/generator.py:18-51` 的 **27 个启发式模板**与 `eve3/search/enumerator.py:49-135` 的 **67 个硬编码枚举模板**（55 个 list 模板 + 12 个 int 模板），逐个比对全部 9 个 benchmark JSON 文件中的 **26 个任务条目（13 个唯一任务）**（含字符串精确匹配与测试集 I/O 语义等价检查）。
   - 实测结论：**24/26（92.3%）** 个任务条目（**11/13 = 84.6%** 个唯一任务）的参考答案被一字不差地硬编码在 `generator.py` 的 27 个模板中；除 `families/list_composition.json` 外的全部 8 个 JSON 切分（共 23 个任务条目、10 个唯一任务）泄漏率均为 **100.0%**。即使在标称 `is_held_out: true` 的 `list_composition.json` 中，`filter_evens_and_sum` 的参考答案 `(sum (filter (lambda (a) (is_even a)) x))` 也是 `generator.py` 的第 #27 号模板。

2. **新增 `proposer_mode` 与 `enumerator_max_depth` 配置（[`eve3/config.py:10-49`](file:///Users/prognosticatex/Desktop/eve-3/eve3/config.py#L10-L49)）**：
   - 定义 `VALID_PROPOSER_MODES = ("leaky_templates", "generic_enumeration", "llm_only", "llm_plus_enumeration")`。
   - 将 `EveConfig.proposer_mode` 默认值设为非泄漏模式 `"generic_enumeration"`（符合 S1 第 3 条铁律："所有对外结论默认使用非 leaky 模式"），并新增 `enumerator_max_depth: int = 4` 与 `__post_init__` 合法性校验。

3. **实现真正的通用自底向上 AST 枚举器与来源追踪（[`eve3/search/enumerator.py:138-259`](file:///Users/prognosticatex/Desktop/eve-3/eve3/search/enumerator.py#L138-L259)、[`eve3/search/controller.py:33-130`](file:///Users/prognosticatex/Desktop/eve-3/eve3/search/controller.py#L33-L130)）**：
   - 在 `SymbolicEnumerator` 中新增 `_enumerate_generic_bottom_up(domain_hint, max_candidates)`，严格按 AST 深度 $d = 1, 2, \dots, \text{max\_depth}$ 自底向上生成通用 DSL 原语组合：
     - $d=1$：变量与基础常量（`x`, `0`, `1`, `2`, `-1`）；
     - $d=2$：一阶一元原语作用在 $d=1$ 子表达式上（`(reverse x)`, `(tail x)`, `(head x)`, `(sum x)`, `(length x)`, `(inc x)`, `(dec x)`, `(neg x)`）；
     - $d=3$：一阶一元与二元原语组合（如 `(tail (reverse x))`, `(reverse (tail x))`, `(cons 0 x)` 等，不含任何 `lambda` 高阶模板）；
     - $d=4$：在 $d=3$ 基础上，由通用一元算子（`inc`, `dec`, `neg`, `is_even`, `is_odd`）及基础算术/比较二元算子（`+`, `-`, `*`, `gt`, `lt`, `eq`）配小整数常量 `{0, 1, 2, 3, 5}` 生成单层 `map`/`filter`/`fold` 表达式，**不含任何复合任务专用模板（如 `(sum (filter ...))` 或 `(reverse (map ...))`）**。
   - 为每个候选程序增加 `CandidateProgram.source_detail` 字段（[`eve3/models.py:173-192`](file:///Users/prognosticatex/Desktop/eve-3/eve3/models.py#L173-L192)），精确记录首次命中来源：`template:#k`（启发式模板编号）、`leaky_enum:#k`（旧枚举模板编号）、`enum:depth=d:#idx`（通用自底向上枚举深度与序号）、`llm:call=c:line=l`（LLM 调用批次与行号）。

4. **安装并固定 `mlx-lm==0.32.2` / `mlx==0.32.4`，修复 `sampler` API 兼容性与 LLM 遥测（[`pyproject.toml:25-28`](file:///Users/prognosticatex/Desktop/eve-3/pyproject.toml#L25-L28)、[`eve3/system1_proposer/generator.py:184-229`](file:///Users/prognosticatex/Desktop/eve-3/eve3/system1_proposer/generator.py#L184-L229)、[`eve3/system1_proposer/sandbox.py:44-104`](file:///Users/prognosticatex/Desktop/eve-3/eve3/system1_proposer/sandbox.py#L44-L104)）**：
   - 在本机安装并固定 `mlx-lm==0.32.2` 与 `mlx==0.32.4`，拉取 `EveConfig.model_name` 默认模型 `mlx-community/Qwen2.5-Coder-3B-Instruct-4bit`。
   - 修复 `generator.py` 中已废弃的 `mlx_lm.generate(..., temp=...)` 参数（在 `mlx-lm==0.32.2` 中会抛出 `TypeError: generate_step() got an unexpected keyword argument 'temp'`），改用 `from mlx_lm.sample_utils import make_sampler; sampler = make_sampler(temp=float(self.config.generation_temperature))` 并传入 `sampler=sampler`。
   - 对 Instruct 模型调用 `tokenizer.apply_chat_template(..., tokenize=False, add_generation_prompt=True)`，并在 `Diagnostics` 中新增 `llm_latencies_ms`、`llm_raw_candidates`、`llm_syntax_valid_candidates`、`llm_sandbox_passed_candidates` 四个遥测字段。
   - 在 `llm_only` 模式下严禁静默回退到启发式模板或枚举器。

5. **新增 S1 回归测试集（[`tests/test_stage_s1_proposer_modes.py`](file:///Users/prognosticatex/Desktop/eve-3/tests/test_stage_s1_proposer_modes.py)）**：
   - 共新增 5 个回归测试（含真实 MLX-LM 冒烟测试 `test_mlx_llm_smoke_test_sampler_compatibility_and_telemetry`），遵循"先红后绿"铁律：修复前 5 个测试全部 FAIL，修复后全套测试 **91 passed, 0 failed, 0 skipped（耗时 9.85s）**。

---

## 3. 核心实测结果：在没有模板泄漏的情况下，系统到底能解多少任务？

### 3.1 6 种 `proposer_mode` 配置在 13 个唯一任务上的总览对比与 Diagnostics 汇总

数据来源：[`reports/s1_evaluation_output.json`](file:///Users/prognosticatex/Desktop/reports/s1_evaluation_output.json)。

| 模式标识 (`mode_key`) | `proposer_mode` | 枚举深度上限 | 唯一任务通过数 (总=13) | 唯一任务通过率 | 总耗时 (ms) | `oracle_queries` | `z3_calls` | `z3_fallbacks` | `z3_timeouts` | `llm_calls` | `sandbox_rejections` | `swallowed_errors` 汇总 | 备注 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `leaky_templates` | `leaky_templates` | N/A (硬编码表) | **11 / 13** | **84.62%** | 367.43 | 20 | 0 | 40 | 0 | 0 | `{}` | `smt_distinguisher._heuristic_distinguishing`: 320 (`TypeError`), `bayesian_prober.group_by_output`: 400 (`TypeError`) | **含答案泄漏，仅作参考** |
| `generic_enumeration_d3` | `generic_enumeration` | `max_depth=3`（仅一阶原语组合，无高阶 `lambda`） | **5 / 13** | **38.46%** | 169.96 | 10 | 0 | 20 | 0 | 0 | `{}` | `smt_distinguisher._heuristic_distinguishing`: 160 (`TypeError`), `bayesian_prober.group_by_output`: 200 (`TypeError`) | 纯一阶自底向上枚举 |
| `generic_enumeration_d4` | `generic_enumeration` | `max_depth=4`（含单层高阶 `map`/`filter`/`fold` 原子谓词组合） | **11 / 13** | **84.62%** | 408.42 | 21 | 0 | 51 | 0 | 0 | `{}` | `smt_distinguisher._heuristic_distinguishing`: 400 (`TypeError`), `bayesian_prober.group_by_output`: 455 (`TypeError`) | 默认非泄漏模式 |
| `llm_only` | `llm_only` | N/A（禁用枚举与启发式模板） | **0 / 13** | **0.00%** | 20,293.10 | 0 | 0 | 0 | 0 | **13** | `{"NameError": 14, "DSLParserError": 13, "TypeError": 10}` | `sandbox.filter_valid_candidates.exec`: 24, `sandbox.filter_valid_candidates.parse`: 13 | 真实本地 `Qwen2.5-Coder-3B-Instruct-4bit` |
| `llm_plus_enumeration_d3` | `llm_plus_enumeration` | `max_depth=3` | **5 / 13** | **38.46%** | 18,237.49 | 10 | 0 | 20 | 0 | **13** | `{"NameError": 17, "TypeError": 11, "DSLParserError": 10}` | `sandbox.exec`: 28, `sandbox.parse`: 10, `smt._heuristic`: 160, `prober.group_by_output`: 200 | 全部 5 个命中均来自枚举器 |
| `llm_plus_enumeration_d4` | `llm_plus_enumeration` | `max_depth=4` | **11 / 13** | **84.62%** | 19,185.43 | 21 | 0 | 51 | 0 | **13** | `{"DSLParserError": 22, "TypeError": 8, "NameError": 7}` | `sandbox.exec`: 15, `sandbox.parse`: 22, `smt._heuristic`: 400, `prober.group_by_output`: 455 | 全部 11 个命中均来自枚举器 |

### 3.2 全部 9 个 Benchmark JSON 切分在不同模式下的通过率对比

| Benchmark 切分文件 | 任务数 | `leaky_templates`（**含答案泄漏，仅作参考**） | `generic_enumeration` ($d \le 3$, 仅一阶) | `generic_enumeration` ($d \le 4$, 含单层高阶) | `llm_only` (`Qwen2.5-Coder-3B-4bit`) | `llm_plus_enumeration` ($d \le 3$) | `llm_plus_enumeration` ($d \le 4$) |
|---|---|---|---|---|---|---|---|
| `benchmarks/dev_train.json` | 2 | 2/2 (100.0%) | **0/2 (0.0%)** | 2/2 (100.0%) | **0/2 (0.0%)** | 0/2 (0.0%) | 2/2 (100.0%) |
| `benchmarks/dev_eval.json` | 2 | 2/2 (100.0%) | **1/2 (50.0%)** | 2/2 (100.0%) | **0/2 (0.0%)** | 1/2 (50.0%) | 2/2 (100.0%) |
| `benchmarks/held_out_test.json` | 3 | 3/3 (100.0%) | **1/3 (33.3%)** | 3/3 (100.0%) | **0/3 (0.0%)** | 1/3 (33.3%) | 3/3 (100.0%) |
| `benchmarks/list_functions.json` | 6 | 6/6 (100.0%) | **2/6 (33.3%)** | 6/6 (100.0%) | **0/6 (0.0%)** | 2/6 (33.3%) | 6/6 (100.0%) |
| `benchmarks/families/list_mapping.json` | 3 | 3/3 (100.0%) | **0/3 (0.0%)** | 3/3 (100.0%) | **0/3 (0.0%)** | 0/3 (0.0%) | 3/3 (100.0%) |
| `benchmarks/families/list_filtering.json` | 3 | 3/3 (100.0%) | **0/3 (0.0%)** | 3/3 (100.0%) | **0/3 (0.0%)** | 0/3 (0.0%) | 3/3 (100.0%) |
| `benchmarks/families/list_reduction.json` | 2 | 2/2 (100.0%) | **2/2 (100.0%)** | 2/2 (100.0%) | **0/2 (0.0%)** | 2/2 (100.0%) | 2/2 (100.0%) |
| `benchmarks/families/list_structural.json` | 2 | 2/2 (100.0%) | **2/2 (100.0%)** | 2/2 (100.0%) | **0/2 (0.0%)** | 2/2 (100.0%) | 2/2 (100.0%) |
| `benchmarks/families/list_composition.json` | 3 | 1/3 (33.3%) [命中 `filter_evens_and_sum`] | **1/3 (33.3%)** [命中 `reverse_and_tail`] | **1/3 (33.3%)** [命中 `reverse_and_tail`] | **0/3 (0.0%)** | 1/3 (33.3%) | 1/3 (33.3%) |
| **26 个任务条目合计** | **26** | **24 / 26 (92.3%)** | **9 / 26 (34.6%)** | **24 / 26 (92.3%)** | **0 / 26 (0.0%)** | **9 / 26 (34.6%)** | **24 / 26 (92.3%)** |

---

## 4. 逐任务首次命中来源（First-Hit Provenance）与"泄漏依赖清单"（按 S1 追加约束 3）

### 4.1 13 个唯一任务的逐任务首次命中来源对比表

| # | 任务名称 (`task_name`) | 参考程序 (`reference_program`) | AST 深度 | `leaky_templates`（含答案泄漏，仅作参考） | `generic_enumeration` ($d \le 3$) | `generic_enumeration` ($d \le 4$) | `llm_only` | `llm_plus_enumeration` ($d \le 4$) |
|---|---|---|---|---|---|---|---|---|
| 1 | `list_increment_all` | `(map (lambda (a) (+ a 1)) x)` | 4 | PASS `(map (lambda (a) (inc a)) x)` [`leaky_enum:#7` / `template:#9`] | FAIL (`collapsed`) | PASS `(map (lambda (a) (inc a)) x)` [`enum:depth=4:#45`] | FAIL (`collapsed`) | PASS [`enum:depth=4:#45`] |
| 2 | `filter_evens` | `(filter (lambda (a) (is_even a)) x)` | 4 | PASS `(filter (lambda (a) (is_even a)) x)` [`leaky_enum:#10` / `template:#12`] | FAIL (`collapsed`) | PASS `(filter (lambda (a) (is_even a)) x)` [`enum:depth=4:#48`] | FAIL (`collapsed`) | PASS [`enum:depth=4:#48`] |
| 3 | `list_double_all` | `(map (lambda (a) (* a 2)) x)` | 4 | PASS `(map (lambda (a) (* a 2)) x)` [`leaky_enum:#26` / `template:#7`] | FAIL (`collapsed`) | PASS `(map (lambda (a) (* a 2)) x)` [`enum:depth=4:#64`] | FAIL (`collapsed`) | PASS [`enum:depth=4:#64`] |
| 4 | `list_sum` | `(sum x)` | 2 | PASS `(sum x)` [`leaky_enum:#5` / `template:#18`] | PASS `(sum x)` [`enum:depth=2:#5`] | PASS `(sum x)` [`enum:depth=2:#5`] | FAIL (`collapsed`) | PASS [`enum:depth=2:#5`] |
| 5 | `filter_greater_than_two` | `(filter (lambda (a) (gt a 2)) x)` | 4 | PASS `(filter (lambda (a) (gt a 2)) x)` [`leaky_enum:#27` / `template:#15`] | FAIL (`collapsed`) | PASS `(filter (lambda (a) (gt a 2)) x)` [`enum:depth=4:#65`] | FAIL (`collapsed`) | PASS [`enum:depth=4:#65`] |
| 6 | `list_reverse` | `(reverse x)` | 2 | PASS `(reverse x)` [`leaky_enum:#2` / `template:#2`] | PASS `(reverse x)` [`enum:depth=2:#2`] | PASS `(reverse x)` [`enum:depth=2:#2`] | FAIL (`collapsed`) | PASS [`enum:depth=2:#2`] |
| 7 | `filter_positive` | `(filter (lambda (a) (gt a 0)) x)` | 4 | PASS `(filter (lambda (a) (gt a 0)) x)` [`leaky_enum:#15` / `template:#14`] | FAIL (`exhausted_unverified`, 伪命中 `(tail (tail x))` [`enum:depth=3:#16`], held-out 0.33) | PASS `(filter (lambda (a) (gt a 0)) x)` [`enum:depth=4:#53`] | FAIL (`collapsed`) | PASS [`enum:depth=4:#53`] |
| 8 | `list_decrement_all` | `(map (lambda (a) (- a 1)) x)` | 4 | PASS `(map (lambda (a) (dec a)) x)` [`leaky_enum:#8` / `template:#10`] | FAIL (`collapsed`) | PASS `(map (lambda (a) (dec a)) x)` [`enum:depth=4:#46`] | FAIL (`collapsed`) | PASS [`enum:depth=4:#46`] |
| 9 | `list_length` | `(length x)` | 2 | PASS `(length x)` [`leaky_enum:#6` / `template:#19`] | PASS `(length x)` [`enum:depth=2:#6`] | PASS `(length x)` [`enum:depth=2:#6`] | FAIL (`collapsed`) | PASS [`enum:depth=2:#6`] |
| 10 | `list_tail_elements` | `(tail x)` | 2 | PASS `(tail x)` [`leaky_enum:#3` / `template:#3`] | PASS `(tail x)` [`enum:depth=2:#3`] | PASS `(tail x)` [`enum:depth=2:#3`] | FAIL (`collapsed`) | PASS [`enum:depth=2:#3`] |
| 11 | `filter_evens_and_sum` | `(sum (filter (lambda (a) (is_even a)) x))` | 5 | **PASS** `(sum (filter (lambda (a) (is_even a)) x))` [**`template:#27`**] | **FAIL (`collapsed`)** | **FAIL (`collapsed`)** | FAIL (`collapsed`) | **FAIL (`collapsed`)** |
| 12 | `filter_positive_and_sum` | `(sum (filter (lambda (a) (gt a 0)) x))` | 5 | FAIL (`collapsed`) | FAIL (`collapsed`) | FAIL (`collapsed`) | FAIL (`collapsed`) | FAIL (`collapsed`) |
| 13 | `reverse_and_tail` | `(tail (reverse x))` | 3 | **FAIL (`collapsed`)** | **PASS `(tail (reverse x))` [`enum:depth=3:#11`]** | **PASS `(tail (reverse x))` [`enum:depth=3:#11`]** | FAIL (`collapsed`) | **PASS [`enum:depth=3:#11`]** |

### 4.2 泄漏依赖清单（Tasks Passing ONLY Under `leaky_templates`）

#### A. 严格泄漏依赖清单（在所有非 leaky 模式 `generic_enumeration d=3/d=4`、`llm_only`、`llm_plus_enumeration d=3/d=4` 下均失败，**仅在 `leaky_templates` 下通过**）

1. **`filter_evens_and_sum`**（所属族：`benchmarks/families/list_composition.json`，`is_held_out: true`）：
   - **参考程序**：`(sum (filter (lambda (a) (is_even a)) x))`（AST 深度 = 5，节点数 = 9）。
   - **在 `leaky_templates` 下通过的唯一原因**：`eve3/system1_proposer/generator.py:50` 的第 **#27 号模板**一字不差地硬编码了 `(sum (filter (lambda (a) (is_even a)) x))`。
   - **在非 leaky 模式下失败的原因**：该程序需要将一阶归约原语 `sum` 嵌套在深度 4 的高阶 `filter` 表达式外层（总 AST 深度为 5），超出了 $d \le 4$ 的无偏自底向上枚举范围，而同家族同结构的 `filter_positive_and_sum`（`(sum (filter (lambda (a) (gt a 0)) x))`）因未被硬编码进 `generator.py`，在 `leaky_templates` 下同样 `collapsed`。这直接证实此前 `list_composition` 上 `filter_evens_and_sum` 的通过完全来自 `template:#27` 答案泄漏。

#### B. 高阶模板依赖清单（在纯一阶枚举 `generic_enumeration (d=3)` 下失败，依赖深度 4 的 `map`/`filter` 高阶原语枚举或 `leaky_templates` 才能通过的 6 个任务）

| 任务名称 | 所属族 | 参考程序 | `leaky_templates` 命中来源 | `generic_enumeration (d=3)` 状态 | `generic_enumeration (d=4)` 命中来源 |
|---|---|---|---|---|---|
| `list_increment_all` | `list_mapping` | `(map (lambda (a) (+ a 1)) x)` | `leaky_enum:#7` / `template:#9` | `collapsed` | `enum:depth=4:#45` (`(map (lambda (a) (inc a)) x)`) |
| `list_decrement_all` | `list_mapping` | `(map (lambda (a) (- a 1)) x)` | `leaky_enum:#8` / `template:#10` | `collapsed` | `enum:depth=4:#46` (`(map (lambda (a) (dec a)) x)`) |
| `list_double_all` | `list_mapping` | `(map (lambda (a) (* a 2)) x)` | `leaky_enum:#26` / `template:#7` | `collapsed` | `enum:depth=4:#64` (`(map (lambda (a) (* a 2)) x)`) |
| `filter_evens` | `list_filtering` | `(filter (lambda (a) (is_even a)) x)` | `leaky_enum:#10` / `template:#12` | `collapsed` | `enum:depth=4:#48` (`(filter (lambda (a) (is_even a)) x)`) |
| `filter_positive` | `list_filtering` | `(filter (lambda (a) (gt a 0)) x)` | `leaky_enum:#15` / `template:#14` | `exhausted_unverified`（`enum:depth=3:#16` `(tail (tail x))` 巧合拟合 2 个训练例 `[-2,0,3,5]->[3,5]` 与 `[-1,-5]->[]`，但在 held-out 上准确率仅 0.33） | `enum:depth=4:#53` (`(filter (lambda (a) (gt a 0)) x)`) |
| `filter_greater_than_two` | `list_filtering` | `(filter (lambda (a) (gt a 2)) x)` | `leaky_enum:#27` / `template:#15` | `collapsed` | `enum:depth=4:#65` (`(filter (lambda (a) (gt a 2)) x)`) |

#### C. 反向发现：在 `leaky_templates` 下失败、但在非 leaky `generic_enumeration (d=3 / d=4)` 下通过的任务

- **`reverse_and_tail`**（所属族：`benchmarks/families/list_composition.json`，参考答案 `(tail (reverse x))`，AST 深度 = 3）：
  - 在 `leaky_templates` 下：**FAIL (`collapsed`)**——因为原 `SymbolicEnumerator` 并非真正的 AST 枚举器，只是硬编码模板表，漏写了 `(tail (reverse x))`。
  - 在 `generic_enumeration` ($d=3$ 与 $d=4$) 下：**PASS (`held_out_tests_passed`)**，首次命中来源为 **`enum:depth=3:#11`**（深度 3 的第 4 个一阶组合表达式）。

---

## 5. 本地 MLX-LM (`llm_only`) 路径实测报告（按 S1 追加约束 4）

1. **软硬件与固定版本环境**：
   - 硬件：Apple M4 (`arm64`, 16 GB 统一内存)
   - Python：`3.14.8`
   - 固定依赖版本（已写入 `pyproject.toml:25-28`）：`mlx==0.32.4`，`mlx-lm==0.32.2`
   - 本地权重：`mlx-community/Qwen2.5-Coder-3B-Instruct-4bit`（`EveConfig.model_name` 默认模型）

2. **API 兼容性修复验证**：
   - 修复前：`generator.py:114` 调用 `mlx_lm.generate(..., temp=self.config.generation_temperature)`，在 `mlx-lm==0.32.2` 下 100% 触发 `TypeError: generate_step() got an unexpected keyword argument 'temp'`，此前被 `except Exception:` 静默吞掉并回退到 27 个泄漏模板。
   - 修复后：使用 `sampler = make_sampler(temp=float(self.config.generation_temperature))` 传入 `mlx_lm.generate(..., sampler=sampler)`，在 13 个任务上共执行 **13 次真实 LLM 推理**，`swallowed_errors["generator._generate_raw_proposals"] == 0`。

3. **`llm_only` 全量 13 任务实测遥测指标**（数据来源：`reports/s1_evaluation_output.json -> llm_telemetry`）：
   - **`llm_calls` 总次数**：**13**（每个唯一任务调用 1 次，无任何静默回退）
   - **单次生成耗时（`llm_latencies_ms`）**：
     - 平均值（Mean）：**1,399.76 ms**
     - 最小值（Min）：**469.25 ms**
     - 最大值（Max）：**2,224.39 ms**
     - 13 次逐次耗时明细（ms）：`[1858.19, 1293.66, 2015.10, 862.46, 1980.01, 469.25, 1321.73, 1825.95, 1180.70, 1214.32, 2224.39, 790.38, 1160.69]`
   - **提取出的原始候选行数（`llm_raw_candidates`）**：**61**（平均每次调用提取 4.69 个 S-表达式候选）
   - **候选语法合法率（`llm_syntax_valid_candidates / llm_raw_candidates`）**：**48 / 61 = 78.69%**（13 个候选因括号不匹配或 `[1, 2, 3]` 逗号分隔语法触发 `DSLParserError`）
   - **候选通过沙箱比例（`llm_sandbox_passed_candidates`）**：
     - 占原始候选比例：**0 / 61 = 0.00%**
     - 占语法合法候选比例：**0 / 48 = 0.00%**
   - **沙箱拒绝异常分类（`sandbox_rejections`）**：
     - `NameError`: **14 次**（LLM 生成了 DSL 未定义的标识符，如 `even?`、`positive?`、`add` 或把 `map` 写成未绑定算子组合）
     - `DSLParserError`: **13 次**（括号未闭合或 Markdown 残片）
     - `TypeError`: **10 次**（LLM 将高阶函数写成 Haskell 式柯里化如 `(map + 1 x)` 而非 `(map (lambda (a) (+ a 1)) x)`，导致 `DSLInterpreter` 对整数调用 `+` 之外的参数形态报错，或直接把示例字面量 `[1 2 3]` 当作输入而非自由变量 `x`）
   - **最终任务通过率**：**0 / 13 (0.00%)**。
   - **实测结论**：在未对 prompt 给出 concrete few-shot DSL 语法示例前，3B 4-bit 本地模型虽然能以 **78.69%** 的语法合法率输出 S-表达式（约 1.4 秒/次），但 **0%** 的候选能同时符合 EVE-3 自定义 Lisp 方言的 `(lambda (a) ...)` 绑定约定并通过全部训练 I/O 对；此前系统声称的"神经直觉提议"贡献度实际上为 **0%**，全部命中均来自硬编码模板或符号枚举。

---

## 6. 重新运行 `experiments/` 下全部 9 个脚本：Leaky vs Non-Leaky 实测对比（按 S1 第 5 项及追加约束 1 & 2）

数据来源：[`reports/s1_evaluation_output.json -> experiments_comparison`](file:///Users/prognosticatex/Desktop/reports/s1_evaluation_output.json)。

| 脚本路径 | 对照模式 | 关键实测输出指标 | `oracle_queries` | `z3_calls` | `z3_fallbacks` | `sandbox_rejections` | `swallowed_errors` 汇总 | 有效性标注 |
|---|---|---|---|---|---|---|---|---|
| `experiments/run_library_ablation.py` | `leaky_templates` | `No-Lib=100%`, `With-Lib=100% (INVALID_PENDING_S4)`, `Avg Probes=4.00` | 24 | 0 | 40 | `{"NameError": 16}` | `smt._heuristic`: 320, `prober.group`: 448, `sandbox.exec`: 16 | **含答案泄漏，仅作参考**；`With-Lib` 为 **`INVALID_PENDING_S4`** |
| `experiments/run_library_ablation.py` | `generic_enumeration (d=3)` | **`No-Lib=50%`**, `With-Lib=50% (INVALID_PENDING_S4)`, `Avg Probes=4.00` | 16 | 0 | 48 | `{"NameError": 8}` | `smt._heuristic`: 384, `prober.group`: 384, `sandbox.exec`: 8 | `No-Lib` 有效；`With-Lib` 为 **`INVALID_PENDING_S4`** |
| `experiments/run_library_ablation.py` | `generic_enumeration (d=4)` | **`No-Lib=100%`**, `With-Lib=100% (INVALID_PENDING_S4)`, `Avg Probes=4.00` | 24 | 0 | 72 | `{"NameError": 8}` | `smt._heuristic`: 576, `prober.group`: 576, `sandbox.exec`: 8 | `No-Lib` 有效；`With-Lib` 为 **`INVALID_PENDING_S4`** |
| `experiments/run_full_ablation.py` | `leaky_templates` | `Baseline_A_Naive=100.0%`, `Baseline_B_FalsifyOnly=100.0%`, `Baseline_C_Library=100.0% (INVALID_PENDING_S4)`, `Full_System=100.0% (INVALID_PENDING_S4)` | 32 | 0 | 48 | `{"NameError": 80}` | `smt._heuristic`: 384, `prober.group`: 576, `sandbox.exec`: 80 | **含答案泄漏，仅作参考**；库相关臂为 **`INVALID_PENDING_S4`** |
| `experiments/run_full_ablation.py` | `generic_enumeration (d=3)` | **`Baseline_A_Naive=40.0%`**, **`Baseline_B_FalsifyOnly=40.0%`**, `Baseline_C_Library=40.0% (INVALID_PENDING_S4)` | 24 | 0 | 72 | `{"NameError": 20}` | `smt._heuristic`: 576, `prober.group`: 576, `sandbox.exec`: 20 | 消除泄漏后一阶枚举仅解 2/5 (40.0%) |
| `experiments/run_full_ablation.py` | `generic_enumeration (d=4)` | **`Baseline_A_Naive=80.0%`**, **`Baseline_B_FalsifyOnly=100.0%`**, `Baseline_C_Library=100.0% (INVALID_PENDING_S4)` | 35 | 0 | 99 | `{"NameError": 40}` | `smt._heuristic`: 768, `prober.group`: 813, `sandbox.exec`: 40 | **重要发现**：在 $d=4$ 非泄漏枚举下，无 System 2 的 `Baseline_A_Naive` 仅 80.0%，加 System 2 的 `Baseline_B_FalsifyOnly` 提升至 100.0%！ |
| `experiments/run_continual_learning.py` | `leaky_templates` | `Cold-Start=0.0% (0/3)`, `Accumulated=33.3% (1/3)`, **`FWT Delta=+33.33%`**, `BWT=0.00%` | 128 | 0 | 288 | `{}` | `smt._heuristic`: 2304, `prober.group`: 2688 | **含答案泄漏，仅作参考**（`+33.33%` 完全源于 Step 4 切换 `hybrid` 触发 `template:#27`） |
| `experiments/run_continual_learning.py` | `generic_enumeration (d=3)` | `Cold-Start=33.3% (1/3)`, `Accumulated=33.3% (1/3)`, **`FWT Delta=+0.00%`**, `Retention=[0%, 0%, 100%, 100%]` | 48 | 0 | 96 | `{}` | `smt._heuristic`: 768, `prober.group`: 960 | 证实 H15：移除 `template:#27` 泄漏后，真实前向迁移 `FWT Delta = 0.00%` |
| `experiments/run_continual_learning.py` | `generic_enumeration (d=4)` | `Cold-Start=33.3% (1/3)`, `Accumulated=33.3% (1/3)`, **`FWT Delta=+0.00%`**, `Retention=[100%, 100%, 100%, 100%]` | 132 | 0 | 340 | `{}` | `smt._heuristic`: 2688, `prober.group`: 2940 | 证实 H15：4 个训练族 100% 解决，但因未向 `CEGISLoop` 传递库或 Adapter，`FWT Delta = 0.00%` |
| `experiments/run_autonomous_curriculum.py` | `leaky_templates` | `Arm A4=33.3% (1/3)`, `Arm A5=33.3% (1/3)` | 66 | 0 | 126 | `{"NameError": 368}` | `smt._heuristic`: 1008, `prober.group`: 1296, `sandbox.exec`: 368 | 库结晶部分 **`INVALID_PENDING_S4`** |
| `experiments/run_autonomous_curriculum.py` | `generic_enumeration (d=3)` | `Arm A4=33.3% (1/3)`, `Arm A5=33.3% (1/3)` | 42 | 0 | 114 | `{"NameError": 40}` | `smt._heuristic`: 912, `prober.group`: 960, `sandbox.exec`: 40 | 库结晶部分 **`INVALID_PENDING_S4`** |
| `experiments/run_autonomous_curriculum.py` | `generic_enumeration (d=4)` | `Arm A4=33.3% (1/3)`, `Arm A5=33.3% (1/3)` | 68 | 0 | 188 | `{"NameError": 184}` | `smt._heuristic`: 1488, `prober.group`: 1566, `sandbox.exec`: 184 | 库结晶部分 **`INVALID_PENDING_S4`** |
| `experiments/run_autonomous_agi_loop.py` | `leaky_templates` | `Cumulative Solved: 11/12 (91.7%)` | 25 | 0 | 35 | `{}` | `smt._heuristic`: 280, `prober.group`: 440 | **含答案泄漏，仅作参考** |
| `experiments/run_autonomous_agi_loop.py` | `generic_enumeration (d=3)` | **`Cumulative Solved: 6/12 (50.0%)`** | 20 | 0 | 50 | `{}` | `smt._heuristic`: 400, `prober.group`: 440 | 纯一阶枚举下解决 6/12 (50.0%) |
| `experiments/run_autonomous_agi_loop.py` | `generic_enumeration (d=4)` | **`Cumulative Solved: 11/12 (91.7%)`** | 26 | 0 | 66 | `{}` | `smt._heuristic`: 520, `prober.group`: 575 | 含单层高阶枚举下解决 11/12 (91.7%) |
| `experiments/run_memory_consolidation.py` | `leaky_templates` | `Baseline=20.60ms`, `Tiered=23.92ms`, `FVR=0.00%` | 50 | 0 | 70 | `{"NameError": 200}` | `sandbox.exec`: 200, `smt._heuristic`: 560, `prober.group`: 880 | 库结晶部分 **`INVALID_PENDING_S4`** |
| `experiments/run_memory_consolidation.py` | `generic_enumeration (d=3)` | `Baseline=15.78ms`, `Tiered=14.99ms`, `FVR=0.00%` | 40 | 0 | 60 | `{"NameError": 15}` | `sandbox.exec`: 15, `smt._heuristic`: 480, `prober.group`: 720 | 库结晶部分 **`INVALID_PENDING_S4`** |
| `experiments/run_memory_consolidation.py` | `generic_enumeration (d=4)` | `Baseline=27.54ms`, `Tiered=23.99ms`, `FVR=0.00%` | 54 | 0 | 94 | `{"NameError": 100}` | `sandbox.exec`: 100, `smt._heuristic`: 720, `prober.group`: 1020 | 库结晶部分 **`INVALID_PENDING_S4`** |
| `experiments/run_policy_evolution.py` | `leaky_templates` | `Online Solved Rate for Top Policy: 3/3` | 0 | 0 | 0 | `{}` | `{}` | **含答案泄漏，仅作参考** |
| `experiments/run_policy_evolution.py` | `generic_enumeration (d=3)` | **`Online Solved Rate for Top Policy: 1/3`** | 0 | 0 | 0 | `{}` | `{}` | 纯一阶枚举下解决 1/3 |
| `experiments/run_policy_evolution.py` | `generic_enumeration (d=4)` | **`Online Solved Rate for Top Policy: 3/3`** | 3 | 0 | 3 | `{}` | `prober.group`: 45 | $d=4$ 下首次真正触发了 3 次 System 2 Oracle 查询（此前被泄漏模板掩盖） |
| `experiments/run_env_simulation.py` | 全部 3 种模式 | 仅测试 GridWorld/Physics，不调用 `CEGISLoop` | 0 | 0 | 0 | `{}` | `{}` | 与 `proposer_mode` 无关（定于 S7 清理） |
| `experiments/run_perception_frontend.py` | 全部 3 种模式 | 仅测试 `PerceptionFrontend` 字典拷贝，不调用 `CEGISLoop` | 0 | 0 | 0 | `{}` | `{}` | 与 `proposer_mode` 无关（定于 S7 清理） |

---

## 7. 关键发现与未解决问题（留待后续阶段）

1. **回答 S1 验收问题（"在没有模板泄漏的情况下，系统到底能解多少任务"）**：
   - **纯本地 LLM (`llm_only`, `Qwen2.5-Coder-3B-Instruct-4bit`)**：**0 / 13 (0.00%)**（26 个任务条目中 **0 / 26 = 0.00%**）。
   - **纯一阶自底向上枚举 (`generic_enumeration`, `max_depth=3`，不含高阶 `lambda`)**：**5 / 13 (38.46%)**（26 个任务条目中 **9 / 26 = 34.62%**），解决全部 4 个一阶归约/结构任务（`list_sum`, `list_length`, `list_reverse`, `list_tail_elements`）以及 1 个深度 3 的一阶组合任务（`reverse_and_tail`，该任务在 `leaky_templates` 下反而失败）。
   - **含单层高阶原语的自底向上枚举 (`generic_enumeration`, `max_depth=4`)**：**11 / 13 (84.62%)**（26 个任务条目中 **24 / 26 = 92.31%**），可解全部深度 $\le 4$ 的单算子任务及 `reverse_and_tail`，但**无法解决任何深度 $\ge 5$ 的高阶复合任务**（`filter_evens_and_sum` 与 `filter_positive_and_sum` 均 `collapsed`）。
   - **复合任务要真正被解决（而非靠 `template:#27` 作弊）**，必须依靠 **Stage S4 的真实库学习/算子结晶（System 3）** 将深度 4 的 `(filter (lambda (a) (is_even a)) x)` 与 `(filter (lambda (a) (gt a 0)) x)` 结晶并注册进 `DSLInterpreter` 后，在深度 3 以 `(sum (op_filter x))` 形式合成！这为 Stage S4 的库学习消融实验建立了完全诚实、无泄漏的零基线（没有库学习时，高阶复合任务 `filter_evens_and_sum` 和 `filter_positive_and_sum` 在 $d \le 4$ 下通过率为 **0/2 = 0.0%**）。

2. **留待后续阶段解决的问题**：
   - **Stage S2**：修复 System 2 确定性噪声模型、版本空间塌缩与重提议、MDL 先验温度、语义等价类合并、IG=0 提前停止（`INDISTINGUISHABLE`）、诚实状态码（消除 `filter_positive` 在 $d=3$ 下未收敛时的伪トップ候选混淆）及探针异常禁用集。
   - **Stage S3**：扩展 Z3 对 list 有界展开的支持，修复 `smt_distinguisher._heuristic_distinguishing` 与 `bayesian_prober.group_by_output` 的探针类型错配（消除上表中数百次 `TypeError`）。
   - **Stage S4**：将结晶算子真正注册进 `DSLInterpreter` 与 `SymbolicEnumerator`，解除所有 `"INVALID_PENDING_S4"` 对照臂，验证结晶库能否让 `filter_evens_and_sum` 与 `filter_positive_and_sum` 从 0% 提升至通过。
