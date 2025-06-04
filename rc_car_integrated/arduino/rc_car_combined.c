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
// 조향 서보 매핑값 (Python 에서 0~180 값 받아서 1100~1900µs 로 매핑)
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
// Auto(라인 추종) 모드에서 사용:
//  - Python ↔ Serial 통신을 통해 수신되는 조향(angle) 및 방향(dir) 값
int currentAngle  = 90;   // Python 에서 넘어온 조향 각도 (0~180)
char currentDir   = 'S';  // Python ↔ Arduino 간 방향 문자인데, 'F'/'B'/'S' (전진/후진/정지)

// Manual(RC 조종) 모드에서 사용:
//  - RC 수신기로부터 받는 PWM 폭 (µs 단위)
volatile int motorPulse   = 1500;  // 채널3 (주행) 펄스폭
volatile int servoPulse   = 1500;  // 채널1 (조향) 펄스폭

// 모드 선택을 위한 채널5(PIN_CH5) PWM 폭
volatile int modePulse    = 1500;  // 채널5 (모드) 펄스폭

// 인터럽트 시작 시간 기록용
volatile unsigned long motorStart = 0;
volatile unsigned long servoStart = 0;
volatile unsigned long modeStart  = 0;

// 플래그: 새로운 PWM 값 수신 여부
volatile bool newMotor = false;
volatile bool newServo = false;
volatile bool newMode  = false;

// ─────────────────────────────────────────────────────────────────────────────
// 블링크용 변수: Manual 모드 전용
// ─────────────────────────────────────────────────────────────────────────────
const unsigned long blinkInterval = 200; // LED 깜빡임 간격(ms)
unsigned long       lastBlinkTime  = 0;
bool                ledLeftState   = LOW;
bool                ledRightState  = LOW;

// ─────────────────────────────────────────────────────────────────────────────
// 모드 전환 상태 저장
// ─────────────────────────────────────────────────────────────────────────────
// 'M' = Manual(RC 조종), 'A' = Auto(라인 추종), 'U' = Undetermined (초기)
char currentModeSwitch = 'U';
char prevModeSwitch    = 'U';

// ─────────────────────────────────────────────────────────────────────────────
// 시리얼 수신 버퍼: Auto 모드에서 Python ↔ Arduino 메시지 처리용
// ─────────────────────────────────────────────────────────────────────────────
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

