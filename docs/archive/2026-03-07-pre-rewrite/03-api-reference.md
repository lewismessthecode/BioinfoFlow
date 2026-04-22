# Bioinfoflow Backend API Design Document

**Version:** 1.0.0
**Status:** Draft
**Date:** 2026-01-27
**Target Framework:** Python 3.13+ / FastAPI

---

## Table of Contents

1. [Overview](#1-overview)
2. [API Conventions](#2-api-conventions)
3. [Authentication](#3-authentication)
4. [Data Models](#4-data-models)
5. [API Endpoints](#5-api-endpoints)
   - [Projects](#51-projects-api)
   - [Workflows](#52-workflows-api)
   - [Runs](#53-runs-api)
   - [Images](#54-images-api)
   - [Agent](#55-agent-api)
   - [Files](#56-files-api)
   - [Events](#57-events-api)
   - [Demos](#58-demos-api)
6. [Real-time Events (SSE)](#6-real-time-events-sse)
7. [Error Handling](#7-error-handling)
8. [Rate Limiting](#8-rate-limiting)

---

## 1. Overview

### Base URL

```
Development: http://localhost:8000/api/v1
Production:  https://api.bioinfoflow.io/v1
```

### Technology Stack

| Component | Technology |
|-----------|------------|
| Framework | FastAPI |
| ORM | SQLAlchemy 2.0 |
| Database | SQLite (MVP), PostgreSQL (future) |
| Vector Store | Local Markdown + lightweight search (MVP), pgvector (future) |
| Background Tasks | In-process async task runner (MVP), Celery + Redis (future) |
| Real-time | SSE (Server-Sent Events) |
| Validation | Pydantic v2 |
| Auth | JWT (future) |

### Design Principles

1. **RESTful** - Resource-oriented URLs, proper HTTP methods
2. **Consistent Envelope** - Stable `success/data/meta` response shape
3. **Idempotent** - Safe retry for PUT/DELETE operations
4. **Streaming** - Single SSE channel for all real-time updates
5. **Pagination** - Cursor-based for large datasets

---

## 2. API Conventions

### Request Headers

| Header | Required | Description |
|--------|----------|-------------|
| `Content-Type` | Yes | `application/json` |
| `Accept` | No | `application/json` (default) |
| `Authorization` | Future | `Bearer <token>` |
| `X-Request-ID` | No | Client-generated UUID for tracing |

### Resource Identifiers

- **Projects, workflows, images, conversations** use UUIDs in APIs.
- **Runs use `run_id` as the primary external identifier** (human-readable string like `run_a1b2c3`).
- Internal DB UUIDs may exist, but **all run-related URLs use `run_id`**.

### Response Format

All responses follow a consistent structure:

```json
{
  "success": true,
  "data": { ... },
  "meta": {
    "timestamp": "2026-01-16T10:30:00Z",
    "request_id": "uuid-string",
    "pagination": { ... }   // Only for list endpoints
  }
}
```

> **Note:** Some examples below omit the `meta` object for brevity. In production responses, `meta` is always present.

**Meta extensions:** Some endpoints may include `meta.status` for non-fatal system hints (e.g. `{"docker": "unavailable"}` on Images list when Docker is not running).

Error responses:

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Human-readable message",
    "details": [ ... ]
  },
  "meta": {
    "timestamp": "2026-01-16T10:30:00Z",
    "request_id": "uuid-string"
  }
}
```

### HTTP Status Codes

| Code | Usage |
|------|-------|
| 200 | Success (GET, PUT, PATCH) |
| 201 | Created (POST) |
| 202 | Accepted (async operations) |
| 204 | No Content (DELETE) |
| 400 | Bad Request |
| 401 | Unauthorized |
| 403 | Forbidden |
| 404 | Not Found |
| 409 | Conflict |
| 422 | Validation Error |
| 429 | Rate Limited |
| 500 | Internal Server Error |
| 503 | Service Unavailable |

### Pagination

Cursor-based pagination for list endpoints:

**Request:**
```
GET /api/v1/runs?limit=20&cursor=eyJpZCI6MTAwfQ==
```

**Response:**
```json
{
  "success": true,
  "data": [ ... ],
  "meta": {
    "pagination": {
      "limit": 20,
      "has_more": true,
      "next_cursor": "eyJpZCI6MTIwfQ==",
      "total_count": 150
    }
  }
}
```

### Filtering

```
GET /api/v1/runs?status=running,failed&project_id=uuid&workflow_id=uuid
```

- `status` supports comma-separated values.
- Other list endpoints expose `search` and `source` filters as documented per resource.

---

## 3. Authentication

> **MVP Note:** Authentication is deferred to v1.0. For MVP, the API is single-user local-only.

### Future Implementation

```
POST /api/v1/auth/login
POST /api/v1/auth/refresh
POST /api/v1/auth/logout
```

JWT tokens with refresh mechanism.

---

## 4. Data Models

### 4.1 Project

```python
class Project(BaseModel):
    id: UUID
    name: str                    # max 100 chars
    description: Optional[str]   # max 500 chars
    workspace_path: str          # absolute path; relative inputs resolve against repo root
    created_at: datetime
    updated_at: datetime
```

### 4.2 Workflow

```python
class WorkflowSource(str, Enum):
    NFCORE = "nf-core"
    GITHUB = "github"
    LOCAL = "local"

class WorkflowEngine(str, Enum):
    NEXTFLOW = "nextflow"
    WDL = "wdl"

class Workflow(BaseModel):
    id: UUID
    name: str                    # e.g., "nf-core/viralrecon"
    description: Optional[str]
    source: WorkflowSource
    engine: WorkflowEngine       # nextflow | wdl
    source_url: Optional[str]    # GitHub URL or nf-core pipeline name
    version: str                 # e.g., "2.6.0"
    estimated_time: Optional[str]
    schema_json: Optional[dict]  # Engine-specific inputs/params schema
    created_at: datetime
    updated_at: datetime
```

### 4.3 Run

```python
class RunStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class Run(BaseModel):
    run_id: str                  # Primary external ID (used in URLs)
    id: Optional[UUID]           # Internal DB ID (optional for clients)
    project_id: UUID
    workflow_id: UUID
    status: RunStatus
    workspace: str               # Analysis directory path
    config: dict                 # Engine-specific config (params for Nextflow, inputs for WDL)
    samplesheet_path: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_seconds: Optional[int]
    samples_count: int
    tasks_total: int
    tasks_completed: int
    current_task: Optional[str]
    error_message: Optional[str]
    nextflow_run_name: Optional[str]
    created_at: datetime
    updated_at: datetime
```

### 4.4 Docker Image

```python
class ImageStatus(str, Enum):
    LOCAL = "local"
    REMOTE = "remote"
    PULLING = "pulling"

class DockerImage(BaseModel):
    id: UUID
    name: str                    # e.g., "bioinfoflow/bwa"
    tag: str                     # e.g., "v2.2.1"
    full_name: str               # e.g., "bioinfoflow/bwa:v2.2.1"
    description: Optional[str]
    size_bytes: Optional[int]
    status: ImageStatus
    registry: str                # e.g., "docker.io", "ghcr.io"
    pull_progress: Optional[int] # 0-100 when pulling
    created_at: datetime
    updated_at: datetime
```

### 4.5 Chat Message

```python
class MessageRole(str, Enum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"

class MessageType(str, Enum):
    TEXT = "text"
    THINKING = "thinking"
    ARTIFACT = "artifact"
    PLAN = "plan"
    STATUS = "status"
    COMPLETION = "completion"

class ChatMessage(BaseModel):
    id: UUID
    conversation_id: UUID
    project_id: UUID
    role: MessageRole
    type: MessageType
    content: str
    metadata: Optional[dict]     # Artifacts, plans, status, etc.
    created_at: datetime
```

### 4.6 File

```python
class FileType(str, Enum):
    FILE = "file"
    DIRECTORY = "directory"

class FileInfo(BaseModel):
    name: str
    path: str                    # Relative to workspace
    type: FileType
    size_bytes: Optional[int]
    modified_at: Optional[datetime]
    children: Optional[List["FileInfo"]]  # For directories
```

---

## 5. API Endpoints

### 5.1 Projects API

#### List Projects

```http
GET /api/v1/projects
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | int | Max items (default: 20) |
| `cursor` | string | Pagination cursor |
| `search` | string | Search by name |

**Response:** `200 OK`
```json
{
  "success": true,
  "data": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "COVID Analysis",
      "description": "SARS-CoV-2 variant analysis project",
      "workspace_path": "/data/covid_samples",
      "created_at": "2026-01-27T09:00:00Z",
      "updated_at": "2026-01-27T10:30:00Z"
    }
  ],
  "meta": {
    "pagination": {
      "limit": 20,
      "has_more": false,
      "next_cursor": null,
      "total_count": 1
    }
  }
}
```

#### Create Project

```http
POST /api/v1/projects
```

**Request Body:**
```json
{
  "name": "RNA-Seq Batch 1",
  "description": "Differential expression analysis",
  "workspace_path": "/data/rnaseq_batch1"
}
```

**Response:** `201 Created`

#### Get Project

```http
GET /api/v1/projects/{project_id}
```

**Response:** `200 OK`

#### Update Project

```http
PATCH /api/v1/projects/{project_id}
```

**Request Body:**
```json
{
  "name": "Updated Name",
  "description": "Updated description"
}
```

**Response:** `200 OK`

#### Delete Project

```http
DELETE /api/v1/projects/{project_id}
```

**Response:** `204 No Content`

---

### 5.2 Workflows API

#### List Workflows

```http
GET /api/v1/workflows
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | int | Max items (default: 20) |
| `cursor` | string | Pagination cursor |
| `search` | string | Search by name or description |
| `source` | string | Filter by source (`nf-core`, `github`, `local`) |

**Response:** `200 OK`
```json
{
  "success": true,
  "data": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440111",
      "name": "viralrecon",
      "description": "Viral genome analysis pipeline",
      "source": "nf-core",
      "engine": "nextflow",
      "source_url": "nf-core/viralrecon",
      "version": "latest",
      "estimated_time": "~15min",
      "schema_json": null,
      "created_at": "2026-01-27T09:00:00Z",
      "updated_at": "2026-01-27T09:00:00Z"
    }
  ]
}
```

#### Register Workflow

```http
POST /api/v1/workflows
```

**Request Body (nf-core):**
```json
{
  "source": "nf-core",
  "name": "viralrecon",
  "version": "latest",
  "engine": "nextflow"
}
```

**Request Body (github):**
```json
{
  "source": "github",
  "source_url": "https://github.com/user/pipeline",
  "version": "main",
  "engine": "nextflow"
}
```

**Request Body (local):**
```json
{
  "source": "local",
  "file_name": "main.wdl",
  "content": "workflow demo { call task1 }",
  "engine": "wdl"
}
```

**Notes:**
- `source_url` is required for `github` workflows.
- For `local`, either `content` or a filesystem `source_url` must be provided.

**Response:** `201 Created`

#### Get Workflow

```http
GET /api/v1/workflows/{workflow_id}
```

**Response:** `200 OK`

#### Update Workflow

```http
PATCH /api/v1/workflows/{workflow_id}
```

**Request Body:**
```json
{
  "description": "Updated description",
  "estimated_time": "~20min",
  "schema_json": {"params": {"input": {"type": "string"}}}
}
```

**Response:** `200 OK`

#### Delete Workflow

```http
DELETE /api/v1/workflows/{workflow_id}
```

**Response:** `204 No Content`

---

### 5.3 Runs API

> **Note:** All run endpoints use `run_id` in URLs (e.g., `/runs/run_a1b2c3`).

#### Create Run

```http
POST /api/v1/runs
```

**Request Body:**
```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "workflow_id": "550e8400-e29b-41d4-a716-446655440111",
  "workspace": ".",
  "params": {
    "input": "samplesheet.csv",
    "outdir": "results"
  },
  "inputs": {
    "fastq_1": "raw/S001_R1.fq.gz",
    "fastq_2": "raw/S001_R2.fq.gz"
  },
  "config_overrides": {
    "process.cpus": 4
  }
}
```

**Response:** `202 Accepted`
```json
{
  "success": true,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440222",
    "run_id": "run_a1b2c3",
    "project_id": "550e8400-e29b-41d4-a716-446655440000",
    "workflow_id": "550e8400-e29b-41d4-a716-446655440111",
    "status": "queued",
    "workspace": ".",
    "config": {
      "params": {"input": "samplesheet.csv", "outdir": "results"},
      "inputs": {"fastq_1": "raw/S001_R1.fq.gz", "fastq_2": "raw/S001_R2.fq.gz"},
      "config_overrides": {"process.cpus": 4}
    },
    "samplesheet_path": null,
    "started_at": null,
    "completed_at": null,
    "duration_seconds": null,
    "samples_count": 0,
    "tasks_total": 0,
    "tasks_completed": 0,
    "current_task": null,
    "error_message": null,
    "nextflow_run_name": null,
    "created_at": "2026-01-27T10:30:00Z",
    "updated_at": "2026-01-27T10:30:00Z"
  }
}
```

#### List Runs

```http
GET /api/v1/runs
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | int | Max items (default: 20) |
| `cursor` | string | Pagination cursor |
| `project_id` | uuid | Filter by project |
| `workflow_id` | uuid | Filter by workflow |
| `status` | string | Filter by status (comma-separated) |

**Response:** `200 OK`

#### Get Run

```http
GET /api/v1/runs/{run_id}
```

**Response:** `200 OK`

#### Get Run Logs

```http
GET /api/v1/runs/{run_id}/logs
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `tail` | int | Last N lines (default: 100) |
| `task` | string | Optional task label to annotate results |

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "logs": [
      {"message": "Starting pipeline...", "task": null},
      {"message": "Process FASTQC started", "task": "FASTQC"}
    ]
  }
}
```

#### Get Run DAG

```http
GET /api/v1/runs/{run_id}/dag
```

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "nodes": [
      {
        "id": "fastp",
        "type": "pipeline",
        "position": {"x": 0, "y": 0},
        "data": {"label": "FASTP", "status": "pending"}
      }
    ],
    "edges": [
      {"id": "e0", "source": "fastp", "target": "bwa_mem", "animated": false}
    ]
  }
}
```

#### Get Run Output Files

```http
GET /api/v1/runs/{run_id}/outputs
```

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "files": [
      {
        "name": "multiqc_report.html",
        "path": "results/multiqc/multiqc_report.html",
        "size_bytes": 2457600,
        "type": "file"
      }
    ]
  }
}
```

#### Download Run Output

```http
GET /api/v1/runs/{run_id}/outputs/download
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `file` | string | Specific file path (optional) |
| `format` | string | `tar.gz` or `zip` (default: `tar.gz`) |

**Response:** File download stream

#### Cancel Run

```http
POST /api/v1/runs/{run_id}/cancel
```

**Response:** `200 OK`

#### Resume Run

```http
POST /api/v1/runs/{run_id}/resume
```

**Request Body (optional):**
```json
{
  "config_overrides": {
    "process.memory": "32.GB"
  }
}
```

**Response:** `202 Accepted`
```json
{
  "success": true,
  "data": {
    "run_id": "run_a1b2c3",
    "new_run_id": "run_x1y2z3",
    "status": "queued",
    "message": "Run resumed"
  }
}
```

#### Retry Run

```http
POST /api/v1/runs/{run_id}/retry
```

**Request Body (optional):**
```json
{
  "params": {"min_depth": 5},
  "config_overrides": {"process.cpus": 8}
}
```

**Response:** `202 Accepted`
```json
{
  "success": true,
  "data": {
    "run_id": "run_a1b2c3",
    "new_run_id": "run_x1y2z3",
    "status": "queued",
    "message": "Run retried"
  }
}
```

#### Delete Run

```http
DELETE /api/v1/runs/{run_id}
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `delete_outputs` | bool | Also delete output files (default: false) |

**Response:** `204 No Content`

---

### 5.4 Images API

#### List Images

```http
GET /api/v1/images
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | int | Max items (default: 20) |
| `cursor` | string | Pagination cursor |
| `search` | string | Search by name |
| `status` | string | Filter by status (`local`, `remote`, `pulling`) |

**Response:** `200 OK`
```json
{
  "success": true,
  "data": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440333",
      "name": "biocontainers/fastqc",
      "tag": "0.12.1",
      "full_name": "biocontainers/fastqc:0.12.1",
      "status": "local",
      "registry": "docker.io",
      "size_bytes": 235000000,
      "pull_progress": null,
      "labels": null,
      "env": null,
      "entrypoint": null,
      "created_at": "2026-01-27T09:00:00Z",
      "updated_at": "2026-01-27T09:00:00Z"
    }
  ],
  "meta": {
    "status": {"docker": "unavailable"}
  }
}
```

#### Get Image

```http
GET /api/v1/images/{image_id}
```

**Response:** `200 OK`

#### Pull Image

```http
POST /api/v1/images/pull
```

**Request Body:**
```json
{
  "name": "biocontainers/fastqc",
  "tag": "0.12.1",
  "registry": "docker.io",
  "project_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response:** `202 Accepted`

#### Load Image (tarball)

```http
POST /api/v1/images/load
```

**Form Data:**
- `file` (required)
- `project_id` (optional)

**Response:** `201 Created`

#### Delete Image

```http
DELETE /api/v1/images/{image_id}
```

**Response:** `204 No Content`

---

### 5.5 Agent API

#### Send Message

```http
POST /api/v1/agent/message
```

**Request Body:**
```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "conversation_id": null,
  "type": "text",
  "content": "Find workflows for SARS-CoV-2"
}
```

**Response:** `202 Accepted`
```json
{
  "success": true,
  "data": {
    "message_id": "550e8400-e29b-41d4-a716-446655440444",
    "conversation_id": "550e8400-e29b-41d4-a716-446655440555",
    "status": "processing"
  }
}
```

> Agent responses stream over SSE (`/events/stream`).

#### Create Conversation

```http
POST /api/v1/agent/conversations
```

**Request Body:**
```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "SARS-CoV-2 analysis"
}
```

**Response:** `201 Created`

#### List Conversations

```http
GET /api/v1/agent/conversations
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `project_id` | uuid | Optional filter |
| `limit` | int | Max items (default: 20) |
| `cursor` | string | Pagination cursor |

**Response:** `200 OK`
```json
{
  "success": true,
  "data": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440555",
      "project_id": "550e8400-e29b-41d4-a716-446655440000",
      "title": "SARS-CoV-2 analysis",
      "pinned": false,
      "created_at": "2026-01-27T10:00:00Z",
      "updated_at": "2026-01-27T10:05:00Z"
    }
  ]
}
```

#### Get Conversation History

```http
GET /api/v1/agent/conversations/{conversation_id}
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | int | Max messages (default: 50) |
| `before` | string | Cursor (message id) |

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "conversation_id": "550e8400-e29b-41d4-a716-446655440555",
    "project_id": "550e8400-e29b-41d4-a716-446655440000",
    "title": "SARS-CoV-2 analysis",
    "pinned": false,
    "messages": [
      {
        "id": "550e8400-e29b-41d4-a716-446655440444",
        "role": "user",
        "type": "text",
        "content": "Find workflows for SARS-CoV-2",
        "metadata": null,
        "created_at": "2026-01-27T10:00:00Z"
      }
    ]
  }
}
```

#### Update Conversation

```http
PATCH /api/v1/agent/conversations/{conversation_id}
```

**Request Body:**
```json
{
  "title": "Updated title",
  "pinned": true
}
```

**Response:** `200 OK`

#### Delete Conversation

```http
DELETE /api/v1/agent/conversations/{conversation_id}
```

**Response:** `204 No Content`

#### Cancel Conversation

```http
POST /api/v1/agent/conversations/{conversation_id}/cancel
```

**Response:** `200 OK`

#### Conversation Status

```http
GET /api/v1/agent/conversations/{conversation_id}/status
```

**Response:** `200 OK`

#### Agent Trace

```http
GET /api/v1/agent/conversations/{conversation_id}/trace
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `message_id` | uuid | Filter trace by a specific message |
| `include_prompt` | bool | Include prompt payloads (default: false) |
| `limit` | int | Max events (default: 200) |

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "conversation_id": "550e8400-e29b-41d4-a716-446655440555",
    "events": [
      {
        "id": "550e8400-e29b-41d4-a716-446655440666",
        "conversation_id": "550e8400-e29b-41d4-a716-446655440555",
        "message_id": "550e8400-e29b-41d4-a716-446655440444",
        "type": "agent.tool",
        "payload": {"name": "search_workflows", "status": "success"},
        "created_at": "2026-01-27T10:01:00Z"
      }
    ]
  }
}
```

---

### 5.6 Files API

> **Safety:** All file operations are constrained to the project's `workspace_path`. Any path traversal outside the workspace is rejected.

#### List Files (Workspace Browser)

```http
GET /api/v1/files
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `project_id` | uuid | Project workspace root (required) |
| `path` | string | Relative path (default: `.`) |
| `recursive` | bool | Include subdirectories (default: false) |
| `pattern` | string | Glob pattern filter |

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "path": ".",
    "files": [
      {
        "name": "raw",
        "path": "raw",
        "type": "directory",
        "children": []
      },
      {
        "name": "samplesheet.csv",
        "path": "samplesheet.csv",
        "type": "file",
        "size_bytes": 256
      }
    ]
  }
}
```

#### Read File

```http
GET /api/v1/files/read
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `project_id` | uuid | Project workspace root |
| `path` | string | Relative file path |
| `lines` | int | Max lines to read (default: 100) |
| `offset` | int | Start from line N |

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "path": "samplesheet.csv",
    "content": "sample,fastq_1,fastq_2
