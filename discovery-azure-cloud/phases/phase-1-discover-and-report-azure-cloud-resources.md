# Phase 1: Discover and Report Azure Cloud Resources

**Skill:** `discovery-azure-cloud` | **Version:** 1.0.0 | **Phase:** 1 of 1 (Final)

---

## 1. PURPOSE

This phase is the complete operational body of the `discovery-azure-cloud` skill. It exists to produce a verified, exhaustive inventory of every Azure resource group, every resource within those groups (regardless of running state), and the current billing cost across the entire subscription — all consolidated into a structured Excel workbook. Without this phase executing correctly, there is no deliverable: no inventory, no cost visibility, and no basis for governance, rightsizing, or compliance reviews.

The phase addresses a critical operational gap in Azure environments where resources are created across multiple resource groups by different teams, projects, and automated pipelines. Resources in stopped, deallocated, or failed states are frequently overlooked in manual reviews yet continue to incur storage and reservation costs. By explicitly targeting all provisioning states — `Succeeded`, `Failed`, `Deleting`, `Creating`, `Updating`, `Canceled` — this phase ensures nothing is invisible to the reporting output.

Without this phase, stakeholders operating on incomplete resource lists risk orphaned resource sprawl, untracked cost accumulation on deallocated VMs and idle disks, compliance violations from forgotten resources in sensitive resource groups, and capacity planning errors. The Excel workbook produced here becomes the single source of truth for the subscription snapshot at the time of execution.

---

## 2. KEY ACTIVITIES

- **Authenticate to the target Azure subscription** using the Azure CLI (`az login` with service principal credentials or interactive login), then explicitly set the active subscription context with `az account set --subscription <SUBSCRIPTION_ID>` to ensure all subsequent API calls are scoped correctly. Verify the active subscription is confirmed before proceeding.

- **Enumerate all resource groups in the subscription** by calling `az group list --output json`, capturing the `name`, `location`, `tags`, and `properties.provisioningState` fields for every resource group. Record the total count of resource groups found for validation against the Excel output.

- **Enumerate all resources across every resource group** using `az resource list --output json` at the subscription scope (not per-group) to retrieve all resources in a single call, capturing `id`, `name`, `type`, `resourceGroup`, `location`, `kind`, `sku`, `tags`, and `properties.provisioningState`. This avoids per-group iteration latency.

- **Determine runtime operational state for compute resources** because `provisioningState` alone is insufficient. For Virtual Machines, issue `az vm get-instance-view --ids <VM_ID>` to capture `statuses[].displayStatus` (e.g., `VM running`, `VM deallocated`, `VM stopped`). For App Services, call `az webapp show --ids <APP_ID>` to read `state`. For AKS clusters, call `az aks show --ids <AKS_ID>` to read `powerState.code`.

- **Retrieve subscription-level cost data** by calling the Azure Cost Management REST API: `GET https://management.azure.com/subscriptions/{subscriptionId}/providers/Microsoft.CostManagement/query?api-version=2023-11-01` with a request body specifying `timeframe: MonthToDate`, `type: ActualCost`, and grouping by `ResourceGroup` and `ResourceType`. Also issue a top-level total query with no grouping to capture the single subscription aggregate cost figure.

- **Normalize and merge all collected data** into a unified Python data structure (list of dicts) where every resource record is enriched with its parent resource group's metadata (location, tags, provisioning state) and its cost allocation from the Cost Management API response. Resources with no cost match receive a `$0.00` cost value — they are not omitted.

- **Detect and flag resources in non-running states** by applying explicit status classification logic to each resource: categorize each as `Running`, `Stopped/Deallocated`, `Failed`, `Creating`, `Updating`, or `Unknown` based on the combination of `provisioningState` and the runtime power state fetched in the compute enrichment step. Non-running resources must be visually differentiated in the Excel output.

