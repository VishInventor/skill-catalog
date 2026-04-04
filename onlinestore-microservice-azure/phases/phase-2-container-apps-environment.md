# Phase 2: Container Apps Environment

**Skill:** `onlinestore-microservice-azure` · **Version:** 1.0.0 · **Author:** Vishal Anand
**Phase Sequence:** Phase 1 (Pre-Provisioning Validation) → **Phase 2 (Container Apps Environment)** → Phase 3 (SQL Database Provisioning)

---

## 1. PURPOSE

Phase 2 establishes the foundational Azure infrastructure layer upon which the entire online store microservice deployment depends. Specifically, it creates the Azure Resource Group that serves as the logical boundary for all resources — Container Apps Environment, SQL Database, monitoring workspace, and identity constructs — ensuring that every downstream phase targets the same billing scope, region, and access control perimeter. Without a correctly provisioned Resource Group and Container Apps Environment, Phases 3 and 4 have no valid resource context in which to operate, and every subsequent `az` command will either fail with a "resource group not found" error or silently deploy to a wrong location.

The Azure Container Apps Environment is the runtime substrate that hosts all microservice containers deployed in Phase 4. The `container-apps-store-api-microservice` sample from Azure-Samples comprises multiple services (a Go-based order service, a Node.js storefront, a Python inventory service, and Dapr sidecar components). The Container Apps Environment configures the shared networking plane, Dapr runtime version, log analytics workspace binding, internal/external ingress DNS suffix, and workload profiles. If this environment is misconfigured — wrong region, wrong Dapr version, missing Log Analytics workspace linkage — the Dapr service invocation and pub/sub components used by the store microservice will fail at runtime in Phase 4.

Completing this phase also unlocks environment-level configuration that cannot be changed post-creation without full teardown: the virtual network integration, the Dapr instrumentation key binding, and the internal vs. external ingress mode. Getting these right here prevents costly re-provisioning cycles across all four phases. The exit gate for this phase is a hard prerequisite for Phase 3 because the SQL Database must be provisioned into the same Resource Group, and its private endpoint (if used) must bind to the same VNet configured in this phase.

---

## 2. KEY ACTIVITIES

- **Create the Azure Resource Group** in the target region (e.g., `eastus`) with a consistent naming convention (`rg-onlinestore-prod-eastus`) and apply mandatory tags (`environment=production`, `owner=vishal-anand`, `project=onlinestore-microservice-azure`, `cost-center=<value>`) so that all child resources inherit a taggable parent for cost attribution and policy compliance.

- **Register required Azure Resource Providers** — specifically `Microsoft.App`, `Microsoft.OperationalInsights`, `Microsoft.ContainerRegistry`, and `Microsoft.ServiceBus` — confirming `RegistrationState: Registered` for each before proceeding, because unregistered providers cause silent failures during environment creation that surface only as opaque ARM errors.

- **Create a Log Analytics Workspace** (`law-onlinestore-prod-eastus`) in the same Resource Group with a 30-day retention policy and `PerGB2018` SKU; capture the workspace ID (`customerId`) and the primary shared key, as both are mandatory inputs to the Container Apps Environment `--logs-workspace-id` and `--logs-workspace-key` parameters.

- **Create the Azure Container Apps Environment** (`cae-onlinestore-prod-eastus`) bound to the Log Analytics Workspace, with Dapr instrumentation enabled, in `eastus`, with `--internal-only false` to permit external ingress for the storefront service, and with `--enable-workload-profiles` enabled to support the Consumption workload profile used by the `container-apps-store-api-microservice` reference architecture.

- **Validate Dapr version compatibility** on the newly created environment by querying the environment's `daprAIInstrumentationKey` and `daprVersion` properties; the Azure-Samples microservice requires Dapr 1.9+ for the pub/sub and state store components it uses — if the environment has provisioned an older Dapr runtime, a manual upgrade flag must be applied before Phase 4 proceeds.

- **Record and persist environment output variables** — specifically `AZURE_ENVIRONMENT_NAME`, `AZURE_RESOURCE_GROUP`, `AZURE_LOCATION`, `AZURE_LAW_WORKSPACE_ID`, and `AZURE_CONTAINER_APPS_ENVIRONMENT_ID` — into a local `.env.phase2` file and, if running in CI/CD, into pipeline secret variables or Azure Key Vault, so Phase 3 and Phase 4 can consume them without re-querying ARM.