S001,S001_R1.fq.gz,S001_R2.fq.gz
",
    "total_lines": 4,
    "truncated": false
  }
}
```

#### Download File

```http
GET /api/v1/files/download
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `project_id` | uuid | Project workspace root |
| `path` | string | Relative file path |

**Response:** File download stream

#### Write File

```http
POST /api/v1/files/write
```

**Request Body:**
```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "path": "samplesheet.csv",
  "content": "sample,fastq_1,fastq_2
..."
}
```

**Response:** `200 OK`

#### Upload File

```http
POST /api/v1/files/upload
```

**Form Data:**
- `project_id` (required)
- `path` (optional)
- `overwrite` (optional, default: false)
- `file` (required)

**Response:** `201 Created`
```json
{
  "success": true,
  "data": {
    "path": "uploads/sample.fastq.gz"
  }
}
```

#### Scan Directory

```http
POST /api/v1/files/scan
```

**Request Body:**
```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "path": ".",
  "file_types": ["fastq", "bam", "vcf"]
}
```

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "path": ".",
    "detected_samples": [
      {
        "sample_id": "S001",
        "files": [
          {"type": "fastq_1", "path": "raw/S001_R1.fq.gz"},
          {"type": "fastq_2", "path": "raw/S001_R2.fq.gz"}
        ]
      }
    ],
    "file_format": "paired-end",
    "compression": "gzip",
    "total_samples": 1
  }
}
```

#### Delete Path

```http
DELETE /api/v1/files
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `project_id` | uuid | Project workspace root |
| `path` | string | Relative path |

