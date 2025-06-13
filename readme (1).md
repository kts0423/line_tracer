# 🚗 RC-Car Line Tracing 프로젝트

## 목차

- [소개](#소개)
- [시스템 구성](#시스템-구성)
- [하드웨어 요구사항](#하드웨어-요구사항)
- [소프트웨어 요구사항](#소프트웨어-요구사항)
- [설치 및 실행 방법](#설치-및-실행-방법)
- [아두이노 핀 구성 및 연결](#아두이노-핀-구성-및-연결)
- [구현 세부 내용](#구현-세부-내용)
  - [1. flask\_camera\_stream 모듈](#1-flask_camera_stream-모듈)
  - [2. rc\_car\_integrated 모듈](#2-rc_car_integrated-모듈)
  - [3. ROI 모듈](#3-ROI-모듈)
  - [4. testfornew 모듈](#4-testfornew-모듈)
- [파일 구조](#파일-구조)
- [테스트 및 결과](#테스트-및-결과)
- [향후 개선점](#향후-개선점)
- [라이선스](#라이선스)

---

## 소개

본 프로젝트는 Raspberry Pi 5의 Pi Camera와 OpenCV를 이용해 바닥의 검은 선을 검출하고, Arduino Uno로 모터·서보를 제어하여 RC Car가 자동으로 선을 따라 주행하도록 구현한 시스템입니다.\
Flask/WebSocket 기반의 웹 UI를 통해 실시간 카메라 영상을 스트리밍하고, 수동·자동 모드를 전환할 수 있습니다.

---

## 시스템 구성

| 모듈명                       | 역할                                       |
| ------------------------- | ---------------------------------------- |
| **flask\_camera\_stream** | Pi Camera 영상 WebSocket 스트리밍 및 웹 뷰어       |
| **rc\_car\_integrated**   | OpenCV 기반 라인 검출 → PID 제어 → Arduino 제어    |
| **ROI**                   | Region-of-Interest 기반 파라미터 테스트           |
| **testfornew**            | 신규 기능(영상 저장·로깅) 테스트용                     |
| **공통 Arduino 스케치**        | 각 모듈별 `arduino/` 폴더 내 C 코드로 모터·ESC 제어 샘플 |

---

## 하드웨어 요구사항

- Raspberry Pi 5 + Pi Camera 모듈
- Arduino Uno
- L298N 모터 드라이버 (또는 ESC)
- DC 모터, 서보 모터
- RC 송수신기 (Radiolink AT9 등)
- 배터리 팩, 점퍼 케이블, 브레드보드

---

## 소프트웨어 요구사항

- Python 3.9 이상
- Flask
- OpenCV-Python
- PySerial
- websockets (또는 flask-socketio)
- Arduino CLI 또는 Arduino IDE

---

## 설치 및 실행 방법

1. **레포지토리 클론**

   ```bash
   git clone https://github.com/kts0423/line_tracer.git
   cd line_tracer-main
   ```

2. **Python 패키지 설치**

   ```bash
   pip install flask opencv-python pyserial websockets
   ```

3. **Arduino 스케치 업로드**\
   각 모듈별 `*/arduino/*.c` 파일을 Arduino IDE 또는 CLI로 컴파일 후 업로드합니다.

   ```bash
   arduino-cli compile --fqbn arduino:avr:uno <module>/arduino
   arduino-cli upload -p /dev/ttyACM0 --fqbn arduino:avr:uno <module>/arduino
   ```

4. **모듈별 서버 실행**

   ```bash
   cd flask_camera_stream && python app.py  
   cd ../rc_car_integrated && python app.py  
   cd ../ROI && python app.py  
   cd ../testfornew && python app.py  
   ```

5. **웹 브라우저에서 확인**\
   `http://<Raspberry_Pi_IP>:5000` 접속하여 각 모듈의 UI를 사용하세요.

---

## 아두이노 핀 구성 및 연결

| 기능                 | 핀 번호   | 설명                          |
| ------------------ | ------ | --------------------------- |
| RC 채널1 입력 (조향)     | Pin 2  | `pulseIn()`으로 PWM 폭 측정      |
| RC 채널3 입력 (주행)     | Pin 3  | `pulseIn()`으로 PWM 폭 측정      |
| RC 채널5 입력 (모드 선택)  | Pin 4  | `pulseIn()`으로 PWM 폭측정       |
| 제어용 서보(조향) PWM 출력  | Pin 9  | `Servo.writeMicroseconds()` |
| 제어용 ESC(모터) PWM 출력 | Pin 10 | `Servo.writeMicroseconds()` |
| 좌회전 표시 LED         | Pin 6  | Manual 모드 시 깜빡이             |
| 우회전 표시 LED         | Pin 7  | Manual 모드 시 깜빡이             |

> **참고**: RC 수신기 VCC/GND는 채널1·3에만 공급(나머지는 Signal 전용). 모든 GND는 공통 접지로 연결해야 합니다.

---

## 구현 세부 내용

### 1. flask\_camera\_stream 모듈

*생략*

---

### 2. rc\_car\_integrated 모듈

- **주요 파일**: `app.py`, `arduino/rc_car_combined.c`, `templates/index.html`

#### `arduino/rc_car_combined.c`

```c
#include <Arduino.h>
#include <Servo.h>
#include <PinChangeInterrupt.h>

// ─────────────────────────────────────────────────────────────────────────────
// 핀 설정
// ─────────────────────────────────────────────────────────────────────────────
const int PIN_CH1      = 2;    // RC 채널1 입력 (조향 PWM 측정용)
const int PIN_CH3      = 3;    // RC 채널3 입력 (주행 PWM 측정용)
const int PIN_CH5      = 4;    // RC 채널5 입력 (모드 선택 PWM 측정용)

const int SERVO_PIN    = 9;    // 제어용 서보(조향) PWM 출력
const int ESC_PIN      = 10;   // 제어용 ESC(모터) PWM 출력

const int LED_LEFT     = 6;    // 좌회전 표시용 LED 핀 (수동 모드 전용)
const int LED_RIGHT    = 7;    // 우회전 표시용 LED 핀 (수동 모드 전용)

// ─────────────────────────────────────────────────────────────────────────────
// 제어 객체
// ─────────────────────────────────────────────────────────────────────────────
Servo driveESC;        // ESC 제어 객체
Servo steeringServo;   // 조향 서보 제어 객체

// ─────────────────────────────────────────────────────────────────────────────
// ESC 및 서보 기준값
// ─────────────────────────────────────────────────────────────────────────────
const int STOP_PWM      = 1500;  // ESC 중립(정지) 펄스
const int FORWARD_PWM   = 1560;  // ESC 전진 펄스
const int REVERSE_PWM   = 1437;  // ESC 후진 펄스

// ─────────────────────────────────────────────────────────────────────────────
// 조향 서보 매핑값
// ─────────────────────────────────────────────────────────────────────────────
const int STEER_ANGLE_MIN   =   0;    // Python 최소 각도
const int STEER_ANGLE_MAX   = 180;    // Python 최대 각도
const int SERVO_PWM_MIN     = 1100;   // 매핑 시 “오른쪽 끝”(180) 대응
const int SERVO_PWM_MAX     = 1900;   // 매핑 시 “왼쪽 끝”(0) 대응

// ─────────────────────────────────────────────────────────────────────────────
// 조향 보정 오프셋 (필요 시 조정 가능)
// ─────────────────────────────────────────────────────────────────────────────
int steerCalibration = 0;  // 예: 0, +5, -5 등

// ─────────────────────────────────────────────────────────────────────────────
// 상태 저장 변수
// ─────────────────────────────────────────────────────────────────────────────
int currentAngle  = 90;   // Python 에서 넘어온 조향 각도 (0~180)
char currentDir   = 'S';  // Python ↔ Arduino 간 방향 ('F'/'B'/'S')

volatile int motorPulse   = 1500;
volatile int servoPulse   = 1500;
volatile int modePulse    = 1500;

volatile unsigned long motorStart = 0;
volatile unsigned long servoStart = 0;
volatile unsigned long modeStart  = 0;

volatile bool newMotor = false;
volatile bool newServo = false;
volatile bool newMode  = false;

const unsigned long blinkInterval = 200;
unsigned long lastBlinkTime  = 0;
bool ledLeftState   = LOW;
bool ledRightState  = LOW;

char currentModeSwitch = 'U';
char prevModeSwitch    = 'U';

static const uint8_t RECV_BUF_SIZE = 32;
char recvBuf[RECV_BUF_SIZE];
uint8_t recvIdx = 0;
bool    hasNewSerialCmd = false;

// ─────────────────────────────────────────────────────────────────────────────
// 함수 프로토타입
// ─────────────────────────────────────────────────────────────────────────────
void parseSerialCommand(const char* buf);
void handleManualMode();
void handleAutoMode();
void stopAllMotors();

void isrServo() {
  if (digitalRead(PIN_CH1) == HIGH) servoStart = micros();
  else { servoPulse = micros() - servoStart; newServo = true; }
}

void isrMotor() {
  if (digitalRead(PIN_CH3) == HIGH) motorStart = micros();
  else { motorPulse = micros() - motorStart; newMotor = true; }
}

void isrMode() {
  if (digitalRead(PIN_CH5) == HIGH) modeStart = micros();
  else { modePulse = micros() - modeStart; newMode = true; }
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_CH1, INPUT_PULLUP);
  pinMode(PIN_CH3, INPUT_PULLUP);
  pinMode(PIN_CH5, INPUT_PULLUP);

  attachPinChangeInterrupt(digitalPinToPCINT(PIN_CH1), isrServo, CHANGE);
  attachPinChangeInterrupt(digitalPinToPCINT(PIN_CH3), isrMotor, CHANGE);
  attachPinChangeInterrupt(digitalPinToPCINT(PIN_CH5), isrMode, CHANGE);

  driveESC.attach(ESC_PIN);
  steeringServo.attach(SERVO_PIN);
  driveESC.writeMicroseconds(STOP_PWM);
  steeringServo.writeMicroseconds(1500);
  delay(2000);

  pinMode(LED_LEFT, OUTPUT);
  pinMode(LED_RIGHT, OUTPUT);
  digitalWrite(LED_LEFT, LOW);
  digitalWrite(LED_RIGHT, LOW);

  Serial.println("MODE:AUTO");
  Serial.println("[OK] RC카 통합 모드 준비 완료");
}

void loop() {
  if (newMode) {
    newMode = false;
    char newModeChar = (modePulse <= 1500 ? 'A' : 'M');
    if (newModeChar != currentModeSwitch) {
      currentModeSwitch = newModeChar;
      stopAllMotors();
      Serial.println(currentModeSwitch == 'A' ? "MODE:AUTO" : "MODE:MANUAL");
    }
  }

  if (currentModeSwitch == 'M')      handleManualMode();
  else if (currentModeSwitch == 'A') handleAutoMode();
  else { driveESC.writeMicroseconds(STOP_PWM); steeringServo.writeMicroseconds(1500); }
}

void handleManualMode() {
  if (newServo || newMotor) {
    newServo = newMotor = false;
    int constrainedServo = constrain(servoPulse, 1000, 2000);
    steeringServo.writeMicroseconds(constrainedServo);

    int motorDeviation = motorPulse - 1500;
    int limitedDev = motorDeviation / 5;
    int out = 1500 + limitedDev;
    out = constrain(out, 1000, 2000);
    driveESC.writeMicroseconds(out);

    static unsigned long lastDbg = 0;
    if (millis() - lastDbg >= 200) {
      Serial.print("[MANUAL] Servo: "); Serial.print(servoPulse);
      Serial.print(" | Motor: "); Serial.println(out);
      lastDbg = millis();
    }
  }

  int deadband = 100;
  bool leftActive  = (servoPulse < 1500 - deadband);
  bool rightActive = (servoPulse > 1500 + deadband);
  unsigned long now = millis();

  if (leftActive) {
    digitalWrite(LED_RIGHT, LOW);
    if (now - lastBlinkTime >= blinkInterval) { ledLeftState = !ledLeftState; digitalWrite(LED_LEFT, ledLeftState); lastBlinkTime = now; }
  } else if (rightActive) {
    digitalWrite(LED_LEFT, LOW);
    if (now - lastBlinkTime >= blinkInterval) { ledRightState = !ledRightState; digitalWrite(LED_RIGHT, ledRightState); lastBlinkTime = now; }
  } else {
    digitalWrite(LED_LEFT, LOW); digitalWrite(LED_RIGHT, LOW);
    ledLeftState = ledRightState = LOW;
  }
}

void handleAutoMode() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '
' && recvIdx > 0) {
      recvBuf[recvIdx] = '�'; parseSerialCommand(recvBuf); recvIdx = 0; hasNewSerialCmd = true;
    } else if (c != '
' && recvIdx < RECV_BUF_SIZE-1) { recvBuf[recvIdx++] = c; }
  }
  if (hasNewSerialCmd) {
    hasNewSerialCmd = false;
    int ang = currentAngle + steerCalibration;
    ang = constrain(ang, STEER_ANGLE_MIN, STEER_ANGLE_MAX);
    int pwmServo = map(ang, STEER_ANGLE_MIN, STEER_ANGLE_MAX, SERVO_PWM_MAX, SERVO_PWM_MIN);
    steeringServo.writeMicroseconds(pwmServo);

    int pwmESC = STOP_PWM;
    if      (currentDir=='F') pwmESC = FORWARD_PWM;
    else if (currentDir=='B') pwmESC = REVERSE_PWM;
    static char prev = 'S';
    if ((prev=='F'&&currentDir=='B')||(prev=='B'&&currentDir=='F')) {
      driveESC.writeMicroseconds(STOP_PWM); delay(100);
    }
    driveESC.writeMicroseconds(pwmESC); prev = currentDir;

    Serial.print("[AUTO] Angle:"); Serial.print(currentAngle);
    Serial.print(" Dir:"); Serial.print(currentDir);
    Serial.print(" SrvPWM:"); Serial.print(pwmServo);
    Serial.print(" ESCPWM:"); Serial.println(pwmESC);
  }
}

void parseSerialCommand(const char* buf) {
  const char* pE = strstr(buf, "E:");
  const char* pD = strstr(buf, "D:");
  if (pE && pD) {
    currentAngle = constrain(atoi(pE+2), STEER_ANGLE_MIN, STEER_ANGLE_MAX);
    char d = *(pD+2);
    currentDir = (d=='F'||d=='B'||d=='S') ? d : 'S';
  } else {
    currentDir = 'S'; currentAngle = 90;
  }
}

void stopAllMotors() {
  driveESC.writeMicroseconds(STOP_PWM);
  steeringServo.writeMicroseconds(1500);
  digitalWrite(LED_LEFT, LOW);
  digitalWrite(LED_RIGHT, LOW);
}
```

### 3. ROI 모듈

- **주요 파일**: `app.py`, `test.c`, `test.txt`, `bin/arduino-cli`, `templates/index.html`

#### `app.py`

```python
from flask import Flask, render_template, request
import cv2, serial

app = Flask(__name__)
# Arduino 연결
ser = serial.Serial('/dev/ttyACM0', 9600, timeout=1)
cap = cv2.VideoCapture(0)
# 초기 ROI 파라미터
roi_x, roi_y, roi_w, roi_h = 0, 0, 320, 240

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/set_roi', methods=['POST'])
def set_roi():
    global roi_x, roi_y, roi_w, roi_h
    roi_x = int(request.form['x'])
    roi_y = int(request.form['y'])
    roi_w = int(request.form['w'])
    roi_h = int(request.form['h'])
    return 'OK'

@app.route('/stream')
def stream():
    while True:
        ret, frame = cap.read()
        if not ret: break
        # ROI 추출
        roi = frame[roi_y:roi_y+roi_h, roi_x:roi_x+roi_w]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY_INV)
        M = cv2.moments(thresh)
        cx = int(M['m10']/M['m00']) if M['m00'] else None
        # 시리얼로 cx 전송
        ser.write(f"ROI_CX:{cx}
".encode())
        yield thresh.tobytes()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
```

- **ROI 처리**: 웹 UI에서 슬라이더로 설정된 영역을 캡처하여 이진화 후 무게 중심(cx) 계산
- **Serial 전송**: Arduino로 ROI 중심 좌표 전송하여 디버깅용 LED 제어 등 테스트 가능

#### `test.c`

```c
#include <Arduino.h>
const int LED_PIN = LED_BUILTIN;
void setup() {
  Serial.begin(9600);
  pinMode(LED_PIN, OUTPUT);
}
void loop() {
  if (Serial.available()) {
    String msg = Serial.readStringUntil('
');
    if (msg.startsWith("ROI_CX:")) {
      int cx = msg.substring(7).toInt();
      // cx 값에 따라 LED 토글
      if (cx > 100) digitalWrite(LED_PIN, HIGH);
      else digitalWrite(LED_PIN, LOW);
    }
  }
}
```

- **Arduino 테스트**: ROI 결과를 시리얼로 수신해 LED 동작 확인

#### `templates/index.html`

```html
<!DOCTYPE html>
<html>
<head><title>ROI Test</title></head>
<body>
  <h3>ROI 설정</h3>
  <form id="roiForm">
    X: <input name="x" type="number" value="0" min="0"><br>
    Y: <input name="y" type="number" value="0" min="0"><br>
    W: <input name="w" type="number" value="320" min="1"><br>
    H: <input name="h" type="number" value="240" min="1"><br>
    <button type="submit">적용</button>
  </form>
  <canvas id="canvas" width="320" height="240"></canvas>
  <script>
    const form = document.getElementById('roiForm');
    form.onsubmit = e => {
      e.preventDefault();
      const data = new FormData(form);
      fetch('/set_roi', {method:'POST', body:data});
    };
    // 이미지 스트림 처리 (생략)
  </script>
</body>
</html>
```

---

### 4. testfornew 모듈

- **주요 파일**: `app.py`, `video.py`, `test.txt`, `templates/index.html`

#### `app.py`

```python
from flask import Flask, render_template, request, jsonify
import os
from werkzeug.utils import secure_filename
import video

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads/'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    f = request.files['file']
    filename = secure_filename(f.filename)
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    f.save(path)
    return jsonify(result='success', filename=filename)

@app.route('/process/<filename>')
def process(filename):
    input_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    output_path = video.process_video(input_path)
    return jsonify(result='done', output=output_path)

@app.route('/logs')
def logs():
    with open('test.txt') as f:
        return f.read()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002)
```

- **영상 업로드 & 처리**: `/upload`로 `.mp4` 업로드 → `video.process_video()` 호출 → 결과 저장

#### `video.py`

```python
import cv2, os
def process_video(path):
    cap = cv2.VideoCapture(path)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out_path = path.replace('.mp4', '_out.mp4')
    out = cv2.VideoWriter(out_path, fourcc, 30.0, (640,480))
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret: break
        # 프레임 처리 (예: 그레이스케일)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        out.write(cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR))
    cap.release(); out.release()
    with open('test.txt', 'a') as f:
        f.write(f"Processed: {path}
")
    return out_path
```

- **프레임별 처리**: 입력 영상 그레이스케일 변환 후 저장 → 로그 파일 기록

#### `templates/index.html`

````html
<!DOCTYPE html>
<html>
<head><title>Testfornew UI</title></head>
<body>
  <h3>영상 업로드 및 처리</h3>
  <input type="file" id="fileInput"><button id="uploadBtn">업로드</button>
  <button id="processBtn" disabled>처리 시작</button>
  <pre id="log"></pre>
  <script>
    let filename;
    document.getElementById('uploadBtn').onclick = () => {
      const file = document.getElementById('fileInput').files[0];
      const fd = new FormData(); fd.append('file', file);
      fetch('/upload', {method:'POST', body:fd})
        .then(r=>r.json()).then(j=>{ filename=j.filename; document.getElementById('processBtn').disabled=false; });
    };
    document.getElementById('processBtn').onclick = () => {
      fetch('/process/'+filename)
        .then(r=>r.json()).then(_=> fetch('/logs'))
        .then(r=>r.text()).then(t=> document.getElementById('log').textContent=t);
    };
  </script>
</body>
</html>
```. testfornew 모듈

*생략*

---

## 파일 구조

```text
line_tracer-main/
├── README.md
├── images/
│   └── rc_receiver_mapping.png
├── flask_camera_stream/
│   ├── app.py
│   ├── arduino/
│   │   └── test.c
│   └── templates/
│       └── index.html
├── rc_car_integrated/
│   ├── app.py
│   ├── arduino/
│   │   └── rc_car_combined.c
│   └── templates/
│       └── index.html
├── ROI/
│   ├── app.py
│   ├── test.c
│   ├── test.txt
│   ├── bin/
│   │   └── arduino-cli
│   └── templates/
│       └── index.html
└── testfornew/
    ├── app.py
    ├── video.py
    ├── test.txt
    └── templates/
        └── index.html
````

---

## 테스트 및 결과

*생략*

---

## 향후 개선점

*생략*

---

## 라이선스

MIT © 2025 Your Name

