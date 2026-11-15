"""Streamlit submits commands and reads SQLite; never executes a Campaign."""
from datetime import datetime, timezone
from uuid import uuid4

import streamlit as st

from agent_pentest.control.catalogue import Catalogue, applicability
from agent_pentest.control.registry import register_target, registered_config, PROFILE_GRAPHS
from agent_pentest.models.schemas import RegisteredTarget, CapabilityRecord
from agent_pentest.evidence.store import EvidenceStore
from agent_pentest.service import project_root, runtime_path, submit_campaign
from agent_pentest.storage.database import Database

st.set_page_config(page_title="AI Agent Pentest", page_icon="🧪", layout="wide")
st.title("AI Agent Pentest")
st.caption("Chế độ bằng chứng: SIMULATION · INTEGRATION_TEST · LIVE_LLM_LAB. Email/calendar luôn nằm trong sandbox.")

root = project_root()
db = Database(runtime_path(root))
db.initialize()
catalogue = Catalogue(root)
targets, tests = catalogue.targets(), catalogue.tests()
registrations = {r["id"]: r for r in db.registry_entries()}
for rid, registration in registrations.items():
    if registration["status"] == "READY":
        targets[rid] = registered_config(db, rid)
page = st.radio("Trang", ["New Campaign", "Targets", "Campaign Progress", "Findings and Evidence"], horizontal=True, key="page")

if page == "Targets":
    st.subheader("Targets — Đăng ký lab")
    st.caption("Chỉ nhận runtime lab protocol đã kiểm tra; repository URL là provenance, không phải attack endpoint.")
    with st.form("register_target"):
        rid = st.text_input("Target ID", "my-email-agent")
        name = st.text_input("Target name", "Email Agent — LangGraph")
        connection = st.selectbox("Connection mode", ["local_endpoint", "local_repository"])
        endpoint = st.text_input("Runtime endpoint", "http://127.0.0.1:8765")
        local_path = st.text_input("Approved local checkout", str(root / "third_party/agents_from_scratch"))
        selected_profile = st.selectbox("Graph profile", list(PROFILE_GRAPHS))
        st.text_input("Source repository", "https://github.com/langchain-ai/agents-from-scratch", disabled=True)
        registered = st.form_submit_button("Register and request check")
    if registered:
        try:
            reg = RegisteredTarget(target_id=rid, target_name=name, endpoint=endpoint, runtime_mode=connection,
                local_project_path=local_path if connection == "local_repository" else None,
                graph_entrypoint=PROFILE_GRAPHS[selected_profile], supported_profiles=(selected_profile,))
            register_target(db, root, reg)
            st.success("Đã lưu yêu cầu kiểm tra. Worker sẽ kết nối và ghi kết quả.")
        except (ValueError, OSError):
            st.error("Target không hợp lệ, trùng ID hoặc nằm ngoài allowlist. Kiểm tra cấu hình lab.")
    for row in db.registry_entries():
        st.write(f"**{row['id']}** · {row['status']}")
        if row["error"]:
            st.warning(row["error"])
        st.json({"registration": row["data"], "capabilities": row["capabilities"]}, expanded=False)
        if st.button("Request connection check", key="check-" + row["id"]):
            db.request_registry_check(row["id"])
            st.info("Đã gửi yêu cầu kiểm tra lại cho worker.")

# URL request token survives a browser refresh and is protected by UNIQUE(request_key) in SQLite.
if "request" not in st.query_params:
    st.query_params["request"] = str(uuid4())
request_key = str(st.query_params["request"])

