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
