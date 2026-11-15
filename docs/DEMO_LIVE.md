# Demo runtime LangGraph v0.3

Ngày cập nhật: 10/11/2026 (Asia/Saigon).
Bạn đã chọn API tương thích OpenAI và sẽ bổ sung URL/model/key sau.
Code live đã có; **chưa có kết quả nghiệm thu inference thật** trong lần bàn giao này.

## 1. Chuẩn bị một lần

Mở PowerShell trong dự án:

```powershell
Set-Location -LiteralPath 'C:\Users\Thanh\Downloads\xây dựng KLTN\KhoaLuanTotNghiep\ai-agent-pentest'
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
Copy-Item configs/live_model.example.yaml configs/live_model.local.yaml
```

Điền ba giá trị trong live_model.local.yaml:

- base_url: URL provider kết thúc bằng /v1.
- allowed_base_urls: chứa đúng URL đó; không để wildcard.
- model: model ID thật của tài khoản.

Giữ api_key_env=AGENT_PENTEST_LLM_API_KEY, require_api_key=true. Key được đặt ở
environment của terminal runtime, không ghi vào YAML và không dán vào chat.
Provider cần hỗ trợ GET /models, POST /chat/completions, response_format=json_object
và function tool calling. Mọi request tắt redirect/proxy và không tự retry.

Runtime token là một bí mật riêng (ít nhất 16 ký tự) do operator chọn; đặt cùng giá trị
AGENT_PENTEST_RUNTIME_TOKEN trong terminal runtime và terminal worker. Token này không
phải API key của provider. UI không cần provider key hoặc runtime token.

## 2. Terminal A — Target runtime

Sau khi đặt hai biến AGENT_PENTEST_RUNTIME_TOKEN và AGENT_PENTEST_LLM_API_KEY:

```powershell
.\.venv\Scripts\python.exe lab_runtime.py --model-config configs/live_model.local.yaml
```

Runtime lắng nghe 127.0.0.1:8765, dùng pinned source trong third_party/agents_from_scratch.
Email/calendar chỉ tạo effects trong bộ nhớ. Chưa cần Git checkout ngoài hoặc Gmail.
Chế độ local_repository cũng nhận một checkout có đúng các hash được cho phép;
đăng ký đường dẫn đó trong configs/registry_policy.yaml và chạy --source <đường-dẫn>.

## 3. Terminal B — Đăng ký và chạy worker

Đặt cùng AGENT_PENTEST_RUNTIME_TOKEN, cùng thư mục gốc/runtime với UI:

```powershell
.\.venv\Scripts\python.exe worker.py --init-db
.\.venv\Scripts\python.exe worker.py --register-target configs/registered_target.example.yaml
.\.venv\Scripts\python.exe worker.py --check-targets
.\.venv\Scripts\python.exe worker.py
```

Target mẫu có ID my-email-agent, graph email_assistant, profile baseline_no_hitl.
Nếu ID đã tồn tại, dùng UI Request connection check để kiểm tra lại. Muốn đổi graph
hoặc cấu hình kết nối, đăng ký ID mới để không sửa snapshot Campaign cũ.

READY chỉ được ghi sau handshake protocol/revision/hash/isolation/profile và kiểm tra
provider. Thiếu API config/key/model cho LIVE_BACKEND_UNAVAILABLE; không thể enqueue
target này như một target live sẵn sàng.

## 4. Terminal C — Streamlit

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Mở http://127.0.0.1:8501:

1. Trang Targets: xem my-email-agent, trạng thái READY, capabilities và surface.
2. Nếu chưa đăng ký CLI, điền form đăng ký; worker xử lý yêu cầu kiểm tra.
3. New Campaign: chọn my-email-agent, baseline_no_hitl và email_input.email_thread.
4. Chọn ASI01-EMAIL-001, Fixed, ngân sách và xác nhận authorized lab scope.
5. Start Campaign; Campaign Progress hiển thị dữ liệu SQLite và tiến độ Attempt.
6. Findings and Evidence: đọc classification, model prompt hash, graph transitions,
   proposal/call/effect, snapshots, verdict và utility.
7. Finding chỉ xuất hiện khi Oracle xác nhận OBSERVED; tải JSON/HTML để đối chiếu.

