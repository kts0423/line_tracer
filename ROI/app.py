import serial
import serial.tools.list_ports
import threading
import queue
import time
import cv2
import numpy as np
from flask import Flask, Response, render_template

app = Flask(__name__)
picam2 = None

try:
    from picamera2 import Picamera2
    picam2 = Picamera2()
    picam2.configure(picam2.create_video_configuration(main={"size": (320, 240)}))
    picam2.start()
    time.sleep(1)
except:
    print("[WARN] Picamera2 initialization failed")

# 시리얼 포트 자동 탐색
def find_arduino_port():
    ports = list(serial.tools.list_ports.comports())
    for p in ports:
        if "Arduino" in p.description or "ttyACM" in p.device or "ttyUSB" in p.device:
            return p.device
    return None

arduino_port = find_arduino_port()
ser = None
if arduino_port:
    try:
        ser = serial.Serial(arduino_port, 9600, timeout=1)
        time.sleep(2)
        print(f"[OK] Arduino connected on {arduino_port}")
    except:
        print("[ERROR] Failed to connect to Arduino")

control_queue = queue.Queue()

def serial_worker():
    while True:
        if ser:
            try:
                cmd = control_queue.get(timeout=1)
                ser.write(cmd.encode('ascii'))  # ASCII 인코딩
            except queue.Empty:
                pass
        time.sleep(0.01)

threading.Thread(target=serial_worker, daemon=True).start()

def send_control_async(err_filtered):
    err_filtered = max(-50, min(50, err_filtered)) if err_filtered != 9999 else 9999
    cmd = f"E:{err_filtered}\n"
    control_queue.put(cmd)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

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

last_err = 0
alpha = 0.8

def gen():
    global last_err
    while True:
        if not picam2:
            continue

        frame = picam2.capture_array()
        h, w = frame.shape[:2]
        center_x = w // 2

        # ROI 설정
        roi_y = int(h * 0.55)
        roi_h = int(h / 6)
        roi = frame[roi_y:roi_y + roi_h, :]

        gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        _, binary = cv2.threshold(blur, 100, 255, cv2.THRESH_BINARY_INV)

        cx, contour = find_line_center(binary)

        if cx == -1:
            err_filtered = 9999
        else:
            err = cx - center_x
            err_filtered = int(alpha * last_err + (1 - alpha) * err)
            last_err = err_filtered

            cv2.drawContours(roi, [contour], -1, (0, 255, 0), 2)
            cv2.circle(roi, (cx, roi_h // 2), 5, (255, 0, 0), -1)

        print(f"[ERR] err_filtered = {err_filtered}")
        send_control_async(err_filtered)

        # 시각적 표시
        cv2.line(roi, (center_x, 0), (center_x, roi_h), (0, 0, 255), 1)
        frame[roi_y:roi_y + roi_h, :] = roi
        cv2.putText(frame, f"err = {err_filtered}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2)

        ret, jpeg = cv2.imencode('.jpg', cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
        if not ret:
            continue
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)


##병목현상발견견