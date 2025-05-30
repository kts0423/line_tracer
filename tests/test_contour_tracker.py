# tests/test_contour_tracker.py
import numpy as np
import cv2
import sys, os
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
from contour_tracker import ContourTracker

@pytest.fixture
def tracker():
    return ContourTracker(os.path.abspath(os.path.join(os.path.dirname(__file__), "../config.yaml")))

def make_mask_line_curve(shape=(100,200), slope=0.5, intercept=50, thickness=3):
    """
    shape: (h,w)
    y -> x = slope*y + intercept
    곡선 대신 직선이지만, polyfit 테스트용 mask 생성
    """
    h, w = shape
    mask = np.zeros((h,w), dtype=np.uint8)
    for y in range(h):
        x = int(slope * y + intercept)
        if 0 <= x < w:
            cv2.line(mask, (x, y), (x, y), 255, thickness)
    return mask

def test_track_center_line(tracker):
    # 수평 중앙(직선)만 테스트
    mask = np.zeros((100,200), dtype=np.uint8)
    cv2.line(mask, (100,0), (100,99), 255, 2)
    cx, ry = tracker.track(mask)
    assert abs(cx - 100) < 5

def test_track_sloped_line(tracker):
    # slope=0.5, intercept=20
    mask = make_mask_line_curve((100,200), slope=0.5, intercept=20)
    cx, ry = tracker.track(mask)
    # 하단 y=99 -> x≈0.5*99+20≈69.5
    assert abs(cx - 70) < 5
