# Phase 1: Pre-Provisioning Validation

**Skill:** `onlinestore-microservice-azure` · **Version:** 1.0.0 · **Author:** Vishal Anand
**Phase:** 1 of 4 · **Followed By:** Phase 2 — Container Apps Environment

---

## 1. PURPOSE

Pre-Provisioning Validation is the mandatory gate that protects every downstream phase of the `onlinestore-microservice-azure` deployment from silent, compounding failures. Azure Container Apps, Azure SQL Database, and the microservice workload from `Azure-Samples/container-apps-store-api-microservice` each carry strict prerequisite dependencies: correct subscription quotas, registered resource providers, a properly authenticated CLI session, network address space availability, and a confirmed ability to pull public container images. Without this phase, you will discover missing dependencies mid-deployment — after partial resources have been created — leaving orphaned resource groups, billing-active SQL servers with no workload, and Container Apps Environments in a broken state that must be manually torn down.

This phase also establishes ground truth for every parameterized value that flows forward: the Azure region, resource group name, SQL administrator credentials, Container Apps Environment name, and Log Analytics workspace name are all validated and locked here. Any agent or human operator picking up Phase 2 can trust these values without re-querying. This is critical for idempotent re-runs — if Phase 2 or beyond fails and the operator retries, Phase 1 outputs prevent drift in naming conventions or region selection that would cause resource conflicts.

Without this phase, the most common failure modes for `onlinestore-microservice-azure` are: (a) `Microsoft.App` resource provider not registered, causing a cryptic `InvalidResourceNamespace` error 10–15 minutes into the Container Apps Environment deployment; (b) subscription-level vCPU quotas exhausted for the target region, causing silent Container App revision failures; and (c) the GitHub repository `Azure-Samples/container-apps-store-api-microservice` being unreachable or having structural changes that break the expected `deploy` manifests. All three are detected in under two minutes during this phase at zero cost.

---

## 2. KEY ACTIVITIES

- **Validate Azure CLI authentication and active subscription.** Confirm `az account show` returns a subscription with the expected Subscription ID and that the principal (user, service principal, or managed identity) has at minimum `Contributor` role on the subscription or on a pre-existing resource group. Capture the `tenantId`, `id` (subscription ID), and `user.name` for embedding in Phase 1 outputs.

- **Verify all required Azure resource providers are registered.** The following providers must be in `Registered` state: `Microsoft.App` (Container Apps), `Microsoft.OperationalInsights` (Log Analytics), `Microsoft.ContainerRegistry` (optional but needed if a private registry is used), `Microsoft.Sql` (Azure SQL Database), `Microsoft.Network` (VNet, if deploying in a custom VNet), and `Microsoft.Insights` (Application Insights). Registration can take 2–5 minutes; the agent must poll until confirmed.

- **Check subscription-level quotas for the target region.** Query the regional quota for `Standard_D2s_v3` or `Consumption` plan Container App cores, and verify at least 4 vCPUs are available. For Azure SQL Database, confirm the subscription has not hit the limit of 2000 DTUs or the server count cap (typically 20 logical SQL servers per subscription in some tier configurations). Use `az vm list-usage` and `az sql server list` to baseline current usage.

- **Resolve and lock deployment parameters.** Interactively or from environment variables, collect and validate: `RESOURCE_GROUP` (must match `^[a-zA-Z0-9._\-]{1,90}$`), `LOCATION` (must be a valid Azure region that supports Container Apps — not all regions do; validate against the known allowlist), `CONTAINER_APP_ENV_NAME`, `LOG_ANALYTICS_WORKSPACE_NAME`, `SQL_SERVER_NAME` (globally unique, 1–63 chars, lowercase alphanumeric and hyphens), `SQL_ADMIN_USERNAME` (not `admin`, `administrator`, `root`, `guest`, or `public`), and `SQL_ADMIN_PASSWORD` (must meet Azure complexity rules: 8–128 chars, three of four character classes).

- **Validate Azure Container Apps region availability.** Container Apps is not available in every Azure region. Programmatically query `az provider show --namespace Microsoft.App --query "resourceTypes[?resourceType=='containerApps'].locations"` and confirm the target `LOCATION` is in the returned list. Common supported regions include `eastus`, `westeurope`, `australiaeast`, `northeurope`; regions like `westcentralus` may not support it.

