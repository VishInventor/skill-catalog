# Phase 3: Ontology
**Skill:** `databricks-full-discovery` | **Version:** 1.0.0 | **Author:** Vishal Anand
**Phase:** 3 of 3 — Final Phase | **Entry Condition:** Full discovery completed (Phase 2 gate passed)

---

## 1. PURPOSE

Phase 3 is the synthesis and visualization layer of the `databricks-full-discovery` skill. Having completed connectivity validation in Phase 1 and exhaustive asset enumeration in Phase 2, this phase transforms raw discovery data — workspaces, Unity Catalog hierarchies, medallion layers, ingestion pipelines, compute clusters, SQL warehouses, dashboards, and AI/BI agents — into a structured, Palantir-style ontology. The ontology is not merely a diagram; it is a formal, typed object model where every Databricks asset becomes a first-class entity with defined properties, relationships, and dependency edges. This creates the authoritative "single pane of glass" that stakeholders — architects, data engineers, platform owners, and security teams — can reason over without needing direct Databricks console access.

Without this phase, the discovery output remains a flat, unstructured inventory that cannot communicate causal relationships: which pipeline feeds which catalog layer, which cluster powers which dashboard, which external source system is the origin of which medallion Bronze table. Decision-makers cannot assess blast radius of a cluster shutdown, cannot trace data lineage end-to-end, and cannot plan migrations or cost optimizations without manually re-deriving the connections Phase 3 makes explicit. The draw.io artifact produced here becomes the deliverable that governance, architecture review boards, and audit processes consume directly.

This phase also enforces completeness: the act of drawing the ontology exposes gaps (orphaned assets, unknown source systems, pipelines with no downstream consumers) that Phase 2 catalogued but did not flag as anomalies. Entities that cannot be connected to the ontology graph are surfaced as unresolved nodes, prompting remediation or deliberate exclusion with documented rationale. The final draw.io file saved to the Desktop is the contractual output of the entire skill run.

---

## 2. KEY ACTIVITIES

- **Define the Ontology Schema (Entity Types and Relationship Types):** Before drawing, formalize the object type model. Entity types include: `DatabricksWorkspace`, `UnityCatalog`, `Schema`, `Table` (subtyped as `BronzeTable`, `SilverTable`, `GoldTable`), `ExternalSourceSystem`, `DLTPipeline`, `IngestionPipeline` (e.g., Autoloader, COPY INTO, Kafka), `InteractiveCluster`, `JobCluster`, `SQLWarehouse`, `Dashboard`, `AIBIAgent`, `DatabricksJob`, `DatabricksWorkflow`, `ExternalLocation`, `StorageCredential`, `ServicePrincipal`. Relationship types include: `FEEDS`, `READS_FROM`, `WRITES_TO`, `DEPENDS_ON`, `RUNS_ON`, `OWNED_BY`, `GOVERNED_BY`, `INGESTS_FROM`, `EXPOSES`, `TRIGGERS`, `PART_OF`.

- **Load Phase 2 Discovery Inventory into Structured Memory:** Ingest all Phase 2 output files (JSON discovery dumps, CSV asset inventories) into an in-memory graph structure. Each discovered asset from Phase 2 — workspace IDs, catalog names, cluster IDs, pipeline IDs, warehouse IDs, dashboard IDs, agent IDs — must be mapped to an ontology entity instance with its properties populated (e.g., `DatabricksWorkspace.workspace_id`, `DatabricksWorkspace.url`, `DatabricksWorkspace.region`, `DatabricksWorkspace.sku`).

- **Resolve Medallion Layer Membership for All Tables:** For each table discovered in Unity Catalog, classify it as Bronze, Silver, or Gold by inspecting table tags (`layer` tag), schema name conventions (e.g., `bronze_`, `silver_`, `gold_`), Delta Live Tables pipeline membership (`pipeline_id` in table properties), and column patterns (raw `_ingest_time`, `_source_file` columns = Bronze). Assign the correct `Table` subtype and annotate the medallion progression chain (`BronzeTable -FEEDS-> SilverTable -FEEDS-> GoldTable`).

- **Map Data Ingestion Pipelines to Source Systems:** For each `IngestionPipeline` entity (Autoloader jobs, DLT Bronze pipelines, JDBC batch jobs, Kafka streaming jobs), extract the source configuration — S3/ADLS/GCS paths, JDBC connection strings, Kafka bootstrap servers, external Delta Sharing endpoints — and create or link an `ExternalSourceSystem` entity. Draw `ExternalSourceSystem -INGESTS_FROM-> IngestionPipeline -WRITES_TO-> BronzeTable` relationship chains.

