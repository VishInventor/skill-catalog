#!/usr/bin/env python3
"""
agent_1.py — onlinestore-microservice-azure
Agent Role: Builder of online store
Version: 1.0.0
Author: Vishal Anand

Deploys a production-grade online store microservice to Azure using:
  - Azure Container Apps Environment
  - Azure SQL Database
  - Full monitoring via Log Analytics

Phases:
  1. Pre-Provisioning Validation
  2. Container Apps Environment
  3. SQL Database Provisioning
  4. Microservice Deployment

USAGE:
  python agent_1.py --confirm [--resource-group RG] [--location LOC]

Required Environment Variables:
  AZURE_SUBSCRIPTION_ID
  AZURE_TENANT_ID
  AZURE_CLIENT_ID
  AZURE_CLIENT_SECRET
  SQL_ADMIN_PASSWORD   (min 12 chars, upper/lower/digit/special)
"""

import argparse
import logging
import os
import sys
import time
import json
import subprocess
import random
import string
from typing import Optional, Dict, Any

# ---------------------------------------------------------------------------
# Attempt to import Azure SDK libraries; guide user if missing
# ---------------------------------------------------------------------------
try:
    from azure.identity import ClientSecretCredential
    from azure.mgmt.resource import ResourceManagementClient
    from azure.mgmt.loganalytics import LogAnalyticsManagementClient
    from azure.mgmt.loganalytics.models import Workspace
    from azure.mgmt.containerinstance import ContainerInstanceManagementClient
    from azure.mgmt.sql import SqlManagementClient
    from azure.mgmt.sql.models import (
        Server,
        ServerExternalAdministrator,
        Database,
        FirewallRule,
        Sku as SqlSku,
    )
    from azure.mgmt.appcontainers import ContainerAppsAPIClient
    from azure.mgmt.appcontainers.models import (
        ManagedEnvironment,
        AppLogsConfiguration,
        LogAnalyticsConfiguration,
        ContainerApp,
        Configuration,
        Ingress,
        Template,
        Container,
        ContainerResources,
        EnvironmentVar,
        Scale,
        ScaleRule,
        HttpScaleRule,
    )
    from azure.core.exceptions import AzureError, HttpResponseError, ResourceNotFoundError
except ImportError as exc:
    print(
        f"[FATAL] Missing Azure SDK dependency: {exc}\n"
        "Install with:\n"
        "  pip install azure-identity azure-mgmt-resource azure-mgmt-loganalytics "
        "azure-mgmt-sql azure-mgmt-appcontainers azure-core\n"
    )
    sys.exit(2)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("onlinestore-microservice-azure")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_RESOURCE_GROUP = "onlinestore-rg"
DEFAULT_LOCATION = "eastus"
MICROSERVICE_REPO = (
    "https://github.com/Azure-Samples/container-apps-store-api-microservice"
)
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 10  # seconds

# Container images from the sample repo (published to MCR)
STORE_IMAGES = {
    "store-front": "mcr.microsoft.com/azuredocs/containerapps-storefront:latest",
    "order-service": "mcr.microsoft.com/azuredocs/containerapps-orderservice:latest",
    "product-service": "mcr.microsoft.com/azuredocs/containerapps-productservice:latest",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def rand_suffix(n: int = 6) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def retry(fn, label: str, max_attempts: int = MAX_RETRIES):
    """Retry a callable up to max_attempts times with exponential back-off."""
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except (AzureError, HttpResponseError, Exception) as exc:
            wait = RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
            if attempt < max_attempts:
                log.warning(
                    "[%s] Attempt %d/%d failed: %s — retrying in %ds",
                    label, attempt, max_attempts, exc, wait,
                )
                time.sleep(wait)
            else:
                log.error("[%s] All %d attempts failed: %s", label, max_attempts, exc)
                raise


def poll_lro(poller, label: str, timeout: int = 600):
    """Poll a Long-Running Operation with timeout."""
    log.info("[%s] Waiting for LRO to complete (timeout=%ds)…", label, timeout)
    result = poller.result(timeout=timeout)
    log.info("[%s] LRO completed successfully.", label)
    return result


def exit_fail(msg: str, code: int = 1):
    log.error(msg)
    sys.exit(code)


# ---------------------------------------------------------------------------
# Credential & Client Factory
# ---------------------------------------------------------------------------

def build_credential() -> ClientSecretCredential:
    tenant_id = os.environ.get("AZURE_TENANT_ID", "")
    client_id = os.environ.get("AZURE_CLIENT_ID", "")
    client_secret = os.environ.get("AZURE_CLIENT_SECRET", "")
    if not all([tenant_id, client_id, client_secret]):
        exit_fail(
            "AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET must all be set."
        )
    return ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
    )


