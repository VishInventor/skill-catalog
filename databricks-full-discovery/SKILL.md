---
name: databricks-full-discovery
description: "Performs a complete end-to-end discovery of an entire Databricks environment, covering workspace connectivity, Unity Catalog structure, medallion data pipelines, ingestion pipelines, source data connections, running compute clusters, SQL warehouses, dashboards, and AI-BI agents. Executes in three sequential phases: Pre-discovery (connectivity validation), Discover (full environment scan), and Ontology (Palantir-style dependency graph rendered as a draw.io diagram saved to Desktop). Produces a structured ontology diagram capturing all discovered assets and their relationships. Use when asked to scan, discover, inventory, or map a Databricks environment, or when keywords 'discovery' or 'scan' are present in context."
license: Proprietary
metadata:
  author: Vishal Anand
  version: "1.0.0"
---

# Databricks Full Discovery

## Description

This skill orchestrates a systematic, production-grade discovery of an entire Databricks environment — from workspace endpoints down to individual running assets — and synthesises all findings into a structured, Palantir-style ontology diagram. It is designed for platform engineers, data architects, and cloud consultants who need an authoritative inventory of a Databricks deployment before migration, optimisation, governance reviews, or architectural documentation exercises.

The discovery spans every material layer of the Databricks estate: Unity Catalog metastores, catalogs, schemas, and tables; Delta Live Tables and Lakeflow pipelines implementing medallion (Bronze → Silver → Gold) architectures; data ingestion pipelines and their upstream source connections (JDBC, cloud storage, Kafka, partner connectors); active compute clusters and their configurations; running SQL warehouses; published dashboards; and deployed AI-BI Genie agents. Each asset is captured with its metadata, ownership, and dependency relationships, not merely its existence.

The terminal output of the skill is a draw.io-compatible XML diagram file placed on the practitioner's Desktop, representing all discovered entities as an ontology graph with typed edges for data flow, compute dependency, ownership, and lineage relationships. This diagram serves as the single source of truth for downstream architecture decisions, cost reviews, and governance onboarding.

---

## Interaction Model

1. **Trigger** — The practitioner invokes the skill verbally or in writing using keywords such as `discovery`, `scan`, `inventory`, `map Databricks environment`, or by directly referencing the skill name.
2. **Credential Handoff** — The agent prompts for Databricks workspace URLs, personal access tokens (or Entra ID / Okta OIDC credentials), and Unity Catalog metastore identifiers if not already present in the session context.
3. **Phase Sequencing** — The agent executes phases strictly in order (1 → 2 → 3). Each phase gate is evaluated before proceeding. Failed gates trigger a configurable retry before halting.
4. **Progress Narration** — The agent emits a structured status line after each major sub-task (e.g., `[DISCOVER] Clusters: 14 found | Warehouses: 6 found | Pipelines: 9 found`).
5. **Artefact Delivery** — On Phase 3 completion, the agent writes `databricks-ontology.drawio` to `~/Desktop/` and prints the absolute path for confirmation.
6. **Memory Update** — After execution, the practitioner types `memory` to trigger the INT_EXPERIENCE.md update protocol.

---

## Phase Reference Files

All execution detail, tooling commands, API endpoint lists, output schemas, and gate logic live in the individual phase files below. Claude must read the relevant phase file before executing that phase.

- [Phase 1 — Pre-discovery](phases/phase-1-pre-discovery.md)
- [Phase 2 — Discover](phases/phase-2-discover.md)
- [Phase 3 — Ontology](phases/phase-3-ontology.md)

---

## ASCII Phase Sequence Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                  DATABRICKS FULL DISCOVERY SKILL                    │
└─────────────────────────────────────────────────────────────────────┘

   START
     │
     ▼
┌──────────────────────────────┐
│  PHASE 1 — PRE-DISCOVERY     │
│  Check workspace & catalog   │
│  connectivity                │
└──────────────────┬───────────┘
                   │
                   ▼
          ┌────────────────┐
          │  GATE:         │
          │  Connectivity  │◄─────────────────┐
          └──────┬─────────┘                  │
                 │                            │
         ┌───────┴────────┐                   │
         │ PASS           │ FAIL              │
         │                ▼                   │
         │        ┌───────────────┐           │
         │        │  RETRY (n≤3)  │───────────┘
         │        └───────────────┘
         │                        └── HALT if max retries exceeded
         ▼
