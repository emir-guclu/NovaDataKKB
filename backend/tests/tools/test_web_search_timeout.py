from unittest.mock import MagicMock, patch

from backend.app.tools.web_search import WebSearchTool


def test_web_search_uses_explicit_timeout():
    fake_ddgs = MagicMock()
    fake_ddgs.__enter__.return_value = fake_ddgs
    fake_ddgs.text.return_value = []

    with patch("backend.app.tools.web_search.DDGS", return_value=fake_ddgs) as cls:
        tool = WebSearchTool()
        result = tool.run(tool.Input(query="test"))

    cls.assert_called_once_with(timeout=5)
    assert result.success is True
