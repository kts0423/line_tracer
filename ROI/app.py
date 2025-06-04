from flask import Flask, render_template, Response, jsonify, request
from picamera2 import Picamera2
import cv2
import numpy as np
import time
import serial
import serial.tools.list_ports
import threading
import queue
import math

app = Flask(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# PiCamera 세팅 (160×120)
picam2 = Picamera2()
picam2.configure(picam2.create_preview_configuration(
    main={"format": "RGB888", "size": (160, 120)}
))
picam2.start()
time.sleep(2)  # 카메라 워밍업

# ─────────────────────────────────────────────────────────────────────────────
# 아두이노 포트 자동 검색
def find_arduino_port():
    ports = list(serial.tools.list_ports.comports())
    print("[DEBUG] 연결된 시리얼 포트:")
    for p in ports:
        print(f" - {p.device}: {p.description}")
        if "Arduino" in p.description or "ttyACM" in p.device or "ttyUSB" in p.device:
            print(f"[DEBUG] 선택된 포트: {p.device}")
            return p.device
    print("[DEBUG] Arduino 포트 자동검색 실패")
    return None

port = find_arduino_port()
ser = None
if port:
    try:
        ser = serial.Serial(port, 115200, timeout=1)
        print(f"[OK] Arduino connected on {port} at 115200 bps")
        time.sleep(2)
    except Exception as e:
        print(f"[ERROR] Arduino connection failed: {e}")
else:
    print("[WARN] No Arduino port found.")

# ─────────────────────────────────────────────────────────────────────────────
# 시리얼 전송 전용 쓰레드
control_queue = queue.Queue()
serial_logs = []

def serial_worker():
    while True:
        try:
            cmd = control_queue.get(timeout=0.1)
            if ser:
                ser.write(cmd.encode('ascii'))
                serial_logs.append(f"[SEND] {cmd.strip()}")
                serial_logs[:] = serial_logs[-100:]
        except queue.Empty:
            pass
        time.sleep(0.01)

threading.Thread(target=serial_worker, daemon=True).start()

# ─────────────────────────────────────────────────────────────────────────────
# ESC 초기화 대기 시간 (초 단위)
ESC_INIT_DELAY = 5
start_time = time.time()
last_send_time = 0
last_steer_angle = 90

# 마지막에 정상적으로 인식된 라인 중심 X 좌표 (ROI 기준)
last_cx = None

# 자동주행이 켜져 있는지 여부 (초기값 False)
is_running = False

# ─────────────────────────────────────────────────────────────────────────────
# gen_frames(): ROI 조정 + 그레이스케일 기반 이진화 + 필터링 + “앞쪽 예측” 강화 + 0~180 steer
def gen_frames():
    global last_send_time, last_steer_angle, last_cx, is_running, start_time

    while True:
        frame = picam2.capture_array()
        h, w, _ = frame.shape

        # 1) ROI 설정: 화면 세로 10%~80%, 가로 전체
        roi_top = int(h * 0.10)
        roi_bottom = int(h * 0.80)
        roi_height = roi_bottom - roi_top
        roi_width = w
        roi_x = 0
        roi = frame[roi_top:roi_bottom, roi_x:roi_x + roi_width]

        # 2) 그레이스케일 변환 + 블러 → Adaptive Threshold 이진화
        gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
        gray_blur = cv2.GaussianBlur(gray, (3, 3), 0)
        binary = cv2.adaptiveThreshold(
            gray_blur, 255,
            cv2.ADAPTIVE_THRESH_MEAN_C,
            cv2.THRESH_BINARY_INV,
            blockSize=21,
            C=15
        )
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        clean_mask = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)

        # 3) 컨투어 찾기
        all_contours, _ = cv2.findContours(
            clean_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        # 필터링된 컨투어만 보관
        valid_contours = []
        for cnt in all_contours:
            area = cv2.contourArea(cnt)
            if area < 50:
                continue

            M = cv2.moments(cnt)
            if M["m00"] == 0:
                continue
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])

            # ROI 상단 절반(벽 쪽) 컨투어 무시
            if cy < (roi_height * 0.5):
                continue

            # last_cx 필터 (너무 멀리 벗어나면 무시)
            if last_cx is not None:
                if abs(cx - last_cx) > (roi_width * 0.5):
                    continue

            valid_contours.append((cnt, cx, cy, area))

        # 기본 steer/방향 값
        direction = "F"
        steer_angle = last_steer_angle

        # 초기화 시간(5초) 이내는 정지
        if time.time() - start_time < ESC_INIT_DELAY or not is_running:
            steer_angle = 90
            direction = "S"
        else:
            # 자동주행 켜져 있고 초기화 시간 경과 후 컨투어가 있을 때
            if valid_contours:
                cnt, cx, cy, area = max(valid_contours, key=lambda x: x[3])

                # (A) 현재 라인 방향 벡터 구하기 (fitLine)
                vx, vy, x0, y0 = cv2.fitLine(cnt, cv2.DIST_L2, 0, 0.01, 0.01)
                vx, vy = float(vx), float(vy)
                if vy < 0:
                    vx, vy = -vx, -vy  # 항상 위쪽으로 향하도록

                # lookahead 예측을 위해 ROI 기준 상대 좌표
                x0_rel = x0
                y0_rel = y0

                # (B) 라인이 화면 밖으로 연장될 때 X 좌표 예측 (lookahead)
                if vy != 0:
                    t = -y0_rel / vy
                else:
                    t = 0
                lookahead_x_rel = x0_rel + vx * t

                # (C) lookahead_offset: 예측 지점이 ROI 중앙에서 얼마나 벗어나는지
                lookahead_offset = lookahead_x_rel - (roi_width / 2)

                # (D) 현재 중심 오프셋: cx - (roi_width/2)
                curr_offset = cx - (roi_width / 2)

                # (E) 두 오프셋을 섞어서 steer_angle 계산
                gain_offset = 0.5
                gain_lookahead = 1.5
                total_offset = int(curr_offset * gain_offset + lookahead_offset * gain_lookahead)

                # (F) fitLine 각도 오차 기반 보정
                angle_line = math.atan2(vy, vx)
                angle_des = math.pi / 2
                angle_error = angle_line - angle_des
                if angle_error > math.pi:
                    angle_error -= 2 * math.pi
                elif angle_error < -math.pi:
                    angle_error += 2 * math.pi
                deg_error = angle_error * (180.0 / math.pi)

                # (G) 작은 각도 무시
                if abs(deg_error) < 5.0:
                    int_error_angle = 0
                else:
                    gain_angle = 30.0
                    int_error_angle = int(deg_error * (gain_angle / 100.0))

                # (H) 최종 steer_angle 계산
                steer_angle = 90 + int_error_angle + total_offset
                steer_angle = max(0, min(180, steer_angle))
                direction = "F"
                last_steer_angle = steer_angle

                # 정상 인식된 cx 저장
                last_cx = cx
            else:
                # 컨투어가 없으면 이전 steer_angle 유지, 전진
                steer_angle = last_steer_angle
                direction = "F"

        # (I) 시각화: ROI 내부에 clean_mask(흑백)를 RGB로 덮어쓰기
        mask_rgb = cv2.cvtColor(clean_mask, cv2.COLOR_GRAY2RGB)
        frame[roi_top:roi_bottom, roi_x:roi_x + roi_width] = mask_rgb

        # (J) 시리얼 송신 (0.1초 간격)
        current_time = time.time()
        if current_time - last_send_time >= 0.1:
            cmd = f"E:{steer_angle} D:{direction}\n"
            control_queue.put(cmd)
            last_send_time = current_time

        # (K) 디버그용 텍스트 + 테두리
        dir_text = f"Run:{'On' if is_running else 'Off'} Angle:{steer_angle} Dir:{direction}"
        cv2.rectangle(frame, (roi_x, roi_top), (roi_x + roi_width, roi_bottom), (255, 0, 0), 2)
        cv2.putText(frame, dir_text, (5, 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        # (L) 스트림 인코딩 & 출력
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        ret, buffer = cv2.imencode('.jpg', frame_bgr)
        if not ret:
            continue

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

# ─────────────────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/log_data')
def log_data():
    return jsonify(serial_logs)

# ─────────────────────────────────────────────────────────────────────────────
# 시작 POST 엔드포인트
@app.route('/start', methods=['POST'])
def start_driving():
    global is_running, start_time
    is_running = True
    start_time = time.time()  # ESC 초기화 시간 리셋
    return jsonify({"status": "running"})

# 정지 POST 엔드포인트
@app.route('/stop', methods=['POST'])
def stop_driving():
    global is_running
    is_running = False
    return jsonify({"status": "stopped"})

# ─────────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
