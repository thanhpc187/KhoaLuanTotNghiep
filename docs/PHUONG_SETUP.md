# Chạy nhánh phuong trên máy Thanh

Kiểm tra ngày 15/11/2026. Đã fetch origin/phuong, checkout nhánh local phuong
tracking origin/phuong tại commit 28f2512. Chưa merge vào main hoặc push bản sửa.

## Phần nhận từ Phương

- upstream/agents-from-scratch: bản nguồn đầy đủ ở revision 603fc7a4ac6119004f43894395e504a1fefcc6c0.
- Allowlist bổ sung đường dẫn nguồn trên.
- CompatibleChatModel hỗ trợ trường thinking tùy chọn.
- Không có cấu hình provider cá nhân/API key hoặc database Campaign lỗi được push.

Bản nguồn được chạy qua wrapper lab của framework. Không cần cài package upstream,
chạy langgraph dev hay bật Gmail để kết nối framework. Server LangGraph thông thường
không cung cấp protocol riêng của adapter này.

## Sửa tương thích Windows

core.autocrlf=true làm 9 file trong manifest của checkout mới bị đổi sang CRLF,
khiến verify_source báo Source differs from the pinned, reviewed revision.
Đã phục hồi đúng byte từ Git, đối chiếu SHA-256 với manifest, thêm .gitattributes
để giữ LF cho source được khóa. Không sửa thuật toán xác minh hay manifest.
Đây là lỗi tái hiện trên máy Thanh; chưa đủ bằng chứng khẳng định cùng nguyên nhân
với ảnh lỗi discover_capabilities: ValueError trên máy Phương.

## 1. Cấu hình model

Đã tạo configs/phuong_model.local.yaml và configs/phuong_target.local.yaml (Git ignore).
Mở phuong_model.local.yaml, thay base_url và allowed_base_urls bằng cùng URL API,
thay model bằng model ID thật. Giữ api_key_env: AGENT_PENTEST_LLM_API_KEY.
Không ghi API key vào YAML. .env không tự được framework nạp.

Trường thinking là tùy chọn của provider: chỉ bỏ comment thinking: disabled nếu
provider/model đang dùng hỗ trợ và cần cấu hình này. Không tự thêm vào mọi API.
Backend cần GET /models, POST /chat/completions, JSON output và function tool calling.

## 2. Terminal A: target runtime

Dừng runtime cũ trước khi chạy; giữ một runtime ở cổng 8765.

```powershell
Set-Location -LiteralPath 'C:\Users\Thanh\Downloads\xây dựng KLTN\KhoaLuanTotNghiep\ai-agent-pentest'
$env:PYTHONUTF8 = '1'
$env:AGENT_PENTEST_RUNTIME_TOKEN = Read-Host 'Nhap token lab tu chon, it nhat 16 ky tu; dung lai o Terminal B'
$phuongKey = Read-Host 'API key cua provider' -AsSecureString
$env:AGENT_PENTEST_LLM_API_KEY = ([System.Net.NetworkCredential]::new('', $phuongKey)).Password
Remove-Variable phuongKey
.\.venv\Scripts\python.exe lab_runtime.py --source upstream/agents-from-scratch --model-config configs/phuong_model.local.yaml
```

Giữ terminal này mở. Không khởi động lại runtime giữa connection check và Campaign.
Runtime khởi động chưa chứng minh provider sẵn sàng; cần bước check phía worker.

## 3. Terminal B: đăng ký và worker

Dừng worker cũ để tránh hai worker cùng thư mục runtime.

```powershell
Set-Location -LiteralPath 'C:\Users\Thanh\Downloads\xây dựng KLTN\KhoaLuanTotNghiep\ai-agent-pentest'
$env:PYTHONUTF8 = '1'
$env:AGENT_PENTEST_RUNTIME_TOKEN = Read-Host 'Nhap DUNG token lab da dung o Terminal A'
.\.venv\Scripts\python.exe worker.py --register-target configs/phuong_target.local.yaml
.\.venv\Scripts\python.exe worker.py --check-targets
.\.venv\Scripts\python.exe worker.py
```

Register chỉ chạy một lần cho ID phuong-email-local. Nếu ID đã có, bỏ lệnh register,
vào UI Targets > Request connection check cho ID này. Worker xử lý yêu cầu đó.
Nếu báo interrupted, chỉ khi worker cũ đã dừng, chạy worker.py --recover-interrupted;
giữ runtime còn hoạt động để đối soát. Không xóa khóa/SQLite để bỏ qua lỗi.

## 4. Terminal C: UI

```powershell
Set-Location -LiteralPath 'C:\Users\Thanh\Downloads\xây dựng KLTN\KhoaLuanTotNghiep\ai-agent-pentest'
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Mở http://127.0.0.1:8501, trang Targets. Đợi phuong-email-local READY rồi tải lại trang.
Chọn New Campaign, target phuong-email-local (không phải langchain-email-assistant
SIMULATION), profile baseline_no_hitl, TestSpec BENIGN-REPLY-001, repetitions 1,
timeout 120, max operations 12. Xác nhận lab, bấm Tạo yêu cầu mới rồi Start Campaign.
Quan sát Verdict/Utility/Evidence và tải report. Tiếp theo tạo yêu cầu mới với
ASI01-EMAIL-001 hoặc ASI02-TOOL-001. Không ép model phải tạo OBSERVED.

## 5. Nếu giống lỗi trong ảnh

- Không có heartbeat: kiểm tra Terminal B, không mở thêm worker nếu worker vẫn chạy.
- Runtime đổi instance/model config: Targets > Request connection check, chờ READY,
  tải lại UI, Tạo yêu cầu mới. Campaign cũ giữ snapshot cũ và không được sửa/replay.
- Token thiếu/sai: đặt cùng token ở runtime và worker, rồi khởi động lại đúng tiến trình.
- local_repository: source runtime phải đúng đường dẫn trong file target local.
- Nguồn hash sai: giữ LF; không bỏ pinning hoặc cập nhật manifest để chấp nhận source lạ.
- LIVE_BACKEND_UNAVAILABLE: kiểm tra URL/model/key và contract API; lỗi này khác với
  một bằng chứng khai thác thành công.

Ảnh ValueError chỉ xác định bước lỗi; không có log/DB gốc để khẳng định nguyên nhân duy nhất.

## Kết quả kiểm tra trên máy này

- Suite hiện có: 129 passed, 1 skipped in 77.14s.
- 4 test bổ sung: 4 passed in 0.21s (source pinning + tùy chọn thinking qua mock HTTP).
- pip check: No broken requirements found.
- Hai thư mục nguồn qua verify_source, cùng manifest hash.
- Chưa chạy API LLM thật vì file cấu hình vẫn là template và chưa được cấp credential.
