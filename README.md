# 铁馆教练 coach-v2

可解释 AI 健身教练系统，v2 架构：**外部专业文献知识库 + RAG 召回 + 引用溯源到真实出处**（书名/论文+作者+年份+链接），替代 v1 的自建概念卡体系。

产品需求文档：`../2026-10-23-23-42-20/健身教练系统-PRD v2.0.md`（开发唯一权威，偏离需先改 PRD）。

## 架构（PRD §5.1）

```
解释层 Why：对话 Agent（LLM + rag_search 知识检索 + 数据工具）
执行层 What：计划/打卡/逐组落库、每日记录
进化层 Adapt：规则引擎（确定性裁决）、pgvector 长期记忆
```

## 运行

```bash
# 1. 数据库（复用 v1 的 coach-pg 容器 @5433；若未运行，到 coach-system 目录 docker compose up -d）
docker exec coach-pg psql -U coach -c "CREATE DATABASE coach_v2"

# 2. 知识库入库（书籍/论文文本放 knowledge/sources/，元数据登记在 scripts/ingest.py REGISTRY）
python scripts/ingest.py

# 3. 服务
python -m uvicorn app.main:app --port 8011
```

## 目录

- `app/prompts/`：提示词版本化资产（PRD §5.5：每版必须交小王校准，通过才可上线）
- `knowledge/sources/`：文献原文（书/论文完整文本）
- `scripts/`：ingest 入库、eval 评测、bakeoff 模型横评
- `eval/`：22 题测评集与金标准（从 v1 迁移）

## 从 v1 迁移的资产

PG/pgvector 基础设施、规则引擎文本、每日记录/打卡/计划表结构、22 题测评集、SSE 与缓冲渐进放行工程经验。v1 的概念卡体系（C01-C58、引用纪律检测、证据审校）已废除，不再迁移。
