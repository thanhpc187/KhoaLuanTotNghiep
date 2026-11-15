# Nghiệm thu CLI v0.3

Dùng [lần nghiệm thu cuối ngày 10/11/2026](final-run/README.md) để đối chiếu code hiện tại.
Hai Campaign chạy runtime/worker riêng, cho OBSERVED và NOT_OBSERVED; model là test double
có nhãn INTEGRATION_TEST. Không có inference API thật.

Các tệp acceptance.json, reports/ và evidence/ ngay tại thư mục này giữ nguyên lần chạy
sơ bộ 09/11/2026 để không ghi đè lịch sử. Lần đó CLI và manifest còn nhãn SIMULATION sai,
trong khi events/report đã là INTEGRATION_TEST. Bộ đọc đã được sửa để từ chối manifest
không khớp mode; vì vậy evidence sơ bộ không còn được coi là hợp lệ để nghiệm thu.
Không dùng bộ sơ bộ làm mẫu kết quả hiện hành. Bộ final-run đã chạy lại và kiểm tra đầy đủ.
