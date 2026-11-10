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

---

## 6. S4 库学习消融的基线选择：受限枚举器 vs 观测等价完全枚举（S1.1-C 核心发现）

- **现状与证据**：
  - S1.1-C 构建了 `BottomUpOEEnumerator`（带观测等价剪枝的完全自底向上 AST 枚举器，`eve3/search/enumeration_full.py`）。
  - 实测证实：在无需任何结晶库或高阶抽象的情况下，`BottomUpOEEnumerator` 在 224.3ms 内解出了 `filter_evens_and_sum`（AST size 6，评估 1,491 个程序），在 1,258.1ms 内解出了 `filter_positive_and_sum`（AST size 7，评估 8,185 个程序）。
  - 这表明此前仓库声称的"组合任务必须依赖 System 3 库学习结晶算子方可求解"在无限制自底向上搜索下被**证伪**。
- **开放问题与后续约束**：
  - 在 Stage S4 的库学习消融实验中，如果继续以 $d \le 4$ 的受限枚举器作为对照基线，会人为夸大库学习的"求解能力"（从无法求解到可以求解）；
  - 因此 S4 的核心研究问题必须调整为：**库学习究竟是带来了不可替代的表达能力，还是仅仅带来了搜索加速（减少评估候选数与搜索耗时）？**
  - 后续评测必须同时将 `enumeration_full` 作为无库上限基线纳入对比。

---

## 7. 神经提议器（LLM）的表达偏置与报错修补有效性边界（S1.1-D 核心发现）

- **现状与证据**：
  - 在加入 DSL 原语表、语法约束与 4 个非基准 few-shot 示例后，Qwen2.5-Coder-3B-Instruct-4bit 的语法合法率从 S1 的 0% 提升至最高 91.33%（$k=16, T=0.7$），在 13 个唯一基准任务上的 Pass@16 达到 46.15%（修补后）/ 38.46%（留出集验证）。
  - 但在所有 4 组采样配置下，模型均**未能产生任何针对多步复合任务（如 `filter_evens_and_sum`）的正确嵌套结构**，高阶 lambda 绑定的嵌套闭包仍是小参数神经提议器的主要瓶颈。
  - 免责声明与开放问题：当前评测显示该 3B 模型在特定 prompt 与少量示例下未能产生复合表达式，仅代表该模型在此配置下的实测表现，不推论为所有语言模型在此任务上的理论极限。后续需探究更大规模模型或微调（LoRA）对 DSL 复杂语法树的合成边界。

---

## 8. Stage S2 / Stage S3 已解决裁决与 Stage S4 准备情况（最新更新）

- **Stage S2 已解决裁决**：
  1. **确定性程序后验归零（H3）已闭环**：通过配置 `noise_model: "deterministic" | "noisy(eps)"` 彻底消除了 Laplace 平滑在确定性设置下的反例复活缺陷。
  2. **假设塌缩与主动重提议（H4）已闭环**：建立起了携带历史全部反例约束的重提议机制（`max_repropose_rounds=3`），并在耗尽后准确报告 `COLLAPSED` 与 `verified_program=None`。
  3. **SMT 列表高阶原语有界符号展开（H5）已闭环**：实现了对 `map`、`reverse`、`tail`、`head`、`sum`、`length` 等的 Z3 符号展开与模型提取，消除了非必要的边界回退。
  4. **随机探针对照臂已就绪**：引入了 `probe_strategy="random"`，消除了此前基线主表的 `INVALID_PENDING_RANDOM_CONTROL` 状态。

- **Stage S3 已解决裁决**：
  1. **贝叶斯先验多样化与强度调节（H1）已闭环**：支持 `prior_mode: "mdl" | "uniform" | "llm"`，引入 `mdl_prior_decay` 调节描述长度惩罚项，支持候选程序 `logprob` 的 softmax 归一化后验传播。
  2. **沙箱多步安全防御与非阻塞硬超时（H11）已闭环**：消除 `ThreadPoolExecutor.__exit__` 中的隐式阻塞等待，使用 `shutdown(wait=False, cancel_futures=True)` 确保超时后主线程立即返回；新增 `ExecutionSizeLimitExceeded` 与 `ExecutionRecursionLimitExceeded`，拦截 `fold` 倍增内存炸弹、连续平方大整数与深层递归调用。
  3. **AST $\alpha$-等价去重与提示词对齐（H9）已闭环**：在 `ASTNode` 实现 `to_canonical_sexpr()`，基于词法嵌套深度统一编号 lambda 形参（`$0, $1...`），使 `CandidateProgram` 的相等判定与哈希严格基于规范形式；动态生成提示词候选数量，消除硬编码 5。

- **接续阶段关注点（Stage S4：System 3 库学习真实性，P0）**：
  - 算子真实注册（H11/H14）：修复结晶算子因未注入 `DSLInterpreter.base_env` 导致 100% 报 `NameError` 的断裂问题；
  - 动态模式挖掘（H12）：修复 `value_compressor.py` 因 `patterns.add()` 与缺失 `LambdaNode` 导致的 100% 崩溃，消除顺序依赖；
  - 次模性检验与贪心解质量（H13）：在无泄漏环境下，以 `enumeration_full` 为对照基线，客观检验库学习带来的实际搜索加速比与压缩率。