**Response:** `200 OK`
```json
{
  "success": true,
  "data": {
    "path": "raw/old_sample.fastq.gz"
  }
}
```

---

### 5.7 Events API

#### Stream Events (SSE)

```http
GET /api/v1/events/stream?project_id={uuid}
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `project_id` | uuid | Required |
| `conversation_id` | uuid | Optional filter |
| `run_id` | string | Optional filter |
| `image_id` | uuid | Optional filter |

**Response:** `text/event-stream` (see Section 6 for event types)

---

### 5.8 Demos API

#### List Demos

```http
GET /api/v1/demos
```

**Response:** `200 OK`
```json
{
  "success": true,
  "data": [
    {
      "id": "demo-sars-cov-2",
      "title": "SARS-CoV-2 Fast Demo",
      "species": "SARS-CoV-2",
      "accession": "NC_045512.2",
      "runtime": "~2-4 min",
      "description": "Quick QC run using the demo Nextflow pipeline.",
      "workspace_path": "demo/workspace"
    }
  ]
}
```

#### Run Demo

```http
POST /api/v1/demos/{demo_id}/run
```

**Request Body:**
```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response:** `201 Created`
```json
{
  "success": true,
  "data": {
    "demo_id": "demo-sars-cov-2",
    "project_id": "550e8400-e29b-41d4-a716-446655440000",
    "workflow_id": "550e8400-e29b-41d4-a716-446655440111",
    "run_id": "run_x1y2z3"
  }
}
```

