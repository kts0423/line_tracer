# src/preprocess.py
import cv2
import numpy as np
import yaml

class Preprocessor:
    """
    전처리 파이프라인 최적화:
    1) Gaussian Blur로 노이즈 저감
    2) Grayscale + 히스토그램 평활화
    3) Adaptive + Otsu 이진화 OR
    4) 경량 Morphology (3×3 Close→Open)
    """
    def __init__(self, cfg_path="../config.yaml"):
        cfg = yaml.safe_load(open(cfg_path))
        morph_cfg = cfg.get('morphology', {})
        self.kernel_size = morph_cfg.get('kernel_size', 3)
        self.min_area_factor = morph_cfg.get('min_area_factor', 0.5)
        self.max_area_factor = morph_cfg.get('max_area_factor', 2.0)

    def process(self, frame):
        # 1) Gaussian Blur (빠른 연산)
        filtered = cv2.GaussianBlur(frame, (5, 5), 0)
        # 2) Grayscale + Histogram Equalization
        gray = cv2.cvtColor(filtered, cv2.COLOR_BGR2GRAY)
        gray_eq = cv2.equalizeHist(gray)

        # 3) 이진화: Adaptive + Otsu OR
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

        # 4) 경량 Morphology
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (self.kernel_size, self.kernel_size))
        m = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k, iterations=1)
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN,  k, iterations=1)

        # 이진화 결과 보장
        return (m > 0).astype(np.uint8) * 255
