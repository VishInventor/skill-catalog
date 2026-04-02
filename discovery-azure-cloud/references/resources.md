# References & Resources

## discovery-azure-cloud — v1.0.0

---

## Official Microsoft Azure Documentation

### Azure Resource Management

| Resource | URL |
|---|---|
| Azure Resource Manager Overview | https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/overview |
| Azure Resource Groups — Manage Resources | https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/manage-resource-groups-portal |
| List All Resources in a Subscription | https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/manage-resources-rest |
| Azure Resource Graph Overview | https://learn.microsoft.com/en-us/azure/governance/resource-graph/overview |
| Resource Graph Query Language (KQL) | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/query-language |
| Resource Graph Explorer (Portal UI) | https://learn.microsoft.com/en-us/azure/governance/resource-graph/first-query-portal |
| Azure Resource Graph REST API Reference | https://learn.microsoft.com/en-us/rest/api/azureresourcegraph/ |

### Azure Cost Management & Billing

| Resource | URL |
|---|---|
| Azure Cost Management Overview | https://learn.microsoft.com/en-us/azure/cost-management-billing/cost-management-billing-overview |
| Query Usage and Costs with REST API | https://learn.microsoft.com/en-us/rest/api/cost-management/query/usage |
| Azure Cost Management API Reference | https://learn.microsoft.com/en-us/rest/api/cost-management/ |
| Azure Billing REST API | https://learn.microsoft.com/en-us/rest/api/billing/ |
| Consumption API — Usage Details | https://learn.microsoft.com/en-us/rest/api/consumption/usage-details/list |
| Export Costs to Storage with Cost Management | https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-export-acm-data |
| Understand Azure Cost Management Scopes | https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/understand-work-scopes |
| Azure Pricing Calculator | https://azure.microsoft.com/en-us/pricing/calculator/ |
| Azure Retail Prices REST API | https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices |

### Azure Subscription & Identity

| Resource | URL |
|---|---|
| Azure Subscriptions REST API | https://learn.microsoft.com/en-us/rest/api/resources/subscriptions |
| List All Subscriptions | https://learn.microsoft.com/en-us/rest/api/resources/subscriptions/list |
| Azure Active Directory (Entra ID) Authentication | https://learn.microsoft.com/en-us/azure/active-directory/develop/authentication-vs-authorization |
| Azure Managed Identities | https://learn.microsoft.com/en-us/azure/active-directory/managed-identities-azure-resources/overview |
| Service Principal Authentication | https://learn.microsoft.com/en-us/azure/active-directory/develop/app-objects-and-service-principals |
| Azure RBAC — Built-in Roles | https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles |
| Assign Reader Role at Subscription Scope | https://learn.microsoft.com/en-us/azure/role-based-access-control/role-assignments-steps |

---

## Azure SDKs & Client Libraries

### Python SDK (Primary)

| Resource | URL |
|---|---|
| Azure SDK for Python — Overview | https://learn.microsoft.com/en-us/azure/developer/python/sdk/azure-sdk-overview |
| azure-mgmt-resource PyPI Package | https://pypi.org/project/azure-mgmt-resource/ |
| azure-mgmt-resource GitHub Source | https://github.com/Azure/azure-sdk-for-python/tree/main/sdk/resources/azure-mgmt-resource |
| ResourceManagementClient Reference | https://learn.microsoft.com/en-us/python/api/azure-mgmt-resource/azure.mgmt.resource.resources.v2022_09_01.resourcemanagementclient |
| azure-mgmt-costmanagement PyPI Package | https://pypi.org/project/azure-mgmt-costmanagement/ |
| CostManagementClient Reference | https://learn.microsoft.com/en-us/python/api/azure-mgmt-costmanagement/azure.mgmt.costmanagement.costmanagementclient |
| azure-identity PyPI Package | https://pypi.org/project/azure-identity/ |
| DefaultAzureCredential Reference | https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.defaultazurecredential |
| azure-mgmt-consumption PyPI Package | https://pypi.org/project/azure-mgmt-consumption/ |
| azure-mgmt-monitor PyPI Package | https://pypi.org/project/azure-mgmt-monitor/ |
| MonitorManagementClient (Resource Metrics) | https://learn.microsoft.com/en-us/python/api/azure-mgmt-monitor/azure.mgmt.monitor.monitormanagementclient |
| azure-mgmt-compute PyPI Package | https://pypi.org/project/azure-mgmt-compute/ |
| ComputeManagementClient (VM Status) | https://learn.microsoft.com/en-us/python/api/azure-mgmt-compute/azure.mgmt.compute.computemanagementclient |

