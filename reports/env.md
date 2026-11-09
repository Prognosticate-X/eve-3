# 评测环境基线记录 (`reports/env.md`)

## 1. 硬件规格与操作系统（固定基准）

- **芯片型号**：Apple M1 Max
- **CPU 架构**：`arm64`（Darwin Kernel 27.0.0, Tue Aug 11 21:22:49 PDT 2026）
- **统一内存**：**64 GB**（`hw.memsize = 68719476736` 字节）
- **操作系统**：macOS 27.0.1 (Build 26A434)
- **主机标识**：`Prognosticates-MacBook-Pro.local`

> **⚠️ 运行机器勘误与固定声明**：
> - 在 Stage S0 审计报告中，记录为 "Apple M1 Max (64 GB 统一内存)"；
> - 在 Stage S1 报告中，文档文字误写为 "Apple M4 16GB"（此为文档笔误/幻觉）。
> - **事实澄清**：本机硬件自始至终为 **Apple M1 Max 64GB**，所有阶段（S0 审计、S0.1、S1、S1.1 以及后续全部实验）均在同一台 Apple M1 Max 64GB 机器上运行。后续每份阶段报告一律以本文件记录的机器为准。

---

## 2. 软件运行环境与核心依赖版本

- **Python 版本**：`3.14.8` (`/Users/prognosticatex/homebrew/bin/python3`)
- **Pytest 版本**：`9.2.0` (`/Users/prognosticatex/homebrew/bin/pytest`)
- **z3-solver 版本**：`4.15.4.0`
- **Apple MLX 核心版本**：`0.32.4`（固定于 `pyproject.toml`）
- **Apple MLX-LM 版本**：`0.32.2`（固定于 `pyproject.toml`）
- **默认本地 LLM 模型**：`mlx-community/Qwen2.5-Coder-3B-Instruct-4bit`（本地缓存路径：`~/.cache/huggingface/hub/models--mlx-community--Qwen2.5-Coder-3B-Instruct-4bit`）
