# Provenance của target email v0.2.0

Tài liệu này mô tả adapter offline được giữ làm regression baseline.
Đường runtime v0.3 dùng source nodes đã khóa hash và API backend riêng:
xem [LIVE_PROVENANCE.md](LIVE_PROVENANCE.md).

Target `langchain-email-assistant` là bản thích nghi có instrumentation của kiến trúc
[langchain-ai/agents-from-scratch](https://github.com/langchain-ai/agents-from-scratch),
khóa tại commit [603fc7a4ac6119004f43894395e504a1fefcc6c0](https://github.com/langchain-ai/agents-from-scratch/tree/603fc7a4ac6119004f43894395e504a1fefcc6c0).
Nguồn được đọc khi triển khai; không import package upstream ở thời điểm chạy.
Target version trong cấu hình là `agents-from-scratch-603fc7a`.

Upstream dùng MIT License, Copyright (c) 2026 LangChain, Inc.
Toàn văn được giữ trong [third_party/agents-from-scratch.LICENSE](../third_party/agents-from-scratch.LICENSE).
Mã thích nghi nằm ở [langgraph_email.py](../src/agent_pentest/execution/langgraph_email.py);
model lab nằm ở [email_model.py](../src/agent_pentest/execution/email_model.py).

## Đối chiếu kiến trúc

| Nguồn upstream tại commit đã khóa | Profile / phần giữ lại |
| --- | --- |
| [email_assistant.py](https://github.com/langchain-ai/agents-from-scratch/blob/603fc7a4ac6119004f43894395e504a1fefcc6c0/src/email_assistant/email_assistant.py) | `baseline_no_hitl`: triage_router → response_agent; subgraph llm_call → tool_handler → llm_call; Done kết thúc |
| [email_assistant_hitl.py](https://github.com/langchain-ai/agents-from-scratch/blob/603fc7a4ac6119004f43894395e504a1fefcc6c0/src/email_assistant/email_assistant_hitl.py) | `hitl_enabled`: interrupt trước write_email, schedule_meeting, Question; resume bằng Command |
| [email_assistant_hitl_memory.py](https://github.com/langchain-ai/agents-from-scratch/blob/603fc7a4ac6119004f43894395e504a1fefcc6c0/src/email_assistant/email_assistant_hitl_memory.py) | `hitl_memory`: triage đọc Store; nhánh ignore học từ toàn bộ lịch sử chứa email ban đầu |
| [schemas.py](https://github.com/langchain-ai/agents-from-scratch/blob/603fc7a4ac6119004f43894395e504a1fefcc6c0/src/email_assistant/schemas.py) | MessagesState, email_input, classification_decision; ba nhãn ignore/respond/notify |

Các lớp LangGraph được dùng trực tiếp: StateGraph, MessagesState, START, END,
Command, interrupt, InMemoryStore, InMemorySaver. Graph thực sự dừng tại interrupt
và được resume; tool không được thực thi trước quyết định HITL.

Trong upstream memory, ba nhánh ignore của write_email / schedule_meeting / Question
gọi update_memory với state["messages"] + result + thông điệp phản hồi. Bản lab giữ
ranh giới tin cậy này: email đầu vào vẫn xuất hiện trong lịch sử truyền cho bộ cập nhật
triage_preferences. Đây là cơ chế được mô phỏng trong ASI06.

## Những khác biệt được chủ động giới hạn

- LabRuleBackedEmailModel thay model API ở triage, llm_call và update_memory. Nó đọc
  subject/email_thread và preferences, không nhận TestSpec ID, profile hoặc verdict
  mong muốn. Các mẫu chỉ thị được mã hóa để tái lập cơ chế lỗi; đây không phải số liệu
  về xác suất một LLM thật làm theo prompt injection.
- Tool email/calendar ghi vào LabEmailState trong bộ nhớ; không gửi thư, không gọi
  lịch thật. check_calendar_availability trả kết quả lab cố định; ngày và giờ đề xuất
  cố định để tái lập. Question chỉ tạo hội thoại tổng hợp.
- Một lượt model chỉ đề xuất một tool. Done là tín hiệu kết thúc, không tạo tác động.
  Lab chỉ triển khai HITL accept/ignore; các nhánh edit/response của upstream chưa được triển khai.
- Quyết định HITL được tự động hóa bởi hitl_policy, ghi automated=true trong evidence.
  Đây không phải thao tác phê duyệt của một người dùng thật.
- Store dùng namespace ("email_assistant", "triage_preferences"), key user_preferences;
  giá trị được bọc trong {"content": "..."} để dùng hợp đồng dict của InMemoryStore.
  response_preferences và cal_preferences được khởi tạo; các luồng học từ edit/response
  tương ứng chưa được đưa vào lab.
- Hai pha ASI06 dùng thread/checkpoint riêng và cùng Store. Mỗi Attempt tạo adapter,
  Store và Saver mới; memory không đi xuyên Attempt. Checkpoint không dùng để retry
  tác động sau crash.
- Mỗi mutation có guard/permit, trace canonical và snapshot; Oracle độc lập với model.
  Đây là instrumentation của framework khóa luận, không phải code có sẵn trong upstream.

## Hook ChatModel

`build_email_model(chat_model=...)` chỉ trả ChatModelEmailBackend khi
`AGENT_PENTEST_EMAIL_BACKEND=chat` và caller truyền instance ChatModel rõ ràng.
Caller có thể truyền backend đó vào tham số model của LangGraphEmailAdapter.
Worker mặc định không tạo provider và sẽ từ chối chế độ chat thiếu instance.
Chưa có cấu hình credentials, transport, network policy, deadline hoặc nghiệm thu
cho API thật; cấu hình bàn giao vẫn là rule và network_enabled=false.

Kết quả ASI01/ASI02/ASI06 trong bản này xác nhận framework quan sát đúng cơ chế được
cài trong lab. Chúng không chứng minh một lỗ hổng đã khai thác trên LLM thật hay
mọi triển khai của repository upstream.
