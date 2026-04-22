# Plan 05 — DAG 解析兼容性

**依赖**: plan-01 (引擎抽象)
**被依赖**: 无 (可独立交付)

## 目标

提升新注册流程的 DAG 解析准确性，改善运行时节点状态匹配，减少"节点无法匹配"的情况。

## 当前问题回顾

1. **WorkflowValidator** 基于单文件正则，无法处理 DSL2 `include` 和多文件管线
2. **nf-core/github 来源**的管线没有 `schema_json` → 初始 DAG 为空
3. **运行时匹配**依赖 `clean_process_label()` + `normalize_dag_id()`，只处理两种模式
4. **schema_json** 格式没有版本管理

## 新增/修改文件

```
backend/app/engine/
├── schema_extractor.py    # 统一的 schema 提取器 (替代部分 WorkflowValidator)
└── adapters/
    ├── nextflow.py        # 增加 inspect + nf-core schema 能力
    └── wdl.py             # 增加 miniwdl check 能力

backend/app/utils/
├── dag_builder.py         # 增强节点匹配逻辑
└── dag_matcher.py         # 新: 模糊匹配 + 别名映射

backend/app/services/
└── workflow_validator.py  # 重构: 委托给引擎 adapter
```

## 详细设计

### 1. SchemaExtractor (统一提取器)

```python
# engine/schema_extractor.py

class SchemaExtractor:
    """统一的 workflow schema 提取。优先使用引擎工具，正则作为 fallback."""

    async def extract(self, engine: str, source: str, **kwargs) -> dict:
        """Extract schema from a workflow source.

        Args:
            engine: "nextflow" or "wdl"
            source: file path, pipeline name, or github URL

        Returns:
            schema_json dict with tasks, dependencies, inputs, outputs
        """
        adapter = get_adapter(engine)
        # 优先: 引擎原生工具
        schema = await adapter.extract_schema(source, **kwargs)
        if schema and schema.get("tasks"):
            return schema
        # Fallback: 正则解析 (如果有文件内容)
        content = kwargs.get("content")
        if content:
            return self._regex_fallback(engine, content)
        return {"tasks": [], "dependencies": [], "inputs": [], "outputs": []}
```

### 2. NextflowAdapter Schema 增强

```python
# engine/adapters/nextflow.py (扩展)
class NextflowAdapter(EngineAdapter):
    async def extract_schema(self, source: str, **kwargs) -> dict | None:
        """Try multiple strategies to extract pipeline schema."""
        # Strategy 1: nf-core schema (for nf-core pipelines)
        if self._is_nfcore_pipeline(source):
            schema = await self._fetch_nfcore_schema(source)
            if schema:
                return schema

        # Strategy 2: nextflow inspect (for local/github pipelines)
        # `nextflow inspect` outputs process/channel info as JSON
        schema = await self._run_nextflow_inspect(source)
        if schema:
            return schema

        # Strategy 3: parse -with-dag output (if available)
        dag_dot = kwargs.get("dag_dot_content")
        if dag_dot:
            return self._parse_dag_dot(dag_dot)

        return None

    async def _fetch_nfcore_schema(self, pipeline_name: str) -> dict | None:
        """Fetch schema from nf-core API or local cache."""
        # nf-core pipelines have a nextflow_schema.json in their repo
        # Can be fetched from: https://raw.githubusercontent.com/nf-core/{name}/master/nextflow_schema.json
        # Or via: nf-core schema lint (if nf-core tools installed)
        pass

    async def _run_nextflow_inspect(self, source: str) -> dict | None:
        """Run 'nextflow inspect' to get pipeline structure."""
        # nextflow inspect outputs JSON with processes, channels
        # Available in Nextflow 23.10+
        cmd = [self.bin, "inspect", source]
        # ... parse output ...
        pass
```

### 3. WDLAdapter Schema 增强

```python
# engine/adapters/wdl.py (扩展)
class WDLAdapter(EngineAdapter):
    async def extract_schema(self, source: str, **kwargs) -> dict | None:
        """Use miniwdl to parse WDL and extract schema."""
        # Already using miniwdl in WorkflowValidator._validate_wdl()
        # This is a cleaner extraction without validation overhead
        try:
            import WDL
            doc = WDL.load(source)
            return self._wdl_doc_to_schema(doc)
        except Exception:
            return None
```

### 4. DagMatcher (模糊匹配)

