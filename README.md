# BRAIN-POWER · 可溯源 AI 健身搭子

一个懂运动科学的健身搭子：聊训练、排计划、记你的逐组数据，**每个关键结论都给出可溯源的文献出处**——出处必须真实存在于知识库召回原文，编造会被代码级护栏打回重答。

> 定位：不是套壳健身问答。三层能力——建议**有迹可循**（RAG 溯源）、计划**动态调整**（真实训练数据驱动）、相处**有活人感**（关系记忆 + 陪伴式语气）。产品设计详见 `docs/`（PRD）。

## 核心设计决策

**1. 可信度护栏是代码级的，不靠提示词自觉（`app/services/agent.py`）**

- **出处校验**：回答中出现的书名/论文引用（中文《》、`标题（作者，年份）`、英文 `Author et al., 2017` 三种格式），逐条与本次 RAG 召回原文比对，找不到 → 打回重答（上限 1 次，强制收答仍校验）。
- **Grounding**：精确统计值（p 值、百分比、倍数、效应量）必须在召回原文中逐字存在，否则降级为定性表述。库中没有的内容要求模型明说"这是经验，不来自文献"。
- 设计原因：提示词层约束在长对话中必然衰减（v1 实测漏网 `Phillips 2014` 等英文引用格式），可信度是本产品的生命线，必须代码兜底。

**2. 知识库是外部真实文献，不是模型自述**

12 份 Springer 专著 + 公开论文（`scripts/ingest_pdfs.py` REGISTRY 登记真实书目与 DOI），~11000 切片入库 PostgreSQL + pgvector，按页溯源。引用格式在回答中原样给出（作者+年份+DOI 链接）。

**3. 模型无关的 provider 抽象层（`app/services/provider.py`）**

OpenAI 兼容端点注册表 + 统一 `chat_with_tools / chat_stream` 接口，换模型 = 改一行 `.env`。当前 DeepSeek 主力（性价比 + 中文对话活人感），DashScope qwen-plus 兜底，故障自动降级。选型决策记录：预fill 耗时实测排除 prefill 瓶颈、违规重答是延迟主因、token 成本从 v1 的 ~40k 降到 5-9k（只注入召回段落）。

**4. 提示词是版本化需求资产（`app/prompts/`）**

每版可回滚、有 CHANGELOG、上线前跑 3 轮 × 5 题稳定性测试。角色是"陪伴式健身搭子"：语气层负责活人感（记得你上次说过什么、先接人再答事），专业内核与安全红线（就医红旗信号）任何版本原样保留。

## 架构

```
解释层 Why    对话 Agent：LLM + rag_search(知识检索) + get_progress/log_exercise(数据)
              + save_memory(长期记忆) + 代码级护栏(出处校验/grounding)
执行层 What   计划/打卡/逐组落库（PostgreSQL），每日记录（睡眠/酸痛/体重）
进化层 Adapt  规则引擎按周期数据裁决加重/维持/减载；pgvector 记忆让搭子"记得你"
```

## 运行

```bash
# 1. 数据库：任意 PostgreSQL 16 + pgvector（示例用 Docker，端口 5433）
docker run -d --name coach-pg -p 5433:5432 -e POSTGRES_USER=coach -e POSTGRES_PASSWORD=coach pgvector/pgvector:pg16
docker exec coach-pg psql -U coach -c "CREATE DATABASE coach_v2"

# 2. 配置：复制 .env.example 为 .env，填入 DashScope（embedding）与 LLM 的 key
cp .env.example .env

# 3. 知识库入库：书籍/论文 PDF 放入知识目录，在 scripts/ingest_pdfs.py REGISTRY 登记真实书目信息
python scripts/ingest_pdfs.py

# 4. 启动（移动端 H5：http://localhost:8011）
python -m uvicorn app.main:app --port 8011
```

依赖见 `requirements.txt`（FastAPI / SQLAlchemy / pgvector / openai 兼容 SDK / pypdf）。

## 目录

```
app/
  main.py           FastAPI：SSE 流式对话、计划/记录/打卡 API、无缓存响应头
  services/
    agent.py        Agent 循环 + 出处校验/grounding 护栏（核心）
    provider.py     跨厂商模型抽象（DeepSeek / DashScope，注册表切换）
    rag.py          PDF 切块、embedding、召回（citation/heading/distance）
    tools.py        工具 schema：rag_search / 计划 / 逐组记录 / 记忆
  prompts/          提示词版本化资产 + CHANGELOG（校准通过才上线）
  config.py         端点注册表与配置
static/index.html  移动端 H5（对话/计划/记录/我的 四页签，流式渲染，工具链过程可视化）
knowledge/sources/ 文献原文（版权原因不入库，见目录内 README）
scripts/           入库 / 稳定性测试 / 22 题评测 / 模型横评
eval/              22 题测评集与稳定性测试结果
```

## 已知边界

- 知识库覆盖不全（当前以训练科学、运动生理、营养补剂为主），库外问题模型会标注"经验之谈"而非硬编引用——这是设计行为，不是缺陷。
- 兜底链触发时（DeepSeek 故障降级 qwen），回复风格可能有差异。
- 非医疗产品：伤病与红旗信号一律劝就医，不做诊断。