- **Verify environment provisioning state** by polling `az containerapp env show` until `provisioningState` returns `Succeeded` (not `InProgress` or `Updating`), implementing a retry loop with a 30-second interval and a 10-minute timeout ceiling; a `Failed` provisioning state requires reading the `statusDetails` field to determine whether the failure is a quota issue, a networking conflict, or a provider registration lag.

- **Validate network reachability and DNS suffix** by extracting the `defaultDomain` property from the provisioned environment (e.g., `<unique-id>.eastus.azurecontainerapps.io`) and confirming it resolves via `nslookup` or `Resolve-DnsName`; this domain suffix is required in Phase 4 for constructing Dapr service invocation URLs and for configuring the ingress hostname of the storefront container app.

---

## 3. TECHNICAL GUIDANCE

### 3.1 Resource Group Creation

```bash
# Set consistent variables — used across all phases
RESOURCE_GROUP="rg-onlinestore-prod-eastus"
LOCATION="eastus"
ENVIRONMENT_NAME="cae-onlinestore-prod-eastus"
LAW_NAME="law-onlinestore-prod-eastus"

# Create resource group with mandatory tags
az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --tags \
    environment=production \
    owner=vishal-anand \
    project=onlinestore-microservice-azure \
    phase=phase2 \
    created-by=agent

# Confirm creation
az group show --name "$RESOURCE_GROUP" --query "properties.provisioningState" -o tsv
# Expected output: Succeeded
```

### 3.2 Resource Provider Registration

```bash
# Register providers required for Container Apps and observability
for provider in \
  Microsoft.App \
  Microsoft.OperationalInsights \
  Microsoft.ContainerRegistry \
  Microsoft.ServiceBus \
  Microsoft.Web; do
  
  echo "Registering $provider..."
  az provider register --namespace "$provider" --wait
  
  state=$(az provider show --namespace "$provider" --query "registrationState" -o tsv)
  if [ "$state" != "Registered" ]; then
    echo "ERROR: $provider failed to register. State: $state"
    exit 1
  fi
  echo "$provider: $state"
done
```

### 3.3 Log Analytics Workspace Creation

```bash
# Create Log Analytics Workspace — required BEFORE Container Apps Environment
az monitor log-analytics workspace create \
  --resource-group "$RESOURCE_GROUP" \
  --workspace-name "$LAW_NAME" \
  --location "$LOCATION" \
  --sku PerGB2018 \
  --retention-time 30 \
  --tags environment=production project=onlinestore-microservice-azure

# Extract workspace ID and key — store immediately
LAW_WORKSPACE_ID=$(az monitor log-analytics workspace show \
  --resource-group "$RESOURCE_GROUP" \
  --workspace-name "$LAW_NAME" \
  --query "customerId" -o tsv)

LAW_PRIMARY_KEY=$(az monitor log-analytics workspace get-shared-keys \
  --resource-group "$RESOURCE_GROUP" \
  --workspace-name "$LAW_NAME" \
  --query "primarySharedKey" -o tsv)

echo "LAW_WORKSPACE_ID=$LAW_WORKSPACE_ID"
echo "LAW_PRIMARY_KEY=[REDACTED — stored securely]"
```

### 3.4 Container Apps Environment Creation

```bash
# Create the Container Apps Environment with Dapr and Log Analytics bound
az containerapp env create \
  --name "$ENVIRONMENT_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --logs-workspace-id "$LAW_WORKSPACE_ID" \
  --logs-workspace-key "$LAW_PRIMARY_KEY" \
  --enable-workload-profiles \
  --tags \
    environment=production \
    project=onlinestore-microservice-azure

# Poll for Succeeded state (max 10 minutes)
MAX_WAIT=600
ELAPSED=0
INTERVAL=30

while true; do
  STATE=$(az containerapp env show \
    --name "$ENVIRONMENT_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query "properties.provisioningState" -o tsv 2>/dev/null)

  echo "[$ELAPSED s] Provisioning state: $STATE"

  if [ "$STATE" = "Succeeded" ]; then
    echo "Container Apps Environment provisioned successfully."
    break
  elif [ "$STATE" = "Failed" ]; then
    echo "ERROR: Provisioning failed. Fetching status details..."
    az containerapp env show \
      --name "$ENVIRONMENT_NAME" \
      --resource-group "$RESOURCE_GROUP" \
      --query "properties" -o json
    exit 1
  fi

  if [ "$ELAPSED" -ge "$MAX_WAIT" ]; then
    echo "ERROR: Timed out waiting for environment to provision."
    exit 1
  fi

  sleep $INTERVAL
  ELAPSED=$((ELAPSED + INTERVAL))
done
```

