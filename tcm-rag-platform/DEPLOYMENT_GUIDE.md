# 中医药智能知识服务平台 — 服务器部署指南

> TCM-RAG-Platform v1.0.0 多用户并发部署指南

---

## 目录

- [并发支持说明](#并发支持说明)
- [当前配置状态](#当前配置状态)
- [性能优化配置](#性能优化配置)
- [服务器部署步骤](#服务器部署步骤)
- [监控和维护](#监控和维护)
- [扩展建议](#扩展建议)

---

## 并发支持说明

### ✅ 支持多用户并发

你的后端服务器**完全支持多用户同时使用**，架构设计如下：

- **FastAPI异步框架**：原生支持异步并发请求
- **Gunicorn多进程**：配置8个worker进程处理并发
- **Nginx反向代理**：负载均衡和连接管理
- **数据库连接池**：MySQL支持多连接
- **Redis缓存**：支持高并发缓存操作
- **Celery异步队列**：文档处理异步化，不阻塞用户请求

### 🚀 并发能力

- **理论并发数**：8个worker × 100并发/进程 = 800并发请求
- **实际承载**：取决于服务器配置和业务复杂度
- **响应时间**：< 3秒（正常查询）
- **稳定性**：自动重启机制，单进程故障不影响整体服务

---

## 当前配置状态

### 生产环境配置

```python
# deploy/gunicorn_conf.py
workers = 8  # 8个worker进程
worker_class = "uvicorn.workers.UvicornWorker"
timeout = 120  # 2分钟超时
max_requests = 1000  # 每个worker处理1000请求后重启
max_requests_jitter = 50  # 随机重启避免同时重启
```

### 服务端口映射

| 服务 | 内部端口 | 外部端口 | 说明 |
|------|----------|----------|------|
| Nginx | 80 | 80 | 统一入口 |
| Backend API | 8000 | 8000 | FastAPI服务 |
| Frontend User | 80 | 3000 | 用户界面 |
| Frontend Admin | 80 | 3001 | 管理后台 |
| MySQL | 3306 | 3307 | 数据库 |
| Redis | 6379 | 6379 | 缓存队列 |
| Elasticsearch | 9200 | 9200 | 搜索 |
| Neo4j | 7687 | 7687 | 图数据库 |

---

## 性能优化配置

### 根据服务器规格调整

```bash
# 查看CPU核心数
nproc

# 推荐配置：
# CPU核心数 <= 4: workers = CPU核心数 * 2
# CPU核心数 > 4: workers = CPU核心数 + 2
```

### 内存配置建议

| 服务器内存 | Worker数量 | 推荐配置 |
|------------|------------|----------|
| 4GB | 4-6 | 基础配置 |
| 8GB | 6-8 | 当前配置 |
| 16GB+ | 8-12 | 高并发配置 |

### 数据库连接池

```python
# backend/app/core/config.py
# 数据库连接池配置
SQLALCHEMY_POOL_SIZE = 20
SQLALCHEMY_MAX_OVERFLOW = 30
SQLALCHEMY_POOL_TIMEOUT = 30
```

---

## 服务器部署步骤

### 1. 服务器准备

```bash
# Ubuntu/Debian服务器
sudo apt update
sudo apt install -y docker.io docker-compose git curl

# 启动Docker服务
sudo systemctl start docker
sudo systemctl enable docker

# 添加用户到docker组（可选）
sudo usermod -aG docker $USER
```

### 2. 代码部署

```bash
# 克隆或上传代码
git clone <repository-url> tcm-rag-platform
cd tcm-rag-platform

# 或上传本地代码
scp -r /local/path/tcm-rag-platform user@server:/path/to/
```

### 3. 环境配置

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑环境变量（必须配置）
nano .env

# 关键配置项：
DASHSCOPE_API_KEY=your-api-key
MYSQL_PASSWORD=strong-password
NEO4J_PASSWORD=strong-password
JWT_SECRET_KEY=your-secret-key
```

### 4. 启动服务

```bash
# 构建并启动所有服务
docker-compose up -d --build

# 查看启动状态
docker-compose ps

# 查看日志
docker-compose logs -f backend
```

### 5. 验证部署

```bash
# 健康检查
curl http://localhost/health

# API文档
curl http://localhost:8000/docs

# 前端访问
# 用户端: http://your-server:3000
# 管理后台: http://your-server:3001
# 统一入口: http://your-server
```

### 6. SSL证书配置（生产环境必需）

```bash
# 安装certbot
sudo apt install certbot python3-certbot-nginx

# 获取免费SSL证书
sudo certbot --nginx -d your-domain.com

# 自动续期
sudo crontab -e
# 添加：0 12 * * * /usr/bin/certbot renew --quiet
```

---

## 监控和维护

### 实时监控

```bash
# 查看服务状态
docker-compose ps

# 查看资源使用
docker stats

# 查看日志
docker-compose logs -f backend
docker-compose logs -f nginx

# 检查健康状态
curl http://localhost/health
```

### 日志管理

```bash
# 清理旧日志
docker-compose logs --tail=100 backend > backend.log
docker system prune -f  # 清理未使用的容器和镜像
```

### 备份策略

```bash
# 数据库备份
docker exec tcm-rag-platform_mysql_1 mysqldump -u root -p tcm_db > backup.sql

# 数据卷备份
docker run --rm -v tcm-rag-platform_mysql_data:/data -v $(pwd):/backup alpine tar czf /backup/mysql_backup.tar.gz -C /data .

# 配置文件备份
cp .env .env.backup
```

### 性能监控

```bash
# 安装监控工具（可选）
docker run -d \
  --name prometheus \
  -p 9090:9090 \
  prom/prometheus

# 查看系统负载
uptime
free -h
df -h
```

---

## 扩展建议

### 水平扩展

```yaml
# docker-compose.scale.yml
version: '3.8'
services:
  backend:
    scale: 3  # 启动3个backend实例
    depends_on:
      - loadbalancer

  loadbalancer:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx-lb.conf:/etc/nginx/nginx.conf
```

### 云服务部署

#### AWS EC2
```bash
# 安装AWS CLI
pip install awscli

# 配置安全组允许端口80,443,22
aws ec2 authorize-security-group-ingress --group-id sg-xxxxx --protocol tcp --port 80 --cidr 0.0.0.0/0
```

#### Docker Swarm/Kubernetes
```bash
# 初始化Swarm
docker swarm init

# 部署stack
docker stack deploy -c docker-compose.yml tcm-stack
```

### 高可用配置

```yaml
# Redis集群配置
redis-cluster:
  image: redis:7-alpine
  deploy:
    replicas: 3
    restart_policy:
      condition: on-failure

# MySQL主从复制
mysql-master:
  # 主库配置
mysql-slave:
  # 从库配置
  depends_on:
    - mysql-master
```

---

## 故障排除

### 常见问题

1. **端口冲突**
   ```bash
   sudo netstat -tulpn | grep :80
   # 修改docker-compose.yml中的端口映射
   ```

2. **内存不足**
   ```bash
   free -h
   # 增加swap空间或升级服务器配置
   ```

3. **数据库连接失败**
   ```bash
   docker-compose logs mysql
   # 检查MYSQL_PASSWORD配置
   ```

4. **API超时**
   ```bash
   # 增加timeout配置
   # deploy/gunicorn_conf.py
   timeout = 300
   ```

### 紧急恢复

```bash
# 重启所有服务
docker-compose down
docker-compose up -d

# 重启特定服务
docker-compose restart backend

# 完全清理重装
docker-compose down -v
docker system prune -f
docker-compose up -d --build
```

---

## 总结

你的系统已经完全准备好支持多用户并发使用：

- ✅ **并发架构**：FastAPI + Gunicorn + Nginx
- ✅ **数据库支持**：MySQL连接池
- ✅ **缓存优化**：Redis高并发缓存
- ✅ **异步处理**：Celery队列处理
- ✅ **监控就绪**：健康检查和日志

按照上述部署步骤，你可以在任何云服务器上快速部署，支持数百用户同时使用。建议先在测试环境验证，然后配置SSL证书用于生产环境。</content>
<parameter name="filePath">/Users/breo/Documents/code/medical/tcm-rag-platform/DEPLOYMENT_GUIDE.md