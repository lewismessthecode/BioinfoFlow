# Phase 4 — DAG and Schema Improvements

**依赖**: Phase 1 (引擎抽象), 最好在 Phase 2 之后执行
**被依赖**: 无

## 目标

改善新注册流程的 DAG 解析准确性和运行时节点匹配，明确区分 **schema DAG** (静态) 和 **runtime DAG** (动态)。

## DAG 双层模型

```
Layer 1: Schema DAG (注册时)
  来源: nextflow inspect / nf-core schema / miniwdl check / 正则 fallback
  质量: 取决于引擎工具可用性和管线复杂度

Layer 2: Runtime DAG (运行时)
  来源: task events + trace file
  质量: 始终反映实际执行

展示层: 合并 Schema DAG + Runtime DAG
  schema 提供结构, runtime 提供状态
  无 schema 时: runtime 独立构建
```

## 新增/修改文件

```
backend/app/engine/
└── schema_extractor.py      # 统一 schema 提取

backend/app/utils/
└── dag_matcher.py           # 模糊匹配器

修改:
  engine/adapters/nextflow.py  # extract_schema()
  engine/adapters/wdl.py       # extract_schema()
  utils/dag_builder.py         # 运行时动态构建
  services/workflow_validator.py  # 委托 adapter
  runtime/jobs.py              # 使用 DagMatcher
```

## 详细设计

### 1. EngineAdapter 扩展

```python
# engine/adapter.py (扩展)
class EngineAdapter(ABC):
    # ... existing ...
    async def extract_schema(self, source: str, **kwargs) -> dict | None:
        """引擎原生 schema 提取. 返回 None 如果不支持."""
        return None
```

### 2. NextflowAdapter.extract_schema

```python
async def extract_schema(self, source, **kwargs):
    # Strategy 1: nf-core schema (pipeline name → GitHub nextflow_schema.json)
    if self._is_nfcore(source):
        schema = await self._fetch_nfcore_schema(source)
        if schema: return schema

    # Strategy 2: nextflow inspect (NF 23.10+, JSON output)
    schema = await self._run_inspect(source)
    if schema: return schema

    # Strategy 3: parse dag.dot if provided
    return None
```

### 3. WDLAdapter.extract_schema

```python
async def extract_schema(self, source, **kwargs):
    try:
        import WDL
        doc = WDL.load(source)
        return self._doc_to_schema(doc)
    except Exception:
        return None
```

### 4. SchemaExtractor (统一入口)

```python
# engine/schema_extractor.py
class SchemaExtractor:
    async def extract(self, engine: str, source: str, **kwargs) -> dict:
        adapter = get_adapter(engine)
        schema = await adapter.extract_schema(source, **kwargs)
        if schema and schema.get("tasks"):
            return schema
        # Fallback: regex (if content provided)
        content = kwargs.get("content")
        if content:
            validator = WorkflowValidator()
            result = validator.validate(content, engine)
            return result.to_schema_json()
        return {"tasks": [], "dependencies": [], "inputs": [], "outputs": []}
```

### 5. DagMatcher (模糊匹配)

```python
# utils/dag_matcher.py
class DagMatcher:
    def __init__(self, dag_nodes: list[dict]):
        self._nodes = {n["id"]: n for n in dag_nodes}

    def match(self, runtime_task_name: str) -> str | None:
        cleaned = clean_process_label(runtime_task_name)
        target_id = normalize_dag_id(cleaned)

        # 1. Exact ID match
        if target_id in self._nodes: return target_id

        # 2. Label match (case-insensitive)
        for nid, node in self._nodes.items():
            label = node.get("data", {}).get("label", "")
            if label.lower() == cleaned.lower(): return nid

        # 3. Suffix match (handles "WORKFLOW:MODULE:PROCESS")
        parts = cleaned.split(":")
        if len(parts) > 1:
            suffix_id = normalize_dag_id(parts[-1])
            if suffix_id in self._nodes: return suffix_id

        # 4. Substring containment
        for nid in self._nodes:
            if target_id in nid or nid in target_id: return nid

        return None
```