### 3.5 Extract and Persist Environment Outputs

```bash
# Extract all required outputs for downstream phases
CONTAINER_APP_ENV_ID=$(az containerapp env show \
  --name "$ENVIRONMENT_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query "id" -o tsv)

DEFAULT_DOMAIN=$(az containerapp env show \
  --name "$ENVIRONMENT_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query "properties.defaultDomain" -o tsv)

STATIC_IP=$(az containerapp env show \
  --name "$ENVIRONMENT_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query "properties.staticIp" -o tsv)

# Write .env.phase2 for consumption by Phases 3 and 4
cat > .env.phase2 << EOF
AZURE_RESOURCE_GROUP=$RESOURCE_GROUP
AZURE_LOCATION=$LOCATION
AZURE_ENVIRONMENT_NAME=$ENVIRONMENT_NAME
AZURE_LAW_WORKSPACE_ID=$LAW_WORKSPACE_ID
AZURE_CONTAINER_APPS_ENVIRONMENT_ID=$CONTAINER_APP_ENV_ID
AZURE_CONTAINER_APPS_DEFAULT_DOMAIN=$DEFAULT_DOMAIN
AZURE_CONTAINER_APPS_STATIC_IP=$STATIC_IP
EOF

echo ".env.phase2 written successfully."
cat .env.phase2
```

### 3.6 DNS Validation

```bash
# Confirm default domain resolves — required for Phase 4 ingress wiring
nslookup "$DEFAULT_DOMAIN" || \
  echo "WARNING: DNS not yet propagated. Retry after 2-3 minutes."

# On Windows (PowerShell):
# Resolve-DnsName $DEFAULT_DOMAIN -ErrorAction SilentlyContinue
```

### 3.7 Dapr Version Check

```bash
# Confirm Dapr runtime version meets minimum requirement (1.9+)
DAPR_VERSION=$(az containerapp env show \
  --name "$ENVIRONMENT_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query "properties.daprAIInstrumentationKey" -o tsv 2>/dev/null || echo "not-set")

# Note: Dapr version is managed by Azure — verify via:
az containerapp env show \
  --name "$ENVIRONMENT_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query "properties" -o json | grep -i dapr
```

---

## 4. DECISION LOGIC

**IF** `az group show` returns `ResourceGroupNotFound` after creation attempt  
**THEN** check subscription context with `az account show`; confirm the agent has `Contributor` or `Owner` role on the subscription; re-run `az group create` with explicit `--subscription` flag  
**ELSE** record `provisioningState: Succeeded` and proceed

---

**IF** any provider in `[Microsoft.App, Microsoft.OperationalInsights, Microsoft.ContainerRegistry]` returns `RegistrationState: Registering` after the `--wait` flag completes  
**THEN** wait an additional 60 seconds and re-query; if still not `Registered` after 5 minutes, raise a support ticket for the subscription — this is a platform-side issue, not a configuration error  
**ELSE** continue to Log Analytics workspace creation

---

**IF** Log Analytics workspace creation fails with `WorkspaceAlreadyExists`  
**THEN** check whether an existing workspace in the same Resource Group has the name `law-onlinestore-prod-eastus`; if it does, re-use it by extracting its `customerId` and shared key; if it belongs to a different Resource Group, rename the new workspace with a suffix (e.g., `law-onlinestore-prod-eastus-2`) and update the environment variable  
**ELSE** proceed with the freshly created workspace

---