- **Link Compute Resources to Their Consumers:** For every `InteractiveCluster` and `JobCluster`, identify attached notebooks, jobs, and workflows from Phase 2 data. For every `SQLWarehouse`, identify which dashboards and AI/BI agents query it (via warehouse_id references in dashboard datasource configs and agent endpoint configs). Draw `DatabricksJob -RUNS_ON-> JobCluster`, `Dashboard -RUNS_ON-> SQLWarehouse`, `AIBIAgent -RUNS_ON-> SQLWarehouse` edges.

- **Construct the Dependency Graph and Detect Cycles/Orphans:** Build a directed acyclic graph (DAG) of all `FEEDS`, `DEPENDS_ON`, and `TRIGGERS` relationships. Run cycle detection (DFS with coloring) — any detected cycle must be flagged as an anomaly node in the diagram (red border, warning label). Identify orphan nodes: entities with no inbound or outbound edges. Orphans are rendered as isolated nodes with a dashed border and tagged `UNRESOLVED`.

- **Generate the draw.io XML Ontology Diagram:** Programmatically generate the draw.io `.drawio` XML file. Use a layered, left-to-right layout: `ExternalSourceSystems` on the far left, `IngestionPipelines` next, `BronzeLayer` → `SilverLayer` → `GoldLayer` in the center medallion swim lane, then `SQLWarehouses`, `Compute`, `Dashboards`, and `AIBIAgents` on the right. Apply Palantir-style visual language: entity types have distinct shape styles (rectangles with rounded corners for data assets, hexagons for compute, diamonds for pipelines, cylinders for storage), color-coded by entity type, relationship edges labeled with the relationship type name.

- **Save the Diagram File to Desktop and Generate Ontology Summary Report:** Write the final `.drawio` file to `~/Desktop/databricks_ontology_<workspace_name>_<timestamp>.drawio`. Additionally produce a companion Markdown summary (`databricks_ontology_summary_<timestamp>.md`) on the Desktop enumerating: total entity count by type, total relationship count by type, list of orphan nodes, list of detected anomalies (cycles, missing source systems, unresolved pipelines), and a human-readable legend of the ontology schema used.

---

## 3. TECHNICAL GUIDANCE

### 3.1 Ontology Schema Definition (Python Dataclasses)

```python
from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum

class EntityType(Enum):
    WORKSPACE = "DatabricksWorkspace"
    UNITY_CATALOG = "UnityCatalog"
    SCHEMA = "Schema"
    BRONZE_TABLE = "BronzeTable"
    SILVER_TABLE = "SilverTable"
    GOLD_TABLE = "GoldTable"
    EXTERNAL_SOURCE = "ExternalSourceSystem"
    DLT_PIPELINE = "DLTPipeline"
    INGESTION_PIPELINE = "IngestionPipeline"
    INTERACTIVE_CLUSTER = "InteractiveCluster"
    JOB_CLUSTER = "JobCluster"
    SQL_WAREHOUSE = "SQLWarehouse"
    DASHBOARD = "Dashboard"
    AIBI_AGENT = "AIBIAgent"
    JOB = "DatabricksJob"
    WORKFLOW = "DatabricksWorkflow"
    EXTERNAL_LOCATION = "ExternalLocation"
    SERVICE_PRINCIPAL = "ServicePrincipal"

class RelationshipType(Enum):
    FEEDS = "FEEDS"
    READS_FROM = "READS_FROM"
    WRITES_TO = "WRITES_TO"
    DEPENDS_ON = "DEPENDS_ON"
    RUNS_ON = "RUNS_ON"
    OWNED_BY = "OWNED_BY"
    GOVERNED_BY = "GOVERNED_BY"
    INGESTS_FROM = "INGESTS_FROM"
    EXPOSES = "EXPOSES"
    TRIGGERS = "TRIGGERS"
    PART_OF = "PART_OF"

@dataclass
class OntologyEntity:
    id: str                      # Unique: e.g., "workspace:adb-1234567890"
    entity_type: EntityType
    label: str                   # Human-readable display name
    properties: dict             # Key-value pairs from Phase 2 discovery
    anomaly: bool = False
    unresolved: bool = False

@dataclass
class OntologyRelationship:
    source_id: str
    target_id: str
    relationship_type: RelationshipType
    properties: dict = field(default_factory=dict)
```

