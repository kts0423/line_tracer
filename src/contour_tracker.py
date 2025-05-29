# src/contour_tracker.py
import cv2
import numpy as np
import yaml

class ContourTracker:
    """
    ContourTracker handles:
      1) Contour detection with dynamic area filtering
      2) 1st-degree polynomial (polyfit) for cx calculation
      3) Exponential smoothing for cx and ROI y
    """
    def __init__(self, cfg_path="../config.yaml"):
        cfg = yaml.safe_load(open(cfg_path))
        smooth_cfg = cfg.get('smoothing', {})
        morph_cfg  = cfg.get('morphology', {})
        camera_cfg = cfg.get('camera', {})

        self.alpha_cx       = smooth_cfg.get('alpha_cx', 0.3)
        self.alpha_roi      = smooth_cfg.get('alpha_roi', 0.2)
        self.min_area_factor= morph_cfg.get('min_area_factor', 0.5)
        self.max_area_factor= morph_cfg.get('max_area_factor', 2.0)
        self.roi_fraction   = camera_cfg.get('roi_fraction', 0.33)

        self.cx_smooth      = None
        self.roi_y_smooth   = None
        self.hist_areas     = []

    def track(self, mask, prev_roi_y=None):
        """
        mask: binary mask (0/255)
        prev_roi_y: previous ROI y-coordinate (optional)
        returns: (cx_smooth, roi_y_smooth)
        """
        h, w = mask.shape

        # 1) Contour detection
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        areas = [cv2.contourArea(c) for c in cnts]
        # dynamic area thresholds
        if areas:
            self.hist_areas += areas
            recent = self.hist_areas[-50:]
            med = np.median(recent)
            min_area = med * self.min_area_factor
            max_area = med * self.max_area_factor
        else:
            min_area = 500
            max_area = w * h * 0.5

        valid = [c for c in cnts if min_area < cv2.contourArea(c) < max_area]

        # 2) Polyfit for cx
        cx = w // 2
        if valid:
            c = max(valid, key=cv2.contourArea)
            pts = c.squeeze()
            if pts.ndim == 1:
                pts = pts[np.newaxis, :]
            if len(pts) > 10:
                ys = pts[:, 1]
                xs = pts[:, 0]
                a, b = np.polyfit(ys, xs, 1)
                cy = h - 1
                cx = int(a * cy + b)

        # 3) Exponential smoothing for cx
        if self.cx_smooth is None:
            self.cx_smooth = cx
        else:
            self.cx_smooth = int(
                self.alpha_cx * cx + (1 - self.alpha_cx) * self.cx_smooth
            )

        # ROI y fallback calculation
        roi_y = prev_roi_y if prev_roi_y is not None else int(h * (1 - self.roi_fraction))
        # ROI y exponential smoothing
        if self.roi_y_smooth is None:
            self.roi_y_smooth = roi_y
        else:
            self.roi_y_smooth = int(
                self.alpha_roi * roi_y + (1 - self.alpha_roi) * self.roi_y_smooth
            )

        return self.cx_smooth, self.roi_y_smooth