- **Generate the multi-sheet Excel workbook** using `openpyxl` with four sheets: `Summary` (subscription name, ID, total resource count, total cost, timestamp), `Resource Groups` (one row per RG), `All Resources` (one row per resource with all enriched fields), and `Cost Breakdown` (cost grouped by resource group and resource type). Apply column auto-sizing, header freeze rows, table formatting, and conditional fill colors (green for Running, amber for Stopped, red for Failed).

---

## 3. TECHNICAL GUIDANCE

### Azure CLI Authentication and Subscription Setup

```bash
# Service principal login (preferred for agent execution)
az login --service-principal \
  --username $AZURE_CLIENT_ID \
  --password $AZURE_CLIENT_SECRET \
  --tenant $AZURE_TENANT_ID

# Set active subscription
az account set --subscription "$AZURE_SUBSCRIPTION_ID"

# Confirm active subscription
az account show --output json | jq '{name: .name, id: .id, state: .state}'
```

### Resource Group Enumeration

```bash
az group list \
  --output json \
  --query "[].{Name:name, Location:location, ProvisioningState:properties.provisioningState, Tags:tags}" \
  > resource_groups.json
```

### All Resources Enumeration (Subscription Scope)

```bash
az resource list \
  --output json \
  --query "[].{Name:name, Type:type, ResourceGroup:resourceGroup, Location:location, \
               Kind:kind, ProvisioningState:properties.provisioningState, \
               SubscriptionId:subscriptionId, ID:id}" \
  > all_resources.json
```

### VM Power State Enrichment (Python)

```python
import subprocess, json

def get_vm_power_state(vm_id: str) -> str:
    result = subprocess.run(
        ["az", "vm", "get-instance-view", "--ids", vm_id,
         "--query", "instanceView.statuses[1].displayStatus",
         "--output", "tsv"],
        capture_output=True, text=True
    )
    return result.stdout.strip() if result.returncode == 0 else "Unknown"
```

### Cost Management API Call (Python with requests)

```python
import requests, os

def get_subscription_costs(subscription_id: str, access_token: str) -> dict:
    url = (
        f"https://management.azure.com/subscriptions/{subscription_id}/"
        f"providers/Microsoft.CostManagement/query?api-version=2023-11-01"
    )
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    
    # Month-to-date cost grouped by resource group and resource type
    payload = {
        "type": "ActualCost",
        "timeframe": "MonthToDate",
        "dataset": {
            "granularity": "None",
            "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}},
            "grouping": [
                {"type": "Dimension", "name": "ResourceGroupName"},
                {"type": "Dimension", "name": "ResourceType"}
            ]
        }
    }
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()


def get_total_subscription_cost(subscription_id: str, access_token: str) -> float:
    url = (
        f"https://management.azure.com/subscriptions/{subscription_id}/"
        f"providers/Microsoft.CostManagement/query?api-version=2023-11-01"
    )
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    payload = {
        "type": "ActualCost",
        "timeframe": "MonthToDate",
        "dataset": {
            "granularity": "None",
            "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}}
        }
    }
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    rows = response.json().get("properties", {}).get("rows", [])
    return float(rows[0][0]) if rows else 0.0
```

### Excel Workbook Generation (openpyxl)

