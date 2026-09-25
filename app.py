"""
Streamlit web interface for the Navjeevan disaster-response triage system.

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import streamlit as st
import time
import threading

# --------------------------------------------------------------------------- #
# Page config — must be first Streamlit call
# --------------------------------------------------------------------------- #

st.set_page_config(
    page_title="Navjeevan · Disaster Alert System",
    page_icon="🚨",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# --------------------------------------------------------------------------- #
# Custom CSS — premium dark theme with glassmorphism
# --------------------------------------------------------------------------- #

st.markdown(
    """
<style>
/* ── Import fonts ───────────────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap');

/* ── Root ───────────────────────────────────────────────────────────── */
:root {
    --bg-primary: #000000;
    --bg-panel: #0a0a0a;
    --border-color: #333333;
    --text-primary: #ffffff;
    --text-secondary: #a3a3a3;
    --text-muted: #525252;
    --accent-red: #ff3333;
    --accent-amber: #ffcc00;
    --accent-emerald: #00ff00;
    --accent-sky: #33ccff;
    --accent-indigo: #ffffff;
}

/* ── Global overrides ───────────────────────────────────────────────── */
html, body, .stApp, [data-testid="stAppViewContainer"] {
    background-color: var(--bg-primary) !important;
    color: var(--text-primary) !important;
    font-family: 'Inter', -apple-system, sans-serif !important;
}
[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stSidebar"] { background: var(--bg-primary) !important; }

/* ── Hero banner ────────────────────────────────────────────────────── */
.hero-banner {
    text-align: left;
    padding: 1.5rem 0 2rem;
    border-bottom: 1px solid var(--border-color);
    margin-bottom: 2rem;
}
.hero-title {
    font-size: 2rem;
    font-weight: 700;
    color: var(--text-primary);
    letter-spacing: -0.5px;
    margin-bottom: 0.2rem;
    text-transform: uppercase;
}
.hero-subtitle {
    font-size: 0.9rem;
    color: var(--text-secondary);
    font-family: 'JetBrains Mono', monospace;
}

/* ── Panels ─────────────────────────────────────────────────────────── */
.data-panel {
    background: var(--bg-panel);
    border: 1px solid var(--border-color);
    border-radius: 2px;
    padding: 1.25rem;
    margin-bottom: 1rem;
}
.summary-panel {
    height: 320px;
    overflow-y: auto;
}
.card-title {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--text-secondary);
    margin-bottom: 0.75rem;
    border-bottom: 1px solid #222;
    padding-bottom: 0.5rem;
}
.card-value {
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--text-primary);
    line-height: 1.3;
}
.card-detail {
    font-size: 0.85rem;
    color: var(--text-secondary);
    margin-top: 0.5rem;
}

