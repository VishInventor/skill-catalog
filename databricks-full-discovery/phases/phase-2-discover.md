# Phase 2: Discover

## Databricks Full Discovery — Phase Reference

**Skill:** `databricks-full-discovery` | **Version:** 1.0.0 | **Author:** Vishal Anand
**Preceded by:** Phase 1 — Pre-discovery | **Followed by:** Phase 3 — Ontology
**Entry Condition:** `Connectivity` gate must be GREEN from Phase 1

---

## 1. PURPOSE

Phase 2 is the operational core of this skill. Its purpose is to perform an exhaustive, structured enumeration of every significant resource running inside the target Databricks environment — workspaces, Unity Catalog objects, medallion pipeline layers, ingestion pipelines, interactive and job compute clusters, SQL Warehouses, Lakeview dashboards, and AI/BI Genie agents. Without this phase, Phase 3 (Ontology) has no raw material from which to construct a dependency graph; it would produce an empty or fabricated diagram. This phase transforms a confirmed network/API connection into a structured, machine-readable inventory that is both human-reviewable and graph-ingestible.

The discovery phase exists because Databricks environments grow organically and often lack a single control-plane view that covers all asset types simultaneously. Workspace administrators manage compute; data engineers own Delta Live Tables pipelines; analytics engineers own Unity Catalog schemas; BI developers publish dashboards; ML engineers register AI agents — none of these teams necessarily have visibility into each other's assets. A single agent executing this phase collapses that siloed reality into one coherent snapshot, providing ground truth that no single human operator typically holds.

Without a complete discovery run, downstream artifacts (the ontology diagram, dependency maps, cost attribution reports) are dangerously incomplete. Stakeholders relying on a partial inventory to make architectural decisions — such as deprecating a pipeline, migrating a compute tier, or decommissioning a catalog — risk cascading failures in production. Phase 2 exists precisely to prevent that risk by ensuring no asset category is skipped and every discovered object is recorded with enough metadata (IDs, states, owners, tags, lineage pointers) to be precisely located in Phase 3.

---

## 2. KEY ACTIVITIES

- **Enumerate all accessible Databricks Workspaces via the Account-level API.** Query `GET /api/2.0/accounts/{account_id}/workspaces` using the Databricks Account Console credentials established in Phase 1. Record `workspace_id`, `workspace_name`, `workspace_url`, `deployment_name`, `aws_region` or `azure_region`, `workspace_status`, and `creation_time` for every workspace returned. Flag any workspace not in `RUNNING` state for separate triage logging.

- **Inventory Unity Catalog Metastores, Catalogs, Schemas, and Tables.** For each workspace confirmed as reachable, authenticate to its Unity Catalog metastore and execute a recursive walk: `LIST CATALOGS` → for each catalog `LIST SCHEMAS IN <catalog>` → for each schema `SHOW TABLES IN <catalog>.<schema>`. Capture `catalog_name`, `catalog_type` (MANAGED / EXTERNAL / DELTASHARING), `schema_name`, `table_name`, `table_type` (MANAGED / EXTERNAL / VIEW / MATERIALIZED_VIEW / STREAMING_TABLE), `storage_location`, `owner`, `comment`, `created_at`, `updated_at`, and `properties`. Cross-reference with `INFORMATION_SCHEMA.TABLE_CONSTRAINTS` and `INFORMATION_SCHEMA.COLUMNS` to collect column-level lineage seeds.

- **Detect and classify Medallion layer membership for every table and schema.** Apply heuristic classification rules against catalog/schema/table names, tags (`layer` tag with values `bronze`, `silver`, `gold`), and Unity Catalog table properties. For objects that cannot be classified by name or tag, inspect the lineage graph via `GET /api/2.0/lineage-tracking/table-lineage` to determine upstream/downstream position. Record each object's assigned medallion layer (`BRONZE`, `SILVER`, `GOLD`, `UNCLASSIFIED`) in the discovery manifest.

- **Enumerate Delta Live Tables (DLT) Pipelines as the medallion orchestration layer.** Query `GET /api/2.0/pipelines` on each workspace. For every pipeline, capture: `pipeline_id`, `name`, `state` (RUNNING / IDLE / FAILED / DELETING), `cluster_id`, `libraries` (notebooks and files that define the pipeline), `target` catalog and schema, `continuous` flag, `channel` (CURRENT / PREVIEW), `last_update_id`, and `creator_user_name`. For each pipeline, further call `GET /api/2.0/pipelines/{pipeline_id}/updates` to retrieve the last 5 update events, capturing `update_id`, `state`, `start_time`, `duration`, and any `cause` for failures. Map each DLT pipeline to its corresponding medallion output schemas discovered in the previous activity.

