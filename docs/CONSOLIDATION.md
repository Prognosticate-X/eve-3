# EVE-3 睡眠巩固（Consolidator）与回归门架构设计

> **对应阶段:** Phase 6  
> **理论参照:** 互补学习系统（Complementary Learning Systems, CLS）与经验回放（Experience Replay）  
> **硬件适配:** Apple Silicon M1/M2/M3/M4 (统一内存架构, 离线批处理)  

---

## 1. 理论动机：为什么不做在线单步更新？

在单机受限环境（如笔记本 32GB 显存）与小型量化代码模型（3B 4-bit）场景下，尝试在线单步 SGD（每次验证成功一个程序即执行一次梯度回传）存在三大致命缺陷：

1. **4-bit 量化权重的梯度不稳定性**：量化基座必须通过额外 LoRA 适配器更新，频繁的小步更新会迅速导致适配器参数过饱和与数值漂移。
2. **灾难性遗忘（Catastrophic Forgetting）**：连续流式数据具有高度的时间自相关性，直接在线微调是导致模型迅速退化为特定任务过拟合的典型配方。
3. **因果与归因断裂**：在线单步更新使每次实验完全不可复现，无法将性能变化与特定机制进行统计归因。

因此，EVE-3 遵循 **互补学习系统（CLS）** 设计原则，采用“三时间尺度可塑性”：
- **T0（快通道，毫秒~秒）**：符号知识库（`KnowledgeLibrary`）即时写入与上下文提示词检索；
- **T1（慢通道，小时~天）**：离线“睡眠阶段”的参数巩固（`Consolidator`），集成反事实回放与回归测试门；
- **T2（固化通道，周级）**：通过多轮长期门禁审核的成熟适配器安全合并入基座。

---

## 2. 数据构建：从 Discovery Tree 中提取因果经验

`Consolidator` 的数据源完全来自自身真实探索的拓扑结构 `DiscoveryTree`，不依赖任何外部未知语料：

### 2.1 正向微调样本（SFT Pairs）
从所有状态标记为 `outcome == "verified"` 且实际通过独立隐藏测试集的节点提取：
$$\mathcal{D}_{\text{new}} = \big\{ (\text{task\_description}, P^*) \mid P^* \in \text{VerifiedNodes} \big\}$$

### 2.2 证伪偏好对（Preference / Counterexample Pairs）
将同任务下被 Z3 或贝叶斯主动探针证伪的候选程序 $P_{\text{rejected}}$ 与最终通过验证的程序 $P^*$ 进行配对，并附带证伪反例 $x_{\text{counter}}$：
$$\mathcal{D}_{\text{pairs}} = \big\{ (\text{task\_description}, P_{\text{rejected}}, P^*, x_{\text{counter}}) \big\}$$

### 2.3 历史因果价值加权回放样本（Value-Weighted Replay）
从历史任务族中抽取回放样本，采样概率严格受抽象复用价值、时间衰减与探索难度驱动：
$$p(i) \propto w_i \cdot e^{-\Delta t_i / \tau} \cdot (1 + \text{hardness}_i)$$
其中：
- $w_i = |\text{TaskFamilies}(P_i)| \times (1 + \ln(1 + \text{ReuseCount}_i))$ 为次模复用价值权重；
- $\Delta t_i$ 为该程序发现至今的时间跨度，$\tau$ 为半衰期衰减常数（默认 72 小时）；
- $\text{hardness}_i$ 为当时发现该程序所消耗的累积因果搜索成本 `causal_path_cost`。

---

## 3. 睡眠微调目标函数 (Consolidation Objective)

睡眠阶段的微调联合优化四个目标：

$$\mathcal{L} = \mathcal{L}_{\text{SFT}}(\mathcal{D}_{\text{new}}) + \lambda_{\text{pref}}\,\mathcal{L}_{\text{pref}}(\mathcal{D}_{\text{pairs}}) + \lambda_{\text{replay}}\,\mathcal{L}_{\text{SFT}}(\mathcal{D}_{\text{replay}}) + \lambda_{\text{KL}}\,\mathrm{KL}\big(\pi_\theta \,\|\, \pi_{\text{base}}\big)$$

各超参数预设配置：
- $\lambda_{\text{pref}} = 0.5$：强化对被证伪负样本与死胡同的规避；
- $\lambda_{\text{replay}} = 0.3$：对抗对新任务族的过拟合，保障旧族保留；
- $\lambda_{\text{KL}} = 0.1$：严格锚定基座模型，防止表示空间漂移与通用代码能力退化。

---

## 4. 自动化回归安全门禁（Regression Gatekeeper）

训练产生候选适配器后，**严禁直接激活生效**，必须无条件通过 `RegressionGate` 的四重自动化安全审查：

```
训练候选 LoRA_candidate
          │
          ▼
   [RegressionGate]
      ├── 1. 历史任务族准确率: Δ Acc(F_j) <= 2.0% (无显著后向遗忘)
      ├── 2. 通用编程探针保持: Δ Score(general_coding_probe) <= 3.0%
      ├── 3. 严格假验证率: FalseVerificationRate == 0.0%
      └── 4. 最低准入胜率: OverallAccuracy >= 80.0%
          │
    ┌─────┴─────┐
 通过 (Pass)   未通过 (Fail)
    │           │
    ▼           ▼
[激活入库]    [即刻回滚 Rollback]
BankVersion++ 记录根因，降低学习率，增大回放比例
```

---

## 5. 任务族物理隔离与版本回滚协议

- **物理隔离**：每个任务族（`list_mapping`, `list_filtering`, `list_reduction`, `list_structural`）在 `AdapterBank` 中持有专属的 LoRA 权重，根据任务描述语义与输入类型自动路由。
- **快照与校验**：每次激活产生带有 SHA256 校验和的不可变快照 `BankVersion`。
- **原子回滚**：当且仅当回归门全部放行，快照才推进；一旦检测到劣化，系统原子恢复上一版本的适配器映射，确保系统始终处于单调不退化的安全边界内。
