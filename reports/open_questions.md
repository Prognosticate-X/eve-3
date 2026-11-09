# EVE-3 仍未解决的问题与后续研究开放问题 (`open_questions.md`)

本文件汇总在对 EVE-3 仓库完成第 0–3 阶段“证据优先”代码审计、P0→P1→P2 修复与多种子实验评测后，仍然存在的架构局限与后续开放问题。

---

## 1. 神经提议器（System 1）与本地 MLX 权重的端到端实证闭环尚未建立（对应 H10）

- **现状与证据**：
  - 在默认 CPU/SMT 环境（未安装 `mlx-lm` 或未下载本地 `mlx-community/Qwen2.5-Coder-7B-Instruct-4bit` 权重）下，`HypothesisGenerator`（`eve3/system1_proposer/generator.py:88-115`）完全回退到基于规则模板的 `_heuristic_synthesizer` 与 `SymbolicEnumerator`。
  - 第 3 阶段多种子实验表明：Regime A（混合模式）与 Regime E（关闭 LLM 纯符号模式）在全部 36 个任务上的成功率完全相同（$B=16$ 时均为 `94.44% ± 0.00%`，留出集均为 `91.67% ± 0.00%`，`LLMCalls = 0.0`）。
- **未解决原因**：
  - 7B 规模本地模型权重依赖 Apple Silicon GPU + 数 GB 外部权重下载，无法在纯离线/轻量 CI 环境中默认运行。
- **后续方向**：
  - 在配备 `mlx-lm` 的实验机上，构造**超出手工启发式模板覆盖范围**的开放域任务（例如深度 $\ge 5$ 的任意算术/字符串混合变换），在严格屏蔽 `_heuristic_synthesizer` 的条件下单独评测真实 LLM 采样（含 log-likelihood 先验 `prior_mode="llm"`）相对于自底向上符号枚举的边际增益。

---

## 2. SMT 形式化编码对高阶组合与字符串原语的覆盖边界（对应 H5, H6）

- **现状与证据**：
  - 第 2 阶段已在 `eve3/system2_falsifier/smt_distinguisher.py` 中修复了 Z3 模型提取崩溃（`model.eval(..., model_completion=True)`），并新增了有界列表展开（`unroll_depth=3`，支持 `map`/`filter`/`sum`/`len`/`head`/`reverse`）及输出签名预聚类。
  - 然而，对于**字符串变换原语**（`str_strip`, `str_upper`, `str_digits` 等）以及**嵌套高阶函数**（如 `(map (lambda ...) (filter (lambda ...) x))` 深度超过有界展开窗口时），`SMTDistinguisher` 仍会回退返回 `None`（依赖 `generate_candidate_probe_pool` 中的多模态结构化种子探针池计算闭式 IG）。
  - 实验证据：Regime C（仅使用 Z3 区分输入、不结合种子探针池与 IG 选择）在全部预算下成功率停滞在 `34.44% ~ 38.89%`。
- **后续方向**：
  - 引入 Z3 字符串理论（`z3.String` / `z3.SeqSort`）编码 `str_*` 原语，使 SMT 区分器能够自动合成针对复杂正则/子串边界的精确反例输入。

---

## 3. System 1 沙箱基于线程超时（`ThreadPoolExecutor`）的固有限制（对应 H11）

- **现状与证据**：
  - 第 2 阶段已在 `DSLInterpreter`（`eve3/dsl/interpreter.py:130-210`）中加入了 AST 求值步数预算（`max_steps=10000`）、递归深度上限（`max_recursion_depth=50`）、输出体积上限（`max_output_size=5000`）与幂指数上限（$|b| \le 100$），在解释器层彻底拦截了恶意 DSL 表达式。
  - 但 `ProgramSandbox.execute_with_timeout`（`eve3/system1_proposer/sandbox.py:42-68`）底层仍使用 Python `ThreadPoolExecutor`（配合 `shutdown(wait=False, cancel_futures=True)` 防止阻塞主线程）。若未来允许执行任意原生 Python C 扩展或非解释器托管代码，Python 线程无法从外部强制杀死（SIGKILL）。
- **后续方向**：
  - 若后续 DSL 扩展至原生 Python 代码合成，需将执行后端迁移至独立受限子进程池（`multiprocessing` + OS 级 `RLIMIT_AS` / `SIGKILL`）。

---

## 4. System 3 子树挖掘的完整 Anti-Unification（反合一）泛化（对应 H12）

- **现状与证据**：
  - 第 2 阶段已将 `ValueCompressor.extract_candidate_abstractions`（`eve3/system3_crystallizer/value_compressor.py:90-145`）从“仅把完整程序包成抽象”升级为递归提取跨任务共享的复杂 AST 子表达式，并修复了 `compute_weighted_benefit` 的集合顺序依赖问题。
  - 但当前子树挖掘仍基于**精确或单参数替换的 AST 子树匹配**，尚未实现完整的亮式高阶反合一（Higher-Order Anti-Unification / Stitch 风格多槽位 $\lambda$-abstraction 发明，例如从 `(map (lambda (a) (+ a 1)) x)` 和 `(map (lambda (a) (* a 2)) x)` 中自动抽象出高阶算子 `(fn (f x) (map f x))`）。
- **后续方向**：
  - 引入一阶/高阶 Anti-Unification 算法提取多变量参数化模式，并在重写阶段使用 AST 同构匹配替代 canonical S-expression 子串替换。

---

## 5. 反事实回放树（Discovery Tree）在连续/高维动作空间下的支撑覆盖率退化（对应 H16）

- **现状与证据**：
  - 第 2 阶段已在 `ReplaySimulator.evaluate_policy`（`eve3/discovery/tree.py:210-290`）中加入了树支撑检查（`support_coverage`）与重要性采样（IS）权重方差统计：当新策略走出历史树已记录分支时，明确标记 `evaluatable=False`（`status="un-evaluatable"`）。
  - 但随着探索深度增加或策略分布偏移加大，历史离散树的支撑覆盖率（`support_coverage`）会按指数衰减，导致大量反事实评估触发 `un-evaluatable` 或产生极高 IS 方差。
- **后续方向**：
  - 引入 Doubly Robust（双重稳健）离策略估计器（结合学习到的价值近似模型 $\hat{Q}$ 与重要性采样权重），在保证无偏性的同时降低多步轨迹的估计方差。
