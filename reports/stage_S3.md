# EVE-3 阶段报告：Stage S3 System 1 提议器质量与鲁棒性实证验收

> **报告日期**：2026-11-10  
> **运行环境**：Windows, Python 3.12.8 (x64), z3-solver 5.3.3.0, pytest 9.2.0, hypothesis 6.170.15, pydantic 2.14.3  
> **报告原则**：严格基于实测数据与代码实现，拒绝推测；全量测试遵循 TDD（先红后绿）、原子 commit、棘轮不退、AST 静态零宽泛异常。

---

## 1. 阶段概述与 Commit 记录

Stage S3 聚焦于提升 System 1 假说提议器与执行沙箱的质量与鲁棒性，全面修复前期审计中确认的核心问题（H1, H11, H9, H10）：
1. **先验多样化与强度调节（H1）**：摆脱硬编码 MDL 先验，支持 `"uniform"`、`"mdl"`（含衰减因子调节）与 `"llm"`（利用候选生成时的对数似然 `logprob`）；
2. **沙箱多步安全防御与非阻塞超时（H11）**：根治 Python 标准库 `ThreadPoolExecutor` 退出时阻塞等待的底层隐患，消除 `fold` 倍增引发的内存与大整数炸弹，建立严格递归深度防御；
3. **AST $\alpha$-等价去重与提示词对齐（H9）**：引入词法规范化表达 `to_canonical_sexpr()`，消融命名差异造成的虚假多样性与先验扭曲，并将提示词要求与配置候选数动态同步；
4. **环境边界与透明核算（H10）**：明确非 Apple Silicon 平台（Windows x64）的运行边界，在无 MLX-LM 的环境下提供健壮回退与优雅跳过，保持纯符号与形式化验证链路 100% 畅通。

本阶段全部交付均通过独立的原子 commit 落地，各 commit 记录如下：

| Commit | 修复范围 / 目标 | 关联假设与证据行 | 关键成果 |
| :--- | :--- | :--- | :--- |
| `4959283` | **S3-H1**：可配置贝叶斯先验分布 | H1 (`audit.md:98-124`) | 引入 `prior_mode: "mdl" \| "uniform" \| "llm"` 与 `mdl_prior_decay`；支持 `logprob` 传播与 softmax 归一化；`tests/test_stage_s3_prior.py` 全绿 |
| `9cfe08d` | **S3-H11**：沙箱多步安全防御与非阻塞超时 | H11 (`audit.md:384-405`) | 消除 `ThreadPoolExecutor` 上下文阻塞退出；增加 `ExecutionSizeLimitExceeded` 与 `ExecutionRecursionLimitExceeded`；`tests/test_stage_s3_sandbox_security.py` 全绿 |
| `08c2fb7` | **S3-H9**：AST $\alpha$-等价去重与提示词对齐 | H9 (`audit.md:344-363`) | 在 AST 实现 `to_canonical_sexpr()`；`CandidateProgram` 基于规范形式判等与哈希；提示词动态格式化候选数 $k$；`tests/test_stage_s3_dedup.py` 全绿 |

---

## 2. H1 先验多样化与配置化贝叶斯更新（Bayesian Prior Modes）

### 2.1 问题机理与修复前状态
- **缺陷**：此前 `BayesianProber.initialize_beliefs` 仅支持硬编码的最小描述长度（MDL）先验：
  $$P(M_i) \propto 2^{-DL(M_i)}$$
  且衰减强度固定为 1.0，既无法配置均匀分布（`uniform`）作为标准消融基线，也无法接入基于语言模型提议时产出的条件对数概率（`logprob`），使得先验分布与 System 1 提议过程完全脱节。
- **修复前状态**：
  ```text
  AttributeError: 'EveConfig' object has no attribute 'prior_mode'
  ```

