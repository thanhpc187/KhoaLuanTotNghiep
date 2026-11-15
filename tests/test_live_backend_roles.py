import json
import httpx
import pytest
from agent_pentest.execution.live_backend import CompatibleChatModel, ModelConfig, LiveBackendUnavailable
from agent_pentest.ai.roles import RoleRunner
from agent_pentest.models.schemas import Campaign, CapabilityRecord, PlanSpec, PayloadSpec, ExecutionStatus, ResultRecord, Verdict
from agent_pentest.control.registry import RuntimeClient
from agent_pentest.models.schemas import RegisteredTarget


def config():
    return ModelConfig(base_url="https://provider.example.invalid/v1", allowed_base_urls=("https://provider.example.invalid/v1",),
                       model="demo-model", require_api_key=False)


def test_chat_payload_uses_provider_output_and_prompt_metadata(monkeypatch):
    seen, audit = [], []
    def handle(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {
            "content": None, "tool_calls": [{"id": "call-actual", "type": "function",
                "function": {"name": "Done", "arguments": '{"done":true}'}}]}}]})
    monkeypatch.setattr(CompatibleChatModel, "_client",
                        lambda self: httpx.Client(transport=httpx.MockTransport(handle), follow_redirects=False))
    model = CompatibleChatModel(config(), audit.append).bind_tools([{"type": "function", "function": {"name": "Done"}}])
    message = model.invoke([("user", "approved email content")])
    assert message.tool_calls[0]["id"] == "call-actual"
    assert seen[0]["model"] == "demo-model"
    assert seen[0]["messages"] == [{"role": "user", "content": "approved email content"}]
    assert audit[0]["prompt_hash"] and "approved email content" not in json.dumps(audit)


def test_provider_redirect_is_not_followed(monkeypatch):
    requests = []
    def handle(request):
        requests.append(request.url)
        return httpx.Response(302, headers={"Location": "https://elsewhere.invalid/steal"})
    monkeypatch.setattr(CompatibleChatModel, "_client",
                        lambda self: httpx.Client(transport=httpx.MockTransport(handle), follow_redirects=False))
    with pytest.raises(LiveBackendUnavailable):
        CompatibleChatModel(config()).invoke([("user", "email")])
    assert len(requests) == 1


def test_unlisted_provider_rejected_before_transport():
    bad = config().model_copy(update={"base_url": "https://elsewhere.invalid/v1"})
    with pytest.raises(LiveBackendUnavailable):
        bad.validate_destination()


def test_missing_provider_key_is_explicit(monkeypatch):
    monkeypatch.delenv("AGENT_PENTEST_LLM_API_KEY", raising=False)
    cfg = config().model_copy(update={"require_api_key": True})
    with pytest.raises(LiveBackendUnavailable, match="LIVE_BACKEND_UNAVAILABLE"):
        CompatibleChatModel(cfg).invoke([("user", "email")])


class ProposalModel:
    def __init__(self, output):
        self.output = output
    def with_structured_output(self, schema):
        return self
    def invoke(self, prompts):
        return self.output


def test_planner_cannot_expand_target_scope(db, submit):
    cid = submit()
    campaign = Campaign.model_validate(db.detail(cid)["campaign"])
    model = ProposalModel(PlanSpec(test_id=campaign.test_spec.id, target_id="outside"))
    roles = RoleRunner({"backend": "compatible_chat"}, model)
    with pytest.raises(ValueError, match="expanded"):
        roles.plan(campaign, CapabilityRecord(target_id="fake-hma", profile="vulnerable"))
    assert roles.audit[0]["prompt_hash"]


def test_role_fallback_is_recorded_and_reviewer_cannot_change_verdict():
    model = ProposalModel({"security_verdict": "OBSERVED", "fabricated": True})
    result = ResultRecord(campaign_id="c", test_id="t", execution_status=ExecutionStatus.COMPLETED,
                          security_verdict=Verdict.NOT_OBSERVED, reason="No proven violation.")
    roles = RoleRunner({"backend": "compatible_chat", "fallback": "fixed"}, model)
    proposal = roles.review(result)
    assert proposal.explanation == result.reason
    assert result.security_verdict == Verdict.NOT_OBSERVED
    assert roles.audit[-1]["status"] == "FALLBACK_FIXED"
    with pytest.raises(ValueError):
        RoleRunner({"backend": "compatible_chat", "fallback": "reject"}, model).review(result)

