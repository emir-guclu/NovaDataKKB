import os
import numpy as np
import pytest
from dotenv import load_dotenv
from app.core.llm_provider import KloudeksProvider

load_dotenv()
pytestmark = pytest.mark.skipif(not os.getenv("MIA_API_KEY"), reason="MIA_API_KEY not configured")


def cosine(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def test_kloudeks_embedding_semantic_health():
    provider = KloudeksProvider()
    a = provider.embed("konut kredisi faiz oranı")
    b = provider.embed("konut finansmanı faiz oranı")
    assert len(a) == len(b)
    assert len(a) == 4096
    assert cosine(a, b) > 0.75
