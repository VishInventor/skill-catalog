#!/usr/bin/env python3
"""
agent_1.py — Databricks Full Discovery Agent
Skill: databricks-full-discovery v1.0.0
Author: Vishal Anand
Role: Discovery expert on Databricks
Trigger: discovery, scan

Phases:
  Phase 1: Pre-discovery  — connectivity checks to workspaces & catalogs
  Phase 2: Discover       — enumerate all Databricks environment assets
  Phase 3: Ontology       — generate Palantir-style draw.io ontology diagram
"""

import argparse
import json
import logging
import os
import sys
import time
import traceback
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from xml.dom import minidom

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("databricks-full-discovery")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # seconds
API_TIMEOUT = 30
DESKTOP = Path.home() / "Desktop"

# ---------------------------------------------------------------------------
# Credential helpers — environment variables ONLY
# ---------------------------------------------------------------------------

def get_env(var: str, required: bool = True) -> Optional[str]:
    val = os.environ.get(var)
    if required and not val:
        logger.error("Required environment variable %s is not set.", var)
        sys.exit(2)
    return val


def build_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# HTTP session with retry
# ---------------------------------------------------------------------------

def make_session(token: str) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=MAX_RETRIES,
        backoff_factor=RETRY_BACKOFF,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.headers.update(build_headers(token))
    return session


# ---------------------------------------------------------------------------
# Generic API caller
# ---------------------------------------------------------------------------