---

## 6. Real-time Events (SSE)

### Connection

```http
GET /api/v1/events/stream?project_id={uuid}&conversation_id={uuid}&run_id={run_id}
```

- `project_id` is required.
- `conversation_id`, `run_id`, `image_id` are optional filters.
- SSE is server to client only. All client actions use REST endpoints.

### Event Envelope

Each SSE message uses standard SSE fields and includes a JSON envelope in the `data` payload:

```
id: <uuid>
event: run.status
data: {"id":"...","event":"run.status","project_id":"...","timestamp":"...","run_id":"run_a1b2c3","data":{...}}
```

Envelope fields:
- `id` (event id)
- `event` (event name)
- `project_id` (always present)
- `timestamp`
- `data` (event-specific payload)
- `conversation_id` / `run_id` / `image_id` when applicable

### Event Types

#### Run Status Updates

```
event: run.status
data: {"id":"...","event":"run.status","project_id":"...","run_id":"run_a1b2c3","timestamp":"...","data":{"run_id":"run_a1b2c3","status":"running","current_task":"FASTQC","tasks_completed":1,"tasks_total":10,"message":"Run queued"}}
```

#### Run Logs

```
event: run.log
data: {"id":"...","event":"run.log","project_id":"...","run_id":"run_a1b2c3","timestamp":"...","data":{"run_id":"run_a1b2c3","level":"info","message":"Process FASTQC completed","task":"FASTQC","timestamp":"..."}}
```

