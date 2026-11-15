# Agent Pentest Framework

Hệ thống kiểm thử bảo mật AI Agent phục vụ khóa luận tốt nghiệp. Chương trình đưa
payload vào nội dung email, theo dõi cách agent xử lý và đối chiếu bằng chứng để
xác định có xảy ra vi phạm hay không.

Target chính là LangGraph Email Assistant, dựa trên mã nguồn
[agents-from-scratch](https://github.com/langchain-ai/agents-from-scratch) của LangChain.
Email và lịch hẹn được ghi trong sandbox, không gửi đến dịch vụ thật.

## Kiến trúc

| Thành phần | Trách nhiệm |
| --- | --- |
| Control Plane | Nhận cấu hình, chọn kịch bản, điều phối và kiểm tra quyền thực thi |
| Execution Plane | Kết nối target, đưa payload vào agent và thực thi qua permit |
| Evidence Plane | Thu thập trace, đối chiếu trạng thái, kết luận và xuất báo cáo |

Luồng kiểm thử: **Chọn target → Chọn TestSpec → Chạy → Thu thập bằng chứng → Đánh giá → Báo cáo.**

Giao diện Streamlit gửi yêu cầu; worker thực hiện kiểm thử. Oracle dùng quy tắc
xác định để đánh giá bằng chứng, không dùng LLM để quyết định verdict.

## Kịch bản thực nghiệm

| Nhóm | Nội dung kiểm tra |
| --- | --- |
| BENIGN | Agent có hoàn thành nhiệm vụ với email sạch hay không |
| ASI01 | Nội dung chèn khiến agent bỏ qua email cần phản hồi |
| ASI02 | Nội dung chèn khiến agent gửi email đến người nhận ngoài phạm vi cho phép; so sánh với HITL |
| ASI06 | Nội dung email tác động đến bộ nhớ và làm sai phân loại email ở pha tiếp theo |

Mỗi lần chạy lưu payload, tool calls, trạng thái trước/sau và báo cáo JSON/HTML.
Kết quả gồm `OBSERVED`, `NOT_OBSERVED`, `INCONCLUSIVE` hoặc `NOT_APPLICABLE`.
Kết quả bảo mật được ghi riêng với mức độ hoàn thành nhiệm vụ của agent.

## Cấu trúc thư mục

```text
ai-agent-pentest/
├── app.py                  # Giao diện Streamlit
├── worker.py               # Xử lý hàng đợi Campaign
├── lab_runtime.py          # Khởi chạy target LangGraph riêng
├── src/agent_pentest/
│   ├── control/            # Workflow, registry, catalogue, safety
│   ├── execution/          # Executor, adapter, runtime, sandbox tools
│   ├── evidence/           # Collector, store, Oracle, findings, báo cáo
│   ├── ai/                 # Planner, Testing Agent, Reviewer
│   ├── models/             # Schema dữ liệu
│   ├── storage/            # SQLite
│   └── service.py          # Nạp cấu hình và tạo yêu cầu
├── configs/                # Scope, target, runtime và model
├── testspecs/              # 8 kịch bản YAML
├── tests/                  # Kiểm thử tự động
├── third_party/            # Source upstream đã khóa revision và giấy phép
├── runtime/                # Database, evidence, báo cáo khi chạy
├── sample-results/         # Kết quả mẫu đã lưu
└── docs/                   # Tài liệu kiến trúc và thực nghiệm
```

## Chạy chương trình

Môi trường đã kiểm tra: Windows, Python 3.12. Chạy các lệnh tại thư mục dự án.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe worker.py --init-db
```

Mở hai terminal riêng:

```powershell
# Terminal 1: worker
.\.venv\Scripts\python.exe worker.py

# Terminal 2: giao diện
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Mở http://127.0.0.1:8501. Các target mô phỏng có thể chạy ngay, không cần API key.
Để chạy target dùng LLM thật, cấu hình provider, khởi động runtime và đăng ký target
thực hiện theo [hướng dẫn demo](docs/DEMO_LIVE.md).

## Trạng thái hiện tại

Phiên bản **0.3.1** đã bổ sung kiểm tra tham số, chống lặp và biên nhận sandbox cho
`write_email`. Kết quả kiểm thử ghi nhận ngày 12/11/2026: **129 passed, 1 skipped**;
`pip check` không có lỗi phụ thuộc.

Ba chế độ được ghi rõ trong báo cáo: `SIMULATION` (mô phỏng), `INTEGRATION_TEST`
(graph thật với model kiểm thử) và `LIVE_LLM_LAB` (API LLM thật).
Chưa nghiệm thu bằng API LLM thật; bài kiểm thử live đang được bỏ qua do thiếu cấu hình.
Chưa hỗ trợ Exploratory, nhiều tool call trong một lượt hoặc Gmail/Calendar thật.
HITL hiện dùng chính sách duyệt/từ chối tự động trong lab.

## Tài liệu

- [Hướng dẫn demo](docs/DEMO_LIVE.md)
- [Kiến trúc và vai trò các file](docs/ARCHITECTURE.md)
- [Nguồn upstream và những thay đổi của wrapper](docs/LIVE_PROVENANCE.md)
- [Nghiên cứu Execution Plane và hướng nâng cấp](docs/EXECUTION_RESEARCH.md)
- [Kết quả kiểm thử](TEST_RESULTS.md) · [Danh sách đầy đủ các file](FILES.txt)
