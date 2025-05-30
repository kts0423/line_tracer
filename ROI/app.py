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

# ─────────────────────────────────────
# 📷 Picamera2 초기화
try:
    from picamera2 import Picamera2
    picam2 = Picamera2()
    picam2.configure(picam2.create_video_configuration(main={"size": (320, 240)}))
    picam2.start()
    time.sleep(1)
except Exception as e:
    print(f"[WARN] Picamera2 initialization failed: {e}")

# ─────────────────────────────────────
# 🔌 DummySerial (디버깅용)
class DummySerial:
    def write(self, data):
        print(f"[MOCK WRITE] {data.decode().strip()}")

# ─────────────────────────────────────
# 🧭 아두이노 포트 탐색 및 연결
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
    except Exception as e:
        print(f"[ERROR] Failed to connect to Arduino: {e}")
        ser = DummySerial()
else:
    print("[WARN] No Arduino port found, using DummySerial.")
    ser = DummySerial()

# ─────────────────────────────────────
# 🛰️ 시리얼 전송 쓰레드
control_queue = queue.Queue()

def serial_worker():
    while True:
        if ser:
            try:
                cmd = control_queue.get(timeout=1)
                ser.write(cmd.encode('ascii'))
                print(f"[SEND] {cmd.strip()}")
            except queue.Empty:
                pass
        time.sleep(0.01)

threading.Thread(target=serial_worker, daemon=True).start()

def send_control_async(err_filtered, direction):
    err_filtered = max(-50, min(50, err_filtered))
    command = f"E:{err_filtered} {direction}\n"
    control_queue.put(command)

# ─────────────────────────────────────
# 🧠 검정선 추출 (grayscale + inverse binary)
def extract_black_only(roi):
    gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
    
    # 선 대비 기준값: 100 정도로 높여서 명확히 필터링
    _, mask = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY_INV)

    # 노이즈 제거 + 선 연결
    kernel = np.ones((7, 7), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    result = cv2.bitwise_and(roi, roi, mask=mask)
    return result, mask

# ─────────────────────────────────────
# 🔎 선 중심점 검출
def find_line_center(binary):
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    valid = [c for c in contours if cv2.contourArea(c) > 5]  # 면적 기준 완화
    if not valid:
        return -1, None
    largest = max(valid, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(largest)
    cx = x + w // 2
    return cx, largest

# ─────────────────────────────────────
# 📺 Flask 영상 스트리밍 + 제어 루프
last_err = 0
alpha = 0.8

def gen():
    global last_err
    last_send_time = 0

    while True:
        if not picam2:
            continue

        frame = picam2.capture_array()
        h, w = frame.shape[:2]
        center_x = w // 2

        roi_h = int(h * 0.4)
        roi_y = int(h * 0.4)
        roi = frame[roi_y:roi_y + roi_h, :]

        roi_cleaned, binary = extract_black_only(roi)
        cx, contour = find_line_center(binary)

        now = time.time()
        if cx == -1:
            direction = "B"
            err_filtered = -999
            print("[DEBUG] ❌ 선을 못 봤음 - 후진")
            if now - last_send_time > 0.1:
                send_control_async(0, "B")
                last_send_time = now
        else:
            err = cx - center_x
            err_filtered = int(alpha * last_err + (1 - alpha) * err)
            last_err = err_filtered

            if abs(err_filtered) < 5:
                err_filtered = 0

            direction = "F"
            if now - last_send_time > 0.1:
                send_control_async(err_filtered, direction)
                last_send_time = now

            print(f"[DEBUG] 선 중심 x좌표: {cx} → err: {err_filtered}")
            cv2.drawContours(roi, [contour], -1, (0, 255, 0), 2)
            cv2.circle(roi, (cx, roi_h // 2), 5, (0, 0, 255), -1)

        # 안내선 및 정보 출력
        cv2.line(frame, (0, roi_y), (w, roi_y), (0, 255, 255), 1)
        cv2.line(frame, (0, roi_y + roi_h), (w, roi_y + roi_h), (0, 255, 255), 1)
        cv2.line(roi, (center_x, 0), (center_x, roi_h), (255, 0, 0), 1)
        frame[roi_y:roi_y + roi_h, :] = roi
        cv2.putText(frame, f"err = {err_filtered}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        # 스트리밍용 JPEG 인코딩
        ret, jpeg = cv2.imencode('.jpg', cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
        if not ret:
            continue
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')

# ─────────────────────────────────────
# 🌐 Flask 라우팅
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

# ─────────────────────────────────────
# 🚀 실행
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)
