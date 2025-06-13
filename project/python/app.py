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
# 0) 모드 변수 및 락
mode_lock = threading.Lock()
current_mode = "UNKNOWN"   # "AUTO" or "MANUAL" or "UNKNOWN"

# ─────────────────────────────────────────────────────────────────────────────
# 1) PiCamera 세팅 (160×120) – 해상도를 절반으로 줄임
picam2 = Picamera2()
picam2.configure(picam2.create_preview_configuration(
    main={"format": "RGB888", "size": (160, 120)}
))
picam2.start()
time.sleep(2)  # 카메라 워밍업

# ─────────────────────────────────────────────────────────────────────────────
# 2) 아두이노 포트 자동 검색 & 연결
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
        # 시리얼 버퍼 초기화
        ser.reset_input_buffer()
        ser.reset_output_buffer()
    except Exception as e:
        print(f"[ERROR] Arduino connection failed: {e}")
        ser = None
else:
    print("[WARN] No Arduino port found.")

# ─────────────────────────────────────────────────────────────────────────────
# 3) Python → Arduino 시리얼 전송 쓰레드
control_queue = queue.Queue()
serial_logs = []

def serial_worker():
    global ser
    while True:
        try:
            cmd = control_queue.get(timeout=0.1)
            if ser and ser.is_open:
                try:
                    ser.write(cmd.encode('ascii'))
                    serial_logs.append(f"[SEND] {cmd.strip()}")
                    # 최근 100개만 보관
                    serial_logs[:] = serial_logs[-100:]
                except serial.SerialException as e:
                    print(f"[ERROR] Serial write failed: {e}")
                    # 포트 닫혔거나 오류 발생 시 재연결 시도
                    try: ser.close()
                    except: pass
                    ser = None
                    time.sleep(1)
                    new_port = find_arduino_port()
                    if new_port:
                        try:
                            ser = serial.Serial(new_port, 115200, timeout=1)
                            print(f"[INFO] Serial reconnected to {new_port}")
                        except Exception as e2:
                            print(f"[WARN] Reconnect failed: {e2}")
        except queue.Empty:
            pass
        time.sleep(0.01)

threading.Thread(target=serial_worker, daemon=True).start()

# ─────────────────────────────────────────────────────────────────────────────
# 4) Arduino → Python 시리얼 수신 쓰레드 (MODE:AUTO / MODE:MANUAL 감지)
def serial_reader():
    global ser, current_mode
    buffer = b""
    while True:
        if ser and ser.is_open:
            try:
                data = ser.read(ser.in_waiting or 1)
                if data:
                    buffer += data
                    # '\n' 단위로 버퍼 쪼개기
                    if b'\n' in buffer:
                        lines = buffer.split(b'\n')
                        for ln in lines[:-1]:
                            text = ln.decode('ascii', errors='ignore').strip()
                            # "MODE:AUTO" 또는 "MODE:MANUAL" 파싱
                            if text.startswith("MODE:"):
                                mode_str = text.split("MODE:")[-1]
                                if mode_str in ("AUTO", "MANUAL"):
                                    with mode_lock:
                                        current_mode = mode_str
                                    print(f"[INFO] Received MODE:{mode_str} from Arduino")
                        buffer = lines[-1]
            except serial.SerialException:
                # 포트가 닫혔거나 에러 발생 시
                try: ser.close()
                except: pass
                ser = None
        time.sleep(0.05)

threading.Thread(target=serial_reader, daemon=True).start()

# ─────────────────────────────────────────────────────────────────────────────
# 5) ESC 초기화 대기 시간 등 제어 관련 변수
ESC_INIT_DELAY = 5
start_time = time.time()
last_send_time = 0
last_steer_angle = 90
last_cx = None

