# Phase 1: Pre-discovery

**Skill:** `databricks-full-discovery`
**Phase sequence:** Phase 1 of 3
**Followed by:** Phase 2 — Discover
**Exit gate:** Connectivity `[conditional]` → on-fail: retry

---

## 1. PURPOSE

Pre-discovery is the mandatory connectivity validation layer that must succeed before any enumeration of Databricks resources begins. Without confirmed reachability to every configured workspace and Unity Catalog metastore, the downstream discovery phase will silently produce incomplete inventories — missing catalogs, schemas, or entire workspaces — with no error signal to indicate the gap. This phase exists precisely to surface those failures explicitly and early, before any state is persisted or any inventory is treated as authoritative.

This phase unlocks Phase 2 by establishing a verified, credentialed connection surface: confirmed REST API reachability per workspace, validated OAuth or PAT token scopes, metastore attachment confirmation, and a healthy Unity Catalog query path. Without these confirmations, Phase 2 would attempt discovery against an unknown and potentially broken substrate, producing partial results that could be mistaken for a complete inventory. Silent partial discovery is significantly more dangerous than a hard failure, because downstream consumers — including the ontology in Phase 3 — would be built on structurally incomplete data.

What fails without Pre-discovery is trust. Connectivity to Databricks workspaces can fail for a wide range of reasons — expired tokens, IP allowlist mismatches, Unity Catalog metastore detachments, service principal permission gaps, private link endpoint misconfigurations, or regional API outages. Pre-discovery forces each of these failure modes into the open, produces a structured connectivity manifest that subsequent phases consume, and establishes the exact set of workspaces and catalogs that are in-scope for discovery. Nothing is assumed reachable; everything is proven.

---

## 2. KEY ACTIVITIES

- **Enumerate all target workspace URLs from configuration input.** Parse the agent's input configuration (environment variables, a `discovery_targets.yaml` file, or inline parameters) to extract every Databricks workspace host (`https://<workspace-id>.azuredatabricks.net`, `https://<account>.cloud.databricks.com`, or `https://<workspace>.gcp.databricks.com`). Deduplicate and normalize all URLs to lowercase with no trailing slash. Record the cloud provider (Azure, AWS, GCP) per workspace for provider-specific API path handling.

- **Resolve and validate authentication credentials per workspace.** For each workspace, determine the authentication method in use: Personal Access Token (PAT), OAuth M2M (client credentials flow via service principal), or Azure Managed Identity / Azure AD token. Retrieve the credential from its configured secret store (environment variable, Azure Key Vault, AWS Secrets Manager, or Databricks Secret Scope). Validate that the credential is not expired by inspecting token TTL where applicable. For OAuth M2M, execute the token exchange before proceeding and cache the bearer token with its expiry timestamp.

- **Execute a live HTTP connectivity check against the Databricks REST API per workspace.** Issue a `GET /api/2.0/clusters/list` or `GET /api/2.1/jobs/list` call (with `limit=1`) against each workspace host. Verify that the HTTP status is `200 OK` and that the response is valid JSON. A `401 Unauthorized` indicates credential failure; a `403 Forbidden` indicates insufficient scope; a `503` or timeout indicates network-layer failure. Record the exact HTTP status, response time in milliseconds, and any error message per workspace.

- **Verify Unity Catalog metastore attachment per workspace.** For each workspace that returned HTTP 200, call `GET /api/2.1/unity-catalog/metastores/summary` to confirm a metastore is attached. Extract the `metastore_id`, `name`, `cloud`, `region`, and `default_data_access_config_type` from the response. A workspace with no attached metastore falls back to legacy Hive metastore only — flag this condition explicitly in the connectivity manifest as `metastore_type: hive_legacy` and note that Unity Catalog catalog enumeration will not be available for that workspace.

- **Enumerate top-level catalogs accessible to the calling principal.** For each workspace with a Unity Catalog metastore confirmed, execute `GET /api/2.1/unity-catalog/catalogs` and collect the full list of catalog names, owners, comment fields, and `created_at` timestamps. Attempt `GET /api/2.1/unity-catalog/catalogs/{catalog_name}` for each returned catalog to confirm read-level access. Record any catalogs that are returned in the list but fail the individual GET with `403` — these exist but are inaccessible to the calling credential and must be flagged in the connectivity manifest.