#### Run DAG Snapshot/Updates

```
event: run.dag
data: {"id":"...","event":"run.dag","project_id":"...","run_id":"run_a1b2c3","timestamp":"...","data":{"run_id":"run_a1b2c3","dag":{"nodes":[],"edges":[]}}}
```

#### Image Pull Progress

```
event: image.progress
data: {"id":"...","event":"image.progress","project_id":"...","image_id":"uuid","timestamp":"...","data":{"image_id":"uuid","progress":65,"status":"pulling"}}
```

#### Agent Messages

```
event: agent.message
data: {"id":"...","event":"agent.message","project_id":"...","conversation_id":"uuid","timestamp":"...","data":{"id":"message_id","type":"text","content":"I found 3 samples.","metadata":null}}
```

`agent.thinking`, `agent.plan`, and `agent.artifact` use the same payload shape with different `event` names.

#### Agent Lifecycle

```
event: agent.done
data: {"id":"...","event":"agent.done","project_id":"...","conversation_id":"uuid","timestamp":"...","data":{"message_id":"message_id"}}
```

```
event: agent.cancelled
data: {"id":"...","event":"agent.cancelled","project_id":"...","conversation_id":"uuid","timestamp":"...","data":{"message_id":"message_id","reason":"user_cancelled"}}
```

