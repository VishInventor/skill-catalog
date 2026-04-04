# Task Contract: Gather Inputs

## Metadata

| Field | Value |
|---|---|
| **Task ID** | `onlinestore-microservice-azure.phase1.gather-inputs` |
| **Task Name** | Gather Inputs |
| **Skill** | `onlinestore-microservice-azure` |
| **Phase** | Phase 1 — Pre-Provisioning Validation |
| **Version** | 1.0.0 |
| **Author** | Vishal Anand |
| **Criticality** | HIGH — Failure here blocks all downstream phases |

---

## Purpose

This task collects, validates, and normalises all user-supplied parameters and environmental context required to deploy the Azure Container Apps online store microservice stack. It acts as the single source of truth for configuration values consumed by all subsequent tasks in Phase 1 and all later phases. No Azure resource provisioning is initiated here; this task is purely about establishing a verified, complete, and conflict-free input surface before any infrastructure is touched.

The task interrogates the user query for explicit parameters, infers defaults where safe to do so, surfaces ambiguities for clarification, and emits a structured `validated_inputs` artefact that every subsequent task reads from.

---

## Prerequisites

Before this task executes, the following conditions must already be true on the agent's execution environment:

- **Azure CLI** `>= 2.55.0` is installed and on PATH (`az --version`)
- **Docker CLI** `>= 24.0` is installed and on PATH (`docker --version`)
- **Git** `>= 2.40` is installed and on PATH (`git --version`)
- **jq** `>= 1.6` is installed for JSON manipulation (`jq --version`)
- The agent has read access to `user_query` and `context` inputs passed by the orchestrator
- Network connectivity is available to `management.azure.com` (for subscription lookup validation)
- No pre-existing `validated_inputs.json` artefact exists in the working session that could cause stale reads

---

## Input Schema

### `user_query` — string (required)

The raw natural-language or structured request submitted by the user that triggered the skill. This string is parsed for explicit parameter declarations and intent signals.

```
Expected signals within user_query:
  - Azure subscription name or ID (e.g. "sub-prod-001" or "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")
  - Target Azure region (e.g. "eastus", "westeurope", "australiaeast")
  - Resource group name preference (e.g. "rg-store-prod")
  - Container Apps Environment name preference
  - SQL Server admin username
  - SQL Server admin password (treat as sensitive)
  - SQL Database name preference
  - Container image tag preference (default: "latest")
  - Environment tier (dev | staging | prod)
  - Any cost or SKU constraints mentioned
```

### `context` — object (required)

Structured context object injected by the orchestrator containing session metadata and any previously resolved values.

```json
{
  "session_id": "string — unique session identifier",
  "agent_role": "string — must equal 'Builder of online store'",
  "trigger_keyword": "string — one of: deploy | build | install",
  "prior_artefacts": "object | null — any artefacts from a prior retry of this phase",
  "user_preferences": {
    "naming_convention": "string | null",
    "tag_policy": "object | null",
    "region_restrictions": "array<string> | null"
  },
  "environment_variables": {
    "AZURE_SUBSCRIPTION_ID": "string | null",
    "AZURE_TENANT_ID": "string | null",
    "AZURE_CLIENT_ID": "string | null",
    "AZURE_CLIENT_SECRET": "string | null"
  }
}
```

---

## Output Schema

### `validated_inputs` — object

All fields below are guaranteed to be present and non-null in a successful output. Sensitive fields are marked `[SENSITIVE]` and must be stored in the session secret store, not in plaintext artefacts.