- **Discover data ingestion pipelines — Auto Loader, COPY INTO, and external orchestration jobs.** Query `GET /api/2.1/jobs/list?expand_tasks=true` on each workspace and filter for jobs whose task type is `spark_python_task`, `notebook_task`, or `spark_submit_task`. Inspect task source code references (notebook paths, Python file paths) for the presence of `cloudFiles`, `COPY INTO`, `readStream`, `kafka`, `kinesis`, `eventhub`, `jdbc`, or third-party connector strings (Fivetran webhook URLs, Airbyte connection IDs embedded as job parameters). Record `job_id`, `job_name`, `task_key`, `source_type` (AUTOLOADER / COPY_INTO / KAFKA / JDBC / FIVETRAN / AIRBYTE / UNKNOWN), `schedule` (cron expression if present), `last_run_status`, and `creator_user_name`.

- **Inventory all running and recently active Compute clusters.** Call `GET /api/2.0/clusters/list` on each workspace. For each cluster, capture: `cluster_id`, `cluster_name`, `cluster_source` (UI / API / JOB / PIPELINE), `state` (RUNNING / TERMINATED / TERMINATING / PENDING), `cluster_type` (ALL_PURPOSE / JOB / PIPELINE), `driver_node_type_id`, `node_type_id`, `num_workers` or `autoscale` config, `spark_version`, `runtime_engine` (STANDARD / PHOTON), `autotermination_minutes`, `data_security_mode` (SINGLE_USER / USER_ISOLATION / NONE), `single_user_name`, `aws_attributes` or `azure_attributes`, `init_scripts`, `spark_conf`, `custom_tags`, `start_time`, and `terminated_time`. For TERMINATED clusters, only include those with `terminated_time` within the last 30 days to bound scope. Cross-reference each cluster's `cluster_id` against DLT pipeline cluster IDs and job cluster definitions to determine ownership.

- **Enumerate SQL Warehouses (Serverless and Classic).** Call `GET /api/2.0/sql/warehouses` on each workspace. For each warehouse, capture: `id`, `name`, `warehouse_type` (CLASSIC / PRO / SERVERLESS), `state` (RUNNING / STOPPED / STARTING / STOPPING / DELETING), `cluster_size`, `min_num_clusters`, `max_num_clusters`, `auto_stop_mins`, `channel` (CURRENT / PREVIEW), `enable_photon`, `spot_instance_policy`, `jdbc_url`, `creator_name`, and `tags`. Also call `GET /api/2.0/sql/warehouses/{warehouse_id}/config` to capture `data_access_config` entries (storage credentials and external data sources configured per warehouse).

- **Discover Lakeview Dashboards and AI/BI Genie Spaces.** For dashboards, call `GET /api/2.0/lakeview/dashboards` and capture `dashboard_id`, `display_name`, `path`, `status` (DRAFT / PUBLISHED), `warehouse_id` (backing compute), `update_time`, `create_time`, and `parent_path`. For each published dashboard, call `GET /api/2.0/lakeview/dashboards/{dashboard_id}` and parse `serialized_dashboard` to extract embedded dataset queries, which reveal which Unity Catalog tables or schemas the dashboard depends on. For AI/BI Genie agents, call `GET /api/2.0/genie/spaces` and capture `space_id`, `title`, `description`, `warehouse_id`, `table_identifiers` (the list of Unity Catalog tables the Genie space is authorized to query), `create_time`, `update_time`, and `creator_user_name`.

---

## 3. TECHNICAL GUIDANCE

### 3.1 — Account-Level Workspace Enumeration

