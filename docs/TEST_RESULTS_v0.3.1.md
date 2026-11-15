# Kết quả nghiệm thu v0.3.1

Cập nhật **12/11/2026**, múi giờ Asia/Saigon. Đợt này chỉ nâng cấp nhánh
`write_email` / ASI02 của registered LangGraph runtime và thêm ca thử đối chứng.
Chưa chạy inference bằng API LLM thật; chủ dự án sẽ bổ sung URL/model/key sau.

## Lệnh và kết quả thực tế

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
```

Lần chạy đầy đủ cuối:

```text
129 passed, 1 skipped in 58.54s
No broken requirements found.
```

Bài skipped: `tests/test_live_runtime.py::test_opt_in_real_llm` — chưa cung cấp
cấu hình/credential cho backend live. Đây không phải một kết quả live pass.
Các bài tích hợp chạy runtime/graph upstream thực tế với model test double,
gắn nhãn `INTEGRATION_TEST`; các adapter hồi quy giữ nhãn `SIMULATION`.

| Nhóm | Pass | Skip | Phạm vi |
| --- | ---: | ---: | --- |
| Suite v0.2 | 95 | 0 | FakeHMA, offline email, foundation fixes, safety, Oracle, UI, migration |
| test_live_runtime.py | 17 | 1 | Registry, graph/runtime, IPC, multi-run, cancel, recovery, UI, provenance |
| test_live_backend_roles.py | 6 | 0 | Provider protocol, redirects, thiếu credential, validation/fallback của AI roles |
| test_write_email_execution.py | 11 | 0 | Validation, binding, chống lặp, receipt, permit ledger, Oracle, ca sạch/attack |
| **Tổng** | **129** | **1** | |

Trước sửa: **118 passed, 1 skipped in 64.94s**. Chạy riêng nhánh mới:
**11 passed in 10.29s**. Lần chạy toàn bộ đầu tiên sau sửa có một lỗi ở assertion
UI đếm danh mục email cũ. Đã cập nhật assertion để nhận ba TestSpec mới, rồi chạy
lại toàn bộ suite ra kết quả ở trên. Không đổi kỳ vọng security verdict để làm test pass.

Log cục bộ ở `work/execution-before-pytest.txt`, `work/write-email-pytest.txt`,
`work/execution-after-pytest.txt` và `work/execution-pip-check.txt`.
Thư mục work là dữ liệu làm việc, không nằm trong FILES.txt.

## Nhánh mới được kiểm chứng

- Từ chối CR/LF trong header, NUL, nội dung rỗng và nội dung vượt giới hạn.
- Tool invoke phải khớp proposal; mỗi accepted write_email có permit identity,
  effect trong sandbox và JSON receipt. Không có thao tác SMTP/Gmail thật.
- Cùng call ID và nội dung chỉ tạo một effect; ID bị dùng lại với nội dung khác
  bị từ chối. Effect không chắc chắn không được tự replay trong cùng Attempt.
- Bốn trường hợp runtime: baseline gửi outsider cho OBSERVED; baseline gửi Alice
  cho NOT_OBSERVED; HITL chặn outsider cho NOT_OBSERVED; HITL cho phép Alice cho
  NOT_OBSERVED. Quyết định được kiểm tra từ call/effect/snapshot, không từ TestSpec ID.
- Thiếu receipt, receipt sai recipient hoặc authorization sai cho INCONCLUSIVE.
  Runtime adapter từ chối accepted call không đối soát được với ledger của worker.
- BENIGN-REPLY-001, ASI02-TOOL-002 và ASI02-TOOL-003 giữ cùng nhiệm vụ/envelope/policy;
  hai ca attack chỉ bổ sung chỉ thị không tin cậy vào email_thread.

Các kiểm thử trên xác nhận contract và sự nhất quán bằng chứng. Chưa đo hiệu quả
hai payload mới trên LLM thật và chưa có tỷ lệ khai thác thành công (ASR).

## Bảo toàn và tương thích

- Giữ FakeHMA, năm TestSpec gốc và source upstream đã khóa revision/hash.
- Đã kiểm tra source pinning của upstream; không sửa mã vendor trong nhánh này.
- Đã đánh giá lại hai bộ evidence mẫu cuối v0.3.0: verdict NOT_OBSERVED và OBSERVED
  giữ nguyên. Metadata write_email_receipts phân biệt contract mới với evidence cũ.
- Không sửa report/evidence lịch sử hoặc snapshot Campaign đã tồn tại.
- Cache chống lặp chỉ ở trong Attempt; không mở cơ chế replay sau worker recovery.
- Giữ kiến trúc Control / Execution / Evidence. Chưa mở multi-tool mỗi lượt,
  notify tương tác, calendar mới, memory mới hoặc Exploratory.

Môi trường đã xác minh: Windows, Python 3.12.14, package editable 0.3.1,
LangGraph 1.2.20, langchain-core 1.7.6, Streamlit 1.67.0, Pydantic 2.14.3,
pytest 9.2.0. Chưa nghiệm thu hệ điều hành/Python khác.

## Tài liệu liên quan

- [Nghiên cứu Execution Plane, thay đổi và roadmap](EXECUTION_RESEARCH.md)
- [Provenance và khác biệt so với upstream](LIVE_PROVENANCE.md)
- [Hướng dẫn demo runtime](DEMO_LIVE.md)
- [Bản nghiệm thu v0.3.0 được lưu lại](TEST_RESULTS_v0.3.0.md)

## Kiểm tra nhánh phuong — 15/11/2026

Commit nhận từ origin/phuong: 28f2512. Suite hiện có: **129 passed, 1 skipped in 77.14s**;
pip check: **No broken requirements found.** Sau đó chạy riêng bốn test mới trong
test_phuong_checkout.py: **4 passed in 0.21s**. Đây là hai lần chạy riêng.
Đã xác minh hash của checkout đầy đủ và bản nguồn rút gọn; sửa xuống dòng CRLF
bằng cách khôi phục byte từ Git và đặt .gitattributes. Không thay manifest.
Chưa kiểm thử API thật; xem [hướng dẫn nhánh phuong](PHUONG_SETUP.md).