- **Confirm network address space availability (if custom VNet is requested).** If the deployment uses a custom VNet (recommended for production), validate that the CIDR block `/23` (minimum required for Container Apps Environment with custom VNet) does not overlap with any existing VNet in the subscription's target region. Retrieve existing VNets with `az network vnet list --query "[].{name:name, addressSpace:addressSpace.addressPrefixes}"` and perform CIDR overlap detection.

- **Validate GitHub repository accessibility and structure.** Perform a `git ls-remote https://github.com/Azure-Samples/container-apps-store-api-microservice` to confirm the repository is publicly reachable from the executing environment. Then perform a shallow clone (`git clone --depth 1`) and verify the presence of expected deployment artifacts: `deploy/` directory, individual service Dockerfiles (`node-app/`, `python-app/`, `go-app/` or equivalent), and any `bicep/` or `azuredeploy.json` IaC files. Record the HEAD commit SHA for traceability.

- **Validate Docker/container image pull capability.** The microservice references base images from Docker Hub (`node:18-alpine`, `python:3.11-slim`, etc.) and potentially MCR (`mcr.microsoft.com/dotnet/aspnet`). From the execution environment, confirm these can be reached with `docker pull --dry-run` or by querying the registry manifest endpoint via `curl`. If the agent is running in an air-gapped or corporate proxy environment, flag this and record the proxy configuration needed for Phase 4 image build steps.

---

## 3. TECHNICAL GUIDANCE

### 3.1 — Authentication and Subscription Validation

```bash
# Confirm login and capture subscription context
az account show --output json | tee /tmp/oasm_subscription_context.json

# Extract key fields for validation
SUBSCRIPTION_ID=$(az account show --query id -o tsv)
TENANT_ID=$(az account show --query tenantId -o tsv)
PRINCIPAL=$(az account show --query user.name -o tsv)

echo "Subscription: $SUBSCRIPTION_ID"
echo "Tenant:       $TENANT_ID"
echo "Principal:    $PRINCIPAL"

# Validate Contributor or Owner role on subscription
az role assignment list \
  --assignee "$PRINCIPAL" \
  --scope "/subscriptions/$SUBSCRIPTION_ID" \
  --query "[?roleDefinitionName=='Contributor' || roleDefinitionName=='Owner'].roleDefinitionName" \
  -o tsv
```

Expected output: `Contributor` or `Owner`. If empty, check resource-group-scoped assignments or escalate.

### 3.2 — Resource Provider Registration

```bash
# Required providers for onlinestore-microservice-azure
REQUIRED_PROVIDERS=(
  "Microsoft.App"
  "Microsoft.OperationalInsights"
  "Microsoft.Sql"
  "Microsoft.Insights"
  "Microsoft.Network"
)

for PROVIDER in "${REQUIRED_PROVIDERS[@]}"; do
  STATE=$(az provider show --namespace "$PROVIDER" --query "registrationState" -o tsv 2>/dev/null)
  if [ "$STATE" != "Registered" ]; then
    echo "Registering $PROVIDER..."
    az provider register --namespace "$PROVIDER" --wait
  else
    echo "$PROVIDER is already Registered."
  fi
done
```

The `--wait` flag blocks until registration completes. For `Microsoft.App`, this can take up to 5 minutes on a fresh subscription.

### 3.3 — Parameter Validation and Locking

