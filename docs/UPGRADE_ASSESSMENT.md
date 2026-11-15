# Kiểm tra kiến trúc trước nâng cấp live

Ngày 08/11/2026. Code thực tế là v0.2.0, gồm 95 tests (không phải 30).
Baseline FakeHMA và LangGraph rule model đều chạy trong worker. ChatModel hiện chỉ có
hook injection, chưa tạo provider. Source provenance là 603fc7a4ac6119004f43894395e504a1fefcc6c0.

| Yêu cầu | Trước nâng cấp | Khoảng trống |
| --- | --- | --- |
| Ba Plane, permit, queue/claim, evidence, Oracle | IMPLEMENTED | Giữ nguyên ranh giới |
| Graph email và interrupt/memory | PARTIAL | Là adaptation offline, chưa chạy node nguyên bản với inference thật |
| Registry độc lập TestSpec, path/endpoint allowlist | MISSING | Cần registry và handshake compatibility |
| Discovery | PARTIAL | Record tĩnh từ adapter; chưa có PRESENT/ABSENT/UNKNOWN theo capability |
| Live runtime / model backend | MISSING | Cần runtime riêng, cấu hình provider và lỗi unavailable rõ ràng |
| Multi-test / repetition | PARTIAL | DB cho phép nhiều dòng; scheduler chỉ một Run/Attempt |
| Cancel / process stop / recovery remote | MISSING | Hiện chỉ cooperative timeout trong process |
| AI roles | PARTIAL | Fixed roles; cần backend có schema, provenance và quyền hạn tách biệt |
| UI | PARTIAL | Chọn YAML target; thiếu registry, preflight, multi-select và cancel |
| Oracle / report | PARTIAL | Tốt cho lab offline; cần phân biệt live/test và provenance mới |

Phạm vi nâng cấp v0.3: protocol runtime lab riêng (không nhận arbitrary LangGraph URL),
node upstream đã khóa hash, sandbox tools, backend chat tương thích, registry và
multi-run Fixed. Exploratory bị vô hiệu hóa có lý do; không tự đổi payload sau kết quả.
Runtime/model thiếu sẽ được báo LIVE_BACKEND_UNAVAILABLE, không fallback rule.

## Kết quả triển khai v0.3 (09/11/2026)

Registry, preflight, capability facts, runtime HTTP có xác thực, node upstream đã
khóa hash, IPC permits, multi-run Fixed, cancel, recovery đối soát và UI đã có code
và kiểm thử tích hợp. Backend compatible-chat và ba role LLM có cấu hình/schema/audit.
Chưa nghiệm thu inference thật vì chủ dự án sẽ điền API URL/model/key sau.

Exploratory, notify tương tác đầy đủ, nhiều tool call mỗi lượt, arbitrary runtime,
Gmail/SMTP/calendar thật và hard kill riêng cho role LLM vẫn chưa hỗ trợ.
Chi tiết instrumentation nằm ở LIVE_PROVENANCE.md; kết quả kiểm tra ở TEST_RESULTS.md.
