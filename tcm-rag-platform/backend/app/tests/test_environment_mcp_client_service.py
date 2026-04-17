import asyncio

from app.services import environment_mcp_client_service as service


def test_environment_mcp_falls_back_when_server_module_missing(monkeypatch):
    async def fake_live_context(preferred_location=None):
        return {"environmental_context": "fallback", "preferred_location": preferred_location}

    def fail_stdio_client(*args, **kwargs):
        raise AssertionError("stdio_client should not be called when server module is unavailable")

    monkeypatch.setattr(service.settings, "LIVE_CONTEXT_ENABLED", True)
    monkeypatch.setattr(service.settings, "MCP_ENVIRONMENT_ENABLED", True)
    monkeypatch.setattr(service, "ClientSession", object())
    monkeypatch.setattr(service, "StdioServerParameters", object())
    monkeypatch.setattr(service, "stdio_client", fail_stdio_client)
    monkeypatch.setattr(service, "_has_environment_mcp_server", lambda: False)
    monkeypatch.setattr(service, "get_live_context_async", fake_live_context)

    payload = asyncio.run(service.flash_call_environment_mcp({"city": "Shanghai"}))

    assert payload == {
        "environmental_context": "fallback",
        "preferred_location": {"city": "Shanghai"},
    }


def test_environment_mcp_times_out_and_falls_back(monkeypatch):
    async def fake_live_context(preferred_location=None):
        return {"environmental_context": "fallback-after-timeout"}

    class FakeSession:
        def __init__(self, read, write):
            self.read = read
            self.write = write

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def initialize(self):
            await asyncio.sleep(0.05)

        async def call_tool(self, name, arguments=None):
            return None

    class FakeStdioContext:
        async def __aenter__(self):
            return object(), object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(service.settings, "LIVE_CONTEXT_ENABLED", True)
    monkeypatch.setattr(service.settings, "MCP_ENVIRONMENT_ENABLED", True)
    monkeypatch.setattr(service.settings, "LIVE_CONTEXT_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(service, "ClientSession", FakeSession)
    monkeypatch.setattr(service, "StdioServerParameters", lambda **kwargs: kwargs)
    monkeypatch.setattr(service, "stdio_client", lambda params: FakeStdioContext())
    monkeypatch.setattr(service, "_has_environment_mcp_server", lambda: True)
    monkeypatch.setattr(service, "get_live_context_async", fake_live_context)

    payload = asyncio.run(service.flash_call_environment_mcp())

    assert payload == {"environmental_context": "fallback-after-timeout"}
