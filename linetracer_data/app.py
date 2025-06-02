from flask import Flask, render_template, Response, request
from picamera2 import Picamera2
import serial
import serial.tools.list_ports
import time
import cv2
import os

app = Flask(__name__)

# ─────── PiCamera 설정 (320x240)
picam2 = Picamera2()
picam2.configure(picam2.create_preview_configuration(main={"format": "RGB888", "size": (320, 240)}))
picam2.start()
time.sleep(2)

# ─────── 시리얼 포트 자동 연결
def find_arduino_port():
    ports = serial.tools.list_ports.comports()
    for p in ports:
        if "Arduino" in p.description or "ttyACM" in p.device or "ttyUSB" in p.device:
            return p.device
    return None

port = find_arduino_port()
ser = serial.Serial(port, 9600, timeout=1) if port else None
if ser:
    print(f"[OK] Arduino 연결됨: {port}")
    time.sleep(2)
else:
    print("[WARN] Arduino를 찾을 수 없음")

# ─────── 폴더 준비
os.makedirs("dataset/images", exist_ok=True)
os.makedirs("dataset/labels", exist_ok=True)

frame_id = 0
last_frame = None

@app.route('/')
def index():
    return render_template('index.html')

def gen_frames():
    global last_frame
    while True:
        frame = picam2.capture_array()
        last_frame = frame.copy()
        _, buffer = cv2.imencode('.jpg', frame)
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/save/<int:angle>', methods=['POST'])
def save_frame(angle):
    global frame_id, last_frame
    if last_frame is not None:
        img_path = f'dataset/images/{frame_id:05}.jpg'
        label_path = f'dataset/labels/{frame_id:05}.txt'
        cv2.imwrite(img_path, last_frame)
        with open(label_path, 'w') as f:
            f.write(str(angle))

        print(f"[SAVE] {img_path} / 조향각: {angle}")

        if ser:
            ser.write(f"{angle}\n".encode('ascii'))
            print(f"[SEND] 시리얼 전송: {angle}")

        frame_id += 1
    return ('', 204)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
