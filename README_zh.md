# EVE-3：神经符号 AGI 算法与自主演化架构

> **融合「直觉假设生成 → 贝叶斯主动证伪 → 价值加权知识晶化」的三系统闭环认知架构。**

<p align="center">
  <a href="README.md">English</a> • <b>简体中文</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/状态-研究进行中-orange.svg" alt="状态: 研究进行中" />
  <img src="https://img.shields.io/badge/开源协议-MIT-blue.svg" alt="开源协议: MIT" />
  <img src="https://img.shields.io/badge/python-3.10+-brightgreen.svg" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/Apple%20Silicon-M系列硬件优化-black.svg" alt="Apple Silicon 优化" />
</p>

---

> [!NOTE]
> **项目状态：研究进行中（Active Research）**  
> 本项目处于核心算法攻关与经验验证的**活跃研究阶段**。系统架构、DSL 规范、贝叶斯探针选择器与知识算子库处于快速迭代演进中。

---

## 🔬 1. 核心假说与研究动机

当前的大语言模型（LLM）主要依赖海量静态数据的模式匹配与无向随机采样。然而，通向通用人工智能（AGI）的核心瓶颈在于**自主构建新知识与高效验证新假说的能力**。真正的认知智能必须具备自闭环的科学探索机制：

$$\text{直觉假设提议} \xrightarrow{\quad} \text{主动反例证伪} \xrightarrow{\quad} \text{抽象晶化固化}$$

EVE-3 项目旨在验证一个严谨且可工程测量的科学问题：

> **在消费级单机环境（如 MacBook M1 Max，32GB 统一内存）下，“假设生成 → 主动证伪 → 算子晶化”的三段认知循环，相比“直接生成”或“随机测试”，在样本效率与跨任务知识复用率上是否具备决定性优势？**

为了避免过早陷入不可微分的连续多模态开放物理世界，本项目将首期实验域聚焦在**神经符号程序合成（Neurosymbolic Program Synthesis）**——这是目前学界已证明能够跑通完整闭环的符号领域。

---

## 🏛️ 2. 三系统认知架构设计

EVE-3 将通用认知回路解构为三个紧密集成的子系统：

```
                  +-----------------------------------+
                  |      任务规格 / 可见输入输出示例     |
                  +-----------------+-----------------+
                                    |
                                    v
+-----------------------------------------------------------------------+
|  System 1: 直觉与假设提议器 (Intuition Proposer)                        |
|  - 本地轻量模型 (MLX + Qwen2.5-Coder-3B-Instruct) / 启发式提议引擎      |
|  - 安全执行沙盒过滤（语法解析与可见示例一致性初筛）                      |
+-----------------------------------+-----------------------------------+
                                    | 候选程序假设集 H = {P_1, ... P_k}
                                    v
+-----------------------------------------------------------------------+
|  System 2: 贝叶斯主动证伪引擎 (Bayesian Active Falsifier)               |
|  - SMT 求解器 (Z3) 两两构建区分性探针输入 P_i(x) != P_j(x)               |
|  - 精确互信息闭式解: IG(x) = H(b) - \sum q_v H(b|G_v)                  |
|  - 主动环境探针执行 -> 贝叶斯后验概率更新与坍塌防御                      |
+-----------------------------------+-----------------------------------+
                                    | 通过全部证伪的稳健程序 P*
                                    v
+-----------------------------------------------------------------------+
|  System 3: 知识晶化与算子库学习 (Knowledge Crystallizer)                 |
|  - SQLite 持久化算子库与探索历史记录                                   |
|  - 面向复用价值的次模加权压缩目标: Benefit_w(L) - \gamma |L|           |
|  - 通用抽象算子反哺 System 1 提示词与原始原语集合                       |
+-----------------------------------+-----------------------------------+
                                    |
                                    v
+-----------------------------------------------------------------------+
|  发现树与重放模拟器 (RSI 递归自我改进层)                                |
|  - 结构化图拓扑树存储完整探索轨迹                                       |
|  - 近零边际成本的离线策略重放与评估                                    |
+-----------------------------------------------------------------------+
```

