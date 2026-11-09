# Stage S1.1 — 启发式模板与枚举器硬编码模板答案泄漏逐项审查报告 (`template_leakage.md`)

> **生成时间**：2026-11-09  
> **审查范围**：
> 1. `eve3/system1_proposer/generator.py:132-165`（`HypothesisGenerator._heuristic_synthesizer` 的 27 个启发式模板）
> 2. `eve3/search/enumerator.py:49-95`（`SymbolicEnumerator.enumerate_candidates` 的 67 个硬编码/参数化枚举模板，其中 `list` 域 49 个、`int` 域 18 个）
> 3. `benchmarks/` 下全部 9 个任务 JSON 文件（共 26 个任务条目，去重后 13 个唯一 `task_id` / `reference_program`）：
>    - `benchmarks/dev_train.json`（2 任务）
>    - `benchmarks/dev_eval.json`（2 任务）
>    - `benchmarks/held_out_test.json`（3 任务）
>    - `benchmarks/list_functions.json`（6 任务）
>    - `benchmarks/families/list_mapping.json`（3 任务）
>    - `benchmarks/families/list_filtering.json`（3 任务）
>    - `benchmarks/families/list_reduction.json`（2 任务）
>    - `benchmarks/families/list_structural.json`（2 任务）
>    - `benchmarks/families/list_composition.json`（3 任务，标注 `is_held_out: true`）

---

## 1. 总体泄漏统计汇总

| 基准集 / 指标 | 任务条目数 | 被 `generator.py` 27 模板精确命中 (`== reference_program`) | 被 `enumerator.py` 模板精确命中 (`== reference_program`) | 被 `SearchController(hybrid)` 精确命中 |
|---|---:|---:|---:|---:|
| `benchmarks/dev_train.json` | 2 | **2 / 2 (100.0%)** | **2 / 2 (100.0%)** | **2 / 2 (100.0%)** |
| `benchmarks/dev_eval.json` | 2 | **2 / 2 (100.0%)** | **2 / 2 (100.0%)** | **2 / 2 (100.0%)** |
| `benchmarks/held_out_test.json` | 3 | **3 / 3 (100.0%)** | **3 / 3 (100.0%)** | **3 / 3 (100.0%)** |
| `benchmarks/list_functions.json` | 6 | **6 / 6 (100.0%)** | **6 / 6 (100.0%)** | **6 / 6 (100.0%)** |
| `benchmarks/families/list_mapping.json` | 3 | **3 / 3 (100.0%)** | **3 / 3 (100.0%)** | **3 / 3 (100.0%)** |
| `benchmarks/families/list_filtering.json` | 3 | **3 / 3 (100.0%)** | **3 / 3 (100.0%)** | **3 / 3 (100.0%)** |
| `benchmarks/families/list_reduction.json` | 2 | **2 / 2 (100.0%)** | **2 / 2 (100.0%)** | **2 / 2 (100.0%)** |
| `benchmarks/families/list_structural.json` | 2 | **2 / 2 (100.0%)** | **2 / 2 (100.0%)** | **2 / 2 (100.0%)** |
| `benchmarks/families/list_composition.json` (`is_held_out=true`) | 3 | **1 / 3 (33.3%)** | 0 / 3 (0.0%) | **1 / 3 (33.3%)** |
| **合计（全部 26 个任务条目）** | **26** | **24 / 26 (92.3%)** | **23 / 26 (88.5%)** | **24 / 26 (92.3%)** |
| **合计（去重后 13 个唯一任务）** | **13** | **11 / 13 (84.6%)** | **10 / 13 (76.9%)** | **11 / 13 (84.6%)** |

---

## 2. `generator.py` 的 27 个启发式模板逐项标注表

代码位置：`eve3/system1_proposer/generator.py:132-165` (`HypothesisGenerator._heuristic_synthesizer`)

