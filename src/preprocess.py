# src/preprocess.py
import cv2
import numpy as np
import yaml

class Preprocessor:
    """
    Preprocessor applies robust masking to detect dark line even under noise and reflection.
    Steps:
    1) Bilateral Filter
    2) Grayscale + Histogram Equalization
    3) Adaptive Threshold + Otsu (OR)
    4) Multi-scale Morphology (3x3 & 5x5)
    """
    def __init__(self, cfg_path="../config.yaml"):
        cfg = yaml.safe_load(open(cfg_path))
        morph_cfg = cfg.get('morphology', {})
        self.min_area_factor = morph_cfg.get('min_area_factor', 0.5)
        self.max_area_factor = morph_cfg.get('max_area_factor', 2.0)

    def process(self, frame):
        # 1) Bilateral filter
        filtered = cv2.bilateralFilter(frame, d=5, sigmaColor=75, sigmaSpace=75)
        # 2) Grayscale & equalize
        gray = cv2.cvtColor(filtered, cv2.COLOR_BGR2GRAY)
        gray_eq = cv2.equalizeHist(gray)

        # 3) Adaptive + Otsu threshold
        adaptive = cv2.adaptiveThreshold(
            gray_eq, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            blockSize=11, C=2
        )
        _, otsu = cv2.threshold(
            gray_eq, 0, 255,
            cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )
        mask = cv2.bitwise_or(adaptive, otsu)

        # 4) Multi-scale morphology
        k3 = cv2.getStructuringElement(cv2.MORPH_RECT, (3,3))
        k5 = cv2.getStructuringElement(cv2.MORPH_RECT, (5,5))
        m1 = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k3, iterations=2)
        m1 = cv2.morphologyEx(m1, cv2.MORPH_OPEN,  k3, iterations=1)
        m2 = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k5, iterations=1)
        combined = cv2.bitwise_or(m1, m2)

        # Binary output
        return (combined > 0).astype(np.uint8) * 255
