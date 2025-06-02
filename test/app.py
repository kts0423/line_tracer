from flask import Flask, render_template, Response, jsonify
from picamera2 import Picamera2
import cv2
import numpy as np
import time
import serial
import serial.tools.list_ports
import threading
import queue

white_history = []

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
        time.sleep(2)  # 시리얼 초기화 대기
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
                # 로그는 최대 100개까지만 유지
                serial_logs[:] = serial_logs[-100:]
        except queue.Empty:
            pass
        time.sleep(0.5)

threading.Thread(target=serial_worker, daemon=True).start()

# ─────── ESC 초기화 대기 시간 설정
ESC_INIT_DELAY = 5  # seconds
start_time = time.time()

# ─────── 라인트레이서 처리
def gen_frames():
    global start_time
    MIN_HISTORY_LENGTH = 20
    DEFAULT_WHITE_THRESHOLD = 100
    last_send_time = 0
    last_reverse_time = 0

    # 조향 파라미터 (튜닝 가능)
    alpha = 0.3   # 오프셋(error) 가중치
    beta  = 0.8   # 곡선 기울기(deviation) 가중치
    straight_thresh = 10.0  # 직선 판별용 각도 차이 임계값(도 단위)

    while True:
        # 1. 카메라 프레임 획득
        frame = picam2.capture_array()  # RGB888 형식
        h, w, _ = frame.shape

        # 2. ROI 설정 (화면 세로 30%~50%, 가로 중앙 1/3)
        roi_top    = int(h * 0.3)
        roi_bottom = int(h * 0.5)
        roi_width  = w // 3
        roi_x      = (w - roi_width) // 2
        roi = frame[roi_top:roi_bottom, roi_x:roi_x + roi_width]

        # 3. Grayscale 변환 + Blur
        gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)

        # 4. Adaptive Threshold로 이진화 (흰 선: 255, 배경: 0)
        binary = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_MEAN_C,
            cv2.THRESH_BINARY_INV,
            blockSize=21,
            C=15
        )

        # 5. Morphological Opening (노이즈 제거)
        kernel = np.ones((3, 3), np.uint8)
        clean_mask = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
        binary = clean_mask

        # 6. 좌/우 흰색 픽셀 개수 계산
        mid = binary.shape[1] // 2
        left  = binary[:, :mid]
        right = binary[:, mid:]
        left_count  = cv2.countNonZero(left)
        right_count = cv2.countNonZero(right)
        total_white = left_count + right_count

        # 7. Adaptive Threshold 보정용 히스토리 갱신
        white_history.append(total_white)
        white_history[:] = white_history[-30:]  # 최근 30프레임만 보관
        if len(white_history) < MIN_HISTORY_LENGTH:
            adaptive_threshold = DEFAULT_WHITE_THRESHOLD
        else:
            adaptive_threshold = max(30, int(np.mean(white_history) * 0.1))

        # 8. 오차(error) 계산 (좌우 흰색 픽셀 차이)
        error = right_count - left_count
        max_error = 300
        error = max(-max_error, min(max_error, error))

        # 9. 선형 피팅으로 “대표 선”의 방향(기울기) 구하기
        #    충분한 흰색 픽셀(total_white >= adaptive_threshold)일 때만 수행
        angle_line = None
        if total_white >= adaptive_threshold and total_white > 50:
            # findNonZero가 검출한 (x, y) 좌표(하지만 ROI 기준이므로 x,y가 ROI 좌표)
            pts = cv2.findNonZero(binary)
            if pts is not None and len(pts) >= 10:
                # cv2.fitLine: returns [vx, vy, x0, y0]
                [vx, vy, x0, y0] = cv2.fitLine(pts, cv2.DIST_L2, 0, 0.01, 0.01)
                # 방향 벡터 (vx, vy) → 각도 계산 (deg)
                # atan2(vy, vx) : x축 대비 각도 (0~180도)
                angle_line = float(np.degrees(np.arctan2(vy, vx)))
                # 적절히 0~180 범위로 정규화
                if angle_line < 0:
                    angle_line += 180.0

        # 10. 조향각(steer_angle) 계산
        #     - 직선: steer = 90 + alpha * error
        #     - 곡선: steer = 90 + alpha * error + beta * (angle_line - 90)
        if angle_line is not None:
            deviation = angle_line - 90.0  # 오른쪽 휨이면 음수, 왼쪽 휨이면 양수
            # 직선/곡선 판단
            if abs(deviation) < straight_thresh:
                # 직선 구간
                steer_offset = alpha * error
                steer_angle = int(90 + steer_offset)
            else:
                # 곡선 구간
                steer_offset = alpha * error
                steer_curve  = beta * deviation
                steer_angle  = int(90 + steer_offset + steer_curve)
        else:
            # 선형 피팅 실패(흰선이 충분치 않거나 검출 안 됨) → 예외 처리용으로 offset만 사용
            steer_offset = alpha * error
            steer_angle  = int(90 + steer_offset)

        # steer_angle 범위 제한 (예: 60~120도)
        steer_angle = max(60, min(120, steer_angle))

        # 11. 진행 방향(direction) 결정
        if total_white < adaptive_threshold:
            # 흰선이 너무 작게 검출되면 후진 혹은 정지
            if time.time() - last_reverse_time < 2:
                direction = "S"  # 최근에 후진한 지 2초 안 → 정지
            else:
                direction = "B"  # 후진
                last_reverse_time = time.time()
        else:
            direction = "F"  # 흰선이 충분히 보임 → 전진

        # ESC 초기화 딜레이 동안에는 무조건 정지
        if time.time() - start_time < ESC_INIT_DELAY:
            direction = "S"

        # 12. 일정 주기(0.5초)마다 아두이노로 명령 전송
        current_time = time.time()
        if current_time - last_send_time >= 0.5:
            cmd = f"E:{steer_angle} D:{direction}\n"
            control_queue.put(cmd)
            last_send_time = current_time

        # 13. 디버깅용 텍스트 (화면에 표시)
        direction_text = f"Angle: {steer_angle}, Dir: {direction}, Thresh: {adaptive_threshold}"
        cv2.rectangle(frame, (roi_x, roi_top), (roi_x + roi_width, roi_bottom), (255, 0, 0), 2)
        cv2.putText(frame, direction_text, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        # 14. Clean mask(이진화 결과) 시각화: 원본 프레임에 덮어쓰기
        mask_bgr = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
        frame[roi_top:roi_bottom, roi_x:roi_x + roi_width] = mask_bgr

        # 15. Flask 스트리밍용 JPEG 인코딩 & yield
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
    return Response(gen_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/log_data')
def log_data():
    return jsonify(serial_logs)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug = True)
