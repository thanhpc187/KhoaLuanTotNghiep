# Agent Pentest Framework — v0.3.1

Đợt 12/11/2026 nâng cấp riêng nhánh `write_email` của runtime: kiểm tra/binding args,
ID do wrapper cấp, đối soát permit worker, receipt sandbox, chống lặp/uncertain replay.
Thêm BENIGN-REPLY-001 cùng ASI02-TOOL-002/003 để chạy ca sạch và hai biến thể cùng nhiệm vụ.
Xem [nghiên cứu Execution Plane và roadmap](docs/EXECUTION_RESEARCH.md).
Multi-tool mỗi lượt, calendar và memory chưa được nâng cấp trong đợt này.

Framework kiểm thử AI Agent trong lab, giữ kiến trúc **Control / Execution / Evidence Plane**.
v0.3 bổ sung đăng ký target, kết nối runtime LangGraph riêng, discovery có bằng chứng,
nhiều TestSpec/Run/Attempt, cancel và backend API tương thích chat.

**Đường live đã được triển khai nhưng chưa nghiệm thu bằng tài khoản LLM thật.**
Bạn sẽ bổ sung URL/model/key sau. Test live opt-in được SKIPPED khi thiếu cấu hình;
không có fallback ngầm sang model quy tắc.

- [Hướng dẫn demo và lệnh khởi động chính xác](docs/DEMO_LIVE.md)
- [Kiến trúc và trách nhiệm các tệp](docs/ARCHITECTURE.md)
- [Đánh giá khoảng trống trước nâng cấp](docs/UPGRADE_ASSESSMENT.md)
- [Source revision, instrumentation và giới hạn upstream](docs/LIVE_PROVENANCE.md)
- [Kết quả kiểm thử thực tế](TEST_RESULTS.md)
- [Danh sách tệp](FILES.txt)

## Ba chế độ bằng chứng

| Mode | Agent decisions | Graph / tools |
| --- | --- | --- |
| SIMULATION | FakeHMA hoặc LabRuleBackedEmailModel | Baseline v0.2, effects trong bộ nhớ |
| INTEGRATION_TEST | Output model kiểm soát, khai báo rõ | Node upstream thật qua runtime/process/permits; không phải LLM proof |
| LIVE_LLM_LAB | API model do operator cấu hình | Node upstream đã khóa hash; effects email/calendar vẫn sandbox |

Finding không được tạo chỉ vì gửi payload. Oracle đối chiếu trace, tool call, state
delta và snapshot; kết quả có thể OBSERVED, NOT_OBSERVED, INCONCLUSIVE hoặc NOT_APPLICABLE.
Utility và execution status được giữ độc lập.

## Cài đặt

Windows/Python 3.12.14 là môi trường đã kiểm tra. Khai báo Python 3.11–3.13 chưa có
nghiệm thu đa nền tảng. Chạy trong thư mục chứa app.py:

```powershell
$env:PYTHONUTF8 = '1'
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe worker.py --init-db
```

requirements-lock.txt vẫn là snapshot dependency đã dùng; không cần cài provider SDK
mới cho đường compatible-chat. Cài package cần Internet; suite offline không gọi API.
.env không tự được nạp.

## Chạy baseline hiện có

Terminal worker và UI riêng:

```powershell
.\.venv\Scripts\python.exe worker.py
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Hai lệnh trên chạy ở hai terminal. Mở http://127.0.0.1:8501. FakeHMA và target
langchain-email-assistant offline vẫn có sẵn, không cần registry hoặc credentials.

CLI cũ giữ nguyên:

```powershell
.\.venv\Scripts\python.exe worker.py --enqueue vulnerable --request-key baseline-1
.\.venv\Scripts\python.exe worker.py --once
```

Fake vulnerable cho OBSERVED/PASSED, protected cho NOT_OBSERVED/PASSED trong regression.
Bốn TestSpec email offline BENIGN/ASI01/ASI02/ASI06 vẫn hoạt động như v0.2.

## Chạy target live

1. Điền configs/live_model.local.yaml theo mẫu live_model.example.yaml.
2. Đặt API key vào AGENT_PENTEST_LLM_API_KEY ở terminal runtime.
3. Đặt cùng AGENT_PENTEST_RUNTIME_TOKEN (ít nhất 16 ký tự) ở runtime và worker.
4. Khởi động runtime, đăng ký target, kiểm tra compatibility, rồi chạy worker/UI.

```powershell
# Terminal A
.\.venv\Scripts\python.exe lab_runtime.py --model-config configs/live_model.local.yaml

