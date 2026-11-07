# Quy tắc phát triển MVP

Phạm vi hiện tại là Vertical Slice MVP mô phỏng, không phải CORE đầy đủ.
Đọc README.md, TestSpec và các schema trước khi sửa luồng thực thi.

- Giữ ba khối Control Plane, Execution Plane, Evidence Plane.
- Streamlit chỉ gửi yêu cầu và đọc trạng thái. Worker cục bộ chạy LangGraph.
- Chỉ hỗ trợ adapter `fake_hma`. Không thêm kết nối target, LLM API, shell hoặc dịch vụ Internet nếu người dùng chưa yêu cầu phạm vi mới.
- Ghi `SIMULATION` trên dữ liệu, giao diện, evidence, finding và báo cáo. Không mô tả Fake HMA là AI Agent thật.
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
- Chưa triển khai 12 TestSpec, ASI06 nhiều pha, LLM thật, Exploratory retry, VMware/pfSense/mailserver hay benchmark trong MVP.

