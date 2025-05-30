# src/camera_control.py
import time
import numpy as np
import yaml

# Picamera2가 없는 환경(Windows) 대비 Stub 클래스 정의
try:
    from picamera2 import Picamera2
except ImportError:
    class Picamera2:
        def __init__(self): pass
        def configure(self, cfg): pass
        def start(self): pass
        def stop(self): pass
        def capture_array(self):
            # 테스트용 검정 프레임
            return np.zeros((100, 100, 3), dtype=np.uint8)
        def create_preview_configuration(self, main):
            return None
        def set_controls(self, ctrls): pass

class CameraController:
    """
    CameraController handles PiCamera2 setup and auto exposure adjustment.
    """
    def __init__(self, cfg_path="../config.yaml"):
        cfg = yaml.safe_load(open(cfg_path))
        cam_cfg = cfg['camera']
        ae_cfg  = cfg['auto_exposure']

        self.picam2 = Picamera2()
        # 구성
        preview_cfg = self.picam2.create_preview_configuration(
            main={
                "format": "RGB888",
                "size": (cam_cfg['frame_width'], cam_cfg['frame_height'])
            }
        )
        self.picam2.configure(preview_cfg)
        self.picam2.start()
        time.sleep(1.5)

        self.current_exp  = cam_cfg['initial_exposure']
        self.current_gain = cam_cfg['initial_gain']
        self.ae_cfg = ae_cfg
        # 수동 노출 설정
        self.picam2.set_controls({
            "AeEnable": False,
            "AwbEnable": False,
            "ExposureTime": self.current_exp,
            "AnalogueGain": self.current_gain
        })

    def get_frame(self):
        """Raw frame 배열(RGB888) 반환"""
        return self.picam2.capture_array()

    def auto_adjust(self, gray):
        """
        gray: 그레이스케일 ROI 이미지
        퍼센타일 기반 자동 노출·게인 보정
        """
        # 1) 퍼센타일 계산
        lo = np.percentile(gray, self.ae_cfg['low_pct'])
        hi = np.percentile(gray, self.ae_cfg['high_pct'])
        cover_lo = np.count_nonzero(gray < lo) / gray.size
        cover_hi = np.count_nonzero(gray > hi) / gray.size

        # 2) 퍼센타일 범위 적응
        if cover_lo < self.ae_cfg['target_cover_min']:
            self.ae_cfg['low_pct'] = max(1, self.ae_cfg['low_pct'] - 1)
        elif cover_lo > self.ae_cfg['target_cover_max']:
            self.ae_cfg['low_pct'] = min(self.ae_cfg['high_pct'] - 1,
                                         self.ae_cfg['low_pct'] + 1)
        if cover_hi < self.ae_cfg['target_cover_min']:
            self.ae_cfg['high_pct'] = min(99, self.ae_cfg['high_pct'] + 1)
        elif cover_hi > self.ae_cfg['target_cover_max']:
            self.ae_cfg['high_pct'] = max(self.ae_cfg['low_pct'] + 1,
                                          self.ae_cfg['high_pct'] - 1)

        # 3) 목표 밝기 중앙 계산
        target_mid = ((self.ae_cfg['target_cover_min'] +
                       self.ae_cfg['target_cover_max']) / 2) * 255
        b = (lo + hi) / 2
        delta = target_mid - b

        # 4) 노출/게인 변경량
        step_exp = int((delta / self.ae_cfg['max_delta']) * 5000)
        new_exp  = int(np.clip(self.current_exp + step_exp, 5000, 100000))
        new_gain = float(np.clip(1.0 + (delta / self.ae_cfg['max_delta']) * 1.5, 1.0, 4.0))

        # 5) 충분 변화 시 적용
        if abs(new_exp - self.current_exp) > 1000 or abs(new_gain - self.current_gain) > 0.1:
            self.picam2.set_controls({
                "ExposureTime": new_exp,
                "AnalogueGain": new_gain
            })
            self.current_exp, self.current_gain = new_exp, new_gain

    def stop(self):
        self.picam2.stop()