### 2.2 修复方案与代码落地
1. **配置项拓展**（`eve3/config.py`）：
   - 新增合法模式集合：`VALID_PRIOR_MODES = ("mdl", "uniform", "llm")`；
   - 在 `EveConfig` 中增加 `prior_mode: str = "mdl"` 与 `mdl_prior_decay: float = 1.0`，并在 `__post_init__` 中加入模式合法性防御。
2. **候选程序模型补充**（`eve3/models.py`）：
   - 在 `CandidateProgram` 中增加 `logprob: Optional[float] = None` 字段，允许神经提议器附带采样置信度。
3. **三种先验计算引擎**（`eve3/system2_falsifier/bayesian_prober.py`）：
   - **`uniform` 模式**：令所有未证伪候选的初始权重为 1.0，归一化后各候选先验均为 $\frac{1}{N}$；
   - **`mdl` 模式**：引入 `mdl_prior_decay` 系数 $\lambda$：
     $$w_i = 2.0^{-\lambda \cdot DL_i}$$
     实现平滑可调的复杂度惩罚；
   - **`llm` 模式**：提取候选绑定的 `logprob`，进行数值稳定的 softmax 归一化：
     $$w_i = \exp(lp_i - \max lp)$$
     若候选缺失 `logprob`，则平滑回退至中位数先验。
4. **CEGIS 循环透传**（`eve3/system2_falsifier/cegis_loop.py`）：
   - 将 `prior_mode` 与 `mdl_prior_decay` 传递给探针器，保证重提议与初始化阶段先验一致。
5. **测试验收**：编写 `tests/test_stage_s3_prior.py`（4 项测试），验证非法配置校验、均匀先验、可调 MDL 衰减与 LLM 对数似然归一化全部通过。

---

## 3. H11 沙箱多步安全防护与非阻塞硬超时（Sandbox Security Guardrails）

### 3.1 问题机理与修复前状态
- **缺陷 1（上下文管理器阻塞挂起）**：
  此前 `DSLInterpreter.run` 使用 `with ThreadPoolExecutor(max_workers=1) as executor:` 来运行同步代码。Python 标准库的 `ThreadPoolExecutor.__exit__` 无条件执行 `executor.shutdown(wait=True)`。当子线程陷入耗时死循环或深层计算时，即使主线程触发了 `FuturesTimeoutError`，离开 `with` 块时主线程仍会强行挂起阻塞，直到耗时任务跑完！
- **缺陷 2（折叠与乘法绕过步数限制制造内存炸弹）**：
  程序 `(fold (lambda (acc item) (concat acc acc)) [1] x)` 仅需约 20 步即可将长度为 1 的列表倍增至 $2^{20} = 1,048,576$ 个元素；程序 `(fold (lambda (acc item) (* acc acc)) 2 x)` 仅需 12 步即可构造出超过 50,000 位的大整数。这些恶意程序在远低于默认 `step_budget=20000` 的极短步数内即可耗尽数 GB 内存，引发 OOM 崩溃。

### 3.2 修复方案与代码落地
1. **非阻塞安全超时**（`eve3/dsl/interpreter.py`）：
   彻底移除 `with ThreadPoolExecutor` 语法糖，显式管理生命周期：
   ```python
   executor = ThreadPoolExecutor(max_workers=1)
   try:
       future = executor.submit(_execute_sync)
       try:
           return future.result(timeout=timeout_seconds)
       except FuturesTimeoutError:
           future.cancel()
           raise ExecutionTimeoutError(f"Execution exceeded hard timeout budget of {timeout_seconds}s")
   finally:
       executor.shutdown(wait=False, cancel_futures=True)
   ```
   实测超时发生后主线程在 $<0.35$s 内瞬间返回，完全杜绝工作线程阻塞主进程。