def api_get(session: requests.Session, url: str, params: dict = None) -> Any:
    resp = session.get(url, params=params, timeout=API_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def api_post(session: requests.Session, url: str, payload: dict = None) -> Any:
    resp = session.post(url, json=payload or {}, timeout=API_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Phase 1 — Pre-discovery: connectivity check
# ---------------------------------------------------------------------------

def phase1_connectivity(host: str, session: requests.Session) -> bool:
    logger.info("=== PHASE 1: Pre-discovery — Connectivity Check ===")
    attempt = 0
    while attempt < MAX_RETRIES:
        attempt += 1
        try:
            logger.info("Attempt %d/%d — pinging workspace %s", attempt, MAX_RETRIES, host)
            url = f"{host}/api/2.0/clusters/list"
            data = api_get(session, url)
            logger.info("Workspace reachable. Active clusters found: %d",
                        len(data.get("clusters", [])))

            # Check Unity Catalog connectivity
            uc_url = f"{host}/api/2.1/unity-catalog/catalogs"
            uc_data = api_get(session, uc_url)
            catalogs = uc_data.get("catalogs", [])
            logger.info("Unity Catalog reachable. Catalogs found: %d", len(catalogs))
            logger.info("GATE[Phase 1]: Connectivity — PASS")
            return True
        except requests.exceptions.RequestException as exc:
            logger.warning("Connectivity check failed (attempt %d): %s", attempt, exc)
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF ** attempt
                logger.info("Retrying in %d seconds …", wait)
                time.sleep(wait)

    logger.error("GATE[Phase 1]: Connectivity — FAIL after %d attempts. Aborting.", MAX_RETRIES)
    return False


# ---------------------------------------------------------------------------
# Phase 2 — Discover
# ---------------------------------------------------------------------------

def discover_workspaces(host: str, session: requests.Session) -> dict:
    logger.info("Discovering workspace identity …")
    try:
        data = api_get(session, f"{host}/api/2.0/workspace/get-status", {"path": "/"})
        return {"host": host, "root_path": data.get("path", "/"), "object_type": data.get("object_type")}
    except Exception as exc:
        logger.warning("Workspace identity partial: %s", exc)
        return {"host": host}


def discover_catalogs(host: str, session: requests.Session) -> list:
    logger.info("Discovering Unity Catalog catalogs …")
    try:
        data = api_get(session, f"{host}/api/2.1/unity-catalog/catalogs")
        catalogs = data.get("catalogs", [])
        result = []
        for cat in catalogs:
            name = cat.get("name")
            schemas = []
            try:
                sd = api_get(session, f"{host}/api/2.1/unity-catalog/schemas",
                             {"catalog_name": name})
                for schema in sd.get("schemas", []):
                    sname = schema.get("name")
                    tables = []
                    try:
                        td = api_get(session, f"{host}/api/2.1/unity-catalog/tables",
                                     {"catalog_name": name, "schema_name": sname})
                        tables = [{"name": t.get("name"), "table_type": t.get("table_type"),
                                   "data_source_format": t.get("data_source_format"),
                                   "storage_location": t.get("storage_location")}
                                  for t in td.get("tables", [])]
                    except Exception:
                        pass
                    schemas.append({"name": sname, "tables": tables})
            except Exception:
                pass
            result.append({"name": name, "comment": cat.get("comment"), "schemas": schemas})
        logger.info("Catalogs discovered: %d", len(result))
        return result
    except Exception as exc:
        logger.warning("Catalog discovery failed: %s", exc)
        return []


def discover_clusters(host: str, session: requests.Session) -> list:
    logger.info("Discovering running compute (clusters) …")
    try:
        data = api_get(session, f"{host}/api/2.0/clusters/list")
        clusters = data.get("clusters", [])
        result = [{"cluster_id": c.get("cluster_id"), "cluster_name": c.get("cluster_name"),
                   "state": c.get("state"), "spark_version": c.get("spark_version"),
                   "node_type_id": c.get("node_type_id"),
                   "num_workers": c.get("num_workers"),
                   "autoscale": c.get("autoscale"),
                   "creator": c.get("creator_user_name"),
                   "cluster_source": c.get("cluster_source")}
                  for c in clusters]
        logger.info("Clusters discovered: %d", len(result))
        return result
    except Exception as exc:
        logger.warning("Cluster discovery failed: %s", exc)
        return []


def discover_warehouses(host: str, session: requests.Session) -> list:
    logger.info("Discovering running SQL warehouses …")
    try:
        data = api_get(session, f"{host}/api/2.0/sql/warehouses")
        warehouses = data.get("warehouses", [])
        result = [{"id": w.get("id"), "name": w.get("name"), "state": w.get("state"),
                   "cluster_size": w.get("cluster_size"), "max_num_clusters": w.get("max_num_clusters"),
                   "warehouse_type": w.get("warehouse_type"),
                   "creator": w.get("creator_name")}
                  for w in warehouses]
        logger.info("Warehouses discovered: %d", len(result))
        return result
    except Exception as exc:
        logger.warning("Warehouse discovery failed: %s", exc)
        return []


def discover_jobs(host: str, session: requests.Session) -> dict:
    logger.info("Discovering data pipelines (jobs/workflows) …")
    try:
        data = api_get(session, f"{host}/api/2.1/jobs/list", {"expand_tasks": "true"})
        jobs = data.get("jobs", [])
        medallion = []
        ingestion = []
        for j in jobs:
            name = (j.get("settings", {}).get("name") or "").lower()
            entry = {"job_id": j.get("job_id"),
                     "name": j.get("settings", {}).get("name"),
                     "creator": j.get("creator_user_name"),
                     "run_as": j.get("run_as", {}),
                     "schedule": j.get("settings", {}).get("schedule"),
                     "task_count": len(j.get("settings", {}).get("tasks", []))}
            if any(kw in name for kw in ["bronze", "silver", "gold", "medallion", "lakehouse"]):
                medallion.append(entry)
            elif any(kw in name for kw in ["ingest", "load", "extract", "etl", "elt", "kafka", "dlt"]):
                ingestion.append(entry)
            else:
                ingestion.append(entry)  # classify all non-medallion as ingestion for completeness
        logger.info("Jobs discovered: %d (medallion: %d, ingestion: %d)",
                    len(jobs), len(medallion), len(ingestion))
        return {"medallion_pipelines": medallion, "ingestion_pipelines": ingestion, "total": len(jobs)}
    except Exception as exc:
        logger.warning("Jobs discovery failed: %s", exc)
        return {"medallion_pipelines": [], "ingestion_pipelines": [], "total": 0}


def discover_delta_live_tables(host: str, session: requests.Session) -> list:
    logger.info("Discovering Delta Live Tables (DLT) pipelines …")
    try:
        data = api_get(session, f"{host}/api/2.0/pipelines")
        pipelines = data.get("statuses", [])
        result = [{"pipeline_id": p.get("pipeline_id"), "name": p.get("name"),
                   "state": p.get("state"), "cluster_id": p.get("cluster_id"),
                   "creator": p.get("creator_user_name")}
                  for p in pipelines]
        logger.info("DLT pipelines discovered: %d", len(result))
        return result
    except Exception as exc:
        logger.warning("DLT discovery failed: %s", exc)
        return []


def discover_external_locations(host: str, session: requests.Session) -> list:
    logger.info("Discovering external data sources / external locations …")
    try:
        data = api_get(session, f"{host}/api/2.1/unity-catalog/external-locations")
        locs = data.get("external_locations", [])
        result = [{"name": l.get("name"), "url": l.get("url"),
                   "credential_name": l.get("credential_name"),
                   "comment": l.get("comment")}
                  for l in locs]
        logger.info("External locations discovered: %d", len(result))
        return result
    except Exception as exc:
        logger.warning("External locations discovery failed: %s", exc)
        return []


def discover_dashboards(host: str, session: requests.Session) -> list:
    logger.info("Discovering running dashboards …")
    try:
        data = api_get(session, f"{host}/api/2.0/preview/sql/dashboards")
        dashboards = data.get("results", []) or data if isinstance(data, list) else []
        result = [{"id": d.get("id"), "name": d.get("name"),
                   "slug": d.get("slug"),
                   "user": d.get("user", {}).get("name") if isinstance(d.get("user"), dict) else d.get("user"),
                   "created_at": d.get("created_at"),
                   "updated_at": d.get("updated_at")}
                  for d in dashboards]
        logger.info("Dashboards discovered: %d", len(result))
        return result
    except Exception as exc:
        logger.warning("Dashboard discovery failed: %s", exc)
        return []


def discover_ai_bi_agents(host: str, session: requests.Session) -> list:
    logger.info("Discovering AI-BI Genie agents …")
    agents = []
    try:
        data = api_get(session, f"{host}/api/2.0/genie/spaces")
        spaces = data.get("spaces", [])
        for s in spaces:
            agents.append({"id": s.get("space_id"), "name": s.get("title"),
                           "description": s.get("description"),
                           "created_by": s.get("created_by"),
                           "type": "AI-BI Genie"})
        logger.info("AI-BI Genie spaces discovered: %d", len(agents))
    except Exception as exc:
        logger.warning("AI-BI Genie discovery failed (may not be enabled): %s", exc)
    return agents


def phase2_discover(host: str, session: requests.Session) -> dict:
    logger.info("=== PHASE 2: Discover ===")
    attempt = 0
    while attempt < MAX_RETRIES:
        attempt += 1
        try:
            inventory = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "workspace": discover_workspaces(host, session),
                "catalogs": discover_catalogs(host, session),
                "clusters": discover_clusters(host, session),
                "warehouses": discover_warehouses(host, session),
                "jobs": discover_jobs(host, session),
                "dlt_pipelines": discover_delta_live_tables(host, session),
                "external_locations": discover_external_locations(host, session),
                "dashboards": discover_dashboards(host, session),
                "ai_bi_agents": discover_ai_bi_agents(host, session),
            }
            logger.info("GATE[Phase 2]: Discovery complete — PASS")
            return inventory
        except Exception as exc:
            logger.warning("Discovery attempt %d failed: %s", attempt, exc)
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF ** attempt
                logger.info("Retrying discovery in %d seconds …", wait)
                time.sleep(wait)

    logger.error("GATE[Phase 2]: Discovery — FAIL after %d attempts.", MAX_RETRIES)
    sys.exit(3)


# ---------------------------------------------------------------------------
# Phase 3 — Ontology: draw.io XML generation (Palantir-style)
# ---------------------------------------------------------------------------

NODE_STYLE = {
    "workspace":   "shape=mxgraph.azure.workspace;fillColor=#0078D4;fontColor=#ffffff;strokeColor=#005A9E;fontStyle=1;fontSize=11;",
    "catalog":     "shape=mxgraph.aws4.resourceIcon;fillColor=#232F3E;fontColor=#ffffff;strokeColor=#147EBA;fontStyle=1;fontSize=10;",
    "schema":      "shape=mxgraph.flowchart.database;fillColor=#1B4F72;fontColor=#ffffff;strokeColor=#1A5276;fontSize=9;",
    "table":       "shape=table;fillColor=#154360;fontColor=#ffffff;strokeColor=#1A5276;fontSize=8;",
    "cluster":     "shape=mxgraph.aws4.resourceIcon;fillColor=#E8762D;fontColor=#ffffff;strokeColor=#D35400;fontStyle=1;fontSize=10;",
    "warehouse":   "shape=mxgraph.aws4.resourceIcon;fillColor=#1E8449;fontColor=#ffffff;strokeColor=#196F3D;fontStyle=1;fontSize=10;",
    "job":         "shape=mxgraph.bpmn.shape;perimeter=mxPerimeter.ellipsePerimeter;fillColor=#7D3C98;fontColor=#ffffff;strokeColor=#6C3483;fontSize=9;",
    "dlt":         "shape=mxgraph.flowchart.process;fillColor=#922B21;fontColor=#ffffff;strokeColor=#7B241C;fontStyle=1;fontSize=9;",
    "external":    "shape=mxgraph.cisco.servers.standard_server;fillColor=#117A65;fontColor=#ffffff;strokeColor=#0E6655;fontSize=9;",
    "dashboard":   "shape=mxgraph.mockup.containers.smartphone;fillColor=#1A237E;fontColor=#ffffff;strokeColor=#283593;fontSize=9;",
    "ai_agent":    "shape=mxgraph.aws4.resourceIcon;fillColor=#4A235A;fontColor=#ffffff;strokeColor=#76448A;fontStyle=1;fontSize=10;",
    "medallion":   "shape=mxgraph.flowchart.process;fillColor=#B7950B;fontColor=#ffffff;strokeColor=#9A7D0A;fontStyle=1;fontSize=9;",
}

EDGE_STYLE = "edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;exitX=0.5;exitY=1;exitDx=0;exitDy=0;entryX=0.5;entryY=0;entryDx=0;entryDy=0;strokeColor=#455A64;strokeWidth=1.5;fontSize=8;"
EDGE_DATA_FLOW = "edgeStyle=elbowEdgeStyle;strokeColor=#27AE60;strokeWidth=2;dashed=1;fontSize=8;exitX=1;exitY=0.5;exitDx=0;exitDy=0;entryX=0;entryY=0.5;entryDx=0;entryDy=0;"


def _cell(cell_id: str, value: str, style: str, x: int, y: int, w: int = 160, h: int = 60,
          vertex: bool = True) -> ET.Element:
    el = ET.Element("mxCell")
    el.set("id", cell_id)
    el.set("value", value)
    el.set("style", style)
    el.set("vertex" if vertex else "edge", "1")
    el.set("parent", "1")
    geo = ET.SubElement(el, "mxGeometry")
    geo.set("x", str(x))
    geo.set("y", str(y))
    geo.set("width", str(w))
    geo.set("height", str(h))
    geo.set("as", "geometry")
    return el


def _edge(edge_id: str, source: str, target: str, label: str = "", style: str = None) -> ET.Element:
    el = ET.Element("mxCell")
    el.set("id", edge_id)
    el.set("value", label)
    el.set("style", style or EDGE_STYLE)
    el.set("edge", "1")
    el.set("source", source)
    el.set("target", target)
    el.set("parent", "1")
    geo = ET.SubElement(el, "mxGeometry")
    geo.set("relative", "1")
    geo.set("as", "geometry")
    return el


def phase3_ontology(inventory: dict, output_path: Path) -> None:
    logger.info("=== PHASE 3: Ontology — Building Palantir-style draw.io diagram ===")

    cells = []
    eid = 1000  # edge id counter

    def next_eid() -> str:
        nonlocal eid
        eid += 1
        return f"e{eid}"

    # Root cells required by draw.io
    root = ET.Element("root")
    root_cell0 = ET.SubElement(root, "mxCell")
    root_cell0.set("id", "0")
    root_cell1 = ET.SubElement(root, "mxCell")
    root_cell1.set("id", "1")
    root_cell1.set("parent", "0")

    # Track positions
    X_BASE = 60
    Y_BASE = 60
    X_GAP = 200
    Y_GAP = 120

    # ---- Workspace node ----
    ws = inventory.get("workspace", {})
    ws_id = "ws_root"
    ws_label = f"Workspace\n{ws.get('host', 'unknown')}"
    cells.append(_cell(ws_id, ws_label, NODE_STYLE["workspace"], X_BASE + 600, Y_BASE, 200, 70))

    # ---- Catalogs ----
    catalogs = inventory.get("catalogs", [])
    cat_y = Y_BASE + Y_GAP + 60
    for ci, cat in enumerate(catalogs):
        cat_id = f"cat_{ci}"
        cat_label = f"Catalog\n{cat.get('name', 'unknown')}"
        cx = X_BASE + ci * (X_GAP + 20)
        cells.append(_cell(cat_id, cat_label, NODE_STYLE["catalog"], cx, cat_y, 160, 60))
        cells.append(_edge(next_eid(), ws_id, cat_id, "contains", EDGE_STYLE))

        # Schemas under catalog (limit to 3 for readability)
        for si, schema in enumerate(cat.get("schemas", [])[:3]):
            sc_id = f"sc_{ci}_{si}"
            sc_label = f"Schema\n{schema.get('name', '')}"
            sx = cx + si * 180
            sy = cat_y + Y_GAP
            cells.append(_cell(sc_id, sc_label, NODE_STYLE["schema"], sx, sy, 150, 50))
            cells.append(_edge(next_eid(), cat_id, sc_id, "has schema"))

            for ti, tbl in enumerate(schema.get("tables", [])[:3]):
                tb_id = f"tb_{ci}_{si}_{ti}"
                tb_label = f"{tbl.get('name', '')}\n({tbl.get('table_type', '')})"
                ty = sy + Y_GAP - 20
                tx = sx + ti * 170
                cells.append(_cell(tb_id, tb_label, NODE_STYLE["table"], tx, ty, 150, 45))
                cells.append(_edge(next_eid(), sc_id, tb_id, "contains"))

    # ---- Clusters ----
    clusters = inventory.get("clusters", [])
    cl_y = Y_BASE
    cl_x_start = X_BASE + 1400
    for cli, cl in enumerate(clusters[:6]):
        cl_id = f"cl_{cli}"
        cl_label = f"Cluster\n{cl.get('cluster_name', '')}\n[{cl.get('state', '')}]"
        cells.append(_cell(cl_id, cl_label, NODE_STYLE["cluster"],
                           cl_x_start, cl_y + cli * (Y_GAP - 10), 160, 65))
        cells.append(_edge(next_eid(), ws_id, cl_id, "runs", EDGE_DATA_FLOW))

    # ---- SQL Warehouses ----
    warehouses = inventory.get("warehouses", [])
    wh_x = cl_x_start + X_GAP + 20
    for wi, wh in enumerate(warehouses[:6]):
        wh_id = f"wh_{wi}"
        wh_label = f"Warehouse\n{wh.get('name', '')}\n[{wh.get('state', '')}]"
        cells.append(_cell(wh_id, wh_label, NODE_STYLE["warehouse"],
                           wh_x, cl_y + wi * (Y_GAP - 10), 160, 65))
        cells.append(_edge(next_eid(), ws_id, wh_id, "hosts", EDGE_DATA_FLOW))

    # ---- Medallion pipelines ----
    jobs = inventory.get("jobs", {})
    medallion = jobs.get("medallion_pipelines", [])
    med_y = cat_y + Y_GAP * 4
    for mi, med in enumerate(medallion[:8]):
        med_id = f"med_{mi}"
        med_label = f"Medallion\n{med.get('name', '')}"
        cells.append(_cell(med_id, med_label, NODE_STYLE["medallion"],
                           X_BASE + mi * (X_GAP - 10), med_y, 170, 55))
        cells.append(_edge(next_eid(), ws_id, med_id, "orchestrates"))

    # ---- Ingestion pipelines ----
    ingestion = jobs.get("ingestion_pipelines", [])
    ing_y = med_y + Y_GAP
    for ii, ing in enumerate(ingestion[:8]):
        ing_id = f"ing_{ii}"
        ing_label = f"Ingestion\n{ing.get('name', '')}"
        cells.append(_cell(ing_id, ing_label, NODE_STYLE["job"],
                           X_BASE + ii * (X_GAP - 10), ing_y, 170, 55))
        cells.append(_edge(next_eid(), ws_id, ing_id, "runs"))
        # Connect ingestion → catalog 0 if present
        if catalogs:
            cells.append(_edge(next_eid(), ing_id, "cat_0", "writes to", EDGE_DATA_FLOW))

    # ---- DLT Pipelines ----
    dlts = inventory.get("dlt_pipelines", [])
    dlt_y = ing_y + Y_GAP
    for di, dlt in enumerate(dlts[:6]):
        dlt_id = f"dlt_{di}"
        dlt_label = f"DLT Pipeline\n{dlt.get('name', '')}\n[{dlt.get('state', '')}]"
        cells.append(_cell(dlt_id, dlt_label, NODE_STYLE["dlt"],
                           X_BASE + di * (X_GAP - 10), dlt_y, 170, 65))
        cells.append(_edge(next_eid(), ws_id, dlt_id, "manages"))

    # ---- External Locations (Data Sources) ----
    externals = inventory.get("external_locations", [])
    ext_y = dlt_y + Y_GAP
    for xi, ext in enumerate(externals[:6]):
        ext_id = f"ext_{xi}"
        ext_label = f"External Source\n{ext.get('name', '')}\n{ext.get('url', '')[:30]}"
        cells.append(_cell(ext_id, ext_label, NODE_STYLE["external"],
                           X_BASE + xi * (X_GAP + 10), ext_y, 180, 65))
        # External → Ingestion edge (data flow)
        if ingestion:
            cells.append(_edge(next_eid(), ext_id, "ing_0", "feeds", EDGE_DATA_FLOW))

    # ---- Dashboards ----
    dashboards = inventory.get("dashboards", [])
    dash_y = Y_BASE + 80
    dash_x = wh_x + X_GAP + 20
    for dashi, dash in enumerate(dashboards[:6]):
        dash_id = f"dash_{dashi}"
        dash_label = f"Dashboard\n{dash.get('name', '')}"
        cells.append(_cell(dash_id, dash_label, NODE_STYLE["dashboard"],
                           dash_x, dash_y + dashi * (Y_GAP - 10), 160, 55))
        if warehouses:
            cells.append(_edge(next_eid(), "wh_0", dash_id, "powers", EDGE_DATA_FLOW))

    # ---- AI-BI Agents ----
    ai_agents = inventory.get("ai_bi_agents", [])
    ai_x = dash_x + X_GAP + 20
    for ai_i, agent in enumerate(ai_agents[:6]):
        ai_id = f"ai_{ai_i}"
        ai_label = f"AI-BI Agent\n{agent.get('name', '')}"
        cells.append(_cell(ai_id, ai_label, NODE_STYLE["ai_agent"],
                           ai_x, dash_y + ai_i * (Y_GAP - 10), 160, 55))
        if warehouses:
            cells.append(_edge(next_eid(), "wh_0", ai_id, "queries", EDGE_DATA_FLOW))
        if catalogs:
            cells.append(_edge(next_eid(), "cat_0", ai_id, "reads", EDGE_DATA_FLOW))

    # Assemble XML
    mxGraphModel = ET.Element("mxGraphModel")
    mxGraphModel.set("dx", "1422")
    mxGraphModel.set("dy", "762")
    mxGraphModel.set("grid", "1")
    mxGraphModel.set("gridSize", "10")
    mxGraphModel.set("guides", "1")
    mxGraphModel.set("tooltips", "1")
    mxGraphModel.set("connect", "1")
    mxGraphModel.set("arrows", "1")
    mxGraphModel.set("fold", "1")
    mxGraphModel.set("page", "1")
    mxGraphModel.set("pageScale", "1")
    mxGraphModel.set("pageWidth", "3508")
    mxGraphModel.set("pageHeight", "2480")
    mxGraphModel.set("math", "0")
    mxGraphModel.set("shadow", "0")
    mxGraphModel.append(root)

    for cell in cells:
        cell.set("parent", "1")
        root.append(cell)

    raw_xml = ET.tostring(mxGraphModel, encoding="unicode")
    pretty_xml = minidom.parseString(raw_xml).toprettyxml(indent="  ")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(pretty_xml, encoding="utf-8")
    logger.info("GATE[Phase 3]: Ontology diagram saved → %s", output_path)


# ---------------------------------------------------------------------------
# Save inventory JSON
# ---------------------------------------------------------------------------

def save_inventory(inventory: dict, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"databricks_inventory_{ts}.json"
    json_path.write_text(json.dumps(inventory, indent=2, default=str), encoding="utf-8")
    logger.info("Inventory JSON saved → %s", json_path)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------