| 序号 | 行号 | 启发式模板 (`code_str`) | 是否等于某 Benchmark `reference_program`（精确匹配） | 是否在全部 I/O 上语义等价于某 Benchmark 任务 | 命中的具体 Benchmark 任务（文件::`task_id`） |
|---:|---:|---|---|---|---|
| 1 | `generator.py:134` | `x` | 否 | 否 | 无 |
| 2 | `generator.py:135` | `(reverse x)` | **是 (LEAK)** | — | `held_out_test.json::list_reverse`, `list_functions.json::list_reverse`, `families/list_structural.json::list_reverse` |
| 3 | `generator.py:136` | `(tail x)` | **是 (LEAK)** | — | `families/list_structural.json::list_tail_elements` |
| 4 | `generator.py:138` | `(map (lambda (a) (+ a 1)) x)` | **是 (LEAK)** | — | `dev_train.json::list_increment_all`, `list_functions.json::list_increment_all`, `families/list_mapping.json::list_increment_all` |
| 5 | `generator.py:139` | `(map (lambda (a) (+ a 2)) x)` | 否 | 否（注：匹配 `Curriculum.propose_from_operators` 合成任务 `k=2`） | 无静态 JSON 匹配 |
| 6 | `generator.py:140` | `(map (lambda (a) (- a 1)) x)` | **是 (LEAK)** | — | `families/list_mapping.json::list_decrement_all` |
| 7 | `generator.py:141` | `(map (lambda (a) (* a 2)) x)` | **是 (LEAK)** | — | `dev_eval.json::list_double_all`, `list_functions.json::list_double_all`, `families/list_mapping.json::list_double_all` |
| 8 | `generator.py:142` | `(map (lambda (a) (* a a)) x)` | 否 | 否 | 无 |
| 9 | `generator.py:143` | `(map (lambda (a) (inc a)) x)` | 否 | **是 (语义泄漏)** | 等价于 `list_increment_all` (`(map (lambda (a) (+ a 1)) x)`) |
| 10 | `generator.py:144` | `(map (lambda (a) (dec a)) x)` | 否 | **是 (语义泄漏)** | 等价于 `list_decrement_all` (`(map (lambda (a) (- a 1)) x)`) |
| 11 | `generator.py:145` | `(map (lambda (a) (neg a)) x)` | 否 | 否 | 无 |
| 12 | `generator.py:147` | `(filter (lambda (a) (is_even a)) x)` | **是 (LEAK)** | — | `dev_train.json::filter_evens`, `list_functions.json::filter_evens`, `families/list_filtering.json::filter_evens` |
| 13 | `generator.py:148` | `(filter (lambda (a) (is_odd a)) x)` | 否 | 否（注：匹配 `Curriculum.propose_from_operators`） | 无静态 JSON 匹配 |
| 14 | `generator.py:149` | `(filter (lambda (a) (gt a 0)) x)` | **是 (LEAK)** | — | `held_out_test.json::filter_positive`, `families/list_filtering.json::filter_positive` |
| 15 | `generator.py:150` | `(filter (lambda (a) (gt a 2)) x)` | **是 (LEAK)** | — | `held_out_test.json::filter_greater_than_two`, `list_functions.json::filter_greater_than_two`, `families/list_filtering.json::filter_greater_than_two` |
| 16 | `generator.py:151` | `(filter (lambda (a) (gt a 3)) x)` | 否 | 否 | 无 |
| 17 | `generator.py:152` | `(filter (lambda (a) (lt a 5)) x)` | 否 | 否 | 无 |
| 18 | `generator.py:154` | `(sum x)` | **是 (LEAK)** | — | `dev_eval.json::list_sum`, `list_functions.json::list_sum`, `families/list_reduction.json::list_sum` |
| 19 | `generator.py:155` | `(length x)` | **是 (LEAK)** | — | `families/list_reduction.json::list_length` |
| 20 | `generator.py:156` | `(head x)` | 否 | 否 | 无 |
| 21 | `generator.py:157` | `(fold (lambda (acc item) (+ acc item)) 0 x)` | 否 | **是 (语义泄漏)** | 等价于 `list_sum` (`(sum x)`) |
| 22 | `generator.py:158` | `(fold (lambda (acc item) (+ acc 1)) 0 x)` | 否 | **是 (语义泄漏)** | 等价于 `list_length` (`(length x)`) |
| 23 | `generator.py:159` | `(fold (lambda (acc item) (* acc item)) 1 x)` | 否 | 否 | 无 |
| 24 | `generator.py:161` | `(reverse (map (lambda (a) (* a 2)) x))` | 否 | 否 | 无 |
| 25 | `generator.py:162` | `(map (lambda (a) (* a 2)) (reverse x))` | 否 | 否 | 无 |
| 26 | `generator.py:163` | `(filter (lambda (a) (is_even a)) (map (lambda (a) (+ a 1)) x))` | 否 | 否 | 无 |
| 27 | `generator.py:164` | `(sum (filter (lambda (a) (is_even a)) x))` | **是 (LEAK, Held-Out!)** | — | `families/list_composition.json::filter_evens_and_sum`（直接泄漏 `is_held_out: true` 组合评测集答案！） |

