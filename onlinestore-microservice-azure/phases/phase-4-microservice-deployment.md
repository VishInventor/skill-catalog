# Phase 4: Microservice Deployment

**Skill:** `onlinestore-microservice-azure` · **Version:** 1.0.0 · **Author:** Vishal Anand
**Phase:** 4 of 4 · **Status:** Final Phase · **Preceded by:** SQL Database Provisioning

---

## 1. PURPOSE

Phase 4 is the culminating execution phase of the `onlinestore-microservice-azure` skill. It takes every infrastructure artifact provisioned in Phases 1–3 — the validated Azure subscription context, the Container Apps Environment with its Log Analytics workspace, and the Azure SQL Database with its connection string — and assembles them into a fully running, externally accessible online store microservice topology. Without this phase, all prior provisioning is inert infrastructure with no business function. This phase is where deployment transitions from resource existence to live application behavior.

The source application is the Azure-Samples reference implementation at `https://github.com/Azure-Samples/container-apps-store-api-microservice`, which ships as a multi-service store API composed of a Node.js-based store frontend API, a Go-based product service, a Rust-based inventory service, and a Python-based order service — each deployed as a discrete Azure Container App within the shared environment. This phase deploys each service with correct environment variable injection, Dapr sidecar configuration, ingress rules, and SQL backend wiring so that inter-service communication and external HTTP traffic both function correctly.

Without this phase completing successfully, the deployment has no runnable workload, no externally accessible endpoint, no Dapr-enabled service-to-service calls, and no SQL-backed persistence. All monitoring dashboards enabled via Log Analytics remain empty. The deployment is non-functional until every container app in this phase reaches `Running` status and the store-api ingress URL returns HTTP 200 on its health probe path.

---

## 2. KEY ACTIVITIES

- **Clone and inspect the source repository** — Pull `https://github.com/Azure-Samples/container-apps-store-api-microservice` locally or into an ephemeral agent workspace. Inspect `deploy/` and `azure.yaml` to understand the expected Container App names (`store-api`, `product-service`, `inventory-service`, `order-service`), Dapr component manifests under `deploy/components/`, and which services expose external ingress versus internal-only.

- **Build and push container images to Azure Container Registry** — Each microservice has its own `Dockerfile`. Build all four images (`store-api`, `product-service`, `inventory-service`, `order-service`) using `az acr build` targeting the ACR provisioned or referenced during Phase 2, tagging each as `<acrName>.azurecr.io/<service>:latest`. Do not use public Docker Hub images in production to avoid rate limits and supply-chain risk.

- **Register Dapr components in the Container Apps Environment** — Apply the `statestore` and `pubsub` Dapr component YAML files from `deploy/components/` using `az containerapp env dapr-component set`. For production, replace the default Redis-based statestore with Azure Storage Account blob or Azure Cache for Redis. Ensure component scoping restricts each component to only the services that consume it.

- **Inject SQL connection string as a Container App secret** — Create a named secret `sql-connection-string` on the `order-service` Container App (the only service that persists to SQL) using `az containerapp secret set`. Reference this secret as the environment variable `ORDER_DB_CONNECTION` inside the Container App's environment configuration. Never embed the connection string as a plain environment variable.

- **Deploy each Container App with correct resource sizing and replicas** — Deploy `store-api` first with external ingress enabled on port 3000. Deploy `product-service`, `inventory-service`, and `order-service` with internal-only ingress, each on their respective ports (8080, 8082, 8083). Set minimum replicas to 1 and maximum to 5 for all services. Assign 0.5 CPU / 1.0 Gi memory per replica for non-critical services; assign 1.0 CPU / 2.0 Gi to `store-api`.

- **Configure Dapr sidecars on all Container Apps** — Enable Dapr on each Container App with `--dapr-enabled true`, setting the `--dapr-app-id` to the canonical service name (e.g., `store-api`, `order-service`) and `--dapr-app-port` matching the application's listen port. This is mandatory for service-to-service invocation via Dapr to resolve correctly — mismatched app IDs break inter-service routing silently.