**IF** `az containerapp env create` fails with `InvalidWorkspaceKey`  
**THEN** the `LAW_PRIMARY_KEY` variable was not correctly captured; re-run the `get-shared-keys` command and confirm the key is not empty or truncated; check for shell quoting issues if the key contains special characters  
**ELSE** proceed with polling loop

---

**IF** `provisioningState` returns `Failed` during the polling loop  
**THEN** inspect `properties.statusDetails` for the error code:
  - `QuotaExceeded` → request quota increase for `Microsoft.App/managedEnvironments` in `eastus` and retry after approval
  - `SubnetConflict` → no VNet is configured in this phase (Consumption plan, no VNet injection), so this error indicates a subscription-level policy; contact the subscription owner
  - `InternalServerError` → wait 5 minutes and retry `az containerapp env create` with the same parameters (idempotent)  
**ELSE** if `Succeeded`, extract outputs and write `.env.phase2`

---

**IF** the `DEFAULT_DOMAIN` DNS lookup fails after 5 minutes post-provisioning  
**THEN** this is expected DNS propagation lag for new environments; wait up to 10 minutes before treating it as an error; do NOT proceed to Phase 4 ingress configuration until DNS resolves  
**ELSE** record `DEFAULT_DOMAIN` in `.env.phase2` and proceed

---

## 5. DECISION GATE

> **DECISION GATE — Created resource group and Deploy Container Apps Environment**
>
> ALL must be true to proceed to Phase 3 (SQL Database Provisioning):
>
> - [ ] `az group show --name rg-onlinestore-prod-eastus` returns `"provisioningState": "Succeeded"` with `location: eastus` and all four mandatory tags (`environment`, `owner`, `project`, `phase`) present
> - [ ] All four resource providers (`Microsoft.App`, `Microsoft.OperationalInsights`, `Microsoft.ContainerRegistry`, `Microsoft.ServiceBus`) return `registrationState: Registered` when queried via `az provider show`
> - [ ] `az monitor log-analytics workspace show --workspace-name law-onlinestore-prod-eastus` returns `provisioningState: Succeeded` and `sku.name: PerGB2018`
> - [ ] `az containerapp env show --name cae-onlinestore-prod-eastus` returns `properties.provisioningState: Succeeded` — not `InProgress`, `Updating`, or `Failed`
> - [ ] `properties.logsConfiguration.destination` on the environment equals `log-analytics` and `properties.logsConfiguration.logAnalyticsConfiguration.customerId` matches the captured `LAW_WORKSPACE_ID`
> - [ ] `properties.defaultDomain` is non-empty and the value resolves via `nslookup` (or DNS propagation wait has been explicitly confirmed at 10-minute mark)
> - [ ] `.env.phase2` file exists locally (or equivalent pipeline variables are set) and contains non-empty values for: `AZURE_RESOURCE_GROUP`, `AZURE_LOCATION`, `AZURE_ENVIRONMENT_NAME`, `AZURE_LAW_WORKSPACE_ID`, `AZURE_CONTAINER_APPS_ENVIRONMENT_ID`, `AZURE_CONTAINER_APPS_DEFAULT_DOMAIN`, `AZURE_CONTAINER_APPS_STATIC_IP`
> - [ ] No Azure Policy `deny` assignments are blocking resource creation in the Resource Group (verified by checking `az policy state list --resource-group rg-onlinestore-prod-eastus` returns no `NonCompliant` with `effect: Deny`)
>
> **If not met:** Perform the following remediation steps in order:
> 1. Identify which specific criterion failed by re-running the corresponding `az` command listed above.
> 2. For provisioning failures, read `statusDetails` from `az containerapp env show --query properties -o json` to identify the error code.
> 3. Apply the matching remediation from Section 4 Decision Logic for the specific error code encountered.
> 4. Re-run the failed CLI command(s) from Section 3 Technical Guidance — all commands are idempotent safe (resource group and environment creation are upsert-safe when names match and location is consistent).
> 5. Re-validate ALL gate criteria from the top of this checklist before re-attempting phase exit.
> 6. If three retry attempts fail for the same criterion, escalate: check Azure Service Health for `eastus` regional incidents at `status.azure.com` and document the incident before re-trying.

---

## 6. OUTPUTS

