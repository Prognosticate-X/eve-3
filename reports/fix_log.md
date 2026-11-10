# EVE-3 第 2 阶段：测试与代码修改日志 (`fix_log.md`)

> **铁律 2 声明**：不得削弱、删除或放宽现有测试断言。需要修改现有测试时，必须在本日志中逐条说明理由、证据行号与前后断言对比。
> **铁律 5 声明**：每一个被审计引用的数字，都要迁移成 tests/ 下的回归测试（修复前红、修复后绿），或未修复前以 `xfail(strict=True)` 严格锁定。

---

## Stage S0：诊断基础设施 (`Diagnostics`) 与消除静默异常吞没

### 1. 现有测试修改记录
- **修改数**：**0**（原有的 80 个单元测试未做任何修改、删除或断言放宽，全部原样通过）。

### 2. 新增回归测试记录
- 新增文件：`tests/test_stage_s0_diagnostics.py`（共 6 个测试，遵循“先红后绿”流程）：
  1. `test_cegis_result_exposes_all_required_diagnostics_fields`：断言 `CEGISResult.diagnostics` 暴露 `oracle_queries`、`z3_calls`、`z3_fallbacks`、`z3_timeouts`、`llm_calls`、`sandbox_rejections`、`swallowed_errors`。
  2. `test_oracle_queries_counts_failed_oracle_invocations`：对应 `reports/audit.md` H8（`cegis_loop.py:164`），断言当 `oracle_fn` 抛出异常时仍计入 `oracle_queries` 且记录 `swallowed_errors["cegis_loop.oracle_query"]`。
  3. `test_sandbox_rejections_categorized_by_exception_type`：对应 `reports/audit.md` H11（`sandbox.py:29,40`），断言沙箱按具体异常类型（`DSLParserError`、`TypeError`、`NameError` 等）分类统计 `sandbox_rejections`。
  4. `test_smt_distinguisher_records_z3_calls_and_fallbacks`：对应 `reports/audit.md` H5（`smt_distinguisher.py:100,122,126`），断言 `z3_calls` 与 `z3_fallbacks` 被精确计数。
  5. `test_value_compressor_records_swallowed_errors_in_diagnostics`：对应 `reports/audit.md` H12（`value_compressor.py:114`），断言 AST 模式挖掘中的异常被计入 `swallowed_errors["value_compressor.extract_candidate_abstractions"]`。
  6. `test_no_bare_except_exception_in_eve3_codebase`：对应铁律 3，使用 Python `ast` 模块静态扫描 `eve3/`、`experiments/` 与 `scripts/` 下所有 `.py` 文件，断言不存在任何 `except:`、`except Exception:`、`except BaseException:`、含 `Exception` 的元组捕获或 `contextlib.suppress(Exception)`。

### 3. S0 各修复项的修复前失败输出（Pre-fix Failure Outputs）

#### 修复前 H8（`oracle_fn` 抛出异常不计入查询）：
```text
AssertionError: 0 not greater than or equal to 1 : CEGISResult.diagnostics.oracle_queries was 0 when oracle raised ValueError
```

#### 修复前 H11（沙箱异常静默吞没且不分类）：
```text
AssertionError: 'DSLParserError' not found in sandbox.diagnostics.sandbox_rejections (sandbox_rejections was empty dict {})
```

#### 修复前 H5（Z3 求解器回退未计数）：
```text
AssertionError: 0 not greater than or equal to 1 : dist.diagnostics.z3_fallbacks was 0 on unsupported primitive (sum x)
```

#### 修复前 H12（公共子表达式挖掘异常静默吞没）：
```text
AssertionError: 'value_compressor.extract_candidate_abstractions' not in vc.diagnostics.swallowed_errors
```

---

## Stage S0.1 / S1.1 补课：仓库卫生与遗留基础设施修复

### 1. 现有测试修改记录
- **修改数**：**0**。原有 86 个测试断言未做任何放宽。