```python
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment
from openpyxl.utils import get_column_letter
from datetime import datetime

STATUS_COLORS = {
    "Running":            "C6EFCE",  # green
    "Stopped/Deallocated":"FFEB9C",  # amber
    "Failed":             "FFC7CE",  # red
    "Creating":           "BDD7EE",  # blue
    "Updating":           "BDD7EE",
    "Unknown":            "D9D9D9",  # grey
}

def build_workbook(rg_data: list, resource_data: list, cost_data: list,
                   subscription_name: str, subscription_id: str,
                   total_cost: float, currency: str) -> Workbook:
    wb = Workbook()

    # ── Sheet 1: Summary ──────────────────────────────────────────────
    ws_summary = wb.active
    ws_summary.title = "Summary"
    summary_rows = [
        ["Subscription Name", subscription_name],
        ["Subscription ID",   subscription_id],
        ["Report Timestamp",  datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")],
        ["Total Resource Groups", len(rg_data)],
        ["Total Resources",   len(resource_data)],
        ["Total MTD Cost",    f"{total_cost:.2f} {currency}"],
    ]
    for row in summary_rows:
        ws_summary.append(row)
    for cell in ws_summary["A"]:
        cell.font = Font(bold=True)

    # ── Sheet 2: Resource Groups ───────────────────────────────────────
    ws_rg = wb.create_sheet("Resource Groups")
    rg_headers = ["Name", "Location", "Provisioning State", "Tags"]
    ws_rg.append(rg_headers)
    for cell in ws_rg[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="4472C4")
        cell.font = Font(bold=True, color="FFFFFF")
    for rg in rg_data:
        ws_rg.append([
            rg.get("Name"), rg.get("Location"),
            rg.get("ProvisioningState"),
            str(rg.get("Tags") or {})
        ])

    # ── Sheet 3: All Resources ─────────────────────────────────────────
    ws_res = wb.create_sheet("All Resources")
    res_headers = [
        "Name", "Type", "Resource Group", "Location",
        "Provisioning State", "Power State", "Operational Status",
        "Kind", "SKU", "Tags", "Resource ID", "MTD Cost (USD)"
    ]
    ws_res.append(res_headers)
    for cell in ws_res[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="4472C4")
    ws_res.freeze_panes = "A2"

    for res in resource_data:
        op_status = res.get("OperationalStatus", "Unknown")
        fill_color = STATUS_COLORS.get(op_status, "FFFFFF")
        row_data = [
            res.get("Name"), res.get("Type"), res.get("ResourceGroup"),
            res.get("Location"), res.get("ProvisioningState"),
            res.get("PowerState", "N/A"), op_status,
            res.get("Kind", ""), res.get("SKU", ""),
            str(res.get("Tags") or {}), res.get("ID"),
            res.get("MTDCost", 0.0)
        ]
        ws_res.append(row_data)
        for cell in ws_res[ws_res.max_row]:
            cell.fill = PatternFill("solid", fgColor=fill_color)

    # Auto-size columns for All Resources sheet
    for col_idx, col in enumerate(ws_res.columns, 1):
        max_len = max((len(str(cell.value or "")) for cell in col), default=10)
        ws_res.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 2, 60)

    # ── Sheet 4: Cost Breakdown ────────────────────────────────────────
    ws_cost = wb.create_sheet("Cost Breakdown")
    cost_headers = ["Resource Group", "Resource Type", "MTD Cost", "Currency"]
    ws_cost.append(cost_headers)
    for cell in ws_cost[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="4472C4")
    for row in cost_data:
        ws_cost.append(row)

    return wb
```

### Operational Status Classification Logic

```python
def classify_operational_status(provisioning_state: str, power_state: str,
                                 resource_type: str) -> str:
    ps = (provisioning_state or "").strip().lower()
    pw = (power_state or "").strip().lower()

    if ps == "failed":
        return "Failed"
    if ps in ("creating", "updating"):
        return ps.capitalize()
    if "deallocated" in pw or "stopped" in pw:
        return "Stopped/Deallocated"
    if "running" in pw:
        return "Running"
    if ps == "succeeded":
        # Non-compute resources with no power state — treat as Running
        compute_types = ["microsoft.compute/virtualmachines",
                         "microsoft.web/sites", "microsoft.containerservice/managedclusters"]
        if not any(rt in resource_type.lower() for rt in compute_types):
            return "Running"
        return "Unknown"
    return "Unknown"
```

---

## 4. DECISION LOGIC

