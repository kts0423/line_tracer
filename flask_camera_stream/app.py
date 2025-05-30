from flask import Flask, render_template, Response
from picamera2 import Picamera2
import cv2

app = Flask(__name__)

# PiCamera2 초기화
picam2 = Picamera2()
config = picam2.create_preview_configuration(main={"format": "RGB888", "size": (640, 480)})
picam2.configure(config)
picam2.start()

def generate_frames():
    while True:
        try:
            frame = picam2.capture_array()
            # frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            ret, buffer = cv2.imencode('.jpg', frame)
            if not ret:
                print("JPEG 인코딩 실패")
                continue
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        except Exception as e:
            print("프레임 생성 오류:", e)
            break


# ## ROI 설정을 통해서 흰색,검은색만 검출
# def generate_frames():
#     while True:
#         try:
#             frame = picam2.capture_array()
#             h, w = frame.shape[:2]

#             roi = frame[int(h * 2 / 3):, :]
#             gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
#             _, binary = cv2.threshold(gray, 60, 255, cv2.THRESH_BINARY_INV)

#             # 디버그 로그
#             print("프레임 처리 완료")

#             M = cv2.moments(binary)
#             if M["m00"] != 0:
#                 cx = int(M["m10"] / M["m00"])
#                 direction = 'L' if cx < w // 3 else 'R' if cx > 2 * w // 3 else 'S'
#                 print("현재 방향:", direction)

#             # 시각화용 프레임
#             debug_rgb = cv2.cvtColor(binary, cv2.COLOR_GRAY2RGB)
#             ret, buffer = cv2.imencode('.jpg', debug_rgb)
#             if not ret:
#                 print("JPEG 인코딩 실패")
#                 continue
#             frame_bytes = buffer.tobytes()

#             yield (b'--frame\r\n'
#                    b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
#         except Exception as e:
#             print("프레임 생성 중 예외:", e)
#             break


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)