┌──────────────────────────────┐
│  PHASE 2 — DISCOVER          │
│  Workspaces, catalogs,       │
│  pipelines, compute,         │
│  warehouses, dashboards,     │
│  AI-BI agents                │
└──────────────────┬───────────┘
                   │
                   ▼
          ┌────────────────────┐
          │  GATE:             │
          │  Discovery         │◄─────────────────┐
          │  Complete?         │                  │
          └──────┬─────────────┘                  │
                 │                                │
         ┌───────┴────────┐                       │
         │ PASS           │ FAIL                  │
         │                ▼                       │
         │        ┌───────────────┐               │
         │        │  RETRY (n≤3)  │───────────────┘
         │        └───────────────┘
         │                        └── HALT if max retries exceeded
         ▼
┌──────────────────────────────┐
│  PHASE 3 — ONTOLOGY          │
│  Build Palantir-style graph, │
│  render draw.io diagram,     │
│  save to Desktop             │
└──────────────────┬───────────┘
                   │
                   ▼
          ┌────────────────┐
          │  GATE:         │
          │  Final Phase   │
          └──────┬─────────┘
                 │
                 ▼
   ✅  databricks-ontology.drawio → ~/Desktop/
   END
```

---

## Phase Overview Table

| Phase # | Name           | Purpose                                                                                                                          | Key Outputs                                                                                                                  | Gate Name          |
|---------|----------------|----------------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------|--------------------|
| 1       | Pre-discovery  | Validate network reachability and authentication for every target Databricks workspace and Unity Catalog metastore               | Connectivity report (per workspace: status, latency, auth method, API version); list of reachable vs. unreachable endpoints  | Connectivity       |
| 2       | Discover       | Enumerate all running and configured assets across workspaces: catalogs, pipelines, compute, warehouses, dashboards, AI-BI agents | Structured JSON inventory per asset class; dependency map (raw); counts per category; unresolved reference list              | Discovery Complete |
| 3       | Ontology       | Synthesise inventory into a typed entity-relationship graph; render as draw.io XML; persist to Desktop                          | `databricks-ontology.drawio` file; ontology entity manifest (Markdown summary); edge-type legend                            | Final Phase        |

---

## Sequencing Rules

| Rule | Detail |
|------|--------|
| **Strictly Sequential** | Phases 1 → 2 → 3 must execute in order. No phase may begin until its predecessor's gate passes. |
| **Not Parallelisable** | Phase 2 requires confirmed connectivity from Phase 1. Phase 3 requires a complete inventory from Phase 2. No phase may run concurrently with another. |
| **Phase 1 — Mandatory** | Cannot be skipped. Attempting Phase 2 without a passed Connectivity gate will produce incomplete and unreliable discovery results. |
| **Phase 2 — Mandatory** | Cannot be skipped. Phase 3 has no data to graph without Phase 2 outputs. |
| **Phase 3 — Mandatory** | The draw.io ontology is the primary deliverable of the skill. Skipping produces no client-facing artefact. |
| **Retry Behaviour** | Phases 1 and 2 support up to 3 automatic retries on gate failure before escalating to the practitioner for manual intervention. Phase 3 is terminal — failures require root-cause analysis of Phase 2 data quality. |
| **Partial Workspace Sets** | If some workspaces fail Phase 1 and cannot be recovered in retries, the agent may proceed to Phase 2 with the reachable subset, clearly marking unreachable workspaces as `OUT_OF_SCOPE` in all outputs. |

---

## Skills Baseline Table

| Phase | Required Practitioner / Agent Skills | Red Flags |
|-------|--------------------------------------|-----------|
| **Phase 1 — Pre-discovery** | Databricks REST API v2.0/v2.1 familiarity; PAT and OIDC auth configuration; network/firewall troubleshooting; Unity Catalog metastore topology awareness | Cannot distinguish workspace-level vs. account-level API endpoints; no access to account console; PATs expired or missing required scopes |
| **Phase 2 — Discover** | Unity Catalog API (catalogs, schemas, tables, lineage); Jobs API; Clusters API; Pipelines API (DLT/Lakeflow); SQL Warehouses API; Dashboards API; AI-BI Genie API; ability to parse paginated API responses; understanding of medallion architecture patterns | Treating Delta Live Tables and Workflow Jobs as the same construct; missing `LIST` privilege on catalogs; no account-level admin token for cross-workspace discovery |
| **Phase 3 — Ontology** | draw.io XML schema authorship; Palantir Ontology modelling concepts (object types, link types, properties); graph layout algorithms (hierarchical preferred); ability to classify entity types and relationship semantics | Producing a flat list diagram instead of a typed graph; omitting data-flow directionality on edges; failing to distinguish compute dependency edges from data lineage edges |

---

## Anti-Patterns

| # | Anti-Pattern | Why It Derails Discovery |
|---|-------------|--------------------------|
| 1 | **Skipping Pre-discovery and hitting the API directly** | Authentication failures in Phase 2 produce silent empty results — the agent believes there are no clusters or pipelines when in fact it simply lacks access. The connectivity gate exists to surface this early. |
| 2 | **Using only workspace-level tokens without account-level admin access** | Unity Catalog metastore enumeration, cross-workspace lineage, and account-level user/group data all require account console API access. Workspace-only tokens yield a dangerously incomplete picture. |
| 3 | **Conflating DLT pipelines with Workflow Jobs in the inventory** | Delta Live Tables pipelines and Databricks Workflow Jobs are distinct constructs with separate APIs, different compute models, and different lineage semantics. Merging them produces a corrupted dependency graph in Phase 3. |
| 4 | **Generating the ontology diagram before discovery is fully complete** | Drawing the graph on partial data embeds structural gaps that are invisible to the reader. Always enforce the Discovery Complete gate before entering Phase 3. |
| 5 | **Producing a flat node list instead of a typed ontology graph** | A spreadsheet or flat list of assets is not an ontology. Phase 3 must produce typed object classes, typed link/edge classes, and directional relationships — matching Palantir Foundry ontology semantics — otherwise the diagram has no analytical value. |
| 6 | **Ignoring stopped or terminated assets** | Discovery scoped only to `RUNNING` state assets misses warehouses in auto-suspend, pipelines in IDLE state, and clusters recently terminated. The inventory must capture all assets with state as an attribute, not a filter. |

---

## Quick Reference Table

| Practitioner Request | Phase File to Read |
|---------------------|--------------------|
| "Check if I can connect to my Databricks workspaces" | [Phase 1 — Pre-discovery](phases/phase-1-pre-discovery.md) |
| "Validate my PAT tokens and API access" | [Phase 1 — Pre-discovery](phases/phase-1-pre-discovery.md) |
| "List all catalogs and schemas in Unity Catalog" | [Phase 2 — Discover](phases/phase-2-discover.md) |
| "Find all running compute clusters and SQL warehouses" | [Phase 2 — Discover](phases/phase-2-discover.md) |
| "Discover all Delta Live Tables / medallion pipelines" | [Phase 2 — Discover](phases/phase-2-discover.md) |
| "What data sources are connected to this environment?" | [Phase 2 — Discover](phases/phase-2-discover.md) |
| "Find all dashboards and AI-BI Genie agents" | [Phase 2 — Discover](phases/phase-2-discover.md) |
| "Build a dependency map of everything discovered" | [Phase 3 — Ontology](phases/phase-3-ontology.md) |
| "Generate a draw.io ontology diagram and save to Desktop" | [Phase 3 — Ontology](phases/phase-3-ontology.md) |
| "Show me relationships between pipelines and compute" | [Phase 3 — Ontology](phases/phase-3-ontology.md) |

---

## Execution Memory Protocol

This skill maintains a `INT_EXPERIENCE.md` file in its directory.

**BEFORE every execution:**
- Read `INT_EXPERIENCE.md` carefully
- Apply every lesson and fix listed — do not repeat known mistakes
- Check confirmed working configurations and use them

**AFTER execution — when user types: `memory`**
Append to `INT_EXPERIENCE.md` using ONLY this format:

### Issue: [one line title]
- Symptom: [exact error or behaviour that appeared]
- Root cause: [why it happened]
- Fix: [exactly what resolved it — be specific]
- Scope: [all environments / specific region / specific subscription]
- Date: [today]

If execution was clean with no new issues, append one line:
`Run [date] [region/env] — clean. Existing fixes confirmed working.`

**Rules:**
- Record issues and fixes ONLY — never log successful steps
- Never duplicate entries already in `INT_EXPERIENCE.md`
- Be specific — vague entries have no value
- After writing, confirm: "INT_EXPERIENCE.md updated."