### 3.2 Table Classification Logic

```python
def classify_table(table_meta: dict) -> EntityType:
    """Classify a Unity Catalog table into Bronze/Silver/Gold."""
    tags = table_meta.get("table_tags", {})
    schema_name = table_meta.get("schema_name", "").lower()
    table_props = table_meta.get("table_properties", {})
    columns = [c["name"].lower() for c in table_meta.get("columns", [])]

    # Priority 1: Explicit tag
    if tags.get("layer", "").lower() == "bronze":
        return EntityType.BRONZE_TABLE
    if tags.get("layer", "").lower() == "silver":
        return EntityType.SILVER_TABLE
    if tags.get("layer", "").lower() == "gold":
        return EntityType.GOLD_TABLE

    # Priority 2: Schema naming convention
    for prefix in ["bronze", "raw", "landing", "ingest"]:
        if schema_name.startswith(prefix):
            return EntityType.BRONZE_TABLE
    for prefix in ["silver", "cleansed", "conformed", "standardized"]:
        if schema_name.startswith(prefix):
            return EntityType.SILVER_TABLE
    for prefix in ["gold", "curated", "serving", "mart", "agg"]:
        if schema_name.startswith(prefix):
            return EntityType.GOLD_TABLE

    # Priority 3: Column fingerprinting
    bronze_signals = {"_ingest_time", "_source_file", "_rescued_data",
                      "_commit_timestamp", "raw_payload"}
    if bronze_signals.intersection(set(columns)):
        return EntityType.BRONZE_TABLE

    # Priority 4: DLT pipeline_id property
    if "pipeline_id" in table_props:
        # DLT-managed without layer tag — default Bronze
        return EntityType.BRONZE_TABLE

    # Default: treat as unclassified Silver (conservative)
    return EntityType.SILVER_TABLE
```

### 3.3 Databricks REST API Calls to Enrich Relationships (Phase 2 Data Supplement)

```bash
# Get DLT pipeline details including source datasets and target tables
curl -X GET "https://<workspace-url>/api/2.0/pipelines/<pipeline_id>" \
  -H "Authorization: Bearer $DATABRICKS_TOKEN" | jq '.spec.libraries[].notebook.path, .spec.target'

# Get SQL warehouse assigned to a dashboard (Lakeview)
curl -X GET "https://<workspace-url>/api/2.0/lakeview/dashboards/<dashboard_id>" \
  -H "Authorization: Bearer $DATABRICKS_TOKEN" | jq '.warehouse_id, .display_name'

# Get AI/BI Genie space with associated warehouse
curl -X GET "https://<workspace-url>/api/2.0/genie/spaces" \
  -H "Authorization: Bearer $DATABRICKS_TOKEN" | jq '.spaces[] | {id, title, warehouse_id}'

# Get cluster details for job cluster assignment
curl -X GET "https://<workspace-url>/api/2.1/jobs/<job_id>" \
  -H "Authorization: Bearer $DATABRICKS_TOKEN" | jq '.settings.job_clusters[].new_cluster'

# Get Unity Catalog lineage for a specific table
curl -X GET "https://<workspace-url>/api/2.0/lineage-tracking/table-lineage" \
  -H "Authorization: Bearer $DATABRICKS_TOKEN" \
  -d '{"table_name": "catalog.schema.table", "include_entity_lineage": true}'
```

### 3.4 Unity Catalog Lineage SQL (via SQL Warehouse)

```sql
-- Query system tables for column-level lineage to map table-to-table FEEDS relationships
SELECT
    source_table_full_name,
    target_table_full_name,
    COUNT(*) AS column_mappings
FROM system.access.column_lineage
WHERE event_date >= CURRENT_DATE - INTERVAL 90 DAYS
GROUP BY source_table_full_name, target_table_full_name
ORDER BY column_mappings DESC;

-- Identify tables with no downstream consumers (leaf Gold tables or orphans)
SELECT t.full_name
FROM system.information_schema.tables t
LEFT JOIN system.access.column_lineage cl
    ON t.full_name = cl.source_table_full_name
WHERE cl.source_table_full_name IS NULL
  AND t.table_type = 'MANAGED';

-- Find external locations backing Bronze tables (source traceability)
SELECT
    t.full_name AS table_name,
    t.storage_location,
    el.name AS external_location_name,
    el.url AS external_location_url
FROM system.information_schema.tables t
JOIN system.information_schema.external_locations el
    ON t.storage_location LIKE el.url || '%'
WHERE t.table_type = 'EXTERNAL';
```

