# src/main.py
import cv2
import yaml
from camera_control  import CameraController
from preprocess      import Preprocessor
from contour_tracker import ContourTracker
from serial_comm     import SerialComm

def main():
    # 1) 설정 로드
    cfg = yaml.safe_load(open("config.yaml"))

    # 2) 모듈 초기화
    cam_ctl = CameraController("config.yaml")
    prep    = Preprocessor  ("config.yaml")
    tracker = ContourTracker("config.yaml")
    comm    = SerialComm    ("config.yaml")

    try:
        prev_roi_y = None
        while True:
            # 3) 프레임 취득
            frame = cam_ctl.get_frame()

            # 4) ROI 그레이스케일 추출 (선택적으로 cam_ctl.auto_adjust 호출)
            # gray = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)     # 이미 BGR
            # cam_ctl.auto_adjust(gray)  # 필요하면 활성화

            # 5) 전처리 → 마스크
            mask = prep.process(frame)

            # 6) 컨투어 트래킹 → cx, roi_y
            cx, roi_y = tracker.track(mask, prev_roi_y)
            prev_roi_y = roi_y

            # 7) 아두이노로 에러값 전송
            error_x = cx - (frame.shape[1] // 2)
            comm.send(error_x)

            # 8) 디버그 화면
            dbg = frame.copy()
            cv2.circle(dbg, (cx, roi_y), 5, (0,255,0), -1)
            cv2.putText(dbg, f"err={error_x}", (10,30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 2)
            cv2.imshow("LineTracer", dbg)
            if cv2.waitKey(1) & 0xFF == 27:  # ESC
                break

    finally:
        cam_ctl.stop()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