```python
import requests
import json

ACCOUNT_ID = "<your_databricks_account_id>"
ACCOUNT_TOKEN = "<pat_or_oauth_token>"
BASE_URL = f"https://accounts.azuredatabricks.net/api/2.0/accounts/{ACCOUNT_ID}"
# For AWS: https://accounts.cloud.databricks.com/api/2.0/accounts/{ACCOUNT_ID}

headers = {"Authorization": f"Bearer {ACCOUNT_TOKEN}"}

resp = requests.get(f"{BASE_URL}/workspaces", headers=headers)
resp.raise_for_status()
workspaces = resp.json().get("workspaces", [])

workspace_inventory = []
for ws in workspaces:
    workspace_inventory.append({
        "workspace_id": ws["workspace_id"],
        "workspace_name": ws["workspace_name"],
        "workspace_url": f"https://{ws['deployment_name']}.azuredatabricks.net",
        "region": ws.get("location") or ws.get("aws_region"),
        "status": ws["workspace_status"],
        "creation_time": ws.get("creation_time")
    })

with open("discovery_workspaces.json", "w") as f:
    json.dump(workspace_inventory, f, indent=2)
```

### 3.2 — Unity Catalog Table Walk via SQL

```sql
-- Execute per workspace against its Unity Catalog metastore
-- Step 1: List all catalogs
SHOW CATALOGS;

-- Step 2: For each catalog, list schemas (parameterize <catalog_name>)
SHOW SCHEMAS IN <catalog_name>;

-- Step 3: Enumerate tables with full metadata
SELECT
  t.table_catalog,
  t.table_schema,
  t.table_name,
  t.table_type,
  t.storage_sub_directory,
  t.data_source_format,
  t.created,
  t.created_by,
  t.last_altered,
  t.last_altered_by,
  t.comment
FROM <catalog_name>.information_schema.tables t
ORDER BY t.table_catalog, t.table_schema, t.table_name;

-- Step 4: Capture table tags for medallion classification
SHOW TBLPROPERTIES <catalog_name>.<schema_name>.<table_name>;

-- Step 5: Check column-level lineage seeds
SELECT * FROM <catalog_name>.information_schema.columns
WHERE table_catalog = '<catalog_name>'
  AND table_schema = '<schema_name>'
  AND table_name = '<table_name>';
```

### 3.3 — Medallion Layer Classification Logic (Python)

```python
import re

BRONZE_PATTERNS = [r"\bbronze\b", r"\braw\b", r"\blanding\b", r"\bingest\b", r"\bstage\b"]
SILVER_PATTERNS = [r"\bsilver\b", r"\bcleansed\b", r"\bconformed\b", r"\btransform\b", r"\bnorm\b"]
GOLD_PATTERNS   = [r"\bgold\b", r"\bserving\b", r"\bagg\b", r"\bmart\b", r"\breport\b", r"\bpresent\b"]

def classify_medallion(catalog: str, schema: str, table: str, tags: dict) -> str:
    layer_tag = tags.get("layer", "").lower()
    if layer_tag in ("bronze", "silver", "gold"):
        return layer_tag.upper()
    
    full_path = f"{catalog}.{schema}.{table}".lower()
    for pattern in BRONZE_PATTERNS:
        if re.search(pattern, full_path): return "BRONZE"
    for pattern in SILVER_PATTERNS:
        if re.search(pattern, full_path): return "SILVER"
    for pattern in GOLD_PATTERNS:
        if re.search(pattern, full_path): return "GOLD"
    
    return "UNCLASSIFIED"
```

### 3.4 — DLT Pipeline Discovery

```python
def discover_dlt_pipelines(workspace_url, token):
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{workspace_url}/api/2.0/pipelines", headers=headers)
    pipelines = resp.json().get("statuses", [])
    
    result = []
    for p in pipelines:
        pipeline_id = p["pipeline_id"]
        # Fetch full pipeline spec
        detail = requests.get(
            f"{workspace_url}/api/2.0/pipelines/{pipeline_id}", 
            headers=headers
        ).json()
        # Fetch last 5 update events
        updates = requests.get(
            f"{workspace_url}/api/2.0/pipelines/{pipeline_id}/updates",
            headers=headers,
            params={"max_results": 5}
        ).json().get("updates", [])
        
        result.append({
            "pipeline_id": pipeline_id,
            "name": detail.get("name"),
            "state": p.get("state"),
            "target_catalog": detail.get("catalog"),
            "target_schema": detail.get("target"),
            "continuous": detail.get("continuous", False),
            "channel": detail.get("channel", "CURRENT"),
            "creator": detail.get("creator_user_name"),
            "libraries": [lib.get("notebook", {}).get("path") or 
                          lib.get("file", {}).get("path") 
                          for lib in detail.get("libraries", [])],
            "recent_updates": [
                {"update_id": u["update_id"], "state": u["state"],
                 "start_time": u.get("creation_time"), 
                 "cause": u.get("cause")} 
                for u in updates
            ]
        })
    return result
```