### Azure CLI Reference

| Resource | URL |
|---|---|
| Azure CLI Installation | https://learn.microsoft.com/en-us/cli/azure/install-azure-cli |
| az resource list — CLI Reference | https://learn.microsoft.com/en-us/cli/azure/resource#az-resource-list |
| az group list — CLI Reference | https://learn.microsoft.com/en-us/cli/azure/group#az-group-list |
| az costmanagement query — CLI Reference | https://learn.microsoft.com/en-us/cli/azure/costmanagement#az-costmanagement-query |
| az vm list — with power state | https://learn.microsoft.com/en-us/cli/azure/vm#az-vm-list |
| az vm get-instance-view — CLI Reference | https://learn.microsoft.com/en-us/cli/azure/vm#az-vm-get-instance-view |
| az graph query — CLI Reference | https://learn.microsoft.com/en-us/cli/azure/graph#az-graph-query |

---

## Excel Report Generation Libraries

| Resource | URL |
|---|---|
| openpyxl Documentation | https://openpyxl.readthedocs.io/en/stable/ |
| openpyxl PyPI Package | https://pypi.org/project/openpyxl/ |
| openpyxl — Working with Styles | https://openpyxl.readthedocs.io/en/stable/styles.html |
| openpyxl — Charts | https://openpyxl.readthedocs.io/en/stable/charts/introduction.html |
| pandas Documentation | https://pandas.pydata.org/docs/ |
| pandas — DataFrame to Excel (to_excel) | https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.to_excel.html |
| pandas PyPI Package | https://pypi.org/project/pandas/ |
| xlsxwriter Documentation | https://xlsxwriter.readthedocs.io/ |
| xlsxwriter — Conditional Formatting | https://xlsxwriter.readthedocs.io/working_with_conditional_formats.html |
| xlsxwriter PyPI Package | https://pypi.org/project/XlsxWriter/ |

---

## Azure Resource Graph — Sample Queries

| Resource | URL |
|---|---|
| Starter Resource Graph Queries | https://learn.microsoft.com/en-us/azure/governance/resource-graph/samples/starter |
| Advanced Resource Graph Queries | https://learn.microsoft.com/en-us/azure/governance/resource-graph/samples/advanced |
| List All Resources by Type | https://learn.microsoft.com/en-us/azure/governance/resource-graph/samples/starter#list-resources |
| Count Resources by Type | https://learn.microsoft.com/en-us/azure/governance/resource-graph/samples/starter#count-resources |
| Resources with Specific Tag | https://learn.microsoft.com/en-us/azure/governance/resource-graph/samples/starter#show-resources-containing-tag |
| VM Power State via Resource Graph | https://learn.microsoft.com/en-us/azure/governance/resource-graph/samples/advanced#list-all-extensions-installed-on-a-virtual-machine |
| Query All Resource Groups with Properties | https://learn.microsoft.com/en-us/azure/governance/resource-graph/samples/starter#list-all-resource-groups |

---

## Azure Resource Provisioning States & Power States

| Resource | URL |
|---|---|
| Azure Resource Provisioning States | https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/resource-manager-deployment-model |
| VM Power States and Life Cycle | https://learn.microsoft.com/en-us/azure/virtual-machines/states-billing |
| Azure App Service States | https://learn.microsoft.com/en-us/azure/app-service/overview |
| Azure SQL Database Status | https://learn.microsoft.com/en-us/azure/azure-sql/database/resource-limits-logical-server |
| Azure Kubernetes Service Node Pool States | https://learn.microsoft.com/en-us/azure/aks/start-stop-cluster |