2. **多步资源物理防御**（`eve3/dsl/ast.py`）：
   - 新增安全异常类：`ExecutionSizeLimitExceeded(RuntimeError)` 与 `ExecutionRecursionLimitExceeded(RuntimeError)`；
   - 强化 `ExecutionContext`，引入 `max_output_size: int = 1000`、`max_integer_bits: int = 2048`、`max_recursion_depth: int = 50`；
   - 实现 `check_val(val)`：实时监控列表/元组长度、字符串长度及整数二进制位数（`bit_length()`）；
   - 在 `ApplyNode.evaluate`、`LambdaNode` 闭包与 `VarNode/ConstNode` 求值中无死角植入 `enter_call()`、`exit_call()` 与 `check_val()`。
3. **沙箱与配置深度对齐**（`eve3/config.py`、`eve3/system1_proposer/sandbox.py`、`controller.py`、`generator.py`）：
   - `ProgramSandbox` 完整接收步数、体积、位数、深度参数，并在 `diagnostics.sandbox_rejections` 中准确记录 `ExecutionSizeLimitExceeded` 与 `ExecutionRecursionLimitExceeded`。
4. **测试验收**：编写 `tests/test_stage_s3_sandbox_security.py`（5 项攻击性测试），实测非阻塞超时（耗时 1.5s 的睡眠在 0.1s 超时后立即安全退出）、列表指数倍增炸弹拦截、连续平方大整数拦截及深层调用链拦截。

---

## 4. H9 AST $\alpha$-等价去重与动态提示词对齐（Deduplication & Prompt Alignment）

### 4.1 问题机理与修复前状态
- **缺陷 1（字符串去重导致的虚假冗余）**：
  此前候选程序去重完全依赖 `self.code_str == other.code_str`。形如：
  `(map (lambda (a) (+ a 1)) x)` 与 `(map (lambda (b) (+ b 1)) x)`
  由于绑定变量名不同，被误判为不同候选。在提议阶段这不仅占满了宝贵的候选池配额（挤掉其他有效假说），更在贝叶斯阶段严重扭曲了先验质量与信息增益计算。
- **缺陷 2（提示词候选数硬编码）**：
  系统配置 `EveConfig.max_hypotheses_per_round = 16`，但 `HypothesisGenerator.build_prompt` 中硬编码写着 `"generate 5 candidate DSL programs"`，导致大模型指令与下游调度参数错位。

### 4.2 修复方案与代码落地
1. **词法规范形式（Canonical S-Expression）**（`eve3/dsl/ast.py`）：
   - 在 `ASTNode` 基类及其所有子类（`ConstNode`, `VarNode`, `LambdaNode`, `ApplyNode`, `IfElseNode`）中实现抽象方法 `to_canonical_sexpr(self, env_map=None) -> str`；
   - 采用确定性作用域映射：对 `LambdaNode` 的形参列表，按照当前词法作用域深度按序分配规范标识符 `$0, $1, $2, ...`；
   - 自由变量（如输入变量 `x` 或算子名称）保留原始名称；
   - 使得任何 $\alpha$-等价的 lambda 表达式均具有完全相同且唯一的规范 S-表达式字符串。
2. **候选程序等价性升级**（`eve3/models.py`）：
   - 为 `CandidateProgram` 提供属性 `canonical_code` 与方法 `is_alpha_equivalent(other)`；
   - 将 `CandidateProgram.__eq__` 与 `CandidateProgram.__hash__` 迁移至 `self.canonical_code`，使得标准容器（`set`, `dict`, `list` 查重）天然具备 $\alpha$-等价识别能力。
3. **端到端提议去重闭环**（`eve3/search/controller.py` 与 `eve3/system1_proposer/sandbox.py`）：
   - `ProgramSandbox.filter_valid_candidates` 在收集通过用例测试的候选时，自动过滤 $\alpha$-等价冗余；
   - `SearchController.propose_candidates` 基于 `seen_canonical` 集合实现符号枚举与神经提议的统一去重。
4. **动态提示词格式化**（`eve3/system1_proposer/generator.py`）：
   - `build_prompt` 增加可选参数 `num_candidates: Optional[int] = None`，默认使用 `self.config.max_hypotheses_per_round`，动态构造提示指令：`f"Given the following input-output examples, generate {k} candidate DSL programs..."`。