```bash
# Load from environment or prompt
: "${LOCATION:=eastus}"
: "${RESOURCE_GROUP:=rg-onlinestore-prod}"
: "${CONTAINER_APP_ENV_NAME:=cae-onlinestore-prod}"
: "${LOG_ANALYTICS_WORKSPACE_NAME:=law-onlinestore-prod}"
: "${SQL_SERVER_NAME:=sql-onlinestore-prod}"
: "${SQL_ADMIN_USERNAME:=onlinestoreadmin}"

# Validate LOCATION supports Container Apps
SUPPORTED_LOCATIONS=$(az provider show \
  --namespace Microsoft.App \
  --query "resourceTypes[?resourceType=='containerApps'].locations[]" \
  -o tsv | tr '[:upper:]' '[:lower:]' | tr ' ' '\n' | sed 's/ //g')

LOCATION_LOWER=$(echo "$LOCATION" | tr '[:upper:]' '[:lower:]')
if ! echo "$SUPPORTED_LOCATIONS" | grep -qx "$LOCATION_LOWER"; then
  echo "ERROR: $LOCATION does not support Azure Container Apps."
  exit 1
fi

# Validate SQL server name global uniqueness
AVAILABILITY=$(az sql server list \
  --query "[?name=='$SQL_SERVER_NAME'] | length(@)" -o tsv 2>/dev/null)
if [ "$AVAILABILITY" != "0" ]; then
  echo "WARNING: SQL server name '$SQL_SERVER_NAME' already exists in your subscription."
fi

# Validate SQL admin password complexity
validate_password() {
  local pass="$1"
  local len=${#pass}
  local classes=0
  [[ "$pass" =~ [A-Z] ]] && ((classes++))
  [[ "$pass" =~ [a-z] ]] && ((classes++))
  [[ "$pass" =~ [0-9] ]] && ((classes++))
  [[ "$pass" =~ [^A-Za-z0-9] ]] && ((classes++))
  if [ "$len" -lt 8 ] || [ "$len" -gt 128 ] || [ "$classes" -lt 3 ]; then
    echo "ERROR: SQL_ADMIN_PASSWORD does not meet Azure complexity requirements."
    return 1
  fi
  echo "Password complexity: PASSED"
}
validate_password "$SQL_ADMIN_PASSWORD"
```

### 3.4 — GitHub Repository Validation

```bash
# Confirm repo is reachable
git ls-remote https://github.com/Azure-Samples/container-apps-store-api-microservice \
  HEAD 2>&1 | head -1

# Shallow clone and structural validation
TMPDIR=$(mktemp -d)
git clone --depth 1 \
  https://github.com/Azure-Samples/container-apps-store-api-microservice \
  "$TMPDIR/store-api" 2>&1

HEAD_SHA=$(git -C "$TMPDIR/store-api" rev-parse HEAD)
echo "Repo HEAD SHA: $HEAD_SHA"

# Verify expected structure
REQUIRED_PATHS=(
  "deploy"
  "node-app"
  "python-app"
)
for PATH_CHECK in "${REQUIRED_PATHS[@]}"; do
  if [ ! -d "$TMPDIR/store-api/$PATH_CHECK" ] && [ ! -f "$TMPDIR/store-api/$PATH_CHECK" ]; then
    echo "ERROR: Expected path '$PATH_CHECK' not found in repository."
  else
    echo "FOUND: $PATH_CHECK"
  fi
done
```

### 3.5 — Quota Check

```bash
# Check Container App consumption quota in target region
az vm list-usage \
  --location "$LOCATION" \
  --query "[?name.value=='cores'].{limit:limit, current:currentValue}" \
  -o table

# Count existing SQL servers (cap is typically 20 per subscription)
az sql server list --query "length(@)" -o tsv
```

### 3.6 — Output Manifest (written at end of phase)

```json
{
  "phase": "pre-provisioning-validation",
  "timestamp": "2024-01-01T00:00:00Z",
  "subscription_id": "<captured>",
  "tenant_id": "<captured>",
  "principal": "<captured>",
  "location": "eastus",
  "resource_group": "rg-onlinestore-prod",
  "container_app_env_name": "cae-onlinestore-prod",
  "log_analytics_workspace_name": "law-onlinestore-prod",
  "sql_server_name": "sql-onlinestore-prod",
  "sql_admin_username": "onlinestoreadmin",
  "repo_head_sha": "<captured>",
  "providers_registered": ["Microsoft.App", "Microsoft.OperationalInsights", "Microsoft.Sql", "Microsoft.Insights", "Microsoft.Network"],
  "validation_status": "PASSED"
}
```

---

## 4. DECISION LOGIC

