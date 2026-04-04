---
name: discovery-azure-cloud
description: "Discovers and inventories all Azure resource groups, running and stopped resources across an entire Azure subscription, and retrieves current billing/cost data, then generates a structured Excel report. Handles Azure Resource Manager enumeration, resource state inspection (running, stopped, deallocated, failed), cost management API queries, and Excel workbook generation with multiple sheets for resource groups, resources by type, and cost summaries. Use when asked to audit Azure subscriptions, inventory cloud resources, report on cloud spend, generate Azure asset registers, enumerate all VMs and services in Azure, find stopped or idle resources, or produce Azure cost and resource Excel reports."
license: Proprietary
metadata:
  author: skill-advantage
  version: "1.0.0"
---

# Skill: discovery-azure-cloud

## Description

This skill provides a structured, repeatable workflow for performing a full Azure subscription discovery — enumerating every resource group, every resource within those groups (regardless of provisioning or power state), and the current billing cost accrued for the subscription. It is designed for cloud architects, FinOps practitioners, and IT auditors who need an accurate, point-in-time picture of what exists in Azure and what it is costing.

The discovery covers all Azure resource types — including but not limited to Virtual Machines (running and deallocated), App Services, SQL Databases, Storage Accounts, AKS clusters, Key Vaults, Virtual Networks, and any other ARM-managed resource. Resource state metadata (powerState, provisioningState, status) is captured so that idle, stopped, and failed resources are clearly distinguished from healthy running ones. Cost data is retrieved via the Azure Cost Management API (or Consumption API as fallback) for the current billing period and is broken down at the resource-group level where available.

All discovered data is exported into a multi-sheet Excel workbook (.xlsx) using a consistent schema: one sheet per major view (Resource Groups summary, All Resources detail, Resources by Type pivot, Cost by Resource Group, and a Master Dashboard). This makes the output immediately usable for stakeholder reporting, budget reviews, tagging audits, and cloud hygiene initiatives without requiring further transformation.

---

## Interaction Model

An agent or practitioner engages with this skill as follows:

1. **Trigger** — User requests an Azure subscription audit, resource inventory, cost report, or Excel asset register. The agent loads this skill file and the linked phase file.
2. **Prerequisite Check** — Agent confirms Azure credentials are available (CLI login, Service Principal, or Managed Identity) and that the `az` CLI or Azure SDK (Python `azure-mgmt-*`) is accessible in the execution environment.
3. **Subscription Scoping** — Agent identifies or prompts for the target Subscription ID. If the user has multiple subscriptions, a listing step is run first.
4. **Phase Execution** — Agent executes Phase 1 end-to-end: resource group enumeration → per-group resource enumeration → state enrichment → cost query → Excel generation.
5. **Output Delivery** — Agent delivers the `.xlsx` file path and prints a brief summary (total resource groups, total resources, resources by state, total current period cost).
6. **Memory Update** — After execution, if the user types `memory`, agent appends run observations to `INT_EXPERIENCE.md` per the Execution Memory Protocol.

---

## Phase Reference Files

All execution detail, tool calls, prompts, and output schemas live in the phase files below. Claude must read the relevant phase file before beginning execution.

- [Phase 1 — Discover and report Azure cloud resources](phases/phase-1-discover-and-report-azure-cloud-resources.md)

---

## ASCII Phase Sequence Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                  SKILL: discovery-azure-cloud                   │
└─────────────────────────────────────────────────────────────────┘

  START
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 1: Discover and report Azure cloud resources             │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ Enumerate    │→ │ Enumerate    │→ │ Enrich       │         │
│  │ Subscript.   │  │ Resource     │  │ Resource     │         │
│  │ & RG List    │  │ Groups &     │  │ States       │         │
│  │              │  │ Resources    │  │ (power/prov) │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│          │                                                      │
│          ▼                                                      │
│  ┌──────────────┐  ┌──────────────┐                           │
│  │ Query Cost   │→ │ Generate     │                           │
│  │ Management   │  │ Excel        │                           │
│  │ API          │  │ Workbook     │                           │
│  └──────────────┘  └──────────────┘                           │
│                                                                 │
│  GATE: ✅ FINAL PHASE — Excel delivered, summary printed       │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
  END — Deliverable: azure_discovery_<subscription_id>_<date>.xlsx