/* ── Severity badges ────────────────────────────────────────────────── */
.badge {
    display: inline-block;
    padding: 0.15rem 0.5rem;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    border: 1px solid;
    border-radius: 2px;
}
.badge-critical { background: transparent; color: var(--accent-red); border-color: var(--accent-red); }
.badge-high     { background: transparent; color: var(--accent-amber); border-color: var(--accent-amber); }
.badge-medium   { background: transparent; color: var(--accent-amber); border-color: #666; }
.badge-low      { background: transparent; color: var(--accent-emerald); border-color: var(--accent-emerald); }

/* ── Pipeline steps ─────────────────────────────────────────────────── */
.step-tracker {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    margin: 1rem 0;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem;
}
.step-pill {
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
.step-pending  { color: var(--text-muted); }
.step-running  { color: var(--text-primary); font-weight: 700; }
.step-done     { color: var(--text-secondary); }

/* ── Resource cards ─────────────────────────────────────────────────── */
.resource-item {
    border-left: 2px solid var(--border-color);
    padding: 0.5rem 0.75rem;
    margin-bottom: 0.75rem;
}
.resource-name {
    font-weight: 600;
    font-size: 0.9rem;
    color: var(--text-primary);
}
.resource-detail {
    font-size: 0.8rem;
    color: var(--text-secondary);
    margin-top: 0.2rem;
}
.resource-meta {
    font-size: 0.75rem;
    color: var(--text-secondary);
    margin-top: 0.2rem;
    font-family: 'JetBrains Mono', monospace;
}

/* ── Action plan ────────────────────────────────────────────────────── */
.action-step {
    display: flex;
    gap: 0.75rem;
    padding: 0.75rem 0;
    border-bottom: 1px dashed var(--border-color);
}
.action-step:last-child { border-bottom: none; }
.action-number {
    flex-shrink: 0;
    font-family: 'JetBrains Mono', monospace;
    font-weight: 700;
    font-size: 0.85rem;
    color: var(--text-secondary);
}
.action-text {
    font-size: 0.9rem;
    color: var(--text-primary);
    line-height: 1.5;
}

/* ── Not-emergency ──────────────────────────────────────────────────── */
.no-emergency-box {
    padding: 2rem;
    border: 1px solid var(--border-color);
    border-left: 4px solid var(--accent-emerald);
}
.no-emergency-title { font-family: 'JetBrains Mono', monospace; font-size: 1rem; font-weight: 700; color: var(--text-primary); text-transform: uppercase; }
.no-emergency-text  { font-size: 0.9rem; color: var(--text-secondary); margin-top: 0.75rem; }

/* ── Text area & button styling ─────────────────────────────────────── */
textarea {
    background: var(--bg-panel) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: 2px !important;
    color: var(--text-primary) !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.85rem !important;
}
textarea:focus {
    border-color: var(--text-primary) !important;
    box-shadow: none !important;
}
/* primary button */
.stButton > button[kind="primary"], .stButton > button {
    background: var(--bg-primary) !important;
    color: var(--text-primary) !important;
    border: 1px solid var(--text-primary) !important;
    border-radius: 2px !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-weight: 700 !important;
    font-size: 0.85rem !important;
    text-transform: uppercase !important;
    padding: 0.5rem 1.5rem !important;
}
.stButton > button:hover {
    background: var(--text-primary) !important;
    color: var(--bg-primary) !important;
}
/* disabled */
.stButton > button:disabled {
    opacity: 0.5 !important;
    cursor: not-allowed !important;
}

/* ── Disclaimer bar ─────────────────────────────────────────────────── */
.disclaimer {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
    color: var(--text-muted);
    padding: 1rem 0;
    border-top: 1px solid var(--border-color);
    margin-top: 3rem;
}

/* ── Divider ────────────────────────────────────────────────────────── */
.section-divider {
    height: 1px;
    background: var(--border-color);
    margin: 2rem 0;
}

/* ── Hide default streamlit elements ────────────────────────────────── */
#MainMenu, footer, [data-testid="stDecoration"] { display: none !important; }
</style>
""",
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------- #
# Hero banner
# --------------------------------------------------------------------------- #

st.markdown(
    """
<div class="hero-banner">
    <div class="hero-title">NAVJEEVAN_SYS</div>
    <div class="hero-subtitle">DISASTER RESPONSE TRIAGE / V1.0</div>
</div>
""",
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------- #
# Pipeline node labels (for step tracker)
# --------------------------------------------------------------------------- #

NODE_LABELS = {
    "analyze": "ANALYZE_REPORT",
    "classify": "CLASSIFY_TYPE",
    "extract": "EXTRACT_ENTITIES",
    "severity": "ASSESS_SEVERITY",
    "medical_resources": "LOCATE_MEDICAL",
    "rescue_resources": "LOCATE_RESCUE",
    "general_resources": "AGGREGATE_RESOURCES",
    "plan": "GENERATE_PLAN",
    "respond": "DISPATCH_RESPONSE",
    "not_emergency": "FLAG_NOT_EMERGENCY",
}

SEVERITY_COLORS = {
    "CRITICAL": "critical",
    "HIGH": "high",
    "MEDIUM": "medium",
    "LOW": "low",
}

CATEGORY_ICONS = {
    "medical": "[+]",
    "rescue": "[!]",
}

CATEGORY_LABEL = {
    "medical": "MEDICAL_RESOURCES",
    "rescue": "RESCUE_TEAMS",
}

NEED_ICONS = {
    "medical": "MED",
    "rescue": "RSC",
    "food": "FOD",
    "water": "WTR",
    "shelter": "SHL",
    "evacuation": "EVC",
}



# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _count(value, reported):
    if value is not None:
        return str(value)
    return "UNKNOWN" if reported else "NONE"


def render_step_tracker(completed: list[str], running: str | None, all_steps: list[str]):
    """Render the pipeline step tracker pills."""
    pills = []
    for step in all_steps:
        label = NODE_LABELS.get(step, step)
        if step in completed:
            pills.append(f'<div class="step-pill step-done"><span style="color:var(--text-muted)">[OK]</span> {label}</div>')
        elif step == running:
            pills.append(f'<div class="step-pill step-running"><span style="color:var(--text-primary)">[>>]</span> {label}</div>')
        else:
            pills.append(f'<div class="step-pill step-pending"><span style="color:var(--bg-panel)">[  ]</span> {label}</div>')
    st.markdown(f'<div class="step-tracker">{"".join(pills)}</div>', unsafe_allow_html=True)


def render_glass_card(title: str, value: str, detail: str = ""):
    detail_html = f'<div class="card-detail">{detail}</div>' if detail else ""
    st.markdown(
        f"""<div class="data-panel summary-panel">
    <div class="card-title">{title}</div>
    <div class="card-value">{value}</div>
    {detail_html}
</div>""",
        unsafe_allow_html=True,
    )


def render_severity_badge(severity: str):
    cls = SEVERITY_COLORS.get(severity, "medium")
    return f'<span class="badge badge-{cls}">{severity}</span>'


# --------------------------------------------------------------------------- #
# Run pipeline — streams node-by-node via graph.stream()
# --------------------------------------------------------------------------- #

def run_pipeline_streaming(report: str):
    """Import navjeevan, run the graph with stream(), and yield state snapshots."""
    import navjeevan  # deferred so env loads at import time
    import importlib
    importlib.reload(navjeevan)

    # Track which nodes complete and the latest state
    completed_nodes: list[str] = []
    state_snapshot: dict = {}

    # graph.stream yields (node_name, partial_state) tuples
    for event in navjeevan.graph.stream(
        {"report": report, "resources": []},
        stream_mode="updates",
    ):
        for node_name, updates in event.items():
            for k, v in updates.items():
                if k == "resources":
                    state_snapshot.setdefault("resources", []).extend(v)
                else:
                    state_snapshot[k] = v
            completed_nodes.append(node_name)

        yield {
            "completed": list(completed_nodes),
            "state": dict(state_snapshot),
        }


# --------------------------------------------------------------------------- #
# Session state init
# --------------------------------------------------------------------------- #

if "result" not in st.session_state:
    st.session_state.result = None
if "running" not in st.session_state:
    st.session_state.running = False
if "steps_completed" not in st.session_state:
    st.session_state.steps_completed = []
if "error" not in st.session_state:
    st.session_state.error = None


# --------------------------------------------------------------------------- #
# Input section
# --------------------------------------------------------------------------- #

st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

col_input, col_btn = st.columns([4, 1], vertical_alignment="bottom")

with col_input:
    report_text = st.text_area(
        "INPUT_REPORT_DATA",
        placeholder="e.g. A 5-storey building has collapsed in Saket, Delhi. Several people are feared trapped under the debris. Fire brigade teams are on site.",
        height=120,
        label_visibility="visible",
    )

with col_btn:
    run_clicked = st.button(
        "EXECUTE",
        use_container_width=True,
        disabled=st.session_state.running,
    )



# --------------------------------------------------------------------------- #
# Pipeline execution
# --------------------------------------------------------------------------- #

if run_clicked and report_text.strip():
    st.session_state.result = None
    st.session_state.error = None
    st.session_state.running = True
    st.session_state.steps_completed = []

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

    # Step tracker placeholder
    tracker_placeholder = st.empty()
    status_placeholder = st.empty()

    # All potential pipeline steps
    all_steps = [
        "analyze", "classify", "extract", "severity",
        "medical_resources", "rescue_resources",
        "general_resources", "plan", "respond", "not_emergency",
    ]

    current_running = "analyze"
    with tracker_placeholder.container():
        render_step_tracker([], current_running, all_steps)

    status_placeholder.info("> PROCESSING DATA...")

    try:
        final_state = None
        for snapshot in run_pipeline_streaming(report_text.strip()):
            completed = snapshot["completed"]
            final_state = snapshot["state"]
            st.session_state.steps_completed = completed

            # Figure out what's likely running next
            # (stream gives us completed — the "running" is the one after the last completed)
            next_node = None
            if "not_emergency" not in completed and "respond" not in completed:
                # Estimate next node
                pipeline_order = ["analyze", "classify", "extract", "severity", "plan", "respond"]
                for n in pipeline_order:
                    if n not in completed:
                        next_node = n
                        break

            with tracker_placeholder.container():
                render_step_tracker(completed, next_node, all_steps)

        if final_state:
            st.session_state.result = final_state
            with tracker_placeholder.container():
                render_step_tracker(
                    st.session_state.steps_completed, None, all_steps
                )
            status_placeholder.success("> PROCESS COMPLETE")
        else:
            status_placeholder.warning("> ERR: NO_OUTPUT")

    except Exception as exc:
        import traceback
        st.session_state.error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        status_placeholder.error(f"> ERR: {st.session_state.error}")

    st.session_state.running = False
    time.sleep(0.8)
    st.rerun()


# --------------------------------------------------------------------------- #
# Display results
# --------------------------------------------------------------------------- #

if st.session_state.error:
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    st.error(f"ERR: {st.session_state.error}")
    st.info("Try rephrasing the report or check your API keys in `.env`.")

if st.session_state.result:
    state = st.session_state.result
    completed = st.session_state.steps_completed

    all_steps = [
        "analyze", "classify", "extract", "severity",
        "medical_resources", "rescue_resources",
        "general_resources", "plan", "respond", "not_emergency",
    ]

    # Show completed tracker
    render_step_tracker(completed, None, all_steps)

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

    # ── Not an emergency ────────────────────────────────────────────── #
    if not state.get("is_emergency", True):
        st.markdown(
            f"""<div class="no-emergency-box">
    <div class="no-emergency-title">SYS_HALT: NON_EMERGENCY_DETECTED</div>
    <div class="no-emergency-text">{state.get('summary', '')}</div>
    <div class="no-emergency-text" style="color: var(--text-muted); font-family: 'JetBrains Mono', monospace; font-size: 0.75rem;">
        > REASON: NOT_ACTIONABLE
    </div>
</div>""",
            unsafe_allow_html=True,
        )

    # ── Full emergency dashboard ────────────────────────────────────── #
    else:
        # ── Summary ─────────────────────────────────────────────────── #
        st.markdown(
            f"""<div class="data-panel" style="border-left: 2px solid var(--text-primary);">
    <div class="card-title">INCIDENT_SUMMARY</div>
    <div style="font-size: 0.95rem; color: var(--text-primary); line-height: 1.5;">{state.get('summary', 'N/A')}</div>
</div>""",
            unsafe_allow_html=True,
        )

        # ── Key metrics row ─────────────────────────────────────────── #
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            dtype = state.get("disaster_type", "N/A")
            type_icons = {
                "FLOOD": "[FLD]", "FIRE": "[FIR]", "EARTHQUAKE": "[EQK]",
                "BUILDING_COLLAPSE": "[BC]", "ROAD_ACCIDENT": "[RA]",
                "LANDSLIDE": "[LND]", "CYCLONE": "[CYC]", "OTHER": "[OTH]",
            }
            render_glass_card(
                "Disaster Type",
                f'{type_icons.get(dtype, "[OTH]")} {dtype.replace("_", " ").title()}',
            )
        with c2:
            _loc_ctx = state.get("location_context", "")
            _loc_detail = f"REGION: {_loc_ctx}" if _loc_ctx else ""
            render_glass_card(
                "Location",
                f"{state.get('location', 'Unknown')}",
                _loc_detail,
            )
        with c3:
            sev = state.get("severity", "N/A")
            badge = render_severity_badge(sev)
            pri = state.get("priority", "N/A")
            pri_badge = render_severity_badge(pri)
            st.markdown(
                f"""<div class="data-panel summary-panel">
    <div class="card-title">SEV_PRIORITY</div>
    <div style="margin-top: 0.3rem;">SEV: {badge}</div>
    <div style="margin-top: 0.5rem;">PRI: {pri_badge}</div>
    <div class="card-detail">{state.get('severity_reasoning', '')}</div>
</div>""",
                unsafe_allow_html=True,
            )
        with c4:
            injured = _count(
                state.get("injured"),
                state.get("injuries_reported", False),
            )
            killed = _count(
                state.get("killed"),
                state.get("fatalities_reported", False),
            )
            
            main_val = "UNKNOWN"
            detail_val = ""
            
            if killed != "NONE" and injured != "NONE":
                main_val = f"KILLED: {killed}"
                detail_val = f"INJURED: {injured}"
            elif killed != "NONE":
                main_val = f"KILLED: {killed}"
            elif injured != "NONE":
                main_val = f"INJURED: {injured}"

            render_glass_card(
                "People Impact",
                main_val,
                detail_val,
            )

        # ── Required assistance ─────────────────────────────────────── #
        needs = state.get("needs", [])
        if needs:
            needs_pills = "".join(
                f'<span style="font-family:JetBrains Mono;font-size:0.7rem;font-weight:700;padding:0.15rem 0.4rem;border:1px solid var(--border-color);margin-right:0.4rem;">{NEED_ICONS.get(n, "REQ")} {n.upper()}</span>'
                for n in needs
            )
            st.markdown(
                f"""<div class="data-panel">
    <div class="card-title">REQUIRED_ASSISTANCE</div>
    <div style="display: flex; flex-wrap: wrap; margin-top: 0.5rem;">
        {needs_pills}
    </div>
</div>""",
                unsafe_allow_html=True,
            )



        # ── Map ─────────────────────────────────────────────────────── #
        lat = state.get("lat")
        lon = state.get("lon")
        if lat is not None and lon is not None:
            import pandas as pd

            st.markdown(
                '<div class="card-title" style="margin-bottom: 0.8rem;">INCIDENT_LOCATION</div>',
                unsafe_allow_html=True,
            )

            import base64

            def get_dashed_circle_b64(color_hex):
                # Use a larger 512x512 SVG so it stays crisp when scaling as meters
                svg = f'<svg width="512" height="512" xmlns="http://www.w3.org/2000/svg"><circle cx="256" cy="256" r="250" fill="none" stroke="{color_hex}" stroke-width="12" stroke-dasharray="30 30"/></svg>'
                b64 = base64.b64encode(svg.encode()).decode()
                return f"data:image/svg+xml;base64,{b64}"

            icon_red = {
                "url": get_dashed_circle_b64("#ff3333"),
                "width": 512, "height": 512, "anchorY": 256
            }
            
            cat_colors = {
                "MEDICAL": "#00ff00",  # green
                "RESCUE": "#00d0ff",   # blue
                "SUPPLIES": "#ff8800", # orange
                "GENERAL": "#ff8800",  # orange
            }
            
            cat_icons = {
                cat: {"url": get_dashed_circle_b64(color), "width": 512, "height": 512, "anchorY": 256}
                for cat, color in cat_colors.items()
            }

            # Build map data: incident + nearby resources
            # size is diameter in meters (radius 800 -> 1600)
            map_points = [{"lat": lat, "lon": lon, "label": "[INCIDENT]", "icon_data": icon_red, "size": 1600, "text_color": [255, 255, 255]}]
            route_lines = []
            cat_rgb = {"MEDICAL": [0,255,0,100], "RESCUE": [0,208,255,100], "SUPPLIES": [255,136,0,100], "GENERAL": [255,136,0,100]}

            resources = state.get("resources", [])
            for entry in resources:
                cat = entry.get("category", "RESOURCE").upper()
                icon = cat_icons.get(cat, cat_icons.get("GENERAL", icon_red))
                
                for item in entry.get("items", []):
                    r_lat = item.get("lat")
                    r_lon = item.get("lon")
                    
                    # Fallback: parse lat/lon from source URL
                    if r_lat is None and item.get("source"):
                        import re as _re
                        match = _re.search(r"mlat=([\d.]+)&mlon=([\d.]+)", item["source"])
                        if match:
                            r_lat, r_lon = float(match.group(1)), float(match.group(2))
                        else:
                            match = _re.search(r"@([\d.-]+),([\d.-]+)", item["source"])
                            if match:
                                r_lat, r_lon = float(match.group(1)), float(match.group(2))
                    
                    if r_lat is not None and r_lon is not None:
                        map_points.append({
                            "lat": float(r_lat), "lon": float(r_lon),
                            "label": f"[{cat}] {item['name']}",
                            "icon_data": icon, "size": 600,
                            "text_color": [255, 255, 255]
                        })
                        route_lines.append({
                            "start_lat": lat, "start_lon": lon,
                            "end_lat": float(r_lat), "end_lon": float(r_lon),
                            "color": cat_rgb.get(cat, [200, 200, 200, 80])
                        })

            df = pd.DataFrame(map_points)
            
            # Add Map Legend
            st.markdown(
                '''
                <div style="display: flex; gap: 20px; font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; margin-bottom: 12px; padding: 10px; border: 1px solid #222; background: #050505; flex-wrap: wrap;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <div style="width: 10px; height: 10px; background-color: #ff3333; border-radius: 50%;"></div>
                        <span style="color: #aaa;">[INCIDENT]</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <div style="width: 10px; height: 10px; background-color: #00ff00; border-radius: 50%;"></div>
                        <span style="color: #aaa;">[MEDICAL]</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <div style="width: 10px; height: 10px; background-color: #00d0ff; border-radius: 50%;"></div>
                        <span style="color: #aaa;">[RESCUE]</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <div style="width: 14px; height: 0; border-top: 1.5px dashed #666;"></div>
                        <span style="color: #aaa;">[ROUTE]</span>
                    </div>
                </div>
                ''', unsafe_allow_html=True
            )

            # Render map layers using PyDeck
            import pydeck as pdk
            
            layers = []
            
            # Route lines from incident to resources
            if route_lines:
                route_df = pd.DataFrame(route_lines)
                layers.append(pdk.Layer(
                    "LineLayer",
                    data=route_df,
                    get_source_position="[start_lon, start_lat]",
                    get_target_position="[end_lon, end_lat]",
                    get_color="color",
                    get_width=2,
                    width_min_pixels=1,
                ))
            
            layers.append(pdk.Layer(
                "IconLayer",
                data=df,
                get_icon="icon_data",
                get_size="size",
                size_units="'meters'",
                size_scale=1,
                get_position="[lon, lat]",
                pickable=True,
            ))
            
            layers.append(pdk.Layer(
                "TextLayer",
                data=df,
                get_position="[lon, lat]",
                get_text="label",
                get_size=70,
                font_weight="'bold'",
                get_color="text_color",
                get_alignment_baseline="'top'",
                get_text_anchor="'middle'",
                get_pixel_offset="[0, 10]",
                font_family="'JetBrains Mono', monospace",
            ))

            view_state = pdk.ViewState(latitude=lat, longitude=lon, zoom=12)
            st.pydeck_chart(pdk.Deck(
                layers=layers,
                initial_view_state=view_state,
                map_provider="carto",
                map_style=pdk.map_styles.CARTO_DARK,
                tooltip={"text": "{label}"}
            ))

        st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

        # ── Resources ───────────────────────────────────────────────── #
        resources = state.get("resources", [])
        if resources:
            total_items = sum(len(e.get("items", [])) for e in resources)
            cat_color_map = {"medical": "#00ff00", "rescue": "#00d0ff"}
            count_pills = ""
            for e in resources:
                _cat = e.get("category", "")
                _n = len(e.get("items", []))
                if _n > 0:
                    _clr = cat_color_map.get(_cat, "#fff")
                    _ico = CATEGORY_ICONS.get(_cat, "[ ]")
                    count_pills += (
                        f'<span style="font-family:JetBrains Mono;font-size:0.65rem;font-weight:700;'
                        f'padding:0.1rem 0.35rem;border:1px solid #333;margin-left:0.3rem;'
                        f'color:{_clr};">{_ico} {_n}</span>'
                    )
            st.markdown(
                f'<div class="card-title" style="margin-bottom: 0.8rem;">LOCATED_RESOURCES '
                f'<span style="font-weight: 400; text-transform: none; font-size: 0.7rem; color: var(--text-muted);">'
                f'({total_items} FOUND · NOT_VERIFIED)</span>{count_pills}</div>',
                unsafe_allow_html=True,
            )

            res_cols = st.columns(min(len(resources), 3))
            for idx, entry in enumerate(resources):
                cat = entry.get("category", "")
                icon = CATEGORY_ICONS.get(cat, "[ ]")
                label = CATEGORY_LABEL.get(cat, cat.upper())
                items = entry.get("items", [])
                note = entry.get("note", "")

                with res_cols[idx % len(res_cols)]:
                    st.markdown(
                        f'<div class="card-title">{icon} {label}</div>',
                        unsafe_allow_html=True,
                    )

                    if not items:
                        st.markdown(
                            f"""<div class="resource-item">
    <div class="resource-name" style="color: var(--text-secondary);">[NO_DATA]</div>
    <div class="resource-detail">{note}</div>
</div>""",
                            unsafe_allow_html=True,
                        )
                    else:
                        for item in items:
                            _item_clr = cat_color_map.get(cat, "var(--accent-sky)")
                            dist = (
                                f'<span style="color: {_item_clr};">[{item["distance_km"]} km]</span> '
                                if item.get("distance_km") is not None
                                else ""
                            )
                            phone_html = (
                                f'<div class="resource-meta">TEL: {item["phone"]}</div>'
                                if item.get("phone")
                                else ""
                            )
                            direction_html = ""
                            lat_i = item.get("lat")
                            lon_i = item.get("lon")
                            
                            # Fallback to parsing lat/lon from OSM link for older data
                            if not lat_i and "openstreetmap.org" in item.get("source", ""):
                                import re as _re
                                match = _re.search(r"mlat=([\d.]+)&mlon=([\d.]+)", item["source"])
                                if match:
                                    lat_i, lon_i = match.group(1), match.group(2)
                                    
                            if lat_i and lon_i:
                                d_url = f"https://www.google.com/maps/dir/?api=1&origin={lat},{lon}&destination={lat_i},{lon_i}"
                                direction_html = f'<div class="resource-meta"><a href="{d_url}" target="_blank" style="color: var(--text-primary); text-decoration: underline;">[DIRECTIONS]</a></div>'
                            elif item.get("source"):
                                direction_html = f'<div class="resource-meta"><a href="{item["source"]}" target="_blank" style="color: var(--text-primary); text-decoration: underline;">[SOURCE]</a></div>'

                            detail_text = item.get("detail", "")
                            html_str = f'<div class="resource-item"><div class="resource-name">{dist}{item["name"]}</div><div class="resource-detail">{detail_text}</div>{phone_html}{direction_html}</div>'
                            st.markdown(html_str, unsafe_allow_html=True)

        st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

        # ── Action plan ─────────────────────────────────────────────── #
        actions = state.get("plan", [])
        if actions:
            st.markdown(
                '<div class="card-title" style="margin-bottom: 0.5rem;">ACTION_PLAN</div>',
                unsafe_allow_html=True,
            )
            html_parts = ['<div class="data-panel">']
            for i, action in enumerate(actions, 1):
                html_parts.append(
                    f"""<div class="action-step">
    <div class="action-number">[{i:02d}]</div>
    <div class="action-text">{action}</div>
</div>"""
                )
            html_parts.append("</div>")
            st.markdown("".join(html_parts), unsafe_allow_html=True)

        # ── Status ──────────────────────────────────────────────────── #
        pri = state.get("priority", "")
        if pri in ("HIGH", "CRITICAL"):
            status_text = "SYS: EMERGENCY_DEPLOYMENT_REQUIRED"
            status_border = "var(--accent-red)"
            status_text_color = "var(--accent-red)"
        else:
            status_text = "SYS: MONITORING_ONLY"
            status_border = "var(--text-secondary)"
            status_text_color = "var(--text-secondary)"

        st.markdown(
            f"""<div style="padding: 1rem; border: 1px solid {status_border}; border-left: 4px solid {status_border}; margin-top: 1rem;">
    <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; font-weight: 700; color: {status_text_color};">{status_text}</div>
</div>""",
            unsafe_allow_html=True,
        )

    # ── Raw response (collapsible) ──────────────────────────────────── #
    with st.expander("RAW_OUTPUT"):
        st.code(state.get("response", ""), language=None)

# --------------------------------------------------------------------------- #
# Footer
# --------------------------------------------------------------------------- #

st.markdown(
    """<div class="disclaimer">
    > LANGGRAPH / GROQ / TAVILY / STREAMLIT
</div>""",
    unsafe_allow_html=True,
)
