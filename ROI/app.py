from flask import Flask, render_template, Response, jsonify
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
# PiCamera 세팅 (320×240)
picam2 = Picamera2()
picam2.configure(picam2.create_preview_configuration(
    main={"format": "RGB888", "size": (320, 240)}
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
        # 시리얼 속도를 115200 bps로 맞춤
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
# line_lost_counter는 더 이상 필요 없으므로 제거했습니다.

# ─────────────────────────────────────────────────────────────────────────────
# gen_frames(): ROI 조정 + 선 이탈 즉시 보정 + 0~180 steer
def gen_frames():
    global last_send_time, last_steer_angle

    while True:
        frame = picam2.capture_array()
        h, w, _ = frame.shape

        # 1) ROI 설정: 화면 세로 50%~95%, 가로 전체
        roi_top = int(h * 0.1)
        roi_bottom = int(h * 0.8)
        roi_width = w
        roi_x = 0
        roi = frame[roi_top:roi_bottom, roi_x:roi_x + roi_width]

        # 2) 그레이스케일 + 블러
        gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)

        # 3) Adaptive Threshold → clean_mask
        binary = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_MEAN_C,
            cv2.THRESH_BINARY_INV,
            blockSize=21,
            C=15
        )
        kernel = np.ones((3, 3), np.uint8)
        clean_mask = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)

        # 4) 컨투어 찾기
        contours, _ = cv2.findContours(clean_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # 기본값: 선을 못 찾으면 이전 steer_angle 유지, 전진
        direction = "F"
        steer_angle = last_steer_angle

        # ESC 초기화(5초) 이후부터만 주행 제어
        if time.time() - start_time >= ESC_INIT_DELAY:
            if len(contours) > 0:
                largest = max(contours, key=cv2.contourArea)
                area = cv2.contourArea(largest)
                # 선이 충분히 커야만 새로 steer_angle 계산
                if area > 50:
                    # (A) fitLine → 벡터(vx,vy), 점(x0,y0)
                    vx, vy, x0, y0 = cv2.fitLine(largest, cv2.DIST_L2, 0, 0.01, 0.01)
                    vx, vy = float(vx), float(vy)
                    if vy < 0:
                        vx, vy = -vx, -vy

                    # (B) 벡터 절대 각도 & 수직 아래(π/2) 차이 계산
                    angle_line = math.atan2(vy, vx)
                    angle_des = math.pi / 2
                    angle_error = angle_line - angle_des
                    if angle_error > math.pi:
                        angle_error -= 2 * math.pi
                    elif angle_error < -math.pi:
                        angle_error += 2 * math.pi
                    deg_error = angle_error * (180.0 / math.pi)

                    # (C) 컨투어 중심 기반 수평 오프셋 계산
                    M = cv2.moments(largest)
                    if M["m00"] != 0:
                        cx = int(M["m10"] / M["m00"])
                    else:
                        cx = roi_width // 2
                    offset_x = cx - (roi_width // 2)

                    # (D) 보정 계수 설정
                    gain_angle = 30.0
                    gain_offset = 0.5

                    # (E) 작은 각도 무시 (±5° 이내)
                    if abs(deg_error) < 5.0:
                        int_error_angle = 0
                    else:
                        int_error_angle = int(deg_error * (gain_angle / 100.0))

                    offset_total = int(offset_x * gain_offset)

                    # (F) 최종 steer_angle 계산 (0~180)
                    steer_angle = 90 + int_error_angle + offset_total
                    steer_angle = max(0, min(180, steer_angle))
                    direction = "F"

                    last_steer_angle = steer_angle
                else:
                    # contour는 있지만 너무 작으면 선 없다고 간주 → 유지
                    steer_angle = last_steer_angle
                    direction = "F"
            else:
                # contour가 없으면 이전 steer_angle 그대로 유지, 전진
                steer_angle = last_steer_angle
                direction = "F"
        else:
            # 초기화 시간 안 지나면 대기 상태 (정지)
            steer_angle = 90
            direction = "S"

        # (G) 시각화: ROI 내부에 clean_mask(흑백)를 RGB로 변환해 덮어쓰기
        mask_rgb = cv2.cvtColor(clean_mask, cv2.COLOR_GRAY2RGB)
        frame[roi_top:roi_bottom, roi_x:roi_x + roi_width] = mask_rgb

        # 벡터 시각화 (contour가 있는 경우에만)
        if len(contours) > 0 and cv2.contourArea(largest) > 50:
            draw_x0 = roi_x + int(x0)
            draw_y0 = roi_top + int(y0)
            draw_x1 = int(draw_x0 + vx * 50)
            draw_y1 = int(draw_y0 + vy * 50)
            cv2.line(frame, (draw_x0, draw_y0), (draw_x1, draw_y1), (0, 255, 0), 2)
            drawCX = roi_x + cx
            drawCY = roi_top + (roi_bottom - roi_top) // 2
            cv2.circle(frame, (drawCX, drawCY), 5, (0, 0, 255), -1)

        # (H) 주행 명령을 매 0.1초마다 전송
        current_time = time.time()
        if current_time - last_send_time >= 0.1:
            cmd = f"E:{steer_angle} D:{direction}\n"
            control_queue.put(cmd)
            last_send_time = current_time

        # (I) 디버그용 텍스트 + 테두리
        dir_text = f"Angle:{steer_angle} Dir:{direction}"
        cv2.rectangle(frame, (roi_x, roi_top), (roi_x + roi_width, roi_bottom), (255, 0, 0), 2)
        cv2.putText(frame, dir_text, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        # (J) 최종 스트림 인코딩 & 출력
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        ret, buffer = cv2.imencode('.jpg', frame_bgr)
        if not ret:
            continue

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/log_data')
def log_data():
    return jsonify(serial_logs)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