**Authentication State**
- `IF` `az account show` returns a valid subscription name and ID with `state: Enabled` → proceed to resource enumeration
- `IF` the subscription state is `Disabled` or `Warned` → halt execution, surface error: *"Subscription {ID} is not in Enabled state. Cost and resource data may be incomplete."*
- `IF` the service principal lacks `Reader` role at subscription scope → the `az resource list` call will return an empty array or 403 error → abort with message: *"Insufficient permissions. Assign Reader role on subscription {ID} to the executing principal."*

**Resource Group Count Validation**
- `IF` `az group list` returns 0 resource groups → confirm the subscription ID is correct and the principal has subscription-level Reader access; do not proceed to resource enumeration with a zero count unless explicitly confirmed by user
- `IF` resource group count > 500 → warn the user that pagination is active and the agent must iterate using `--next-link` tokens from the ARM REST API directly, as `az group list` handles pagination automatically but very large responses may require increased timeout values

**Cost Data Availability**
- `IF` Cost Management API returns HTTP 404 or `BillingAccountNotFound` → the subscription may be a free trial or CSP subscription without direct Cost Management access; set all cost values to `"N/A (Cost Management unavailable)"` and continue Excel generation — do not halt
- `IF` Cost Management API returns HTTP 429 → implement exponential backoff: wait 30 seconds, retry up to 3 times before marking cost as `"N/A (Rate limited)"`
- `IF` `MonthToDate` cost returns `$0.00` and the subscription has known running resources → flag this as suspicious in the Summary sheet note; it may indicate a billing cycle reset or new subscription

**Compute Power State Enrichment**
- `IF` resource type is `Microsoft.Compute/virtualMachines` → always call `az vm get-instance-view` to fetch power state; never rely solely on `provisioningState`
- `IF` resource type is `Microsoft.Web/sites` → call `az webapp show` for `state` field
- `IF` resource type is `Microsoft.ContainerService/managedClusters` → call `az aks show` for `powerState.code`
- `IF` resource type is none of the above → set `PowerState` to `"N/A"` and derive `OperationalStatus` from `provisioningState` alone
- `IF` the per-resource API call for power state fails (network error, throttling) → set `PowerState` to `"Fetch Error"` and `OperationalStatus` to `"Unknown"` — do not halt the entire run

**Excel File Naming**
- `IF` a custom output path is provided by the user → write the file to that path
- `IF` no output path is provided → default to `azure_inventory_{SUBSCRIPTION_ID}_{YYYYMMDD_HHMMSS}.xlsx` in the current working directory

---

## 5. DECISION GATE

> **DECISION GATE — Phase Complete (Final)**
>
> ALL must be true before marking this skill execution complete:
>
> - [ ] Active Azure subscription context confirmed via `az account show` — subscription name, ID, and `state: Enabled` are captured and recorded in the Summary sheet
> - [ ] Resource group enumeration completed with at least 1 resource group returned, or user has confirmed the subscription intentionally has zero resource groups
> - [ ] `az resource list` has returned a complete resource array (not truncated); total resource count recorded in Summary sheet matches the row count in the `All Resources` Excel sheet (excluding header row)
> - [ ] Every `Microsoft.Compute/virtualMachines` resource in the inventory has a `PowerState` value that is not empty — either a real status string, `"N/A"`, or `"Fetch Error"` (but not blank)
> - [ ] Cost Management API has been called; either a numeric cost value or an explicit `"N/A"` explanation string is present in the Summary sheet `Total MTD Cost` row — the field is never blank
> - [ ] The Excel workbook file exists on disk at the declared output path, contains exactly 4 sheets (`Summary`, `Resource Groups`, `All Resources`, `Cost Breakdown`), and the file size is greater than 0 bytes
> - [ ] The `All Resources` sheet contains conditional fill color formatting — at minimum one row with green, amber, or red fill (or all grey/blue if all resources are in identical states)
> - [ ] No unhandled Python exceptions occurred during execution; all errors were caught, logged, and surfaced as warning annotations in the workbook or console output
>
> **If not met — exact remediation steps:**
>
> - **Subscription not Enabled:** Run `az account list --output table` to identify available subscriptions; re-run `az account set` with the correct subscription ID.
> - **Zero resource groups with unexpected result:** Verify the service principal has `Reader` role via `az role assignment list --assignee $AZURE_CLIENT_ID --scope /subscriptions/$AZURE_SUBSCRIPTION_ID`.
> - **Resource count mismatch between API and Excel:** Re-run `az resource list` with explicit `--subscription` flag; check for pagination issues by verifying response array length versus `az resource list | jq length`.
> - **VM power state blank:** Confirm `Microsoft.Compute` resource provider is registered: `az provider show --namespace Microsoft.Compute --query registrationState`. Re-trigger per-VM enrichment loop for VMs with missing power state.
> - **Cost field blank:** Check Cost Management registration: `az provider show --namespace Microsoft.CostManagement --query registrationState`. If unregistered, run `az provider register --namespace Microsoft.CostManagement` and retry after 2-3 minutes.
> - **Excel file missing or 0 bytes:** Check Python environment has `openpyxl` installed (`pip install openpyxl`); verify write permissions on the target output directory.

