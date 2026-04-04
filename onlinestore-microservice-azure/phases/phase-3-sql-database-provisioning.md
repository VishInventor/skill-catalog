# Phase 3: SQL Database Provisioning

## Phase Overview

| Field | Value |
|---|---|
| **Phase Name** | SQL Database Provisioning |
| **Phase Number** | 3 of 4 |
| **Skill** | onlinestore-microservice-azure v1.0.0 |
| **Preceded By** | Phase 2: Container Apps Environment |
| **Followed By** | Phase 4: Microservice Deployment |
| **Exit Gate** | SQL Database Provisioning complete? [conditional] on-fail: retry |
| **Author** | Vishal Anand |

---

## 1. PURPOSE

This phase establishes the persistent relational data tier for the online store microservice deployment. The `container-apps-store-api-microservice` sample requires a live, reachable Azure SQL Database to store order records, product catalog data, and transactional state — none of which can be held in-memory across Container App scaling events or restarts. Without a properly provisioned and configured Azure SQL instance in the same resource group, the microservice will either fail startup health checks or silently drop write operations, making Phase 4 deployment non-functional regardless of how correctly the container image is pulled and executed.

Provisioning SQL in the same resource group as the Container Apps Environment (created in Phase 2) is architecturally significant. It allows the two resources to share a VNet scope if private networking is later layered in, simplifies IAM boundaries for managed identity access, and ensures that a single `az group delete` command can cleanly tear down the entire deployment. The SQL Server firewall rules and connection string must be deliberately scoped to allow the Container Apps outbound IPs — this phase is the only opportunity to establish that trust before the microservice binaries attempt to resolve and authenticate against the database endpoint.

This phase also produces the connection string secret value that Phase 4 will inject into the Container App as an environment variable. If the SQL logical server name, database name, admin credentials, or firewall rules are misconfigured here, Phase 4 will require a full rollback of secret values and a Container App revision restart — a failure that is expensive in time and debugging effort. Getting SQL right in isolation, before the microservice code is anywhere near it, is the correct sequencing.

---

## 2. KEY ACTIVITIES

- **Create the Azure SQL Logical Server** in the exact resource group and region established in Phase 2. The server name must be globally unique (e.g., `onlinestore-sql-<unique-suffix>`), and SQL authentication must be enabled with a strong admin password that will be stored in a secure variable for later injection. Server-level collation should be set to `SQL_Latin1_General_CP1_CI_AS` for compatibility with the store API's Entity Framework migrations.

- **Create the Azure SQL Database** on the logical server with SKU `Basic` (or `Standard S0` for production-grade throughput) named `ordersdb`. This name must be confirmed and recorded — Phase 4's microservice reads the database name from its `DATABASE_NAME` environment variable. Set the max size to `2GB` minimum to avoid hitting quota limits during the store's seed data operations.

- **Configure the SQL Server firewall to allow Azure services** by enabling the `Allow Azure Services and resources to access this server` flag. This is the prerequisite for Container Apps (which use Azure-managed egress IPs) to reach the SQL endpoint without private endpoint configuration. Additionally, retrieve the outbound static IPs of the Container Apps Environment from Phase 2 outputs and add them as explicit firewall rules named `ContainerAppsEgressRule`.

- **Retrieve and validate the outbound IPs of the Container Apps Environment** provisioned in Phase 2 using `az containerapp env show` and parsing the `properties.staticIp` or `outboundIpAddresses` field. Each IP must be registered as a named firewall rule on the SQL logical server before any connectivity test is run.

- **Test connectivity from the CLI host** using `sqlcmd` or `az sql db show-connection-string` to verify the logical server DNS name resolves and the admin account can authenticate. Run `SELECT 1` against `ordersdb` to confirm the database is online and the admin credential is valid end-to-end.

- **Generate and record the ADO.NET connection string** in the format the store microservice expects:  
  `Server=tcp:<server-name>.database.windows.net,1433;Initial Catalog=ordersdb;Persist Security Info=False;User ID=<admin-user>;Password=<admin-password>;MultipleActiveResultSets=False;Encrypt=True;TrustServerCertificate=False;Connection Timeout=30;`  
  This string will be stored as a Container Apps secret in Phase 4.

- **Enable Azure Defender for SQL / Microsoft Defender for SQL** at the server level for the production deployment. Set the vulnerability assessment storage account to the one in the same resource group. This satisfies the monitoring-enabled requirement stated in the skill description and generates a baseline security report before the microservice ever touches the database.