| Output Name | Type | Location | Consumed By |
|---|---|---|---|
| `rg-onlinestore-prod-eastus` | Azure Resource Group | Azure Subscription | Phase 3, Phase 4 |
| `law-onlinestore-prod-eastus` | Azure Log Analytics Workspace | Resource Group | Phase 4 (monitoring) |
| `cae-onlinestore-prod-eastus` | Azure Container Apps Environment | Resource Group | Phase 4 (container app creation) |
| `.env.phase2` | Shell environment variable file | Local working directory / CI pipeline secrets | Phase 3, Phase 4 |
| `AZURE_CONTAINER_APPS_ENVIRONMENT_ID` | ARM resource ID string | `.env.phase2` | Phase 4 `az containerapp create --environment` flag |
| `AZURE_CONTAINER_APPS_DEFAULT_DOMAIN` | DNS suffix string (e.g., `abc123.eastus.azurecontainerapps.io`) | `.env.phase2` | Phase 4 ingress URL construction and Dapr service invocation endpoint |
| `AZURE_CONTAINER_APPS_STATIC_IP` | IPv4 address string | `.env.phase2` | Phase 3 SQL firewall rule (if private endpoint not used) |
| `AZURE_LAW_WORKSPACE_ID` | GUID string | `.env.phase2` | Phase 4 diagnostic settings validation |
| Provider registration confirmation log | Console output / CI log artifact | Pipeline log | Audit trail for compliance |

---

## 7. ANTI-PATTERNS

**Anti-Pattern 1: Creating the Container Apps Environment before the Log Analytics Workspace exists**
If the agent attempts to run `az containerapp env create` before capturing `LAW_WORKSPACE_ID` and `LAW_PRIMARY_KEY`, the environment will be created with `--logs-destination none` (the default fallback), which silently disables all container log streaming. In Phase 4, when the microservice containers fail to start due to missing environment variables or connection string errors, there will be no logs available in the Azure portal or via `az containerapp logs show`, making the failure completely opaque. The environment cannot have its log analytics binding changed post-creation without full deletion and recreation, which requires tearing down Phase 3 (SQL) and Phase 4 (apps) resources as well.

**Anti-Pattern 2: Using an inconsistent or wrong `--location` between Resource Group and Container Apps Environment**
The Container Apps Environment `--location` must match the Resource Group location. If the Resource Group is created in `eastus` but the agent specifies `--location eastus2` in the `az containerapp env create` command, Azure will silently cross-region bind the environment, causing latency issues between the SQL Database (Phase 3, targeting the Resource Group location) and the container apps, and potentially violating data residency policies. More critically, the `AZURE_CONTAINER_APPS_STATIC_IP` captured in `.env.phase2` will correspond to the wrong region's network plane, making SQL firewall rules in Phase 3 ineffective. Always derive `LOCATION` from the Resource Group show output rather than hard-coding it in each command.

**Anti-Pattern 3: Skipping the `provisioningState: Succeeded` polling loop and proceeding immediately after `az containerapp env create` returns**
The `az containerapp env create` CLI command returns as soon as the ARM deployment is accepted — not when the environment is fully provisioned. The `defaultDomain`, `staticIp`, and Dapr configuration are not populated until `provisioningState` reaches `Succeeded`, which can take 3–8 minutes. If Phase 3 or Phase 4 reads `.env.phase2` before the polling loop completes, they will encounter empty or placeholder values for `AZURE_CONTAINER_APPS_DEFAULT_DOMAIN` and `AZURE_CONTAINER_APPS_STATIC_IP`, causing SQL firewall misconfiguration and ingress binding failures that are extremely difficult to diagnose because the environment appears to exist when queried by name.

**Anti-Pattern 4: Reusing an existing Container Apps Environment from a prior failed run without verifying its configuration**
If a previous run partially completed and left behind a `cae-onlinestore-prod-eastus` environment in a `Failed` or `Updating` state, a subsequent `az containerapp env create` with the same name will return an `AlreadyExists` error and the agent may assume the environment is valid. If the agent proceeds without explicitly verifying `provisioningState: Succeeded` and validating the `logsConfiguration.customerId` matches the current workspace, Phase 4 will deploy container apps into a broken environment where Dapr sidecars cannot start and log streaming is disconnected. Always run `az containerapp env show` to validate the existing environment's full `properties` block before accepting it as a valid phase output.