// ─────────────────────────────────────────────────────────────────────────────
// 인터럽트 핸들러: 채널1 (조향 PWM 계산)
// ─────────────────────────────────────────────────────────────────────────────
void isrServo() {
  if (digitalRead(PIN_CH1) == HIGH) {
    servoStart = micros();
  } else {
    servoPulse = micros() - servoStart;  // PWM 폭 계산
    newServo   = true;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 인터럽트 핸들러: 채널3 (주행 PWM 계산)
// ─────────────────────────────────────────────────────────────────────────────
void isrMotor() {
  if (digitalRead(PIN_CH3) == HIGH) {
    motorStart = micros();
  } else {
    motorPulse = micros() - motorStart;  // PWM 폭 계산
    newMotor   = true;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 인터럽트 핸들러: 채널5 (모드 선택 PWM 계산)
// ─────────────────────────────────────────────────────────────────────────────
void isrMode() {
  if (digitalRead(PIN_CH5) == HIGH) {
    modeStart = micros();
  } else {
    modePulse = micros() - modeStart;  // PWM 폭 계산
    newMode   = true;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// setup(): 보드 초기화 시 한 번 실행
//  - 시리얼 통신 시작 (115200bps)
//  - ESC/서보 attach 및 중립값 세팅
//  - 채널1, 채널3, 채널5 핀 인터럽트 설정 (PinChangeInterrupt)
//  - LED 핀 출력 모드 설정
//  - 초기 모드를 AUTO로 Python(Flask) 쪽에 알려 줌
// ─────────────────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);

  // ─── RC 수신기 입력 핀 설정 (Pull-up 활성화)
  pinMode(PIN_CH1, INPUT_PULLUP);
  pinMode(PIN_CH3, INPUT_PULLUP);
  pinMode(PIN_CH5, INPUT_PULLUP);

  // 채널1/3/5에 Change 인터럽트 연결
  attachPinChangeInterrupt(digitalPinToPCINT(PIN_CH1), isrServo, CHANGE);
  attachPinChangeInterrupt(digitalPinToPCINT(PIN_CH3), isrMotor, CHANGE);
  attachPinChangeInterrupt(digitalPinToPCINT(PIN_CH5), isrMode, CHANGE);

  // ─── Servo 및 ESC 초기화
  driveESC.attach(ESC_PIN);
  steeringServo.attach(SERVO_PIN);

  // ESC 정지(1500µs), 서보 중립(1500µs)으로 초기화
  driveESC.writeMicroseconds(STOP_PWM);
  steeringServo.writeMicroseconds(1500);

  delay(2000);  // ESC 캘리브레이션 대기 (2초)

  // ─── LED 핀 설정 (Manual 모드용)
  pinMode(LED_LEFT, OUTPUT);
  pinMode(LED_RIGHT, OUTPUT);
  digitalWrite(LED_LEFT, LOW);
  digitalWrite(LED_RIGHT, LOW);

  // ─── 초기 모드를 AUTO로 Python(Flask) 쪽에 알려 줌
  Serial.println("MODE:AUTO");

  Serial.println("[OK] RC카 통합 모드 준비 완료");
  Serial.println("[INFO] 모드 스위치 채널5 입력 준비됨");
}

// ─────────────────────────────────────────────────────────────────────────────
// loop(): 반복 실행
//  1) RC 채널5로 모드 판단 (Manual vs Auto)
//  2) 모드 전환 시 모터/서보 정지 + Python으로 MODE:xxx 전송
//  3) 각 모드별 처리
//  4) Auto 모드 시리얼 명령 파싱
//  5) Manual 모드 LED 깜빡임 처리
// ─────────────────────────────────────────────────────────────────────────────
void loop() {
  // ─── (1) 새로운 모드 PWM 수신 여부 확인
  if (newMode) {
    newMode = false;
    char newModeChar;

    // modePulse ≤ 1500 → Auto, >1500 → Manual
    if (modePulse <= 1500) {
      newModeChar = 'A';
    } else {
      newModeChar = 'M';
    }

    // (2) 모드가 바뀌었으면 그 즉시 전부 정지시키고, Python에 문자열로 알림
    if (newModeChar != currentModeSwitch) {
      currentModeSwitch = newModeChar;
      stopAllMotors();  // 모드를 바꿀 때 모터/서보를 즉시 정지

      if (currentModeSwitch == 'A') {
        Serial.println("MODE:AUTO");
      } else {
        Serial.println("MODE:MANUAL");
      }
    }
  }

  // ─── (3) 현재 모드별 처리 분기
  if (currentModeSwitch == 'M') {
    handleManualMode();
  }
  else if (currentModeSwitch == 'A') {
    handleAutoMode();
  }
  else {
    // 초기(U) 상태: 그냥 정지 유지
    driveESC.writeMicroseconds(STOP_PWM);
    steeringServo.writeMicroseconds(1500);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// handleManualMode(): RC 수신값 기반으로 ESC/서보 제어
//  1) 채널1/채널3에서 새로운 PWM 값 수신 시 처리
//  2) 조향은 PWM 폭 그대로 서보에 전달 (1000~2000µs)
//  3) 주행은 PWM 폭을 감도 제한(1/5) 후 ESC에 전달
//  4) 조향 방향에 따라 LED 깜빡임 제어
// ─────────────────────────────────────────────────────────────────────────────
void handleManualMode() {
  if (newServo || newMotor) {
    newServo = false;
    newMotor = false;

    // ── Steering (채널1 PWM) → 바로 서보에 전달
    int constrainedServo = constrain(servoPulse, 1000, 2000);
    steeringServo.writeMicroseconds(constrainedServo);

    // ── Motor (채널3 PWM) → 감도 제한 후 ESC에 전달
    int motorDeviation      = motorPulse - 1500;          // -500 ~ +500
    int limitedMotorDev     = motorDeviation / 5;         // -100 ~ +100
    int limitedMotorOutput  = 1500 + limitedMotorDev;     // 1400 ~ 1600
    int constrainedMotorOut = constrain(limitedMotorOutput, 1000, 2000);
    driveESC.writeMicroseconds(constrainedMotorOut);

    // ── 디버깅용 시리얼 출력 (200ms 주기)
    static unsigned long lastDbgTime = 0;
    if (millis() - lastDbgTime >= 200) {
      Serial.print("[MANUAL] Servo PWM: ");
      Serial.print(servoPulse);
      Serial.print(" | Motor PWM: ");
      Serial.print(motorPulse);
      Serial.print(" → ESC Out: ");
      Serial.println(constrainedMotorOut);
      lastDbgTime = millis();
    }
  }

  // ── LED 깜빡임 제어 (조향 방향 표시)
  const int deadband     = 100;  // ±100 내를 중립으로 간주
  bool leftActive  = (servoPulse < (1500 - deadband));
  bool rightActive = (servoPulse > (1500 + deadband));
  unsigned long currentMillis = millis();

  if (leftActive) {
    digitalWrite(LED_RIGHT, LOW);
    if (currentMillis - lastBlinkTime >= blinkInterval) {
      ledLeftState  = !ledLeftState;
      digitalWrite(LED_LEFT, ledLeftState);
      lastBlinkTime = currentMillis;
    }
  }
  else if (rightActive) {
    digitalWrite(LED_LEFT, LOW);
    if (currentMillis - lastBlinkTime >= blinkInterval) {
      ledRightState  = !ledRightState;
      digitalWrite(LED_RIGHT, ledRightState);
      lastBlinkTime  = currentMillis;
    }
  }
  else {
    // 중립(±100 이내): 양쪽 LED 모두 끔
    digitalWrite(LED_LEFT, LOW);
    digitalWrite(LED_RIGHT, LOW);
    ledLeftState  = LOW;
    ledRightState = LOW;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// handleAutoMode(): Serial 명령 기반으로 ESC/서보 제어
//  1) Serial에서 한 줄 수신 시 parseSerialCommand() 호출
//  2) parseSerialCommand()에서 currentAngle, currentDir 갱신
//  3) currentDir, currentAngle 값에 따라 ESC/서보 출력
// ─────────────────────────────────────────────────────────────────────────────
void handleAutoMode() {
  // ── Python → Arduino로 “E:<angle> D:<dir>” 문자열이 올 때마다 처리
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') {
      continue;
    }
    if (c == '\n') {
      if (recvIdx > 0) {
        recvBuf[recvIdx] = '\0';
        parseSerialCommand(recvBuf);
        recvIdx = 0;
        hasNewSerialCmd = true;
      }
    } else {
      if (recvIdx < RECV_BUF_SIZE - 1) {
        recvBuf[recvIdx++] = c;
      } else {
        recvIdx = 0;  // Overflow 시 드롭
      }
    }
  }

  if (hasNewSerialCmd) {
    hasNewSerialCmd = false;

    // ── (1) 조향: currentAngle(0~180) + 보정 → PWM(1100~1900) 매핑 → 서보
    int adjustedAngle = currentAngle + steerCalibration;
    adjustedAngle = constrain(adjustedAngle, STEER_ANGLE_MIN, STEER_ANGLE_MAX);
    int pwmServo = map(
      adjustedAngle,
      STEER_ANGLE_MIN, STEER_ANGLE_MAX,
      SERVO_PWM_MAX, SERVO_PWM_MIN
    );
    steeringServo.writeMicroseconds(pwmServo);

    // ── (2) ESC 속도: currentDir('F'/'B'/'S')에 따라 FORWARD/REVERSE/STOP
    int pwmESC = STOP_PWM;
    if (currentDir == 'F')      pwmESC = FORWARD_PWM;
    else if (currentDir == 'B') pwmESC = REVERSE_PWM;
    else                        pwmESC = STOP_PWM;

    static char prevDir = 'S';
    if ((prevDir == 'F' && currentDir == 'B') ||
        (prevDir == 'B' && currentDir == 'F')) {
      // 전진↔후진 전환 시 잠깐 중립(100ms) 펄스
      driveESC.writeMicroseconds(STOP_PWM);
      delay(100);
    }
    driveESC.writeMicroseconds(pwmESC);
    prevDir = currentDir;

    // ── (3) 디버깅용 시리얼 출력
    Serial.print("[AUTO] Angle: ");
    Serial.print(currentAngle);
    Serial.print(" | Dir: ");
    Serial.print(currentDir);
    Serial.print(" → Servo PWM: ");
    Serial.print(pwmServo);
    Serial.print(" | ESC PWM: ");
    Serial.println(pwmESC);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// parseSerialCommand(buf):
//   - recvBuf에 저장된 "E:<angle> D:<dir>" 문자열을 파싱
//   - currentAngle, currentDir 업데이트
//   - 형식 불일치 시 정지(S) 모드 적용
// ─────────────────────────────────────────────────────────────────────────────
void parseSerialCommand(const char* buf) {
  const char* pE = strstr(buf, "E:");
  const char* pD = strstr(buf, "D:");
  if (pE && pD) {
    int angle = atoi(pE + 2);
    angle = constrain(angle, STEER_ANGLE_MIN, STEER_ANGLE_MAX);
    currentAngle = angle;

    char dir = *(pD + 2);
    if (dir == 'F' || dir == 'B' || dir == 'S') {
      currentDir = dir;
    } else {
      currentDir = 'S';
    }
  } else {
    // 파싱 실패 시 정지 모드
    currentDir   = 'S';
    currentAngle = 90;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// stopAllMotors(): 모터 & 서보를 즉시 중립 상태로 정지
// ─────────────────────────────────────────────────────────────────────────────
void stopAllMotors() {
  driveESC.writeMicroseconds(STOP_PWM);      // ESC 정지
  steeringServo.writeMicroseconds(1500);      // 서보 중립
  digitalWrite(LED_LEFT, LOW);                // 수동 LED 모두 끔
  digitalWrite(LED_RIGHT, LOW);
}
