#!/usr/bin/env python3
# src/main.py

import cv2
import yaml
import threading
import time
import os
import signal
import numpy as np
from concurrent.futures import ProcessPoolExecutor
from camera_control  import CameraController
from serial_comm     import SerialComm
from flask import Flask, request, jsonify, render_template, Response

# === 설정 파일 & 전역 모드 ===
CONFIG_PATH = "config.yaml"
config      = yaml.safe_load(open(CONFIG_PATH))
mode        = 'auto'
_last_mtime = None
running     = True

def load_config():
    global config, _last_mtime
    mtime = os.path.getmtime(CONFIG_PATH)
    if _last_mtime is None or mtime > _last_mtime:
        config = yaml.safe_load(open(CONFIG_PATH))
        _last_mtime = mtime
        print(f"[CONFIG] reloaded at {time.ctime(mtime)}")

# === Flask 앱 & 엔드포인트 ===
app = Flask(__name__, template_folder='../templates')

@app.route('/')
def index():
    return render_template('index.html')

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

@app.route('/control', methods=['POST'])
def control():
    data = request.get_json() or {}
    cmd = data.get('cmd')
    if mode == 'manual' and cmd and comm.ser:
        try:
            comm.ser.write(f"{cmd}\n".encode())
            return jsonify(success=True, cmd=cmd)
        except Exception as e:
            return jsonify(success=False, error=str(e)), 500
    return jsonify(success=False, error='invalid command or mode'), 400

# === 워커 함수 (별도 프로세스) ===
def process_frame_worker(frame, cfg, cfg_path):
    import cv2, numpy as np
    from preprocess      import Preprocessor
    from contour_tracker import ContourTracker

    cam_cfg   = cfg['camera']
    morph_cfg = cfg.get('morphology', {})

    # ROI 계산
    h, w   = frame.shape[:2]
    roi_h  = int(h * cam_cfg['roi_fraction'])
    roi_y  = h - roi_h
    roi    = frame[roi_y:h, :w]

    # 전처리 & 컨투어
    prep    = Preprocessor(cfg_path)
    tracker = ContourTracker(cfg_path)
    mask    = prep.process(roi)
    cx, _   = tracker.track(mask, roi_y)

    # error 계산
    error_x = cx - (w // 2)

    # 자동 튜닝: mask coverage 기반 kernel size
    cov    = np.count_nonzero(mask) / mask.size
    kernel = morph_cfg.get('kernel_size', 3)
    if cov < 0.05:
        kernel = max(3, kernel - 2)
    elif cov > 0.2:
        kernel = min(11, kernel + 2)

    # ROI fraction 적응
    offset_norm = abs(error_x) / (w // 2)
    roi_frac    = cam_cfg['roi_fraction']
    if offset_norm > 0.3:
        roi_frac = min(0.5, roi_frac + 0.05)
    else:
        roi_frac = max(0.2, roi_frac - 0.01)

    return error_x, cx, roi_y, tracker.alpha_cx, kernel, roi_frac

# === 안전 종료 설정 ===
def sig_handler(sig, frame):
    global running
    running = False

signal.signal(signal.SIGINT, sig_handler)
signal.signal(signal.SIGTERM, sig_handler)

if __name__ == "__main__":
    load_config()
    cam_ctl = CameraController(CONFIG_PATH)
    comm    = SerialComm(CONFIG_PATH)

    # Flask 서버 시작
    threading.Thread(
        target=lambda: app.run(host='0.0.0.0', port=5001, threaded=True),
        daemon=True
    ).start()

    # 워커 풀 생성
    executor = ProcessPoolExecutor(max_workers=2)
    futures  = []

    try:
        while running:
            load_config()

            # 1) 프레임 캡처 & 크기 획득
            frame = cam_ctl.get_frame()
            h, w  = frame.shape[:2]

            # 2) 자동 노출 (ROI 기반)
            roi_h    = int(h * config['camera']['roi_fraction'])
            roi_y    = h - roi_h
            gray_roi = cv2.cvtColor(frame[roi_y:h, :w], cv2.COLOR_BGR2GRAY)
            cam_ctl.auto_adjust(gray_roi)

            # 3) 워커에 처리 제출
            futures.append(executor.submit(
                process_frame_worker, frame, config, CONFIG_PATH
            ))

            # 4) 완료된 작업 수집
            for f in futures.copy():
                if f.done():
                    futures.remove(f)
                    err, cx, ry, a_cx, k, rf = f.result()

                    # 5) 설정 값 업데이트
                    config['smoothing']['alpha_cx']     = a_cx
                    config['morphology']['kernel_size'] = k
                    config['camera']['roi_fraction']    = rf

                    # 6) 자동 모드 시 시리얼 전송
                    if mode == 'auto':
                        comm.send(err)

                    # 7) 디버그 화면 표시
                    dbg = frame.copy()
                    cv2.rectangle(dbg, (0, ry), (w, h), (255,0,0), 2)
                    cv2.circle(dbg, (cx, ry), 5, (0,255,0), -1)
                    cv2.putText(dbg, f"err={err}", (10, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 2)
                    cv2.imshow("LineTracer", dbg)

            # 8) ESC 키로 종료
            if cv2.waitKey(1) & 0xFF == 27:
                running = False

    finally:
        executor.shutdown(wait=True)
        cam_ctl.stop()
        cv2.destroyAllWindows()
        print("Exited.")