- **Test SQL warehouse query path via JDBC/ODBC or HTTP connector.** For at least one running SQL warehouse per workspace, execute a trivial connectivity query — `SELECT current_catalog(), current_metastore()` — via the Databricks SQL Connector for Python (`databricks-sql-connector`) using the warehouse's HTTP path. Confirm the returned `current_catalog()` matches an expected value. This validates the full query path independently of the REST API path and catches issues such as warehouse firewall rules or proxy interceptions that REST API checks alone would not surface.

- **Check service principal or user permissions for discovery-required privilege sets.** Call `GET /api/2.1/unity-catalog/permissions/metastore/<metastore_id>` to confirm the calling principal holds at minimum `USE METASTORE`. Call `GET /api/2.1/unity-catalog/effective-permissions/catalog/<catalog_name>` for each accessible catalog to confirm `USE CATALOG`. For compute enumeration in Phase 2, verify that the principal holds `CAN_VIEW` on clusters via `GET /api/2.0/permissions/clusters` on a known cluster ID. Log all permission deficits without failing the phase — they reduce discovery scope but do not block connectivity.

- **Measure and record API rate limit headroom per workspace.** Inspect response headers `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `Retry-After` (where present) from the connectivity probe calls. If `X-RateLimit-Remaining` is below 20% of `X-RateLimit-Limit`, emit a warning in the connectivity manifest. Calculate estimated API call budget for Phase 2 based on the number of catalogs, expected schemas, and object types. If the budget exceeds the remaining rate limit, insert adaptive throttling parameters (`requests_per_second` cap) into the Phase 2 configuration block of the connectivity manifest.

---

## 3. TECHNICAL GUIDANCE

### 3.1 Authentication — OAuth M2M Token Exchange

```python
import requests
import time

def get_oauth_token(host: str, client_id: str, client_secret: str) -> dict:
    """
    Exchange client credentials for a Databricks OAuth M2M bearer token.
    Returns dict with 'access_token', 'expires_at' (unix epoch), 'scope'.
    """
    token_url = f"{host}/oidc/v1/token"
    payload = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "all-apis"
    }
    response = requests.post(token_url, data=payload, timeout=15)
    response.raise_for_status()
    token_data = response.json()
    token_data["expires_at"] = int(time.time()) + token_data.get("expires_in", 3600) - 60
    return token_data
```

### 3.2 REST API Connectivity Probe

```python
import requests

def probe_workspace(host: str, token: str) -> dict:
    """
    Execute a minimal REST API call to confirm workspace reachability and auth.
    Returns structured connectivity result.
    """
    url = f"{host}/api/2.0/clusters/list"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"limit": 1}
    result = {
        "host": host,
        "reachable": False,
        "http_status": None,
        "response_ms": None,
        "error": None,
        "rate_limit_remaining": None
    }
    try:
        import time
        start = time.monotonic()
        resp = requests.get(url, headers=headers, params=params, timeout=20)
        result["response_ms"] = round((time.monotonic() - start) * 1000, 1)
        result["http_status"] = resp.status_code
        result["rate_limit_remaining"] = resp.headers.get("X-RateLimit-Remaining")
        if resp.status_code == 200:
            result["reachable"] = True
        else:
            result["error"] = resp.json().get("message", resp.text[:200])
    except requests.exceptions.ConnectionError as e:
        result["error"] = f"CONNECTION_ERROR: {str(e)}"
    except requests.exceptions.Timeout:
        result["error"] = "TIMEOUT: No response within 20 seconds"
    return result