---

## Authentication & Security Best Practices

| Resource | URL |
|---|---|
| Azure Authentication Best Practices | https://learn.microsoft.com/en-us/azure/security/fundamentals/identity-management-best-practices |
| Credential Chain — DefaultAzureCredential | https://learn.microsoft.com/en-us/azure/developer/python/sdk/authentication-overview |
| Authenticate with Service Principal (Python) | https://learn.microsoft.com/en-us/azure/developer/python/sdk/authentication-service-principal |
| Least Privilege RBAC for Cost Management | https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/assign-access-acm-data |
| Required Permissions — Resource Graph Queries | https://learn.microsoft.com/en-us/azure/governance/resource-graph/overview#permissions-in-azure-resource-graph |
| Store Secrets in Azure Key Vault | https://learn.microsoft.com/en-us/azure/key-vault/secrets/quick-create-python |

---

## Reference Architectures

| Resource | URL |
|---|---|
| Azure Cloud Adoption Framework — Landing Zones | https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/landing-zone/ |
| Azure Architecture Center — Management & Governance | https://learn.microsoft.com/en-us/azure/architecture/framework/devops/principles |
| Well-Architected Framework — Cost Optimization | https://learn.microsoft.com/en-us/azure/architecture/framework/cost/overview |
| Azure Monitor Architecture Overview | https://learn.microsoft.com/en-us/azure/azure-monitor/overview |
| Azure Resource Inventory Open Source Tool | https://github.com/microsoft/ARI |
| Cloud Custodian — Azure Policy Engine | https://cloudcustodian.io/docs/azure/gettingstarted.html |

---

## Environment Variables & Configuration Reference

The skill uses the following environment variables for authentication and targeting. Set these before invoking the skill.

| Variable | Purpose | Required |
|---|---|---|
| `AZURE_SUBSCRIPTION_ID` | Target subscription UUID | Yes |
| `AZURE_TENANT_ID` | Entra ID tenant UUID | Yes (SP auth) |
| `AZURE_CLIENT_ID` | Service principal app ID | Yes (SP auth) |
| `AZURE_CLIENT_SECRET` | Service principal secret | Yes (SP auth) |
| `AZURE_OUTPUT_PATH` | Directory for generated Excel report | Optional |
| `AZURE_BILLING_PERIOD` | Billing period in `YYYYMM` format | Optional |
| `AZURE_COST_GRANULARITY` | `None`, `Daily`, or `Monthly` | Optional |

---

## Required Python Dependencies

```text
azure-identity>=1.15.0
azure-mgmt-resource>=23.0.0
azure-mgmt-costmanagement>=4.0.0
azure-mgmt-consumption>=10.0.0
azure-mgmt-compute>=30.0.0
azure-mgmt-monitor>=6.0.0
azure-mgmt-network>=25.0.0
openpyxl>=3.1.2
pandas>=2.1.0
```

---

## Useful Community Resources

| Resource | URL |
|---|---|
| Azure SDK for Python GitHub Repository | https://github.com/Azure/azure-sdk-for-python |
| Azure Resource Graph GitHub Samples | https://github.com/Azure-Samples/resource-graph |
| Stack Overflow — azure-resource-graph Tag | https://stackoverflow.com/questions/tagged/azure-resource-graph |
| Stack Overflow — azure-cost-management Tag | https://stackoverflow.com/questions/tagged/azure-cost-management |
| Microsoft Q&A — Azure Cost Management | https://learn.microsoft.com/en-us/answers/tags/97/azure-cost-management |
| Azure Feedback Portal | https://feedback.azure.com/d365community |

---

## Changelog

| Version | Date | Notes |
|---|---|---|
| 1.0.0 | 2025-07 | Initial release — resource discovery + cost + Excel export |