**小结（`generator.py`）**：
- 27 个启发式模板中，**11 个模板（#2, #3, #4, #6, #7, #12, #14, #15, #18, #19, #27）** 逐字符等于 Benchmark 任务的 `reference_program`，另有 **4 个模板（#9, #10, #21, #22）** 在全部可见+隐藏测试上语义完全等价于 Benchmark `reference_program`，合计 **15 / 27 (55.6%)** 的模板直接对应 Benchmark 答案。
- 尤其严重的是模板 **#27 `(sum (filter (lambda (a) (is_even a)) x))`**（`generator.py:164`），直接把标注为 `is_held_out: true` 的组合泛化评测任务 `list_composition.json::filter_evens_and_sum` 的参考答案硬编码进了 `generator.py`。

---

## 3. `SymbolicEnumerator` 的 67 个硬编码模板逐项标注表

代码位置：`eve3/search/enumerator.py:49-95` (`SymbolicEnumerator.enumerate_candidates`，默认 `consts = [0, 1, 2, -1, 3]`, `max_depth = 3`)。  
注：`SearchController.propose_candidates` 调用 `enumerate_candidates(domain_hint="list", max_candidates=max_candidates * 2)`（默认 `max_candidates=16`，即截取前 32 个 `list` 候选）。以下列出全部 67 个模板条目及其精确/语义匹配情况：

### 3.1 `domain_hint in ("list", "generic")` 模板（序号 1–49）