### 2. 新增与扩充回归测试记录
- **扩充 `test_no_bare_except_exception_in_eve3_codebase`**：静态分析扫描范围从 `eve3/` 扩展至 `experiments/` 与 `scripts/`，覆盖 `except (..., Exception)`、`BaseException` 与 `contextlib.suppress(Exception)`，违规数恒为 0。
- **新增 `test_threadpool_worker_exceptions_recorded_in_cegis_diagnostics`**：验证在 `ThreadPoolExecutor` 工作线程内求值崩溃的候选程序（如 `ZeroDivisionError`、`TypeError`、超时）其异常被完整上报并计入 `diagnostics.sandbox_rejections` 与 `diagnostics.swallowed_errors["sandbox.filter_valid_candidates.exec"]`。
- **新增 `test_swallowed_errors_ratchet_only_decreases` 与 `tests/diagnostics_ratchet_baseline.json`**：建立诊断棘轮基线，断言各位置的被吞异常计数在后续重构中只降不升（上限被严格封死）。
- **新增 `tests/test_audit_p0_regressions.py`**：将 `reports/audit.md` 中的 5 项未修复 P0 缺陷（H3 Laplace 平滑抬高反例、H4 塌缩判定失效、H5 Z3 seq 理论不支持列表高阶函数、H11 结晶算子未注册导致 NameError、H12 模式挖掘崩溃）编写为 5 个使用 `@pytest.mark.xfail(strict=True)` 装饰的严格回归测试。当前在未修复代码上全部 strictly failed 并被标记为 XFAIL。

---

## Stage S1：评测完整性与消除模板答案泄漏（H9 / H10）

### 1. 现有测试修改记录
- **修改数**：**0**（原有的 86 个单元测试未做任何修改、删除或断言放宽，全部原样通过）。
- **实验脚本参数扩展说明**：在 `experiments/run_continual_learning.py:35,65` 中，为 `run_continual_learning_experiment(proposer_mode: str = "leaky_templates")` 增加了可选参数 `proposer_mode`。原因：如 `reports/audit.md` H15（`audit.md:273-286`）所证实，在 Stage S4/S6 修复 `run_continual_learning.py`（向 `CEGISLoop` 注入真实的 `KnowledgeLibrary` 与 `AdapterBank`）之前，该脚本 Step 0 (`symbolic_only`) 与 Step 4 (`hybrid`) 之间的 `+33.33%` FWT 增益完全来自 `leaky_templates` 的第 #27 号模板泄漏（在 `generic_enumeration` 下 `fwt_delta == 0.00%`）。保留函数签名默认参数为 `"leaky_templates"` 使未进入 S6 前的 `tests/test_continual_learning.py` 无需修改断言即可通过，同时 S1 评测脚本显式传入 `generic_enumeration` 完成了无泄漏对比评测（详见 `reports/stage_S1.md` 第 6 节）。

### 2. 新增回归测试记录
- 新增文件：`tests/test_stage_s1_proposer_modes.py`（共 5 个测试，遵循"先红后绿"流程）：
  1. `test_proposer_mode_config_defaults_to_non_leaky`：断言 `EveConfig().proposer_mode` 默认为 `"generic_enumeration"`（非 leaky），且支持全部 4 种合法模式并拒绝非法模式。
  2. `test_generic_enumeration_orders_by_ast_depth_and_tracks_provenance`：断言 `SymbolicEnumerator` 在 `generic_enumeration` 模式下严格按 AST 深度单调递增生成候选，記録 `enum:depth=d:#idx` 来源，且不包含深度 5 的硬编码泄漏模板 `(sum (filter (lambda (a) (is_even a)) x))`。
  3. `test_leaky_vs_generic_enumeration_on_held_out_composition`：对应 `reports/audit.md` H9/H10（`generator.py:132-165`、`enumerator.py:49-95`），断言在 `list_composition` 上，`filter_evens_and_sum` 仅在 `leaky_templates` 下因 `template:#27` 泄漏通过而在 `generic_enumeration` 下 `collapsed`；反之 `reverse_and_tail` (`(tail (reverse x))`) 在 `leaky_templates` 下 `collapsed`，而在 `generic_enumeration` 下于 `enum:depth=3` 通过。
  4. `test_llm_only_mode_never_falls_back_to_heuristic_or_enumerator`：断言 `llm_only` 模式在 LLM 返回空或失败时严禁静默回退到启发式模板或符号枚举器。
  5. `test_mlx_llm_smoke_test_sampler_compatibility_and_telemetry`：真实调用本机 `mlx-lm==0.32.2` 与 `mlx-community/Qwen2.5-Coder-3B-Instruct-4bit`，断言 `sampler = make_sampler(temp=...)` 正常工作、`llm_calls > 0`、`swallowed_errors["generator._generate_raw_proposals"] == 0`，且记录延迟与候选语法合法率遥测。

### 3. S1 各修复项的修复前失败输出（Pre-fix Failure Outputs）