- **Tag all SQL resources** with the standard tag set: `project=onlinestore-microservice-azure`, `phase=sql-provisioning`, `managed-by=agent`, `environment=production`. Tags must match the resource group tags applied in Phase 2 to maintain cost allocation consistency.

- **Document the logical server FQDN, database name, admin username, and the firewall rule set** in the phase outputs record. This documentation is the formal handoff artifact for Phase 4 and must be complete before the exit gate is evaluated.

---

## 3. TECHNICAL GUIDANCE

### 3.1 Retrieve Phase 2 Outputs (Required Before Any SQL Command)

```bash
# Retrieve resource group name and location from Phase 2
RG_NAME="onlinestore-rg"
LOCATION="eastus"   # Must match Phase 2 location

# Retrieve Container Apps Environment outbound IPs
CAE_NAME="onlinestore-cae"
OUTBOUND_IPS=$(az containerapp env show \
  --name "$CAE_NAME" \
  --resource-group "$RG_NAME" \
  --query "properties.staticIp" \
  --output tsv)

echo "Container Apps Outbound IP: $OUTBOUND_IPS"
```

> **Note:** If the environment uses multiple outbound IPs, query `properties.outboundIpAddresses` (array). Parse each IP and register a separate firewall rule per entry.

---

### 3.2 Create Azure SQL Logical Server

```bash
SQL_SERVER_NAME="onlinestore-sql-$(openssl rand -hex 4)"
SQL_ADMIN_USER="onlinestore-admin"
SQL_ADMIN_PASSWORD="<STRONG_PASSWORD_GENERATED_OR_PROMPTED>"

az sql server create \
  --name "$SQL_SERVER_NAME" \
  --resource-group "$RG_NAME" \
  --location "$LOCATION" \
  --admin-user "$SQL_ADMIN_USER" \
  --admin-password "$SQL_ADMIN_PASSWORD" \
  --enable-ad-only-auth false

echo "SQL Server FQDN: ${SQL_SERVER_NAME}.database.windows.net"
```

> **Password policy:** Minimum 16 characters, must contain uppercase, lowercase, digit, and special character. Do not hardcode — prompt or inject from a secrets vault.

---

### 3.3 Create the `ordersdb` Database

```bash
DB_NAME="ordersdb"

az sql db create \
  --name "$DB_NAME" \
  --server "$SQL_SERVER_NAME" \
  --resource-group "$RG_NAME" \
  --edition "Basic" \
  --capacity 5 \
  --max-size "2GB" \
  --collation "SQL_Latin1_General_CP1_CI_AS" \
  --zone-redundant false \
  --tags project=onlinestore-microservice-azure phase=sql-provisioning managed-by=agent environment=production
```

For production-grade throughput (recommended if order volume > 100 req/min):

```bash
az sql db create \
  --name "$DB_NAME" \
  --server "$SQL_SERVER_NAME" \
  --resource-group "$RG_NAME" \
  --edition "Standard" \
  --capacity 10 \
  --max-size "5GB" \
  --collation "SQL_Latin1_General_CP1_CI_AS"
```

---

### 3.4 Configure Firewall Rules

```bash
# Allow all Azure services (required for Container Apps managed egress)
az sql server firewall-rule create \
  --resource-group "$RG_NAME" \
  --server "$SQL_SERVER_NAME" \
  --name "AllowAzureServices" \
  --start-ip-address "0.0.0.0" \
  --end-ip-address "0.0.0.0"

# Add explicit Container Apps Environment static IP rule
az sql server firewall-rule create \
  --resource-group "$RG_NAME" \
  --server "$SQL_SERVER_NAME" \
  --name "ContainerAppsEgressRule" \
  --start-ip-address "$OUTBOUND_IPS" \
  --end-ip-address "$OUTBOUND_IPS"
```

If multiple outbound IPs exist (loop pattern):

```bash
IPS_ARRAY=($(az containerapp env show \
  --name "$CAE_NAME" \
  --resource-group "$RG_NAME" \
  --query "properties.outboundIpAddresses[*]" \
  --output tsv))

for i in "${!IPS_ARRAY[@]}"; do
  az sql server firewall-rule create \
    --resource-group "$RG_NAME" \
    --server "$SQL_SERVER_NAME" \
    --name "ContainerAppsEgressRule-$i" \
    --start-ip-address "${IPS_ARRAY[$i]}" \
    --end-ip-address "${IPS_ARRAY[$i]}"
done
```