# ─────────────────────────────────────────────────────────────────────────────
# 6) gen_frames(): 모드 분기 + ROI/이진화/컨투어 + 제어용 시리얼 송신
def gen_frames():
    global last_send_time, last_steer_angle, last_cx

    while True:
        # 1) 현재 모드 읽어오기
        with mode_lock:
            mode = current_mode

        # 2) 카메라 프레임 캡처
        frame = picam2.capture_array()
        h, w, _ = frame.shape

        # ─── 수동 모드(MANUAL)인 경우: 원본 프레임만 스트리밍하고, 정지 명령을 Arduino로 보냄
        if mode == "MANUAL":
            # 수동 모드에서는 항상 정지(Angle=90, Dir=S) 상태를 보내자
            now = time.time()
            if now - last_send_time >= 0.1:
                control_queue.put("E:90 D:S\n")
                last_send_time = now

            # 단순 PiCamera 원본 영상을 JPEG으로 인코딩해 스트리밍
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            ret, buffer = cv2.imencode('.jpg', frame_bgr)
            if not ret:
                continue
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            time.sleep(0.01)
            continue  # 다음 루프

        # ─── 이 시점부터는 mode가 "AUTO" 또는 "UNKNOWN"인 경우 ───
        # (UNKNOWN: Arduino에서 아직 모드 문자를 못 받았거나, 초기 상태)

        # 3) ROI 설정 (화면 세로 10%~80%, 가로 전체) -> roi_top 을 h * 0.1 으로 고정
        roi_top = int(h * 0.1)
        roi_bottom = int(h * 0.80)
        roi_height = roi_bottom - roi_top
        roi_width = w
        roi_x = 0
        roi = frame[roi_top:roi_bottom, roi_x:roi_x + roi_width]

        # 4) 그레이스케일 → 블러 → Adaptive Threshold → 모폴로지 → clean_mask 생성
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

        # 5) 컨투어 찾기 → 필터링하여 valid_contours 리스트 생성
        all_contours, _ = cv2.findContours(
            clean_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
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
            # ROI 상단 절반 컨투어 무시
            if cy < (roi_height * 0.5):
                continue
            # last_cx 필터: 너무 멀리 벗어나면 무시
            if last_cx is not None and abs(cx - last_cx) > (roi_width * 0.5):
                continue
            valid_contours.append((cnt, cx, cy, area))

        # 6) steer_angle, direction 기본값 설정
        direction = "F"
        steer_angle = last_steer_angle

        # 7) AUTO 모드일 때만 실제 제어 로직 수행 (단, ESC_INIT_DELAY 이후부터)
        if mode == "AUTO" and (time.time() - start_time >= ESC_INIT_DELAY) and valid_contours:
            # 7-A) 면적이 가장 큰 컨투어 선택
            cnt, cx, cy, area = max(valid_contours, key=lambda x: x[3])

            # 7-B) fitLine으로 벡터(vx, vy), 한 점(x0, y0) 구하기
            vx_arr, vy_arr, x0_arr, y0_arr = cv2.fitLine(cnt, cv2.DIST_L2, 0, 0.01, 0.01)
            vx = float(vx_arr[0])
            vy = float(vy_arr[0])
            if vy < 0:
                vx, vy = -vx, -vy

            x0_rel = float(x0_arr[0])
            y0_rel = float(y0_arr[0])

            # 7-C) lookahead 예측: ROI 상단까지 벡터 확장
            if vy != 0:
                t = -y0_rel / vy
            else:
                t = 0.0
            lookahead_x_rel = x0_rel + vx * t

            # 7-D) offset 계산
            lookahead_offset = lookahead_x_rel - (roi_width / 2)
            curr_offset = cx - (roi_width / 2)

            gain_offset = 0.5
            gain_lookahead = 1.5
            total_offset = int(curr_offset * gain_offset + lookahead_offset * gain_lookahead)

            # 7-E) fitLine 각도 오차 보정
            angle_line = math.atan2(vy, vx)
            angle_des = math.pi / 2
            angle_error = angle_line - angle_des
            if angle_error > math.pi:
                angle_error -= 2 * math.pi
            elif angle_error < -math.pi:
                angle_error += 2 * math.pi
            deg_error = angle_error * (180.0 / math.pi)

            if abs(deg_error) < 1.0:
                int_error_angle = 0
            else:
                gain_angle = 30.0
                int_error_angle = int(deg_error * (gain_angle / 100.0))

            # 7-F) 최종 steer_angle 계산 (0~180)
            steer_angle = 90 + int_error_angle + total_offset
            steer_angle = max(0, min(180, steer_angle))
            direction = "F"
            last_steer_angle = steer_angle
            last_cx = cx

            # 7-G) 시각화: fitLine 벡터와 lookahead 점 그리기
            draw_x0 = int(x0_rel + roi_x)
            draw_y0 = int(y0_rel + roi_top)
            draw_x1 = int(draw_x0 + vx * 50)
            draw_y1 = int(draw_y0 + vy * 50)
            cv2.line(frame, (draw_x0, draw_y0), (draw_x1, draw_y1), (0, 255, 0), 2)
            look_x = int(lookahead_x_rel + roi_x)
            look_y = roi_top
            cv2.circle(frame, (look_x, look_y), 5, (0, 0, 255), -1)

        else:
            # ─── ① ESC_INIT_DELAY가 아직 안 지났거나  
            # ─── ② mode != "AUTO" 이거나  
            # ─── ③ valid_contours가 비었을 때(라인 인식 실패)  
            #
            # 이전에는 여기서 바로 정지(steer_angle=90, direction="S")했지만,
            # 이제는 valid_contours가 비었을 경우 마지막 steering 각도로 전진 유지
            if mode == "AUTO" and (time.time() - start_time >= ESC_INIT_DELAY) and not valid_contours:
                # 라인이 잠시 사라진 경우 → 이전에 계산한 last_steer_angle 유지, 전진(F)
                steer_angle = last_steer_angle
                direction = "F"
                # last_cx는 변경하지 않음
            else:
                # ESC_INIT_DELAY가 지나지 않았거나 mode가 AUTO가 아니거나(수동 등) 라인 복원이 어려운 경우
                steer_angle = 90
                direction = "S"

        # 9) clean_mask를 ROI 부분에 덮어쓰기 (시각화)
        mask_rgb = cv2.cvtColor(clean_mask, cv2.COLOR_GRAY2RGB)
        frame[roi_top:roi_bottom, roi_x:roi_x + roi_width] = mask_rgb

        # 10) 시리얼 송신 (0.1초 간격)
        now = time.time()
        if now - last_send_time >= 0.1:
            cmd = f"E:{steer_angle} D:{direction}\n"
            control_queue.put(cmd)
            last_send_time = now

        # 11) 디버그용 텍스트 + ROI 테두리
        dir_text = f"Mode:{mode}  Angle:{steer_angle}  Dir:{direction}"
        cv2.rectangle(frame, (roi_x, roi_top), (roi_x + roi_width, roi_bottom), (255, 0, 0), 2)
        cv2.putText(frame, dir_text, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        # 12) 스트림 인코딩 & 출력
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

@app.route('/current_mode')
def current_mode_api():
    with mode_lock:
        return jsonify({"mode": current_mode})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

##ss
