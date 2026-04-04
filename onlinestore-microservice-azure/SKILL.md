---
name: onlinestore-microservice-azure
description: "Deploys a production-grade online store microservice architecture to Azure using Container Apps, Azure SQL Database, and integrated monitoring. Covers four sequential phases: Pre-Provisioning Validation, Container Apps Environment creation, SQL Database Provisioning, and Microservice Deployment from the Azure-Samples/container-apps-store-api-microservice GitHub repository. Handles Azure CLI validation, resource group creation, Container Apps Environment setup, Log Analytics workspace configuration, Azure SQL Server and database provisioning, firewall rule management, connection string injection, Dapr component wiring, and full microservice rollout via Container Apps. Use when user requests to deploy, build, or install an online store microservice on Azure, or when working with Azure Container Apps, Azure SQL, Dapr, or the container-apps-store-api-microservice sample."
license: Proprietary
metadata:
  author: Vishal Anand
  version: "1.0.0"
---

# onlinestore-microservice-azure

## Description

This skill orchestrates the end-to-end deployment of a production-grade online store microservice system on Microsoft Azure. It targets the [Azure-Samples/container-apps-store-api-microservice](https://github.com/Azure-Samples/container-apps-store-api-microservice) reference architecture, which comprises a store front, order service, product service, and Dapr-enabled communication between services. The deployment is executed across four structured phases that enforce prerequisite validation before any cloud resources are created, ensuring idempotent, repeatable runs regardless of environment state.

The infrastructure foundation is Azure Container Apps (ACA), a fully managed serverless container platform that natively integrates Dapr for service-to-service invocation, pub/sub messaging, and state management. A dedicated Log Analytics workspace is provisioned alongside the Container Apps Environment to capture structured logs and enable Azure Monitor-based alerting from day one. Azure SQL Database serves as the persistent backend for order and product data, provisioned in the same resource group to simplify network peering, managed identity bindings, and cost attribution.

The skill is designed for builders and platform engineers who need a repeatable, gate-driven deployment process. Each phase produces verifiable outputs checked by a conditional gate before the next phase begins. Failures at any gate trigger a structured retry with diagnostic guidance rather than silent continuation, reducing the risk of partial deployments and configuration drift.

---

## Interaction Model

1. **Trigger** — User types a keyword such as `deploy`, `build`, or `install` in the context of an online store or Azure microservice deployment.
2. **Skill Load** — Agent loads `SKILL.md` (this file) to understand the full phase sequence, then reads `INT_EXPERIENCE.md` to apply all prior lessons before taking any action.
3. **Phase Execution** — Agent opens the phase file for the current phase, reads it completely, and executes every step in order. No phase is skipped unless the sequencing rules explicitly permit it.
4. **Gate Evaluation** — At the end of each phase the agent evaluates the conditional gate. If the gate condition is not met, the agent retries the phase using the on-fail guidance in that phase file before proceeding.
5. **State Handoff** — Key outputs (resource group name, ACA environment ID, SQL connection string, container app URLs) are recorded in working memory and passed forward as inputs to subsequent phases.
6. **Completion** — Phase 4 is the final phase. On successful deployment the agent reports all service endpoints, connection strings (redacted), and monitoring URLs.
7. **Memory Update** — When the user types `memory`, the agent appends a structured entry to `INT_EXPERIENCE.md` covering any issues encountered during the run.

---

## Phase Reference Files

- [Phase 1 — Pre-Provisioning Validation](phases/phase-1-pre-provisioning-validation.md)
- [Phase 2 — Container Apps Environment](phases/phase-2-container-apps-environment.md)
- [Phase 3 — SQL Database Provisioning](phases/phase-3-sql-database-provisioning.md)
- [Phase 4 — Microservice Deployment](phases/phase-4-microservice-deployment.md)

---

## ASCII Phase Sequence Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                  onlinestore-microservice-azure                      │
│                     Deployment Phase Flow                            │
└──────────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────┐
  │  PHASE 1                        │
  │  Pre-Provisioning Validation    │
  │  · Azure CLI version check      │
  │  · Subscription/auth check      │
  │  · Provider registration check  │
  │  · Region capacity check        │
  └────────────────┬────────────────┘
                   │
                   ▼
        ┌──────────────────────┐
        │  GATE 1 (conditional)│
        │  Pre-Provisioning    │
        │  Validated?          │
        └──────┬───────┬───────┘
          PASS │       │ FAIL
               │       └──────────► RETRY Phase 1
               ▼
  ┌─────────────────────────────────┐
  │  PHASE 2                        │
  │  Container Apps Environment     │
  │  · Create resource group        │
  │  · Deploy Log Analytics WS      │
  │  · Deploy ACA Environment       │
  └────────────────┬────────────────┘
                   │
                   ▼
        ┌──────────────────────┐
        │  GATE 2 (conditional)│
        │  Resource Group &    │
        │  ACA Env Created?    │
        └──────┬───────┬───────┘
          PASS │       │ FAIL
               │       └──────────► RETRY Phase 2
               ▼
  ┌─────────────────────────────────┐
  │  PHASE 3                        │
  │  SQL Database Provisioning      │
  │  · Deploy Azure SQL Server      │
  │  · Create SQL Database          │
  │  · Configure firewall rules     │
  │  · Retrieve connection string   │
  └────────────────┬────────────────┘
                   │
                   ▼
        ┌──────────────────────┐
        │  GATE 3 (conditional)│
        │  SQL Database        │
        │  Provisioning        │
        │  Complete?           │
        └──────┬───────┬───────┘
          PASS │       │ FAIL
               │       └──────────► RETRY Phase 3
               ▼
  ┌─────────────────────────────────┐
  │  PHASE 4                        │
  │  Microservice Deployment        │
  │  · Clone/reference GitHub repo  │
  │  · Configure Dapr components    │
  │  · Deploy store-front app       │
  │  · Deploy order-service app     │
  │  · Deploy product-service app   │
  │  · Validate all service URLs    │
  └────────────────┬────────────────┘
                   │
                   ▼
        ┌──────────────────────┐
        │  GATE 4 — FINAL      │
        │  All services live   │
        │  & reachable         │
        └──────────────────────┘
                   │
                   ▼
         ✅ DEPLOYMENT COMPLETE
```

---

## Phase Overview Table

| Phase # | Name                          | Purpose                                                                 | Key Outputs                                                              | Gate Name                                            |
|---------|-------------------------------|-------------------------------------------------------------------------|--------------------------------------------------------------------------|------------------------------------------------------|
| 1       | Pre-Provisioning Validation   | Confirm tooling, auth, subscription, region, and provider readiness    | Validated CLI version, active subscription ID, registered providers      | Pre-Provisioning Validated? (conditional / retry)    |
| 2       | Container Apps Environment    | Create resource group, Log Analytics workspace, and ACA Environment    | Resource group name, Log Analytics workspace ID, ACA Environment ID      | Resource Group & ACA Env Created? (conditional / retry) |
| 3       | SQL Database Provisioning     | Deploy Azure SQL Server and database in same resource group            | SQL Server FQDN, database name, admin credentials ref, connection string  | SQL Database Provisioning Complete? (conditional / retry) |
| 4       | Microservice Deployment       | Deploy all microservices with Dapr, wired to ACA env and SQL backend   | Store-front URL, order-service URL, product-service URL, Dapr component manifests | Final phase                                   |

---

## Sequencing Rules

### Sequential (must run in order)
- **Phase 1 → Phase 2 → Phase 3 → Phase 4** is the only valid execution order.
- Phase 2 requires the subscription and region validated in Phase 1.
- Phase 3 requires the resource group created in Phase 2.
- Phase 4 requires both the ACA Environment ID (Phase 2) and the SQL connection string (Phase 3).

### Parallelisable
- Within Phase 2, the Log Analytics workspace deployment and the resource group tagging operations can run concurrently.
- Within Phase 4, individual microservice container deployments (store-front, order-service, product-service) can be submitted concurrently after shared Dapr component manifests are applied.

### Skippable (conditional)
- **Phase 2** may be partially skipped if a pre-existing resource group is confirmed in Phase 1 validation and the caller explicitly passes the resource group name. The ACA Environment step must still be executed.
- **Phase 3** may be skipped if an external SQL connection string is provided by the caller at run start. The agent must validate connectivity to that external endpoint before marking the gate as passed.
- **Phase 1** is never skippable under any condition.
- **Phase 4** is never skippable under any condition.

---

## Skills Baseline Table

| Phase | Required Skills                                      | Red Flags                                                                 |
|-------|------------------------------------------------------|---------------------------------------------------------------------------|
| 1     | Azure CLI 2.53+, Bash/PowerShell, Azure RBAC concepts | CLI version below 2.47; no Contributor role on subscription; MFA not completed |
| 2     | Azure Resource Manager, Container Apps, Log Analytics | containerapp extension not installed; region quota exhausted for ACA; missing `Microsoft.App` provider |
| 3     | Azure SQL, firewall rule management, secret storage   | SQL admin password not stored in Key Vault; public access left fully open; SKU mismatch for selected region |
| 4     | Dapr component authoring, Docker/OCI images, YAML     | Dapr sidecar version incompatible with ACA runtime; SQL connection string not injected as secret; container registry pull errors |

---

## Anti-Patterns

1. **Skipping Phase 1 to save time** — Running Phase 2 without validating the Azure CLI version and provider registrations leads to mid-deployment failures that are harder to diagnose than the 2-minute validation cost.

2. **Hard-coding SQL credentials in environment variables** — Injecting the SQL admin password directly as a plain-text Container App environment variable exposes secrets in ARM deployment logs. Always reference Azure Key Vault secrets or use Container Apps secret references.

3. **Using the default consumption plan without capacity planning** — The Container Apps consumption plan scales to zero, which causes cold-start latency for the store-front. Set minimum replicas to 1 for customer-facing services in production.

4. **Creating the SQL Server in a different resource group than the ACA Environment** — Cross-resource-group network rules and managed identity bindings add unnecessary complexity. All resources must share the same resource group per this skill's design.

5. **Deploying Phase 4 microservices before Dapr components are applied** — Container Apps that reference a Dapr state store or pub/sub component will fail to start if the component manifest is not already registered in the ACA Environment. Always apply Dapr components first within Phase 4.

6. **Ignoring Log Analytics workspace linkage** — Deploying the ACA Environment without a linked Log Analytics workspace leaves the deployment with no observability. Structured log queries, container console logs, and system logs all depend on this link being established in Phase 2.

---

## Quick Reference Table

| Practitioner Request                                      | Phase File to Read                                                          |
|-----------------------------------------------------------|-----------------------------------------------------------------------------|
| "Check my Azure CLI and subscription before I start"      | [Phase 1 — Pre-Provisioning Validation](phases/phase-1-pre-provisioning-validation.md) |
| "Create the resource group and Container Apps Environment" | [Phase 2 — Container Apps Environment](phases/phase-2-container-apps-environment.md) |
| "Set up the SQL database for the store"                   | [Phase 3 — SQL Database Provisioning](phases/phase-3-sql-database-provisioning.md) |
| "Deploy the microservices from the GitHub sample"         | [Phase 4 — Microservice Deployment](phases/phase-4-microservice-deployment.md) |
| "Wire up Dapr components to the Container App"            | [Phase 4 — Microservice Deployment](phases/phase-4-microservice-deployment.md) |
| "Configure the Log Analytics workspace for monitoring"    | [Phase 2 — Container Apps Environment](phases/phase-2-container-apps-environment.md) |
| "Validate SQL firewall rules and connectivity"            | [Phase 3 — SQL Database Provisioning](phases/phase-3-sql-database-provisioning.md) |
| "Check what providers need to be registered"              | [Phase 1 — Pre-Provisioning Validation](phases/phase-1-pre-provisioning-validation.md) |
| "Re-deploy after a failed container app rollout"          | [Phase 4 — Microservice Deployment](phases/phase-4-microservice-deployment.md) |
| "I need to retry after a quota error in Phase 2"          | [Phase 2 — Container Apps Environment](phases/phase-2-container-apps-environment.md) |

---

## Execution Memory Protocol

This skill maintains a `INT_EXPERIENCE.md` file in its directory.

**BEFORE every execution:**
- Read `INT_EXPERIENCE.md` carefully
- Apply every lesson and fix listed — do not repeat known mistakes
- Check confirmed working configurations and use them

**AFTER execution — when user types:** `memory`

Append to `INT_EXPERIENCE.md` using ONLY this format:

```
### Issue: [one line title]
- Symptom: [exact error or behaviour that appeared]
- Root cause: [why it happened]
- Fix: [exactly what resolved it — be specific]
- Scope: [all environments / specific region / specific subscription]
- Date: [today]
```

If execution was clean with no new issues, append one line:
`Run [date] [region/env] — clean. Existing fixes confirmed working.`

**Rules:**
- Record issues and fixes ONLY — never log successful steps
- Never duplicate entries already in `INT_EXPERIENCE.md`
- Be specific — vague entries have no value
- After writing, confirm: `"INT_EXPERIENCE.md updated."`