### 3.5 — SQL Warehouse Discovery with JDBC URL Capture

```bash
# Databricks CLI approach for warehouse enumeration
databricks warehouses list --output json | jq '
  .[] | {
    id: .id,
    name: .name,
    type: .warehouse_type,
    state: .state,
    size: .cluster_size,
    auto_stop_mins: .auto_stop_mins,
    photon: .enable_photon,
    jdbc_url: .jdbc_url
  }
'
```

### 3.6 — Lakeview Dashboard and Genie Space Discovery

```python
def discover_dashboards_and_genie(workspace_url, token):
    headers = {"Authorization": f"Bearer {token}"}
    
    # Dashboards
    dash_resp = requests.get(
        f"{workspace_url}/api/2.0/lakeview/dashboards",
        headers=headers,
        params={"page_size": 200}
    )
    dashboards = []
    for d in dash_resp.json().get("dashboards", []):
        detail = requests.get(
            f"{workspace_url}/api/2.0/lakeview/dashboards/{d['dashboard_id']}",
            headers=headers
        ).json()
        # Extract dataset queries from serialized_dashboard
        import json as _json
        try:
            dash_spec = _json.loads(detail.get("serialized_dashboard", "{}"))
            datasets = [ds.get("query", {}).get("text", "") 
                        for ds in dash_spec.get("datasets", [])]
        except Exception:
            datasets = []
        dashboards.append({
            "dashboard_id": d["dashboard_id"],
            "name": d["display_name"],
            "status": d.get("lifecycle_state"),
            "warehouse_id": detail.get("warehouse_id"),
            "embedded_queries": datasets,
            "update_time": d.get("update_time")
        })
    
    # Genie Spaces
    genie_resp = requests.get(
        f"{workspace_url}/api/2.0/genie/spaces",
        headers=headers
    )
    genie_spaces = []
    for g in genie_resp.json().get("spaces", []):
        genie_spaces.append({
            "space_id": g["space_id"],
            "title": g["title"],
            "warehouse_id": g.get("warehouse_id"),
            "tables": g.get("table_identifiers", []),
            "creator": g.get("creator_user_name"),
            "create_time": g.get("create_time")
        })
    
    return {"dashboards": dashboards, "genie_spaces": genie_spaces}
```

---

## 4. DECISION LOGIC

**IF** `GET /api/2.0/accounts/{account_id}/workspaces` returns HTTP 403,
**THEN** the account-level token used in Phase 1 lacks the `Account Admin` role. Do NOT proceed with workspace enumeration using this token. Attempt fallback to workspace-level PAT tokens for each known workspace URL from the Phase 1 connectivity manifest. Log the permission gap as a `DISCOVERY_WARNING` and annotate the discovery manifest with `account_scope: PARTIAL`.
**ELSE IF** the response is HTTP 200 but `workspaces` array is empty,
**THEN** the account may be a single-workspace deployment. Proceed using the single workspace URL from Phase 1 directly. Set `account_scope: SINGLE_WORKSPACE` in the manifest.

---

**IF** Unity Catalog is not enabled on a workspace (confirmed by `GET /api/2.0/unity-catalog/metastores` returning HTTP 404 or empty),
**THEN** fall back to Hive Metastore enumeration via `SHOW DATABASES` on the workspace's default Spark context. Tag all discovered databases and tables as `catalog_type: HIVE_METASTORE`. Set `unity_catalog_enabled: false` on that workspace record. Apply medallion classification heuristics to database/table names only (no tags available in Hive Metastore).
**ELSE** proceed with full Unity Catalog enumeration including `INFORMATION_SCHEMA` queries and lineage API calls.

---

**IF** a DLT pipeline is in `FAILED` state during discovery,
**THEN** still record it with `state: FAILED` and capture the `cause` from the most recent update event. Do NOT skip it. Flag it as `pipeline_health: DEGRADED` and include the failure `cause` string in the discovery manifest. Healthy pipelines get `pipeline_health: HEALTHY`; idle pipelines get `pipeline_health: IDLE`.
**ELSE IF** a pipeline is in `DELETING` state,
**THEN** include it with a `pipeline_health: DECOMMISSIONING` flag but mark it as lower-priority for ontology inclusion.