```

### 3.3 Unity Catalog Metastore Check

```python
def check_unity_catalog(host: str, token: str) -> dict:
    """
    Confirm Unity Catalog metastore attachment and retrieve metastore metadata.
    """
    url = f"{host}/api/2.1/unity-catalog/metastores/summary"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers, timeout=15)
    if resp.status_code == 200:
        data = resp.json()
        return {
            "metastore_attached": True,
            "metastore_id": data.get("metastore_id"),
            "metastore_name": data.get("name"),
            "region": data.get("region"),
            "cloud": data.get("cloud"),
            "metastore_type": "unity_catalog"
        }
    elif resp.status_code == 404:
        return {"metastore_attached": False, "metastore_type": "hive_legacy"}
    else:
        return {"metastore_attached": False, "metastore_type": "unknown",
                "error": resp.json().get("message")}
```

### 3.4 SQL Warehouse Connectivity Test

```python
from databricks import sql as dbsql

def test_sql_path(host: str, http_path: str, token: str) -> dict:
    """
    Execute a trivial SQL query via the Databricks SQL Connector to validate
    the full JDBC/HTTP query path independently of the REST API.
    """
    try:
        with dbsql.connect(
            server_hostname=host.replace("https://", ""),
            http_path=http_path,
            access_token=token,
            _socket_timeout=30
        ) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT current_catalog(), current_metastore()")
                row = cursor.fetchone()
                return {
                    "sql_path_reachable": True,
                    "current_catalog": row[0],
                    "current_metastore": row[1]
                }
    except Exception as e:
        return {"sql_path_reachable": False, "error": str(e)}
```

### 3.5 Connectivity Manifest Schema (YAML)

```yaml
# connectivity_manifest.yaml — generated output of Phase 1
# Written to: ./discovery_output/phase1_connectivity_manifest.yaml

schema_version: "1.0"
generated_at: "2025-01-15T09:32:11Z"
skill: "databricks-full-discovery"
phase: "pre-discovery"

workspaces:
  - host: "https://adb-1234567890123456.7.azuredatabricks.net"
    cloud: "azure"
    region: "eastus"
    reachable: true
    http_status: 200
    response_ms: 312
    auth_method: "oauth_m2m"
    token_expires_at: 1737032331
    metastore_type: "unity_catalog"
    metastore_id: "abc12345-def6-7890-ghij-klmnopqrstuv"
    metastore_name: "prod-metastore-eastus"
    catalogs_accessible: ["main", "bronze", "silver", "gold", "sandbox"]
    catalogs_inaccessible: ["system"]
    sql_path_reachable: true
    rate_limit_remaining: "847"
    permission_gaps:
      - "MISSING: USE CATALOG on 'system'"
    connectivity_status: "PASS"

  - host: "https://adb-9876543210987654.3.azuredatabricks.net"
    cloud: "azure"
    reachable: false
    http_status: 401
    error: "Token expired or invalid"
    connectivity_status: "FAIL"
    fail_reason: "AUTH_FAILURE"

phase1_summary:
  total_workspaces: 2
  reachable: 1
  unreachable: 1
  unity_catalog_workspaces: 1
  hive_legacy_workspaces: 0
  total_catalogs_accessible: 5
  gate_status: "FAIL"
  retry_required: true
  retry_targets:
    - "https://adb-9876543210987654.3.azuredatabricks.net"
```

### 3.6 Databricks CLI Spot-check Commands

```bash
# Verify CLI profile configuration
databricks configure --profile prod-workspace-1

# Test REST API reachability via CLI
databricks clusters list --profile prod-workspace-1 --output json | head -20

# Confirm Unity Catalog metastore attachment
databricks unity-catalog metastores summary --profile prod-workspace-1

# List accessible catalogs
databricks unity-catalog catalogs list --profile prod-workspace-1

# Check current user identity (confirms auth is working)
databricks current-user me --profile prod-workspace-1
```

---

## 4. DECISION LOGIC

```
IF workspace HTTP response status == 200 AND response body is valid JSON:
    THEN mark workspace as REACHABLE
    THEN proceed to Unity Catalog metastore check for this workspace
ELSE IF status == 401:
    THEN classify failure as AUTH_FAILURE
    THEN attempt credential refresh (OAuth M2M re-exchange or PAT rotation hint)
    THEN retry once after 5 seconds
    IF retry still returns 401:
        THEN mark workspace as PERMANENTLY_UNREACHABLE for this phase run
        THEN add to retry_targets in connectivity manifest