#### 修复前 S1.2（`proposer_mode` 配置项缺失）：
```text
AttributeError: 'EveConfig' object has no attribute 'proposer_mode'
```

#### 修复前 S1.3（`reverse_and_tail` 在旧枚举器中无法通过）：
```text
AssertionError: VerificationStatus.COLLAPSED != VerificationStatus.HELD_OUT_TESTS_PASSED : reverse_and_tail failed in generic enumeration
```

#### 修复前 S1.4（`mlx_lm.generate` temp 参数崩溃导致静默回退）：
```text
TypeError: generate_step() got an unexpected keyword argument 'temp'
AssertionError: 0 not greater than 0 : gen.diagnostics.llm_calls was 0 due to silent fallback to heuristic synthesizer
```

#### 修复前 S1.4（`llm_only` 模式下静默回退到启发式模板）：
```text
AssertionError: CandidateProgram(code_str='(reverse x)', created_by='heuristic') created_by is 'heuristic', expected 'llm'
```

---

## 3. Stage S1.1 修复记录与修复前失败输出（Pre-fix Failure Outputs）

### 1. S1.1-A（仓库卫生与 S0.1 遗留项）
- **修复内容**：
  - 扩展 AST 检查覆盖 `eve3/`、`experiments/`、`scripts/` 下的 `except (..., Exception)`、`BaseException` 与 `contextlib.suppress(Exception)`。
  - 新增线程池工作线程内吞异常计入当前 `CEGISResult.diagnostics` 的回归测试。
  - 新增 `swallowed_errors` 棘轮测试（基线存入 `tests/diagnostics_ratchet_baseline.json`，只降不升）。
  - 将审计报告 P0 数值（H3/H4/H5/H11/H12）做成 `@pytest.mark.xfail(strict=True)` 回归测试（`tests/test_audit_p0_regressions.py`，5 项全部严格 xfail）。
  - 固定运行硬件记录于 `reports/env.md`（澄清物理机器为 Apple M1 Max 64GB，S1 文本中 "M4 16GB" 系笔误）。
- **修复前失败输出**：
  - AST 宽泛异常漏检：
    ```text
    AssertionError: Lists differ: ['eve3/search/enumeration_full.py:237 except Exception:'] != []
    ```
  - 线程池异常漏记：
    ```text
    AssertionError: 0 == 0 : Thread pool worker exception not recorded in CEGISResult.diagnostics.swallowed_errors
    ```
  - 棘轮测试超限失败：
    ```text
    AssertionError: Current swallowed_errors count 1935 exceeded ratchet baseline 0 for smt_distinguisher.py:112
    ```

### 2. S1.1-B（探针类型修复与错误隔离，提前自 S3）
- **修复内容**：
  - 在 `eve3/system2_falsifier/smt_distinguisher.py` 中引入 `domain_hint`（`"list"` vs `"int"`），探针候选池按输入域分区生成。
  - 在 `eve3/system2_falsifier/bayesian_prober.py:86` 中将执行异常候选隔离为独立错误分区 `f"__ERROR_{type(exc).__name__}_{idx}__"`，严禁并入公共 `__EXEC_ERROR__`。
- **修复前失败输出**：
  - 探针调用域不匹配导致大量 TypeError：
    ```text
    TypeError: unsupported operand type(s) for +: 'int' and 'list'
    [Recorded 1,323 times at smt_distinguisher.py:112 and 612 times at bayesian_prober.py:86]
    ```
  - 错误合并导致虚假信息增益：
    ```text
    AssertionError: '__EXEC_ERROR__' unexpectedly found in output partition classes
    ```
  - 修复后对比：两处 TypeError 被吞计数均严格归零（`1,935 -> 0`）。

### 3. S1.1-C（枚举器诚实化与基线强化）
- **修复内容**：
  - 常量池去基准化：从 `{0, 1, 2, 3, 10, -1, 100}` 彻底清除，改为 `{0, 1} ∪ 当前任务训练样例提取数值`（`extract_constants_from_examples`）。
  - 新增真正的自底向上枚举基线 `BottomUpOEEnumerator`（`eve3/search/enumeration_full.py`），支持任意嵌套与观测等价（OE）剪枝，预算至多 size=9 或 60s。
  - 建立文法外泛化基准 `benchmarks/ood_constants.json`（常量含 4, 6, 7, 3）与高歧义基准 `benchmarks/high_ambiguity.json`（初始仅 1 样例）。