---

**IF** a cluster's `data_security_mode` is `NONE`,
**THEN** flag it as `governance_risk: HIGH` in the discovery manifest. This cluster can access all data in the workspace without Unity Catalog enforcement. Annotate the cluster record with a `governance_note: "Single-user or no-isolation mode — Unity Catalog row/column filters not enforced"` field.
**ELSE IF** `data_security_mode` is `SINGLE_USER`,
**THEN** record `single_user_name` and flag `governance_risk: MEDIUM`.
**ELSE** (`USER_ISOLATION`) flag `governance_risk: LOW`.

---

**IF** a job task references a notebook path that contains `cloudFiles`, `readStream`, or `COPY INTO`,
**THEN** classify the ingestion source as the appropriate type and attempt to extract the `source` path or connection string from the notebook's parameter widgets or task parameters. Record `source_type` accordingly.
**ELSE IF** the task parameters contain keys matching `FIVETRAN_CONNECTOR_ID`, `AIRBYTE_CONNECTION_ID`, or similar,
**THEN** classify as `EXTERNAL_ORCHESTRATOR` and record the connection ID for cross-referencing in Phase 3.
**ELSE** classify as `UNKNOWN` and flag for manual review.

---

## 5. DECISION GATE

> **DECISION GATE — Discovery complete?**
>
> ALL of the following must be true before Phase 3 (Ontology) may begin:
>
> - [ ] `discovery_workspaces.json` exists and contains at least one workspace record with `status: RUNNING` and a non-null `workspace_url`
> - [ ] Unity Catalog or Hive Metastore enumeration has completed for every RUNNING workspace with at least one catalog/database record captured (even if empty)
> - [ ] Every table and schema record has a `medallion_layer` field assigned (values: `BRONZE`, `SILVER`, `GOLD`, or `UNCLASSIFIED` — never `null`)
> - [ ] `discovery_dlt_pipelines.json` exists (may be empty array `[]` if no DLT pipelines found — absence of the file is a failure)
> - [ ] `discovery_jobs_ingestion.json` exists and each job task record has a non-null `source_type` field
> - [ ] `discovery_clusters.json` exists and every cluster record includes `governance_risk` classification
> - [ ] `discovery_warehouses.json` exists and every warehouse record includes `state` and `jdbc_url`
> - [ ] `discovery_dashboards.json` exists with at least a `dashboards` key (empty array permitted if no dashboards deployed)
> - [ ] `discovery_genie_spaces.json` exists with at least a `genie_spaces` key (empty array permitted if no Genie spaces deployed)
> - [ ] `discovery_manifest_summary.json` exists with aggregate counts: `total_workspaces`, `total_catalogs`, `total_schemas`, `total_tables`, `total_dlt_pipelines`, `total_jobs`, `total_clusters`, `total_warehouses`, `total_dashboards`, `total_genie_spaces`, `discovery_timestamp`
> - [ ] No discovery file contains `null` for a required field — all gaps must be explicitly represented as `"UNKNOWN"` string or empty array `[]`
> - [ ] All API calls have completed with either a successful response or a documented error captured in `discovery_errors.log` — no silent failures permitted
>
> **If not met — remediation steps:**
>
> 1. Identify which specific output file is missing or incomplete by comparing actual files against the checklist above.
> 2. Re-execute only the failing discovery activity (do not re-run the full phase unless >50% of checks are failing).
> 3. If the failure is an API permission error (HTTP 403/401), escalate to the workspace administrator to provision the required token scope before retrying.
> 4. If the failure is a timeout or rate-limit error (HTTP 429 or HTTP 504), implement exponential backoff with `initial_delay=2s`, `max_delay=60s`, `max_retries=5` and re-attempt the specific API call.
> 5. If a workspace is in a non-RUNNING state and cannot be reached, document it in `discovery_errors.log` with `workspace_id`, `status`, and `reason`, then mark that workspace as `scope: EXCLUDED` in `discovery_workspaces.json` and continue with remaining workspaces.
> 6. After remediation, re-evaluate ALL gate criteria from the top — partial re-runs must still satisfy every criterion.

---

## 6. OUTPUTS

