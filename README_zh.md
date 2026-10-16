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

## 📂 4. 仓库目录结构

```
eve-3/
├── README.md                          # 英文主文档与系统架构
├── README_zh.md                       # 中文说明文档（当前文件）
├── pyproject.toml                     # Python 包规范与依赖配置
├── requirements.txt                   # Pip 依赖清单
├── LICENSE                            # MIT 开源许可证
├── docs/
│   ├── ARCHITECTURE.md                # 架构设计详解
│   ├── MATHEMATICS.md                 # 完整数学公式推导与算法规范
│   ├── ROADMAP.md                     # 分阶段路线图与验收标准
│   └── RSI_INTEGRATION.md             # 发现树与 RSI 重放模拟理论
├── eve3/
│   ├── config.py                      # 全局运行时配置与超参数控制
│   ├── dsl/                           # 确定性函数领域特定语言 (DSL)
│   │   ├── ast.py                     # AST 节点抽象与 MDL 描述长度
│   │   ├── interpreter.py             # S-表达式解析与沙盒执行环境
│   │   └── primitives.py              # 高阶函数与列表/逻辑算子
│   ├── system1_proposer/              # 直觉与假设提议器 (System 1)
│   │   ├── generator.py               # MLX-LM 编排与启发式候选生成
│   │   └── sandbox.py                 # 可见示例多候选沙盒验证
│   ├── system2_falsifier/             # 贝叶斯主动证伪引擎 (System 2)
│   │   ├── bayesian_prober.py         # 闭式互信息 IG(x) 与 Laplace 后验更新
│   │   ├── smt_distinguisher.py       # Z3 SMT 符号区分输入生成
│   │   └── cegis_loop.py              # CEGIS 主动证伪协调回路
│   ├── system3_crystallizer/          # 知识晶化与算子库学习 (System 3)
│   │   ├── library.py                 # SQLite 持久化算子库底座
│   │   └── value_compressor.py        # 面向复用价值的次模贪心压缩
│   └── discovery/                     # RSI 递归自我改进层
│       └── tree.py                    # 发现树与反事实离线策略重放器
├── benchmarks/
│   └── list_functions.json            # 列表变换、过滤与归约基准任务集
└── tests/
    ├── test_dsl.py                    # DSL AST 与语法解析单元测试
    ├── test_prober.py                 # 信息增益与贝叶斯更新单元测试
    ├── test_crystallizer.py           # SQLite 持久化与价值加权测试
    ├── test_discovery_tree.py         # 发现树构建与离线重放测试
    └── test_cegis_loop.py             # CEGIS 端到端主动合成测试
```

---

## ⚡ 5. 快速开始与实验运行

### 安装环境
```bash
git clone https://github.com/Prognosticate-X/eve-3.git
cd eve-3
pip install -e .
```

### 运行全套单元测试
```bash
python3 -m unittest discover -s tests -p "test_*.py"
```

### 运行端到端主动 CEGIS 合成实验
```python
from eve3.config import EveConfig
from eve3.system2_falsifier.cegis_loop import CEGISLoop

# 定义真实环境逻辑（例如：对列表各元素自增 1）
def oracle(lst):
    return [x + 1 for x in lst]

# 启动主动 CEGIS 循环
config = EveConfig(max_falsification_rounds=5)
loop = CEGISLoop(config)
result = loop.run_synthesis([([1, 2], [2, 3])], oracle_fn=oracle)

if result.converged:
    print(f"成功合成程序: {result.verified_program.code_str}")
    print(f"执行轮数: {result.rounds_executed}, 消耗探针数: {len(result.probes_used)}")
    print("未见输入 [10, 20] 泛化测试输出:", result.verified_program.evaluate([10, 20]))
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
