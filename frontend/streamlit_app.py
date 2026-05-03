"""
MIT License
Streamlit dashboard for the Multi-Agent Healthcare Provider Validator.
"""
import io

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

st.set_page_config(
    page_title="Healthcare Provider Validator",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

DARK_CSS = """
<style>
    body { background-color: #0e1117; color: #fafafa; }
    .stApp { background-color: #0e1117; }
    .stSidebar { background-color: #1a1d24; }
    .metric-card {
        background-color: #1a1d24;
        border: 1px solid #2d3139;
        border-radius: 8px;
        padding: 16px;
        text-align: center;
    }
    .status-approved { color: #00c853; font-weight: bold; }
    .status-flagged { color: #ffd600; font-weight: bold; }
    .status-failed { color: #ff1744; font-weight: bold; }
    table { width: 100%; border-collapse: collapse; }
    th { background-color: #1a1d24; color: #fafafa; padding: 8px; }
    td { padding: 8px; border-bottom: 1px solid #2d3139; }
</style>
"""
st.markdown(DARK_CSS, unsafe_allow_html=True)

PLOTLY_TEMPLATE = "plotly_dark"


def get_auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def fetch_token(base_url: str, username: str, password: str) -> str:
    response = requests.post(
        f"{base_url}/auth/token",
        data={"username": username, "password": password},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def color_status(val: str) -> str:
    colors = {
        "approved": "color: #00c853; font-weight: bold",
        "flagged": "color: #ffd600; font-weight: bold",
        "failed": "color: #ff1744; font-weight: bold",
        "validated": "color: #00c853",
        "enriched": "color: #29b6f6",
        "pending": "color: #9e9e9e",
    }
    return colors.get(val.lower(), "")


with st.sidebar:
    st.title("Healthcare Provider Validator")
    st.divider()

    base_url = st.text_input("API Base URL", value="http://localhost:8001")
    username = st.text_input("Username", value="")
    password = st.text_input("Password", type="password", value="")
    login_btn = st.button("Login", use_container_width=True)
    st.divider()
    groq_key = st.text_input(
        "Groq API Key (optional)",
        type="password",
        help="Used only for this session to enable LLM enrichment. Never stored.",
    )

    if login_btn:
        if not username or not password:
            st.error("Enter username and password.")
        else:
            try:
                token = fetch_token(base_url, username, password)
                st.session_state["token"] = token
                st.session_state["base_url"] = base_url
                st.session_state["groq_key"] = groq_key
                st.success("Logged in successfully.")
            except Exception as exc:
                st.error(f"Login failed: {exc}")

if "token" not in st.session_state:
    st.info("Please log in using the sidebar to get started.")
    st.stop()

token = st.session_state["token"]
base_url = st.session_state.get("base_url", "http://localhost:8001")
headers = get_auth_headers(token)

tab_validate, tab_directory, tab_analytics, tab_audit = st.tabs(
    ["Validate Providers", "Provider Directory", "Analytics", "Audit Log"]
)

with tab_validate:
    st.header("Validate Provider Batch")

    uploaded = st.file_uploader("Upload CSV (max 50 providers per batch)", type=["csv"])

    if uploaded is not None:
        try:
            df = pd.read_csv(uploaded)
            required_cols = {"npi", "name", "specialty", "phone", "address", "city", "state", "zip_code"}
            missing_cols = required_cols - set(df.columns)
            if missing_cols:
                st.error(f"CSV missing columns: {missing_cols}")
            else:
                st.subheader("Preview")
                st.dataframe(df.head(10), use_container_width=True)
                st.caption(f"{len(df)} records loaded. First 50 will be submitted.")

                if st.button("Run Validation", type="primary"):
                    batch = df.head(50).fillna("").to_dict(orient="records")
                    providers_payload = []
                    for row in batch:
                        row["npi"] = str(row.get("npi", "")).strip().split(".")[0].zfill(10) if row.get("npi") else ""
                        row["zip_code"] = str(row.get("zip_code", "")).strip().split(".")[0]
                        providers_payload.append(row)

                    with st.spinner("Running multi-agent validation..."):
                        try:
                            validate_headers = dict(headers)
                            session_groq_key = st.session_state.get("groq_key", "")
                            if session_groq_key:
                                validate_headers["X-Groq-Key"] = session_groq_key
                            resp = requests.post(
                                f"{base_url}/api/v1/validate",
                                json={"providers": providers_payload},
                                headers=validate_headers,
                                timeout=180,
                            )
                            resp.raise_for_status()
                            result = resp.json()

                            c1, c2, c3, c4 = st.columns(4)
                            c1.metric("Total", result["total"])
                            c2.metric("Approved", result["approved"])
                            c3.metric("Flagged", result["flagged"])
                            c4.metric("Failed", result["failed"])

                            st.caption(
                                f"Processing time: {result['processing_time_seconds']:.2f}s | "
                                f"Batch ID: {result['batch_id']}"
                            )

                            rows = []
                            for r in result["results"]:
                                rows.append({
                                    "NPI": r.get("npi", ""),
                                    "Name": r.get("name", ""),
                                    "Status": r.get("final_status", ""),
                                    "Confidence": f"{r.get('confidence_score', 0):.0%}",
                                    "Error": r.get("error") or "",
                                })
                            results_df = pd.DataFrame(rows)
                            st.subheader("Results")
                            st.dataframe(
                                results_df.style.applymap(
                                    color_status, subset=["Status"]
                                ),
                                use_container_width=True,
                            )
                        except requests.HTTPError as exc:
                            st.error(f"API error: {exc.response.text}")
                        except Exception as exc:
                            st.error(f"Validation failed: {exc}")
        except Exception as exc:
            st.error(f"Failed to parse CSV: {exc}")


with tab_directory:
    st.header("Provider Directory")

    status_options = ["all", "pending", "validated", "enriched", "failed"]
    col1, col2 = st.columns([1, 3])
    with col1:
        status_filter = st.selectbox("Filter by status", status_options)
    with col2:
        page = st.number_input("Page", min_value=1, value=1, step=1)

    params: dict = {"page": page, "size": 20}
    if status_filter != "all":
        params["status"] = status_filter

    try:
        resp = requests.get(
            f"{base_url}/api/v1/providers",
            headers=headers,
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        st.caption(f"Total providers: {data['total']} | Page {data['page']}")
        if data["items"]:
            df = pd.DataFrame(data["items"])
            display_cols = ["npi", "name", "specialty", "city", "state", "status", "created_at"]
            display_cols = [c for c in display_cols if c in df.columns]
            st.dataframe(
                df[display_cols].style.applymap(color_status, subset=["status"]),
                use_container_width=True,
            )
        else:
            st.info("No providers found.")
    except Exception as exc:
        st.error(f"Failed to load providers: {exc}")


with tab_analytics:
    st.header("Analytics")

    try:
        resp = requests.get(
            f"{base_url}/api/v1/stats",
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        stats = resp.json()

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Providers", stats["total_providers"])
        c2.metric("Approval Rate", f"{stats['approval_rate']:.0%}")
        c3.metric("Avg Confidence", f"{stats['average_confidence_score']:.0%}")

        col_left, col_right = st.columns(2)

        with col_left:
            status_data = stats.get("providers_by_status", {})
            if status_data:
                fig = px.pie(
                    names=list(status_data.keys()),
                    values=list(status_data.values()),
                    title="Providers by Status",
                    template=PLOTLY_TEMPLATE,
                    color=list(status_data.keys()),
                    color_discrete_map={
                        "validated": "#00c853",
                        "enriched": "#29b6f6",
                        "failed": "#ff1744",
                        "pending": "#9e9e9e",
                    },
                )
                st.plotly_chart(fig, use_container_width=True)

        with col_right:
            specialty_data = stats.get("providers_by_specialty", {})
            if specialty_data:
                fig = px.bar(
                    x=list(specialty_data.values()),
                    y=list(specialty_data.keys()),
                    orientation="h",
                    title="Providers by Specialty",
                    template=PLOTLY_TEMPLATE,
                    labels={"x": "Count", "y": "Specialty"},
                )
                st.plotly_chart(fig, use_container_width=True)

    except Exception as exc:
        st.error(f"Failed to load statistics: {exc}")


with tab_audit:
    st.header("Audit Log")

    provider_id_input = st.text_input("Provider ID (UUID)")

    if st.button("Fetch Audit Log") and provider_id_input:
        provider_id_input = provider_id_input.strip()
        try:
            resp = requests.get(
                f"{base_url}/api/v1/audit/{provider_id_input}",
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            st.subheader(f"Audit trail for NPI {data.get('provider_npi', '')}")
            logs = data.get("audit_logs", [])
            if logs:
                for log in logs:
                    with st.expander(f"{log['action']} - {log['performed_at'][:19]}"):
                        st.json(log.get("details") or {})
            else:
                st.info("No audit logs found for this provider.")
        except requests.HTTPError as exc:
            st.error(f"API error: {exc.response.text}")
        except Exception as exc:
            st.error(f"Failed to fetch audit log: {exc}")