ELSE IF status == 403:
    THEN classify failure as PERMISSION_FAILURE
    THEN mark workspace as REACHABLE but RESTRICTED
    THEN log missing permissions and proceed with reduced scope
ELSE IF status == 503 OR connection timeout:
    THEN classify failure as NETWORK_FAILURE
    THEN wait 15 seconds and retry up to 3 times with exponential backoff (15s, 30s, 60s)
    IF all retries fail:
        THEN mark workspace as UNREACHABLE with NETWORK_FAILURE
        THEN add to retry_targets

IF metastore check returns 200:
    THEN set metastore_type = unity_catalog
    THEN proceed to catalog enumeration
ELSE IF metastore check returns 404:
    THEN set metastore_type = hive_legacy
    THEN skip Unity Catalog catalog enumeration for this workspace
    THEN flag workspace for Hive-only discovery in Phase 2
ELSE:
    THEN treat as connectivity degraded, log error, continue to next workspace

IF catalog GET returns 200 for all catalogs in list:
    THEN mark all catalogs as ACCESSIBLE
ELSE IF catalog GET returns 403 for specific catalogs:
    THEN mark those catalogs as EXISTS_BUT_INACCESSIBLE
    THEN include them in the manifest with reduced-access flag
    THEN do NOT fail the workspace connectivity check on this condition alone

IF SQL warehouse query path test returns current_catalog successfully:
    THEN mark sql_path_reachable = true
ELSE:
    THEN mark sql_path_reachable = false
    THEN log warning — Phase 2 will rely on REST API only for this workspace
    THEN do NOT block connectivity gate on this condition if REST API is reachable

IF ALL workspaces are UNREACHABLE (zero reachable):
    THEN set gate_status = FAIL
    THEN halt and surface full failure report
    THEN await human intervention before retry
ELSE IF at least ONE workspace is REACHABLE:
    THEN set gate_status = PARTIAL_PASS
    THEN proceed to Phase 2 with the reachable subset
    THEN flag unreachable workspaces as out-of-scope for this discovery run
```

---

## 5. DECISION GATE

> **DECISION GATE — Connectivity**
>
> ALL must be true to proceed to Phase 2 — Discover:
>
> - [ ] At least one Databricks workspace has returned HTTP `200 OK` from a live REST API probe with a valid JSON response body
> - [ ] For every reachable workspace, the authentication token or credential has been confirmed as non-expired and the calling principal identity has been resolved via `GET /api/2.0/token/list` or `GET /api/2.1/me`
> - [ ] At least one workspace has a confirmed Unity Catalog metastore attachment OR at least one workspace has been confirmed as Hive-legacy (metastore type must be explicitly classified — "unknown" is not acceptable)
> - [ ] At least one catalog (Unity Catalog) or database (Hive) is confirmed accessible to the calling principal with `USE` privilege or equivalent
> - [ ] The `phase1_connectivity_manifest.yaml` file has been written to `./discovery_output/` with `schema_version`, `generated_at`, and at least one workspace entry in `workspaces[]`
> - [ ] All unreachable workspaces have a documented `fail_reason` (one of: `AUTH_FAILURE`, `PERMISSION_FAILURE`, `NETWORK_FAILURE`, `TIMEOUT`, `UNKNOWN`) — no workspace may be left with `connectivity_status: FAIL` and an empty `fail_reason`
> - [ ] API rate limit headroom has been assessed and either confirmed sufficient (`X-RateLimit-Remaining > 20%`) or an adaptive throttle configuration has been written into the manifest for Phase 2
>
> **If not met — exact remediation steps:**
>
> 1. **AUTH_FAILURE on all workspaces:** Re-execute the OAuth M2M token exchange manually using `curl -X POST <host>/oidc/v1/token` with the client credentials. If the PAT is in use, verify it has not been revoked via the Databricks UI → Settings → Developer → Access Tokens. Rotate the credential in the secret store and update the agent's configuration. Retry Phase 1 from the beginning.
>
> 2. **NETWORK_FAILURE on all workspaces:** Confirm network routing from the agent's execution environment. If running inside a private network, verify that private link or VNet peering to the Databricks control plane is active. Run `nslookup <workspace-host>` and `curl -v --max-time 10 https://<workspace-host>/api/2.0/clusters/list` directly. Engage the network/infrastructure team if DNS or TCP connectivity is absent. Do not retry until confirmed routable.
>
> 3. **Zero catalogs accessible (UC exists but no USE grants):** Request that a Unity Catalog admin execute `GRANT USE CATALOG ON CATALOG <name> TO <service_principal_or_user>` for at least one catalog. Alternatively, grant `METASTORE ADMIN` role temporarily for discovery purposes if organizational policy permits.
>
> 4. **Manifest file not written:** Check write permissions on `./discovery_output/` directory. Create the directory if absent: `mkdir -p ./discovery_output`. Retry manifest write.
>
> 5. **Partial pass (some workspaces unreachable):** Proceed to Phase 2 with the reachable subset. Log the unreachable workspaces in the manifest with `out_of_scope: true`. Notify the operator that the discovery will be incomplete for those workspaces and they must be re-run after remediation.

