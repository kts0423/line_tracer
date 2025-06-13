# 🚗 RC-Car Line Tracing 프로젝트


## 팀원 및 역할 분담

| 팀원    | 주요 업무                                                                                                                                                         |
|-------|----------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **김동현** | **Arduino 하드웨어 & 펌웨어**<br>- RC 송수신기(Receiver)→Arduino 회로 연결<br>- `PinChangeInterrupt`, `Servo` 라이브러리 활용 아두이노 스케치 작성<br>- 수동/자동 모드 전환 로직 및 LED 표시 기능 구현 |
| **김태성** | **Python 라인트레이싱 & WebSocket 서버**<br>- Raspberry Pi + PiCamera → OpenCV 기반 검은선 검출 알고리즘 개발<br>- PID 제어 루프 설계 및 `asyncio`/`websockets` 이용한 실시간 영상 스트리밍 구현       |
| **길진성** | **RC 송수신기 연동 & 문서화**<br>- Radiolink AT9 송수신기 채널 매핑 및 시리얼 통신 설정<br>- 전체 프로젝트 구조 및 사용 가이드 `README.md` 작성·관리<br>- GitHub 레포 관리 및 CI/릴리즈 진행 지원      |




## 목차

- [소개](#소개)
- [시스템 구성](#시스템-구성)
- [하드웨어 요구사항](#하드웨어-요구사항)
- [소프트웨어 요구사항](#소프트웨어-요구사항)
- [설치 및 실행 방법](#설치-및-실행-방법)
- [아두이노 핀 구성 및 연결](#아두이노-핀-구성-및-연결)
- [구현 세부 내용](#구현-세부-내용)
  - [1. 라인트레이싱 파이썬 코드 (app.py)
  - [2. 아두이노 코드 (rc_car_combined.c)
- [파일 구조](#파일-구조)
- [테스트 및 결과](#테스트-및-결과)
- [향후 개선점](#향후-개선점)
- [라이선스](#라이선스)

---

## 소개

본 프로젝트는 Raspberry Pi 5의 Pi Camera와 OpenCV를 이용해 바닥의 검은 선을 검출하고, Arduino Uno로 모터·서보를 제어하여 RC Car가 자동으로 선을 따라 주행하도록 구현한 자율 주행 모드와 AT9 송신기와 R9DS 수신기에서 펄스폭 변조를 통하여 아두이는 해당 신호를 받고 서보모터와 ESC 모터를 동작시키는 자동 + 수동 조작이 통합 된 시스템입니다.
Flask/WebSocket 기반의 웹 UI를 통해 실시간 카메라 영상을 스트리밍하여 자동 모드와 수동 모드의 화면이 다릅니다.

---

## 시스템 구성

| 모듈명                                  | 역할                                                                                                                                                                                                                           |
|--------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 구성 요소 | 동작 설명 |
|-----------|-----------|
| **Python 제어 프로그램**<br>`project/python/app.py` | - **자동 모드**: 카메라(Pi Camera 또는 USB Cam)로 실시간 영상 캡처 → OpenCV 기반 검은 선 검출 → 중심선 좌표 계산 → 조향 각도 및 속도 계산 → 시리얼(Serial)로 Arduino에 `AUTO,STEER:<각도>,SPEED:<E,S,R>` 형태로 전송<br>- **수동 모드**: Arduino로부터 현재 모드 정보를 수신 (`MODE:MANUAL` 등) → UI에 표시 및 제어 비활성화 |
| **Arduino 펌웨어**<br>`project/arduino/line_tracer.ino` | - **수동 모드**: AT9 송신기 → R9DS 수신기 → PWM 신호 수신 (PinChangeInterrupt 활용) → `Servo.writeMicroseconds()` 및 ESC 제어로 직접 서보/모터 제어<br>- **자동 모드**: Python으로부터 시리얼 메시지 수신 (`AUTO,STEER:<각도>,SPEED:<E,S,R>`) → 문자열 파싱 후 해당 각도 및 고정된 아두이노의 속도에 맞춰 Servo/ESC 동작 제어<br>- 모드 상태(`MODE:AUTO` 또는 `MODE:MANUAL`)를 시리얼로 Python에 전송 |


---

## 하드웨어 요구사항

- Raspberry Pi 5 + Pi Camera 모듈
- Arduino Uno
- ESC 모터
- DC 모터, 서보 모터
- RC 송수신기 - Radiolink AT9 
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


   ```

4. **웹 브라우저에서 확인**\
   `http://<Raspberry_Pi_IP>:5000` 접속하여 각 모듈의 UI를 사용하세요.

---




## 아두이노 핀 구성 및 연결

| 기능                 | 핀 번호   | 설명                          |
| ------------------ | ------ | --------------------------- |
| RC 채널1 입력 (조향)     | Pin 2  | `pinchangeinterrupt`으로 PWM 폭 측정      |
| RC 채널3 입력 (주행)     | Pin 3  | `pinchangeinterrupt`으로 PWM 폭 측정      |
| RC 채널5 입력 (모드 선택)  | Pin 4  | `pinchangeinterrupt`으로 PWM 폭측정       |
| 제어용 서보(조향) PWM 출력  | Pin 9  | `Servo.writeMicroseconds()` |
| 제어용 ESC(모터) PWM 출력 | Pin 10 | `Servo.writeMicroseconds()` |
| 좌회전 표시 LED         | Pin 6  | Manual 모드 시 깜빡이             |
| 우회전 표시 LED         | Pin 7  | Manual 모드 시 깜빡이             |

> **참고**: RC 수신기 VCC/GND는 채널1·3에만 공급(나머지는 Signal 전용). 모든 GND는 공통 접지로 연결해야 합니다.

---

## 🧠 라인 검출 및 조향 제어 알고리즘 (Python)

자동 모드에서는 카메라에서 입력된 영상을 기반으로 검은색 라인을 인식하고, 이를 통해 조향(steering) 각도와 방향을 계산하여 Arduino로 제어 명령을 전송합니다.

### 1. ROI 설정

- 전체 영상 중 세로 10% ~ 80% 구간만 관심 영역(ROI)으로 설정합니다.
- ROI 내에서만 라인을 검출하여 연산 효율을 높입니다.

python 코드
roi_top = int(h * 0.1)
roi_bottom = int(h * 0.80)
roi = frame[roi_top:roi_bottom, :]

### 2. 전처리 및 마스크 생성 
1. Grayscale로 변환
2. Gaussian Blur로 노이즈 제거
3. Adaptive Threshold로 이진화
4. Morphology Open으로 잡음 제거

### 3. 컨투어 검출 및 유효성 필터링
cv2.findContours()로 외곽선(contours)을 추출하고, 다음 조건을 만족하는 컨투어만 사용합니다:

### 4. 조향 벡터 계산 (fitLine + lookahead)
가장 큰 컨투어에 대해 cv2.fitLine()으로 중심선 방향 벡터 (vx, vy)와 기준점 (x0, y0)를 계산합니다.

ROI 상단으로 벡터를 연장하여 "lookahead" 지점을 구하고, 이 위치와 중심 오프셋을 기반으로 조향 보정값 계산:

최종 조향 각도는 0~180 범위로 클램핑됩니다.

### 5. 예외 처리 및 유지 동작
SC 초기화 시간 이전에는 정지(90도, D:S) 명령을 유지합니다.

라인이 일시적으로 사라진 경우에는 직전 조향 각도(last_steer_angle)로 전진(F)을 유지합니다.

라인을 완전히 상실했거나 모드가 수동일 경우에는 정지 상태 유지.

### 6. 시리얼 명령 전송
계산된 조향 각도와 주행 방향은 아래 포맷으로 Arduino에 시리얼 전송됩니다:
예: E:85 D:F

### 7. 시각화
ROI 테두리, 조향 벡터, lookahead 지점, 현재 조향 각도 및 방향 등을 영상에 시각적으로 표시하여 디버깅에 활용합니다.


## 구현 세부 내용

### 1. 라인트레이싱 파이썬 코드(app.py)

- **주요 파일**: `app.py`, `arduino/test.c`, `templates/index.html`

#### `app.py`

```python
from flask import Flask, render_template
import asyncio, websockets, io
import picamera

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

async def stream_camera(websocket, path):
    with picamera.PiCamera(resolution='640x480', framerate=30) as cam:
        stream = io.BytesIO()
        for _ in cam.capture_continuous(stream, 'jpeg', use_video_port=True):
            stream.seek(0)
            frame = stream.read()
            await websocket.send(frame)
            stream.seek(0)
            stream.truncate()
            await asyncio.sleep(0.03)

if __name__ == '__main__':
    start_server = websockets.serve(stream_camera, '0.0.0.0', 8765)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_server)
    loop.run_forever()
```

- **picamera.capture\_continuous**: 카메라의 JPEG 프레임을 연속 캡처
- **WebSocket 전송**: 바이너리 프레임을 그대로 클라이언트에 브로드캐스트
- **프레임 속도 제어**: `framerate=30` 및 `await asyncio.sleep(0.03)`로 약 30 fps 유지

#### `templates/index.html`

```html
<!DOCTYPE html>
<html>
<head>
  <title>Camera Stream</title>
</head>
<body>
  <img id="video" width="640" height="480" />
  <script>
    const img = document.getElementById('video');
    const ws = new WebSocket('ws://' + location.hostname + ':8765/');
    ws.onmessage = ev => {
      img.src = 'data:image/jpeg;base64,' + btoa(
        new Uint8Array(ev.data).reduce((data, byte) => data + String.fromCharCode(byte), '')
      );
    };
  </script>
</body>
</html>
```

- **WebSocket 연결** 후 수신된 JPEG 바이너리를 `<img>` 태그로 실시간 디스플레이

---


### 2. 아두이노 코드 (rc_car_combined.c)

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

- **영상 업로드 & 처리**: `/upload`로 `.mp4` 업로드 → `video.process_video()` 호출 → 결과 저장

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

text
line_tracer-main/
├── README.md
└── project/
├── arduino/
│ └── rc_car_combined.c
└── python/
├── app.py
├── test.txt
├── video.py
└── templates/
└── index.html

````

---

## 테스트 및 결과

- **영상 스트리밍**: 평균 30 fps 이상 안정적 전송 확인
- **라인 추종 성공률**: 곡선 트랙에서 약 90% 이상
- **수동 모드 반응 속도**: 명령 전송 후 < 50 ms

---

## 향후 개선점

1. **적응형 임계치** 알고리즘 도입(조명 변화 대응)
2. **PID 게인 튜닝** 자동화 및 장애물 회피 기능 추가
3. 웹 UI에 **모터 상태(전압·전류)** 실시간 모니터링
4. **Docker** 컨테이너화 및 CI/CD 파이프라인 구성

---

## 라이선스

MIT © 2025 