---

## 7. Error Handling

### Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `VALIDATION_ERROR` | 422 | Request body validation failed |
| `NOT_FOUND` | 404 | Resource not found |
| `CONFLICT` | 409 | Resource conflict (duplicate name, etc.) |
| `UNAUTHORIZED` | 401 | Authentication required |
| `FORBIDDEN` | 403 | Permission denied |
| `RATE_LIMITED` | 429 | Too many requests |
| `INTERNAL_ERROR` | 500 | Server error |
| `SERVICE_UNAVAILABLE` | 503 | Dependency unavailable |
| `RUN_IN_PROGRESS` | 409 | Cannot modify running pipeline |
| `PIPELINE_ERROR` | 500 | Nextflow execution error |
| `DOCKER_ERROR` | 500 | Docker operation failed |
| `FILE_NOT_FOUND` | 404 | File path does not exist |
| `PERMISSION_DENIED` | 403 | Cannot access file path |

### Error Response Example

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid request parameters",
    "details": [
      {
        "field": "workspace",
        "message": "Path does not exist",
        "value": "/invalid/path"
      }
    ]
  },
  "meta": {
    "timestamp": "2026-01-16T10:30:00Z",
    "request_id": "uuid"
  }
}
```

---

## 8. Rate Limiting

> **MVP Note:** Rate limiting is deferred to production deployment.

### Headers

```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1705398600
```

### Limits

| Endpoint | Limit |
|----------|-------|
| General | 1000 req/hour |
| Agent messages | 60 req/hour |
| File operations | 300 req/hour |
| Workflow runs | 100 req/hour |

---

## Appendix A: FastAPI Implementation Notes

### Project Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app entry
│   ├── config.py            # Settings (pydantic-settings)
│   ├── database.py          # SQLAlchemy setup
│   ├── models/              # SQLAlchemy models
│   │   ├── project.py
│   │   ├── workflow.py
│   │   ├── run.py
│   │   ├── image.py
│   │   └── message.py
│   ├── schemas/             # Pydantic schemas
│   │   ├── project.py
│   │   ├── workflow.py
│   │   ├── run.py
│   │   └── ...
│   ├── api/
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   ├── projects.py
│   │   │   ├── workflows.py
│   │   │   ├── runs.py
│   │   │   ├── images.py
│   │   │   ├── agent.py
│   │   │   └── files.py
│   │   └── deps.py          # Dependencies (DB session, etc.)
│   ├── services/            # Business logic
│   │   ├── nextflow.py      # Nextflow execution
│   │   ├── docker.py        # Docker operations
│   │   ├── agent.py         # LangGraph agent
│   │   └── files.py         # File scanning
│   ├── runtime/             # In-process task runner & event bus
│   │   ├── task_runner.py
│   │   ├── jobs.py
│   │   └── events.py
│   └── utils/
│       ├── exceptions.py
│       └── responses.py
├── tests/
├── alembic/                 # Database migrations
├── pyproject.toml
└── Dockerfile
```

