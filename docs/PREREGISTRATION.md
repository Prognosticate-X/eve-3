# EVE-3 评测指标与验收准则预注册协议 (Preregistration Protocol)

> **注册日期 (Registration Date):** 2026-10-18  
> **协议版本 (Protocol Version):** v1.0  
> **适用研究阶段:** Phase 5 – Phase 11  
> **硬件与执行约束:** 单机受限环境 (Apple Silicon, 32GB Unified Memory), 无在线梯度更新  

---

## 1. 核心科学假设与可证伪命题 (Core Hypotheses)

在资源受限环境下，引入**三时间尺度分层可塑性（T0 符号库 + T1 睡眠巩固 LoRA + T2 权重合并）**、**因果价值加权经验回放**、**严格回归测试门**与**基于信息增益和压缩收益的自主探索引擎**的 EVE-3 闭环系统：

1. **假设 H1 (样本效率)**：相比无主动证伪（Baseline A）、无知识结晶（Baseline B）及纯 few-shot 采样基线，达到 $\ge 95\%$ held-out 准确率所需的 Oracle/环境查询数中位数显著下降。
2. **假设 H2 (前向迁移 FWT)**：在完全未见的新任务族（Hold-out Family）上，利用积累的抽象算子与任务族适配器，合成成功率显著高于冷启动基线。
3. **假设 H3 (抗遗忘 / 后向迁移 BWT)**：在连续学习多个任务族的过程中，通过因果价值加权回放与任务族适配器隔离，历史任务族准确率不发生灾难性遗忘。
4. **假设 H4 (通用能力保持)**：经验内化与 LoRA 睡眠巩固不会侵蚀与 DSL 无关的通用编码与逻辑推理能力。
5. **假设 H5 (预测校准)**：System 2 的贝叶斯置信度后验具备良好的概率校准性，期望校准误差 (ECE) 保持在严格置信区间内。
6. **假设 H6 (零假验证率)**：系统绝不将未通过 100% 独立测试集或形式化证明的程序标记为“已验证 (converged)”。

---

## 2. 预注册指标与达标阈值 (Preregistered Metrics & Passing Thresholds)

所有后续阶段的实验与模型版本提交，必须严格对照下述预先冻结的阈值矩阵，任何未达标情况均触发回归回滚或阻断合并：

| 评估指标 | 符号与公式定义 | 预注册验收基准线 (相对最强基线) | 判定机制 |
| :--- | :--- | :---: | :--- |
| **样本效率 (Sample Efficiency)** | $\mathrm{Median}(\text{OracleQueries}_{95\%})$ | **降低 $\ge 30\%$** | $p < 0.05$ (配对 Wilcoxon 检验) |
| **前向迁移 (FWT)** | $\mathrm{Acc}_{\text{accumulated}}(\mathcal{F}_{\text{new}}) - \mathrm{Acc}_{\text{cold}}(\mathcal{F}_{\text{new}})$ | **$\ge +10$ 个百分点** | 留出族测试集独立验证 |
| **后向迁移 / 遗忘 (BWT)** | $\max_{t < T} R_{t, j} - R_{T, j}$ | **遗忘 $\le 2$ 个百分点** | 历史各族 Held-out 集持续监控 |
| **通用能力保持率** | $\frac{\mathrm{Score}_{\text{new}}(\text{GeneralProbe})}{\mathrm{Score}_{\text{base}}(\text{GeneralProbe})}$ | **相对基座下降 $\le 3\%$** | `benchmarks/general_coding_probe.json` |
| **期望校准误差 (ECE)** | $\sum_{m=1}^{M} \frac{\|B_m\|}{N} \|\mathrm{acc}(B_m) - \mathrm{conf}(B_m)\|$ | **$\mathrm{ECE} \le 0.05$** | 10 等宽区间分桶校准测试 |
| **假验证率 (False Verification)** | $\frac{\sum \mathbb{I}(\text{status}=\text{converged} \land \mathrm{acc}_{\text{hidden}} < 1.0)}{N}$ | **严格等于 $0.0\%$** | 违反即判定为系统性致命缺陷 |
| **算力与运行成本** | 墙钟时间、峰值显存 (MB)、能耗估算 | 报告均值与方差 | 不设淘汰阈值，必须完整记录 |

