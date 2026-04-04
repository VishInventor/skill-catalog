# References & Resources

## Databricks-full-discovery v1.0.0
### Compiled by Vishal Anand

---

## Author Assets

### Palantir Foundry — Ontology Reference
- **URL:** [https://www.palantir.com/platforms/foundry/](https://www.palantir.com/platforms/foundry/)
- **Purpose:** Primary reference for Ontology diagram structure, entity-relationship modelling conventions, and dependency mapping methods used to produce the Phase 3 draw.io output.
- **Usage in skill:** The Palantir Foundry Ontology methodology is the canonical pattern for representing objects, actions, and links in the final discovery diagram. Entities discovered in Phase 2 (workspaces, catalogs, schemas, pipelines, compute clusters, warehouses, dashboards, AI-BI agents) are modelled as typed objects; relationships (reads-from, writes-to, triggers, depends-on, governed-by) are modelled as typed links — mirroring Foundry's Object Type / Link Type construct.

---

## Official Databricks Documentation

### Core Platform
| Resource | URL |
|---|---|
| Databricks Documentation Home | https://docs.databricks.com |
| Databricks REST API Reference (2.0 / 2.1) | https://docs.databricks.com/api/workspace/introduction |
| Databricks CLI Reference | https://docs.databricks.com/dev-tools/cli/index.html |
| Databricks SDK for Python | https://databricks-sdk-py.readthedocs.io/en/latest/ |
| Databricks SDK for Go | https://pkg.go.dev/github.com/databricks/databricks-sdk-go |
| Authentication and Secrets | https://docs.databricks.com/dev-tools/auth/index.html |
| Personal Access Tokens (PATs) | https://docs.databricks.com/dev-tools/auth/pat.html |
| OAuth M2M Authentication | https://docs.databricks.com/dev-tools/auth/oauth-m2m.html |

### Unity Catalog — Metastore, Catalogs & Governance
| Resource | URL |
|---|---|
| Unity Catalog Overview | https://docs.databricks.com/data-governance/unity-catalog/index.html |
| Unity Catalog API — Catalogs | https://docs.databricks.com/api/workspace/catalogs |
| Unity Catalog API — Schemas | https://docs.databricks.com/api/workspace/schemas |
| Unity Catalog API — Tables | https://docs.databricks.com/api/workspace/tables |
| Unity Catalog API — External Locations | https://docs.databricks.com/api/workspace/externallocations |
| Unity Catalog API — Storage Credentials | https://docs.databricks.com/api/workspace/storagecredentials |
| Unity Catalog API — Connections (Lakehouse Federation) | https://docs.databricks.com/api/workspace/connections |
| Data Lineage in Unity Catalog | https://docs.databricks.com/data-governance/unity-catalog/data-lineage.html |
| System Tables Reference | https://docs.databricks.com/administration-guide/system-tables/index.html |

### Compute — Clusters & Warehouses
| Resource | URL |
|---|---|
| Clusters API 2.0 | https://docs.databricks.com/api/workspace/clusters |
| Clusters API 2.1 (Policy & Instance Pools) | https://docs.databricks.com/api/workspace/instancepools |
| List Running Clusters | https://docs.databricks.com/api/workspace/clusters/list |
| SQL Warehouses API | https://docs.databricks.com/api/workspace/warehouses |
| Serverless Compute Overview | https://docs.databricks.com/serverless-compute/index.html |
| Compute Policies | https://docs.databricks.com/administration-guide/clusters/policies.html |

### Data Pipelines — Delta Live Tables & Ingestion
| Resource | URL |
|---|---|
| Delta Live Tables Overview | https://docs.databricks.com/delta-live-tables/index.html |
| DLT Pipelines API | https://docs.databricks.com/api/workspace/pipelines |
| DLT Pipeline Events & Lineage | https://docs.databricks.com/delta-live-tables/observability.html |
| Medallion Architecture on Databricks | https://docs.databricks.com/lakehouse/medallion.html |
| Auto Loader (Cloud File Ingestion) | https://docs.databricks.com/ingestion/auto-loader/index.html |
| COPY INTO (Batch Ingestion) | https://docs.databricks.com/ingestion/copy-into/index.html |
| Databricks Workflows (Jobs API) | https://docs.databricks.com/api/workspace/jobs |
| Workflow Orchestration Overview | https://docs.databricks.com/workflows/index.html |
| Partner Connect (Source Connectors) | https://docs.databricks.com/integrations/partner-connect/index.html |
| Lakehouse Federation (Query Federation) | https://docs.databricks.com/query-federation/index.html |

### Dashboards & AI-BI
| Resource | URL |
|---|---|
| Databricks SQL Dashboards (Legacy) | https://docs.databricks.com/sql/user/dashboards/index.html |
| AI/BI Dashboards (Lakeview) | https://docs.databricks.com/dashboards/index.html |
| AI/BI Genie (Conversational Analytics) | https://docs.databricks.com/genie/index.html |
| Lakeview Dashboards API | https://docs.databricks.com/api/workspace/lakeview |
| SQL Queries API | https://docs.databricks.com/api/workspace/queries |
| Alerts API | https://docs.databricks.com/api/workspace/alerts |

### MLflow & AI — Model Tracking and Agents
| Resource | URL |
|---|---|
| MLflow on Databricks | https://docs.databricks.com/mlflow/index.html |
| MLflow Tracking Server API | https://mlflow.org/docs/latest/rest-api.html |
| Model Registry API | https://docs.databricks.com/api/workspace/modelregistry |
| Unity Catalog Model Registry | https://docs.databricks.com/machine-learning/manage-model-lifecycle/index.html |
| Mosaic AI (Databricks AI Functions) | https://docs.databricks.com/machine-learning/ai-functions/index.html |
| Vector Search API | https://docs.databricks.com/generative-ai/vector-search.html |
| Databricks AI Agents (Agent Framework) | https://docs.databricks.com/generative-ai/agent-framework/index.html |

### Workspace & Administration
| Resource | URL |
|---|---|
| Workspace API | https://docs.databricks.com/api/workspace/workspace |
| Account API (Multi-workspace) | https://docs.databricks.com/api/account/introduction |
| Groups & Permissions API | https://docs.databricks.com/api/workspace/groups |
| Service Principals API | https://docs.databricks.com/api/workspace/serviceprincipals |
| Workspace Repos API | https://docs.databricks.com/api/workspace/repos |
| Secret Scopes API | https://docs.databricks.com/api/workspace/secrets |
| IP Access Lists API | https://docs.databricks.com/api/workspace/ipaccesslists |
| Workspace Settings API | https://docs.databricks.com/api/workspace/settings |

---

## Key Tools & Their Documentation

### Connectivity & Pre-discovery (Phase 1)
| Tool | Purpose | Documentation |
|---|---|---|
| Databricks CLI | Workspace ping, config profiles, token validation | https://docs.databricks.com/dev-tools/cli/index.html |
| `databricks auth env` | Resolve and validate active credential chain | https://docs.databricks.com/dev-tools/cli/authentication.html |
| `curl` / `httpie` | Raw REST probe for `/api/2.0/clusters/list` reachability check | https://httpie.io/docs |
| Python `requests` library | Scripted connectivity pre-flight checks | https://requests.readthedocs.io |
| Databricks SDK `WorkspaceClient` | Programmatic workspace connectivity test | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/workspace.html |
| Network connectivity checker | TLS/port 443 reachability to `*.azuredatabricks.net` / `*.cloud.databricks.com` / `*.gcp.databricks.com` | https://docs.databricks.com/administration-guide/cloud-configurations/aws/customer-managed-vpc.html |

### Discovery Execution (Phase 2)
| Tool | Purpose | Documentation |
|---|---|---|
| Databricks SDK for Python | Primary programmatic discovery client | https://databricks-sdk-py.readthedocs.io |
| Unity Catalog system tables (`system.information_schema`) | SQL-based bulk discovery of catalogs, schemas, tables, columns, lineage | https://docs.databricks.com/administration-guide/system-tables/information-schema.html |
| `system.access.audit` | Audit log query to identify active data sources and access patterns | https://docs.databricks.com/administration-guide/system-tables/audit.html |
| `system.compute.clusters` | Historical and active cluster inventory | https://docs.databricks.com/administration-guide/system-tables/compute.html |
| `system.lakeflow` (DLT system table) | Delta Live Tables pipeline run history | https://docs.databricks.com/administration-guide/system-tables/lakeflow.html |
| Terraform Databricks Provider | Cross-reference discovered state against IaC definitions | https://registry.terraform.io/providers/databricks/databricks/latest/docs |
| `jq` | JSON output processing for REST API responses | https://jqlang.github.io/jq/manual/ |

### Ontology Diagramming (Phase 3)
| Tool | Purpose | Documentation |
|---|---|---|
| draw.io (diagrams.net) | Target diagramming tool for ontology output | https://www.drawio.com |
| draw.io XML schema | Understanding `.drawio` file format for programmatic generation | https://jgraph.github.io/mxgraph/docs/js-api/files/io/mxCodec-js.html |
| `diagrams` Python library | Code-first diagram generation (can export draw.io-compatible XML) | https://diagrams.mingrammer.com |
| Palantir Ontology SDK (reference model) | Object Type / Link Type / Action Type conventions used as modelling reference | https://www.palantir.com/platforms/foundry/ |
| NetworkX | Python graph library for dependency graph construction before render | https://networkx.org/documentation/stable/ |
| Graphviz | Optional layout engine for complex dependency graphs | https://graphviz.org/documentation/ |

---

## Reference Architectures

### Databricks Lakehouse Architecture
- **Medallion Architecture (Bronze / Silver / Gold):** https://docs.databricks.com/lakehouse/medallion.html
- **Lakehouse Reference Architecture (AWS):** https://databricks.com/solutions/aws
- **Lakehouse Reference Architecture (Azure):** https://learn.microsoft.com/en-us/azure/architecture/solution-ideas/articles/azure-databricks-modern-analytics-architecture
- **Lakehouse Reference Architecture (GCP):** https://databricks.com/solutions/gcp
- **Data Mesh on Databricks with Unity Catalog:** https://www.databricks.com/blog/2022/10/10/databricks-unity-catalog-data-mesh.html
- **Streaming Lakehouse Pattern (Kafka + Auto Loader + DLT):** https://www.databricks.com/blog/2022/08/09/real-time-lakehouse-with-delta-live-tables.html

### Ontology & Knowledge Graph Patterns
- **Palantir Foundry Ontology Whitepaper:** https://www.palantir.com/platforms/foundry/
- **W3C RDF/OWL Ontology Standards (academic reference):** https://www.w3.org/TR/owl2-overview/
- **Knowledge Graph Construction Patterns:** https://arxiv.org/abs/2003.02320

---

## Community & Supplementary Resources

| Resource | URL |
|---|---|
| Databricks Community Forum | https://community.databricks.com |
| Databricks Engineering Blog | https://www.databricks.com/blog/category/engineering |
| Awesome Databricks (curated GitHub list) | https://github.com/dhruv-kanojia/awesome-databricks |
| Databricks Notebook Examples (GitHub) | https://github.com/databricks/notebook_gallery |
| Delta Lake Documentation | https://docs.delta.io/latest/index.html |
| MLflow Documentation | https://mlflow.org/docs/latest/index.html |
| Apache Spark Documentation | https://spark.apache.org/docs/latest/ |
| draw.io GitHub (source & issue tracker) | https://github.com/jgraph/drawio |

---

## API Endpoint Quick Reference for Discovery Scripting

```
# Phase 1 — Connectivity probes
GET  /api/2.0/clusters/list                          # Cluster API reachability
GET  /api/2.1/unity-catalog/metastores               # Metastore reachability

# Phase 2 — Discovery endpoints
GET  /api/2.1/unity-catalog/catalogs                 # All catalogs
GET  /api/2.1/unity-catalog/schemas?catalog_name=X   # Schemas per catalog
GET  /api/2.1/unity-catalog/tables?catalog_name=X&schema_name=Y  # Tables
GET  /api/2.0/pipelines                              # DLT pipelines
GET  /api/2.0/jobs                                   # Workflow jobs
GET  /api/2.0/clusters/list                          # Running clusters
GET  /api/2.0/sql/warehouses                         # SQL warehouses
GET  /api/2.0/preview/sql/dashboards                 # Legacy dashboards
GET  /api/2.0/lakeview/dashboards                    # AI/BI dashboards
GET  /api/2.0/mlflow/registered-models/list          # MLflow models
GET  /api/2.1/unity-catalog/connections              # External connections
GET  /api/2.0/secrets/scopes/list                    # Secret scopes (source hints)
```

---

*Last reviewed: 2025 — Databricks Runtime 15.x / Unity Catalog GA / AI-BI Genie GA*
*Maintained by: Vishal Anand | databricks-full-discovery v1.0.0*