| 序号 | 行号 | 生成方式 | 模板 (`code_str`) | 是否在前 32 个候选中 | 精确匹配 `reference_program` | 语义等价匹配 | 命中的 Benchmark 任务 |
|---:|---:|---|---|---|---|---|---|
| 1 | `enumerator.py:50` | 固定 | `x` | 是 (#1) | 否 | 否 | 无 |
| 2 | `enumerator.py:54` | 固定 | `(reverse x)` | 是 (#2) | **是 (LEAK)** | — | `held_out_test::list_reverse`, `list_functions::list_reverse`, `list_structural::list_reverse` |
| 3 | `enumerator.py:55` | 固定 | `(tail x)` | 是 (#3) | **是 (LEAK)** | — | `list_structural::list_tail_elements` |
| 4 | `enumerator.py:56` | 固定 | `(head x)` | 是 (#4) | 否 | 否 | 无 |
| 5 | `enumerator.py:57` | 固定 | `(sum x)` | 是 (#5) | **是 (LEAK)** | — | `dev_eval::list_sum`, `list_functions::list_sum`, `list_reduction::list_sum` |
| 6 | `enumerator.py:58` | 固定 | `(length x)` | 是 (#6) | **是 (LEAK)** | — | `list_reduction::list_length` |
| 7 | `enumerator.py:60` | 固定 | `(map (lambda (a) (inc a)) x)` | 是 (#7) | 否 | **是 (语义泄漏)** | 等价于 `list_increment_all` (`(map (lambda (a) (+ a 1)) x)`) |
| 8 | `enumerator.py:61` | 固定 | `(map (lambda (a) (dec a)) x)` | 是 (#8) | 否 | **是 (语义泄漏)** | 等价于 `list_decrement_all` (`(map (lambda (a) (- a 1)) x)`) |
| 9 | `enumerator.py:62` | 固定 | `(map (lambda (a) (neg a)) x)` | 是 (#9) | 否 | 否 | 无 |
| 10 | `enumerator.py:63` | 固定 | `(filter (lambda (a) (is_even a)) x)` | 是 (#10) | **是 (LEAK)** | — | `dev_train::filter_evens`, `list_functions::filter_evens`, `list_filtering::filter_evens` |
| 11 | `enumerator.py:64` | 固定 | `(filter (lambda (a) (is_odd a)) x)` | 是 (#11) | 否 | 否 | 无 |
| 12 | `enumerator.py:69` | `k=0` | `(map (lambda (a) (+ a 0)) x)` | 是 (#12) | 否 | 否 | 无 |
| 13 | `enumerator.py:70` | `k=0` | `(map (lambda (a) (- a 0)) x)` | 是 (#13) | 否 | 否 | 无 |
| 14 | `enumerator.py:71` | `k=0` | `(map (lambda (a) (* a 0)) x)` | 是 (#14) | 否 | 否 | 无 |
| 15 | `enumerator.py:72` | `k=0` | `(filter (lambda (a) (gt a 0)) x)` | 是 (#15) | **是 (LEAK)** | — | `held_out_test::filter_positive`, `list_filtering::filter_positive` |
| 16 | `enumerator.py:73` | `k=0` | `(filter (lambda (a) (lt a 0)) x)` | 是 (#16) | 否 | 否 | 无 |
| 17 | `enumerator.py:74` | `k=0` | `(filter (lambda (a) (eq a 0)) x)` | 是 (#17) | 否 | 否 | 无 |
| 18 | `enumerator.py:69` | `k=1` | `(map (lambda (a) (+ a 1)) x)` | 是 (#18) | **是 (LEAK)** | — | `dev_train::list_increment_all`, `list_functions::list_increment_all`, `list_mapping::list_increment_all` |
| 19 | `enumerator.py:70` | `k=1` | `(map (lambda (a) (- a 1)) x)` | 是 (#19) | **是 (LEAK)** | — | `list_mapping::list_decrement_all` |
| 20 | `enumerator.py:71` | `k=1` | `(map (lambda (a) (* a 1)) x)` | 是 (#20) | 否 | 否 | 无 |
| 21 | `enumerator.py:72` | `k=1` | `(filter (lambda (a) (gt a 1)) x)` | 是 (#21) | 否 | 否 | 无 |
| 22 | `enumerator.py:73` | `k=1` | `(filter (lambda (a) (lt a 1)) x)` | 是 (#22) | 否 | 否 | 无 |
| 23 | `enumerator.py:74` | `k=1` | `(filter (lambda (a) (eq a 1)) x)` | 是 (#23) | 否 | 否 | 无 |
| 24 | `enumerator.py:69` | `k=2` | `(map (lambda (a) (+ a 2)) x)` | 是 (#24) | 否 | 否 | 无 |
| 25 | `enumerator.py:70` | `k=2` | `(map (lambda (a) (- a 2)) x)` | 是 (#25) | 否 | 否 | 无 |
| 26 | `enumerator.py:71` | `k=2` | `(map (lambda (a) (* a 2)) x)` | 是 (#26) | **是 (LEAK)** | — | `dev_eval::list_double_all`, `list_functions::list_double_all`, `list_mapping::list_double_all` |
| 27 | `enumerator.py:72` | `k=2` | `(filter (lambda (a) (gt a 2)) x)` | 是 (#27) | **是 (LEAK)** | — | `held_out_test::filter_greater_than_two`, `list_functions::filter_greater_than_two`, `list_filtering::filter_greater_than_two` |
| 28 | `enumerator.py:73` | `k=2` | `(filter (lambda (a) (lt a 2)) x)` | 是 (#28) | 否 | 否 | 无 |
| 29 | `enumerator.py:74` | `k=2` | `(filter (lambda (a) (eq a 2)) x)` | 是 (#29) | 否 | 否 | 无 |
| 30 | `enumerator.py:69` | `k=-1` | `(map (lambda (a) (+ a -1)) x)` | 是 (#30) | 否 | **是 (语义泄漏)** | 等价于 `list_decrement_all` (`(map (lambda (a) (- a 1)) x)`) |
| 31 | `enumerator.py:70` | `k=-1` | `(map (lambda (a) (- a -1)) x)` | 是 (#31) | 否 | **是 (语义泄漏)** | 等价于 `list_increment_all` (`(map (lambda (a) (+ a 1)) x)`) |
| 32 | `enumerator.py:71` | `k=-1` | `(map (lambda (a) (* a -1)) x)` | 是 (#32) | 否 | 否 | 无 |
| 33 | `enumerator.py:72` | `k=-1` | `(filter (lambda (a) (gt a -1)) x)` | 否 (#33, 被 `max_candidates=32` 截断) | 否 | 否 | 无 |
| 34 | `enumerator.py:73` | `k=-1` | `(filter (lambda (a) (lt a -1)) x)` | 否 (#34) | 否 | 否 | 无 |
| 35 | `enumerator.py:74` | `k=-1` | `(filter (lambda (a) (eq a -1)) x)` | 否 (#35) | 否 | 否 | 无 |
| 36 | `enumerator.py:69` | `k=3` | `(map (lambda (a) (+ a 3)) x)` | 否 (#36) | 否 | 否 | 无 |
| 37 | `enumerator.py:70` | `k=3` | `(map (lambda (a) (- a 3)) x)` | 否 (#37) | 否 | 否 | 无 |
| 38 | `enumerator.py:71` | `k=3` | `(map (lambda (a) (* a 3)) x)` | 否 (#38) | 否 | 否 | 无 |
| 39 | `enumerator.py:72` | `k=3` | `(filter (lambda (a) (gt a 3)) x)` | 否 (#39) | 否 | 否 | 无 |
| 40 | `enumerator.py:73` | `k=3` | `(filter (lambda (a) (lt a 3)) x)` | 否 (#40) | 否 | 否 | 无 |
| 41 | `enumerator.py:74` | `k=3` | `(filter (lambda (a) (eq a 3)) x)` | 否 (#41) | 否 | 否 | 无 |
| 42 | `enumerator.py:77` | 固定 | `(fold (lambda (acc item) (+ acc item)) 0 x)` | 否 (#42) | 否 | **是 (语义泄漏)** | 等价于 `list_sum` (`(sum x)`) |
| 43 | `enumerator.py:78` | 固定 | `(fold (lambda (acc item) (* acc item)) 1 x)` | 否 (#43) | 否 | 否 | 无 |
| 44 | `enumerator.py:83` | `depth=3, k=1` | `(reverse (map (lambda (a) (+ a 1)) x))` | 否 (#44) | 否 | 否（匹配 `Curriculum` 合成模板） | 无静态 JSON 匹配 |
| 45 | `enumerator.py:84` | `depth=3, k=1` | `(sum (map (lambda (a) (+ a 1)) x))` | 否 (#45) | 否 | 否（匹配 `Curriculum` 合成模板） | 无静态 JSON 匹配 |
| 46 | `enumerator.py:85` | `depth=3, k=1` | `(filter (lambda (a) (is_even a)) (map (lambda (a) (+ a 1)) x))` | 否 (#46) | 否 | 否 | 无 |
| 47 | `enumerator.py:83` | `depth=3, k=2` | `(reverse (map (lambda (a) (+ a 2)) x))` | 否 (#47) | 否 | 否（匹配 `Curriculum` 合成模板） | 无静态 JSON 匹配 |
| 48 | `enumerator.py:84` | `depth=3, k=2` | `(sum (map (lambda (a) (+ a 2)) x))` | 否 (#48) | 否 | 否（匹配 `Curriculum` 合成模板） | 无静态 JSON 匹配 |
| 49 | `enumerator.py:85` | `depth=3, k=2` | `(filter (lambda (a) (is_even a)) (map (lambda (a) (+ a 2)) x))` | 否 (#49) | 否 | 否 | 无 |

### 3.2 `domain_hint in ("int", "generic")` 模板（序号 50–67）

| 序号 | 行号 | 生成方式 | 模板 (`code_str`) | 精确匹配 `reference_program` | 语义等价匹配 |
|---:|---:|---|---|---|---|
| 50–64 | `enumerator.py:89-91` | `k in [0, 1, 2, -1, 3]` | `(+ x k)`, `(- x k)`, `(* x k)`（共 15 个） | 否 | 否 |
| 65–67 | `enumerator.py:92-94` | 固定 | `(inc x)`, `(dec x)`, `(neg x)`（共 3 个） | 否 | 否 |

---

## 4. 全部 13 个唯一 Benchmark 任务的泄漏状态总表

| 唯一任务 ID (`task_id`) | 所属任务族 (`task_family`) | 出现的 Benchmark 文件 | 参考答案 (`reference_program`) | AST 深度 / 节点数 | `generator.py` 命中模板序号 | `enumerator.py` 命中模板序号 | 泄漏分类 |
|---|---|---|---|---:|---|---|---|
| `list_increment_all` | `list_mapping` | `dev_train`, `list_functions`, `families/list_mapping` | `(map (lambda (a) (+ a 1)) x)` | depth=4, DL=8 | **#4** (精确), #9 (语义) | **#18** (精确), #7/#31 (语义) | **精确泄漏 (Direct Leak)** |
| `list_double_all` | `list_mapping` | `dev_eval`, `list_functions`, `families/list_mapping` | `(map (lambda (a) (* a 2)) x)` | depth=4, DL=8 | **#7** (精确) | **#26** (精确) | **精确泄漏 (Direct Leak)** |
| `list_decrement_all` | `list_mapping` | `families/list_mapping` | `(map (lambda (a) (- a 1)) x)` | depth=4, DL=8 | **#6** (精确), #10 (语义) | **#19** (精确), #8/#30 (语义) | **精确泄漏 (Direct Leak)** |
| `filter_evens` | `list_filtering` | `dev_train`, `list_functions`, `families/list_filtering` | `(filter (lambda (a) (is_even a)) x)` | depth=4, DL=7 | **#12** (精确) | **#10** (精确) | **精确泄漏 (Direct Leak)** |
| `filter_greater_than_two` | `list_filtering` | `held_out_test`, `list_functions`, `families/list_filtering` | `(filter (lambda (a) (gt a 2)) x)` | depth=4, DL=8 | **#15** (精确) | **#27** (精确) | **精确泄漏 (Direct Leak)** |
| `filter_positive` | `list_filtering` | `held_out_test`, `families/list_filtering` | `(filter (lambda (a) (gt a 0)) x)` | depth=4, DL=8 | **#14** (精确) | **#15** (精确) | **精确泄漏 (Direct Leak)** |
| `list_sum` | `list_reduction` | `dev_eval`, `list_functions`, `families/list_reduction` | `(sum x)` | depth=2, DL=2 | **#18** (精确), #21 (语义) | **#5** (精确), #42 (语义) | **精确泄漏 / 深度 2 原语** |
| `list_length` | `list_reduction` | `families/list_reduction` | `(length x)` | depth=2, DL=2 | **#19** (精确), #22 (语义) | **#6** (精确) | **精确泄漏 / 深度 2 原语** |
| `list_reverse` | `list_structural` | `held_out_test`, `list_functions`, `families/list_structural` | `(reverse x)` | depth=2, DL=2 | **#2** (精确) | **#2** (精确) | **精确泄漏 / 深度 2 原语** |
| `list_tail_elements` | `list_structural` | `families/list_structural` | `(tail x)` | depth=2, DL=2 | **#3** (精确) | **#3** (精确) | **精确泄漏 / 深度 2 原语** |
| `filter_evens_and_sum` | `list_composition` (`is_held_out=true`) | `families/list_composition` | `(sum (filter (lambda (a) (is_even a)) x))` | depth=5, DL=8 | **#27** (精确) | 未命中 | **Held-Out 精确泄漏 (Held-Out Direct Leak)** |
| `filter_positive_and_sum` | `list_composition` (`is_held_out=true`) | `families/list_composition` | `(sum (filter (lambda (a) (gt a 0)) x))` | depth=5, DL=9 | 未命中 | 未命中 | 未泄漏（需组合合成） |
| `reverse_and_tail` | `list_composition` (`is_held_out=true`) | `families/list_composition` | `(tail (reverse x))` | depth=3, DL=3 | 未命中 | 未命中 | 未泄漏（需深度 3 通用枚举） |

---

## 5. 关键审计结论（证据总结）

1. **`dev_train`、`dev_eval`、`held_out_test`、`list_functions` 以及 4 个训练任务族 100% 答案预置**：上述 23 个任务条目（10 个唯一任务）的 `reference_program` 100% 同时出现在 `generator.py:132-165` 的 27 个模板和 `enumerator.py:49-74` 的前 27 个模板中。
2. **所谓的“Held-Out 组合泛化测试 (`list_composition.json`)”存在直接答案硬编码**：`list_composition.json` 中 3 个任务只有 `filter_evens_and_sum` 在原实验中通过（`33.3%`），原因根本不是“学到了可迁移算子或跨族迁移”，而是 `generator.py:164` 的第 27 号模板硬编码了 `(sum (filter (lambda (a) (is_even a)) x))`；而另外两个同样简单的组合任务 `filter_positive_and_sum` (`(sum (filter (lambda (a) (gt a 0)) x))`) 和 `reverse_and_tail` (`(tail (reverse x))`) 因为不在 27 个模板内，在原系统中 100% 失败 (`COLLAPSED`)。
3. **`SymbolicEnumerator` 并非真正的自底向上语法枚举器**：`enumerator.py:49-95` 没有按 AST 语法规则递归组合子表达式（例如它甚至无法在 `depth=3` 枚举出 3 节点的 `(tail (reverse x))`），而是手写了 11 个固定字符串 + `k` 循环拼接 + 3 个深度 3 复合模板。在 S1 中必须替换为真正的通用自底向上 AST 枚举器 (`generic_enumeration`)。