- **Validate inter-service connectivity and SQL persistence** — After all four apps reach `Running` state, exercise the end-to-end flow: POST an order via the `store-api` external URL, verify the order-service writes to Azure SQL by querying `SELECT TOP 1 * FROM Orders ORDER BY CreatedAt DESC`, and confirm Dapr tracing appears in Log Analytics under the `ContainerAppConsoleLogs_CL` table.

- **Capture and store all deployment outputs** — Record the `store-api` external FQDN, all four Container App resource IDs, the Dapr component names registered, and the ACR image digests used. Write these to a structured output file (`phase4-outputs.json`) for audit, rollback reference, and downstream CI/CD pipeline consumption.

---

## 3. TECHNICAL GUIDANCE

### 3.1 Repository Clone and Structure Inspection

```bash
git clone https://github.com/Azure-Samples/container-apps-store-api-microservice.git
cd container-apps-store-api-microservice
ls deploy/components/
# Expected: statestore.yaml  pubsub.yaml
cat azure.yaml
```

### 3.2 Build and Push All Service Images

```bash
ACR_NAME="<your-acr-name>"                  # Set from Phase 2 outputs
RESOURCE_GROUP="<your-resource-group>"      # Set from Phase 2 outputs

for SERVICE in store-api product-service inventory-service order-service; do
  az acr build \
    --registry $ACR_NAME \
    --image "${SERVICE}:latest" \
    --file "./${SERVICE}/Dockerfile" \
    "./${SERVICE}"
done
```

> If the repo uses a monorepo structure with a root `docker-compose.yml`, build context paths may differ. Always verify each service's `Dockerfile` path before building.

### 3.3 Register Dapr Components

```bash
ENVIRONMENT_NAME="<your-container-apps-env>"   # From Phase 2 outputs

# Register statestore (replace with Azure Redis or Storage for production)
az containerapp env dapr-component set \
  --name $ENVIRONMENT_NAME \
  --resource-group $RESOURCE_GROUP \
  --dapr-component-name statestore \
  --yaml deploy/components/statestore.yaml

# Register pubsub
az containerapp env dapr-component set \
  --name $ENVIRONMENT_NAME \
  --resource-group $RESOURCE_GROUP \
  --dapr-component-name pubsub \
  --yaml deploy/components/pubsub.yaml
```

**Production-grade statestore override (Azure Cache for Redis):**

```yaml
# deploy/components/statestore-prod.yaml
componentType: state.redis
version: v1
metadata:
  - name: redisHost
    value: "<redis-name>.redis.cache.windows.net:6380"
  - name: redisPassword
    secretRef: redis-access-key
  - name: enableTLS
    value: "true"
scopes:
  - order-service
  - store-api
```

### 3.4 Deploy the `store-api` Container App (External Ingress)

```bash
az containerapp create \
  --name store-api \
  --resource-group $RESOURCE_GROUP \
  --environment $ENVIRONMENT_NAME \
  --image "${ACR_NAME}.azurecr.io/store-api:latest" \
  --registry-server "${ACR_NAME}.azurecr.io" \
  --registry-identity system \
  --cpu 1.0 \
  --memory 2.0Gi \
  --min-replicas 1 \
  --max-replicas 5 \
  --target-port 3000 \
  --ingress external \
  --dapr-enabled true \
  --dapr-app-id store-api \
  --dapr-app-port 3000 \
  --env-vars \
    PRODUCT_SERVICE_URL=http://localhost:3500/v1.0/invoke/product-service/method \
    ORDER_SERVICE_URL=http://localhost:3500/v1.0/invoke/order-service/method \
    INVENTORY_SERVICE_URL=http://localhost:3500/v1.0/invoke/inventory-service/method
```

### 3.5 Deploy Internal Services (product-service, inventory-service)

```bash
for SERVICE_CONFIG in \
  "product-service:8080" \
  "inventory-service:8082"; do
  SERVICE=$(echo $SERVICE_CONFIG | cut -d: -f1)
  PORT=$(echo $SERVICE_CONFIG | cut -d: -f2)

  az containerapp create \
    --name $SERVICE \
    --resource-group $RESOURCE_GROUP \
    --environment $ENVIRONMENT_NAME \
    --image "${ACR_NAME}.azurecr.io/${SERVICE}:latest" \
    --registry-server "${ACR_NAME}.azurecr.io" \
    --registry-identity system \
    --cpu 0.5 \
    --memory 1.0Gi \
    --min-replicas 1 \
    --max-replicas 5 \
    --target-port $PORT \
    --ingress internal \
    --dapr-enabled true \
    --dapr-app-id $SERVICE \
    --dapr-app-port $PORT
done
```

