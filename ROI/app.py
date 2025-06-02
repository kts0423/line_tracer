from flask import Flask, render_template, Response, jsonify
from picamera2 import Picamera2
import cv2
import numpy as np
import time
import serial
import serial.tools.list_ports
import threading
import queue

app = Flask(__name__)

# ─────── 카메라 설정
picam2 = Picamera2()
picam2.configure(picam2.create_preview_configuration(
    main={"format": "RGB888", "size": (320, 240)}
))
picam2.start()
time.sleep(2)

# ─────── 아두이노 포트 자동 검색
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
        ser = serial.Serial(port, 9600, timeout=1)
        print(f"[OK] Arduino connected on {port}")
        time.sleep(2)
    except Exception as e:
        print(f"[ERROR] Arduino connection failed: {e}")
else:
    print("[WARN] No Arduino port found.")

# ─────── 시리얼 송신 쓰레드
control_queue = queue.Queue()
serial_logs = []

def serial_worker():
    while True:
        try:
            cmd = control_queue.get(timeout=1)
            if ser:
                ser.write(cmd.encode('ascii'))
                print(f"[SEND] {cmd.strip()}")
                serial_logs.append(f"[SEND] {cmd.strip()}")
                serial_logs[:] = serial_logs[-100:]
        except queue.Empty:
            pass
        time.sleep(0.5)  # 0.5초 주기 송신

threading.Thread(target=serial_worker, daemon=True).start()

# ─────── 라인트레이서 처리
last_steer_angle = None
last_speed_pwm = None
last_send_time = 0
last_reverse_time = 0


def gen_frames():
    global last_steer_angle, last_speed_pwm, last_send_time, last_reverse_time
    while True:
        frame = picam2.capture_array()
        h, w, _ = frame.shape

        roi_top = int(h * 0.4)
        roi_bottom = int(h * 0.7)
        roi_width = w // 6
        roi_x = (w - roi_width) // 2
        roi = frame[roi_top:roi_bottom, roi_x:roi_x + roi_width]

        gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)

        binary = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_MEAN_C,
            cv2.THRESH_BINARY_INV,
            blockSize=15,
            C=10
        )

        mid = binary.shape[1] // 2
        left = binary[:, :mid]
        right = binary[:, mid:]

        left_count = cv2.countNonZero(left)
        right_count = cv2.countNonZero(right)
        total_white = left_count + right_count

        gain = 0.3
        max_error = 300
        speed_pwm = 1570

        if total_white < 100:
            steer_angle = 90  # 직진
            if time.time() - last_reverse_time < 2:
                speed_pwm = 1500 # 정지
            else:
                speed_pwm = 1440
                last_reverse_time = time.time()
        else:
            error = right_count - left_count
            error = max(-max_error, min(max_error, error))
            steer_angle = int(90 + error * gain)
            steer_angle = max(80, min(100, steer_angle))

        current_time = time.time()
        if current_time - last_send_time >= 0.5:
            cmd = f"E:{steer_angle} S:{speed_pwm}\n"
            control_queue.put(cmd)
            last_steer_angle = steer_angle
            last_speed_pwm = speed_pwm
            last_send_time = current_time

        direction = f"▶ Steering: {steer_angle}°"
        cv2.rectangle(frame, (roi_x, roi_top), (roi_x + roi_width, roi_bottom), (255, 0, 0), 2)

        cv2.putText(frame, direction, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        ret, buffer = cv2.imencode('.jpg', frame_bgr)
        if not ret:
            continue
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

# ─────── 웹 라우팅
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/log_data')
def log_data():
    return jsonify(serial_logs)

# ─────── 실행
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
