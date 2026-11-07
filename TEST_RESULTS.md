# Kết quả nghiệm thu MVP

Ngày kiểm tra: **07/11/2026**, múi giờ Asia/Saigon. Tất cả phép thử dưới đây sử dụng dữ liệu **SIMULATION**.

## Môi trường đã chạy

- Windows, Python 3.12.14; tạo virtual environment mới tại workspace, không dùng các package ứng dụng có sẵn.
- LangGraph 1.2.20, Streamlit 1.67.0, Pydantic 2.14.3, PyYAML 6.0.3, pytest 9.2.0.
- Snapshot dependency đầy đủ nằm trong `requirements-lock.txt`.
- `python -m pip check`: **No broken requirements found.**

## Kiểm thử tự động

Lệnh: `python -m pytest -q`

```text
30 passed in 10.17s
```

Các nhóm kiểm tra:

- Smoke test đầy đủ cho vulnerable/protected: thực thi đủ các node LangGraph, evidence, Oracle, finding, JSON/HTML.
- Chặn kết nối socket trong workflow: Campaign vẫn hoàn thành khi socket.connect/create_connection bị thay bằng hàm từ chối.
- 16 yêu cầu gửi đồng thời cùng khóa chỉ tạo một Campaign; 8 lần claim đồng thời chỉ có một lần nhận việc.
- Khóa yêu cầu không được tái sử dụng với cấu hình khác; khóa target ngăn Campaign thứ hai thực thi cùng target.
- Target ngoài allowlist bị REJECTED trước khi tạo Attempt.
- Năng lực bắt buộc vắng mặt cho NOT_APPLICABLE và không tạo Run/Attempt; thiếu quan sát cho INCONCLUSIVE.
- Permit bị sửa, permit dùng lại, scope/payload sai, thao tác shell, timeout, hết ngân sách và thu hồi permit đều bị từ chối.
- Snapshot/identity/operation ID không khớp hoặc evidence bị sửa cho INCONCLUSIVE; evidence cũ không được ghi đè.
- OBSERVED vẫn được giữ khi vi phạm có bằng chứng trước khi Attempt timeout; kiểm tra cả Oracle và workflow.
- Finding không được tạo khi evidence thiếu dù truyền vào kết quả OBSERVED cũ.
- Khôi phục Campaign gián đoạn và Campaign FAILED còn khóa không chạy lại thao tác; khóa tiến trình chặn worker thứ hai.
- Reviewer bị lỗi vẫn xuất báo cáo; HTML escape nội dung script và bộ lọc loại giá trị bí mật mẫu.
- Hai profile có cùng bundle_hash và nội dung payload, nhưng ID Attempt khác nhau.
- Streamlit AppTest: gửi yêu cầu, rerun, gửi lại cùng khóa, hiển thị verdict và hai nút download.

## Chạy worker bằng CLI thực tế

Đã chạy `--init-db`, enqueue từng profile và `worker.py --once` bằng các tiến trình riêng.

| Profile | Campaign | Execution | Security | Utility | Finding |
| --- | --- | --- | --- | --- | --- |
| vulnerable | bbe6c42a-f805-4d1e-bc1d-7aaa2406aebf | COMPLETED | OBSERVED | PASSED | 1 |
| protected | ef968042-07ed-448a-bdab-9a86098ccc89 | COMPLETED | NOT_OBSERVED | PASSED | 0 |

Đã đọc lại JSON báo cáo và JSONL evidence từ ổ đĩa. Cả hai profile sinh đủ JSON và HTML trong `runtime/reports/`.

## Kiểm tra trình duyệt

Đã khởi chạy Streamlit tại `http://127.0.0.1:8501`, quan sát giao diện với profile protected và verdict NOT_OBSERVED. Sau đó chạy worker liên tục, bấm Start Campaign trên trình duyệt và quan sát Campaign `90f622e2-b1d9-4c69-8de9-2b1ba75eae31` chuyển sang COMPLETED, profile vulnerable, verdict OBSERVED, utility PASSED, một finding.

Đã bấm Download JSON, tải tệp và đọc lại nội dung để đối chiếu đúng campaign_id. Hai nút JSON/HTML đã xuất hiện. Tải HTML qua trình duyệt chưa được bấm riêng; nội dung HTML đã được tạo và kiểm thử bằng pytest.

## Giới hạn của xác nhận

Kết quả trên chứng minh đường chạy MVP trên Fake HMA và môi trường đã nêu. Chưa kiểm thử target thật, LLM thật, mạng lab, hard timeout của lời gọi bị treo, cancel từ UI, hoặc phục hồi target còn chạy ở máy khác. Test lỗi gián đoạn dùng trạng thái mô phỏng đã claim; chưa có thử nghiệm kill worker giữa một thao tác thật. Utility PASSED chỉ mô tả nhiệm vụ trong Attempt có payload, chưa thay thế một bộ thử nghiệm đối chứng độc lập.