### 3.5 draw.io XML Generation (Python)

```python
import xml.etree.ElementTree as ET
from datetime import datetime
import os

# Visual style constants — Palantir-inspired color palette
ENTITY_STYLES = {
    EntityType.WORKSPACE:           "rounded=1;fillColor=#1B3A5C;fontColor=#FFFFFF;strokeColor=#0D2137;",
    EntityType.UNITY_CATALOG:       "rounded=1;fillColor=#2E6DA4;fontColor=#FFFFFF;strokeColor=#1B4F7A;",
    EntityType.SCHEMA:              "rounded=1;fillColor=#4A90D9;fontColor=#FFFFFF;strokeColor=#2E6DA4;",
    EntityType.BRONZE_TABLE:        "rounded=1;fillColor=#CD7F32;fontColor=#FFFFFF;strokeColor=#8B5A20;",
    EntityType.SILVER_TABLE:        "rounded=1;fillColor=#A8A9AD;fontColor=#000000;strokeColor=#6B6C6F;",
    EntityType.GOLD_TABLE:          "rounded=1;fillColor=#D4AF37;fontColor=#000000;strokeColor=#9B7D1F;",
    EntityType.EXTERNAL_SOURCE:     "shape=cylinder3;fillColor=#2D6A2D;fontColor=#FFFFFF;strokeColor=#1A4A1A;",
    EntityType.DLT_PIPELINE:        "shape=rhombus;fillColor=#8B1A8B;fontColor=#FFFFFF;strokeColor=#5A0F5A;",
    EntityType.INGESTION_PIPELINE:  "shape=rhombus;fillColor=#6A2D8B;fontColor=#FFFFFF;strokeColor=#3D1A5A;",
    EntityType.INTERACTIVE_CLUSTER: "shape=hexagon;fillColor=#1A5C8B;fontColor=#FFFFFF;strokeColor=#0D3A5C;",
    EntityType.JOB_CLUSTER:         "shape=hexagon;fillColor=#0D3A5C;fontColor=#FFFFFF;strokeColor=#091F33;",
    EntityType.SQL_WAREHOUSE:       "shape=hexagon;fillColor=#2D5A8B;fontColor=#FFFFFF;strokeColor=#1A3A5C;",
    EntityType.DASHBOARD:           "rounded=1;fillColor=#2D8B5A;fontColor=#FFFFFF;strokeColor=#1A5A3A;",
    EntityType.AIBI_AGENT:          "rounded=1;fillColor=#8B2D2D;fontColor=#FFFFFF;strokeColor=#5A1A1A;",
    EntityType.JOB:                 "rounded=1;fillColor=#5A5A8B;fontColor=#FFFFFF;strokeColor=#3A3A5C;",
    EntityType.EXTERNAL_LOCATION:   "shape=cylinder3;fillColor=#3A5C2D;fontColor=#FFFFFF;strokeColor=#1A3A0D;",
    EntityType.SERVICE_PRINCIPAL:   "shape=mxgraph.basic.person;fillColor=#5C3A2D;fontColor=#FFFFFF;strokeColor=#3A1A0D;",
}

EDGE_STYLE = "edgeStyle=orthogonalEdgeStyle;rounded=1;strokeColor=#666666;fontSize=9;labelBackgroundColor=#FFFFFF;"

def generate_drawio_xml(entities: list, relationships: list, workspace_name: str) -> str:
    root = ET.Element("mxGraphModel")
    root.set("dx", "1422"); root.set("dy", "762"); root.set("grid", "1")
    root.set("gridSize", "10"); root.set("guides", "1"); root.set("tooltips", "1")
    root.set("connect", "1"); root.set("arrows", "1"); root.set("fold", "1")

    parent = ET.SubElement(root, "root")
    ET.SubElement(parent, "mxCell", id="0")
    ET.SubElement(parent, "mxCell", id="1", parent="0")

    # Add title cell
    title_cell = ET.SubElement(parent, "mxCell",
        id="title", value=f"Databricks Ontology — {workspace_name} — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        style="text;html=1;fontSize=18;fontStyle=1;align=center;",
        vertex="1", parent="1")
    ET.SubElement(title_cell, "mxGeometry", x="0", y="-60", width="1400", height="40", **{"as": "geometry"})

    # Layout: assign x positions by entity type layer
    x_positions = {
        EntityType.EXTERNAL_SOURCE: 0, EntityType.EXTERNAL_LOCATION: 0,
        EntityType.INGESTION_PIPELINE: 220, EntityType.DLT_PIPELINE: 220,
        EntityType.BRONZE_TABLE: 440,
        EntityType.SILVER_TABLE: 660,
        EntityType.GOLD_TABLE: 880,
        EntityType.SQL_WAREHOUSE: 1100, EntityType.INTERACTIVE_CLUSTER: 1100, EntityType.JOB_CLUSTER: 1100,
        EntityType.DASHBOARD: 1320, EntityType.AIBI_AGENT: 1320, EntityType.JOB: 1320,
        EntityType.WORKSPACE: 660, EntityType.UNITY_CATALOG: 660, EntityType.SCHEMA: 660,
        EntityType.SERVICE_PRINCIPAL: 0,
    }
    y_counters = {etype: 0 for etype in EntityType}

    entity_cell_map = {}
    for entity in entities:
        etype = entity.entity_type
        x = x_positions.get(etype, 660)
        y = y_counters[etype]
        y_counters[etype] += 90

        style = ENTITY_STYLES.get(etype, "rounded=1;")
        if entity.anomaly:
            style += "strokeColor=#FF0000;strokeWidth=3;"
        if entity.unresolved:
            style += "dashed=1;strokeColor=#FF9900;"

        cell = ET.SubElement(parent, "mxCell",
            id=entity.id, value=f"<b>{entity.label}</b><br/><i>{etype.value}</i>",
            style=style + "html=1;", vertex="1", parent="1")
        ET.SubElement(cell, "mxGeometry", x=str(x), y=str(y), width="180", height="60", **{"as": "geometry"})
        entity_cell_map[entity.id] = entity

    for i, rel in enumerate(relationships):
        edge = ET.SubElement(parent, "mxCell",
            id=f"edge_{i}", value=rel.relationship_type.value,
            style=EDGE_STYLE, edge="1", source=rel.source_id, target=rel.target_id, parent="1")
        ET.SubElement(edge, "mxGeometry", relative="1", **{"as": "geometry"})

    return ET.tostring(root, encoding="unicode", xml_declaration=True)

def save_drawio_to_desktop(xml_content: str, workspace_name: str):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = workspace_name.replace(" ", "_").replace("/", "-")
    filename = f"databricks_ontology_{safe_name}_{timestamp}.drawio"
    desktop_path = os.path.join(os.path.expanduser("~"), "Desktop", filename)
    with open(desktop_path, "w", encoding="utf-8") as f:
        f.write(xml_content)
    return desktop_path
```