---

## 6. OUTPUTS

| Output Artifact | Format | Location | Description |
|---|---|---|---|
| `phase1_connectivity_manifest.yaml` | YAML | `./discovery_output/phase1_connectivity_manifest.yaml` | Primary structured output. Contains per-workspace connectivity status, metastore type, accessible catalog list, auth method, rate limit headroom, permission gaps, and overall gate status. Consumed by Phase 2 as its input configuration. |
| `phase1_probe_log.jsonl` | JSONL | `./discovery_output/logs/phase1_probe_log.jsonl` | Raw per-request log with timestamp, URL, HTTP method, status code, response time ms, and truncated response body (first 500 chars). One JSON object per line. Retained for debugging failed connectivity. |
| `phase1_permission_gaps.md` | Markdown | `./discovery_output/phase1_permission_gaps.md` | Human-readable summary of all permission deficits discovered during the phase. Lists workspace, principal, missing privilege, and remediation SQL. Intended for forwarding to a Databricks admin. |
| `phase2_input_config.yaml` | YAML | `./discovery_output/phase2_input_config.yaml` | Auto-generated input configuration for Phase 2, derived from the connectivity manifest. Contains the exact list of reachable workspaces with their tokens (referenced by env var name, not inline), metastore IDs, accessible catalog lists, and throttle parameters. |
| Phase 1 Gate Status (console/log) | Text | stdout + `./discovery_output/logs/gate_status.log` | Single-line gate evaluation result: `GATE: PASS`, `GATE: PARTIAL_PASS`, or `GATE: FAIL` with timestamp and count of reachable/unreachable workspaces. Used by the orchestrator to decide whether to advance to Phase 2 or enter retry. |

---

## 7. ANTI-PATTERNS

### Anti-Pattern 1: Assuming reachability based on previous successful connections

**Mistake:** Skipping the live HTTP connectivity probe because the workspace was reachable in a prior discovery run or because a developer confirmed it was working yesterday.

**Consequence:** Tokens expire (Databricks PATs default to 90 days; OAuth M2M tokens expire in 1 hour). Network rules change. IP allowlists are updated. A metastore that was attached yesterday can be detached today by an admin. If Phase 1 does not probe live, Phase 2 will begin discovery against a workspace that fails on the first real API call, but by that point the agent has already committed to a discovery scope. The result is a partial inventory with no explicit error — the most dangerous outcome because it appears complete to consumers of the Phase 3 ontology.

### Anti-Pattern 2: Treating a 403 Forbidden on one catalog as a workspace-level connectivity failure

**Mistake:** When `GET /api/2.1/unity-catalog/catalogs/system` returns `403 Forbidden`, marking the entire workspace as UNREACHABLE or FAIL and triggering a full retry loop.

**Consequence:** The `system` catalog in Unity Catalog is restricted to `METASTORE ADMIN` by default. A 403 on specific catalogs is a permission scope issue, not a connectivity failure. Mis-classifying it as a connectivity failure causes the phase to enter an infinite retry loop against a perfectly reachable workspace, wasting time and API rate limit budget. Worse, if the retry condition escalates to human intervention, operators waste time investigating a non-existent network problem. The correct behavior is to log the inaccessible catalog, continue enumerating the remaining catalogs, and note the permission gap in the manifest.