```

---

## Phase Overview Table

| Phase # | Name | Purpose | Key Outputs | Gate Name |
|---------|------|---------|-------------|-----------|
| 1 | Discover and report Azure cloud resources | Enumerate all resource groups and resources across the Azure subscription; capture resource states (running/stopped/failed/deallocated); query current billing period cost; export all data to a multi-sheet Excel workbook | `azure_discovery_<sub_id>_<date>.xlsx` containing: Resource Groups sheet, All Resources sheet, Resources by Type sheet, Cost by RG sheet, Dashboard sheet; console summary of totals | **FINAL PHASE** |

---

## Sequencing Rules

| Rule | Detail |
|------|--------|
| **Sequential execution** | Phase 1 is the only phase. All steps within it are sequential: subscription → resource groups → resources → state enrichment → cost → Excel. Do not skip the state enrichment step; deallocated/stopped resources must be captured. |
| **Cost query is non-blocking** | If the Cost Management API returns a 403 (insufficient permissions) or quota error, the Excel must still be generated — with the cost columns left blank and a warning note in the Dashboard sheet. Never abort the entire run due to a cost API failure. |
| **Large subscriptions** | For subscriptions with >1,000 resources, use pagination (`--top` / `nextLink`) in ARM queries. Do not truncate results. |
| **Parallel resource enumeration** | Per-resource-group enumeration may be parallelised (e.g., using `asyncio` or concurrent CLI calls) to reduce wall-clock time on large subscriptions. |
| **Credential failure** | If authentication fails, halt immediately with a clear error message listing the required permission scopes before attempting any API calls. |
| **No phase skipping** | This is a single-phase skill. All sub-steps are mandatory except cost (see cost rule above). |

---

## Skills Baseline Table

| Phase | Required Skills | Acceptable Tooling | Red Flags |
|-------|---------------|-------------------|-----------|
| 1 — Resource Enumeration | Azure Resource Manager API, ARM REST or `az` CLI, Python `azure-mgmt-resource` | `az resource list`, `azure-mgmt-resource` SDK, REST ARM API | Agent only queries one resource group — must enumerate ALL. Pagination ignored, resulting in truncated lists. |
| 1 — State Enrichment | Understanding of Azure resource power states vs provisioning states; VM instance view API | `az vm get-instance-view`, `azure-mgmt-compute` `instance_view()` | Reporting only `provisioningState` and missing `powerState` — a VM can be "Succeeded" provisioning but "deallocated" power state. |
| 1 — Cost Management | Azure Cost Management API (`Microsoft.CostManagement/query`), billing period scoping | `az costmanagement query`, `azure-mgmt-costmanagement` SDK | Querying lifetime costs instead of current billing period. Mixing currencies in multi-currency subscriptions. |
| 1 — Excel Generation | Multi-sheet workbook creation, column formatting, table styling | `openpyxl`, `xlsxwriter`, `pandas.ExcelWriter` | Single flat CSV instead of multi-sheet Excel. No column widths or headers set — unreadable output. |
| 1 — Permissions | Subscription-level `Reader` + `Cost Management Reader` RBAC roles minimum | Azure RBAC, Service Principal scoping | Running with `Owner` unnecessarily. Not validating permissions before starting — causes mid-run failures. |

---

## Anti-Patterns

1. **Enumerating only running resources** — The skill explicitly requires capturing resources in ALL states including deallocated, stopped, and failed. Filtering `provisioningState == 'Succeeded'` or `powerState == 'running'` will miss a significant portion of the inventory. Always query all resources and then annotate state.

2. **Ignoring pagination in ARM responses** — Azure ARM API returns a maximum of 1,000 resources per page. Failing to follow `nextLink` tokens results in silently incomplete inventories. This is especially dangerous in large enterprise subscriptions with thousands of resources.

3. **Conflating provisioning state with power state** — `provisioningState: Succeeded` means the resource was successfully created; it says nothing about whether a VM is currently running or deallocated. Always call the VM instance view endpoint separately to get `powerState` for compute resources.

4. **Aborting on cost API failure** — Cost Management API requires specific RBAC permissions (`Cost Management Reader` or `Billing Reader`) that may not be granted in all environments. A permission error on cost queries must not abort the entire discovery. Degrade gracefully: generate the Excel without cost data and note the gap.

5. **Generating a single flat sheet** — Dumping all data into one CSV or one Excel sheet makes the output difficult to use. The required format is a multi-sheet workbook with distinct sheets for resource groups, detailed resources, type pivot, cost breakdown, and a dashboard. Missing this makes the deliverable unprofessional and harder to act on.

6. **Not capturing resource tags** — Azure resource tags are essential context for ownership, environment classification, and cost allocation. Omitting tags from the Excel output removes critical metadata that stakeholders need for hygiene reviews and chargeback reporting.

---

## Quick Reference Table

| Practitioner Request | Phase File to Read |
|---------------------|-------------------|
| "List all resource groups in my Azure subscription" | [Phase 1](phases/phase-1-discover-and-report-azure-cloud-resources.md) |
| "Show me all Azure resources including stopped ones" | [Phase 1](phases/phase-1-discover-and-report-azure-cloud-resources.md) |
| "What is the current cost for my Azure subscription?" | [Phase 1](phases/phase-1-discover-and-report-azure-cloud-resources.md) |
| "Generate an Excel report of all my Azure resources" | [Phase 1](phases/phase-1-discover-and-report-azure-cloud-resources.md) |
| "Find all deallocated or idle VMs in Azure" | [Phase 1](phases/phase-1-discover-and-report-azure-cloud-resources.md) |
| "Audit my Azure subscription for a cost and inventory review" | [Phase 1](phases/phase-1-discover-and-report-azure-cloud-resources.md) |
| "Export Azure resource inventory with tags and states to Excel" | [Phase 1](phases/phase-1-discover-and-report-azure-cloud-resources.md) |
| "How much is Azure costing me this month broken down by resource group?" | [Phase 1](phases/phase-1-discover-and-report-azure-cloud-resources.md) |
| "Create an Azure asset register spreadsheet" | [Phase 1](phases/phase-1-discover-and-report-azure-cloud-resources.md) |
| "Discover all resources in Azure subscription ID xxxx-xxxx" | [Phase 1](phases/phase-1-discover-and-report-azure-cloud-resources.md) |

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
- After writing, confirm: "INT_EXPERIENCE.md updated."