---

### 3.5 Validate Connectivity

```bash
# Verify server is reachable (DNS + TLS)
az sql db show-connection-string \
  --server "$SQL_SERVER_NAME" \
  --name "$DB_NAME" \
  --client ado.net

# Test actual query connectivity using sqlcmd (requires sqlcmd installed)
sqlcmd \
  -S "${SQL_SERVER_NAME}.database.windows.net" \
  -d "$DB_NAME" \
  -U "$SQL_ADMIN_USER" \
  -P "$SQL_ADMIN_PASSWORD" \
  -Q "SELECT DB_NAME() AS CurrentDatabase, GETUTCDATE() AS ServerTime" \
  -N \
  -C
```

Expected output:
```
CurrentDatabase    ServerTime
-----------------  -----------------------
ordersdb           2024-11-15 10:22:34.123
```

---

### 3.6 Generate and Record the ADO.NET Connection String

```bash
CONN_STRING="Server=tcp:${SQL_SERVER_NAME}.database.windows.net,1433;\
Initial Catalog=${DB_NAME};\
Persist Security Info=False;\
User ID=${SQL_ADMIN_USER};\
Password=${SQL_ADMIN_PASSWORD};\
MultipleActiveResultSets=False;\
Encrypt=True;\
TrustServerCertificate=False;\
Connection Timeout=30;"

echo "CONNECTION_STRING=${CONN_STRING}" >> .phase3-outputs.env
```

> **Security note:** `.phase3-outputs.env` must be added to `.gitignore` immediately. This file is consumed only by the Phase 4 Container App secret injection step and must not be committed to source control.

---

### 3.7 Enable Microsoft Defender for SQL

```bash
az sql server microsoft-support-auditing-policy update \
  --resource-group "$RG_NAME" \
  --server "$SQL_SERVER_NAME" \
  --state Enabled 2>/dev/null || true

# Enable Advanced Threat Protection
az security atp sql set \
  --resource-group "$RG_NAME" \
  --server-name "$SQL_SERVER_NAME" \
  --is-enabled true
```

---

### 3.8 Tag the SQL Logical Server

```bash
az sql server update \
  --name "$SQL_SERVER_NAME" \
  --resource-group "$RG_NAME" \
  --set tags.project=onlinestore-microservice-azure \
         tags.phase=sql-provisioning \
         tags.managed-by=agent \
         tags.environment=production
```

---

## 4. DECISION LOGIC

### Decision: SQL SKU Selection

```
IF expected_order_volume <= 100 req/min AND environment == "dev/test":
    USE edition="Basic", capacity=5, max-size="2GB"
ELSE IF expected_order_volume > 100 req/min OR environment == "production":
    USE edition="Standard", capacity=10, max-size="5GB"
ELSE IF cost_constraints are strict AND production is confirmed:
    USE edition="General Purpose" with serverless tier, auto-pause=60min
```

### Decision: Firewall Rule Strategy

```
IF Container Apps Environment has staticIp (single IP):
    CREATE one rule named "ContainerAppsEgressRule" with that IP for both start and end
ELSE IF Container Apps Environment has outboundIpAddresses (array):
    FOR each IP in array:
        CREATE rule "ContainerAppsEgressRule-{index}"
ELSE IF no static IP is available (consumption plan, dynamic egress):
    ENABLE "AllowAzureServices" rule ONLY
    LOG warning: "No static IP available; relying on Azure service tag — review before production"
    DO NOT proceed with private endpoint bypass assumptions
```

### Decision: Admin Password Source

```
IF running in CI/CD pipeline:
    FETCH password from Azure Key Vault or pipeline secret variable
    NEVER accept password as plain CLI argument visible in process list
ELSE IF running interactively (agent-driven):
    PROMPT for password using read -s or equivalent
    VALIDATE against complexity policy before attempting server creation
ELSE IF previous attempt failed at server creation:
    GENERATE new password with: openssl rand -base64 20
    ENSURE it meets policy: uppercase + lowercase + digit + special char
```

### Decision: Connectivity Test Failure