### 3.6 Deploy `order-service` with SQL Secret Injection

```bash
SQL_CONNECTION_STRING="Server=tcp:<sql-server>.database.windows.net,1433;\
Initial Catalog=<db-name>;Persist Security Info=False;\
User ID=<admin-user>;Password=<password>;\
MultipleActiveResultSets=False;Encrypt=True;\
TrustServerCertificate=False;Connection Timeout=30;"

# Create the Container App first
az containerapp create \
  --name order-service \
  --resource-group $RESOURCE_GROUP \
  --environment $ENVIRONMENT_NAME \
  --image "${ACR_NAME}.azurecr.io/order-service:latest" \
  --registry-server "${ACR_NAME}.azurecr.io" \
  --registry-identity system \
  --cpu 0.5 \
  --memory 1.0Gi \
  --min-replicas 1 \
  --max-replicas 5 \
  --target-port 8083 \
  --ingress internal \
  --dapr-enabled true \
  --dapr-app-id order-service \
  --dapr-app-port 8083

# Inject the SQL connection string as a secret
az containerapp secret set \
  --name order-service \
  --resource-group $RESOURCE_GROUP \
  --secrets "sql-connection-string=${SQL_CONNECTION_STRING}"

# Update the app to reference the secret as an env var
az containerapp update \
  --name order-service \
  --resource-group $RESOURCE_GROUP \
  --set-env-vars "ORDER_DB_CONNECTION=secretref:sql-connection-string"
```

### 3.7 Validate Deployment Status

```bash
# Check all Container Apps are Running
for APP in store-api product-service inventory-service order-service; do
  STATUS=$(az containerapp show \
    --name $APP \
    --resource-group $RESOURCE_GROUP \
    --query "properties.runningStatus" -o tsv)
  echo "${APP}: ${STATUS}"
done

# Get the external FQDN for store-api
STORE_API_FQDN=$(az containerapp show \
  --name store-api \
  --resource-group $RESOURCE_GROUP \
  --query "properties.configuration.ingress.fqdn" -o tsv)

echo "Store API URL: https://${STORE_API_FQDN}"

# Health check
curl -f "https://${STORE_API_FQDN}/health" && echo "HEALTHY" || echo "UNHEALTHY"
```

### 3.8 End-to-End SQL Persistence Validation

```bash
# Post a test order through the store-api
curl -X POST "https://${STORE_API_FQDN}/orders" \
  -H "Content-Type: application/json" \
  -d '{"customerId":"test-customer-001","items":[{"productId":"prod-001","qty":2}]}'

# Then query SQL to confirm persistence (requires sqlcmd or az sql query)
az sql db query \
  --server <sql-server-name> \
  --database <db-name> \
  --resource-group $RESOURCE_GROUP \
  --query-text "SELECT TOP 1 * FROM Orders ORDER BY CreatedAt DESC" \
  --admin-user <admin-user> \
  --admin-password <password>
```

### 3.9 Log Analytics Validation Query

```kusto
ContainerAppConsoleLogs_CL
| where ContainerAppName_s in ("store-api", "order-service", "product-service", "inventory-service")
| where TimeGenerated > ago(15m)
| project TimeGenerated, ContainerAppName_s, Log_s
| order by TimeGenerated desc
| take 50
```

---

## 4. DECISION LOGIC

**IF** any `az acr build` command fails with an exit code other than 0:
→ **THEN** inspect the build log for missing `Dockerfile`, incorrect build context path, or ACR authentication failure. Re-authenticate with `az acr login --name <acrName>` and retry the specific failing service build before proceeding.
→ **ELSE** (all builds succeed) proceed to Dapr component registration.