---

## 6. OUTPUTS

| Deliverable | Format | Location | Description |
|---|---|---|---|
| **Azure Inventory Workbook** | `.xlsx` | `./azure_inventory_{SUBSCRIPTION_ID}_{TIMESTAMP}.xlsx` | Primary deliverable — 4-sheet Excel workbook with full resource inventory and cost data |
| **Summary Sheet** | Excel sheet within workbook | Sheet 1: `Summary` | Subscription name, ID, execution timestamp, total resource group count, total resource count, total MTD cost |
| **Resource Groups Sheet** | Excel sheet within workbook | Sheet 2: `Resource Groups` | One row per resource group: name, location, provisioning state, tags |
| **All Resources Sheet** | Excel sheet within workbook | Sheet 3: `All Resources` | One row per resource: name, type, resource group, location, provisioning state, power state, operational status, kind, SKU, tags, resource ID, MTD cost; color-coded by status |
| **Cost Breakdown Sheet** | Excel sheet within workbook | Sheet 4: `Cost Breakdown` | Cost rows from Cost Management API grouped by resource group and resource type with currency |
| **Execution Log** | Console stdout / stderr | Terminal output | Real-time progress messages including resource group count found, resource count found, cost API call status, and output file path confirmation |

---

## 7. ANTI-PATTERNS

**Anti-Pattern 1: Relying on `provisioningState: Succeeded` to Mean "Running"**
Using `provisioningState` as the sole indicator of a resource's operational health is a critical error. A VM with `provisioningState: Succeeded` can be in a `VM deallocated` power state — it was successfully provisioned but has since been stopped. This causes stopped VMs to be reported as running in the inventory, defeating the purpose of identifying resources that are "down." The consequence is that operations teams act on false data, potentially missing idle deallocated VMs that still incur managed disk storage costs. Always call the instance-view endpoint for compute resources.

**Anti-Pattern 2: Iterating Per-Resource-Group Instead of Querying at Subscription Scope**
Calling `az resource list --resource-group <NAME>` in a loop for each resource group introduces N sequential API calls (where N = number of resource groups), dramatically increasing execution time and Azure ARM API throttling risk. In subscriptions with 50+ resource groups, this pattern will hit the ARM read throttle limit (12,000 requests per hour per subscription) and produce incomplete results with silent failures on throttled calls. Always use `az resource list` at subscription scope to retrieve all resources in one call and filter client-side.