```
IF sqlcmd returns "Cannot open server" error:
    CHECK firewall rules — outbound IP may have changed since rule creation
    RE-FETCH Container Apps Environment IP: az containerapp env show
    UPDATE firewall rule with new IP
    RETRY connectivity test
    IF still failing after firewall update:
        VERIFY SQL server is in "Online" state: az sql server show
        CHECK for Azure SQL regional outages via Azure Status page
ELSE IF sqlcmd returns "Login failed":
    VERIFY SQL_ADMIN_USER and SQL_ADMIN_PASSWORD variables are correctly scoped
    RESET admin password: az sql server update --admin-password "<new_password>"
    RETRY with updated credentials
ELSE IF sqlcmd returns "Database does not exist":
    VERIFY DB_NAME matches exactly: az sql db list --server "$SQL_SERVER_NAME"
    If DB is absent, RE-RUN Section 3.3 database creation command
```

---

## 5. DECISION GATE

> **DECISION GATE — SQL Database Provisioning complete?**
>
> ALL of the following must be true before proceeding to Phase 4:
>
> - [ ] Azure SQL Logical Server named `onlinestore-sql-<suffix>` exists in resource group `onlinestore-rg` and reports `state: Ready` via `az sql server show`
> - [ ] Database `ordersdb` exists on the logical server, collation is `SQL_Latin1_General_CP1_CI_AS`, and `az sql db show` reports `status: Online`
> - [ ] Firewall rule `AllowAzureServices` (0.0.0.0–0.0.0.0) is present on the SQL logical server
> - [ ] At least one `ContainerAppsEgressRule` firewall rule exists matching the current outbound IP(s) of the Container Apps Environment created in Phase 2
> - [ ] Connectivity test via `sqlcmd` or equivalent returns `SELECT 1` = `1` against `ordersdb` with admin credentials
> - [ ] ADO.NET connection string has been generated, validated, and written to `.phase3-outputs.env`
> - [ ] SQL logical server and database are both tagged with `project=onlinestore-microservice-azure`
> - [ ] Microsoft Defender for SQL is enabled at the server level (confirmed via `az security atp sql show`)
> - [ ] Admin password meets complexity policy (16+ chars, mixed case, digit, special char) and is NOT stored in any version-controlled file
>
> **If any criterion is not met, do NOT proceed to Phase 4.**
>
> **Remediation steps:**
> - For missing server or database: re-run the relevant `az sql server create` or `az sql db create` command from Section 3.2 or 3.3
> - For firewall issues: re-execute Section 3.4 after re-fetching current Container Apps outbound IPs
> - For connectivity failure: follow the Decision Logic in Section 4 — "Decision: Connectivity Test Failure"
> - For missing connection string: re-run Section 3.6 and verify `.phase3-outputs.env` contains the `CONNECTION_STRING` key
> - For tagging gaps: re-run Section 3.8 `az sql server update` tag command
> - For Defender not enabled: re-run Section 3.7 commands
> - After all remediations: re-evaluate ALL gate criteria from the top before marking complete

---

## 6. OUTPUTS

The following named deliverables must exist and be confirmed before Phase 4 begins:

| Output Name | Type | Location / Value | Consumed By |
|---|---|---|---|
| `SQL_SERVER_NAME` | Environment variable | e.g., `onlinestore-sql-a1b2c3d4` | Phase 4 — Container App secret injection |
| `SQL_SERVER_FQDN` | String | `<server>.database.windows.net` | Phase 4 — connection string, firewall validation |
| `DB_NAME` | Environment variable | `ordersdb` | Phase 4 — `DATABASE_NAME` env var |
| `SQL_ADMIN_USER` | Secret variable | Securely held in session/vault | Phase 4 — connection string |
| `SQL_ADMIN_PASSWORD` | Secret variable | Securely held in session/vault, NOT in files | Phase 4 — connection string |
| `CONNECTION_STRING` | Secret string (ADO.NET format) | `.phase3-outputs.env` (gitignored) | Phase 4 — Container Apps secret `sql-connection-string` |
| `FIREWALL_RULES_LIST` | CLI output record | Logged output of `az sql server firewall-rule list` | Phase 3 gate validation, audit trail |
| `SQL_CONNECTIVITY_TEST_LOG` | Console output | Logged sqlcmd output showing `SELECT DB_NAME()` success | Phase 3 gate validation |
| `DEFENDER_STATUS_RECORD` | CLI output record | `az security atp sql show` output | Monitoring compliance, Phase 3 gate |
| `PHASE3_TAG_RECORD` | CLI output record | `az sql server show --query tags` output | Audit trail, cost attribution |

---

## 7. ANTI-PATTERNS

### Anti-Pattern 1: Provisioning SQL in a Different Resource Group Than the Container Apps Environment

