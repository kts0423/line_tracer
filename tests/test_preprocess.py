import cv2
import numpy as np
import pytest
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
from preprocess import Preprocessor

@pytest.fixture
def prep():
    return Preprocessor(os.path.abspath(os.path.join(os.path.dirname(__file__), "../config.yaml")))

def test_simple_line(prep):
    img = np.zeros((200,200,3), dtype=np.uint8)
    cv2.line(img, (100,0), (100,199), (255,255,255), 5)
    noise = (np.random.rand(200,200) > 0.98).astype(np.uint8) * 255
    img[noise==255] = (255,255,255)

    mask = prep.process(img)
    unique = set(np.unique(mask))
    assert unique.issubset({0,255})
    assert (mask==255).sum() / mask.size > 0.05
