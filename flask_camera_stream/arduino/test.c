#include <Arduino.h>
#include <Servo.h>
#include <PinChangeInterrupt.h>

// ─────────────────────────────────────────────
// 핀 정의

const int servo      = 2;    // RC 채널1 입력 (PWM 신호 측정용)
const int motor      = 3;    // RC 채널3 입력 (PWM 신호 측정용)

const int SERVO_PIN  = 9;    // 제어용 서보(조향) PWM 출력
const int ESC_PIN    = 10;   // 제어용 ESC(모터) PWM 출력

const int LED_LEFT   = 6;    // 좌회전 표시용 LED 핀
const int LED_RIGHT  = 7;    // 우회전 표시용 LED 핀

// ─────────────────────────────────────────────
// RC 수신값 변수
volatile int         motorPulse   = 1500;
volatile int         servoPulse   = 1500;
volatile unsigned long motorStart = 0;
volatile unsigned long servoStart = 0;
volatile bool        newMotor     = false;
volatile bool        newServo     = false;

// ─────────────────────────────────────────────
// 블링크용 변수
const unsigned long blinkInterval = 200; // LED 깜빡임 간격(ms)
unsigned long       lastBlinkTime  = 0;
bool                ledLeftState   = LOW;
bool                ledRightState  = LOW;

// ─────────────────────────────────────────────
// 모터 및 서보 객체
Servo esc;
Servo steerServo;

// ─────────────────────────────────────────────
// 인터럽트 핸들러

// 채널1번(servo) 인터럽트: PWM 폭 계산
void isrServo() {
  if (digitalRead(servo) == HIGH) {
    servoStart = micros();
  } else {
    servoPulse = micros() - servoStart;
    newServo   = true;
  }
}

// 채널3번(motor) 인터럽트: PWM 폭 계산
void isrMotor() {
  if (digitalRead(motor) == HIGH) {
    motorStart = micros();
  } else {
    motorPulse = micros() - motorStart;
    newMotor   = true;
  }
}

// ─────────────────────────────────────────────
void setup() {
  Serial.begin(9600);

  // RC 수신기 입력 핀 설정
  pinMode(motor, INPUT_PULLUP);
  pinMode(servo, INPUT_PULLUP);
  attachPinChangeInterrupt(digitalPinToPCINT(motor), isrMotor, CHANGE);
  attachPinChangeInterrupt(digitalPinToPCINT(servo), isrServo, CHANGE);

  // 제어용 서보/ESC 초기화
  esc.attach(ESC_PIN);
  steerServo.attach(SERVO_PIN);
  esc.writeMicroseconds(1500);
  steerServo.writeMicroseconds(1500);
  delay(3000);
  Serial.println("시작 준비 완료");

  // LED 핀을 출력으로 설정
  pinMode(LED_LEFT, OUTPUT);
  pinMode(LED_RIGHT, OUTPUT);
  digitalWrite(LED_LEFT, LOW);
  digitalWrite(LED_RIGHT, LOW);
}

void loop() {
  // ─── RC 입력을 새로 받았을 때만 값 갱신 ─────
  if (newMotor || newServo) {
    newMotor = false;
    newServo = false;

    // 1) Steering(servoPulse)을 바로 서보에 전달
    int constrainedServo = constrain(servoPulse, 1000, 2000);
    steerServo.writeMicroseconds(constrainedServo);

    // 2) Motor (motorPulse)를 1/2로 감도 제한
    int motorDeviation      = motorPulse - 1500;          // -500 ~ +500
    int limitedMotorDev     = motorDeviation / 5;         // -250 ~ +250
    int limitedMotorOutput  = 1500 + limitedMotorDev;     // 1250 ~ 1750
    int constrainedMotorOut = constrain(limitedMotorOutput, 1000, 2000);
    esc.writeMicroseconds(constrainedMotorOut);

    // 3) 디버깅용 출력 (200ms 주기)
    static unsigned long lastDebugTime = 0;
    if (millis() - lastDebugTime >= 200) {
      Serial.print("Servo PWM: "); Serial.print(servoPulse);
      Serial.print(" | Motor PWM: "); Serial.print(motorPulse);
      Serial.print(" → Real Motor Out: "); Serial.println(constrainedMotorOut);
      lastDebugTime = millis();
    }
  }

  // ─── LED 깜빡임 제어 ─────────────────────────
  // (a) 현재 스티어링 방향 판정 (중립에서 어느 정도 벗어났는지 기준)
  //     1500을 기준으로 ±100 이하 범위는 “중립”으로 간주
  const int  deadband     = 100;
  bool leftActive  = (servoPulse < (1500 - deadband));
  bool rightActive = (servoPulse > (1500 + deadband));
  // 중립 구간: servoPulse ∈ [1400, 1600] → LED 모두 꺼짐

  unsigned long currentMillis = millis();
  if (leftActive) {
    // 좌회전 중이라면, 오른쪽 LED는 끄고 왼쪽 LED를 blinkInterval 주기로 토글
    digitalWrite(LED_RIGHT, LOW);
    if (currentMillis - lastBlinkTime >= blinkInterval) {
      ledLeftState   = !ledLeftState;
      digitalWrite(LED_LEFT, ledLeftState);
      lastBlinkTime  = currentMillis;
    }
  }
  else if (rightActive) {
    // 우회전 중이라면, 왼쪽 LED는 끄고 오른쪽 LED를 blinkInterval 주기로 토글
    digitalWrite(LED_LEFT, LOW);
    if (currentMillis - lastBlinkTime >= blinkInterval) {
      ledRightState  = !ledRightState;
      digitalWrite(LED_RIGHT, ledRightState);
      lastBlinkTime  = currentMillis;
    }
  }
  else {
    // 중립(직진 혹은 정지) 구간: 양쪽 LED 모두 꺼놓기
    digitalWrite(LED_LEFT, LOW);
    digitalWrite(LED_RIGHT, LOW);
    ledLeftState   = LOW;
    ledRightState  = LOW;
    // lastBlinkTime는 초기 상태를 유지
  }
}
