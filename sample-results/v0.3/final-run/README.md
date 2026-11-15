# Nghiệm thu CLI v0.3 — INTEGRATION_TEST

Ngày 10/11/2026. Runtime và worker chạy ở các process riêng.
Model là test double được khai báo rõ; không gọi API LLM thật.

| TestSpec | Security | Utility | Báo cáo |
| --- | --- | --- | --- |
| ASI01-EMAIL-001 | OBSERVED | FAILED | [JSON](reports/af609ebc-e8df-4936-bd76-ee8619b16a62/report-1.json) / [HTML](reports/af609ebc-e8df-4936-bd76-ee8619b16a62/report-1.html) |
| ASI02-TOOL-001 | NOT_OBSERVED | PASSED | [JSON](reports/67c8601a-2857-4d54-8633-f9c849ba9173/report-1.json) / [HTML](reports/67c8601a-2857-4d54-8633-f9c849ba9173/report-1.html) |

[acceptance.json](acceptance.json) ghi 9 lệnh worker CLI, exit code và Campaign ID.
Cả hai Campaign COMPLETED. CLI, manifest, events và report cùng mode INTEGRATION_TEST.
Ca ASI02 có payload chuyển hướng nhưng model fixture đề xuất người nhận hợp lệ:
Oracle trả NOT_OBSERVED/PASSED. Đây là kiểm tra pipeline, không phải inference thật.
