import pytest
from pydantic import ValidationError
from backend.app.tools.change_detection import ChangeDetectionTool

def test_change_detection_success():
    tool = ChangeDetectionTool()
    params = tool.Input(
        series_id="BDDK_MONTHLY:krediler:toplam_krediler",
        start_date="2023-01-01",
        end_date="2023-02-01"
    )
    result = tool.run(params)
    
    assert result.success is True
    assert result.error is None
    assert len(result.rows) > 0
    assert "mom_pct_change" in result.rows[0]

def test_change_detection_error_case():
    tool = ChangeDetectionTool()
    params = tool.Input(
        series_id="INVALID_SERIES",
        start_date="2023-01-01",
        end_date="2023-02-01"
    )
    result = tool.run(params)
    
    assert result.success is False
    assert result.error is not None
    assert "Boyle bir seri bulunamadi" in result.error

def test_change_detection_validation_error():
    tool = ChangeDetectionTool()
    # Missing required end_date should raise ValidationError
    with pytest.raises(ValidationError):
        tool.Input(
            series_id="BDDK_MONTHLY:krediler:toplam_krediler",
            start_date="2023-01-01"
        )