### 6. 运行时 DAG 动态构建

当 schema 为空时，从 task events 自动构建节点:

```python
# utils/dag_builder.py (扩展)
def create_runtime_node(task_name: str, status: str, existing_dag: dict) -> dict:
    """创建一个运行时发现的 DAG 节点."""
    node_id = normalize_dag_id(clean_process_label(task_name))
    # 自动计算位置 (追加到最后一行)
    y = len(existing_dag.get("nodes", [])) * NODE_Y_SPACING + NODE_Y_OFFSET
    return {
        "id": node_id,
        "type": "pipeline",
        "position": {"x": NODE_X_OFFSET, "y": y},
        "data": {
            "label": clean_process_label(task_name),
            "displayLabel": clean_process_label(task_name),
            "status": status,
            "source": "runtime",  # 标注来源
        },
    }

def infer_runtime_edge(dag: dict, new_node_id: str) -> None:
    """基于执行顺序推断边 (简单: 前一个节点 → 新节点)."""
    nodes = dag.get("nodes", [])
    if len(nodes) >= 2:
        prev_id = nodes[-2]["id"]
        edge_id = f"e_{prev_id}_{new_node_id}"
        if not any(e["id"] == edge_id for e in dag.get("edges", [])):
            dag.setdefault("edges", []).append({
                "id": edge_id, "source": prev_id, "target": new_node_id, "animated": True,
            })
```

### 7. jobs.py 中使用 DagMatcher

```python
# runtime/jobs.py _handle_engine_event 修改
if event.type == EngineEventType.TASK_UPDATE:
    matcher = DagMatcher(dag.get("nodes", []))
    matched_id = matcher.match(event.task_name)
    if matched_id:
        _update_node_status(dag, matched_id, event.task_status)
    else:
        # 动态创建节点
        new_node = create_runtime_node(event.task_name, event.task_status, dag)
        dag["nodes"].append(new_node)
        infer_runtime_edge(dag, new_node["id"])
```

### 8. WorkflowValidator 简化

```python
class WorkflowValidator:
    async def validate_and_extract(self, content, engine, file_name=None):
        syntax = self._validate_syntax(content, engine)  # 快速正则检查
        if not syntax.valid: return syntax
        extractor = SchemaExtractor()
        schema = await extractor.extract(engine, source=None, content=content)
        syntax.tasks = [WorkflowTask(**t) for t in schema.get("tasks", [])]
        syntax.dependencies = [WorkflowDependency(**d) for d in schema.get("dependencies", [])]
        return syntax
```

## 测试计划

```
backend/tests/test_engine/
└── test_schema_extractor.py

backend/tests/test_utils/
├── test_dag_matcher.py
└── test_dag_builder_runtime.py
```

### 关键测试用例

1. **DagMatcher**:
   - `"FASTQC"` → exact match ✓
   - `"nf-core/viralrecon:FASTQC"` → suffix match ✓
   - `"FASTQC (sample1)"` → cleaned match ✓
   - `"UNKNOWN"` → None

2. **运行时 DAG 构建**:
   - 空 schema + 3 task events → 3 nodes + 2 edges
   - 节点标注 `source: "runtime"`

3. **SchemaExtractor**: 引擎工具失败 → regex fallback

4. **DagMatcher 在 jobs.py 中**: 无 schema + task events → DAG 动态生长

## 验收标准

- [ ] nf-core 管线注册后有非空 schema_json
- [ ] 无 schema 时运行时动态构建 DAG
- [ ] DagMatcher 模糊匹配通过所有用例
- [ ] Runtime 节点标注 `source: "runtime"` (区分 schema vs runtime)
- [ ] 新代码覆盖率 ≥ 80%
