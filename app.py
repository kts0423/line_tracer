import serial
import serial.tools.list_ports
import threading
import queue
import time
import cv2
import numpy as np
from flask import Flask, Response, render_template, request, jsonify

app = Flask(__name__)
picam2 = None
try:
    from picamera2 import Picamera2
    picam2 = Picamera2()
    picam2.configure(picam2.create_video_configuration(main={"size": (320, 240)}))
    picam2.start()
    time.sleep(1)
except:
    print("⚠ Picamera2 초기화 실패")

# -------------------- 기본 변수 --------------------
last_err = 0
alpha = 0.8
current_mode = "auto"
last_cmd = "None"
speed_us = 1560
log_history = []
serial_log_lines = []

# -------------------- 아두이노 연결 --------------------
def find_arduino_port():
    ports = serial.tools.list_ports.comports()
    for p in ports:
        if "Arduino" in p.description or "ttyACM" in p.device:
            return p.device
    return None

arduino_port = find_arduino_port()
ser = None
if arduino_port:
    try:
        ser = serial.Serial(arduino_port, 9600, timeout=1)
        time.sleep(2)
        print(f"✅ 아두이노 연결됨: {arduino_port}")
    except:
        print("❌ 시리얼 연결 실패")

control_queue = queue.Queue()

# -------------------- 시리얼 송신 --------------------
def serial_worker():
    while True:
        if ser:
            try:
                cmd = control_queue.get(timeout=1)
                if isinstance(cmd, str):
                    ser.write(cmd.encode('ascii'))
            except queue.Empty:
                pass
        time.sleep(0.01)

# -------------------- 시리얼 수신 --------------------
def serial_reader():
    while True:
        if ser and ser.in_waiting:
            line = ser.readline().decode(errors="ignore").strip()
            if line:
                print(f"[Arduino] {line}")
                serial_log_lines.append(f"{time.strftime('%H:%M:%S')} → {line}")
                if len(serial_log_lines) > 50:
                    serial_log_lines.pop(0)
        time.sleep(0.05)

threading.Thread(target=serial_worker, daemon=True).start()
threading.Thread(target=serial_reader, daemon=True).start()

# -------------------- Flask 라우팅 --------------------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/control')
def control():
    global last_cmd, speed_us
    cmd = request.args.get("cmd")
    spd = request.args.get("speed", type=int, default=1560)
    speed_us = spd
    last_cmd = cmd
    log_history.append(f"{time.strftime('%H:%M:%S')} → {cmd}")
    if len(log_history) > 20:
        log_history.pop(0)
    print(f"📦 수동 명령 수신: {cmd}")
    control_queue.put(f"{cmd}\n")
    return ('', 204)

@app.route('/mode')
def mode():
    global current_mode
    m = request.args.get("type", "auto")
    current_mode = m
    log_history.append(f"{time.strftime('%H:%M:%S')} → MODE:{m.upper()}")
    control_queue.put(f"MODE:{m.upper()}\n")
    return ('', 204)

@app.route('/status')
def status():
    return jsonify({
        "mode": current_mode,
        "last_cmd": last_cmd,
        "speed": speed_us,
        "log": log_history[-20:]
    })

@app.route('/serial_log')
def serial_log():
    return jsonify(serial_log_lines[-20:])

# -------------------- 영상 프레임 생성 --------------------
def find_line_center(binary):
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    valid = [c for c in contours if cv2.contourArea(c) > 100]
    if not valid:
        return -1, None
    largest = max(valid, key=cv2.contourArea)
    M = cv2.moments(largest)
    if M["m00"] == 0:
        return -1, None
    cx = int(M["m10"] / M["m00"])
    return cx, largest

def send_control_async(err_filtered, speed_us):
    err_filtered = max(-50, min(50, err_filtered))
    speed_us = max(1460, min(1560, speed_us))
    if abs(speed_us - 1500) < 5:
        speed_us = 1500
    cmd = f"E:{err_filtered} S:{speed_us}\n"
    control_queue.put(cmd)

def gen():
    global last_err, current_mode
    while True:
        if not picam2:
            continue
        frame = picam2.capture_array()
        h, w = frame.shape[:2]
        center_x = w // 2
        roi_y = int(h * 0.6)
        roi_h = int(h / 4)
        roi = frame[roi_y:roi_y + roi_h, :]
        gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        binary = cv2.threshold(blur, 100, 255, cv2.THRESH_BINARY_INV)[1]
        cx, contour = find_line_center(binary)

        err = err_filtered = err_diff = 0
        if cx != -1:
            err = cx - center_x
            err_filtered = int(alpha * last_err + (1 - alpha) * err)
            err_diff = err_filtered - last_err
            last_err = err_filtered
            cv2.drawContours(roi, [contour], -1, (0, 255, 0), 2)
            cv2.circle(roi, (cx, roi_h // 2), 5, (255, 0, 0), -1)

        cv2.line(roi, (center_x, 0), (center_x, roi_h), (0, 0, 255), 1)
        frame[roi_y:roi_y + roi_h, :] = roi
        cv2.putText(frame, f"err = {err_filtered}", (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)
        cv2.putText(frame, f"diff = {err_diff}", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)

        if current_mode == "auto":
            send_control_async(err_filtered, speed_us)

        ret, jpeg = cv2.imencode('.jpg', cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
        if not ret:
            continue
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)
