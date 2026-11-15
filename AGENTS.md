# Quy tắc phát triển v0.3.1

Đợt 12/11/2026: chủ dự án yêu cầu nghiên cứu Execution Plane, sau đó giới hạn
triển khai một nhánh trước. v0.3.1 chỉ nâng cấp write_email của runtime và các
TestSpec ASI02 tương ứng. Không coi roadmap multi-tool/calendar/memory là đã triển khai.
Giữ hồi quy v0.3.0; receipt mới phải liên kết proposal, permit, effect và snapshot.

Chủ dự án đã cho phép nâng cấp live runtime, target registry, discovery, multi-run,
cancel và backend LLM. Các giới hạn chỉ-offline bên dưới mô tả baseline v0.2;
yêu cầu mới cho phép LIVE_LLM_LAB, vẫn cô lập effects và giữ toàn bộ 95 regression tests.
Chỉ chạy node upstream đã khóa revision/hash qua wrapper được mô tả rõ.
Không tự thay backend live bằng rule/test; test doubles phải mang nhãn INTEGRATION_TEST.
UI chỉ ghi queue/registry/check/cancel requests và đọc dữ liệu; worker thực hiện kết nối.
Credential lấy từ environment, không lưu vào registry/campaign/evidence.

Chủ dự án đã cho phép nâng cấp MVP v0.1.0 lên v0.2.0 để thực nghiệm offline.
Giữ fake_hma làm regression baseline và bảo toàn toàn bộ 30 bài kiểm thử v0.1.0.
Cho phép adapter langgraph_email_assistant dựa trên kiến trúc ba biến thể
email_assistant, email_assistant_hitl, email_assistant_hitl_memory của
https://github.com/langchain-ai/agents-from-scratch tại commit 603fc7a (MIT).
Ghi provenance, giấy phép và các khác biệt so với upstream; không trình bày model
quy tắc offline như LLM thật hoặc kết quả benchmark mô hình thật.
Đọc README.md, TestSpec và các schema trước khi sửa luồng thực thi.

- Giữ ba khối Control Plane, Execution Plane, Evidence Plane.
- Streamlit chỉ gửi yêu cầu và đọc trạng thái. Worker cục bộ chạy LangGraph.
- Hỗ trợ hai adapter offline và langgraph_runtime qua protocol lab allowlist. Runtime live đọc cấu hình provider rõ ràng; thiếu backend phải báo LIVE_BACKEND_UNAVAILABLE.
- Phân biệt SIMULATION, INTEGRATION_TEST và LIVE_LLM_LAB trên dữ liệu/evidence/report. Không mô tả test double hoặc FakeHMA là inference thật.
- Campaign cố định target/profile/scope/TestSpec. Run là một TestSpec và chỉ số lặp. Attempt là một lần thực thi đầy đủ, có ID/reset_id/evidence riêng.
- Không tự retry thao tác thay đổi trạng thái. Không tự mở khóa target vì thời gian khóa đã hết.
- Chống trùng ở SQLite bằng khóa yêu cầu, giao dịch claim và khóa target; không chỉ dựa vào session_state.
- Mọi thay đổi trạng thái phải qua ControlledExecutor và permit đúng target/profile/Attempt/action/content hash, có thời hạn và ngân sách.
- Các vai trò AI chỉ được trả proposal có schema. Không cấp cho chúng Database, adapter, policy writer hoặc evidence writer.
- Không cho phép nguồn không tin cậy quyết định authenticated sender hoặc nhãn nguồn evidence.
- Oracle chỉ dùng evidence hợp lệ, không dùng lời tự thuật của target. Giữ độc lập execution status/security verdict/utility.
- NOT_APPLICABLE cần năng lực vắng mặt đã được xác minh; thiếu thông tin là INCONCLUSIVE, không tạo Attempt dư thừa.
- Chỉ tạo finding khi kiểm chứng lại điều kiện OBSERVED và evidence references.
- Bảo toàn evidence và kết quả trước đó. Report xuất lại phải tạo revision mới.
- Không ghi credentials vào mã nguồn, log, evidence hoặc báo cáo. Không lưu nguyên văn lỗi từ target.
- HTML phải escape nội dung không tin cậy. Không dùng unsafe_allow_html cho nội dung từ target.
- Chạy `python -m pytest -q` và `python -m pip check` sau thay đổi có ảnh hưởng hành vi.
- Thêm test khi sửa safety, oracle, dedup hoặc phục hồi lỗi. Không khẳng định tính năng hoạt động khi chưa kiểm chứng.
- v0.2.0 thêm BENIGN-EMAIL-001, ASI01-EMAIL-001, ASI02-TOOL-001 và ASI06-MEM-001 hai pha trên cùng InMemoryStore; không reset giữa hai pha.
- HITL dùng interrupt/Command của LangGraph; quyết định lab được tự động hóa theo hitl_policy, không mô tả là người dùng thật đã duyệt.
- Exploratory, Gmail/SMTP/calendar thật, VMware/pfSense và benchmark thống kê chưa được hỗ trợ. Kiểm thử live API chỉ được ghi pass sau khi thực sự gọi provider trong bài opt-in.
- Recovery giữ khóa target đến khi xuất báo cáo thành công, bảo toàn lỗi gốc và không replay thao tác.