**IF** `az account show` returns a non-zero exit code or empty subscription ID,
**THEN** halt immediately and prompt the operator to run `az login` (interactive) or `az login --service-principal -u <appId> -p <password> --tenant <tenantId>` (automated), and re-run Phase 1 from the beginning.
**ELSE** capture subscription context and proceed to provider validation.

---

**IF** any required provider is in state `NotRegistered` or `Unregistering`,
**THEN** execute `az provider register --namespace <provider> --wait` and poll until state is `Registered`. If registration fails or times out after 10 minutes,
**THEN** log the failure and exit with error code 2 (provider registration failure).
**ELSE** mark provider as validated and continue.

---

**IF** the target `LOCATION` is not in the list of regions supporting `Microsoft.App/containerApps`,
**THEN** prompt the operator to select an alternative region from the validated allowlist (e.g., `eastus`, `westeurope`, `australiaeast`, `northeurope`, `eastasia`), update `LOCATION`, and re-run location validation.
**ELSE** lock the `LOCATION` parameter in the output manifest.

---

**IF** `SQL_SERVER_NAME` already exists in the current subscription,
**THEN** append a 4-character random suffix (e.g., `sql-onlinestore-prod-x7k2`) and re-validate uniqueness. Log the rename in the output manifest.
**ELSE** use the original name.

---

**IF** the GitHub repository shallow clone fails with a network error (exit code 128),
**THEN** check for proxy settings (`HTTP_PROXY`, `HTTPS_PROXY` environment variables), attempt clone with `--config http.proxy=$HTTPS_PROXY`, and if that also fails, alert the operator that outbound GitHub access is required and the deployment cannot proceed in the current network environment.
**ELSE IF** the clone succeeds but required paths (`deploy/`, `node-app/`, `python-app/`) are missing,
**THEN** log a structural mismatch warning, record the HEAD SHA, and flag for manual review before proceeding — the microservice deployment steps in Phase 4 may need path adjustments.
**ELSE** record HEAD SHA and mark repository as validated.

---

**IF** SQL admin username is one of the reserved words: `admin`, `administrator`, `root`, `guest`, `public`, `sa`, `sysadmin`,
**THEN** reject the value, prompt for a replacement, and re-validate.
**ELSE** accept and lock the username.

---

**IF** password complexity validation fails,
**THEN** do NOT log the attempted password value anywhere. Prompt the operator to supply a new password meeting requirements: 8–128 characters, at least 3 of 4 character classes (uppercase, lowercase, digits, special characters). Re-validate without proceeding.
**ELSE** store a SHA-256 hash of the password in the output manifest for audit (never the plaintext value), and store the plaintext in Azure Key Vault or as a session environment variable only.

---

## 5. DECISION GATE

> **DECISION GATE — Pre-Provisioning Validated?**
>
> ALL of the following must be true to proceed to Phase 2:
>
> - [ ] `az account show` returns a valid Subscription ID and the authenticated principal has `Contributor` or `Owner` role on the subscription or target resource group scope
> - [ ] `Microsoft.App` provider registration state is `Registered`
> - [ ] `Microsoft.OperationalInsights` provider registration state is `Registered`
> - [ ] `Microsoft.Sql` provider registration state is `Registered`
> - [ ] `Microsoft.Insights` provider registration state is `Registered`
> - [ ] `Microsoft.Network` provider registration state is `Registered`
> - [ ] Target `LOCATION` (e.g., `eastus`) is confirmed in the Azure Container Apps supported regions list
> - [ ] `RESOURCE_GROUP` name matches `^[a-zA-Z0-9._\-]{1,90}$` and does not conflict with an existing resource group in a different region
> - [ ] `SQL_SERVER_NAME` is globally unique (or has been auto-suffixed and re-validated)
> - [ ] `SQL_ADMIN_USERNAME` is not a reserved word and passes Azure naming rules
> - [ ] `SQL_ADMIN_PASSWORD` passes Azure complexity validation (length 8–128, 3 of 4 character classes)
> - [ ] `git ls-remote https://github.com/Azure-Samples/container-apps-store-api-microservice` returns exit code 0 and a valid HEAD SHA
> - [ ] Shallow clone of the repository confirms presence of `deploy/`, `node-app/`, and `python-app/` directories
> - [ ] Subscription quota check confirms available compute headroom in target region (minimum 4 cores available)
> - [ ] Phase 1 output manifest file (`/tmp/oasm_phase1_output.json`) has been written with `validation_status: PASSED`
>
> **If ANY criterion is not met:**
> 1. Log the specific failing criterion with details (e.g., which provider is not registered, which parameter failed validation).
> 2. Attempt automated remediation where applicable: run `az provider register`, auto-suffix conflicting names, re-prompt for invalid credentials.
> 3. Re-run the specific failed check after remediation — do NOT re-run the entire phase unless multiple items failed.
> 4. If automated remediation is not possible (e.g., insufficient quota, no GitHub access), halt with a human-readable error message identifying the exact blocker and the manual steps required.
> 5. Do NOT proceed to Phase 2 under any condition until all 15 criteria above are marked passing.