| Output File | Format | Contents | Required |
|---|---|---|---|
| `discovery_workspaces.json` | JSON array | All workspace records with IDs, URLs, regions, statuses | YES |
| `discovery_catalogs_schemas_tables.json` | JSON array | Full Unity Catalog / Hive Metastore object inventory with medallion classification | YES |
| `discovery_dlt_pipelines.json` | JSON array | All DLT pipeline specs, states, recent update events, target schemas | YES |
| `discovery_jobs_ingestion.json` | JSON array | All ingestion jobs with task decomposition and source type classification | YES |
| `discovery_clusters.json` | JSON array | All clusters (running + recently terminated) with governance risk flags | YES |
| `discovery_warehouses.json` | JSON array | All SQL Warehouses with JDBC URLs and data access configs | YES |
| `discovery_dashboards.json` | JSON object | `{"dashboards": [...]}` with embedded query extraction | YES |
| `discovery_genie_spaces.json` | JSON object | `{"genie_spaces": [...]}` with table identifiers and warehouse references | YES |
| `discovery_lineage_seeds.json` | JSON array | Table-level upstream/downstream pairs from Unity Catalog lineage API | RECOMMENDED |
| `discovery_source_connections.json` | JSON array | External source systems identified (S3 paths, JDBC URLs, Kafka brokers, Fivetran/Airbyte IDs) | YES |
| `discovery_manifest_summary.json` | JSON object | Aggregate counts, discovery timestamp, scope flags, health summary | YES |
| `discovery_errors.log` | Plain text | Timestamped log of all API errors, permission gaps, skipped resources | YES |

All output files must be saved to a consistent output directory (e.g., `./databricks_discovery_output/`) with a timestamp suffix in the directory name: `databricks_discovery_output_YYYYMMDD_HHMMSS/`.

---

## 7. ANTI-PATTERNS

**Anti-Pattern 1: Enumerating only RUNNING clusters and ignoring TERMINATED ones.**
Many Databricks environments use job clusters that spin up for a task and immediately terminate. Skipping TERMINATED clusters (within the last 30 days) means the agent will miss the compute backbone of scheduled pipelines entirely. In Phase 3, this results in an ontology diagram where ingestion jobs and DLT pipelines appear to have no compute association — producing a dangerously misleading architecture view. Always include TERMINATED clusters with `terminated_time` within a 30-day lookback window and cross-reference them against job run history.

**Anti-Pattern 2: Treating Genie spaces and dashboards as optional or cosmetic.**
A common mistake is to deprioritize Lakeview dashboards and AI/BI Genie spaces on the assumption that they are "just presentation layer" and don't affect data architecture. In reality, Genie spaces explicitly enumerate which Unity Catalog tables they are authorized to query, making them the most direct map of Gold-layer table consumption in the environment. Skipping them means the ontology will not show who consumes the Gold layer, making the entire medallion dependency chain appear to terminate at Gold tables with no downstream. Every Genie space and dashboard must be discovered and its `table_identifiers` / embedded queries extracted to close the consumption loop.

**Anti-Pattern 3: Applying medallion classification by catalog/schema name alone without checking table properties and lineage.**
Environments frequently have inconsistently named schemas — a `silver_temp` table might actually be a Bronze-layer raw dump, or a `landing` schema might contain pre-processed Silver-quality data. Relying solely on name-based regex classification without cross-referencing Unity Catalog table properties (the `layer` tag) and the lineage graph position (upstream vs. downstream table count) produces a medallion map with systematic mis-classification errors. These errors propagate directly into Phase 3, where the ontology will show incorrect data flow directions. Always run all three classification signals (name heuristics → tag → lineage position) and use the tag as the authoritative source when it conflicts with name heuristics.

**Anti-Pattern 4: Stopping discovery after the first workspace in a multi-workspace account.**
In enterprise accounts, the first workspace returned by the account API is often a development or sandbox workspace — not the production environment where the majority of assets reside. Stopping after one workspace produces a discovery manifest that represents a fraction of the environment. Always iterate over every workspace returned by `GET /api/2.0/accounts/{account_id}/workspaces` and process each one independently. Track per-workspace completion status in the manifest summary.

---

## 8. AGENT INSTRUCTIONS

1. **Verify Phase 1 gate is GREEN.** Before executing any discovery action, read the Phase 1 output file `connectivity_check_results.json`. Confirm that `gate_status` equals `"PASS"`. If it equals `"FAIL"` or the file does not exist, halt immediately and return control to Phase 1. Do not proceed under any circumstance without a confirmed GREEN connectivity gate.