**IF** `az containerapp env dapr-component set` returns a conflict error (component name already exists):
→ **THEN** check if a prior partial deployment left stale components. Run `az containerapp env dapr-component list --name $ENVIRONMENT_NAME --resource-group $RESOURCE_GROUP` to list existing components. If the existing component has a different spec, delete it with `az containerapp env dapr-component remove` and re-apply. If it matches the desired spec, treat registration as idempotent and continue.
→ **ELSE** proceed to Container App deployment.

**IF** a Container App's `runningStatus` is `Degraded` or `Failed` after deployment:
→ **THEN** run `az containerapp logs show --name <app> --resource-group $RESOURCE_GROUP --follow` to retrieve runtime logs. Common causes: incorrect image tag (404 from ACR), missing environment variable, SQL connection string malformed, or Dapr app port mismatch. Fix the root cause and run `az containerapp update` with corrected parameters. Do NOT delete and recreate the Container App unless configuration is fundamentally broken — use update to preserve identity and secrets.
→ **ELSE** all apps Running, proceed to validation.

**IF** the `store-api` external FQDN health check returns HTTP 503:
→ **THEN** the most likely cause is one of the upstream internal services (`product-service`, `inventory-service`, `order-service`) failing Dapr service invocation. Verify all three internal apps show `Running` status. Check that `--dapr-app-id` values exactly match the service name strings used in the `store-api` environment variables (`PRODUCT_SERVICE_URL`, `ORDER_SERVICE_URL`, `INVENTORY_SERVICE_URL`). Dapr app ID mismatches produce 500/503 responses without clear error messages.
→ **ELSE** HTTP 200 confirmed, proceed to SQL persistence validation.

**IF** SQL query returns 0 rows after posting a test order:
→ **THEN** the `order-service` is either not receiving the order (inter-service routing issue) or not writing to SQL (connection string issue or schema mismatch). Check `order-service` logs for connection errors. Verify the secret `sql-connection-string` is correctly mounted by running `az containerapp secret list --name order-service --resource-group $RESOURCE_GROUP`. If the schema does not exist, run the DDL initialization script from the repository's `deploy/sql/` directory against the Phase 3 SQL Database.
→ **ELSE** SQL persistence confirmed, proceed to output capture.

**IF** this is a re-run of Phase 4 (retry scenario):
→ **THEN** use `az containerapp update` instead of `az containerapp create` for any app that already exists. Use `az acr repository show-tags` to verify if images are already pushed and skip rebuild if digest matches. Dapr component set is idempotent if YAML content is unchanged.
→ **ELSE** (first run) execute full creation sequence as documented.

---

## 5. DECISION GATE

> **DECISION GATE — Phase 4 Complete (Final Phase)**
>
> ALL of the following must be true before declaring deployment complete:
>
> - [ ] All four Container Apps (`store-api`, `product-service`, `inventory-service`, `order-service`) report `runningStatus: Running` via `az containerapp show`.
> - [ ] All four container images are confirmed pushed to ACR with non-null image digests (verified via `az acr repository show-manifests --name <acrName> --repository <service>`).
> - [ ] Both Dapr components (`statestore`, `pubsub`) are registered in the Container Apps Environment (verified via `az containerapp env dapr-component list`).
> - [ ] The `order-service` Container App has secret `sql-connection-string` registered and environment variable `ORDER_DB_CONNECTION` references it (verified via `az containerapp secret list` and `az containerapp show --query "properties.template.containers[0].env"`).
> - [ ] `store-api` external ingress FQDN is assigned and returns HTTP 200 on `/health` endpoint (verified via `curl -f`).
> - [ ] A POST to `https://<store-api-fqdn>/orders` produces a row in the Azure SQL `Orders` table (verified via SQL query returning ≥ 1 row).
> - [ ] Log Analytics workspace receives log entries from all four Container Apps within the last 15 minutes (verified via KQL query against `ContainerAppConsoleLogs_CL`).
> - [ ] `phase4-outputs.json` file has been written containing: `storeApiFqdn`, all four Container App resource IDs, ACR image digests, Dapr component names, resource group name, and deployment timestamp.
>
> **If any criterion is not met:**
>
> - **Apps not Running:** Run `az containerapp logs show --name <failing-app> --resource-group $RESOURCE_GROUP` to retrieve the failure reason. Address root cause (image pull error → re-push image; startup crash → fix env vars; port mismatch → update `--target-port`). Then run `az containerapp update` with corrected parameters and re-poll status.
> - **Health check not HTTP 200:** Verify Dapr app IDs match env var URL patterns. Check internal service ingress is set to `internal` (not `external` and not disabled). Confirm Dapr sidecar is enabled on all four apps.
> - **SQL row not present:** Re-validate connection string format, secret mounting, and SQL schema existence. Run DDL init script if schema is absent. Retry the POST test order.
> - **Log Analytics empty:** Confirm the Log Analytics workspace is correctly linked to the Container Apps Environment (check `--logs-workspace-id` used in Phase 2). Allow up to 5 minutes for first log ingestion after apps reach Running state.