def build_clients(credential, subscription_id: str) -> Dict[str, Any]:
    return {
        "resource": ResourceManagementClient(credential, subscription_id),
        "loganalytics": LogAnalyticsManagementClient(credential, subscription_id),
        "sql": SqlManagementClient(credential, subscription_id),
        "appcontainers": ContainerAppsAPIClient(credential, subscription_id),
    }


# ---------------------------------------------------------------------------
# Phase 1 — Pre-Provisioning Validation
# ---------------------------------------------------------------------------

def phase1_validate(subscription_id: str, sql_admin_password: str) -> None:
    log.info("=" * 60)
    log.info("PHASE 1 — Pre-Provisioning Validation")
    log.info("=" * 60)

    errors = []

    # Subscription ID
    if not subscription_id:
        errors.append("AZURE_SUBSCRIPTION_ID is not set.")

    # SQL password complexity
    if len(sql_admin_password) < 12:
        errors.append("SQL_ADMIN_PASSWORD must be at least 12 characters.")
    if not any(c.isupper() for c in sql_admin_password):
        errors.append("SQL_ADMIN_PASSWORD must contain an uppercase letter.")
    if not any(c.islower() for c in sql_admin_password):
        errors.append("SQL_ADMIN_PASSWORD must contain a lowercase letter.")
    if not any(c.isdigit() for c in sql_admin_password):
        errors.append("SQL_ADMIN_PASSWORD must contain a digit.")
    specials = set("!@#$%^&*()-_=+[]{}|;:,.<>?")
    if not any(c in specials for c in sql_admin_password):
        errors.append("SQL_ADMIN_PASSWORD must contain a special character.")

    # Check Azure CLI availability (optional, used for env operations)
    try:
        subprocess.run(
            ["az", "--version"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        log.info("[Phase 1] Azure CLI detected.")
    except (FileNotFoundError, subprocess.CalledProcessError):
        log.warning(
            "[Phase 1] Azure CLI not found — SDK-only mode will be used for all operations."
        )

    if errors:
        for e in errors:
            log.error("[Phase 1] Validation error: %s", e)
        exit_fail("[Phase 1] Pre-provisioning validation FAILED.")

    log.info("[Phase 1] All validations passed. ✓")


# ---------------------------------------------------------------------------
# Phase 2 — Container Apps Environment
# ---------------------------------------------------------------------------

def phase2_container_env(
    clients: Dict[str, Any],
    resource_group: str,
    location: str,
    suffix: str,
) -> Dict[str, str]:
    """
    Creates:
      - Resource Group
      - Log Analytics Workspace
      - Container Apps Managed Environment
    Returns names/IDs for downstream phases.
    """
    log.info("=" * 60)
    log.info("PHASE 2 — Container Apps Environment")
    log.info("=" * 60)

    rc: ResourceManagementClient = clients["resource"]
    lac: LogAnalyticsManagementClient = clients["loganalytics"]
    cac: ContainerAppsAPIClient = clients["appcontainers"]

    # 2a. Resource Group
    rg_name = resource_group
    log.info("[Phase 2] Creating resource group '%s' in '%s'…", rg_name, location)

    def _create_rg():
        return rc.resource_groups.create_or_update(
            rg_name, {"location": location, "tags": {"project": "onlinestore", "managed-by": "agent_1"}}
        )

    retry(_create_rg, "create-resource-group")
    log.info("[Phase 2] Resource group '%s' ready. ✓", rg_name)

    # 2b. Log Analytics Workspace
    workspace_name = f"onlinestore-logs-{suffix}"
    log.info("[Phase 2] Creating Log Analytics Workspace '%s'…", workspace_name)

    def _create_workspace():
        poller = lac.workspaces.begin_create_or_update(
            rg_name,
            workspace_name,
            Workspace(
                location=location,
                sku={"name": "PerGB2018"},
                retention_in_days=30,
                tags={"project": "onlinestore"},
            ),
        )
        return poll_lro(poller, "create-log-analytics-workspace")

    workspace = retry(_create_workspace, "create-log-analytics-workspace")
    workspace_id = workspace.customer_id

    # Retrieve shared keys
    def _get_ws_keys():
        return lac.workspaces.get_shared_keys(rg_name, workspace_name)

    ws_keys = retry(_get_ws_keys, "get-workspace-shared-keys")
    workspace_key = ws_keys.primary_shared_key
    log.info("[Phase 2] Log Analytics Workspace '%s' ready (id=%s). ✓", workspace_name, workspace_id)

    # 2c. Container Apps Managed Environment
    env_name = f"onlinestore-env-{suffix}"
    log.info("[Phase 2] Creating Container Apps Managed Environment '%s'…", env_name)

    def _create_env():
        poller = cac.managed_environments.begin_create_or_update(
            rg_name,
            env_name,
            ManagedEnvironment(
                location=location,
                tags={"project": "onlinestore"},
                app_logs_configuration=AppLogsConfiguration(
                    destination="log-analytics",
                    log_analytics_configuration=LogAnalyticsConfiguration(
                        customer_id=workspace_id,
                        shared_key=workspace_key,
                    ),
                ),
            ),
        )
        return poll_lro(poller, "create-container-apps-env", timeout=900)

    env = retry(_create_env, "create-container-apps-env")
    env_id = env.id
    log.info("[Phase 2] Container Apps Environment '%s' ready (id=%s). ✓", env_name, env_id)

    return {
        "resource_group": rg_name,
        "location": location,
        "suffix": suffix,
        "workspace_name": workspace_name,
        "workspace_id": workspace_id,
        "env_name": env_name,
        "env_id": env_id,
    }


# ---------------------------------------------------------------------------
# Phase 3 — SQL Database Provisioning
# ---------------------------------------------------------------------------

def phase3_sql(
    clients: Dict[str, Any],
    ctx: Dict[str, str],
    sql_admin_user: str,
    sql_admin_password: str,
) -> Dict[str, str]:
    log.info("=" * 60)
    log.info("PHASE 3 — SQL Database Provisioning")
    log.info("=" * 60)

    sql_client: SqlManagementClient = clients["sql"]
    rg_name = ctx["resource_group"]
    location = ctx["location"]
    suffix = ctx["suffix"]

    server_name = f"onlinestore-sql-{suffix}"
    db_name = "onlinestore-db"

    # 3a. SQL Server
    log.info("[Phase 3] Creating SQL Server '%s'…", server_name)

    def _create_server():
        poller = sql_client.servers.begin_create_or_update(
            rg_name,
            server_name,
            Server(
                location=location,
                administrator_login=sql_admin_user,
                administrator_login_password=sql_admin_password,
                version="12.0",
                tags={"project": "onlinestore"},
            ),
        )
        return poll_lro(poller, "create-sql-server", timeout=600)

    server = retry(_create_server, "create-sql-server")
    server_fqdn = server.fully_qualified_domain_name
    log.info("[Phase 3] SQL Server '%s' ready (fqdn=%s). ✓", server_name, server_fqdn)

    # 3b. Firewall rule — allow Azure services
    log.info("[Phase 3] Creating firewall rule: AllowAllAzureIPs…")

    def _create_fw_rule():
        return sql_client.firewall_rules.create_or_update(
            rg_name,
            server_name,
            "AllowAllAzureIPs",
            FirewallRule(start_ip_address="0.0.0.0", end_ip_address="0.0.0.0"),
        )

    retry(_create_fw_rule, "create-sql-firewall-rule")
    log.info("[Phase 3] Firewall rule applied. ✓")

    # 3c. Database
    log.info("[Phase 3] Creating SQL Database '%s'…", db_name)

    def _create_db():
        poller = sql_client.databases.begin_create_or_update(
            rg_name,
            server_name,
            db_name,
            Database(
                location=location,
                sku=SqlSku(name="S1", tier="Standard"),
                tags={"project": "onlinestore"},
            ),
        )
        return poll_lro(poller, "create-sql-database", timeout=600)

    db = retry(_create_db, "create-sql-database")
    log.info("[Phase 3] SQL Database '%s' ready (status=%s). ✓", db_name, db.status)

    connection_string = (
        f"Server=tcp:{server_fqdn},1433;"
        f"Initial Catalog={db_name};"
        f"Persist Security Info=False;"
        f"User ID={sql_admin_user};"
        f"Password={sql_admin_password};"
        "MultipleActiveResultSets=False;"
        "Encrypt=True;"
        "TrustServerCertificate=False;"
        "Connection Timeout=30;"
    )

    ctx.update(
        {
            "sql_server_name": server_name,
            "sql_server_fqdn": server_fqdn,
            "sql_db_name": db_name,
            "sql_connection_string": connection_string,
            "sql_admin_user": sql_admin_user,
        }
    )
    return ctx


# ---------------------------------------------------------------------------
# Phase 4 — Microservice Deployment
# ---------------------------------------------------------------------------

def _deploy_container_app(
    cac: ContainerAppsAPIClient,
    rg_name: str,
    location: str,
    env_id: str,
    app_name: str,
    image: str,
    env_vars: list,
    external_ingress: bool,
    target_port: int,
    cpu: float = 0.5,
    memory: str = "1Gi",
    min_replicas: int = 1,
    max_replicas: int = 5,
) -> str:
    """Deploy a single Container App and return its FQDN."""

    log.info("[Phase 4] Deploying Container App '%s' (image=%s)…", app_name, image)

    ingress_cfg = Ingress(
        external=external_ingress,
        target_port=target_port,
        transport="http",
    ) if target_port else None

    def _deploy():
        poller = cac.container_apps.begin_create_or_update(
            rg_name,
            app_name,
            ContainerApp(
                location=location,
                managed_environment_id=env_id,
                tags={"project": "onlinestore", "source": "agent_1"},
                configuration=Configuration(
                    ingress=ingress_cfg,
                    active_revisions_mode="Single",
                ),
                template=Template(
                    containers=[
                        Container(
                            name=app_name,
                            image=image,
                            resources=ContainerResources(cpu=cpu, memory=memory),
                            env=env_vars,
                        )
                    ],
                    scale=Scale(
                        min_replicas=min_replicas,
                        max_replicas=max_replicas,
                        rules=[
                            ScaleRule(
                                name="http-scale",
                                http=HttpScaleRule(metadata={"concurrentRequests": "50"}),
                            )
                        ],
                    ),
                ),
            ),
        )
        return poll_lro(poller, f"deploy-{app_name}", timeout=600)

    app = retry(_deploy, f"deploy-{app_name}")
    fqdn = ""
    if app.configuration and app.configuration.ingress:
        fqdn = app.configuration.ingress.fqdn or ""
    log.info("[Phase 4] Container App '%s' deployed. FQDN=%s ✓", app_name, fqdn or "internal")
    return fqdn


def phase4_deploy(
    clients: Dict[str, Any],
    ctx: Dict[str, str],
) -> None:
    log.info("=" * 60)
    log.info("PHASE 4 — Microservice Deployment")
    log.info("=" * 60)
    log.info("[Phase 4] Source: %s", MICROSERVICE_REPO)

    cac: ContainerAppsAPIClient = clients["appcontainers"]
    rg_name = ctx["resource_group"]
    location = ctx["location"]
    env_id = ctx["env_id"]
    suffix = ctx["suffix"]
    conn_str = ctx["sql_connection_string"]

    # Common env vars for all services
    common_env = [
        EnvironmentVar(name="AZURE_SQL_CONNECTIONSTRING", value=conn_str),
        EnvironmentVar(name="ASPNETCORE_ENVIRONMENT", value="Production"),
    ]

    # --- Product Service (internal) ---
    product_fqdn = _deploy_container_app(
        cac=cac,
        rg_name=rg_name,
        location=location,
        env_id=env_id,
        app_name=f"product-service-{suffix}",
        image=STORE_IMAGES["product-service"],
        env_vars=common_env + [
            EnvironmentVar(name="SERVICE_NAME", value="product-service"),
        ],
        external_ingress=False,
        target_port=3002,
        cpu=0.5,
        memory="1Gi",
        min_replicas=1,
        max_replicas=5,
    )

    # --- Order Service (internal) ---
    order_fqdn = _deploy_container_app(
        cac=cac,
        rg_name=rg_name,
        location=location,
        env_id=env_id,
        app_name=f"order-service-{suffix}",
        image=STORE_IMAGES["order-service"],
        env_vars=common_env + [
            EnvironmentVar(name="SERVICE_NAME", value="order-service"),
            EnvironmentVar(name="PRODUCT_SERVICE_URL", value=f"https://{product_fqdn}" if product_fqdn else "http://product-service"),
        ],
        external_ingress=False,
        target_port=3003,
        cpu=0.5,
        memory="1Gi",
        min_replicas=1,
        max_replicas=5,
    )

    # --- Store Front (external / public) ---
    store_fqdn = _deploy_container_app(
        cac=cac,
        rg_name=rg_name,
        location=location,
        env_id=env_id,
        app_name=f"store-front-{suffix}",
        image=STORE_IMAGES["store-front"],
        env_vars=common_env + [
            EnvironmentVar(name="SERVICE_NAME", value="store-front"),
            EnvironmentVar(name="ORDER_SERVICE_URL", value=f"https://{order_fqdn}" if order_fqdn else "http://order-service"),
            EnvironmentVar(name="PRODUCT_SERVICE_URL", value=f"https://{product_fqdn}" if product_fqdn else "http://product-service"),
        ],
        external_ingress=True,
        target_port=8080,
        cpu=0.75,
        memory="1.5Gi",
        min_replicas=1,
        max_replicas=10,
    )

    log.info("=" * 60)
    log.info("DEPLOYMENT COMPLETE")
    log.info("  Resource Group : %s", rg_name)
    log.info("  Environment    : %s", ctx["env_name"])
    log.info("  SQL Server     : %s", ctx["sql_server_fqdn"])
    log.info("  SQL Database   : %s", ctx["sql_db_name"])
    log.info("  Store Front URL: https://%s", store_fqdn)
    log.info("  Source Repo    : %s", MICROSERVICE_REPO)
    log.info("=" * 60)


# ---------------------------------------------------------------------------
# Rollback (best-effort)
# ---------------------------------------------------------------------------

def rollback(clients: Dict[str, Any], resource_group: str) -> None:
    log.warning("[ROLLBACK] Attempting to delete resource group '%s'…", resource_group)
    rc: ResourceManagementClient = clients["resource"]
    try:
        poller = rc.resource_groups.begin_delete(resource_group)
        poll_lro(poller, "rollback-delete-rg", timeout=900)
        log.warning("[ROLLBACK] Resource group '%s' deleted.", resource_group)
    except Exception as exc:
        log.error("[ROLLBACK] Failed to delete resource group '%s': %s", resource_group, exc)
        log.error(
            "[ROLLBACK] Manual cleanup required: az group delete --name %s --yes",
            resource_group,
        )


# ---------------------------------------------------------------------------
# Argument Parsing
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "onlinestore-microservice-azure agent_1.py\n"
            "Deploys a production-grade online store microservice to Azure.\n\n"
            "Keywords: deploy, build, install"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        required=True,
        help=(
            "REQUIRED. Confirms that this script will make REAL changes to Azure "
            "infrastructure. Pass this flag explicitly to proceed."
        ),
    )
    parser.add_argument(
        "--resource-group",
        default=DEFAULT_RESOURCE_GROUP,
        help=f"Azure resource group name (default: {DEFAULT_RESOURCE_GROUP})",
    )
    parser.add_argument(
        "--location",
        default=DEFAULT_LOCATION,
        help=f"Azure region (default: {DEFAULT_LOCATION})",
    )
    parser.add_argument(
        "--suffix",
        default=None,
        help="Random suffix for unique resource names (auto-generated if not provided)",
    )
    parser.add_argument(
        "--sql-admin-user",
        default="onlinestoreAdmin",
        help="SQL Server administrator username (default: onlinestoreAdmin)",
    )
    parser.add_argument(
        "--skip-rollback-on-failure",
        action="store_true",
        help="Do not attempt resource group rollback on failure",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    if not args.confirm:
        # argparse required=True handles this, but belt-and-suspenders
        exit_fail(
            "ERROR: --confirm flag is required. This script makes REAL infrastructure changes.",
            code=2,
        )

    log.info("onlinestore-microservice-azure v1.0.0 — Agent: Builder of online store")
    log.info("Trigger keywords: deploy, build, install")
    log.info("Destructive mode: YES")

    # Environment variables
    subscription_id = os.environ.get("AZURE_SUBSCRIPTION_ID", "")
    sql_admin_password = os.environ.get("SQL_ADMIN_PASSWORD", "")

    if not sql_admin_password:
        exit_fail("SQL_ADMIN_PASSWORD environment variable must be set.", code=2)

    suffix = args.suffix or rand_suffix(6)
    log.info("Deployment suffix: %s", suffix)

    # Phase 1 — validate
    def _p1():
        phase1_validate(subscription_id, sql_admin_password)

    try:
        retry(_p1, "phase1-validate")
    except Exception as exc:
        exit_fail(f"[Phase 1] GATE FAILED: {exc}", code=1)

    # Build credential and clients
    credential = build_credential()
    clients = build_clients(credential, subscription_id)

    ctx: Dict[str, str] = {}

    # Phase 2 — Container Apps Environment
    def _p2():
        return phase2_container_env(
            clients=clients,
            resource_group=args.resource_group,
            location=args.location,
            suffix=suffix,
        )

    try:
        ctx = retry(_p2, "phase2-container-env")
    except Exception as exc:
        if not args.skip_rollback_on_failure:
            rollback(clients, args.resource_group)
        exit_fail(f"[Phase 2] GATE FAILED: {exc}", code=1)

    # Phase 3 — SQL Database
    def _p3():
        return phase3_sql(
            clients=clients,
            ctx=ctx,
            sql_admin_user=args.sql_admin_user,
            sql_admin_password=sql_admin_password,
        )

    try:
        ctx = retry(_p3, "phase3-sql")
    except Exception as exc:
        if not args.skip_rollback_on_failure:
            rollback(clients, args.resource_group)
        exit_fail(f"[Phase 3] GATE FAILED: {exc}", code=1)

    # Phase 4 — Microservice Deployment
    def _p4():
        phase4_deploy(clients=clients, ctx=ctx)

    try:
        retry(_p4, "phase4-deploy")
    except Exception as exc:
        if not args.skip_rollback_on_failure:
            rollback(clients, args.resource_group)
        exit_fail(f"[Phase 4] GATE FAILED: {exc}", code=1)

    log.info("All 4 phases completed successfully. Online store microservice is live. ✓")
    sys.exit(0)


if __name__ == "__main__":
    main()