**Anti-Pattern 3: Omitting Resources in Non-Succeeded Provisioning States from the Excel Output**
Filtering the resource list to only include `provisioningState: Succeeded` resources before writing to Excel means resources in `Failed`, `Creating`, `Updating`, or `Deleting` states are completely invisible in the output. This is the most dangerous anti-pattern for governance use cases: a resource that failed to deploy and is stuck in `Failed` state may still be holding allocated storage, reserved IPs, or network security group rules — and still incurs cost. The Excel output must contain every resource returned by the API with its exact provisioning state, visually differentiated by row color.

---

## 8. AGENT INSTRUCTIONS

1. **Confirm prerequisites.** Verify that the following tools are available in the execution environment: `az` (Azure CLI, version ≥ 2.50.0), `python3` (version ≥ 3.9), and the `openpyxl` and `requests` Python packages. If any are missing, install them before proceeding (`pip install openpyxl requests`).

2. **Read required environment variables.** Load `AZURE_SUBSCRIPTION_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, and `AZURE_CLIENT_SECRET` from the environment or prompt the user to provide them. If `AZURE_SUBSCRIPTION_ID` is not set, call `az account list --output json` and prompt the user to select from available subscriptions.

3. **Authenticate to Azure.** Execute the service principal login command. If it fails, fall back to `az login` for interactive authentication. After login, explicitly set the subscription context and call `az account show` to confirm. Store the subscription name, ID, and tenant ID in variables for use in output file naming and Excel content.

4. **Enumerate all resource groups.** Run `az group list --output json` and parse the JSON response into a Python list of dicts. Log the total count of resource groups to the console (e.g., `[INFO] Found 14 resource groups`). If the count is 0, warn the user and pause for confirmation before continuing.

5. **Enumerate all resources at subscription scope.** Run `az resource list --output json` and parse the response. Log the total resource count. Build a dictionary keyed by resource ID for fast lookup during enrichment steps.

6. **Enrich compute resources with power state.** Iterate over all resources. For each `Microsoft.Compute/virtualMachines` resource, call `az vm get-instance-view --ids <ID>` to get the power state. For each `Microsoft.Web/sites` resource, call `az webapp show --ids <ID>`. For each `Microsoft.ContainerService/managedClusters` resource, call `az aks show --ids <ID>`. Implement a per-call try/except block — on failure, set `PowerState = "Fetch Error"` and continue. Log each successful enrichment with resource name and retrieved state.

7. **Retrieve an access token for the Cost Management REST API.** Execute `az account get-access-token --output json` and extract the `accessToken` field. This token is valid for 60 minutes — if the enrichment step takes longer, refresh the token before calling Cost Management.

8. **Call the Cost Management API for total MTD cost.** Issue the POST request to the Cost Management query endpoint with `timeframe: MonthToDate` and no grouping to get the subscription total. Then issue a second call grouped by `ResourceGroupName` and `ResourceType` for the Cost Breakdown sheet. Handle 404 (no billing access), 429 (throttle), and 5xx errors explicitly per the decision logic in Section 4.

9. **Classify operational status for every resource.** Apply the `classify_operational_status` function from Section 3 to every resource record, passing `provisioningState`, `power_state`, and `resource_type`. Store the result as the `OperationalStatus` field on each resource dict.

10. **Match cost data to resources.** Build a lookup dict from the Cost Management grouped response keyed by `(ResourceGroupName.lower(), ResourceType.lower())`. For each resource record, look up its cost using this key and attach as `MTDCost`. Resources with no match receive `MTDCost = 0.0`.

11. **Build and write the Excel workbook.** Call the `build_workbook` function from Section 3 with all collected data. Save the workbook to `azure_inventory_{SUBSCRIPTION_ID}_{YYYYMMDD_HHMMSS}.xlsx`. Confirm the file exists and is non-zero in size using `os.path.getsize()`.

12. **Output final confirmation message.** Print a structured summary to the console: total resource groups, total resources, total MTD cost (with currency), count of Running vs. Stopped/Deallocated vs. Failed resources, and the absolute path to the output Excel file. This is the terminal success signal for the skill execution.