2. **Create the timestamped output directory.** Generate a timestamp string in `YYYYMMDD_HHMMSS` format and create the directory `./databricks_discovery_output_{timestamp}/`. All output files for this phase must be written to this directory. Write the directory path to a session variable `DISCOVERY_OUTPUT_DIR` for consistent reference throughout the phase.

3. **Initialize `discovery_errors.log`.** Create an empty log file at `{DISCOVERY_OUTPUT_DIR}/discovery_errors.log`. Every API call failure, permission error, timeout, or skipped resource must be appended to this file with format: `[TIMESTAMP] [SEVERITY: INFO|WARN|ERROR] [RESOURCE_TYPE] [RESOURCE_ID_OR_URL] [HTTP_STATUS] [MESSAGE]`.

4. **Enumerate all workspaces using the account-level API.** Execute the workspace enumeration code from Technical Guidance section 3.1. Handle HTTP 403 per the Decision Logic in section 4. Write the output to `{DISCOVERY_OUTPUT_DIR}/discovery_workspaces.json`. Log the count of RUNNING vs. non-RUNNING workspaces to the errors log as `INFO` entries.

5. **For each RUNNING workspace, authenticate and begin the Unity Catalog walk.** Use the workspace-specific PAT or OAuth token from Phase 1's `connectivity_check_results.json`. If Unity Catalog is unavailable (HTTP 404 on metastore endpoint), switch to Hive Metastore mode per Decision Logic section 4. Execute the SQL from Technical Guidance section 3.2 against each workspace and accumulate results into a running array. Do not write the file until all workspaces are processed.

6. **Apply medallion classification to every table record.** Pass each table record through the `classify_medallion()` function from Technical Guidance section 3.3. Enforce the three-signal priority order: (a) `layer` tag value, (b) name heuristic, (c) lineage API position. Assign a `medallion_layer` field to every record. Write the completed array to `{DISCOVERY_OUTPUT_DIR}/discovery_catalogs_schemas_tables.json`.

7. **Enumerate DLT pipelines per workspace.** Execute the `discover_dlt_pipelines()` function from Technical Guidance section 3.4 for each RUNNING workspace. Apply `pipeline_health` classification per Decision Logic section 4. Accumulate results across all workspaces and write to `{DISCOVERY_OUTPUT_DIR}/discovery_dlt_pipelines.json`.

8. **Enumerate all jobs and classify ingestion tasks.** Call `GET /api/2.1/jobs/list?expand_tasks=true` for each workspace. For each task, apply the source type decision logic from section 4. Write results to `{DISCOVERY_OUTPUT_DIR}/discovery_jobs_ingestion.json`. For any job task classified as `UNKNOWN`, add an `INFO` entry to `discovery_errors.log` flagging it for manual classification.

9. **Enumerate all clusters with governance risk classification.** Call `GET /api/2.0/clusters/list` per workspace. Apply the 30-day lookback filter for TERMINATED clusters. Apply `governance_risk` classification per Decision Logic section 4. Write to `{DISCOVERY_OUTPUT_DIR}/discovery_clusters.json`.

10. **Enumerate SQL Warehouses per workspace.** Execute the CLI command from Technical Guidance section 3.5 or its Python equivalent. For each warehouse, call the `/config` endpoint to capture data access configuration. Write to `{DISCOVERY_OUTPUT_DIR}/discovery_warehouses.json`.

11. **Enumerate Lakeview Dashboards and AI/BI Genie Spaces.** Execute the `discover_dashboards_and_genie()` function from Technical Guidance section 3.6 for each RUNNING workspace. Parse embedded queries from dashboard specs. Capture Genie space table identifiers. Write dashboards to `{DISCOVERY_OUTPUT_DIR}/discovery_dashboards.json` and Genie spaces to `{DISCOVERY_OUTPUT_DIR}/discovery_genie_spaces.json`.

12. **Extract external source connection records.** Scan all ingestion job records in `discovery_jobs_ingestion.json` and all DLT pipeline library paths for external connection strings: S3 `s3://` paths, ADLS `abfss://` paths, JDBC connection URLs, Kafka broker strings, Fivetran connector IDs, Airbyte connection IDs. Deduplicate and write to `{DISCOVERY_OUTPUT_DIR}/discovery_source_connections.json`.

13. **Call the Unity Catalog lineage API for top-level tables.**