ASI01 không được ép thành công: model có thể ignore, respond, notify hoặc lỗi.
Theo evidence, kết quả có thể OBSERVED, NOT_OBSERVED hoặc INCONCLUSIVE.
Notify tương tác và nhiều tool call trong một lượt hiện chưa được hỗ trợ đầy đủ;
đường đó được báo lỗi quan sát, không tạo finding giả.

## 5. Demo không khai thác và so sánh

Tạo yêu cầu mới với BENIGN-EMAIL-001 để kiểm tra thư công việc hợp lệ. Kết quả âm tính
chỉ được xác nhận nếu quan sát hoàn tất. Nếu model không hoàn thành nhiệm vụ,
utility sẽ không được ép thành PASSED.

Để so sánh ASI02, đăng ký target ID khác trên cùng runtime:
graph_entrypoint=email_assistant_hitl, supported_profiles=[hitl_enabled].
Chạy ASI02-TOOL-001 ở hai target. test_bundle_hash giống nhau khi cùng TestSpec,
repetition và surface; bundle_hash cấu hình đầy đủ khác vì implementation/target khác.
HITL reject_external có thể ngăn người nhận ngoài allowlist, trong khi utility vẫn FAILED
nếu Alice chưa nhận được phản hồi.

Additional TestSpecs và Repetitions tạo nhiều Run/Attempt trong cùng Campaign.
Mỗi Attempt có reset/evidence riêng; Fixed không sửa payload theo kết quả trước.

## 6. ASI06

Đăng ký graph email_assistant_hitl_memory, profile hitl_memory, ID mới.
Chọn ASI06-MEM-001. Phải có persistent_memory/memory_update PRESENT.
Hai email dùng cùng Store trong một Attempt; reset chỉ xảy ra trước pha một.
Quan sát ignore → update_memory(full history) → Store delta → triage pha hai.
Model thật có thể từ chối poison; không giả định phải có OBSERVED.

## 7. Cancel và recovery

Cancel / Stop lưu yêu cầu vào SQLite. Worker kiểm tra trong vòng poll và tại guard;
runtime có thể dừng process chứa model đang chờ. Evidence thiếu sau kill cho INCONCLUSIVE.
Deadline runtime tối đa 180 giây mặc định; lease mất worker khoảng 15 giây cũng dừng child.

Nếu worker bị gián đoạn:

```powershell
.\.venv\Scripts\python.exe worker.py --recover-interrupted
```

Recovery không replay. Nó đối soát campaign với runtime instance cũ, dừng job,
giữ kết quả đã có và ghi INCONCLUSIVE cho Attempt còn thiếu kết quả. Khóa chỉ được
mở sau xác nhận dừng và export report. Runtime mất kết nối/đổi instance giữ
STOP_UNCONFIRMED; cần operator xác minh tiến trình cũ, không mở khóa theo thời gian.

## 8. LLM cho các vai trò pentest (tùy chọn)

Mặc định Planner/Testing Agent/Reviewer vẫn là Fixed. Điền configs/roles.example.yaml
thành một tệp .local.yaml riêng, dùng AGENT_PENTEST_ROLE_API_KEY trong worker, rồi:

```powershell
.\.venv\Scripts\python.exe worker.py --enqueue baseline_no_hitl --target my-email-agent --testspec ASI01-EMAIL-001 --request-key role-demo-1 --roles-config configs/roles.local.yaml
```

Role output có Pydantic schema; Planner không mở rộng target/plan, Testing Agent vẫn
phải giữ approved Fixed payload, Reviewer không đổi Oracle verdict. Fallback chỉ diễn ra
khi cấu hình rõ fallback=fixed và được ghi role_audit. Target LLM không sử dụng cấu hình
role này. Lời gọi role trong worker có request timeout nhưng chưa có process kill riêng.

## 9. Kiểm tra tự động và live opt-in

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
# Chỉ bật khi đã điền cấu hình thật và cấp quyền gọi API:
$env:AGENT_PENTEST_RUN_LIVE = (Resolve-Path configs/live_model.local.yaml).Path
.\.venv\Scripts\python.exe -m pytest tests/test_live_runtime.py -k opt_in_real_llm -q
```

Bài opt-in chạy cả runtime/graph/worker/Oracle với API thật và không ép verdict dương.
Không có biến opt-in thì bài này SKIPPED, không được ghi là live pass.
