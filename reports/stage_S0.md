# Stage S0 阶段报告：诊断基础设施 (`Diagnostics`) 与静默异常曝光 (`stage_S0.md`)

> **对应审计项**：H5 (`smt_distinguisher.py:122,160,199,265`)、H8 (`cegis_loop.py:45-64,164,236`)、H11 (`sandbox.py:29,40`)、H12 (`value_compressor.py:31,71,114,126`) 及全仓 `except Exception` 横向清理。

---

## 1. 本阶段完成了什么（What Was Done）

1. **统一诊断数据结构 (`Diagnostics`)**：
   - 在 [`eve3/models.py:22-125`](file:///Users/prognosticatex/Desktop/eve-3/eve3/models.py#L22-L125) 新增 `Diagnostics` 数据类、全局汇总器 `GLOBAL_DIAGNOSTICS` 及上下文作用域 `active_diagnostics_scope`，支持属性访问与字典访问（`to_dict()` / `__getitem__`），包含全部 S0 规定字段：
     - `oracle_queries`：Oracle 调用总次数（**在调用 `oracle_fn` 前计数，包含抛出异常的失败调用**）
     - `z3_calls`：实际触发 `s.check()` 的 Z3 求解器调用次数
     - `z3_fallbacks`：因 AST 不支持、Z3 未安装、Z3 抛异常或未返回区分输入而回退至启发式边界探针的次数
     - `z3_timeouts`：Z3 返回 `z3.unknown`（超时/取消）的次数
     - `llm_calls`：实际调用 `mlx_lm.generate` 的次数
     - `sandbox_rejections`：按具体异常类型（`Dict[str, int]`，如 `NameError`、`DSLParserError`、`TypeError`、`ExecutionTimeoutError`）分类的沙箱拒绝计数
     - `swallowed_errors`：按代码位置（`Dict[str, int]`）分类的被捕获异常计数，同时在 `swallowed_error_details` 中记录 `{location: {ExcType: count}}` 明细并写入 `logger` 日志
2. **在 `CEGISResult` 与各核心组件暴露 `diagnostics`**：
   - [`eve3/system2_falsifier/cegis_loop.py:30-56,90-295`](file:///Users/prognosticatex/Desktop/eve-3/eve3/system2_falsifier/cegis_loop.py#L30-L56)：`CEGISResult.diagnostics` 保存单次 `run_synthesis` 作用域内的完整诊断计数。
   - `SMTDistinguisher.diagnostics`、`ProgramSandbox.diagnostics`、`ValueCompressor.diagnostics`、`HypothesisGenerator.diagnostics`、`BayesianProber.diagnostics`、`SymbolicEnumerator.diagnostics`、`Curriculum.diagnostics`、`NoisyLikelihoodEngine.diagnostics` 均暴露组件级计数器并同步汇总至当前活跃 `CEGISLoop` 作用域与 `GLOBAL_DIAGNOSTICS`。
3. **全仓消除 `except Exception: pass/continue`（铁律 3）**：
   - 将 `eve3/` 下全部 **29 处** 宽泛 `except Exception`（含 `sandbox.py` 中的 `except (..., Exception):`）全部替换为**具体异常类型元组 + `diagnostics.record_swallowed_error(location, exc)` + `logger.debug`/`logger.warning`**。
4. **新增 S0 回归测试（先红后绿）**：
   - 新增 [`tests/test_stage_s0_diagnostics.py`](file:///Users/prognosticatex/Desktop/eve-3/tests/test_stage_s0_diagnostics.py)（6 个测试，含 AST 静态扫描器強制禁止 `eve3/` 中出现任何 `except:` 或 `except Exception:`）。

---

## 2. 验收证据：运行 Test Suite 与 Experiments 暴露的静默失败统计

执行脚本：`/Users/prognosticatex/.gemini/antigravity/brain/b1d1b2d0-c8fa-469b-bdb9-515766625a95/scratch/run_s0_diagnostics_report.py`
原始 JSON 记录：`/Users/prognosticatex/.gemini/antigravity/brain/b1d1b2d0-c8fa-469b-bdb9-515766625a95/scratch/s0_diagnostics_output.json`

### 2.1 全量单元测试套件（86 个测试：原有 80 + 新增 6，100% 通过）诊断计数器

```json
{
  "tests_run": 86,
  "failures": 0,
  "errors": 0,
  "skipped": 0,
  "diagnostics": {
    "oracle_queries": 357,
    "z3_calls": 2,
    "z3_fallbacks": 926,
    "z3_timeouts": 0,
    "llm_calls": 0,
    "sandbox_rejections": {
      "NameError": 648,
      "DSLParserError": 1,
      "TypeError": 1
    },
    "swallowed_errors": {
      "smt_distinguisher._heuristic_distinguishing": 5602,
      "bayesian_prober.group_by_output": 7232,
      "sandbox.filter_valid_candidates.exec": 649,
      "value_compressor.extract_candidate_abstractions": 5,
      "smt_distinguisher.find_distinguishing_input": 2,
      "cegis_loop.oracle_query": 1,
      "sandbox.filter_valid_candidates.parse": 1
    },
    "swallowed_error_details": {
      "smt_distinguisher._heuristic_distinguishing": { "TypeError": 5602 },
      "bayesian_prober.group_by_output": { "TypeError": 7232 },
      "sandbox.filter_valid_candidates.exec": { "NameError": 648, "TypeError": 1 },
      "value_compressor.extract_candidate_abstractions": { "NameError": 4, "DSLParserError": 1 },
      "smt_distinguisher.find_distinguishing_input": { "AttributeError": 2 },
      "cegis_loop.oracle_query": { "ValueError": 1 },
      "sandbox.filter_valid_candidates.parse": { "DSLParserError": 1 }
    }
  }
}
```

### 2.2 `experiments/` 下全部 9 个实验脚本诊断计数器汇总表

| 实验脚本 (`experiments/*.py`) | `oracle_queries` | `z3_calls` | `z3_fallbacks` | `llm_calls` | `sandbox_rejections` | `swallowed_errors`（按位置与异常类型） |
| :--- | :---: | :---: | :---: | :---: | :--- | :--- |
| `run_autonomous_agi_loop.py` | 25 | **0** | 35 | **0** | `{}` | `_heuristic_distinguishing`: 280 (`TypeError`)<br>`group_by_output`: 440 (`TypeError`) |
| `run_autonomous_curriculum.py` | 66 | **0** | 126 | **0** | **`{"NameError": 368}`** | `_heuristic_distinguishing`: 1008 (`TypeError`)<br>`group_by_output`: 1296 (`TypeError`)<br>`sandbox.exec`: **368 (`NameError`)** |
| `run_continual_learning.py` | 128 | **0** | 288 | **0** | `{}` | `_heuristic_distinguishing`: 2304 (`TypeError`)<br>`group_by_output`: 2688 (`TypeError`) |
| `run_env_simulation.py` | 0 | 0 | 0 | 0 | `{}` | `{}` |
| `run_full_ablation.py` | 32 | **0** | 48 | **0** | **`{"NameError": 80}`** | `_heuristic_distinguishing`: 384 (`TypeError`)<br>`group_by_output`: 576 (`TypeError`)<br>`sandbox.exec`: **80 (`NameError`)** |
| `run_library_ablation.py` | 24 | **0** | 40 | **0** | **`{"NameError": 16}`** | `_heuristic_distinguishing`: 320 (`TypeError`)<br>`group_by_output`: 448 (`TypeError`)<br>`sandbox.exec`: **16 (`NameError`)** |
| `run_memory_consolidation.py` | 50 | **0** | 70 | **0** | **`{"NameError": 200}`** | `_heuristic_distinguishing`: 560 (`TypeError`)<br>`group_by_output`: 880 (`TypeError`)<br>`sandbox.exec`: **200 (`NameError`)** |
| `run_perception_frontend.py` | 0 | 0 | 0 | 0 | `{}` | `{}` |
| `run_policy_evolution.py` | 0 | 0 | 0 | 0 | `{}` | `{}` |

---

## 3. S0 诊断计数器暴露出的四大核心静默故障（直接验证 Phase 1 审计结论）

1. **System 1 ↔ System 3 彻底断路（648 次测试 + 664 次实验 `NameError` 沙箱拒绝，对应 H14 / S4）**：
   - 在 `run_library_ablation.py`（16 次）、`run_full_ablation.py`（80 次）、`run_memory_consolidation.py`（200 次）、`run_autonomous_curriculum.py`（368 次）中，System 3 结晶出的算子（如 `map_add`, `abs_list_increment_all`, `base_abs_filter_positive_0`）被 System 1 拼入候选表达式（如 `(map_add 1 x)`），但由于**从未注册进 `DSLInterpreter.base_env`**，在沙箱执行时 100% 抛出 `NameError: Unknown primitive or function '...' in environment` 并被旧代码 `except Exception:` 静默吞掉！这意味着此前所有实验声称的“知识库结晶复用”在执行层全部静默失败。
2. **System 3 动态 AST 模式挖掘 100% 崩溃（4 次 `NameError: name 'LambdaNode' is not defined`，对应 H12 / S5）**：
   - 在 `test_crystallizer.py` 中对 4 个验证程序调用 `ValueCompressor.extract_candidate_abstractions` 时，每次均抛出 `NameError: name 'LambdaNode' is not defined`（且 `patterns = []` 调用 `.add()` 会抛 `AttributeError`），被 `value_compressor.py:114` 静默吞掉后仅返回硬编码的 3 个 `seed_patterns`。
3. **System 2 Z3 求解器在实验中调用数为 0，在单测中 100% 崩溃回退（对应 H5 / S3）**：
   - 在 9 个实验脚本中，`z3_calls = 0, z3_fallbacks = 607`：因为实验任务全部使用 `map`/`filter`/`sum`/`reverse`，而 `_ast_to_z3_seq` 仅编码了 `length` 和 `tail`，导致 `expr1 is None`，Z3 从未被实际调用！
   - 在单测中仅有的 2 次 `z3_calls`（针对 `(+ x 1)` vs `(+ x 2)`）全部在 `m[x].as_long()` 处抛出 `AttributeError: 'NoneType' object has no attribute 'as_long'`，100% 退化为启发式边界采样。
4. **探针池类型不匹配导致逾 24,000 次静默 `TypeError`（对应 H6 / S3）**：
   - `SMTDistinguisher.generate_default_probes()` 将标量整数探针（`0, 1, -1, 2, ...`）与列表探针混在一起，导致对列表程序求值时在 `bayesian_prober.group_by_output`（测试中 7,232 次）和 `smt_distinguisher._heuristic_distinguishing`（测试中 5,602 次）触发海量 `TypeError`，並在 `group_by_output` 中将所有报错候选归入同一个 `"__EXEC_ERROR__"` 等价类，污染了信息增益计算。

---

## 4. 仍未解决的问题（留待 S1–S8 按序修复）

- **S1**：`generator.py` 27 个启发式模板与 `SymbolicEnumerator` 硬编码模板的答案泄漏审查与 `proposer_mode` 隔离、`mlx-lm` 安装与 `sampler` API 修复。
- **S2**：确定性/噪声后验模型显式化、塌缩重提议、语义等价类合并、IG=0 提前停止（`INDISTINGUISHABLE`）、诚实状态与 `MATHEMATICS.md` 修正。
- **S3**：`m.eval(x, model_completion=True)` 修复、Z3 输出解释器复核、有界展开与支持矩阵对齐、探针池签名聚类。
- **S4**：结晶算子注册进 `DSLInterpreter`、可终止沙箱超时、资源上限（拦截 `fold` 倍增）、库名额上限与回滚联通。
- **S5**：`ValueCompressor` 动态挖掘修复、顺序无关集合目标函数、小规模穷举对比、复用饱和/衰减、消除手工注入 `map_add`。
- **S6–S8**：反事实回放支撑集检查、不可变门禁配置、测试体系加固与正式多种子实验。
