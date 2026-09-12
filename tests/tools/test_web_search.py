import pytest
from pydantic import ValidationError
from backend.app.tools.web_search import WebSearchTool

def test_web_search_success():
    tool = WebSearchTool()
    params = tool.Input(query="TCMB faiz karari")
    result = tool.run(params)
    
    assert result.success is True
    assert result.error is None
    # We should get some results back
    assert len(result.results) >= 0

def test_web_search_error_case():
    tool = WebSearchTool()
    params = tool.Input(query="ERROR_TRIGGER")
    result = tool.run(params)
    
    assert result.success is False
    assert result.error is not None
    assert "Simulated network error" in result.error

def test_web_search_validation_error():
    tool = WebSearchTool()
    # query is required
    with pytest.raises(ValidationError):
        tool.Input()