### 3.6 Cycle Detection in Dependency Graph

```python
from collections import defaultdict

def detect_cycles(relationships: list) -> list:
    """Returns list of entity IDs involved in cycles."""
    graph = defaultdict(list)
    for rel in relationships:
        if rel.relationship_type in [RelationshipType.FEEDS, RelationshipType.DEPENDS_ON, RelationshipType.TRIGGERS]:
            graph[rel.source_id].append(rel.target_id)

    WHITE, GRAY, BLACK = 0, 1, 2
    color = defaultdict(int)
    cycle_nodes = set()

    def dfs(node):
        color[node] = GRAY
        for neighbor in graph[node]:
            if color[neighbor] == GRAY:
                cycle_nodes.add(node)
                cycle_nodes.add(neighbor)
            elif color[neighbor] == WHITE:
                dfs(neighbor)
        color[node] = BLACK

    for node in list(graph.keys()):
        if color[node] == WHITE:
            dfs(node)
    return list(cycle_nodes)
```

---

## 4. DECISION LOGIC

**IF** Phase 2 discovery output JSON files are present and non-empty AND the `phase2_gate_passed` flag is `true` in the discovery state file:
- **THEN** proceed with ontology construction using all discovered assets.

**IF** Phase 2 output is present but the `phase2_gate_passed` flag is `false` (partial discovery):
- **THEN** load available data but mark all entities from failed discovery sub-domains as `unresolved=True`. Log a warning in the ontology summary report. Do NOT abort Phase 3 — generate the best-effort ontology with explicit `PARTIAL DISCOVERY` watermark on the diagram.