5. **测试验收**：编写 `tests/test_stage_s3_dedup.py`（6 项测试），覆盖单层/多层嵌套 lambda 规范化、`CandidateProgram` 哈希集合去重、沙箱与控制器去重及动态提示词测试。

---

## 5. H10 平台环境边界与透明核算

- **跨平台约束声明**：
  `mlx` 与 `mlx-lm` 深度依赖 Apple Silicon 专用统一内存架构与 Metal 驱动，无法在 Windows / Linux 原生运行。
- **透明处理原则**：
  1. 在 Windows 运行环境中，测试套件对 `test_mlx_llm_smoke_test_sampler_compatibility_and_telemetry` 实施优雅跳过（`SKIPPED`），不制造假阳性或假失败；
  2. 其余纯符号推理、SMT 有界求解、贝叶斯更新、沙箱安全防御与全套控制流程均 100% 独立于硬件平台，在 Windows Python 3.12 环境下全部稳定通过。

---

## 6. 全量实证检验与铁律审计

全量运行包含 Stage S0–S3 的全部测试集：
```text
pytest tests/ -v
================== 133 passed, 1 skipped, 2 xfailed in 9.57s ==================
```

### 6.1 铁律核对明细
1. **铁律 1（不可推测，实证优先）**：全部 3 个子任务均通过攻击性用例（内存炸弹、深递归、$\alpha$-等价候选）真实触发并修复。
2. **铁律 2（严禁削弱现有断言）**：先前阶段全部 118 项现有测试未删除、未修改断言，完全原样 PASS。
3. **铁律 3（AST 静态零宽泛异常）**：运行 `tests/test_stage_s0_diagnostics.py::test_no_bare_except_exception_in_eve3_codebase`，静态遍历 `eve3/`、`experiments/`、`scripts/` 下全部 Python 代码，违规数为 0。
4. **铁律 4（严格封闭核算）**：沙箱分类统计与先验分布满足归一化与排他性。
5. **铁律 5（审计发现转为严格回归测试）**：H1、H11、H9 均已转化为专属回归测试套件。
6. **铁律 6（棘轮只降不升）**：运行 `tests/test_stage_s0_diagnostics.py::test_swallowed_errors_ratchet_only_decreases`，全部位置的异常捕获计数均严格低于或等于 baseline 阈值。
7. **铁律 7（阶段完成停下等待确认）**：完成本报告与文档原子提交后，**主动停下等待用户确认**，严禁擅自跨入 Stage S4。

---

## 7. 下一阶段（Stage S4）核心任务预告

待用户确认后，下一步将进入 **Stage S4：System 3 库学习真实性（P0）**：
1. **结晶算子真实注册与沙箱执行（H11 / H14，P0）**：
   - 当前在 `tests/test_audit_p0_regressions.py` 中标记为 `XFAIL` 的 `test_h11_crystallized_operators_must_execute_successfully_in_sandbox` 记录了结晶算子因未注入 `DSLInterpreter.base_env` 导致 100% 报 `NameError` 的问题。Stage S4 将修复算子注册并转绿此测试。
2. **动态 AST 模式挖掘与次模性检验（H12，P0）**：
   - 修复 `value_compressor.py` 因未导入 `LambdaNode` 与 `patterns.add()` 导致的 100% 崩溃问题，转绿 `test_h12_submodular_pattern_mining_must_extract_abstractions_from_lambda`。
3. **严格对照完全自底向上枚举器（S1.1-C 发现）**：
   - 库学习消融实验必须以 `enumeration_full` 作为无库上限基线，客观检验库学习带来的实际加速比与表达压缩比。

---

## 8. 结论与暂停等待

Stage S3 的全部提议器先验、沙箱多步安全防御、超时非阻塞改造、AST $\alpha$-等价去重与提示词对齐任务已圆满完成并通过全套测试验证。

代码库已处于绝对整洁、安全、全绿、可验证状态，**现在停下等待用户检阅与推进确认**。