**What it looks like:** Running `az sql server create` without explicitly specifying `--resource-group "$RG_NAME"`, accidentally defaulting to a different subscription-default group, or placing SQL in a "shared-services" resource group to reuse it across projects.

**Consequences:** Phase 4's microservice deployment uses resource group-scoped role assignments and environment variable lookups that assume co-location. A cross-group SQL server will not be discoverable by the Container App's managed identity unless additional cross-group role assignments are manually configured — a step not covered in the `container-apps-store-api-microservice` sample's deployment scripts. VNet integration, if added later, becomes dramatically more complex. Cost reporting for the `onlinestore-microservice-azure` deployment becomes inaccurate. The `az group delete` cleanup command for the project will leave the SQL server orphaned.

---

### Anti-Pattern 2: Relying Solely on `AllowAzureServices` Without Explicit Container Apps IP Rules

**What it looks like:** Creating only the `AllowAzureServices` firewall rule (0.0.0.0 to 0.0.0.0) and skipping the explicit Container Apps outbound IP firewall rule, reasoning that "Azure services are already allowed."

**Consequences:** The `AllowAzureServices` flag allows traffic from any Azure datacenter IP, not specifically from your Container Apps Environment. While this may appear to work, it is a significant security misconfiguration that violates the principle of least privilege. In environments where Azure Policy enforces firewall rule restrictions, this rule may be automatically reverted by a Defender for Cloud policy, breaking the microservice connection at runtime with no warning. The explicit IP rule is the security-correct and production-auditable approach. Using only the broad rule will also cause Phase 4's deployment to silently pass smoke tests while leaving the database exposed to all Azure-hosted services globally.

---

### Anti-Pattern 3: Hardcoding or Logging the SQL Admin Password in CLI History or Output

**What it looks like:** Passing `--admin-password "MyPass123!"` directly on the command line in a terminal session, storing it in a `.env` file that gets committed to the repository, or echoing it unmasked in deployment logs.

**Consequences:** Shell history files (`.bash_history`, `.zsh_history`) capture the full command including the password in plaintext. If this deployment is run in a shared environment, CI/CD pipeline, or developer workstation, the credential is immediately compromised. The `container-apps-store-api-microservice` repository is a public GitHub sample — if any developer accidentally commits a `.env` file with this password while following this skill, the SQL server becomes publicly accessible within seconds of the push (automated secret scanners and threat actors both monitor GitHub for this pattern). At minimum, this results in mandatory credential rotation, Azure Security Center alerts, and potential data breach disclosure obligations depending on what data has been loaded.

---

### Anti-Pattern 4: Skipping the Connectivity Test Before Exiting the Phase

**What it looks like:** Considering the phase complete after the `az sql db create` command returns success, without running `sqlcmd` or an equivalent TCP connectivity probe, and proceeding directly to Phase 4.

**Consequences:** Azure SQL provisioning can succeed at the control plane level while the database is still in a `Creating` state at the data plane level. Firewall rules can be created without validating that the correct IP is actually registered. Admin passwords can fail complexity validation in edge cases and be silently truncated by some CLI versions. If Phase 4 begins without confirmed end-to-end connectivity, the microservice will fail with `SqlException: A network-related or instance-specific error occurred` on first startup, and the debugging path requires re-entering Phase 3 logic mid-deployment — a far more costly and disruptive failure mode than a two-minute connectivity check at this phase boundary.

---

## 8. AGENT INSTRUCTIONS

The following numbered steps define the exact execution sequence for an AI agent running Phase 3. Each step must be completed and verified before moving to the next.

1. **Read Phase 2 outputs.** Confirm that `RG_NAME`, `LOCATION`, and `CAE_NAME` are available in the current session from Phase 2. If not, run `az group show --name "onlinestore-rg"` to confirm the resource group exists and retrieve its location. Run `az containerapp env show --name "onlinestore-cae" --resource-group "onlinestore-rg"` to confirm the Container Apps Environment is present.

2. **Retrieve the Container Apps Environment outbound IP(s).** Execute:  
   `az containerapp env show --name "$CAE_NAME" --resource-group "$RG_NAME" --query "properties.staticIp" --output tsv`  
   Store the result in `$OUTBOUND_IPS`. If the result is empty or null, query `properties.outboundIpAddresses` instead. Record all IPs. If no IPs are found, log a warning and proceed with the `AllowAzureServices` rule only.