### System 1：直觉与假设提议器（`eve3/system1_proposer`）
- 采用本地轻量化开源模型（基于 Apple Silicon MLX 优化的 `Qwen2.5-Coder-3B-Instruct` 4-bit 量化版），免除大规模预训练开销，专职作为**直觉提议器（Intuition Generator）**。
- 根据领域特定语言（DSL）语法规范与可见示例，快速提议候选程序假设空间 $\mathcal{H} = \{P_1, \dots, P_k\}$。
- 安全沙盒机制在独立执行上下文中快速剔除语法错误与死循环候选。

### System 2：贝叶斯主动证伪引擎（`eve3/system2_falsifier`）
- 将证伪过程形式化为 **CEGIS（反例引导的归纳合成）** 与 **广义二分搜索（Generalized Binary Search）**。
- 引入 **Z3 SMT 符号求解器**，针对每对候选程序求解使其输出相异的区分性输入（Distinguishing Inputs）：
  $$\exists x : P_i(x) \neq P_j(x)$$
- 基于候选集输出分布，直接计算**香农互信息（闭式解，无需蒙特卡洛采样）**，选取信息增益最大且执行代价最优的探针：
  $$x^* = \arg\max_{x \in X_{\text{cand}}} \Big[ IG(x) - \lambda \cdot C(x) \Big]$$
- 配套 Laplace 平滑与假设空间坍塌保护，杜绝因外部环境异常导致的后验概率除零崩溃。

### System 3：知识晶化与算子库学习（`eve3/system3_crystallizer`）
- 克服传统 Stitch / DreamCoder 纯按语料压缩率选取算子的局限，提出**面向复用价值的加权次模压缩目标**：
  $$\mathcal{L}^* = \arg\max_{\mathcal{L} \subseteq \text{Candidates}} \Big[ \sum_{i=1}^N w_i \cdot \big(\text{DL}(P_i \mid \varnothing) - \text{DL}(P_i \mid \mathcal{L})\big) - \gamma |\mathcal{L}| \Big]$$
- 权重 $w_i = |\text{TaskFamilies}(P_i)| \times (1 + \ln(1 + \text{ReuseCount}_i))$ 强力惩罚仅在单一任务偶然出现的高压缩模式，优先固化横跨多个不同任务家族的高泛化算子。
- 固化成果以 SQLite 单文件存储，作为持久化知识资产反哺 System 1 提示词。

---

## 🔄 3. 递归自我改进（RSI）与发现树重放机制

参考 Google / DeepMind 最新关于 RSI 的理论进展（*Dream-RSI*, arXiv:2609.14858；*The Last AI Built by Humans*, arXiv:2609.11873）：

- **“轨迹是资产，不是日志”**：EVE-3 将所有探索过程以拓扑树（`DiscoveryTree`）的形式进行持久化结构存储，而非无结构的线性聊天记录。
- **近零成本的离线策略评估**：在科学发现与算法探索中，环境评估器（编译、执行、外部测试）极为昂贵。累积的发现树本身即为已探索空间的**重放模拟器（Replay Simulator）**，允许系统通过离线“做梦”，以几乎为零的边际成本评估不同的探针搜索策略，规避自然语言总结带来的偏见与探索多样性坍塌。

---

## 🛡️ 4. 多时间尺度可塑性与回归安全门禁

根据预注册演进协议（[`docs/PREREGISTRATION.md`](docs/PREREGISTRATION.md)），系统的持续学习与权重可塑性采用严格的**多时间尺度分层机制**，取代容易导致灾难性遗忘的在线单步 SGD：

- **T0（即时）**：符号知识库检索增强与 Context 提示词动态加载（`KnowledgeLibrary`）。
- **T1（巩固）**：离线“睡眠”阶段的任务族 LoRA 适配器参数微调（`Consolidator`），采用因果价值加权回放：
  $$p(i) \propto w_i \cdot e^{-\Delta t_i / \tau} \cdot (1 + \text{hardness}_i)$$
- **T2（合并）**：跨周期通过长期审核后，将成熟适配器合并入基座。
- **任务族适配器物理隔离**：各任务族 LoRA（`AdapterBank`）独立寻址与路由，互不干扰，杜绝跨族负迁移。
- **自动化回归门禁（`RegressionGate`）**：提交前自动评测，若历史任一任务族准确率下降 $> 2\%$、通用无 DSL 编程探针得分下降 $> 3\%$、或假验证率 $> 0.0\%$，即刻阻断提交并触发版本回滚。