---

## 3. 任务族划分与数据集隔离协议 (Dataset Partitioning Protocol)

为消除数据泄露并使前向迁移（FWT）具有统计学可信度，基准集按算法结构强制划分为独立任务族：

### 3.1 训练与已知任务族 (Training & In-Distribution Families)
1. **`list_mapping`** (元素级变换):
   - 包含增减、乘法、绝对值、仿射变换等。
2. **`list_filtering`** (谓词条件筛选):
   - 包含奇偶过滤、数值阈值过滤、正负号判断等。
3. **`list_reduction`** (聚合与归约计算):
   - 包含求和、乘积、极值、元素计数等。
4. **`list_structural`** (结构性排列与切片):
   - 包含反转、去头、恒等变换、交替提取等。

### 3.2 严格留出任务族 (Strictly Held-Out Cross-Family Suite)
- **`list_composition`** (高阶组合逻辑):
  - 任务结构必须由两个以上基础族复合而成（例如“先递增再过滤”、“先过滤偶数再求和”）。
  - **严禁**进入 T0 初始词表与 T1 训练阶段，仅在跨族泛化测试时接入。

### 3.3 通用能力探针集 (General Coding Probe)
- 文件路径: `benchmarks/general_coding_probe.json`
- 考察模型在通用 Python 算法（递归、双指针、哈希统计、位运算、边界处理）上的表现，确保 DSL 专用适配器没有发生灾难性表征漂移或代码理解退化。

---

## 4. 统计检验与消融矩阵协议 (Statistical Rigor & Ablation Protocol)

### 4.1 随机种子与重复实验
- 所有核心实验必须在固定的 **5 个独立随机种子**下执行：`[42, 100, 2024, 777, 999]`。
- 报告格式统一为：$\text{Mean} \pm \text{Std}$ 以及 95% 置信区间 (Bootstrap 1000 次重采样)。

### 4.2 消融对比矩阵 (Ablation Matrix)
- **A0 (Naive Few-shot)**: 无证伪、无结晶、无睡眠巩固。
- **A1 (Falsify Only)**: 仅启用贝叶斯主动证伪器。
- **A2 (Crystallize Only)**: 仅启用 MDL 抽象算子结晶。
- **A3 (Closed-Loop Baseline)**: 主动证伪 + 算子结晶 (P0~P3 状态)。
- **A4 (Sleep Consolidation)**: A3 + T1 LoRA 睡眠微调 + 价值加权回放。
- **A5 (Autonomous Discovery)**: A4 + 课程驱动自生成任务。
- **A6 (EWC Baseline)**: 以 EWC 参数重要性正则替代价值加权回放作为持续学习消融项。

---

## 5. 变更管理与回归门协议 (Regression Gate Protocol)

任何写入 `AdapterBank` 或发布新模型版本的动作，必须无条件通过 `eve3/plasticity/regression_gate.py` 的自动化流水线门禁：

```text
[新适配器候选 / 巩固训练输出]
              │
              ▼
    [RegressionGate 运行]
      ├── 1. 验证历史任务族准确率: Δ Acc(family) >= -2.0%
      ├── 2. 验证通用能力基准得分: Score(general) >= 0.97 * BaseScore
      ├── 3. 验证假验证率: FalseVerificationRate == 0.0%
      └── 4. 验证整体任务准确率: OverallAcc >= 80.0%
              │
        ┌─────┴─────┐
     通过 (Pass)   未通过 (Fail)
        │           │
        ▼           ▼
  [提交新版本]   [触发回滚 / 记录根因 / 降低 LR / 增大回放]
```

---

*本协议一经提交并纳入版本控制，后续实验报告必须遵循上述指标及阈值进行客观陈述与可信归因。*