# Terminal B
.\.venv\Scripts\python.exe worker.py --register-target configs/registered_target.example.yaml
.\.venv\Scripts\python.exe worker.py --check-targets
.\.venv\Scripts\python.exe worker.py

# Terminal C
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Đọc [DEMO_LIVE.md](docs/DEMO_LIVE.md) trước khi demo: cấu hình mẫu còn placeholder,
chưa phải provider đã kết nối. API cần hỗ trợ /models, /chat/completions, JSON output
và function tool calling. Provider lỗi/thiếu key/model báo LIVE_BACKEND_UNAVAILABLE.

Target Registry hỗ trợ local_endpoint hoặc local_repository. Cả hai kết nối tới
runtime lab protocol; với repository, worker kiểm tra thêm checkout/hash và runtime
đang dùng đúng đường dẫn. Không import arbitrary source hoặc xem URL GitHub như endpoint.

## Giao diện

- **Targets:** đăng ký, gửi yêu cầu check, xem trạng thái/provenance/capabilities.
- **New Campaign:** target/profile/surface, TestSpec chính và bổ sung, repetition,
  budget/deadline, xác nhận lab scope.
- **Campaign Progress:** trạng thái SQLite, Run/Attempt, graph node/phase, operation count,
  thời gian từ enqueue và Cancel / Stop.
- **Findings and Evidence:** verdict/utility, timeline, proposal/call/effect, before/after,
  finding/remediation và JSON/HTML.

Streamlit không chạy target hoặc gọi model. Worker xử lý check/execute/cancel; UI chỉ
ghi yêu cầu và đọc trạng thái. Profile và danh sách khả năng áp dụng dựa trên target
đã chọn. UNKNOWN không được coi là NOT_APPLICABLE. Exploratory bị vô hiệu hóa có lý do.

## Fixed multi-run

```powershell
.\.venv\Scripts\python.exe worker.py --enqueue baseline_no_hitl --target my-email-agent --testspecs ASI01-EMAIL-001 ASI02-TOOL-001 --repetitions 2 --request-key fixed-batch-1
```

Campaign khóa toàn bộ TestSpec/config. Mỗi TestSpec/lần lặp có Run/Attempt/reset_id/
evidence riêng; không adaptive retry. ASI06 giữ Store giữa hai pha trong một Attempt.
test_bundle_hash dùng đối chiếu workload giữa profile; bundle_hash còn ràng buộc
target/connection/config, vì vậy có thể khác khi đổi implementation đã đăng ký.

Planner/Testing Agent/Reviewer mặc định Fixed. Có backend LLM riêng qua --roles-config,
schema validation, prompt/config hash và fallback được ghi audit. Không vai trò nào
được trực tiếp gọi target; Reviewer không đổi verdict. Xem mẫu roles.example.yaml.

## Safety và recovery

Scope giữ allowlist action, profile, budget và deadline. Runtime endpoint chỉ nhận
numeric loopback HTTP origin có trong registry_policy.yaml, tắt redirect/proxy.
Provider HTTPS có allowlist URL riêng; token runtime tách khỏi API key.

Mỗi mutation chờ permit một lần từ worker. Target child không được cấp Database hoặc
EvidenceStore. Runtime theo dõi lease và có thể terminate/kill child khi model bị chặn.
Không xác nhận stop được thì giữ target lock. Recovery đối soát instance/campaign,
không replay operation không chắc chắn, chỉ release sau khi report thành công.

```powershell
.\.venv\Scripts\python.exe worker.py --recover-interrupted
```

SQLite v0.1/v0.2 tương thích qua migration bổ sung; dữ liệu/evidence/report trước đó
được giữ nguyên. Evidence không ghi đè; report export lại có revision.
AGENT_PENTEST_ROOT ưu tiên hơn cwd hợp lệ, rồi package fallback.
AGENT_PENTEST_RUNTIME phải đồng nhất giữa worker/UI.

## Kiểm thử và giới hạn

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
```

Xem TEST_RESULTS.md cho số liệu cuối. Sample v0.1/v0.2 được giữ nguyên;
[sample v0.3](sample-results/v0.3/README.md) ghi rõ INTEGRATION_TEST và có cả kết quả
dương lẫn âm từ các process runtime/worker CLI riêng.

Chưa hỗ trợ Gmail/SMTP/calendar thật, arbitrary LangGraph server, Exploratory, nhiều
tool proposal trong một lượt, notify tương tác đầy đủ, sandbox OS cho code độc hại
hoặc benchmark ASR. HITL là chính sách accept/ignore tự động. Role LLM dùng request
timeout nhưng chưa có process kill riêng. Runtime restart đổi instance có thể cần
operator xác minh STOP_UNCONFIRMED; không tự mở khóa theo thời gian.