---

## 📂 5. 仓库目录结构

```
eve-3/
├── README.md                          # 英文主文档与系统架构
├── README_zh.md                       # 中文说明文档（当前文件）
├── pyproject.toml                     # Python 包规范与依赖配置
├── requirements.txt                   # Pip 依赖清单
├── LICENSE                            # MIT 开源许可证
├── docs/
│   ├── ARCHITECTURE.md                # 架构设计详解
│   ├── CONSOLIDATION.md               # 睡眠微调与安全回滚门禁架构设计
│   ├── CONTINUAL_LEARNING_RESULTS.md  # 持续学习 (BWT抗遗忘/FWT前向迁移) 评测报告
│   ├── EXPERIMENT_RESULTS.md          # 4组基线全量消融实验报告
│   ├── MATHEMATICS.md                 # 完整数学公式推导与算法规范
│   ├── PREREGISTRATION.md             # 预注册指标与验收阈值协议
│   ├── ROADMAP.md                     # 分阶段路线图与验收标准 (Phase 0-11)
│   └── RSI_INTEGRATION.md             # 发现树与 RSI 重放模拟理论
├── eve3/
│   ├── config.py                      # 全局运行时配置与超参数控制
│   ├── models.py                      # 证据链模型、验证凭证与学习抽象类
│   ├── dsl/                           # 确定性函数领域特定语言 (DSL)
│   │   ├── ast.py                     # AST 节点抽象、MDL 描述长度与硬深度检查
│   │   ├── interpreter.py             # S-表达式解析与沙盒执行环境
│   │   └── primitives.py              # 高阶函数与列表/逻辑算子
│   ├── system1_proposer/              # 直觉与假设提议器 (System 1)
│   │   ├── generator.py               # MLX-LM 编排与启发式候选生成
│   │   └── sandbox.py                 # 可见示例多候选沙盒验证
│   ├── system2_falsifier/             # 贝叶斯主动证伪引擎 (System 2)
│   │   ├── bayesian_prober.py         # 闭式互信息 IG(x) 与 Laplace 后验更新
│   │   ├── smt_distinguisher.py       # Z3 SMT 符号区分输入生成与支持矩阵
│   │   └── cegis_loop.py              # CEGIS 主动证伪协调回路与诚实验证状态机
│   ├── system3_crystallizer/          # 知识晶化与算子库学习 (System 3)
│   │   ├── library.py                 # SQLite 持久化抽象算子库
│   │   └── value_compressor.py        # 基于 AST 节点 MDL 的次模价值加权贪心压缩
│   ├── discovery/                     # RSI 递归自我改进层
│   │   ├── tree.py                    # 因果拓扑发现树与反事实离线策略重放器
│   │   └── policy.py                  # 版本化探索策略配置与打分
│   ├── plasticity/                    # 多时间尺度可塑性与安全门禁
│   │   ├── adapter_bank.py            # 任务族隔离 LoRA 库管理与安全回滚
│   │   ├── consolidator.py            # 离线睡眠微调训练循环与因果加权回放
│   │   └── regression_gate.py         # 预注册指标自动化回归安全门禁
│   └── search/                        # 多策略搜索控制器
│       ├── controller.py              # 统一神经/符号搜索调度器
│       └── enumerator.py              # 类型剪枝符号 AST 枚举器
├── benchmarks/
│   ├── families/                      # 结构化任务族基准集
│   │   ├── manifest.json              # 任务族清单与留出族定义
│   │   ├── list_mapping.json          # 映射类任务族
│   │   ├── list_filtering.json        # 过滤类任务族
│   │   ├── list_reduction.json        # 归约类任务族
│   │   ├── list_structural.json       # 结构变换任务族
│   │   └── list_composition.json      # 严格留出组合任务族 (前向迁移 FWT 测试)
│   ├── general_coding_probe.json      # 通用无 DSL 编程能力探针集 (抗遗忘测试)
│   ├── dev_train.json                 # 训练集拆分
│   ├── dev_eval.json                  # 域内评测集拆分
│   └── held_out_test.json             # 严格泛化隐藏测试集
├── experiments/
│   ├── run_continual_learning.py      # 持续学习 (BWT/FWT) 评测脚本
│   ├── run_full_ablation.py           # 4组基线全量消融实验脚本 (支持多种子评测)
│   ├── run_library_ablation.py        # 知识库复用收益消融脚本
│   └── run_policy_evolution.py        # 发现树因果策略回放与泛化验证脚本
├── tests/                             # 44 项严密单元测试套件 (100% 通过)
```