---

## 6. OUTPUTS

| Output | Type | Location | Description |
|---|---|---|---|
| `oasm_phase1_output.json` | JSON manifest | `/tmp/oasm_phase1_output.json` | Locked deployment parameters, subscription context, repo HEAD SHA, provider states, and overall validation status |
| `oasm_subscription_context.json` | JSON | `/tmp/oasm_subscription_context.json` | Raw output of `az account show` for audit and traceability |
| `oasm_provider_states.txt` | Text log | `/tmp/oasm_provider_states.txt` | Timestamped registration state for each required resource provider |
| `oasm_repo_structure.txt` | Text log | `/tmp/oasm_repo_structure.txt` | Output of `find $TMPDIR/store-api -maxdepth 2 -type f` confirming repo structure at validated SHA |
| `oasm_quota_snapshot.json` | JSON | `/tmp/oasm_quota_snapshot.json` | Output of `az vm list-usage` for the target region at time of validation |
| Environment variables (session-scoped) | Shell exports | Current shell session | `SUBSCRIPTION_ID`, `TENANT_ID`, `LOCATION`, `RESOURCE_GROUP`, `CONTAINER_APP_ENV_NAME`, `LOG_ANALYTICS_WORKSPACE_NAME`, `SQL_SERVER_NAME`, `SQL_ADMIN_USERNAME`, `SQL_ADMIN_PASSWORD` (plaintext, session only, never written to disk) |
| `oasm_phase1_checklist.md` | Markdown | `/tmp/oasm_phase1_checklist.md` | Human-readable checklist with all 15 gate criteria marked PASS/FAIL with details — suitable for handoff documentation |

---

## 7. ANTI-PATTERNS

### Anti-Pattern 1: Skipping Provider Registration Check Because "It Was Registered Last Week"

**Mistake:** Assuming `Microsoft.App` is registered because the operator previously deployed a Container App in a different subscription or because it was registered on a test subscription. Provider registration is **per-subscription**, not per-tenant or per-account.

**Consequence:** Phase 2 fails 8–12 minutes into the Container Apps Environment creation with error `The subscription is not registered to use namespace 'Microsoft.App'`. At this point, a partially created resource group exists, and the operator must debug the failure, register the provider, and re-run Phase 2 — all while the resource group exists and could accumulate other partial resources on retry.

**Correct approach:** Always programmatically query the registration state for all five required providers at Phase 1 runtime, regardless of assumed prior state.

---

### Anti-Pattern 2: Hardcoding `eastus` Without Validating Container Apps Availability

**Mistake:** Assuming `eastus` or any other popular region supports all required services and bypassing the region availability check because "of course that region supports it."

**Consequence:** Azure Container Apps has a limited and expanding set of supported regions. If the operator's organization has a policy mandating a specific region (e.g., `germanywestcentral` for data residency) that does not yet support `Microsoft.App/containerApps`, Phase 2 fails immediately with `Resource type 'containerApps' not supported in location`. The operator loses time, and all planned resource naming becomes tied to an invalid location that requires renaming in subsequent retry attempts.

**Correct approach:** Dynamically query the provider's supported locations at runtime and validate the target region against this live list. Never hardcode or assume region availability for Container Apps.

---

