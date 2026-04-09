# 中医药智能知识服务平台 — 运行文档

> TCM-RAG-Platform v1.0.0 运行部署与开发指南

---

## 目录

- [环境要求](#环境要求)
- [快速启动 (Docker Compose)](#快速启动-docker-compose)
- [环境配置 (.env)](#环境配置-env)
- [本地开发启动](#本地开发启动)
- [首次数据初始化](#首次数据初始化)
- [服务端口说明](#服务端口说明)
- [常见问题排查](#常见问题排查)

---

## 环境要求

| 依赖 | 最低版本 | 说明 |
|------|---------|------|
| Python | 3.11+ | 后端运行时 |
| Node.js | 18+ | 前端构建与开发 |
| Docker | 20.10+ | 容器化部署 |
| Docker Compose | 2.0+ (V2) | 多服务编排 |
| OS | macOS / Linux | 推荐 macOS 或 Ubuntu 22.04+ |

> **注意**：Windows 用户建议使用 WSL2 运行本项目。

---

## 快速启动 (Docker Compose)

### 1. 克隆项目

```bash
git clone <repository-url> tcm-rag-platform
cd tcm-rag-platform
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件，**至少**填入以下必填项：

```bash
# 必填：DashScope API Key（用于 LLM 问答和 Embedding）
DASHSCOPE_API_KEY=sk-your-dashscope-api-key

# 必填：MySQL 密码
MYSQL_PASSWORD=your_mysql_password

# 必填：Neo4j 密码
NEO4J_PASSWORD=your_neo4j_password

# 建议修改：JWT 密钥（生产环境务必更换）
JWT_SECRET_KEY=your-random-secret-key
```

### 3. 启动全部服务

```bash
docker-compose up -d
```

首次启动需要下载镜像和构建，耐心等待约 5-10 分钟。

### 4. 检查服务状态

```bash
docker-compose ps
docker-compose logs -f backend
```

### 5. 访问服务

- 用户端：http://localhost:3000
- 管理后台：http://localhost:3001
- API 文档：http://localhost:8000/docs
- 统一入口 (Nginx)：http://localhost

### Docker Compose 服务说明

| 服务名 | 镜像/构建 | 说明 |
|--------|----------|------|
| `backend` | `deploy/docker/backend.Dockerfile` | FastAPI 后端 API，由 Gunicorn + Uvicorn Worker 运行 |
| `celery-worker` | `deploy/docker/worker.Dockerfile` | Celery 异步任务工作进程，处理文档入库 |
| `mysql` | `mysql:8.0` | 主数据库，存储用户、文档、会话等结构化数据 |
| `redis` | `redis:7-alpine` | 缓存 + Celery 消息队列 Broker/Backend |
| `elasticsearch` | `elasticsearch:8.15.0` | BM25 稀疏检索引擎，存储文档分块索引 |
| `neo4j` | `neo4j:5-community` | 知识图谱数据库，存储中医实体与关系 |
| `minio` | `minio/minio:latest` | 对象存储，管理上传的原始文档文件 |
| `frontend-user` | `frontend-user/Dockerfile` | 用户端 React 应用 |
| `frontend-admin` | `frontend-admin/Dockerfile` | 管理后台 React 应用 |
| `nginx` | `nginx:alpine` | 反向代理，统一入口路由分发 |

---

## 环境配置 (.env)

所有配置通过 `.env` 文件或环境变量注入，配置类定义在 `backend/app/core/config.py`。

### 应用配置

| 变量名 | 默认值 | 必填 | 说明 |
|--------|--------|------|------|
| `APP_NAME` | `TCM-RAG-Platform` | 否 | 应用名称 |
| `DEBUG` | `false` | 否 | 调试模式，开启后日志级别为 DEBUG |
| `API_V1_PREFIX` | `/api/v1` | 否 | API v1 路由前缀 |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/tcm_rag.db` | 否 | 数据库连接 URL（设置此项将覆盖 MySQL 配置） |
| `ENABLE_DEMO_DATA` | `true` | 否 | 是否在首次启动时自动灌入演示数据 |

### MySQL 配置

| 变量名 | 默认值 | 必填 | 说明 |
|--------|--------|------|------|
| `MYSQL_HOST` | `localhost` | 是 | MySQL 主机地址（Docker 中为 `mysql`） |
| `MYSQL_PORT` | `3306` | 否 | MySQL 端口 |
| `MYSQL_USER` | `root` | 否 | MySQL 用户名 |
| `MYSQL_PASSWORD` | _(空)_ | **是** | MySQL 密码 |
| `MYSQL_DATABASE` | `tcm_rag` | 否 | 数据库名 |

### Redis 配置

| 变量名 | 默认值 | 必填 | 说明 |
|--------|--------|------|------|
| `REDIS_URL` | `redis://localhost:6379/0` | 否 | Redis 连接 URL（Docker 中改为 `redis://redis:6379/0`） |

### Elasticsearch 配置

| 变量名 | 默认值 | 必填 | 说明 |
|--------|--------|------|------|
| `ES_HOSTS` | `["http://localhost:9200"]` | 否 | ES 集群地址列表（JSON 数组格式） |
| `ES_INDEX_PREFIX` | `tcm` | 否 | 索引名前缀 |

### Neo4j 配置

| 变量名 | 默认值 | 必填 | 说明 |
|--------|--------|------|------|
| `NEO4J_URI` | `bolt://localhost:7687` | 否 | Neo4j Bolt 协议地址 |
| `NEO4J_USER` | `neo4j` | 否 | Neo4j 用户名 |
| `NEO4J_PASSWORD` | _(空)_ | **是** | Neo4j 密码 |

### MinIO 配置

| 变量名 | 默认值 | 必填 | 说明 |
|--------|--------|------|------|
| `MINIO_ENDPOINT` | `localhost:9000` | 否 | MinIO 端点地址 |
| `MINIO_ACCESS_KEY` | _(空)_ | 否 | MinIO Access Key |
| `MINIO_SECRET_KEY` | _(空)_ | 否 | MinIO Secret Key |
| `MINIO_BUCKET` | `tcm-documents` | 否 | 文档存储桶名称 |

### DashScope LLM 配置

| 变量名 | 默认值 | 必填 | 说明 |
|--------|--------|------|------|
| `DASHSCOPE_API_KEY` | _(空)_ | **是** | 阿里云 DashScope API Key |
| `LLM_MODEL` | `qwen-max` | 否 | 答案生成模型 |
| `LLM_REWRITE_MODEL` | `qwen-plus` | 否 | 查询改写模型 |
| `LLM_TIMEOUT` | `15` | 否 | LLM 请求超时（秒） |
| `EMBEDDING_MODEL` | `text-embedding-v3` | 否 | 向量化模型 |
| `EMBEDDING_DIM` | `1024` | 否 | 向量维度 |
| `RERANKER_MODEL` | `gte-rerank` | 否 | 重排序模型 |

> **获取 DashScope API Key**：
> 1. 访问 [阿里云百炼平台](https://dashscope.console.aliyun.com/)
> 2. 注册/登录阿里云账号
> 3. 在「API Key 管理」页面创建 Key
> 4. 将 Key 填入 `.env` 的 `DASHSCOPE_API_KEY` 字段

### 检索参数

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `SPARSE_TOP_K` | `20` | BM25 稀疏检索返回条数 |
| `DENSE_TOP_K` | `20` | FAISS 向量检索返回条数 |
| `GRAPH_TOP_K` | `15` | 图谱检索返回条数 |
| `FUSION_TOP_K` | `20` | RRF 融合后保留条数 |
| `RERANK_K` | `5` | 重排后最终返回条数 |
| `RRF_K` | `60` | RRF 融合算法常数（控制排名衰减） |
| `GRAPH_MAX_HOPS` | `2` | 图谱实体扩展最大跳数 |
| `RETRIEVAL_TIMEOUT` | `1.0` | 检索超时（秒） |

### 特性开关

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `QUERY_REWRITE_ENABLED` | `true` | 启用 LLM 查询改写 |
| `GRAPH_RECALL_ENABLED` | `true` | 启用知识图谱召回通道 |
| `RERANKER_ENABLED` | `true` | 启用重排序 |

### JWT 安全配置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `JWT_SECRET_KEY` | `change-me-in-production` | JWT 签名密钥 (**生产环境务必更换**) |
| `JWT_ALGORITHM` | `HS256` | JWT 算法 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access Token 有效期（分钟） |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh Token 有效期（天） |

### 多轮对话配置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `HISTORY_WINDOW_SIZE` | `5` | 多轮上下文窗口大小（消息条数） |
| `HISTORY_SUMMARY_INTERVAL` | `5` | 每隔多少轮生成一次摘要 |

### 限流配置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `RATE_LIMIT_USER` | `60` | 普通接口限流（次/分钟） |
| `RATE_LIMIT_QA` | `10` | QA 问答限流（次/分钟） |
| `RATE_LIMIT_ADMIN` | `120` | 管理接口限流（次/分钟） |

---

## 本地开发启动

### 前提条件

确保已启动基础设施服务（MySQL、Redis、Elasticsearch、Neo4j、MinIO），可以单独启动这些依赖：

```bash
docker-compose up -d mysql redis elasticsearch neo4j minio
```

### 后端启动

```bash
# 1. 创建虚拟环境
cd tcm-rag-platform
python3.11 -m venv .venv
source .venv/bin/activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env 填入实际配置

# 4. 启动后端 API（开发模式，热重载）
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

启动后访问 http://localhost:8000/docs 查看 Swagger 文档。

### Celery Worker 启动

```bash
# 在项目根目录，激活虚拟环境后执行
celery -A backend.app.tasks.celery_app worker --loglevel=info
```

> Worker 负责处理文档入库的异步任务（解析 → 分块 → 向量化 → 索引 → 图谱构建）。

### 前端用户端启动

```bash
cd frontend-user
npm install
npm run dev
```

默认运行在 http://localhost:5173。

### 前端管理端启动

```bash
cd frontend-admin
npm install
npm run dev
```

默认运行在 http://localhost:5174。

### 数据库初始化

后端首次启动时会自动执行以下初始化操作（由 `backend/app/services/bootstrap_service.py` 控制）：

1. **创建数据表**：SQLAlchemy 自动根据 ORM 模型创建所有表
2. **初始化角色**：自动创建 `admin`、`reviewer`、`operator`、`user` 四个角色
3. **种子图谱实体**：灌入基础中医实体（失眠、口苦、易怒、肝火扰心、气虚、脾虚）
4. **加载数据字典**：从 `data/dictionaries/` 加载症状同义词、中药别名、方剂别名

如使用 Docker Compose，MySQL 会自动执行 `deploy/mysql/init.sql` 创建数据库。

---

## 首次数据初始化

### 自动演示数据

当 `ENABLE_DEMO_DATA=true`（默认）时，Bootstrap 服务会在数据库为空时自动灌入 3 条演示文档：

- 「失眠口苦辨证参考」
- 「脾虚乏力调理要点」
- 「咽痛咳嗽知识卡片」

每条文档会自动分块并创建对应的 Chunk 记录。

### 批量导入中医古籍数据

项目配套的 `TCM-Ancient-Books-master/` 目录包含大量中医古籍文本。可通过 Celery 的 `batch_ingest` 任务批量导入：

```python
# 在 Python shell 或脚本中调用
from backend.app.tasks.ingest_tasks import batch_ingest

# 准备文件路径列表
import glob
file_paths = glob.glob("/path/to/TCM-Ancient-Books-master/**/*.txt", recursive=True)

# 派发批量入库任务
result = batch_ingest.delay(file_paths)
print(f"已派发 batch 任务: {result.id}")
```

每个文件会经过完整的入库流水线：
1. 解析文本 → 2. 智能分块 → 3. 存入数据库 → 4. 生成向量 → 5. ES 索引 → 6. FAISS 索引 → 7. 知识图谱构建 → 8. 状态更新为 PUBLISHED

### 数据字典文件

位于 `data/dictionaries/` 目录：

| 文件 | 说明 |
|------|------|
| `symptom_synonyms.json` | 症状同义词映射（如 失眠 → 睡不好、入睡困难） |
| `herb_aliases.json` | 中药别名映射 |
| `formula_aliases.json` | 方剂别名映射 |

格式为 JSON 对象，键为标准名，值为别名数组：

```json
{
  "失眠": ["睡不好", "入睡困难", "多梦", "睡眠差"],
  "口苦": ["口苦", "嘴苦"]
}
```

### 评测数据集

位于 `data/eval/` 目录：

| 文件 | 说明 |
|------|------|
| `retrieval_eval.jsonl` | 检索评测数据集 |
| `generation_eval.jsonl` | 生成评测数据集 |
| `regression_cases.jsonl` | 回归测试用例集 |

---

## 服务端口说明

| 服务 | 端口 | 说明 |
|------|------|------|
| **Nginx** (统一入口) | `80` | 反向代理，路由 `/api` → 后端, `/admin` → 管理端, `/` → 用户端 |
| **Backend API** | `8000` | FastAPI 后端 API |
| **Frontend-User** (容器) | `3000` | 用户端前端（容器映射端口） |
| **Frontend-Admin** (容器) | `3001` | 管理后台前端（容器映射端口） |
| **Frontend-User** (开发) | `5173` | Vite 开发服务器默认端口 |
| **Frontend-Admin** (开发) | `5174` | Vite 开发服务器默认端口 |
| **MySQL** | `3306` | 关系型数据库 |
| **Redis** | `6379` | 缓存 / Celery Broker |
| **Elasticsearch** | `9200` | 全文检索引擎 |
| **Neo4j Browser** | `7474` | Neo4j Web 管理界面 |
| **Neo4j Bolt** | `7687` | Neo4j Bolt 协议端口 |
| **MinIO API** | `9000` | 对象存储 API |
| **MinIO Console** | `9001` | MinIO Web 管理界面 |

---

## 常见问题排查

### 1. Redis 连接失败

**错误信息**：`Redis 不可用，继续以降级模式运行` 或 `Connection refused`

**解决方案**：
```bash
# 检查 Redis 是否运行
docker-compose ps redis
docker-compose logs redis

# 确认 .env 中 REDIS_URL 配置正确
# Docker 环境: redis://redis:6379/0
# 本地开发: redis://localhost:6379/0

# 手动测试连接
redis-cli -h localhost -p 6379 ping
```

> 注：Redis 不可用时后端会以**降级模式**运行（无缓存），但 Celery Worker 无法启动。

### 2. MySQL 连接问题

**错误信息**：`Access denied` 或 `Can't connect to MySQL server`

**解决方案**：
```bash
# 检查 MySQL 是否就绪
docker-compose ps mysql
docker-compose logs mysql

# 确认密码配置一致
# docker-compose.yml 中 MYSQL_ROOT_PASSWORD 与 .env 中 MYSQL_PASSWORD 必须匹配

# 测试连接
mysql -h 127.0.0.1 -P 3306 -u root -p
```

### 3. DashScope API Key 缺失

**错误信息**：LLM 调用返回认证错误，或查询改写/答案生成无响应

**解决方案**：
```bash
# 确认 .env 中已配置
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxx

# 验证 Key 有效性
curl -X POST https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation \
  -H "Authorization: Bearer sk-your-key" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen-plus","input":{"prompt":"你好"}}'
```

> 没有 DashScope API Key 时，查询改写会退化为规则匹配模式，答案生成将不可用。

### 4. Elasticsearch 无法启动（内存不足）

**错误信息**：ES 容器反复重启，日志中出现 `OutOfMemoryError`

**解决方案**：
```bash
# 检查 ES 日志
docker-compose logs elasticsearch

# docker-compose.yml 中 ES 内存默认为 512MB
# 如果机器内存不足，可降低：
# ES_JAVA_OPTS=-Xms256m -Xmx256m

# macOS 上确保 Docker Desktop 分配了足够内存（建议 ≥ 6GB）
# Docker Desktop → Settings → Resources → Memory

# Linux 上需要调整 vm.max_map_count
sudo sysctl -w vm.max_map_count=262144
echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf
```

### 5. Neo4j 认证问题

**错误信息**：`AuthError` 或 `Unauthorized`

**解决方案**：
```bash
# 确认密码配置
# docker-compose.yml: NEO4J_AUTH: neo4j/${NEO4J_PASSWORD:-tcm_neo4j_123}
# .env: NEO4J_PASSWORD=your_password

# 首次启动后如果修改密码，需要清除 Neo4j 数据卷：
docker-compose down
docker volume rm tcm-rag-platform_neo4j_data
docker-compose up -d neo4j

# 通过浏览器访问 http://localhost:7474 验证连接
```

### 6. FAISS 索引未找到

**错误信息**：`FAISS 初始化失败` 或检索时向量通道为空

**解决方案**：
```bash
# FAISS 索引文件存储在 data/ 目录
# 首次启动时索引为空属正常，需要先导入文档

# 确认 data/ 目录已挂载（docker-compose.yml 中已配置）
# volumes:
#   - ./data:/app/data

# 检查索引文件是否存在
ls -la data/

# 如果需要重建索引，重新执行文档入库任务即可
```

> FAISS 索引不可用时，系统会退化到 ES BM25 + 图谱检索，仍可正常工作。

### 7. Celery Worker 不处理任务

**错误信息**：上传文档后状态一直为 `pending`

**解决方案**：
```bash
# 检查 Worker 是否运行
docker-compose ps celery-worker
docker-compose logs -f celery-worker

# 确认 Redis 连接正常（Redis 是 Celery 的 Broker）
# Worker 中的 REDIS_URL 须与后端一致

# 本地开发时手动启动 Worker：
celery -A backend.app.tasks.celery_app worker --loglevel=info

# 检查任务队列
celery -A backend.app.tasks.celery_app inspect active
celery -A backend.app.tasks.celery_app inspect reserved
```

### 8. 前端构建失败

```bash
# 确认 Node.js 版本
node -v  # 需要 >= 18

# 清除缓存重新安装
cd frontend-user  # 或 frontend-admin
rm -rf node_modules package-lock.json
npm install
npm run dev
```

---

## 停止与清理

```bash
# 停止所有服务
docker-compose down

# 停止并删除数据卷（⚠️ 会清除所有数据）
docker-compose down -v

# 重新构建镜像
docker-compose build --no-cache
docker-compose up -d
```