**IF** a table cannot be classified as Bronze/Silver/Gold after all four classification heuristics (tag → schema name → column fingerprint → DLT membership):
- **THEN** assign `EntityType.SILVER_TABLE` as the conservative default AND set `unresolved=True` AND add a note property `classification_source: "default_fallback"`.

**IF** a pipeline entity exists in Phase 2 data but its source `ExternalSourceSystem` cannot be resolved (e.g., connection string is encrypted, JDBC URL missing):
- **THEN** create a placeholder `ExternalSourceSystem` entity with `label="UNKNOWN SOURCE"`, `unresolved=True`, and draw the `INGESTS_FROM` edge to it with a dashed, orange edge style. Do NOT skip the pipeline entity.

**IF** cycle detection returns one or more node IDs:
- **THEN** set `anomaly=True` on all implicated entities, render them with red borders in the diagram, add an `ANOMALY: CIRCULAR DEPENDENCY` label to the connecting edges, and include the cycle in the summary report's anomaly section.

**IF** the Desktop directory does not exist or is not writable (e.g., running in a containerized environment):
- **THEN** fall back to saving the `.drawio` file to the current working directory AND `~/Documents/` AND log a `FILE_SAVE_FALLBACK` warning in the summary. Do NOT fail Phase 3 on file-path issues.

**IF** Unity Catalog lineage API returns no results for a table (lineage not tracked):
- **THEN** rely exclusively on Phase 2 pipeline-to-table mapping and DLT pipeline spec for relationship construction. Do NOT infer relationships from table names alone.

**IF** the total entity count exceeds 500 nodes:
- **THEN** generate two draw.io files: (a) a full detailed diagram, and (b) a condensed summary diagram grouping entities by type into swim lanes with counts, for readability.

---

## 5. DECISION GATE

> **DECISION GATE — Phase 3 Complete (Final Phase)**
>
> ALL must be true before marking the skill run as complete:
>
> - [ ] All Phase 2 entities (workspaces, catalogs, schemas, tables, pipelines, clusters, warehouses, dashboards, AI/BI agents) have been instantiated as typed `OntologyEntity` objects with at minimum `id`, `entity_type`, `label`, and one non-empty `properties` key
> - [ ] Every `BronzeTable`, `SilverTable`, and `GoldTable` entity has been classified via at least one of the four classification heuristics (tag, schema name, column fingerprint, DLT membership) — not left as raw `Table`
> - [ ] At minimum one `FEEDS` relationship exists connecting a Bronze entity to a Silver entity (confirms medallion chain resolution) — if none exists, the reason must be explicitly documented in the summary report
> - [ ] All `DLTPipeline` and `IngestionPipeline` entities have at least one inbound relationship (`INGESTS_FROM` or `READS_FROM`) and at least one outbound relationship (`WRITES_TO`) OR are marked `unresolved=True` with documented reason
> - [ ] All `Dashboard` and `AIBIAgent` entities have a `RUNS_ON` relationship pointing to a `SQLWarehouse` entity OR the warehouse_id is explicitly recorded as missing with `unresolved=True`
> - [ ] Cycle detection has been executed against the full dependency graph and results (even if empty) are recorded in the summary report
> - [ ] The `.drawio` file has been successfully written to `~/Desktop/` (or documented fallback path) and the file size is greater than 0 bytes
> - [ ] The companion Markdown summary report (`databricks_ontology_summary_<timestamp>.md`) exists on Desktop with all sections completed: entity counts, relationship counts, orphan list, anomaly list, legend
> - [ ] All orphan nodes (entities with zero inbound and zero outbound relationships) have been identified, listed in the summary, and rendered as dashed-border nodes in the diagram
> - [ ] The draw.io file opens without XML parse errors (validate by re-parsing the generated XML with `ET.fromstring()` before saving)
>
> **If not met — Remediation Steps:**
> - **Entity instantiation incomplete:** Re-run the Phase 2 JSON loader against each output file individually; log which files failed to parse and which entity types are missing; create placeholder entities for missing types with `unresolved=True`
> - **Medallion classification gap:** Manually inspect the Unity Catalog schema list from Phase 2; apply the schema-name heuristic with a broader regex (`.*bronze.*|.*raw.*|.*land.*`) and re-classify
> - **No FEEDS relationships:** Query `system.access.column_lineage` directly via SQL warehouse; if Unity Catalog lineage is disabled in the workspace, document this in the report and draw `FEEDS` edges based solely on DLT pipeline `source → target` specs
> - **Missing SQLWarehouse links for dashboards:** Re-run the Lakeview dashboard API call (`/api/2.0/lakeview/dashboards/<id>`) for each unlinked dashboard; if `warehouse_id` is null, mark as `unresolved=True`
> - **draw.io file not saved:** Check Desktop path resolution on OS; attempt fallback save to `~/Documents/` and current working directory; verify disk space is not exhausted
> - **XML parse error:** Print the generated XML to stdout, identify the malformed element (likely an unescaped `&`, `<`, or `>` in a label string), apply `html.escape()` to all `value` attributes before element creation, regenerate

