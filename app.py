"""Streamlit submits commands and reads SQLite; never executes a Campaign."""
from datetime import datetime, timezone
from uuid import uuid4

import streamlit as st

from agent_pentest.control.catalogue import Catalogue
from agent_pentest.evidence.store import EvidenceStore
from agent_pentest.service import project_root, runtime_path, submit_campaign
from agent_pentest.storage.database import Database

st.set_page_config(page_title="AI Agent Pentest | SIMULATION", page_icon="🧪", layout="wide")
st.title("AI Agent Pentest")
st.warning("SIMULATION — Fake HMA chạy theo quy tắc cố định. Kết quả không chứng minh khai thác AI Agent thật.")

root = project_root()
db = Database(runtime_path(root))
db.initialize()
catalogue = Catalogue(root)
targets, tests = catalogue.targets(), catalogue.tests()

# URL request token survives a browser refresh and is protected by UNIQUE(request_key) in SQLite.
if "request" not in st.query_params:
    st.query_params["request"] = str(uuid4())
request_key = str(st.query_params["request"])

with st.sidebar:
    st.header("Tạo Campaign")
    with st.form("campaign_form"):
        target_id = st.selectbox("Target", list(targets), key="target")
        profile = st.selectbox("Profile", ["vulnerable", "protected"], key="profile")
        test_id = st.selectbox("TestSpec", list(tests), key="testspec")
        submitted = st.form_submit_button("Start Campaign")
    if submitted:
        try:
            campaign_id, created = submit_campaign(db, catalogue, target_id, profile, test_id, request_key)
            st.session_state["selected_campaign"] = campaign_id
            st.success("Đã đưa vào hàng đợi." if created else "Yêu cầu này đã tồn tại; mở lại Campaign.")
        except (ValueError, KeyError):
            st.error("Khóa yêu cầu đã gắn với cấu hình khác hoặc cấu hình không hợp lệ. Chọn Tạo yêu cầu mới để chạy lần khác.")
    if st.button("Tạo yêu cầu mới", key="new_request"):
        st.query_params["request"] = str(uuid4())
        st.rerun()
    st.caption("Start Campaign gửi lại cùng yêu cầu sẽ không tạo hoặc thực thi trùng.")
    st.json(catalogue.scope().model_dump(mode="json"), expanded=False)


@st.fragment(run_every="2s")
def campaign_view():
    heartbeat = db.last_heartbeat()
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(heartbeat)).total_seconds() if heartbeat else float("inf")
    if age < 15:
        st.caption("Worker: nhận heartbeat gần đây")
    else:
        st.info("Chưa nhận heartbeat gần đây. Chạy worker.py trong một terminal riêng.")
    campaigns = db.list_campaigns()
    if not campaigns:
        st.info("Chọn cấu hình bên trái và nhấn Start Campaign.")
        return
    ids = [c["id"] for c in campaigns]
    wanted = st.session_state.get("selected_campaign", ids[0])
    campaign_id = st.selectbox("Campaign", ids, index=ids.index(wanted) if wanted in ids else 0,
        format_func=lambda value: f"{value[:8]} · {next(c['status'] for c in campaigns if c['id'] == value)}")
    detail = db.detail(campaign_id)
    st.subheader(f"Campaign {campaign_id[:8]}")
    a, b, c = st.columns(3)
    a.metric("Trạng thái", detail["status"])
    b.metric("Profile", detail["campaign"]["profile"])
    c.metric("Bước", detail["stage"])
    if detail["error"]:
        st.error(detail["error"])
    result_tab, execution_tab, evidence_tab, report_tab = st.tabs(["Verdict / Finding", "Run / Attempt", "Evidence", "Báo cáo"])
    with result_tab:
        for entry in detail["results"]:
            result = entry["data"]
            st.write(f"Security: **{result['security_verdict']}** · Execution: **{result['execution_status']}** · Utility: **{result['utility_result']}**")
            st.write(result["reason"])
            st.json(result, expanded=False)
        for entry in detail["findings"]:
            st.json(entry["data"])
        if not detail["findings"]:
            st.caption("Chưa có finding được chứng minh bằng evidence hợp lệ.")
    with execution_tab:
        st.json({"runs": detail["runs"], "attempts": detail["attempts"]})
        st.dataframe(detail["audit"], width="stretch")
    with evidence_tab:
        for entry in detail["attempts"]:
            bundle = EvidenceStore(db.runtime).read(entry["id"])
            st.caption(f"{entry['id']} — {bundle.reason}")
            st.json([event.model_dump(mode="json") for event in bundle.events], expanded=False)
    with report_tab:
        st.caption("Báo cáo luôn ghi rõ SIMULATION; utility chưa bao gồm phép thử đối chứng riêng.")
        for kind, mime in (("json", "application/json"), ("html", "text/html")):
            relative = detail[f"report_{kind}"]
            if relative:
                path = (db.runtime / relative).resolve()
                if path.is_relative_to(db.runtime) and path.is_file():
                    st.download_button(f"Download {kind.upper()}", path.read_bytes(),
                                       f"simulation-{campaign_id}.{kind}", mime=mime,
                                       key=f"download-{kind}-{campaign_id}")


campaign_view()

