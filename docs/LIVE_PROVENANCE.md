# Provenance và ranh giới của runtime v0.3

Source upstream được khóa tại commit
[603fc7a4ac6119004f43894395e504a1fefcc6c0](https://github.com/langchain-ai/agents-from-scratch/tree/603fc7a4ac6119004f43894395e504a1fefcc6c0).
Các tệp được giữ nguyên trong third_party/agents_from_scratch; manifest.json chứa
SHA-256 từng tệp. MIT License và copyright upstream được giữ cùng source.

Đây là **bản bọc có instrumentation**, không phải chạy nguyên ứng dụng upstream
không thay đổi. Điểm khác với v0.2: runtime thực thi thân hàm node lấy trực tiếp từ
source đã xác minh, không dùng LabRuleBackedEmailModel cho đường live.

## Phần thực thi nguyên thân hàm

- triage_router, llm_call, tool_node/interrupt_handler, should_continue của graph đã chọn.
- update_memory của biến thể memory: nhánh ignore truyền nguyên lịch sử email/tool
  result/feedback vào hàm cập nhật memory và gọi model structured output.
- parse_email, format_email_markdown, format_for_display và các prompt constants.

Loader dùng AST chọn function definitions và prompt constants từ source đã khóa hash.
Không import module initializer, .env, Gmail, provider mặc định hoặc tool ngoài.
Trước mỗi Attempt, các tệp nguồn được xác minh lại; chỉ đường dẫn trong allowlist mới được đăng ký.

## Thay đổi do wrapper

| Phần | Cách bọc / giới hạn |
| --- | --- |
| Graph | Dựng lại wiring cùng triage → response subgraph; node wrapper gọi function upstream rồi ghi quan sát. MessagesState thêm phase. |
| Provider | Thay init_chat_model("openai:gpt-4.1") bằng CompatibleChatModel đọc cấu hình operator. Cần /models, /chat/completions, JSON output và function tools. |
| Output schemas | Giữ classification/user_preferences, cho phép reasoning/chain_of_thought rỗng. Không lưu reasoning vào evidence. |
| Tool contracts | Dùng năm tool sandbox đã khai báo; ngày calendar là chuỗi ISO thay datetime của tool upstream. Mỗi lượt model phải có đúng một proposal. Nhiều proposal/không proposal bị báo không đủ khả năng quan sát, không tự diễn giải thành tác động. |
| Sandbox effects | write_email/schedule_meeting ghi LabEmailState, không gửi mạng. Calendar trả availability lab. Mỗi mutation chờ permit từ worker qua protocol. |
| write_email v0.3.1 | Wrapper cấp call ID và giữ hash ID provider; kiểm tra args khớp proposal, header/body hợp lệ. Gửi sandbox trả JSON receipt (không gửi email thật). Worker đối soát authorization_id; Oracle đối chiếu receipt với call/state delta/snapshot. Đây là thay đổi kết quả tool so với upstream/v0.3.0. |
| Store | get_memory trả content; Store bọc giá trị trong dict để tương thích schema v0.2. Khởi tạo đúng default preferences upstream trong permit reset. |
| Memory writes | Hàm update_memory upstream chạy với view Store; put đi qua guard, trace và state delta trước khi commit vào InMemoryStore. |
| HITL | interrupt và Command resume thật; chỉ accept/ignore tự động theo TestSpec. Không có người phê duyệt trực tiếp; không hỗ trợ edit/response. |
| Notify | Handler tương tác notify chưa được instrument đầy đủ. Runtime báo OBSERVATION_UNAVAILABLE, workflow/evidence kết luận INCONCLUSIVE thay vì bịa phản hồi. |
| Stop | Mỗi Attempt ở process riêng. Supervisor HTTP còn hoạt động khi model bị chặn và có thể terminate/kill process; mất xác nhận giữ target lock. |

Các prompt upstream có ngày hiện tại; prompt hash ghi lại nội dung thực tế được gửi.
Fixed khóa TestSpec/payload/config; không hứa byte-for-byte giống nhau giữa các lần
inference của provider. Backend/model/config hash, source hash/revision, graph entrypoint,
wrapper version, runtime instance, rule version và injection surface được gắn vào Attempt/events.

## Nguồn bằng chứng

Target không có Database hoặc EvidenceStore. Nó chỉ xuất observation qua IPC.
Worker xác minh context, lưu JSONL/manifest và chạy Oracle. Oracle yêu cầu provenance,
trace, accepted call, state delta và snapshot khớp; text model tự tuyên bố thành công
không phải bằng chứng tác động.

Protocol xác thực bằng bearer token riêng cho runtime và chỉ chấp nhận origin
http://127.0.0.1:<port> đã allowlist. HTTP redirects, proxy environment, userinfo,
query/fragment và arbitrary LangGraph URL không được chấp nhận. Provider inference
có allowlist base URL riêng; không dùng allowlist runtime để cấp truy cập target bên ngoài.

Đây là lab với source được operator tin cậy. Process separation không phải OS sandbox
cho mã Python độc hại; hashes/token không phải remote attestation. Runtime không có
đường SMTP/Gmail/calendar, nhưng provider inference có thể ra Internet nếu operator
cấu hình một API HTTPS được phép.

## Trạng thái nghiệm thu

INTEGRATION_TEST chạy cùng source nodes/graph/IPC/permits bằng output model kiểm soát
trong tests; nó kiểm tra pipeline, không chứng minh LLM thật bị khai thác.
LIVE_LLM_LAB chỉ dùng API, không tự rơi về rule hoặc test fixture. Thiếu URL/model/key
hoặc provider không khả dụng được báo LIVE_BACKEND_UNAVAILABLE.
Chạy opt-in integration test trước khi ghi nhận demo sử dụng inference thật.

Wrapper hiện là upstream-sandbox-2. Capability metadata `write_email_receipts: "1"`
đánh dấu hợp đồng receipt bắt buộc cho write_email được thực thi. Evidence cũ không
có cờ này tiếp tục dùng hợp đồng cũ; không thêm receipt hồi tố hoặc đổi nhãn sample.
Chống lặp chỉ trong cùng Attempt/process; recovery sau crash vẫn không replay.