---

## 6. OUTPUTS

| Output | Type | Location | Description |
|---|---|---|---|
| `databricks_ontology_<workspace>_<timestamp>.drawio` | draw.io XML File | `~/Desktop/` | Primary deliverable: Palantir-style ontology diagram with all discovered entities, typed relationships, color coding, anomaly flags, and medallion swim lanes |
| `databricks_ontology_summary_<timestamp>.md` | Markdown Report | `~/Desktop/` | Human-readable summary: entity counts by type, relationship counts by type, orphan node list, anomaly/cycle list, classification heuristic results, ontology schema legend, file paths |
| `ontology_graph_<timestamp>.json` | JSON Graph File | `~/Desktop/` | Machine-readable ontology: full list of `OntologyEntity` and `OntologyRelationship` objects serialized to JSON; consumable by downstream tools (Neo4j import, custom dashboards) |
| `ontology_state.json` | State File | Phase execution directory | Records `phase3_complete: true`, output file paths, entity/relationship counts, anomaly flags; used by the skill's state machine to confirm final phase completion |
| `phase3_execution.log` | Log File | Phase execution directory | Timestamped execution log capturing: Phase 2 data load results, classification decisions, relationship resolution steps, cycle detection output, file save confirmations, any `unresolved` or `anomaly` flags raised |

---

## 7. ANTI-PATTERNS

**Anti-Pattern 1: Drawing relationships from naming conventions alone without Phase 2 data validation.**
Inferring that a table named `silver_customer` is fed by `bronze_customer` purely because names match — without verifying an actual lineage record, DLT pipeline config, or column lineage entry — produces a diagram that looks correct but is architecturally fabricated. Architects making migration or deprecation decisions based on invented FEEDS edges will break production pipelines. Every relationship edge in the ontology must be traceable to a concrete Phase 2 data artifact or an API/SQL query result.

**Anti-Pattern 2: Collapsing all compute into a single "Cluster" entity type.**
Failing to distinguish `InteractiveCluster` (shared, always-on, attached to notebooks and ad-hoc queries) from `JobCluster` (ephemeral, job-scoped, cost-isolated) from `SQLWarehouse` (ANSI SQL endpoint for dashboards and BI tools) produces misleading compute dependency maps. A cost optimization analysis relying on this conflated diagram cannot identify which dashboards are driving SQL warehouse spend versus which engineering jobs are spawning ephemeral job clusters. Use the full entity type hierarchy from the schema definition.

**Anti-Pattern 3: Skipping orphan and cycle analysis and rendering a "clean" diagram.**
Omitting cycle detection and orphan identification makes the ontology diagram actively dangerous: it presents a false impression of a well-connected, dependency-clean Databricks environment. In reality, orphaned pipelines are likely broken or abandoned (wasting compute cost), and circular dependencies in workflow triggers cause unpredictable execution behavior. The Palantir ontology philosophy requires that the diagram represent ground truth — including anomalies — not an idealized architecture. Suppressing anomalies to produce a visually clean diagram defeats the entire purpose of the discovery skill.

**Anti-Pattern 4: Generating a static screenshot instead of a native draw.io XML file.**
Exporting the diagram as a PNG or PDF loses all the interactivity, layering, grouping, and editability that make draw.io diagrams valuable for architecture review sessions. Stakeholders need to collapse/expand entity groups, filter by relationship type, and annotate the diagram in review meetings. Always produce the native `.drawio` XML format; screenshots may be generated as an addendum but never as the primary deliverable.

---

## 8. AGENT INSTRUCTIONS

1. **Verify