### Anti-Pattern 3: Writing SQL Credentials to the Phase 1 Output Manifest in Plaintext

**Mistake:** Storing `SQL_ADMIN_PASSWORD` in plaintext inside `oasm_phase1_output.json` for "convenience" so that downstream phases (Phase 3: SQL Database Provisioning) can read the password without re-prompting.

**Consequence:** The manifest file written to `/tmp/` is world-readable on most Linux systems by default. In a CI/CD pipeline, it may be captured in build artifacts, logged in stdout, or uploaded to blob storage for audit. The SQL admin password is then exposed in plaintext across multiple systems, violating least-privilege and secrets-management requirements. Additionally, this violates Azure's security baseline recommendations for Azure SQL.

**Correct approach:** Store `SQL_ADMIN_PASSWORD` only as a session environment variable (exported, not written to disk), or inject it into Azure Key Vault during Phase 1 using `az keyvault secret set` and reference only the Key Vault secret URI in downstream phases. Record the Key Vault secret URI (not the value) in the manifest.

---

### Anti-Pattern 4: Treating `git ls-remote` Success as Sufficient Repository Validation

**Mistake:** Running `git ls-remote` to confirm the repo is reachable and marking the repository check as passed without performing a shallow clone and structural validation.

**Consequence:** The `Azure-Samples/container-apps-store-api-microservice` repository may be reachable but may have undergone structural refactoring (directory renames, removed Dockerfiles, changed deploy manifests) since the skill was authored. Phase 4 instructions reference specific paths (`node-app/`, `python-app/`, `deploy/`) that may no longer exist at those paths. This causes Phase 4 to fail with `path not found` errors mid-deployment after SQL and Container Apps infrastructure has already been provisioned at cost.

**Correct approach:** Always perform a shallow clone, record the HEAD SHA, and programmatically verify all expected paths used by Phase 4 exist at that commit. Flag structural mismatches before spending on infrastructure.

---

## 8. AGENT INSTRUCTIONS

The following numbered steps are the precise execution sequence for an AI agent running Phase 1 of `onlinestore-microservice-azure`. Execute each step in order. Do not skip steps. If any step fails, follow the stated remediation before proceeding to the next step.

1. **Initialize working directory and log file.** Create `/tmp/oasm_phase1.log` and begin writing timestamped entries for all actions. Write header: `onlinestore-microservice-azure Phase 1: Pre-Provisioning Validation — started at <ISO8601 timestamp>`.

2. **Check Azure CLI availability.** Run `az version --output json`. If exit code is non-zero, halt and emit: `ERROR: Azure CLI not found. Install from https://learn.microsoft.com/cli/azure/install-azure-cli and re-run.` Do not proceed.

3. **Validate Azure authentication.** Run `az account show --output json`. If exit code is non-zero, run `az login` (interactive) or surface the appropriate service principal login command. Re-run `az account show`. If still failing, halt with auth error. On success, write the full JSON output to `/tmp/oasm_subscription_context.json` and extract `SUBSCRIPTION_ID`, `TENANT_ID`, and `PRINCIPAL` into session environment variables.

4. **Confirm RBAC permissions.** Run `az role assignment list --assignee "$PRINCIPAL" --scope "/subscriptions/$SUBSCRIPTION_ID" --query "[?roleDefinitionName=='Contributor' || roleDefinitionName=='Owner'].roleDefinitionName" -o tsv`. If the result is empty, check resource-group-level assignments. If no sufficient role is found, halt with: `ERROR: Principal lacks Contributor or Owner role. Grant access at https://portal.azure.com/#blade/Microsoft_AAD_IAM/ActiveDirectoryMenuBlade/RegisteredApps and re-run.`

5. **Collect and validate deployment parameters.** For each of the following parameters, check if already set as an environment variable; if not, prompt the operator for input. After collection, run all validation regexes and rules defined in Section 3.3. Parameters: `LOCATION`, `RESOURCE_GROUP`, `CONTAINER_APP_ENV_NAME`, `LOG_ANALYTICS_WORKSPACE_NAME`, `SQL_SERVER_NAME`, `SQL_ADMIN_USERNAME`, `SQL_ADMIN_PASSWORD`. On any validation failure, prompt for corrected input and re-validate. Do not proceed until all pass.

