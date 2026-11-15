# Upstream checkout (reference copy)

Bản sao đầy đủ của [langchain-ai/agents-from-scratch](https://github.com/langchain-ai/agents-from-scratch)
tại commit `603fc7a4ac6119004f43894395e504a1fefcc6c0`, dùng làm target tham chiếu cho
các profile `baseline_no_hitl`, `hitl_enabled`, `hitl_memory`.

- License: MIT, xem [LICENSE](agents-from-scratch/LICENSE).
- Bản rút gọn dùng ở runtime nằm tại `third_party/agents_from_scratch` (có hash pinning
  trong `manifest.json`). Các file dùng chung giữa hai bản là giống hệt nhau.
- Đăng ký làm `local_repository` thông qua `configs/registry_policy.yaml`
  (`upstream/agents-from-scratch`). Worker vẫn kiểm tra revision và SHA-256 trước khi chạy.
- Không phải dependency tự tải: không có `.git`, không import package upstream khi chạy.
