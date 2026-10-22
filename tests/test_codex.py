import asyncio

from jarvis.codex import DISABLED_FEATURES
from jarvis.runtime import Runtime


async def test_actual_installed_app_server_handshake_without_credentials(tmp_path):
    # Integration with the actual installed binary, not a simulated account or model response.
    runtime = Runtime(tmp_path)
    try:
        result = await runtime.codex.refresh()
        assert result["version"] == "codex-cli 0.163.0"
        assert result["connected"]
        assert result["account"] is None  # dedicated empty profile: never copy the host's credentials
        assert result["verified_models"] == []
        thread = await runtime.codex.request(
            "thread/start",
            {
                "cwd": str(runtime.root / "agent-workspace"),
                "ephemeral": True,
                "sandbox": "read-only",
                "approvalPolicy": "on-request",
                "dynamicTools": runtime.tools.specifications(),
            },
        )
        assert thread["thread"]["id"]
    finally:
        await runtime.codex.close()
        runtime.store.close()


async def test_unknown_execution_route_is_denied(tmp_path):
    # Protocol unit test only; this is not evidence of an authenticated inference.
    runtime = Runtime(tmp_path)
    frames = []

    async def capture(frame):
        frames.append(frame)

    runtime.codex.send = capture
    await runtime.codex.notification(
        {"id": 17, "method": "item/commandExecution/requestApproval", "params": {"command": "powershell"}}
    )
    assert frames[0]["error"]["code"] == -32601
    assert "shell_tool" in DISABLED_FEATURES
    runtime.store.close()


async def test_duplicate_structured_call_executes_once(tmp_path):
    # Protocol unit test with real tool persistence; no model inference is simulated as a success.
    runtime = Runtime(tmp_path)
    codex = runtime.codex
    codex.thread_id = "thread"
    codex.turn_id = "turn"
    replies = []

    async def capture(frame):
        replies.append(frame)

    codex.send = capture
    params = {
        "threadId": "thread",
        "turnId": "turn",
        "callId": "same-call",
        "tool": "memory_save",
        "arguments": {"title": "Uma vez", "body": "Uma única nota"},
    }
    try:
        await codex.notification({"id": 1, "method": "item/tool/call", "params": params})
        await codex.notification({"id": 2, "method": "item/tool/call", "params": params})
        await asyncio.gather(*codex.response_tasks)
        assert len(runtime.store.notes()) == 1
        assert {r["id"] for r in replies} == {1, 2}
    finally:
        runtime.store.close()


async def test_late_delta_is_not_delivered_to_new_turn(tmp_path):
    runtime = Runtime(tmp_path)
    codex = runtime.codex
    codex.thread_id = "thread"
    codex.turn_id = "current"
    received = []
    codex.on_delta = received.append
    await codex.notification(
        {
            "method": "item/agentMessage/delta",
            "params": {"threadId": "thread", "turnId": "old", "delta": "Late response"},
        }
    )
    assert not received
    runtime.store.close()


async def test_quota_failure_does_not_retry(tmp_path):
    import pytest

    runtime = Runtime(tmp_path)
    codex = runtime.codex
    codex.account = {"type": "chatgpt"}
    codex.models = [{"model": "fixture-model", "isDefault": True}]
    codex.thread_id = "fixture-thread"
    attempts = []

    async def no_start():
        pass

    async def request(method, params):
        attempts.append(method)
        asyncio.get_running_loop().call_soon(
            lambda: codex.turn_done.set_result(
                {"id": "fixture-turn", "status": "failed", "error": {"message": "Quota exhausted"}}
            )
        )
        return {"turn": {"id": "fixture-turn"}}

    codex.start = no_start
    codex.request = request
    with pytest.raises(RuntimeError, match="Quota exhausted"):
        await codex.answer("Protocol test only", lambda text: None)
    assert attempts == ["turn/start"]
    assert not codex.access_verified
    runtime.store.close()