### Anti-Pattern 3: Writing workspace credentials (tokens) directly into the connectivity manifest file

**Mistake:** Including the literal bearer token or PAT value inside `phase1_connectivity_manifest.yaml` or `phase2_input_config.yaml` for convenience, so downstream phases can read it without additional secret resolution.

**Consequence:** The manifest file is a discovery artifact that gets shared, copied, logged, and potentially committed to version control as part of the skill's output. Embedding tokens in plain-text YAML creates a secret sprawl vulnerability. If the manifest is emitted to the Desktop as part of the Phase 3 ontology output or shared with stakeholders, the token is fully exposed. Tokens must always be referenced by environment variable name or secret store path (e.g., `token_env_var: DATABRICKS_PROD_WS1_TOKEN`) and resolved at execution time. The manifest must never contain a token value — only a reference to where the token lives.

### Anti-Pattern 4: Running all workspace probes sequentially with no timeout enforcement

**Mistake:** Probing each workspace one at a time with a default `requests` timeout of `None` (blocking indefinitely) when a workspace is behind a misconfigured proxy or a black-hole firewall rule.

**Consequence:** A single unresponsive workspace can block the entire Pre-discovery phase for minutes to hours, because TCP connections to black-hole routes never time out unless explicitly bounded. In environments with 10+ workspaces, this compounds catastrophically. Always set explicit `timeout=(connect_timeout, read_timeout)` values — recommended: `(10, 20)` seconds — and run workspace probes concurrently using `concurrent.futures.ThreadPoolExecutor` with a max worker count equal to the number of target workspaces (capped at 10).

---

## 8. AGENT INSTRUCTIONS

The following numbered steps define the exact execution sequence for an AI agent running Phase 1: Pre-discovery of the `databricks-full-discovery` skill.

1. **Load target configuration.** Read the discovery targets from the primary input source. Check in priority order: (a) `DATABRICKS_DISCOVERY_TARGETS` environment variable (JSON array of workspace objects), (b) `./discovery_targets.yaml` in the working directory, (c) inline parameters passed at skill invocation. If no configuration is found, halt immediately and emit: `ERROR: No discovery targets configured. Provide DATABRICKS_DISCOVERY_TARGETS or discovery_targets.yaml.`

2. **Parse and normalize workspace entries.** For each workspace entry in the configuration, extract: `host` (normalize to lowercase, strip trailing slash, ensure `https://` prefix), `auth_method` (`pat`, `oauth_m2m`, or `azure_managed_identity`), credential reference (env var name or secret path — never the raw value), and optional `sql_warehouse_http_path`. Build an internal list of `WorkspaceTarget` objects.

3. **Resolve credentials for each workspace.** For each `WorkspaceTarget`, retrieve the credential using the specified `auth_method`. For `oauth_m2m`: execute the token exchange against `<host>/oidc/v1/token` using `client_id` and `client_secret` from the referenced env vars. For `pat`: read the PAT from the referenced env var. For `azure_managed_identity`: call the Azure IMDS endpoint `http://169.254.169.254/metadata/identity/oauth2/token` with `resource=2ff814a6-3304-4ab8-85cb-cd0e6f879c1d`. Cache each resolved token with its `expires_at` timestamp. If credential resolution fails for any workspace, log the failure with the workspace host and credential reference name, and mark that workspace as `AUTH_FAILURE` — do not halt the entire phase.

4. **Create output directory structure.** Execute `mkdir -p ./discovery_output/logs`. Verify write access by creating a zero-byte sentinel file `./discovery_output/.phase1_started` with the current UTC timestamp as content. If write fails, halt and emit directory permission error.

5. **Execute concurrent workspace connectivity probes.** Launch probes for all `WorkspaceTarget` objects with a resolved credential using `concurrent.futures.ThreadPoolExecutor`. Each probe thread calls `GET /api/2.0/clusters/list?limit=1` with `timeout=(10, 20)`. Collect results as they complete. Log each raw request/response to `./discovery_output/logs/phase1_probe_log.jsonl` as a JSONL entry immediately upon completion (do not batch).