```python
# utils/dag_matcher.py

class DagMatcher:
    """Improved DAG node matching with fuzzy logic."""

    def __init__(self, dag_nodes: list[dict]):
        self._nodes = {n["id"]: n for n in dag_nodes}
        self._label_index = self._build_label_index()

    def match(self, runtime_task_name: str) -> str | None:
        """Match a runtime task name to a DAG node ID.

        Strategy (in order):
        1. Exact ID match (after normalize)
        2. Label match (case-insensitive)
        3. Suffix match (strip workflow prefix)
        4. Fuzzy match (Levenshtein distance ≤ 2)
        """
        cleaned = clean_process_label(runtime_task_name)
        target_id = normalize_dag_id(cleaned)

        # 1. Exact match
        if target_id in self._nodes:
            return target_id

        # 2. Label match (case-insensitive comparison of display labels)
        cleaned_lower = cleaned.lower()
        for node_id, node in self._nodes.items():
            label = node.get("data", {}).get("label", "").lower()
            if label == cleaned_lower:
                return node_id

        # 3. Suffix match (handles "WORKFLOW:MODULE:PROCESS" → "PROCESS")
        parts = cleaned.split(":")
        if len(parts) > 1:
            suffix_id = normalize_dag_id(parts[-1])
            if suffix_id in self._nodes:
                return suffix_id

        # 4. Substring containment
        for node_id in self._nodes:
            if target_id in node_id or node_id in target_id:
                return node_id

        return None

    def _build_label_index(self) -> dict[str, str]:
        """Build lowercase label → node_id index."""
        index = {}
        for node_id, node in self._nodes.items():
            label = node.get("data", {}).get("label", "")
            index[label.lower()] = node_id
        return index
```

### 5. 运行时 DAG 动态构建

当 `schema_json` 为空 (nf-core/github 管线) 时，从运行时事件动态构建 DAG:

```python
# runtime/jobs.py (修改 _handle_engine_event)

async def _handle_engine_event(...):
    if event.type == EngineEventType.TASK_UPDATE:
        dag = run.config.get("dag", {"nodes": [], "edges": []})
        matcher = DagMatcher(dag.get("nodes", []))
        matched_id = matcher.match(event.task_name)

        if matched_id:
            # Update existing node
            _update_node_status(dag, matched_id, event.task_status)
        else:
            # Dynamic node creation (no schema → build from runtime)
            new_node = _create_runtime_node(event.task_name, event.task_status, dag)
            dag["nodes"].append(new_node)
            # Try to infer edges from task execution order
            _infer_runtime_edges(dag, new_node)

        run.config = {**run.config, "dag": dag}
```

### 6. WorkflowValidator 重构

将 schema 提取逻辑委托给 `SchemaExtractor`:

```python
# services/workflow_validator.py (简化)
class WorkflowValidator:
    def __init__(self):
        self._extractor = SchemaExtractor()

    async def validate_and_extract(self, content: str, engine: str, file_name: str | None = None) -> ValidationResult:
        """Validate syntax + extract schema in one pass."""
        # Step 1: Basic syntax validation (keep regex for quick checks)
        syntax_result = self._validate_syntax(content, engine)
        if not syntax_result.valid:
            return syntax_result

        # Step 2: Extract schema (delegates to engine adapter)
        schema = await self._extractor.extract(engine, source=None, content=content)
        syntax_result.tasks = [WorkflowTask(**t) for t in schema.get("tasks", [])]
        syntax_result.dependencies = [WorkflowDependency(**d) for d in schema.get("dependencies", [])]
        return syntax_result
```

## 测试计划

### 新增测试文件

```
backend/tests/test_engine/
├── test_schema_extractor.py   # 各引擎 schema 提取
└── (existing)

backend/tests/test_utils/
├── test_dag_matcher.py        # 模糊匹配测试
└── (existing)
```

### 关键测试用例

1. **DagMatcher.match**:
   - 精确匹配: `"FASTQC"` → `"fastqc"` ✓
   - 前缀剥离: `"nf-core/viralrecon:FASTQC"` → `"fastqc"` ✓
   - 后缀剥离: `"FASTQC (sample1)"` → `"fastqc"` ✓
   - 子串匹配: `"FASTQC_RAW"` 能匹配到 `"fastqc_raw_reads"` (如果存在)
   - 无匹配: `"UNKNOWN_PROCESS"` → None

2. **运行时动态 DAG**:
   - 空schema + 3个task事件 → DAG有3个节点
   - 按执行顺序推断 edges

3. **NextflowAdapter.extract_schema**:
   - nf-core pipeline name → schema with tasks
   - local .nf file → schema with processes and dependencies

4. **WDLAdapter.extract_schema**:
   - local .wdl file → schema with tasks and call dependencies

5. **SchemaExtractor fallback**:
   - 引擎工具失败 → 正则 fallback → 至少提取到 process/task 名称

## 验收标准

- [ ] nf-core 管线注册后有非空 schema_json
- [ ] 运行时无 schema 时能动态构建 DAG
- [ ] DagMatcher 模糊匹配通过所有测试用例
- [ ] WorkflowValidator 重构后现有测试通过
- [ ] 新代码覆盖率 ≥ 80%