```json
{
  "subscription_id": "string — validated Azure subscription GUID",
  "subscription_name": "string — human-readable subscription name",
  "tenant_id": "string — Azure AD tenant GUID",
  "region": "string — normalised Azure region slug (e.g. eastus)",
  "resource_group_name": "string — target resource group name",
  "container_apps_env_name": "string — Container Apps Environment name",
  "container_apps_env_location": "string — same as region",
  "sql_server_name": "string — globally unique SQL Server logical name",
  "sql_database_name": "string — SQL Database name",
  "sql_admin_username": "string — SQL Server admin login",
  "sql_admin_password": "[SENSITIVE] string — SQL Server admin password",
  "image_tag": "string — container image tag (default: latest)",
  "environment_tier": "string — one of: dev | staging | prod",
  "session_id": "string — propagated from context",
  "microservice_repo_url": "string — fixed: https://github.com/Azure-Samples/container-apps-store-api-microservice",
  "naming_prefix": "string — derived short prefix used across all resource names",
  "tags": {
    "environment": "string",
    "managed_by": "agent",
    "skill": "onlinestore-microservice-azure",
    "session_id": "string"
  },
  "validation_timestamp": "string — ISO 8601 UTC timestamp of successful validation",
  "validation_warnings": "array<string> — non-fatal warnings to surface to user"
}
```

---

## Execution Steps

### Step 1 — Assert Tool Availability

Verify all CLI tools required by this skill are present before attempting any parsing or network calls.

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "=== Step 1: Assert Tool Availability ==="

required_tools=("az" "docker" "git" "jq")
missing_tools=()

for tool in "${required_tools[@]}"; do
  if ! command -v "$tool" &>/dev/null; then
    missing_tools+=("$tool")
    echo "[MISSING] $tool"
  else
    version=$("$tool" --version 2>&1 | head -1)
    echo "[OK] $tool — $version"
  fi
done

