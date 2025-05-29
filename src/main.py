#!/usr/bin/env python3
# src/main.py

import cv2
import yaml
import threading
import time
import queue
import os
import signal
from camera_control  import CameraController
from preprocess      import Preprocessor
from contour_tracker import ContourTracker
from serial_comm     import SerialComm
from flask import Flask, request, jsonify, render_template, Response

# === 설정 파일 경로 & 자동 재로드 ===
CONFIG_PATH = "config.yaml"
_last_mtime = None
config = {}

def load_config():
    global config, _last_mtime
    mtime = os.path.getmtime(CONFIG_PATH)
    if _last_mtime is None or mtime > _last_mtime:
        config = yaml.safe_load(open(CONFIG_PATH))
        _last_mtime = mtime
        print(f"[CONFIG] reloaded at {time.ctime(mtime)}")

# === Flask 앱 설정 ===
app = Flask(__name__, template_folder='../templates')
mode = 'auto'  # 'auto' 또는 'manual'

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/config', methods=['GET'])
def get_config():
    return jsonify(config)

@app.route('/reload', methods=['POST'])
def reload_config():
    load_config()
    return jsonify(success=True, config=config)

@app.route('/mode', methods=['GET', 'POST'])
def handle_mode():
    global mode
    if request.method == 'POST':
        data = request.get_json() or {}
        m = data.get('mode', 'auto')
        if m in ('auto', 'manual'):
            mode = m
            print(f"[MODE] set to {mode}")
            return jsonify(success=True, mode=mode)
        return jsonify(success=False, error='invalid mode'), 400
    return jsonify(mode=mode)

# MJPEG 비디오 스트림
@app.route('/video_feed')
def video_feed():
    def gen():
        while running:
            frame = cam_ctl.get_frame()
            ret, buf = cv2.imencode('.jpg', frame)
            if not ret:
                continue
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + buf.tobytes() + b'\r\n')
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

# Arduino 시리얼 모니터 스트림 (SSE)
@app.route('/serial_stream')
def serial_stream():
    def gen():
        last = None
        while running:
            if comm.ser and hasattr(comm.ser, 'in_waiting') and comm.ser.in_waiting:
                line = comm.ser.readline().decode(errors='ignore').strip()
                if line and line != last:
                    yield f"data: {line}\n\n"
                    last = line
            time.sleep(0.05)
    return Response(gen(), mimetype='text/event-stream')

# RC카 직접 제어 API (manual 모드용)
@app.route('/control', methods=['POST'])
def control():
    data = request.get_json() or {}
    cmd = data.get('cmd')
    if cmd and comm.ser and mode == 'manual':
        try:
            comm.ser.write(f"{cmd}\n".encode())
            return jsonify(success=True, cmd=cmd)
        except Exception as e:
            return jsonify(success=False, error=str(e)), 500
    return jsonify(success=False, error='invalid command or mode'), 400

# === 로그 파일 ===
os.makedirs('logs', exist_ok=True)
LOG_PATH = os.path.join('logs', f"run_{int(time.time())}.csv")
with open(LOG_PATH, 'w') as f:
    f.write('timestamp,error_x,exposure,gain,cx,roi_y\n')

# === 안전 종료 제어 ===
running = True

def signal_handler(sig, frame):
    global running
    running = False

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

if __name__ == '__main__':
    # 설정 로드
    load_config()

    # 모듈 초기화
    cam_ctl = CameraController(CONFIG_PATH)
    prep    = Preprocessor  (CONFIG_PATH)
    tracker = ContourTracker(CONFIG_PATH)
    comm    = SerialComm    (CONFIG_PATH)

    # 시리얼 전송 쓰레드 (자동 모드용)
    q_err = queue.Queue()
    def serial_thread():
        while running:
            try:
                err = q_err.get(timeout=0.1)
            except queue.Empty:
                continue
            comm.send(err)
    th_serial = threading.Thread(target=serial_thread, daemon=True)
    th_serial.start()

    # Flask 서버 실행
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=5001, threaded=True), daemon=True).start()

    prev_roi_y = None
    try:
        while running:
            load_config()
            frame = cam_ctl.get_frame()
            h, w = frame.shape[:2]
            roi_h = int(h * config['camera']['roi_fraction'])
            roi_y = h - roi_h
            roi   = frame[roi_y:h, :w]

            # 자동 노출
            gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            cam_ctl.auto_adjust(gray_roi)

            # 전처리
            mask = prep.process(roi)

            # 라인트래킹
            cx, prev_roi_y = tracker.track(mask, prev_roi_y)
            error_x = cx - (w // 2)

            # 로그 기록
            with open(LOG_PATH, 'a') as f:
                f.write(f"{time.time()},{error_x},{cam_ctl.current_exp},"
                        f"{cam_ctl.current_gain},{cx},{prev_roi_y}\n")

            # 자동 모드인 경우에만 시리얼 전송
            if mode == 'auto':
                q_err.put(error_x)

            # 디버그 화면
            dbg = frame.copy()
            cv2.rectangle(dbg, (0, roi_y), (w, h), (255,0,0), 2)
            cv2.circle(dbg, (cx, prev_roi_y), 5, (0,255,0), -1)
            cv2.putText(dbg, f"err={error_x}", (10,30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 2)
            cv2.imshow('LineTracer', dbg)
            if cv2.waitKey(1) & 0xFF == 27:
                break
    except Exception as e:
        print('[ERROR]', e)
    finally:
        running = False
        th_serial.join()
        cam_ctl.stop()
        cv2.destroyAllWindows()
        print('Exited.')