- **修复前失败输出**：
  - `leaky_templates` 在文法外常量任务上全部崩溃：
    ```text
    AssertionError: 0 != 4 : leaky_templates scored 0/4 (0.0%) on benchmarks/ood_constants.json
    ```
  - 旧枚举器硬编码深度限制导致组合任务失败：
    ```text
    VerificationStatus.COLLAPSED != VerificationStatus.HELD_OUT_TESTS_PASSED : filter_evens_and_sum collapsed at depth 4
    ```
  - `enumeration_full` 验证：`filter_evens_and_sum`（224.3ms）、`filter_positive_and_sum`（1258.1ms）、`reverse_and_tail`（4.5ms）均成功解出，证实无需库学习即可解出。

### 4. S1.1-D（LLM 公平测试与封闭核算）
- **修复内容**：
  - 构建严密非基准 few-shot 提示词库 `prompts/fewshot.json` 与测试 `tests/test_fewshot_integrity.py`，保证与 13 任务零重合。
  - 在本机 MLX 环境对 Qwen2.5-Coder-3B-Instruct-4bit 运行 4 组配置（$k \in \{8, 16\} \times \text{temp} \in \{0.7, 1.0\}$），支持至多 2 轮报错反馈修补。
  - 实施严格封闭核算断言：`raw_candidates == syntax_invalid + exec_error + wrong_output + passed`。
- **修复前失败输出**：
  - Few-shot 污染检测：
    ```text
    AssertionError: Fewshot task input/output overlaps with benchmark task list_increment_all
    ```
  - 封闭核算不守恒：
    ```text
    AssertionError: Accounting mismatch: raw (101) != syntax_invalid (21) + exec_error (13) + wrong_output (52) + passed (14)
    ```

---

## 4. Stage S2：System 2 数学与流程正确性修复（H3, H4, H5, H2, 随机对照臂）

### 1. 现有测试适配说明（遵循铁律 2）
- **`tests/test_audit_p0_regressions.py`**：
  - `test_h3`、`test_h4`、`test_h5` 在代码修复后严格实现预期逻辑，移除了 `@pytest.mark.xfail(strict=True)` 装饰器，直接转绿为正常 PASS。
  - 在 `test_h4` 中补充了原作者在注释中声明但遗漏的候选池限制 mock，使测试真实覆盖"全候选被证伪后重提议耗尽并返回 COLLAPSED"的闭环逻辑。
- **`tests/test_prober.py`**：
  - `test_posterior_update_and_collapse_prevention` 显式传入新增参数 `noise_model="noisy(1e-4)"`，以测试带 Laplace 平滑的噪声更新场景，断言保持原样不变。

### 2. 新增回归测试记录
- **`tests/test_stage_s2_bayesian.py`**：
  - `test_deterministic_posterior_strictly_zero_on_falsification`：断言在 `deterministic` 模式下被证伪候选后验严格归零且 `falsified=True`, `status=REJECTED`。
  - `test_deterministic_posterior_when_all_falsified_returns_all_zeros`：断言全候选被证伪时返回严格全零分布 `[0.0, ...] `。
  - `test_noisy_mode_preserves_laplace_smoothing`：断言在显式 `noisy(eps)` 模式下 Laplace 平滑正常保留。
- **`tests/test_stage_s2_collapse.py`**：
  - `test_collapse_detected_when_all_candidates_falsified_and_repropose_exhausted`：验证全候选证伪且重提议无新候选时正确返回 `COLLAPSED` 与 `verified_program=None`。
  - `test_active_repropose_recovers_when_better_candidate_found`：验证通过累积反例进行重提议能够成功恢复并找到真程序。
- **`tests/test_stage_s2_mathematics.py`**：
  - 针对 H2 编写 4 项数值单元测试，手算 3 候选、2/3 分区及非均匀先验下的信息增益（IG），实测误差 $< 10^{-6}$。
- **`tests/test_stage_s2_random_probes.py`**：
  - 测试 `probe_strategy` 的全部三种模式（`none`, `random`, `bayesian_ig`）。

### 3. S2 各修复项的修复前失败输出（Pre-fix Failure Outputs）

#### 修复前 H3（Laplace 平滑抬高已证伪程序）：
```text
AssertionError: 0.001994015956119673 != 0.0 : Falsified program posterior should be 0.0, but got 0.001994015956119673 (remains top-1!)
```