### Router Example

```python
# app/api/v1/workflows.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.workflow import WorkflowCreate, WorkflowResponse, WorkflowList
from app.services import workflow_service

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.get("", response_model=WorkflowList)
async def list_workflows(
    limit: int = 20,
    cursor: str | None = None,
    search: str | None = None,
    source: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List registered workflow templates."""
    return await workflow_service.list_workflows(
        db, limit=limit, cursor=cursor, search=search, source=source
    )


@router.post("", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
async def register_workflow(
    workflow: WorkflowCreate,
    db: AsyncSession = Depends(get_db),
):
    """Register a new workflow template."""
    return await workflow_service.register_workflow(db, workflow)


@router.post("/{workflow_id}/run", status_code=status.HTTP_202_ACCEPTED)
async def run_workflow(
    workflow_id: str,
    run_config: RunConfig,
    db: AsyncSession = Depends(get_db),
):
    """Start a new pipeline run."""
    return await workflow_service.start_run(db, workflow_id, run_config)
```

---

## Appendix B: OpenAPI Schema

The full OpenAPI 3.1 schema will be auto-generated by FastAPI and available at:

```
GET /api/v1/openapi.json
GET /api/v1/docs          # Swagger UI
GET /api/v1/redoc         # ReDoc
```

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-01-16 | Initial API design document |