---

## 8. AGENT INSTRUCTIONS

1. **Load Phase 1 outputs.** Before executing any command, confirm that Phase 1 (Pre-Provisioning Validation) has completed successfully. Check for the presence of the Phase 1 gate confirmation. Verify that `az account show` returns the correct subscription ID and tenant ID established in Phase 1. If the subscription context has changed, run `az account set --subscription <subscription-id>` before proceeding.

2. **Set all shell variables.** Export the following variables at the top of the execution session:
   ```
   RESOURCE_GROUP="rg-onlinestore-prod-eastus"
   LOCATION="eastus"
   ENVIRONMENT_NAME="cae-onlinestore-prod-eastus"
   LAW_NAME="law-onlinestore-prod-eastus"
   ```
   Do not hard-code these values in individual commands; reference the variables consistently.

3. **Register resource providers.** Execute the provider registration loop from Section 3.2. Wait for `Registered` state on all four providers before proceeding. Log the result of each provider check. If any provider fails to register within 5 minutes after `--wait`, stop and report the failure with the provider name and current state.

4. **Create the Resource Group.** Run the `az group create` command from Section 3.1 with all four mandatory tags. Run `az group show` immediately after to confirm `provisioningState: Succeeded`. If the Resource Group already exists (idempotent re-run scenario), verify that its `location` matches `$LOCATION` and that all required tags are present; add any missing tags with `az group update --set tags.<key>=<value>`.

5. **Create the Log Analytics Workspace.** Run the `az monitor log-analytics workspace create` command from Section 3.3. Immediately after creation, run the `workspace show` and `get-shared-keys` commands to capture `LAW_WORKSPACE_ID` and `LAW_PRIMARY_KEY`. Confirm both variables are non-empty strings. If either is empty, do not proceed — re-run the extraction commands and check for CLI authentication token expiry.

6. **Create the Container Apps Environment.** Run the `az containerapp env create` command from Section 3.4, passing `LAW_WORKSPACE_ID` and `LAW_PRIMARY_KEY` captured in Step 5. Do not proceed until the command has been submitted; note that this command may take 1–2 minutes to return the initial ARM acceptance response.

7. **Poll for provisioning completion.** Execute the polling loop from Section 3.4 verbatim. Log each poll cycle with the elapsed time and current state. Do not short-circuit the loop even if the state appears to be `Succeeded` on the first poll — wait for two consecutive `Succeeded` responses before proceeding. If `Failed` is returned, extract `statusDetails`, apply the matching remediation from Section 4, and restart from Step 6.

8. **Extract and write environment outputs.** After `provisioningState: Succeeded` is confirmed, run the output extraction commands from Section 3.5. Write `.env.phase2` with all seven required variables. Print the contents of `.env.phase2` to the execution log (redacting `LAW_PRIMARY_KEY` if it was included). Confirm no variable value is empty.

9. **Validate DNS resolution.** Run the `nslookup` command against `DEFAULT_DOMAIN`. If it fails, wait 3 minutes and retry up to 3 times. If DNS does not resolve after 10 minutes post-provisioning, log a warning — do NOT block phase exit on DNS propagation lag alone; document the timestamp and move to gate evaluation, noting that DNS validation must be re-confirmed before Phase 4 ingress configuration.

10. **Evaluate the Decision Gate.** Work through every criterion in Section 5 sequentially. Run the exact `az` command specified for each criterion and compare the returned value to the expected value. Record PASS or FAIL for each criterion. Only mark the phase complete and emit the gate confirmation when ALL eight criteria return PASS. If any criterion FAILs, apply the remediation steps from Section 5, re-run the relevant commands, and re-evaluate the full gate checklist from the top. Do not selectively re-check only the failed criterion — evaluate all criteria on each retry to catch any regressions introduced by remediation actions.

11. **Emit phase completion signal.** Write the string `PHASE_2_COMPLETE=true` to `.env.phase2` as an additional variable. Log the completion timestamp and a summary of all seven captured output values (with key redaction as appropriate). Signal to the orchestrating agent or pipeline that Phase 3 (SQL Database Provisioning) may now begin, passing the path to `.env.phase2` as the inter-phase artifact.