if [ ${#missing_tools[@]} -gt 0 ]; then
  echo "[ERROR] Required tools not found: ${missing_tools[*]}"
  echo "Install missing tools before retrying this phase."
  exit 1
fi

echo "[PASS] All required tools present."
```

---

### Step 2 — Parse and Extract Parameters from `user_query`

Extract explicit parameters from the raw user query using pattern matching. Unmatched fields fall back to defaults or are flagged for interactive clarification.

```python
# gather_inputs_parse.py
import re
import json
import sys
import os
from datetime import datetime, timezone

user_query = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("USER_QUERY", "")
context    = json.loads(sys.argv[2]) if len(sys.argv) > 2 else json.loads(os.environ.get("CONTEXT", "{}"))

parsed = {}
warnings = []

# --- Subscription ---
sub_match = re.search(
    r'subscription[:\s]+([a-f0-9\-]{36}|[\w\-]+)',
    user_query, re.IGNORECASE
)
parsed["subscription_raw"] = sub_match.group(1).strip() if sub_match else \
    context.get("environment_variables", {}).get("AZURE_SUBSCRIPTION_ID") or None

# --- Region ---
known_regions = [
    "eastus","eastus2","westus","westus2","westus3","centralus","northcentralus",
    "southcentralus","westeurope","northeurope","uksouth","ukwest","australiaeast",
    "australiasoutheast","southeastasia","eastasia","japaneast","japanwest",
    "brazilsouth","canadacentral","canadaeast","francecentral","germanywestcentral",
    "switzerlandnorth","uaenorth","southafricanorth","koreacentral","norwayeast"
]
region_pattern = '|'.join(known_regions)
region_match = re.search(rf'\b({region_pattern})\b', user_query, re.IGNORECASE)
parsed["region"] = region_match.group(1).lower() if region_match else "eastus"
if not region_match:
    warnings.append("No Azure region specified in user_query — defaulting to 'eastus'. Override by re-running with an explicit region.")

# --- Resource Group ---
rg_match = re.search(r'resource.?group[:\s]+([\w\-]+)', user_query, re.IGNORECASE)
parsed["resource_group_name"] = rg_match.group(1).strip() if rg_match else None

# --- Environment Tier ---
tier_match = re.search(r'\b(dev|development|staging|stage|prod|production)\b', user_query, re.IGNORECASE)
if tier_match:
    raw_tier = tier_match.group(1).lower()
    tier_map = {"development": "dev", "stage": "staging", "production": "prod"}
    parsed["environment_tier"] = tier_map.get(raw_tier, raw_tier)
else:
    parsed["environment_tier"] = "dev"
    warnings.append("No environment tier detected — defaulting to 'dev'.")

# --- SQL Admin Username ---
sql_user_match = re.search(r'sql.?admin[:\s]+([\w]+)', user_query, re.IGNORECASE)
parsed["sql_admin_username"] = sql_user_match.group(1).strip() if sql_user_match else "sqladmin"

# --- SQL Admin Password ---
sql_pass_match = re.search(r'sql.?password[:\s]+([^\s]+)', user_query, re.IGNORECASE)
parsed["sql_admin_password_raw"] = sql_pass_match.group(1).strip() if sql_pass_match else None

# --- SQL Database Name ---
db_match = re.search(r'database[:\s]+([\w\-]+)', user_query, re.IGNORECASE)
parsed["sql_database_name_raw"] = db_match.group(1).strip() if db_match else None

# --- Image Tag ---
tag_match = re.search(r'tag[:\s]+([\w\.\-]+)', user_query, re.IGNORECASE)
parsed["image_tag"] = tag_match.group(1).strip() if tag_match else "latest"

# --- Fixed Values ---
parsed["microservice_repo_url"] = "https://github.com/Azure-Samples/container-apps-store-api-microservice"

print(json.dumps({"parsed": parsed, "warnings": warnings}, indent=2))
```

---

### Step 3 — Resolve Subscription and Tenant from Azure CLI

Use the parsed subscription identifier to resolve a verified subscription GUID and tenant ID from the live Azure control plane.

```bash
echo "=== Step 3: Resolve Subscription and Tenant ==="

SUBSCRIPTION_RAW=$(echo "$PARSED_OUTPUT" | jq -r '.parsed.subscription_raw // empty')

if [ -z "$SUBSCRIPTION_RAW" ]; then
  echo "[INFO] No subscription specified. Using default from 'az account show'."
  ACCOUNT_JSON=$(az account show --output json 2>/dev/null) || {
    echo "[ERROR] Not logged in to Azure CLI. Run 'az login' or set service principal env vars."
    exit 2
  }
else
  # Try as GUID first, then as name
  ACCOUNT_JSON=$(az account show --subscription "$SUBSCRIPTION_RAW" --output json 2>/dev/null) || {
    echo "[ERROR] Subscription '$SUBSCRIPTION_RAW' not found or not accessible."
    echo "Run 'az account list --output table' to see available subscriptions."
    exit 2
  }
fi

SUBSCRIPTION_ID=$(echo "$ACCOUNT_JSON" | jq -r '.id')
SUBSCRIPTION_NAME=$(echo "$ACCOUNT_JSON" | jq -r '.name')
TENANT_ID=$(echo "$ACCOUNT_JSON" | jq -r '.tenantId')
SUBSCRIPTION_STATE=$(echo "$ACCOUNT_JSON" | jq -r '.state')

echo "Subscription ID   : $SUBSCRIPTION_ID"
echo "Subscription Name : $SUBSCRIPTION_NAME"
echo "Tenant ID         : $TENANT_ID"
echo "State             : $SUBSCRIPTION_STATE"

if [ "$SUBSCRIPTION_STATE" != "Enabled" ]; then
  echo "[ERROR] Subscription state is '$SUBSCRIPTION_STATE'. Only 'Enabled' subscriptions are supported."
  exit 2
fi

echo "[PASS] Subscription resolved and active."
```

---

### Step 4 — Derive and Validate Resource Names

Generate safe, unique resource names from the parsed inputs and naming prefix, then validate against Azure naming rules.

```bash
echo "=== Step 4: Derive and Validate Resource Names ==="

SESSION_ID=$(echo "$CONTEXT" | jq -r '.session_id')
ENVIRONMENT_TIER=$(echo "$PARSED_OUTPUT" | jq -r '.parsed.environment_tier')
REGION=$(echo "$PARSED_OUTPUT" | jq -r '.parsed.region')

# Generate short 6-char hex suffix for uniqueness
SUFFIX=$(echo -n "$SESSION_ID" | sha256sum | cut -c1-6)
NAMING_PREFIX="store${SUFFIX}"

# Resource Group: user-supplied or derived
RG_RAW=$(echo "$PARSED_OUTPUT" | jq -r '.parsed.resource_group_name // empty')
RESOURCE_GROUP_NAME="${RG_RAW:-rg-${NAMING_PREFIX}-${ENVIRONMENT_TIER}}"

# Container Apps Environment Name (max 60 chars, alphanumeric + hyphens)
CAE_NAME="cae-${NAMING_PREFIX}-${ENVIRONMENT_TIER}"

# SQL Server Name (must be globally unique, 3-63 chars lowercase alphanumeric + hyphens)
SQL_SERVER_NAME="sql-${NAMING_PREFIX}-${ENVIRONMENT_TIER}"

# SQL Database Name
DB_RAW=$(echo "$PARSED_OUTPUT" | jq -r '.parsed.sql_database_name_raw // empty')
SQL_DATABASE_NAME="${DB_RAW:-storedb}"

# Validate naming rules
validate_name() {
  local name="$1"
  local max_len="$2"
  local pattern="$3"
  local label="$4"

  if [ ${#name} -gt "$max_len" ]; then
    echo "[ERROR] $label '$name' exceeds max length of $max_len characters."
    exit 3
  fi
  if ! echo "$name" | grep -qP "$pattern"; then
    echo "[ERROR] $label '$name' contains invalid characters. Pattern: $pattern"
    exit 3
  fi
  echo "[OK] $label: $name"
}

validate_name "$RESOURCE_GROUP_NAME" 90  '^[a-zA-Z0-9\-_\.]+$'          "Resource Group"
validate_name "$CAE_NAME"           60  '^[a-zA-Z0-9\-]+$'              "Container Apps Environment"
validate_name "$SQL_SERVER_NAME"    63  '^[a-z][a-z0-9\-]+[a-z0-9]$'   "SQL Server"
validate_name "$SQL_DATABASE_NAME"  128 '^[a-zA-Z0-9\-_]+$'             "SQL Database"

echo "[PASS] All resource names are valid."
```

---

### Step 5 — Validate and Secure SQL Admin Password

Confirm a password has been provided, enforce complexity rules, and store it in the session secret store.

```bash
echo "=== Step 5: Validate SQL Admin Password ==="

SQL_PASS_RAW=$(echo "$PARSED_OUTPUT" | jq -r '.parsed.sql_admin_password_raw // empty')

if [ -z "$SQL_PASS_RAW" ]; then
  # Prompt interactively if no password was found
  read -r -s -p "[INPUT REQUIRED] Enter SQL admin password (min 12 chars, upper+lower+digit+special): " SQL_PASS_RAW
  echo ""
fi

# Complexity checks
length=${#SQL_PASS_RAW}
has_upper=$(echo "$SQL_PASS_RAW" | grep -cP '[A-Z]' || true)
has_lower=$(echo "$SQL_PASS_RAW" | grep -cP '[a-z]' || true)
has_digit=$(echo "$SQL_PASS_RAW" | grep -cP '[0-9]' || true)
has_special=$(echo "$SQL_PASS_RAW" | grep -cP '[^a-zA-Z0-9]' || true)

fail=0
[ "$length" -lt 12 ] && echo "[ERROR] Password must be at least 12 characters." && fail=1
[ "$has_upper" -eq 0 ] && echo "[ERROR] Password must contain at least one uppercase letter." && fail=1
[ "$has_lower" -eq 0 ] && echo "[ERROR] Password must contain at least one lowercase letter." && fail=1
[ "$has_digit" -eq 0 ] && echo "[ERROR] Password must contain at least one digit." && fail=1
[ "$has_special" -eq 0 ] && echo "[ERROR] Password must contain at least one special character." && fail=1

[ "$fail" -eq 1 ] && exit 4

# Store securely — write only to session secret store, never plaintext
echo "$SQL_PASS_RAW" | agent-secret-store write "sql_admin_password" --session "$SESSION_ID"
echo "[PASS] SQL admin password meets complexity requirements and has been stored securely."
```

---

### Step 6 — Validate Region Availability for Required Services

Confirm that Azure Container Apps and Azure SQL Database are available in the selected region.

```bash
echo "=== Step 6: Validate Region Service Availability ==="

REGION=$(echo "$PARSED_OUTPUT" | jq -r '.parsed.region')

# Check Container Apps provider registration and location
CA_LOCATIONS=$(az provider show \
  --namespace Microsoft.App \
  --query "resourceTypes[?resourceType=='containerApps'].locations[]" \
  --output tsv 2>/dev/null | tr '[:upper:]' '[:lower:]' | tr -d ' ')

# Normalise region for comparison
REGION_NORMALISED=$(echo "$REGION" | tr -d ' ' | tr '[:upper:]' '[:lower:]')

if ! echo "$CA_LOCATIONS" | grep -q "$REGION_NORMALISED"; then
  echo "[ERROR] Azure Container Apps is not available in region '$REGION'."
  echo "Available regions: $CA_LOCATIONS"
  exit 5
fi
echo "[OK] Azure Container Apps available in $REGION."

# Check SQL provider
SQL_LOCATIONS=$(az provider show \
  --namespace Microsoft.Sql \
  --query "resourceTypes[?resourceType=='servers'].locations[]" \
  --output tsv 2>/dev/null | tr '[:upper:]' '[:lower:]' | tr -d ' ')

if ! echo "$SQL_LOCATIONS" | grep -q "$REGION_NORMALISED"; then
  echo "[ERROR] Azure SQL Database is not available in region '$REGION'."
  exit 5
fi
echo "[OK] Azure SQL Database available in $REGION."

echo "[PASS] All required services available in selected region."
```

---

### Step 7 — Confirm Required Azure Resource Providers Are Registered

```bash
echo "=== Step 7: Verify Resource Provider Registration ==="

required_providers=(
  "Microsoft.App"
  "Microsoft.Sql"
  "Microsoft.ContainerRegistry"
  "Microsoft.OperationalInsights"
  "Microsoft.Insights"
  "Microsoft.Network"
)

for provider in "${required_providers[@]}"; do
  state=$(az provider show --namespace "$provider" --query "registrationState" -o tsv 2>/dev/null || echo "NotFound")
  if [ "$state" == "Registered" ]; then
    echo "[OK] $provider — Registered"
  elif [ "$state" == "Registering" ]; then
    echo "[WARN] $provider — Currently registering. May need to wait before Phase 2."
  else
    echo "[ACTION] Registering $provider..."
    az provider register --namespace "$provider" --wait
    echo "[OK] $provider — Registration initiated."
  fi
done

echo "[PASS] All required resource providers registered."
```

---

### Step 8 — Assemble and Write `validated_inputs` Artefact

```bash
echo "=== Step 8: Assemble validated_inputs Artefact ==="

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
WARNINGS=$(echo "$PARSED_OUTPUT" | jq '.warnings')

validated_inputs=$(jq -n \
  --arg sub_id        "$SUBSCRIPTION_ID" \
  --arg sub_name      "$SUBSCRIPTION_NAME" \
  --arg tenant_id     "$TENANT_ID" \
  --arg region        "$REGION" \
  --arg rg            "$RESOURCE_GROUP_NAME" \
  --arg cae_name      "$CAE_NAME" \
  --arg sql_server    "$SQL_SERVER_NAME" \
  --arg sql_db        "$SQL_DATABASE_NAME" \
  --arg sql_user      "$(echo "$PARSED_OUTPUT" | jq -r '.parsed.sql_admin_username')" \
  --arg image_tag     "$(echo "$PARSED_OUTPUT" | jq -r '.parsed.image_tag')" \
  --arg env_tier      "$ENVIRONMENT_TIER" \
  --arg session_id    "$SESSION_ID" \
  --arg repo_url      "https://github.com/Azure-Samples/container-apps-store-api-microservice" \
  --arg prefix        "$NAMING_PREFIX" \
  --arg timestamp     "$TIMESTAMP" \
  --argjson warnings  "$WARNINGS" \
  '{
    subscription_id:              $sub_id,
    subscription_name:            $sub_name,
    tenant_id:                    $tenant_id,
    region:                       $region,
    resource_group_name:          $rg,
    container_apps_env_name:      $cae_name,
    container_apps_env_location:  $region,
    sql_server_name:              $sql_server,
    sql_database_name:            $sql_db,
    sql_admin_username:           $sql_user,
    sql_admin_password:           "[SENSITIVE — stored in session secret store]",
    image_tag:                    $image_tag,
    environment_tier:             $env_tier,
    session_id:                   $session_id,
    microservice_repo_url:        $repo_url,
    naming_prefix:                $prefix,
    tags: {
      environment: $env_tier,
      managed_by:  "agent",
      skill:       "onlinestore-microservice-azure",
      session_id:  $session_id
    },
    validation_timestamp:  $timestamp,
    validation_warnings:   $warnings
  }')

echo "$validated_inputs" > validated_inputs.json
echo "[PASS] validated_inputs.json written."
cat validated_inputs.json
```

---

## Validation Criteria

The task is considered **successful** only when ALL of the following conditions are verified:

| # | Criterion | Verification Method |
|---|---|---|
| 1 | All four CLI tools are available and meet minimum version requirements | Exit code 0 from Step 1 |
| 2 | A valid, enabled Azure subscription is resolved | `az account show` returns `state == Enabled` |
| 3 | Tenant ID is non-null and a valid GUID format | Regex `^[a-f0-9\-]{36}$` |
| 4 | Selected region supports both Azure Container Apps and Azure SQL Database | Provider location list contains region slug |
| 5 | All resource names pass Azure naming rule validation | Step 4 exits 0 |
| 6 | SQL admin password meets Azure SQL complexity requirements | Step 5 all checks pass |
| 7 | All 6 resource providers are in `Registered` or `Registering` state | Step 7 loop exits 0 |
| 8 | `validated_inputs.json` is written and parseable by `jq` | `jq . validated_inputs.json` exits 0 |

---

## Error Handling

| Exit Code | Meaning | Remediation |
|---|---|---|
| `1` | Missing required CLI tool | Install the missing tool, then retry the phase |
| `2` | Azure login failure or subscription not found | Run `az login` or verify `AZURE_SUBSCRIPTION_ID`; phase gate triggers retry |
| `3` | Resource name validation failure | Adjust naming inputs or allow auto-derivation; phase gate triggers retry |
| `4` | SQL password complexity failure | Re-supply a compliant password; phase gate triggers retry |
| `5` | Required Azure service unavailable in region | Choose a supported region; phase gate triggers retry |

All errors write a structured error payload to `gather_inputs_error.json`:

```json
{
  "task": "gather-inputs",
  "exit_code": 3,
  "step_failed": 4,
  "message": "Resource Group name 'rg-my store' contains invalid character: space",
  "retry_eligible": true,
  "timestamp": "2025-01-15T10:22:00Z"
}
```

---

## Phase Gate Contribution

This task produces `validated_inputs.json` which is the primary artefact evaluated by the **Phase 1 gate**: _Pre-Provisioning Validated?_

The gate passes when `validated_inputs.json` is present, all fields are non-null, `validation_timestamp` is set, and no `gather_inputs_error.json` exists in the working directory. On gate failure, the phase retries from this task with prior artefacts available in `context.prior_artefacts` to avoid re-prompting for already-resolved values.