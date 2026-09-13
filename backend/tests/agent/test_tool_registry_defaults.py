from backend.app.agent.tool_registry import create_default_tool_registry


def test_default_tool_registry_includes_web_url_reader_tool():
    registry = create_default_tool_registry()

    assert registry.get("web_url_reader") is not None


def test_default_tool_registry_includes_evds_data_service_tool():
    registry = create_default_tool_registry()

    assert registry.get("evds_data_service") is not None