6. **Validate Container Apps region availability.** Execute the `az provider show` query from Section 3.3 to retrieve supported locations for `Microsoft.App/containerApps`. Normalize the target `LOCATION` to lowercase and compare. If not found in the list, output the full list of supported regions and prompt the operator to choose one. Update `LOCATION` and re-validate.

7. **Check and register required resource providers.** For each provider in `[Microsoft.App, Microsoft.OperationalInsights, Microsoft.Sql, Microsoft.Insights, Microsoft.Network]`, query current registration state. For any not in `Registered` state, run `az provider register --namespace <provider> --wait`. After each registration, re-query to confirm state is `Registered`. Write all states to `/tmp/oasm_provider_states.txt` with timestamps. If any provider fails to reach `Registered` state after 10 minutes, halt with provider-specific error.

8. **Run subscription quota check.** Execute `az vm list-usage --location "$LOCATION" --output json` and write to `/tmp/oasm_quota_snapshot.json`. Parse the `cores` entry and confirm `limit - currentValue >= 4`. If headroom is insufficient, report current usage and limit and halt with: `ERROR: Insufficient core quota in $LOCATION. Request quota increase at https://portal.azure.com/#blade/Microsoft_Azure_Capacity/QuotaMenuBlade`.

9. **Validate SQL server name uniqueness.** Run `az sql server list --query "[?name=='$SQL_SERVER_NAME'] | length(@)" -o tsv`. If result is `1`, auto-generate a 4-character lowercase alphanumeric suffix, append it to `SQL_SERVER_NAME`, update the environment variable, and log the rename. Re-run the check to confirm the new name is unique.

10. **Validate GitHub repository accessibility.** Run `git ls-remote https://github.com/Azure-Samples/container-apps-store-api-microservice HEAD`. If exit code is non-zero, check `HTTPS_PROXY` and retry with proxy. If still failing, halt with network access error. If successful, record the returned SHA.

11. **Shallow clone repository and validate structure.** Clone to `$(mktemp -d)/store-api` with `--depth 1`. Capture HEAD SHA with `git rev-parse HEAD`. Check for existence of `deploy/`, `node-app/`, and `python-app/` directories. Run `find <clonedir> -maxdepth 2 -type f > /tmp/oasm_repo_structure.txt`. If any required path is missing, log a structural mismatch warning with the HEAD SHA and flag for manual review — do NOT auto-fail, but mark the criterion as `WARN` rather than `PASS` in the output manifest.

12. **Write Phase 1 output manifest.** Populate `/tmp/oasm_phase1_output.json` using the template from Section 3.6 with all captured values. Set `validation_status` to `PASSED` only if all 15 gate criteria are met. If any are `WARN` or `FAIL`, set to `WARN` or `FAILED` respectively.

13. **Evaluate Decision Gate.** Review all 15 criteria from Section 5 against the output manifest. If all are `PASS`, emit: `Phase 1: Pre-Provisioning Validation — COMPLETE. Proceed to Phase 2: Container Apps Environment.` If any are `FAIL`, list each failing criterion, the specific value or error, and the exact remediation step from Section 4. Re-run only the failed checks after remediation. If any are `WARN`, surface the warning to the operator and request explicit confirmation before proceeding.

14. **Write human-readable checklist.** Generate `/tmp/oasm_phase1_checklist.md` with all 15 gate criteria, their PASS/FAIL/WARN status, and any captured values (excluding `SQL_ADMIN_PASSWORD`). This file is the handoff artifact to the operator or to the Phase 2 agent.

15. **Export validated environment variables.** Export all locked parameters as session environment variables for use by Phase 2. Confirm each export with `echo "Exported: $VAR_NAME"`. Do NOT write `SQL_ADMIN_PASSWORD` to any file. If the execution environment supports Key Vault integration, run `az keyvault secret set --vault-name <keyvault> --name oasm-sql-admin-password --value "$SQL_ADMIN_PASSWORD"` and export only `SQL_ADMIN_PASSWORD_KV_URI` for downstream phases.