with st.sidebar:
    st.header("Tạo Campaign")
    # Target must rerun immediately so dependent profile choices update before submit.
    target_id = st.selectbox("Target", list(targets), key="target")
    profiles = [p.value for p in targets[target_id].profiles]
    if st.session_state.get("profile") not in profiles:
        st.session_state["profile"] = profiles[0]
    compatible = [key for key, spec in tests.items()
                  if (spec.email_input is not None) == (targets[target_id].adapter != "fake_hma")]
    st.caption("Evidence mode: " + targets[target_id].mode)
    with st.form("campaign_form"):
        profile = st.selectbox("Profile", profiles, key="profile")
        test_id = st.selectbox("TestSpec", compatible, key="testspec")
        extra_tests = st.multiselect("Additional TestSpecs", compatible, key="extra_tests")
        paired = st.checkbox("Chạy đối chứng sạch / payload", key="paired", help="Tự thêm control_id; reset riêng từng Attempt. Hỗ trợ ASI01 và ASI02 đã khai báo đối chứng.")
        repetitions = st.number_input("Repetitions", 1, 10, 1)
        attack_surface = st.selectbox("Attack surface", ["email_input.email_thread"])
        st.selectbox("Execution mode", ["Fixed"], disabled=True)
        st.caption("Exploratory chưa hỗ trợ: payload Fixed không thay đổi theo kết quả.")
        timeout = st.number_input("Timeout per Attempt (seconds)", 1, 600, 120 if targets[target_id].registration else 10)
        budget = st.number_input("Max operations per Attempt", 1, 100, 12)
        authorized = st.checkbox("Tôi xác nhận target thuộc lab được phép kiểm thử.", value=targets[target_id].registration is None)
        submitted = st.form_submit_button("Start Campaign")
    if submitted:
        try:
            if not authorized:
                raise ValueError("Authorized lab scope must be confirmed.")
            selection = tuple(dict.fromkeys([test_id, *extra_tests]))
            if target_id in registrations:
                cap = CapabilityRecord.model_validate(registrations[target_id]["capabilities"][profile])
                if any(applicability(tests[sid], cap)[0] != "APPLICABLE" for sid in selection):
                    raise ValueError("Selection includes unsupported or unknown capabilities.")
            if paired:
                from agent_pentest.control.pairing import expand_controls
                expanded = expand_controls(tuple(tests[sid] for sid in selection), tests)
                if target_id in registrations and any(applicability(spec, cap)[0] != "APPLICABLE" for spec in expanded):
                    raise ValueError("A clean control is unsupported by this target.")
            campaign_id, created = submit_campaign(db, catalogue, target_id, profile, test_id, request_key,
                test_ids=selection if extra_tests else (), repetitions=repetitions, attack_surface=attack_surface,
                timeout_seconds=timeout, max_operations=budget, paired=paired)
            st.session_state["selected_campaign"] = campaign_id
            st.session_state["campaign_picker"] = campaign_id
            st.success("Đã đưa vào hàng đợi." if created else "Yêu cầu này đã tồn tại; mở lại Campaign.")
        except (ValueError, KeyError):
            st.error("Yêu cầu trùng hoặc cấu hình không hợp lệ. Đối chứng cần ASI01/ASI02 có control_id, không chọn ca sạch không liên quan. Chọn Tạo yêu cầu mới để chạy lần khác.")
    if st.button("Tạo yêu cầu mới", key="new_request"):
        st.query_params["request"] = str(uuid4())
        st.rerun()
    st.caption("Start Campaign gửi lại cùng yêu cầu sẽ không tạo hoặc thực thi trùng.")
    st.json(catalogue.scope().model_dump(mode="json"), expanded=False)
    if target_id in registrations:
        cap = CapabilityRecord.model_validate(registrations[target_id]["capabilities"][st.session_state["profile"]])
        st.write("Verified attack surfaces", cap.attack_surfaces)
        st.dataframe([{"TestSpec": sid, "Applicability": applicability(tests[sid], cap)[0]} for sid in compatible])


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
    if st.session_state.get("campaign_picker") not in ids:
        st.session_state["campaign_picker"] = wanted if wanted in ids else ids[0]
    campaign_id = st.selectbox("Campaign", ids, index=ids.index(wanted) if wanted in ids else 0,
        key="campaign_picker",
        format_func=lambda value: f"{value[:8]} · {next(c['status'] for c in campaigns if c['id'] == value)}")
    st.session_state["selected_campaign"] = campaign_id
    detail = db.detail(campaign_id)
    st.subheader(f"Campaign {campaign_id[:8]}")
    a, b, c = st.columns(3)
    a.metric("Trạng thái", detail["status"])
    b.metric("Profile", detail["campaign"]["profile"])
    c.metric("Bước", detail["stage"])
    if detail["error"]:
        st.error(detail["error"])
    st.caption("Evidence mode: " + detail["campaign"]["mode"])
    elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(detail["campaign"]["created_at"])).total_seconds()
    st.caption(f"Thời gian từ enqueue: {elapsed:.1f}s · Cancel requested: {db.cancelled(campaign_id)}")
    if detail["status"] in ("PENDING", "RUNNING"):
        if st.button("Cancel / Stop", key="cancel-" + campaign_id):
            db.request_cancel(campaign_id)
            st.info("Đã lưu yêu cầu dừng. Worker sẽ xác nhận trạng thái stop.")
    for entry in detail["attempts"]:
        progress = db.live_progress(entry["id"])
        if progress:
            st.json({"attempt_id": entry["id"], **progress}, expanded=False)
    result_tab, execution_tab, evidence_tab, report_tab, comparison_tab = st.tabs(["Verdict / Finding", "Run / Attempt", "Evidence", "Báo cáo", "Đối chứng sạch / payload"])
    with comparison_tab:
        if not detail["campaign"].get("paired"):
            st.info("Campaign này chưa bật đối chứng. Tạo yêu cầu mới, chọn ASI01/ASI02 và bật Chạy đối chứng sạch / payload.")
        else:
            from agent_pentest.evidence.comparison import compare_campaign
            comparison = compare_campaign(detail, db.runtime)
            st.json(comparison["summary"])
            st.caption("Baseline = agent đã xử lý email sạch; state_before chỉ là snapshot sau reset. Không suy ra nhân quả từ một cặp LLM ngẫu nhiên.")
            for pair in comparison["pairs"]:
                st.write(f"{pair['control_id']} → {pair['attack_id']} · lần {pair['repetition']} · **{pair['status']}**")
                st.write(pair.get("reason", ""))
                st.code(pair.get("input_diff", ""), language="diff")
                left, right = st.columns(2)
                for column, side, label in ((left, "control", "Email sạch"), (right, "attack", "Có payload")):
                    arm = pair.get(side, {})
                    column.write(label)
                    column.json({k: arm.get(k) for k in ("attempt_id", "security", "utility", "execution", "final_state", "evidence_ref")}, expanded=True)
                    with column.expander("Trace: proposal → call → effect"):
                        st.json(arm.get("trace", []))
                st.write("Khác biệt hành động đầu tiên (không tự đồng nghĩa với khai thác):")
                st.json(pair.get("first_behavior_difference"))
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
            store = EvidenceStore(db.runtime)
            if entry["status"] == "RUNNING" and not (store.directory(entry["id"]) / "events.jsonl").exists():
                st.info(f"{entry['id']} — Đang chờ thu thập bằng chứng.")
                continue
            bundle = store.read(entry["id"])
            st.caption(f"{entry['id']} — {bundle.reason}")
            st.json([event.model_dump(mode="json") for event in bundle.events], expanded=False)
            st.dataframe([{"sequence": e.sequence, "kind": e.kind, "operation_id": e.operation_id,
                           "phase": e.data.get("phase")} for e in bundle.events])
            before, after = st.columns(2)
            before.write("State before")
            before.json(next((e.data for e in bundle.events if e.kind == "state_before"), {}), expanded=False)
            after.write("State after")
            after.json(next((e.data for e in bundle.events if e.kind == "state_after"), {}), expanded=False)
    with report_tab:
        st.caption("Báo cáo ghi rõ mode/backend, source revision và evidence. BENIGN cung cấp phép thử đối chứng.")
        for kind, mime in (("json", "application/json"), ("html", "text/html")):
            relative = detail[f"report_{kind}"]
            if relative:
                path = (db.runtime / relative).resolve()
                if path.is_relative_to(db.runtime) and path.is_file():
                    st.download_button(f"Download {kind.upper()}", path.read_bytes(),
                                       f"{detail['campaign']['mode'].lower()}-{campaign_id}.{kind}", mime=mime,
                                       key=f"download-{kind}-{campaign_id}")


campaign_view()