3. **Generate a unique SQL server name.** Construct `SQL_SERVER_NAME="onlinestore-sql-$(openssl rand -hex 4)"`. Verify uniqueness by running `az sql server show --name "$SQL_SERVER_NAME" --resource-group "$RG_NAME"` — if it returns a result (server already exists from a prior attempt), skip creation and proceed to step 5.

4. **Prompt for or generate the SQL admin password.** If running in interactive mode, prompt securely: `read -s -p "Enter SQL admin password: " SQL_ADMIN_PASSWORD`. If running in automated/CI mode, fetch from Azure Key Vault or the pipeline secret store. Validate that the password is at least 16 characters and contains uppercase, lowercase, digit, and special character. If it fails validation, generate one: `SQL_ADMIN_PASSWORD=$(python3 -c "import secrets, string; chars=string.ascii_letters+string.digits+'!@#$%'; print(''.join(secrets.choice(chars) for _ in range(20)))")`.

5. **Create the Azure SQL Logical Server** using the command in Section 3.2. Wait for the command to complete (this is synchronous in Azure CLI). Verify success with `az sql server show --name "$SQL_SERVER_NAME" --resource-group "$RG_NAME" --query "state" --output tsv` — expected value: `Ready`. If the state is not `Ready` after 2 minutes, wait an additional 60 seconds and retry the show command up to 3 times before marking the step as failed.

6. **Create the `ordersdb` database** using the command in Section 3.3. Use `edition="Basic"` for development, `Standard S0` for production as determined by the Decision Logic in Section 4. Wait for completion. Verify: `az sql db show --name "ordersdb" --server "$SQL_SERVER_NAME" --resource-group "$RG_NAME" --query "status" --output tsv` — expected value: `Online`.

7. **Apply firewall rules.** Run the `AllowAzureServices` rule creation command from Section 3.4. Then, for each IP in `$OUTBOUND_IPS`, create a named `ContainerAppsEgressRule` as shown in Section 3.4. Verify all rules are present: `az sql server firewall-rule list --server "$SQL_SERVER_NAME" --resource-group "$RG_NAME" --output table`.

8. **Run the connectivity test** using `sqlcmd` as specified in Section 3.5. The command `SELECT DB_NAME() AS CurrentDatabase` must return `ordersdb`. If `sqlcmd` is not available on the agent host, substitute with a Python one-liner:  
   `python3 -c "import pyodbc; conn = pyodbc.connect('${CONN_STRING}'); cursor = conn.cursor(); cursor.execute('SELECT 1'); print('Connectivity OK:', cursor.fetchone())"`  
   If connectivity fails, follow the Decision Logic in Section 4 — "Decision: Connectivity Test Failure" before proceeding.

9. **Generate and write the ADO.NET connection string** to `.phase3-outputs.env` as shown in Section 3.6. Ensure `.phase3-outputs.env` is listed in the project's `.gitignore`. Log the connection string key name (`CONNECTION_STRING`) but NOT its value to any persistent log.

10. **Enable Microsoft Defender for SQL** using the commands in Section 3.7. Verify with:  
    `az security atp sql show --resource-group "$RG_NAME" --server-name "$SQL_SERVER_NAME" --query "isEnabled" --output tsv`  
    Expected value: `true`.

11. **Apply resource tags** to the SQL logical server using the command in Section 3.8. Verify with:  
    `az sql server show --name "$SQL_SERVER_NAME" --resource-group "$RG_NAME" --query "tags" --output json`  
    Confirm all four tags are present: `project`, `phase`, `managed-by`, `environment`.

12. **Evaluate the Decision Gate.** Go through every criterion in Section 5 sequentially. For each criterion that is not met, execute the specified remediation, then re-check the criterion. Do not proceed to Phase 4 until ALL criteria are confirmed true. Log the final gate evaluation result with a timestamp.

13. **Record all Phase 3 outputs.** Append `SQL_SERVER_NAME`, `SQL_SERVER_FQDN`, `DB_NAME`, and `SQL_ADMIN_USER` to the session's output tracking file. Confirm `.phase3-outputs.env` exists and contains the `CONNECTION_STRING` key. These values are mandatory inputs for Phase 4 and must be accessible at the start of that phase.

14. **Signal Phase 3 complete.** Log the completion message: `"Phase 3: SQL Database Provisioning — COMPLETE. SQL Server: ${SQL_SERVER_FQDN}, Database: ${DB_NAME}, Gate: PASSED. Proceeding to Phase 4: Microservice Deployment."` Do not proceed until this log line is written.