# 中医药智能知识服务平台 — 技术文档

> TCM-RAG-Platform v1.0.0 系统架构与技术设计文档

---

## 目录

- [项目概述](#项目概述)
- [系统架构](#系统架构)
- [技术栈](#技术栈)
- [目录结构](#目录结构)
- [核心模块说明](#核心模块说明)
- [API 接口总览](#api-接口总览)
- [数据模型](#数据模型)
- [配置管理](#配置管理)
- [部署指南](#部署指南)
- [扩展指南](#扩展指南)

---

## 项目概述

**中医药智能知识服务平台**（TCM-RAG-Platform）是一个基于 RAG（Retrieval-Augmented Generation）技术的中医药古籍知识问答与检索系统。

### 核心目标

- **知识数字化**：将中医药古籍、教材、临床指南等文献进行结构化入库和向量化索引
- **智能问答**：结合三路混合检索（稀疏 + 稠密 + 图谱）与大语言模型，为用户提供准确、有据可查的中医药知识问答
- **知识图谱**：自动从文本中抽取中医实体（症状、证候、方剂、中药等）及其关系，构建中医知识图谱
- **质量闭环**：通过用户反馈收集、Bad Case 管理、自动化评测体系，持续优化检索与生成质量

### 愿景

打造一个**专业、可信、可追溯**的中医药知识服务平台，让中医药从业者和研究者能够高效地检索和理解古籍中的临床智慧。

---

## 系统架构

### 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                          客户端层                                │
│  ┌─────────────────────┐    ┌──────────────────────────┐        │
│  │   用户端 (React)     │    │   管理后台 (React)        │        │
│  │   :3000 / :5173     │    │   :3001 / :5174           │        │
│  └─────────┬───────────┘    └──────────┬───────────────┘        │
└────────────┼───────────────────────────┼────────────────────────┘
             │                           │
             ▼                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Nginx 反向代理 (:80)                         │
│         /api → backend  │  /admin → admin  │  / → user          │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                   FastAPI 后端 (:8000)                           │
│  ┌──────────┐ ┌─────────┐ ┌──────────┐ ┌────────────┐          │
│  │ 认证模块  │ │ RAG 模块 │ │ 文档管理  │ │ 知识图谱   │          │
│  │ (JWT)    │ │(Pipeline)│ │ (CRUD)   │ │ (Neo4j)    │          │
│  └──────────┘ └─────────┘ └──────────┘ └────────────┘          │
│  ┌──────────┐ ┌─────────┐ ┌──────────┐ ┌────────────┐          │
│  │ 对话管理  │ │ 评测模块 │ │ 反馈系统  │ │ 管理后台   │          │
│  │(Session) │ │ (Eval)  │ │(Feedback)│ │ (Admin)    │          │
│  └──────────┘ └─────────┘ └──────────┘ └────────────┘          │
└──────┬──────────┬──────────┬──────────┬──────────┬──────────────┘
       │          │          │          │          │
       ▼          ▼          ▼          ▼          ▼
┌──────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
│  MySQL   │ │ Redis  │ │  ES    │ │ FAISS  │ │ Neo4j  │
│  8.0     │ │  7     │ │ 8.15   │ │(内存/磁│ │  5     │
│ :3306    │ │ :6379  │ │ :9200  │ │ 盘索引) │ │ :7687  │
└──────────┘ └────────┘ └────────┘ └────────┘ └────────┘
                │
                ▼
       ┌────────────────┐
       │ Celery Worker  │ ← 异步文档入库流水线
       │ (Redis Broker) │
       └────────────────┘
```

### 架构说明

- **前后端分离**：前端 React 应用通过 HTTP API 与后端通信，SSE 实现流式答案
- **Nginx 网关**：统一入口路由，API 代理支持 WebSocket 和 SSE
- **服务层设计**：后端按业务领域拆分为独立 Service，通过依赖注入解耦
- **三路检索**：稀疏（ES BM25）+ 稠密（FAISS 向量）+ 图谱（Neo4j 实体扩展），通过 RRF 融合
- **异步处理**：文档入库通过 Celery 异步执行，避免阻塞 API 请求
- **优雅降级**：每个外部依赖（Redis/ES/Neo4j/FAISS）不可用时系统均可降级运行

---

## 技术栈

### 后端

| 技术 | 版本 | 用途 |
|------|------|------|
| Python | 3.11+ | 运行时 |
| FastAPI | 0.115.0 | Web 框架 |
| Gunicorn | 22.0.0 | WSGI 服务器（生产部署） |
| Uvicorn | 0.30.0 | ASGI 服务器 |
| SQLAlchemy | 2.0.35 | ORM（异步模式） |
| Alembic | 1.13.2 | 数据库迁移 |
| Pydantic | 2.9.0 | 数据校验 & 序列化 |
| pydantic-settings | 2.5.0 | 配置管理 |
| Celery | 5.4.0 | 分布式任务队列 |
| python-jose | 3.3.0 | JWT Token 处理 |
| bcrypt | 4.2.0 | 密码哈希 |
| DashScope SDK | 1.20.0 | 阿里云 LLM/Embedding/Rerank |
| httpx | 0.27.0 | 异步 HTTP 客户端 |

### 前端

| 技术 | 版本 | 用途 |
|------|------|------|
| React | 19.2.4 | UI 框架 |
| TypeScript | 6.0.2 | 类型安全 |
| Vite | 8.0.4 | 构建工具 |
| Ant Design | 6.3.5 | UI 组件库 |
| React Router | 7.14.0 | 路由 |
| Zustand | 5.0.12 | 状态管理 |
| Axios | 1.14.0 | HTTP 客户端 |

### 基础设施

| 技术 | 版本 | 用途 |
|------|------|------|
| MySQL | 8.0 | 关系型数据库 |
| Redis | 7 (Alpine) | 缓存 / 消息队列 |
| Elasticsearch | 8.15.0 | BM25 全文检索 |
| FAISS | 1.8.0 (CPU) | 向量相似度搜索 |
| Neo4j | 5 (Community) | 图数据库 / 知识图谱 |
| MinIO | latest | 对象存储 |
| Nginx | Alpine | 反向代理 / 负载均衡 |
| Docker Compose | 3.8 | 容器编排 |

### LLM 模型（DashScope）

| 模型 | 用途 |
|------|------|
| `qwen-max` | 答案生成（主模型） |
| `qwen-plus` | 查询改写、实体抽取 |
| `text-embedding-v3` | 文本向量化（1024 维） |
| `gte-rerank` | 检索结果重排序 |

---

## 目录结构

```
tcm-rag-platform/
├── .env.example                    # 环境变量模板
├── docker-compose.yml              # Docker Compose 编排文件
├── pyproject.toml                  # Python 项目配置（pytest/black/ruff）
├── requirements.txt                # Python 依赖
│
├── backend/                        # 后端源码
│   └── app/
│       ├── main.py                 # FastAPI 应用入口 & 生命周期管理
│       ├── api/                    # API 层
│       │   ├── deps.py             # 依赖注入（认证、数据库会话）
│       │   ├── router.py           # 路由汇总
│       │   └── v1/                 # v1 版本接口
│       │       ├── auth.py         #   认证接口（注册/登录/刷新/登出）
│       │       ├── users.py        #   用户接口
│       │       ├── chats.py        #   对话接口（会话/消息/流式问答）
│       │       ├── rag.py          #   RAG 预览接口（改写/检索预览）
│       │       ├── documents.py    #   文档管理接口（上传/列表/详情）
│       │       ├── admin.py        #   管理后台接口（用户管理/审核/仪表盘）
│       │       ├── feedback.py     #   反馈接口
│       │       ├── evaluation.py   #   评测接口
│       │       └── knowledge_graph.py  # 知识图谱接口
│       │
│       ├── core/                   # 核心模块
│       │   ├── config.py           #   配置管理（pydantic-settings）
│       │   ├── exceptions.py       #   全局异常定义 & 处理器
│       │   ├── logger.py           #   日志配置（trace_id 链路追踪）
│       │   ├── middleware.py       #   中间件（请求日志/TraceID）
│       │   └── security.py        #   安全工具（JWT/密码哈希）
│       │
│       ├── db/                     # 数据库层
│       │   ├── base.py             #   SQLAlchemy Base 声明
│       │   ├── session.py          #   数据库会话工厂（异步/同步）
│       │   └── repositories/       #   数据仓库（CRUD 封装）
│       │       ├── user_repo.py
│       │       ├── document_repo.py
│       │       ├── chunk_repo.py
│       │       └── ...
│       │
│       ├── models/                 # ORM 模型
│       │   ├── user.py             #   用户模型
│       │   ├── role.py             #   角色模型 & 用户-角色关联
│       │   ├── document.py         #   文档模型
│       │   ├── chunk.py            #   文档分块模型
│       │   ├── session.py          #   会话模型
│       │   ├── message.py          #   消息模型
│       │   ├── feedback.py         #   反馈模型
│       │   ├── eval_task.py        #   评测任务模型
│       │   ├── graph_entity.py     #   图谱实体模型
│       │   ├── answer_log.py       #   答案日志模型
│       │   ├── retrieval_log.py    #   检索日志模型
│       │   └── rerank_log.py       #   重排日志模型
│       │
│       ├── schemas/                # Pydantic Schema（请求/响应）
│       │   ├── auth.py             #   认证 Schema
│       │   ├── chat.py             #   对话 Schema
│       │   ├── document.py         #   文档 Schema
│       │   ├── evaluation.py       #   评测 Schema
│       │   ├── feedback.py         #   反馈 Schema
│       │   ├── graph.py            #   图谱 Schema
│       │   ├── rag.py              #   RAG Schema
│       │   ├── user.py             #   用户 Schema
│       │   └── common.py           #   通用 Schema（分页等）
│       │
│       ├── services/               # 业务逻辑层
│       │   ├── auth_service.py     #   认证服务
│       │   ├── user_service.py     #   用户服务
│       │   ├── chat_service.py     #   对话服务（RAG Pipeline 编排）
│       │   ├── rag_service.py      #   RAG 答案生成编排
│       │   ├── query_rewrite_service.py  # 查询改写服务
│       │   ├── retrieval_service.py      # 三路混合检索服务
│       │   ├── rerank_service.py         # 重排服务
│       │   ├── answer_service.py         # LLM 答案生成 & 流式输出
│       │   ├── prompt_service.py         # Prompt 模板管理
│       │   ├── citation_service.py       # 引用提取服务
│       │   ├── document_service.py       # 文档业务服务
│       │   ├── document_ingest_service.py # 文档入库服务
│       │   ├── chunking_service.py       # 文本分块服务
│       │   ├── graph_build_service.py    # 知识图谱构建服务
│       │   ├── graph_query_service.py    # 知识图谱查询服务
│       │   ├── feedback_service.py       # 反馈服务
│       │   ├── badcase_service.py        # Bad Case 分类服务
│       │   ├── evaluation_service.py     # 评测服务
│       │   ├── admin_service.py          # 管理后台服务
│       │   ├── bootstrap_service.py      # 启动初始化服务
│       │   └── store.py                  # 内存数据缓存层
│       │
│       ├── integrations/           # 外部服务集成客户端
│       │   ├── es_client.py        #   Elasticsearch 客户端
│       │   ├── vector_store.py     #   FAISS 向量存储
│       │   ├── neo4j_client.py     #   Neo4j 图数据库客户端
│       │   ├── llm_client.py       #   DashScope LLM 客户端
│       │   └── embedding_client.py #   DashScope Embedding 客户端
│       │
│       ├── tasks/                  # Celery 异步任务
│       │   ├── __init__.py         #   Celery App 配置
│       │   ├── celery_config.py    #   Celery 详细配置
│       │   └── ingest_tasks.py     #   文档入库任务（完整流水线）
│       │
│       ├── tests/                  # 单元测试
│       └── utils/                  # 工具函数
│           └── response.py         #   统一响应格式
│
├── frontend-user/                  # 用户端前端（React + Vite）
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
│
├── frontend-admin/                 # 管理后台前端（React + Vite）
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
│
├── data/                           # 数据目录
│   ├── dictionaries/               #   数据字典（症状/中药/方剂同义词）
│   │   ├── symptom_synonyms.json
│   │   ├── herb_aliases.json
│   │   └── formula_aliases.json
│   ├── eval/                       #   评测数据集
│   │   ├── retrieval_eval.jsonl
│   │   ├── generation_eval.jsonl
│   │   └── regression_cases.jsonl
│   ├── raw/                        #   原始上传文档
│   └── processed/                  #   处理后的文档
│
└── deploy/                         # 部署配置
    ├── docker/
    │   ├── backend.Dockerfile      #   后端镜像
    │   └── worker.Dockerfile       #   Worker 镜像
    ├── gunicorn_conf.py            #   Gunicorn 配置
    ├── nginx.conf                  #   Nginx 配置
    └── mysql/
        └── init.sql                #   MySQL 初始化脚本
```

---

## 核心模块说明

### 1. 用户认证 (JWT + RBAC)

**相关文件**：`backend/app/core/security.py`、`backend/app/services/auth_service.py`、`backend/app/api/v1/auth.py`

#### 认证流程

1. 用户通过 `/api/v1/auth/register` 注册，密码使用 bcrypt 加盐哈希存储
2. 通过 `/api/v1/auth/login` 登录，验证成功后签发 JWT Token 对（Access + Refresh）
3. Access Token 有效期 30 分钟，Refresh Token 有效期 7 天
4. 请求 Header 中携带 `Authorization: Bearer <access_token>`

#### 四种角色 (RBAC)

| 角色 | 说明 | 权限 |
|------|------|------|
| `admin` | 系统管理员 | 全部权限，包括用户管理、文档审核、评测 |
| `reviewer` | 审核员 | 文档审核、文档管理 |
| `operator` | 运营人员 | 文档管理、仪表盘查看 |
| `user` | 普通用户 | 问答、反馈提交 |

角色通过 `require_role()` 依赖注入装饰器实现接口级权限控制。

---

### 2. 知识管理

**相关文件**：`backend/app/services/document_service.py`、`backend/app/services/document_ingest_service.py`、`backend/app/api/v1/documents.py`

#### 文档生命周期

```
上传 → PENDING → (审核通过) → PROCESSING → (入库完成) → PUBLISHED
                → (审核拒绝) → REJECTED
                → (入库失败) → FAILED
```

#### 文档状态

| 状态 | 说明 |
|------|------|
| `pending` | 已上传，待审核 |
| `processing` | 审核通过，正在入库处理（分块/向量化/索引） |
| `published` | 入库完成，可检索 |
| `rejected` | 审核拒绝 |
| `failed` | 入库处理失败 |

#### 权威度评分 (authority_score)

| 分数 | 文档类型 |
|------|---------|
| 1.0 | 药典 |
| 0.9 | 教材 |
| 0.85 | 临床指南 |
| 0.7 | 药品说明书 |
| 0.5 | FAQ / 常见问答 |

---

### 3. RAG 核心流程

完整的 RAG Pipeline 由 `chat_service.py` 编排，流程如下：

```
用户提问
   │
   ▼
┌─────────────────────────┐
│ 1. 查询改写               │  → query_rewrite_service.py
│    - 规则归一化            │     _normalize_query()
│    - 实体抽取              │     extract_entities()
│    - LLM 改写 (可选)       │     _llm_rewrite()
└─────────┬───────────────┘
          ▼
┌─────────────────────────┐
│ 2. 三路并行检索            │  → retrieval_service.py
│    ├─ ES BM25 (稀疏)     │     _sparse_retrieve()
│    ├─ FAISS (稠密向量)    │     _dense_retrieve()
│    └─ Neo4j (图谱扩展)    │     _graph_retrieve()
└─────────┬───────────────┘
          ▼
┌─────────────────────────┐
│ 3. RRF 融合               │  → retrieval_service.py
│    score = Σ 1/(K+rank)  │     _fuse_results()
└─────────┬───────────────┘
          ▼
┌─────────────────────────┐
│ 4. 重排序                  │  → rerank_service.py
│    DashScope gte-rerank   │     rerank()
└─────────┬───────────────┘
          ▼
┌─────────────────────────┐
│ 5. Prompt 构建             │  → prompt_service.py
│    上下文 + 历史 + 引用    │     build_prompt()
└─────────┬───────────────┘
          ▼
┌─────────────────────────┐
│ 6. LLM 流式生成           │  → answer_service.py
│    qwen-max (SSE)        │     stream_answer()
└─────────┬───────────────┘
          ▼
┌─────────────────────────┐
│ 7. 引用提取               │  → citation_service.py
│    从答案中抽取引用片段    │     extract_citations()
└─────────────────────────┘
```

#### 各步骤详解

**Step 1: 查询改写** (`backend/app/services/query_rewrite_service.py`)
- 规则归一化：去除口语化表达，统一中医术语
- 实体抽取：使用正则和别名字典识别症状、方剂、中药、证候
- LLM 改写（当 `QUERY_REWRITE_ENABLED=true`）：调用 `qwen-plus` 生成 2-3 个改写变体
- 意图识别：判断查询属于 `symptom_diagnosis` / `formula_or_herb_knowledge` / `knowledge_lookup` / `general_consultation`

**Step 2: 三路并行检索** (`backend/app/services/retrieval_service.py`)
- **稀疏检索 (ES BM25)**：对改写后的多个查询分别搜索 ES，按 BM25 评分去重
- **稠密检索 (FAISS)**：将归一化查询向量化后在 FAISS 索引中搜索近邻
- **图谱检索 (Neo4j)**：根据抽取的实体名称在图谱中扩展关联实体
- 三路使用 `asyncio.TaskGroup` 并行执行，每路均有独立的超时和降级逻辑

**Step 3: RRF 融合** (`backend/app/services/retrieval_service.py` → `_fuse_results`)
- Reciprocal Rank Fusion: `score(d) = Σ 1/(K + rank_i)`，K 默认 60
- 将三路结果按融合分数排序，取 Top-K

**Step 4: 重排序** (`backend/app/services/rerank_service.py`)
- 调用 DashScope `gte-rerank` 模型对候选文档重新打分
- 当 `RERANKER_ENABLED=false` 时跳过此步

**Step 5: Prompt 构建** (`backend/app/services/prompt_service.py`)
- 组装系统提示词 + 检索上下文 + 多轮对话历史
- 注入引用格式要求，指导 LLM 在答案中标注来源

**Step 6: LLM 流式生成** (`backend/app/services/answer_service.py`)
- 调用 `qwen-max` 进行流式生成（SSE）
- 实时推送 token 到前端

**Step 7: 引用提取** (`backend/app/services/citation_service.py`)
- 从 LLM 生成的答案文本中提取引用标记
- 关联到检索命中的原文 chunk

---

### 4. 知识图谱

**相关文件**：`backend/app/services/graph_build_service.py`、`backend/app/services/graph_query_service.py`、`backend/app/api/v1/knowledge_graph.py`

#### 实体类型

| 类型 | 说明 | 示例 |
|------|------|------|
| `Symptom` | 症状 | 失眠、头痛、咳嗽、口苦 |
| `Syndrome` | 证候 | 肝火扰心、脾虚湿困、气血两虚 |
| `Formula` | 方剂 | 桂枝汤、小柴胡汤、归脾汤 |
| `Herb` | 中药 | 当归、黄芪、柴胡、甘草 |
| `Effect` | 功效 | 清热解毒、活血化瘀 |
| `Contraindication` | 禁忌 | 孕妇忌用 |
| `TongueSign` | 舌象 | 舌红苔黄 |
| `PulseSign` | 脉象 | 脉弦数 |

#### 关系类型

- 证候 → 包含 → 症状
- 方剂 → 治疗 → 证候
- 方剂 → 组成 → 中药
- 中药 → 功效 → 效用
- 症状 → 常见于 → 证候

#### 图谱构建流程

1. 文档入库时，`graph_build_service.py` 从文本 chunk 中抽取实体
2. 优先使用正则模式匹配（覆盖常见中医术语）
3. 可选调用 LLM 进行更精确的实体和关系抽取
4. 抽取的实体和关系写入 Neo4j 图数据库
5. 同时在 MySQL 的 `graph_entities` 表中维护实体映射

---

### 5. 反馈系统

**相关文件**：`backend/app/services/feedback_service.py`、`backend/app/services/badcase_service.py`、`backend/app/api/v1/feedback.py`

#### 反馈类型

| 类型 | 说明 |
|------|------|
| `thumbs_up` | 点赞（回答有帮助） |
| `thumbs_down` | 点踩（回答无帮助） |
| `correction` | 纠错（用户提供正确信息） |
| `badcase` | Bad Case（系统性错误报告） |

#### Bad Case 管理

- `badcase_service.py` 自动对 Bad Case 进行分类
- 分类结果写入反馈的 `metadata_json` 字段
- 管理员可在后台查看反馈统计和 Bad Case 分布

---

### 6. 评估框架

**相关文件**：`backend/app/services/evaluation_service.py`、`backend/app/api/v1/evaluation.py`

#### 评测类型

| 类型 | 说明 |
|------|------|
| `retrieval` | 检索质量评测 |
| `generation` | 生成质量评测 |
| `rewrite` | 查询改写评测 |
| `full` | 端到端完整评测 |

#### 评测指标

- **Recall@K**：Top-K 结果中包含正确文档的比例
- **MRR (Mean Reciprocal Rank)**：正确结果排名的倒数均值
- **NDCG (Normalized Discounted Cumulative Gain)**：考虑排名位置的累积增益

#### 评测数据集格式

评测数据存储在 `data/eval/` 目录，格式为 JSONL：

```jsonl
{"query": "失眠口苦怎么辨证？", "expected_doc_ids": ["doc-001", "doc-002"], "expected_answer": "..."}
```

#### 评测对比

支持两个评测任务的结果对比（`/api/v1/evaluation/compare`），用于 A/B 测试和回归检测。

---

### 7. 后台任务

**相关文件**：`backend/app/tasks/__init__.py`、`backend/app/tasks/ingest_tasks.py`、`backend/app/tasks/celery_config.py`

#### Celery 配置

- **Broker/Backend**：Redis
- **序列化**：JSON
- **时区**：Asia/Shanghai
- **确认模式**：`task_acks_late=True`（处理完再确认，防丢失）
- **预取**：`worker_prefetch_multiplier=1`（逐条取任务，防内存溢出）

#### 文档入库流水线 (`ingest_document`)

```
1. 更新状态 → PROCESSING
2. 解析文档文本（支持 .txt/.md，自动检测编码）
3. 文本分块（chunking_service）
4. 分块持久化到 MySQL（chunks 表）
5. 批量生成 Embedding 向量
6. 批量索引到 Elasticsearch
7. 批量写入 FAISS 向量索引
8. 从文本中抽取实体和关系，写入 Neo4j
9. 更新状态 → PUBLISHED
```

- 支持自动重试（最多 3 次，间隔 30 秒）
- 支持批量入库任务 (`batch_ingest`)：接收文件路径列表，逐一派发入库任务

---

## API 接口总览

所有接口均以 `/api/v1` 为前缀。

### 认证模块 (`/auth`)

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | `/auth/register` | 用户注册 | 无 |
| POST | `/auth/login` | 用户登录 | 无 |
| POST | `/auth/refresh` | 刷新 Token | 无 |
| POST | `/auth/logout` | 退出登录 | 无 |
| GET | `/auth/me` | 获取当前用户信息 | 需登录 |

### 用户模块 (`/users`)

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET | `/users/me` | 获取个人资料 | 需登录 |

### 对话模块 (`/chats`)

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | `/chats` | 创建新会话 | 需登录 |
| GET | `/chats` | 获取会话列表 | 需登录 |
| GET | `/chats/{session_id}/messages` | 获取会话消息列表 | 需登录 |
| POST | `/chats/{session_id}/stream` | 流式问答（SSE） | 需登录 |

### RAG 预览模块 (`/rag`)

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | `/rag/rewrite-preview` | 查询改写预览 | 无 |
| POST | `/rag/retrieve-preview` | 检索结果预览 | 无 |

### 文档管理模块 (`/documents`)

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET | `/documents` | 文档列表（支持状态筛选） | admin/reviewer/operator |
| GET | `/documents/{doc_id}` | 文档详情 | admin/reviewer/operator |
| POST | `/documents/upload` | 上传文档 | admin/reviewer/operator |

### 管理后台模块 (`/admin`)

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET | `/admin/users` | 用户列表 | admin |
| PUT | `/admin/users/{user_id}/role` | 修改用户角色 | admin |
| POST | `/admin/documents/{doc_id}/review` | 审核文档（通过/拒绝） | admin/reviewer |
| GET | `/admin/dashboard/stats` | 仪表盘统计数据 | admin/reviewer/operator |

### 反馈模块 (`/feedback`)

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | `/feedback` | 提交反馈 | 需登录 |
| GET | `/feedback` | 反馈列表 | 需登录 |
| GET | `/feedback/{feedback_id}` | 反馈详情 | 需登录 |
| GET | `/feedback/stats` | 反馈统计 | admin |

### 评测模块 (`/evaluation`)

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | `/evaluation/run` | 触发评测任务 | admin |
| GET | `/evaluation/tasks` | 评测任务列表 | 需登录 |
| GET | `/evaluation/tasks/{task_id}` | 评测任务详情 | 需登录 |
| GET | `/evaluation/compare` | 对比两次评测结果 | 需登录 |

### 知识图谱模块 (`/graph`)

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET | `/graph/entities` | 搜索实体 | 需登录 |
| GET | `/graph/entities/{name}` | 实体详情（含邻居） | 需登录 |
| GET | `/graph/paths` | 实体间路径查询 | 需登录 |
| GET | `/graph/visualization` | 图谱可视化数据 | 需登录 |
| POST | `/graph/entities` | 创建/更新实体 | admin |
| POST | `/graph/relationships` | 创建关系 | admin |

### 健康检查

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET | `/health` | 健康检查 | 无 |

---

## 数据模型

### 模型关系图

```
User ──1:N──> ChatSession ──1:N──> Message
 │                                    │
 │                                    └──1:1──> Feedback
 │
 ├──N:M──> Role (通过 UserRole 关联表)
 │
 └──1:N──> Document ──1:N──> Chunk
                │
                └──refs──> EvalTask (triggered_by)

独立日志表:
  AnswerLog (trace_id, message_id)
  RetrievalLog (trace_id, message_id)
  RerankLog (trace_id, message_id)

图谱映射:
  GraphEntity (entity_id, name, entity_type, neo4j_node_id)
```

### 模型详情

#### User (`users`)

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Integer (PK) | 自增主键 |
| `username` | String(64) | 用户名（唯一） |
| `email` | String(128) | 邮箱（唯一） |
| `password_hash` | String(256) | bcrypt 密码哈希 |
| `status` | Enum(active/disabled) | 账号状态 |
| `created_at` | DateTime | 创建时间 |
| `updated_at` | DateTime | 更新时间 |

#### Role (`roles`) & UserRole (`user_roles`)

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Integer (PK) | 角色 ID |
| `name` | Enum(admin/reviewer/operator/user) | 角色名 |
| `description` | String(256) | 角色描述 |

UserRole 为多对多关联表：`user_id` + `role_id` 联合主键。

#### Document (`documents`)

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Integer (PK) | 自增主键 |
| `doc_id` | String(36) | UUID，唯一文档标识 |
| `title` | String(512) | 文档标题 |
| `source` | String(256) | 来源（教材名/药典等） |
| `file_path` | String(512) | 文件路径（MinIO） |
| `version` | Integer | 版本号 |
| `status` | Enum | 文档状态 |
| `authority_score` | Float | 权威度评分 (0-1) |
| `uploaded_by` | Integer (FK) | 上传用户 ID |
| `published_at` | DateTime | 发布时间 |

#### Chunk (`chunks`)

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Integer (PK) | 自增主键 |
| `chunk_id` | String(36) | UUID，唯一分块标识 |
| `doc_id` | String(36) (FK) | 所属文档 ID |
| `chunk_index` | Integer | 在文档中的顺序 |
| `chunk_text` | Text | 分块文本内容 |
| `token_count` | Integer | Token 数 |
| `metadata_json` | JSON | 章节、标题等元数据 |
| `embedding_id` | String(64) | FAISS 向量 ID |

#### ChatSession (`sessions`)

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Integer (PK) | 自增主键 |
| `session_id` | String(36) | UUID |
| `user_id` | Integer (FK) | 所属用户 |
| `title` | String(256) | 会话标题 |
| `summary` | Text | 多轮对话摘要 |

#### Message (`messages`)

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Integer (PK) | 自增主键 |
| `message_id` | String(36) | UUID |
| `session_id` | String(36) (FK) | 所属会话 |
| `role` | Enum(user/assistant/system) | 消息角色 |
| `content` | Text | 消息内容 |
| `rewritten_query` | Text | 改写后的查询 |
| `citations` | JSON | 引用信息 |
| `latency_ms` | Integer | 端到端延迟 |

#### Feedback (`feedbacks`)

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Integer (PK) | 自增主键 |
| `message_id` | String(36) | 关联消息 ID |
| `user_id` | Integer (FK) | 反馈用户 |
| `feedback_type` | Enum | 反馈类型 |
| `content` | Text | 反馈内容 |
| `metadata_json` | JSON | 扩展信息（如 badcase 分类） |

#### EvalTask (`eval_tasks`)

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Integer (PK) | 自增主键 |
| `task_id` | String(36) | UUID |
| `task_type` | String(64) | 评测类型 |
| `status` | Enum | 状态 |
| `config_json` | JSON | 评测配置 |
| `result_json` | JSON | 评测结果 |
| `triggered_by` | Integer (FK) | 触发用户 |

#### GraphEntity (`graph_entities`)

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Integer (PK) | 自增主键 |
| `entity_id` | String(36) | UUID |
| `name` | String(256) | 实体名称 |
| `entity_type` | String(64) | 实体类型 |
| `aliases` | JSON | 别名列表 |
| `properties` | JSON | 属性（性味归经、关系等） |
| `neo4j_node_id` | String(64) | Neo4j 节点 ID |

#### AnswerLog (`answer_logs`)

| 字段 | 类型 | 说明 |
|------|------|------|
| `trace_id` | String(64) | 链路追踪 ID |
| `message_id` | String(36) | 关联消息 ID |
| `answer_text` | Text | 答案文本 |
| `cited_chunks` | JSON | 引用的 chunk 列表 |
| `input_tokens` | Integer | 输入 token 数 |
| `output_tokens` | Integer | 输出 token 数 |
| `latency_ms` | Integer | 延迟 |
| `model_name` | String(64) | 使用的模型 |

#### RetrievalLog (`retrieval_logs`)

| 字段 | 类型 | 说明 |
|------|------|------|
| `trace_id` | String(64) | 链路追踪 ID |
| `query` | Text | 原始查询 |
| `rewritten_query` | Text | 改写后的查询 |
| `sparse_hits` | JSON | BM25 命中结果 |
| `dense_hits` | JSON | 向量命中结果 |
| `graph_hits` | JSON | 图谱命中结果 |
| `merged_hits` | JSON | RRF 融合后结果 |

#### RerankLog (`rerank_logs`)

| 字段 | 类型 | 说明 |
|------|------|------|
| `trace_id` | String(64) | 链路追踪 ID |
| `input_chunks` | JSON | 重排前 |
| `output_chunks` | JSON | 重排后 |
| `rerank_scores` | JSON | 分数明细 |

---

## 配置管理

### 配置加载机制

配置由 `backend/app/core/config.py` 中的 `Settings` 类管理，基于 `pydantic-settings`：

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
    )
```

**加载优先级**（从高到低）：
1. 系统环境变量
2. `.env` 文件
3. 代码中的默认值

### 计算属性

| 属性 | 说明 |
|------|------|
| `MYSQL_DSN` | 自动拼接 MySQL 异步连接字符串 |
| `MYSQL_SYNC_DSN` | 自动拼接 MySQL 同步连接字符串 |
| `SQLALCHEMY_DATABASE_URI` | 优先使用 `DATABASE_URL`，否则 fallback 到 SQLite |

### 特性开关

| 开关 | 默认 | 影响 |
|------|------|------|
| `QUERY_REWRITE_ENABLED` | `true` | 关闭后仅使用规则改写，不调用 LLM |
| `GRAPH_RECALL_ENABLED` | `true` | 关闭后跳过图谱检索通道 |
| `RERANKER_ENABLED` | `true` | 关闭后跳过重排步骤 |
| `ENABLE_DEMO_DATA` | `true` | 关闭后不自动灌入演示数据 |

---

## 部署指南

### Docker Compose 生产部署

1. **准备服务器**：推荐 4C8G+ 配置（Elasticsearch 较耗内存）

2. **配置 .env**：
```bash
# 生产环境关键配置
DEBUG=false
JWT_SECRET_KEY=<随机生成的强密钥>
MYSQL_PASSWORD=<强密码>
NEO4J_PASSWORD=<强密码>
DASHSCOPE_API_KEY=sk-<your-key>

# Docker 内部服务地址
MYSQL_HOST=mysql
REDIS_URL=redis://redis:6379/0
ES_HOSTS=["http://elasticsearch:9200"]
NEO4J_URI=bolt://neo4j:7687
MINIO_ENDPOINT=minio:9000
```

3. **启动**：
```bash
docker-compose up -d
```

### Nginx 配置

`deploy/nginx.conf` 已配置：
- Gzip 压缩
- 反向代理（API / 用户端 / 管理端）
- SSE 支持（`proxy_buffering off`，读写超时 300s）
- WebSocket 支持
- 静态资源缓存（30 天）
- 文件上传限制 100MB

### Gunicorn 配置

`deploy/gunicorn_conf.py`：

| 参数 | 值 | 说明 |
|------|-----|------|
| `bind` | `0.0.0.0:8000` | 监听地址 |
| `workers` | `4` | Worker 进程数 |
| `worker_class` | `uvicorn.workers.UvicornWorker` | 使用 Uvicorn Worker |
| `timeout` | `120` | 请求超时（秒） |
| `keepalive` | `5` | Keep-Alive 超时 |

### 扩容建议

- **后端**：增加 Gunicorn `workers` 数量（建议 `2 × CPU核心数 + 1`）
- **Celery Worker**：可通过 `docker-compose scale celery-worker=N` 水平扩展
- **Elasticsearch**：生产环境建议独立部署，分配 2GB+ 堆内存
- **数据库**：MySQL 可配置主从读写分离
- **FAISS**：大规模数据建议使用 IVF 索引或迁移至 Milvus

---

## 扩展指南

### 添加新的检索源

1. 在 `backend/app/integrations/` 下创建新的客户端，如 `milvus_client.py`
2. 实现 `init()` / `close()` / `search()` / `available` 等标准接口
3. 在 `backend/app/services/retrieval_service.py` 的 `RetrievalService.retrieve()` 中添加新的检索通道：

```python
# 在 TaskGroup 中添加新任务
tasks["milvus"] = tg.create_task(
    self._milvus_retrieve(queries, settings.MILVUS_TOP_K)
)

# 将结果加入 RRF 融合
milvus_docs = tasks.get("milvus", _EmptyResult()).result()
fused_docs = await self._fuse_results(sparse, dense, graph, milvus_docs, fusion_k)
```

4. 在 `backend/app/core/config.py` 中添加对应配置项
5. 在 `.env.example` 中添加配置模板

### 添加新的 API 接口

1. 在 `backend/app/api/v1/` 下创建新的路由文件，如 `statistics.py`：

```python
from fastapi import APIRouter
router = APIRouter()

@router.get("/overview")
async def get_overview():
    ...
```

2. 在 `backend/app/api/router.py` 中注册路由：

```python
from app.api.v1 import statistics
api_router.include_router(statistics.router, prefix="/statistics", tags=["统计"])
```

3. 在 `backend/app/schemas/` 下创建对应的请求/响应 Schema
4. 在 `backend/app/services/` 下创建对应的业务服务

### 添加新的评测指标

1. 在 `backend/app/services/evaluation_service.py` 中添加指标计算函数：

```python
def _calculate_custom_metric(predictions: list, ground_truth: list) -> float:
    # 自定义指标计算逻辑
    ...
```

2. 在 `_run_eval()` 方法中调用新指标
3. 将结果写入 `EvalTask.result_json`

### 集成不同的 LLM 提供商

1. 在 `backend/app/integrations/` 下创建新的 LLM 客户端，如 `openai_client.py`
2. 实现与 `llm_client.py` 相同的接口：
   - `generate(prompt, **kwargs) -> str`
   - `stream_generate(prompt, **kwargs) -> AsyncGenerator`
3. 在 `backend/app/core/config.py` 中添加新提供商的配置
4. 在 `backend/app/services/answer_service.py` 中根据配置选择 LLM 客户端：

```python
# config.py
LLM_PROVIDER: str = "dashscope"  # 或 "openai"

# answer_service.py
if settings.LLM_PROVIDER == "openai":
    from app.integrations.openai_client import openai_client as llm
else:
    from app.integrations.llm_client import llm_client as llm
```

5. 同理，Embedding 客户端也可按此模式扩展