---

## 6. OUTPUTS

| Output Artifact | Type | Description |
|---|---|---|
| `phase4-outputs.json` | JSON file | Structured record of all deployment outputs: `storeApiFqdn`, four Container App resource IDs, ACR image digests for all services, Dapr component names registered, SQL secret name, resource group name, environment name, deployment timestamp (ISO 8601 UTC) |
| `store-api` Container App | Live Azure resource | External-ingress Container App running the store frontend API, Dapr-enabled, replicas 1–5 |
| `product-service` Container App | Live Azure resource | Internal-ingress Container App running Go-based product catalog service, Dapr-enabled |
| `inventory-service` Container App | Live Azure resource | Internal-ingress Container App running Rust-based inventory service, Dapr-enabled |
| `order-service` Container App | Live Azure resource | Internal-ingress Container App running Python-based order service, Dapr-enabled, SQL-backed |
| Dapr `statestore` component | Azure Container Apps Env resource | Registered Dapr state store component scoped to `store-api` and `order-service` |
| Dapr `pubsub` component | Azure Container Apps Env resource | Registered Dapr pub/sub component scoped to all four services |
| ACR image tags | 4 container image tags in ACR | `store-api:latest`, `product-service:latest`, `inventory-service:latest`, `order-service:latest` all pushed and pullable |
| `order-service` secret `sql-connection-string` | Container App secret | SQL connection string injected as a named secret, not exposed as plaintext env var |
| Health check result log | Console/file output | Timestamped output of `curl -f https://<fqdn>/health` confirming HTTP 200 |
| SQL persistence validation result | Console/file output | Output of `SELECT TOP 1 * FROM Orders ORDER BY CreatedAt DESC` confirming ≥ 1 row after test order POST |

---

## 7. ANTI-PATTERNS

### Anti-Pattern 1: Deploying All Four Container Apps with External Ingress

**Mistake:** Setting `--ingress external` on `product-service`, `inventory-service`, and `order-service` because it seems safer or easier to test each service independently via browser.

**Consequence:** All three internal services become publicly accessible on the internet without authentication. This exposes the order-service (which holds the SQL connection string reference) to unauthenticated HTTP calls, violating the principle of least privilege. It also increases attack surface, raises egress costs unnecessarily, and breaks the Dapr service invocation pattern — Dapr resolves services by app ID over the internal network; if a service has external ingress but internal Dapr routing is expected, service discovery conflicts arise. In production this is a critical security misconfiguration.

**Correct approach:** Only `store-api` gets `--ingress external`. All other services use `--ingress internal`. Inter-service calls route exclusively through Dapr sidecar invocation on `http://localhost:3500/v1.0/invoke/<app-id>/method`.

### Anti-Pattern 2: Hardcoding the SQL Connection String as a Plain Environment Variable

**Mistake:** Passing the SQL connection string directly as `--env-vars ORDER_DB_CONNECTION="Server=tcp:..."` instead of using `az containerapp secret set` and `secretref:`.

**Consequence:** The connection string (including username and password) is stored in plaintext in the Container App's configuration, visible to anyone with `Contributor` or `Reader` access to the resource in the Azure portal or via `az containerapp show`. It also appears in deployment logs, CI/CD pipeline outputs, and any exported ARM templates. If the password must be rotated, there is no clean mechanism — the env var must be updated via deployment, causing a restart. Using `secretref:` keeps the value encrypted at rest in the Container Apps secret store and allows secret rotation without full redeployment.