#### 修复前 H4（假设塌缩判定失效）：
```text
AssertionError: <VerificationStatus.HELD_OUT_TESTS_PASSED> != <VerificationStatus.COLLAPSED> : Expected status COLLAPSED when candidates fail, got held_out_tests_passed
```

#### 修复前 H5（SMT 求解器缺失高阶列表展开）：
```text
AssertionError: 'heuristic_boundary' != 'smt_symbolic'
- heuristic_boundary
+ smt_symbolic
 : Expected probe from Z3 SMT symbolic solve, got heuristic_boundary
```

---

## 5. Stage S3：System 1 提议器质量与鲁棒性修复（H1, H11, H9）

### 1. 现有测试适配说明（遵循铁律 2）
- **修改数**：**0**（所有先前阶段的测试未做任何删除或断言放宽，继续 100% 全量通过）。

### 2. 新增回归测试记录
- **`tests/test_stage_s3_prior.py`**（4 个测试，遵循“先红后绿”流程）：
  1. `test_config_prior_mode_validation`：验证 `EveConfig` 的 `prior_mode` 校验，支持 `"mdl"`, `"uniform"`, `"llm"`，非法模式抛出 `ValueError`。
  2. `test_uniform_prior_mode`：验证 `BayesianProber` 在 `uniform` 模式下为所有候选程序赋予均匀先验 $1/N$。
  3. `test_mdl_prior_mode_with_custom_decay`：验证 `mdl` 模式下结合 `mdl_prior_decay` 动态缩放描述长度惩罚项。
  4. `test_llm_prior_mode_uses_candidate_logprob`：验证 `llm` 模式下依据候选的 `logprob` 进行 softmax 归一化分配先验。
- **`tests/test_stage_s3_sandbox_security.py`**（5 个测试，遵循“先红后绿”流程）：
  1. `test_timeout_is_non_blocking`：验证硬超时机制在超时发生时立即返回（实测 $<0.35$s），不阻塞主线程等待后台 worker 执行。
  2. `test_fold_memory_bomb_caught_by_size_limit`：验证 `(fold (lambda (acc item) (concat acc acc)) [1] x)` 列表指数倍增在 12 步内被 `ExecutionSizeLimitExceeded` 安全拦截。
  3. `test_fold_integer_squaring_bomb_caught_by_bit_limit`：验证 `(fold (lambda (acc item) (* acc acc)) 2 x)` 整数连续平方在 12 步内超过 2048 位被 `ExecutionSizeLimitExceeded` 安全拦截。
  4. `test_call_chain_recursion_limit`：验证深层嵌套调用链超过 `max_recursion_depth` 时被 `ExecutionRecursionLimitExceeded` 安全拦截。
  5. `test_sandbox_filters_and_records_all_security_rejections`：验证 `ProgramSandbox` 安全捕获全部超时/内存/递归炸弹并分类记录进 `diagnostics.sandbox_rejections`。
- **`tests/test_stage_s3_dedup.py`**（6 个测试，遵循“先红后绿”流程）：
  1. `test_ast_canonical_sexpr_alpha_equivalence`：验证 `to_canonical_sexpr` 将形参按词法作用域规范化为 `$0, $1...`，实现 `(map (lambda (a) (+ a 1)) x)` 与 `(map (lambda (b) (+ b 1)) x)` 等价。
  2. `test_nested_lambdas_alpha_equivalence`：验证多层嵌套 lambda 的规范化一致性。
  3. `test_candidate_program_equality_and_alpha_equivalence`：验证 `CandidateProgram.__eq__` 与 `__hash__` 严格基于 $\alpha$-等价，消融同义候选。
  4. `test_sandbox_deduplicates_alpha_equivalent_candidates`：验证 `ProgramSandbox.filter_valid_candidates` 自动去重 $\alpha$-等价候选。
  5. `test_search_controller_deduplicates_alpha_equivalent_proposals`：验证 `SearchController.propose_candidates` 基于规范形式去重。
  6. `test_build_prompt_dynamically_aligns_candidate_count`：验证 `HypothesisGenerator.build_prompt` 动态反映请求的候选数 $k$，消除硬编码 5。

### 3. S3 各修复项的修复前失败输出（Pre-fix Failure Outputs）

#### 修复前 H1（先验模式不可配置与缺失 LLM/均匀支持）：
```text
AttributeError: 'EveConfig' object has no attribute 'prior_mode'
AssertionError: BayesianProber prior was not uniform
```