---

## ⚡ 6. 快速开始与实验运行

### 安装环境
```bash
git clone https://github.com/Prognosticate-X/eve-3.git
cd eve-3
pip install -e .
```

### 运行全套单元测试
兼容 Python 标准库 `unittest` 与 `pytest`：

```bash
# 使用标准库 unittest discover 运行
python3 -m unittest discover -s tests -p "test_*.py"

# 或使用 pytest 运行
pytest tests/
```

### 运行端到端主动 CEGIS 合成实验
```python
from eve3.config import EveConfig
from eve3.system2_falsifier.cegis_loop import CEGISLoop, VerificationStatus

# 定义真实环境逻辑（例如：对列表各元素自增 1）
def oracle(lst):
    return [x + 1 for x in lst]

# 启动主动 CEGIS 循环，并注入独立隐藏测试集严格检验
config = EveConfig(max_falsification_rounds=5)
loop = CEGISLoop(config)
result = loop.run_synthesis(
    initial_examples=[([1, 2], [2, 3])],
    oracle_fn=oracle,
    held_out_tests=[([10, 20], [11, 21]), ([-5, 0], [-4, 1])],
)

print(f"验证状态: {result.status.value}, 是否最终收敛: {result.converged}")
if result.converged:
    print(f"成功合成程序: {result.verified_program.code_str}")
    print(f"隐藏测试集准确率: {result.held_out_accuracy * 100:.1f}%")
```

---

## 📈 6. 分阶段研发路线图（Roadmap）

- **Phase 0：基础地基**（已完成）  
  轻量级函数式 DSL AST、S-表达式解析器、沙盒执行器与基准测试集规范。
- **Phase 1：System 1 假设生成器**（已完成）  
  Few-shot 提示词编排、本地模型/启发式生成管线与语法沙盒过滤。
- **Phase 2：System 2 贝叶斯主动证伪**（已完成核心闭环）  
  精确互信息闭式解、SMT 区分性输入提取、Laplace 后验更新与 CEGIS 主循环。
- **Phase 3：System 3 价值加权晶化**（已完成核心机制）  
  SQLite 知识库底座、任务家族多样性加权、次模贪心算子库压缩。
- **Phase 4：对照消融与量化评测**（进行中）  
  在完整基准任务集上对比：① EVE-3 完整版、② 无晶化版、③ 无证伪过拟合版，产出样本效率与泛化率消融曲线。
- **Phase 5：跨域迁移与业务落地**（规划中）  
  将这套流程迁移至 Agent 规则推断与超参自动调优等实际复杂任务。

---

## 📚 7. 参考文献与理论根基

1. **Active Learning for Neurosymbolic Program Synthesis** (arXiv:2508.15750) — *版本空间剪枝与区分性主动探测*
2. **Dream-RSI: Recursive Self-Improvement through Evolving Worlds** (arXiv:2609.14858, Google × DeepMind × UMD) — *基于历史发现树重放模拟的探索策略递归演化*
3. **The Last AI Built by Humans: Toward Genuine Recursive Self-Improvement** (arXiv:2609.11873) — *RSI 严格定义与五阶段自主演化分级*
4. **Generalized Binary Search** (Nowak, 2011) — *广义二分搜索与版本空间信息论样本复杂度上界*
5. **DreamCoder: Bootstrapping inductive program synthesis with wake-sleep library learning** (Ellis et al.) — *神经符号唤醒-睡眠库学习范式*
6. **Stitch: Top-Down Synthesis for Library Learning** (Bowers et al., arXiv:2211.16605) — *自顶向下 AST 高效程序压缩与抽象学习*

---

## 📄 开源许可证

本项目采用 [MIT 许可证](LICENSE) 开源。