**Correct approach:** Always use `az containerapp secret set` followed by `--set-env-vars "ORDER_DB_CONNECTION=secretref:sql-connection-string"` as shown in Section 3.6.

### Anti-Pattern 3: Setting Dapr App ID to a Value That Doesn't Match the Store-API's Service Invocation URL Pattern

**Mistake:** Deploying `order-service` with `--dapr-app-id orders` (plural) instead of `order-service` (matching the pattern used in `store-api`'s `ORDER_SERVICE_URL` environment variable), or using camelCase (`orderService`) instead of the kebab-case expected by the reference application.

**Consequence:** Dapr service-to-service invocation silently fails. The `store-api` attempts to invoke `http://localhost:3500/v1.0/invoke/order-service/method/...` but Dapr's name resolution cannot find a registered app with that ID. The result is HTTP 500 errors on order-related endpoints with Dapr returning a generic "ERR_DIRECT_INVOKE" error — which is extremely difficult to diagnose without knowing to check Dapr app IDs. The store frontend appears to work for product browsing but all order placement fails. This mistake can survive days of debugging because the error message does not mention app ID mismatch.

**Correct approach:** Before deploying, read the `store-api` source code or `azure.yaml` to extract the exact service name strings used in outbound invocation URLs. Use those exact strings — character for character — as the `--dapr-app-id` values for each Container App.

---

## 8. AGENT INSTRUCTIONS

The following numbered steps are the authoritative execution sequence for an AI agent performing Phase 4 of the `onlinestore-microservice-azure` skill. Execute each step in order. Do not skip steps. Validate each step's output before proceeding to the next.

1. **Load Phase 2 and Phase 3 outputs.** Read `phase2-outputs.json` and `phase3-outputs.json` from the working directory. Extract and set the following variables for use throughout this phase: `RESOURCE_GROUP`, `ENVIRONMENT_NAME`, `ACR_NAME`, `SQL_SERVER_NAME`, `SQL_DB_NAME`, `SQL_ADMIN_USER`, `SQL_ADMIN_PASSWORD`. If any of these values are missing or null, halt and report which phase output is incomplete — do not proceed with partial configuration.

2. **Clone the source repository.** Execute `git clone https://github.com/Azure-Samples/container-apps-store-api-microservice.git`. Change directory into the cloned repo. Verify the following subdirectories exist: `store-api/`, `product-service/`, `inventory-service/`, `order-service/`, `deploy/components/`. If any directory is missing, the repo may have been restructured — read the root `README.md` and `azure.yaml` to determine the correct paths before continuing.

3. **Verify ACR accessibility.** Run `az acr show --name $ACR_NAME --resource-group $RESOURCE_GROUP --query "loginServer" -o tsv`. Confirm output matches `<acrName>.azurecr.io`. If the ACR does not exist or access is denied, halt and escalate — ACR must have been provisioned in Phase 2.

4. **Build and push all four service images.** For each service in the order `store-api`, `product-service`, `inventory-service`, `order-service`: run `az acr build --registry $ACR_NAME --image <service>:latest --file ./<service>/Dockerfile ./<service>`. After each build, verify the image is in ACR by running `az acr repository show-manifests --name $ACR_NAME --repository <service>` and confirming at least one manifest exists with a non-null digest. Record all four digests.

5. **Register Dapr statestore component.** Run `az containerapp env dapr-component set --name $ENVIRONMENT_NAME --resource-group $RESOURCE_GROUP --dapr-component-name statestore --yaml deploy/components/statestore.yaml`. If the component already exists (conflict error), list existing components, compare specs, and proceed if identical or overwrite if different.

6. **Register Dapr pubsub component.** Run `az containerapp env dapr-component set --name $ENVIRONMENT_NAME --resource-group $RESOURCE_GROUP --dapr-component-name pubsub --yaml deploy/components/pubsub.yaml`. Apply same idempotency check as step 5.

7. **Deploy `store-api` Container App with external ingress.** Execute the `az containerapp create` command as specified in Section 3.4, substituting all variables from step 1. Confirm the command returns exit code 0. Run `az containerapp show --name store-api --resource-group $RESOURCE_GROUP --query "properties.runningStatus" -o tsv` and wait (polling every 30 seconds, maximum 5 minutes) until value is `Running`.

8. **Deploy `product-service` Container App.** Execute `az containerapp create` with `--ingress internal`, `--target-port 8080`, `--dapr-app-id product-service`, `--dapr-app-port 8080`, `--cpu 0.5`, `--memory 1.0Gi`. Poll for `Running` status.

9. **Deploy `inventory-service` Container App.** Execute `az containerapp create` with `--ingress internal`, `--target-port 8082`, `--dapr-app-id inventory-service`, `--dapr-app-port 8082`, `--cpu 0.5`, `--memory 1.0Gi`. Poll for `Running` status.

10. **Construct the SQL connection string.** Assemble the connection string in the format: `Server=tcp:${SQL_SERVER_NAME}.database.windows.net,1433;Initial Catalog=${SQL_DB_NAME};Persist Security Info=False;User ID=${SQL_ADMIN_USER};Password=${SQL_ADMIN_PASSWORD};MultipleActiveResultSets=False;Encrypt=True;TrustServerCertificate=False;Connection Timeout=30;`. Do not log or print this value. Store it only in an in-memory variable.

11. **Deploy `order-service` Container App.** Execute `az containerapp create` with `--ingress internal`, `--target-port 8083`, `--dapr-app-id order-service`, `--dapr-app-port 8083`, `--cpu 0.5`, `--memory 1.0Gi`. After creation, run `az containerapp secret set --name order-service --resource-group $RESOURCE_GROUP --secrets "sql-connection-string=<value>"`. Then run `az containerapp update --name order-service --resource-group $RESOURCE_GROUP --set-env-vars "ORDER_DB_CONNECTION=secretref:sql-connection-string"`. Poll for `Running` status.

12. **Retrieve `store-api` FQDN.** Run `az containerapp show --name store-api --resource-group $RESOURCE_GROUP --query "properties.configuration.ingress.fqdn" -o tsv`. Store value as `STORE_API_FQDN`. Confirm it is non-empty.

13. **Execute health check.** Run `curl -f -s -o /dev/null -w "%{http_code}" "https://${STORE_API_FQDN}/health"`. If result is not `200`, inspect `store-api` logs via `az containerapp logs show --name store-api --resource-group $RESOURCE_GROUP` and apply decision logic from Section 4. Do not proceed to step 14 until health check returns 200.

14. **Execute end-to-end order test.** POST a test order: `curl -X POST "https://${STORE_API_FQDN}/orders" -H "Content-Type: application/json" -d '{"customerId":"agent-test-001","items":[{"productId":"prod-001","qty":1}]}'`. Verify HTTP 201 or 200 response. Then validate SQL persistence using `az sql db query` or `sqlcmd` to confirm a row exists in the `Orders` table.

15. **Validate Log Analytics ingestion.** Open Azure Monitor or run a KQL query against the Log Analytics workspace linked in Phase 2: query `ContainerAppConsoleLogs_CL` filtered to the last 15 minutes, all four app names. Confirm rows are returned. If empty, wait 5 minutes and retry once before raising a diagnostic flag.

16. **Write `phase4-outputs.json`.** Construct and write the output file containing: `storeApiFqdn` (FQDN string), `containerAppIds` (object with four app names as keys, resource IDs as values), `acrImageDigests` (object with four service names as keys, digest strings as values), `daprComponents` (array: `["statestore","pubsub"]`), `sqlSecretName` (`"sql-connection-string"`), `resourceGroup`, `environmentName`, `deploymentTimestamp` (ISO 8601 UTC). Log the file path to console output.

17. **Declare Phase 4 complete.** Verify all eight Decision Gate criteria from Section 5 are met. If all pass, emit the completion message: `"Phase 4: Microservice Deployment COMPLETE. Store API live at https://<fqdn>. All 4 services Running. SQL persistence confirmed. Deployment artifact: phase4-outputs.json."` This is the final phase — no further phases exist. The `onlinestore-microservice-azure` skill deployment is complete.