6. **Execute Unity Catalog metastore check for all reachable workspaces.** For each workspace where the connectivity probe returned HTTP 200, call `GET /api/2.1/unity-catalog/metastores/summary`. Parse and store the `metastore_id`, `metastore_name`, `region`, `cloud`, and classify `metastore_type` as `unity_catalog` or `hive_legacy`. If the call returns 404, classify as `hive_legacy`. Log this check to the probe JSONL log.

7. **Enumerate accessible catalogs for Unity Catalog workspaces.** For each workspace with `metastore_type = unity_catalog`, call `GET /api/2.1/unity-catalog/catalogs`. Iterate over each returned catalog name and issue an individual `GET /api/2.1/unity-catalog/catalogs/<name>`. Classify each as `ACCESSIBLE` (200) or `EXISTS_BUT_INACCESSIBLE` (403). Store both lists in the workspace result. For `hive_legacy` workspaces, call `GET /api/2.0/clusters/list` with `limit=1` to verify at least basic cluster-level access for Hive discovery later.

8. **Execute SQL warehouse connectivity test for all reachable workspaces.** For workspaces that have a configured `sql_warehouse_http_path`, use `databricks-sql-connector` to execute `SELECT current_catalog(), current_metastore()`. Record the result as `sql_path_reachable: true/false`. If `sql_warehouse_http_path` is not configured for a workspace, set `sql_path_reachable: null` and emit a warning that SQL path validation was skipped.

9. **Assess rate limit headroom.** Parse `X-RateLimit-Remaining` and `X-RateLimit-Limit` headers from the probe responses. Calculate headroom as `remaining / limit`. If headroom < 0.20 for any workspace, compute a conservative `requests_per_second` cap for Phase 2: `(remaining * 0.8) / expected_phase2_duration_seconds`. Write this value into the Phase 2 input config for that workspace.

10. **Compile permission gap report.** Aggregate all 403 responses observed during catalog enumeration and any permission check calls. For each gap, generate the remediation SQL: `GRANT USE CATALOG ON CATALOG <name> TO <principal>` or `GRANT USE METASTORE ON METASTORE TO <principal>`. Write the compiled report to `./discovery_output/phase1_permission_gaps.md` in Markdown table format.

11. **Write the connectivity manifest.** Serialize the full structured result to `./discovery_output/phase1_connectivity_manifest.yaml` following the schema defined in Section 3.5. Include `generated_at` (UTC ISO 8601), `phase`, `schema_version: "1.0"`, and the complete `workspaces[]` array. Set `phase1_summary.gate_status` to `PASS` (all workspaces reachable), `PARTIAL_PASS` (some reachable), or `FAIL` (none reachable).

12. **Write the Phase 2 input configuration.** Generate `./discovery_output/phase2_input_config.yaml` containing only the reachable workspaces with their metastore IDs, accessible catalog lists, auth method and token env var references (not token values), SQL path availability flag, and rate limit throttle parameters. This file is the handoff artifact to Phase 2.

13. **Evaluate the connectivity gate.** Apply all gate criteria from Section 5. If `gate_status = PASS` or `PARTIAL_PASS`, emit `GATE: PASS — Proceeding to Phase 2: Discover` to stdout and to `./discovery_output/logs/gate_status.log`. If `gate_status = FAIL`, emit `GATE: FAIL — Retry required. See phase1_connectivity_manifest.yaml for fail_reason details.` Enter the retry loop: wait 60 seconds, then re-execute from Step 3 (skip Steps 1–2 which are idempotent setup steps). After 3 consecutive FAIL outcomes, halt and require human intervention.

14. **Transition to Phase 2.** Pass the path `./discovery_output/phase2_input_config.yaml` as the input configuration for Phase 2: Discover. Do not carry forward any workspace marked `connectivity_status: FAIL` into Phase 2. Emit a transition log entry: `Phase 1 complete. Reachable workspaces: <N>. Catalogs in scope: <total>. Advancing to Phase 2.`