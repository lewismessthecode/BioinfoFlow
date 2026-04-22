# Operational Runbook

**Last Updated:** 2026-02-04
**Audience:** DevOps, SRE, Platform Engineers

This runbook provides operational procedures for deploying, monitoring, and maintaining Bioinfoflow.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Deployment](#deployment)
- [Monitoring](#monitoring)
- [Common Issues](#common-issues)
- [Rollback Procedures](#rollback-procedures)
- [Maintenance](#maintenance)

---

## Architecture Overview

### System Components

```
┌─────────────┐
│   Browser   │
└──────┬──────┘
       │ HTTPS
       ▼
┌─────────────┐     ┌──────────────┐
│  Next.js    │────▶│   FastAPI    │
│  Frontend   │ API │   Backend    │
│  (Port 3000)│◀────│  (Port 8000) │
└─────────────┘     └──────┬───────┘
                           │
                    ┌──────┴───────┬─────────────┬──────────────┐
                    ▼              ▼             ▼              ▼
              ┌──────────┐   ┌─────────┐  ┌──────────┐   ┌──────────┐
              │  SQLite  │   │ Docker  │  │Nextflow  │   │ LangGraph│
              │    DB    │   │ Engine  │  │/MiniWDL  │   │  Agent   │
              └──────────┘   └─────────┘  └──────────┘   └──────────┘
```

### Technology Stack

**Frontend:**
- Next.js 16 (React 19)
- Radix UI components
- Better Auth for authentication
- React Flow for DAG visualization

**Backend:**
- FastAPI (Python 3.13)
- SQLAlchemy async + aiosqlite
- LangGraph agent runtime
- Docker SDK for container management

**Infrastructure:**
- SQLite database (async)
- Docker for workflow execution
- Nextflow/MiniWDL workflow engines
- SSE (Server-Sent Events) for real-time updates

---

## Deployment

### Prerequisites

**System Requirements:**
- Python 3.13+
- Node.js 18+
- Docker Engine 20.10+
- 2GB+ RAM, 10GB+ disk space
- Linux/macOS (Windows with WSL2)

**External Services:**
- LLM API keys (Anthropic, OpenAI, or Gemini)
- Docker daemon running
- (Optional) Nextflow and/or MiniWDL installed

### Environment Configuration

1. **Create environment file:**

```bash
cd backend
cp .env.example .env
```

2. **Configure critical variables:**

```bash
# Application
APP_NAME=Bioinfoflow
DEBUG=false                                # Set to false in production
WORKFLOW_REGISTRY_ROOT=/data/workflows     # Persistent storage path

# Database
DATABASE_URL=sqlite+aiosqlite:///./bioinfoflow.db  # Use absolute path in production

# LLM Provider (choose one)
ANTHROPIC_API_KEY=sk-ant-xxx              # Anthropic (recommended)
GEMINI_API_KEY=xxx                         # Or Gemini
OPENAI_API_KEY=xxx                         # Or OpenAI

# Docker
DOCKER_SOCKET=unix:///var/run/docker.sock  # Verify Docker is accessible

# CORS (update for production domain)
CORS_ORIGINS=["https://your-domain.com"]
```

3. **Security checklist:**
- [ ] `DEBUG=false` in production
- [ ] API keys stored in secure secret manager
- [ ] CORS origins limited to production domains
- [ ] Database path uses persistent storage
- [ ] Docker socket has proper permissions

### Deployment: Development

**Local development setup:**

```bash
# Terminal 1: Backend
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend
bun install
bun run dev
```

Access: `http://localhost:3000`

### Deployment: Docker Compose (Recommended)

**1. Create docker-compose.yml:**

```yaml
version: '3.8'

services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=sqlite+aiosqlite:////data/bioinfoflow.db
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - CORS_ORIGINS=["http://localhost:3000"]
    volumes:
      - ./data:/data
      - /var/run/docker.sock:/var/run/docker.sock
    restart: unless-stopped

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_BASE_URL=http://backend:8000
    depends_on:
      - backend
    restart: unless-stopped

volumes:
  data:
```

**2. Deploy:**

```bash
# Build and start
docker compose up -d --build

# Check status
docker compose ps

# View logs
docker compose logs -f

# Stop
docker compose down
```

### Deployment: Production (Systemd)

**Backend service (`/etc/systemd/system/bioinfoflow-backend.service`):**

```ini
[Unit]
Description=Bioinfoflow Backend
After=network.target docker.service

[Service]
Type=simple
User=bioinfoflow
WorkingDirectory=/opt/bioinfoflow/backend
Environment="PATH=/opt/bioinfoflow/backend/.venv/bin"
ExecStart=/opt/bioinfoflow/backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Frontend service (`/etc/systemd/system/bioinfoflow-frontend.service`):**

```ini
[Unit]
Description=Bioinfoflow Frontend
After=network.target bioinfoflow-backend.service

[Service]
Type=simple
User=bioinfoflow
WorkingDirectory=/opt/bioinfoflow/frontend
Environment="NODE_ENV=production"
ExecStart=/usr/local/bin/bun run start
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Enable and start:**

```bash
sudo systemctl daemon-reload
sudo systemctl enable bioinfoflow-backend bioinfoflow-frontend
sudo systemctl start bioinfoflow-backend bioinfoflow-frontend
```

**Check status:**

```bash
sudo systemctl status bioinfoflow-backend
sudo systemctl status bioinfoflow-frontend
sudo journalctl -u bioinfoflow-backend -f
```

### Database Migrations

**Apply migrations:**

```bash
cd backend
uv run alembic upgrade head
```

**Create new migration:**

```bash
uv run alembic revision --autogenerate -m "Add new column"
```

**Rollback migration:**

```bash
uv run alembic downgrade -1        # Rollback one migration
uv run alembic downgrade <revision>  # Rollback to specific revision
```

**Check migration status:**

```bash
uv run alembic current               # Show current revision
uv run alembic history               # Show migration history
```

---

## Monitoring

### Health Checks

**Backend health endpoint:**

```bash
curl http://localhost:8000/api/v1/health
# Expected: {"status": "ok"}
```

**Frontend:**

```bash
curl http://localhost:3000/api/health
# Expected: 200 OK
```

### Logging

**Backend logs (structlog):**

```bash
# Docker Compose
docker compose logs -f backend

# Systemd
sudo journalctl -u bioinfoflow-backend -f

# Development
# Logs written to stdout/stderr
```

**Frontend logs:**

```bash
# Docker Compose
docker compose logs -f frontend

# Systemd
sudo journalctl -u bioinfoflow-frontend -f
```

### Key Metrics to Monitor

**System Health:**
- CPU usage (should be <70% under normal load)
- Memory usage (2GB+ recommended)
- Disk space (10GB+ recommended)
- Docker daemon status

**Application Metrics:**
- API response times (<200ms for simple requests)
- SSE connection count
- Active agent conversations
- Workflow run queue length

**Database:**
- SQLite file size
- Query execution time
- Connection pool status

### Monitoring Tools

**Recommended setup:**

1. **System monitoring:**
   - Prometheus + Grafana for metrics
   - Loki for log aggregation
   - Alertmanager for alerts

2. **Application monitoring:**
   - FastAPI middleware for request tracking
   - LangSmith for agent observability (optional)
   - Sentry for error tracking (optional)

3. **Infrastructure:**
   - Docker stats for container metrics
   - Disk usage monitoring
   - Network traffic monitoring

---

## Common Issues

### Issue: Backend won't start

**Symptoms:**
- Backend crashes on startup
- "Connection refused" errors from frontend

**Diagnosis:**

```bash
# Check if backend is running
curl http://localhost:8000/api/v1/health

# View logs
docker compose logs backend
# Or
sudo journalctl -u bioinfoflow-backend -n 50
```

**Common causes and fixes:**

1. **Database migration needed:**
   ```bash
   cd backend
   uv run alembic upgrade head
   ```

2. **Missing environment variables:**
   ```bash
   # Check .env file exists and has required vars
   cat backend/.env | grep API_KEY
   ```

3. **Port already in use:**
   ```bash
   # Find process using port 8000
   lsof -i :8000
   # Kill process or change port
   ```

4. **Docker socket permission:**
   ```bash
   # Add user to docker group
   sudo usermod -aG docker $USER
   newgrp docker
   ```

### Issue: Agent not responding

**Symptoms:**
- Agent requests timeout
- No SSE events received
- "Agent thinking..." indefinitely

**Diagnosis:**

```bash
# Check backend logs for LLM API errors
docker compose logs backend | grep -i "anthropic\|openai\|gemini"

# Test LLM API connectivity
curl -H "x-api-key: $ANTHROPIC_API_KEY" https://api.anthropic.com/v1/messages
```

**Common causes and fixes:**

1. **Invalid API key:**
   ```bash
   # Verify API key is set and valid
   echo $ANTHROPIC_API_KEY
   # Update .env and restart
   ```

2. **Rate limit exceeded:**
   - Wait for rate limit reset
   - Switch to different LLM provider
   - Increase retry delays

3. **LLM API outage:**
   - Check status pages:
     - Anthropic: https://status.anthropic.com
     - OpenAI: https://status.openai.com
   - Switch to backup provider

4. **Network connectivity:**
   ```bash
   # Test outbound connectivity
   curl -I https://api.anthropic.com
   # Check firewall rules
   ```

### Issue: Workflow execution fails

**Symptoms:**
- Workflow runs stuck in "pending" state
- Docker container errors
- Nextflow/MiniWDL errors

**Diagnosis:**

```bash
# Check Docker daemon
docker ps
docker info

# Check workflow logs
docker compose logs backend | grep -i "workflow\|nextflow\|miniwdl"

# Check workflow working directory
ls -la /tmp/bioinfoflow/work
```

**Common causes and fixes:**

1. **Docker daemon not running:**
   ```bash
   sudo systemctl start docker
   ```

2. **Insufficient disk space:**
   ```bash
   df -h /tmp/bioinfoflow
   # Clean up old workflow directories
   rm -rf /tmp/bioinfoflow/work/*
   ```

3. **Missing workflow engine:**
   ```bash
   # Install Nextflow
   curl -s https://get.nextflow.io | bash
   sudo mv nextflow /usr/local/bin/

   # Or install MiniWDL
   pip install miniwdl
   ```

4. **Permission issues:**
   ```bash
   # Ensure working directories are writable
   sudo chown -R bioinfoflow:bioinfoflow /tmp/bioinfoflow
   ```

### Issue: Frontend can't connect to backend

**Symptoms:**
- API errors in browser console
- "Failed to fetch" errors
- CORS errors

**Diagnosis:**

```bash
# Test backend from frontend container
docker compose exec frontend curl http://backend:8000/api/v1/health

# Check CORS configuration
docker compose logs backend | grep -i cors
```

**Common causes and fixes:**

1. **CORS misconfiguration:**
   ```bash
   # Update backend/.env
   CORS_ORIGINS=["http://localhost:3000","https://your-domain.com"]
   # Restart backend
   docker compose restart backend
   ```

2. **Backend not reachable:**
   ```bash
   # Check if backend is running
   docker compose ps backend
   # Check network connectivity
   docker compose exec frontend ping backend
   ```

3. **Wrong API URL:**
   ```bash
   # Check frontend environment
   docker compose exec frontend env | grep API_BASE_URL
   # Should be: NEXT_PUBLIC_API_BASE_URL=http://backend:8000
   ```

### Issue: Database corruption

**Symptoms:**
- SQLite errors in logs
- "database is locked" errors
- Data inconsistencies

**Diagnosis:**

```bash
# Check database integrity
sqlite3 backend/bioinfoflow.db "PRAGMA integrity_check;"

# Check file permissions
ls -la backend/bioinfoflow.db
```

**Recovery:**

1. **If integrity check passes:**
   ```bash
   # Restart services
   docker compose restart
   ```

2. **If integrity check fails:**
   ```bash
   # Stop services
   docker compose down

   # Restore from backup
   cp backend/bioinfoflow.db.backup backend/bioinfoflow.db

   # Or rebuild from migrations
   rm backend/bioinfoflow.db
   cd backend
   uv run alembic upgrade head

   # Restart
   docker compose up -d
   ```

### Issue: High memory usage

**Symptoms:**
- OOM (Out of Memory) kills
- Slow response times
- System swapping

**Diagnosis:**

```bash
# Check container memory usage
docker stats

# Check system memory
free -h
```

**Mitigation:**

1. **Limit container memory:**
   ```yaml
   # docker-compose.yml
   services:
     backend:
       mem_limit: 2g
       mem_reservation: 1g
   ```

2. **Tune agent settings:**
   ```bash
   # Reduce token limits
   AGENT_MAX_TOKENS=2048
   ```

3. **Clean up old data:**
   ```bash
   # Remove old workflow artifacts
   find /tmp/bioinfoflow -mtime +7 -delete
   ```

---

## Rollback Procedures

### Application Rollback

**Docker Compose:**

```bash
# 1. Stop current version
docker compose down

# 2. Checkout previous version
git checkout <previous-tag>

# 3. Rebuild and start
docker compose up -d --build

# 4. Verify health
curl http://localhost:8000/api/v1/health
```

**Systemd:**

```bash
# 1. Stop services
sudo systemctl stop bioinfoflow-backend bioinfoflow-frontend

# 2. Restore previous version
cd /opt/bioinfoflow
git checkout <previous-tag>

# 3. Reinstall dependencies
cd backend && uv sync
cd ../frontend && bun install && bun run build

# 4. Restart services
sudo systemctl start bioinfoflow-backend bioinfoflow-frontend

# 5. Verify
sudo systemctl status bioinfoflow-backend
```

### Database Rollback

**Rollback to previous migration:**

```bash
cd backend

# View migration history
uv run alembic history

# Rollback one migration
uv run alembic downgrade -1

# Or rollback to specific revision
uv run alembic downgrade <revision-id>
```

**Restore from backup:**

```bash
# Stop services
docker compose down

# Restore database file
cp backend/bioinfoflow.db.backup backend/bioinfoflow.db

# Restart
docker compose up -d
```

### Emergency Rollback

**If application is completely broken:**

```bash
# 1. Stop everything
docker compose down
sudo systemctl stop bioinfoflow-*

# 2. Restore last known good state
git checkout <last-good-tag>
cp backend/bioinfoflow.db.backup backend/bioinfoflow.db

# 3. Rebuild from scratch
cd backend && uv sync
cd ../frontend && bun install && bun run build

# 4. Start services
docker compose up -d --build
# Or
sudo systemctl start bioinfoflow-backend bioinfoflow-frontend

# 5. Verify all services
curl http://localhost:8000/api/v1/health
curl http://localhost:3000
```

---

## Maintenance

### Regular Maintenance Tasks

**Daily:**
- Check service health status
- Monitor disk space usage
- Review error logs

**Weekly:**
- Backup database
- Clean up old workflow artifacts
- Review security advisories

**Monthly:**
- Update dependencies
- Review and optimize database
- Audit system access logs

### Backup Procedures

**Database backup:**

```bash
#!/bin/bash
# backup-db.sh

DATE=$(date +%Y%m%d-%H%M%S)
DB_FILE="backend/bioinfoflow.db"
BACKUP_DIR="backups"

mkdir -p "$BACKUP_DIR"

# Create backup
sqlite3 "$DB_FILE" ".backup '$BACKUP_DIR/bioinfoflow-$DATE.db'"

# Compress
gzip "$BACKUP_DIR/bioinfoflow-$DATE.db"

# Keep only last 30 days
find "$BACKUP_DIR" -name "bioinfoflow-*.db.gz" -mtime +30 -delete

echo "Backup complete: $BACKUP_DIR/bioinfoflow-$DATE.db.gz"
```

**Run backup:**

```bash
chmod +x backup-db.sh
./backup-db.sh

# Schedule with cron (daily at 2 AM)
crontab -e
# Add: 0 2 * * * /opt/bioinfoflow/backup-db.sh
```

### Cleanup Procedures

**Clean old workflow artifacts:**

```bash
#!/bin/bash
# cleanup-workflows.sh

WORK_DIR="/tmp/bioinfoflow/work"
DAYS=7

# Remove workflow directories older than DAYS
find "$WORK_DIR" -type d -mtime +$DAYS -exec rm -rf {} +

echo "Cleaned workflow artifacts older than $DAYS days"
```

**Clean Docker resources:**

```bash
# Remove unused images
docker image prune -a -f

# Remove unused volumes
docker volume prune -f

# Remove unused networks
docker network prune -f

# Full cleanup
docker system prune -a --volumes -f
```

### Update Procedures

**Update application:**

```bash
# 1. Backup database
./backup-db.sh

# 2. Pull latest code
git fetch origin
git checkout <new-version-tag>

# 3. Update dependencies
cd backend && uv sync
cd ../frontend && bun install

# 4. Run migrations
cd backend && uv run alembic upgrade head

# 5. Rebuild and restart
docker compose up -d --build

# 6. Verify
curl http://localhost:8000/api/v1/health
```

**Update dependencies:**

```bash
# Backend
cd backend
uv sync --upgrade

# Frontend
cd frontend
bun update

# Test after update
uv run pytest
bun run lint
```

### Performance Optimization

**Database optimization:**

```bash
# Vacuum database to reclaim space
sqlite3 backend/bioinfoflow.db "VACUUM;"

# Analyze database for query optimization
sqlite3 backend/bioinfoflow.db "ANALYZE;"
```

**Docker optimization:**

```bash
# Optimize Docker storage
docker system df
docker builder prune -f

# Review Docker logs size
docker inspect --format='{{.LogPath}}' <container-id>
```

---

## Security

### Security Checklist

- [ ] API keys stored in secret manager (not .env files)
- [ ] CORS limited to production domains
- [ ] DEBUG=false in production
- [ ] Database file permissions: 600
- [ ] Docker socket access restricted
- [ ] Regular security updates applied
- [ ] HTTPS enabled (via reverse proxy)
- [ ] Rate limiting configured
- [ ] Input validation on all endpoints

### Security Monitoring

```bash
# Check for exposed secrets
git log --all -p | grep -i "api_key\|secret\|password"

# Review access logs
docker compose logs backend | grep "POST\|PUT\|DELETE"

# Check file permissions
find backend -name "*.db" -exec ls -l {} \;
```

---

## Support

### Escalation Path

1. **Check this runbook** for common issues
2. **Review logs** for error messages
3. **Search issues** on GitHub
4. **Create new issue** with:
   - Detailed description
   - Steps to reproduce
   - Relevant logs
   - System information

### Useful Commands

```bash
# Full system status
docker compose ps
systemctl status bioinfoflow-*

# Tail all logs
docker compose logs -f

# Restart everything
docker compose restart

# Full cleanup and restart
docker compose down
docker compose up -d --build

# Database status
sqlite3 backend/bioinfoflow.db ".tables"
sqlite3 backend/bioinfoflow.db "SELECT COUNT(*) FROM conversations;"
```

---

## Appendix

### System Requirements

**Minimum:**
- 2 CPU cores
- 2GB RAM
- 10GB disk space
- Python 3.13+
- Node.js 18+
- Docker 20.10+

**Recommended:**
- 4 CPU cores
- 4GB RAM
- 50GB disk space
- Fast SSD storage
- Dedicated Docker host

### Useful Links

- [Contributing Guide](CONTRIB.md)
- [Architecture Documentation](02-architecture.md)
- [API Reference](03-api-reference.md)
- [Codemaps](../codemaps/)