#### 修复前 H11（沙箱超时阻塞主线程与内存炸弹击穿）：
```text
ImportError: cannot import name 'ExecutionRecursionLimitExceeded' from 'eve3.dsl.ast'
AssertionError: Timeout blocked the main thread! Elapsed: 1.503s
AssertionError: did not raise ExecutionSizeLimitExceeded (memory bomb generated huge output)
```

#### 修复前 H9（$\alpha$-等价候选未去重与提示词硬编码）：
```text
AssertionError: ASTNode must implement to_canonical_sexpr
AssertionError: assert 3 == 1 (sandbox passed 3 duplicate alpha-equivalent programs)
TypeError: HypothesisGenerator.build_prompt() got an unexpected keyword argument 'num_candidates'
```

---

## 6. Stage S4：System 3 库学习真实性（H11, H12, H13, H14, S1.1-C）

### 1. 现有测试适配说明（遵循铁律 2）
- **修改数**：**0**（所有先前阶段的测试未做任何删除或断言放宽，继续 100% 全量通过）。
- **`tests/test_audit_p0_regressions.py` 严格转绿**：
  - 此前标记为 `@pytest.mark.xfail(strict=True)` 的全部 5 个 P0 回归测试在 Stage S2、S3、S4 逐个修复后，现已全部移除 `xfail` 标记，**彻底 100% 正式 PASS**！

### 2. 新增回归测试记录
- **`tests/test_stage_s4_operators.py`**（5 个测试，遵循“先红后绿”流程）：
  1. `test_default_crystallized_operators_execute_in_sandbox`：验证默认结晶算子（如 `op_increment_list`）在沙箱中成功执行，消除 `NameError`。
  2. `test_dynamic_operator_registration_from_sexpr`：验证动态解析 S-expression 表达式注册新算子并在沙箱中可执行。
  3. `test_parameterized_dynamic_operator_registration`：验证带参数的二元算子动态编译与注册执行。
  4. `test_search_controller_syncs_library_operators_to_sandbox`：验证搜索控制器自动将知识库结晶算子同步给沙箱。
  5. `test_h14_max_active_library_operators_cap`：验证 `max_active_library_operators` 容量截断机制，避免算子爆炸。
- **`tests/test_stage_s4_pattern_mining.py`**（3 个测试，遵循“先红后绿”流程）：
  1. `test_dynamic_lambda_pattern_mining_no_crash`：验证处理包含 `LambdaNode` 的高阶表达式时模式挖掘零崩溃。
  2. `test_dynamic_pattern_compression_savings`：验证从程序对中挖掘公共子表达式并正确计算 AST 压缩节约量。
  3. `test_arbitrary_nested_subpattern_mining`：验证深层嵌套 lambda 复合结构的子模式稳定提取。
- **`tests/test_stage_s4_submodular.py`**（3 个测试，遵循“先红后绿”流程）：
  1. `test_reuse_saturation_prevents_positive_feedback_lockin`：验证 `max_reuse_saturation=20.0` 阻止陈旧算子的复用权重无界攀升。
  2. `test_order_independent_library_benefit`：验证 `compute_weighted_benefit` 规范降序后对于任意输入排列顺序输出严格相同的集合价值。
  3. `test_better_new_abstraction_wins_over_stale_lower_saving_abstraction`：验证高压缩比新算子在次模选择中能够击败低节约量的老算子。

### 3. S4 各修复项的修复前失败输出（Pre-fix Failure Outputs）

#### 修复前 H11（结晶算子沙箱执行未定义）：
```text
AssertionError: 0 != 1 : Crystallized operator should execute successfully in sandbox when registered
NameError: 'op_increment_list' is not defined
```

#### 修复前 H12（模式挖掘处理 LambdaNode 崩溃与列表 add 异常）：
```text
WARNING: Swallowed NameError in extract_candidate_abstractions: name 'LambdaNode' is not defined
AttributeError: 'list' object has no attribute 'add'
```

#### 修复前 H13（次模集合函数计算结果强依赖于输入顺序）：
```text
AssertionError: Evaluation order caused asymmetry: f([c1, c2])=12.0 != f([c2, c1])=16.0
```

#### 修复前 H11-Dyn（自主演化循环动态结晶算子跨周期求值报 NameError）：
```text
NameError: Unknown primitive or function 'abs_synth_list_structural_189c81' in environment
NameError: Unknown primitive or function 'base_abs_synth_list_mapping_7942d8_2' in environment
```




