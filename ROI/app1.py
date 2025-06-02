# import serial
# import serial.tools.list_ports
# import threading
# import queue
# import time
# import cv2
# import numpy as np
# from flask import Flask, Response, render_template

# app = Flask(__name__)
# picam2 = None

# # ─────────────────────────────────────
# # 📷 Picamera2 초기화
# try:
#     from picamera2 import Picamera2
#     picam2 = Picamera2()
#     picam2.configure(picam2.create_video_configuration(main={"size": (320, 240)}))
#     picam2.start()
#     time.sleep(1)
# except Exception as e:
#     print(f"[WARN] Picamera2 initialization failed: {e}")

# # ─────────────────────────────────────
# # 🔌 DummySerial (디버깅용)
# class DummySerial:
#     def write(self, data):
#         print(f"[MOCK WRITE] {data.decode().strip()}")

# # ─────────────────────────────────────
# # 🧭 아두이노 포트 탐색 및 연결
# def find_arduino_port():
#     ports = list(serial.tools.list_ports.comports())
#     for p in ports:
#         if "Arduino" in p.description or "ttyACM" in p.device or "ttyUSB" in p.device:
#             return p.device
#     return None

# arduino_port = find_arduino_port()
# ser = None
# if arduino_port:
#     try:
#         ser = serial.Serial(arduino_port, 9600, timeout=1)
#         time.sleep(2)
#         print(f"[OK] Arduino connected on {arduino_port}")
#     except Exception as e:
#         print(f"[ERROR] Failed to connect to Arduino: {e}")
#         ser = DummySerial()
# else:
#     print("[WARN] No Arduino port found, using DummySerial.")
#     ser = DummySerial()

# # ─────────────────────────────────────
# # 🛰️ 시리얼 전송 쓰레드
# control_queue = queue.Queue()

# def serial_worker():
#     while True:
#         if ser:
#             try:
#                 cmd = control_queue.get(timeout=1)
#                 ser.write(cmd.encode('ascii'))
#                 print(f"[SEND] {cmd.strip()}")
#             except queue.Empty:
#                 pass
#         time.sleep(0.01)

# threading.Thread(target=serial_worker, daemon=True).start()

# # ─────────────────────────────────────
# # 📺 영상 분석 및 제어 루프
# def gen():
#     last_send_time = 0
#     last_frame_time = 0

#     while True:
#         if not picam2:
#             continue

#         now = time.time()
#         if now - last_frame_time < 0.1:  # 제한 FPS ≈ 10
#             continue
#         last_frame_time = now

#         frame = picam2.capture_array()
#         frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2RGB)
#         h, w = frame.shape[:2]

#         # ROI 설정 (중앙 폭 30%, 하단 35%)
#         roi_y = int(h * 0.5)
#         roi_h = int(h * 0.3)
#         roi_w = int(w * 0.2)
#         roi_x = (w - roi_w) // 2

#         roi = frame[roi_y:roi_y + roi_h, roi_x:roi_x + roi_w]
#         gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)

#         mask = cv2.adaptiveThreshold(
#             gray, 255,
#             cv2.ADAPTIVE_THRESH_MEAN_C,
#             cv2.THRESH_BINARY_INV,
#             15, 3
#         )

#         contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

#         direction = "B"
#         if contours:
#             valid = [c for c in contours if cv2.contourArea(c) > 100]
#             if valid:
#                 largest = max(valid, key=cv2.contourArea)
#                 x, y, w_box, h_box = cv2.boundingRect(largest)
#                     # 잘못된 오탐 방지: 테이프는 가늘고 세로로 긴 특징이 있음
#                 aspect_ratio = h_box / w_box if w_box > 0 else 0
#                 if aspect_ratio > 1.5 and w_box > 5:
#                     lane_center = x + w_box // 2
#                     err = lane_center - (roi_w // 2)

#                     if abs(err) < 10:
#                         direction = "F"
#                     elif err < 0:
#                         direction = "L"
#                     else:
#                         direction = "R"

#                     cv2.rectangle(roi, (x, y), (x + w_box, y + h_box), (0, 255, 0), 1)
#                     cv2.circle(roi,(lane_center, roi_h // 2), 1, (0, 0, 255), 1)
#                     print(f"[DEBUG] cx={lane_center}, err={err}, dir={direction}")
#             else:
#                 print("[DEBUG] No valid contours → B")
#                 direction = "B"
#                 continue

#         else:
#             print("[DEBUG] No contours found → B")

#         if now - last_send_time > 0.2:
#             control_queue.put(f"{direction}\n")
#             last_send_time = now

#         # ROI 시각화
#         cv2.rectangle(frame,
#                       (roi_x, roi_y),
#                       (roi_x + roi_w, roi_y + roi_h),
#                       (0, 255, 255), 1)

#         cv2.putText(frame, f"dir = {direction}", (10, 30),
#                     cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

#         # JPEG 인코딩
#         ret, jpeg = cv2.imencode('.jpg', cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
#         if not ret:
#             continue
#         yield (b'--frame\r\n'
#                b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')

# # ─────────────────────────────────────
# # 🌐 Flask 라우팅
# @app.route('/')
# def index():
#     return render_template('index.html')

# @app.route('/video_feed')
# def video_feed():
#     return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

# # ─────────────────────────────────────
# # 🚀 실행
# if __name__ == '__main__':
#     app.run(host='0.0.0.0', port=5000, threaded=True)