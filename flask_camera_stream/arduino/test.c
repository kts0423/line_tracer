#include <Arduino.h>
#include <Servo.h>
#include <PinChangeInterrupt.h>

// ─────────────────────────────────────────────
// 핀 정의

const int servo = 2;    // 조향조절(채널1)
const int motor = 3;    // 앞뒤조절(채널3)

const int SERVO_PIN = 9;     // 서보 제어 핀(초록색이 서보핀)
const int ESC_PIN = 10;        // ESC 제어 핀(노란색이 esc핀)

// ─────────────────────────────────────────────
// RC 수신값 변수
volatile int motorPulse = 1500;
volatile int servoPulse = 1500;
volatile unsigned long motorStart = 0;
volatile unsigned long servoStart = 0;
volatile bool newMotor = false;
volatile bool newServo = false;

// 디버깅용 변수
unsigned long lastDebugTime = 0;

// ─────────────────────────────────────────────
// 모터 및 서보
Servo esc;
Servo steerServo;

// 인터럽트 핸들러

// 채널1번 조향 장치 인터럽트 핸들러
void isrServo() {
  if (digitalRead(servo) == HIGH) { // 서보 채널 핀 HIGH 상태
    servoStart = micros();  // 서보 시작 시간 기록
  } else {
    servoPulse = micros() - servoStart; // 서보 펄스 길이 계산
    newServo = true; // 새로운 스로틀 값 수신
  }
}

// 채널3번 esc 모터 인터럽트 핸들러
void isrMotor() {
  if (digitalRead(motor) == HIGH) { // 모터 채널 핀 HIGH 상태
    motorStart = micros();  // 모터 시작 시간 기록
  } else {
    motorPulse = micros() - motorStart; // 모터 펄스 길이 계산
    newMotor = true;  // 새로운 조향 값 수신
  }
}

// ─────────────────────────────────────────────
void setup() {
  Serial.begin(9600);

  // RC 수신기 핀 설정
  pinMode(motor, INPUT_PULLUP); // 모터 채널핀 풀업저항으로 설정
  pinMode(servo, INPUT_PULLUP); // 서보 채널핀 풀업저항으로 설정
  attachPinChangeInterrupt(digitalPinToPCINT(motor), isrMotor, CHANGE); // 모터 채널 핀 인터럽트 설정
  attachPinChangeInterrupt(digitalPinToPCINT(servo), isrServo, CHANGE); // 서보 채널 핀 인터럽트 설정

  // 모터/서보 초기화
  esc.attach(ESC_PIN);
  steerServo.attach(SERVO_PIN);

  esc.writeMicroseconds(1500);     // ESC 정지 상태
  steerServo.writeMicroseconds(1500); // 서보 중립 위치

  delay(3000);  // ESC 초기화 대기
  Serial.println("시작 준비 완료");
}

void loop() {
  if (newMotor || newServo) {
    newMotor = false;
    newServo = false;

    // // 주행: 1/2 감도 제한(직관적)
    int motorDeviation = motorPulse - 1500;           // 기본 중립값 1500을 기준으로 얼마나 멀어졌는지 계산(-500 ~ +500)

    int limitedMotorDeviation = motorDeviation / 2;   // -167 ~ +167
    int limitedmotorOutput = 1500 + limitedMotorDeviation; //다시 기본 중립값 1500을 기준으로 다시 계산

    // 조향: 입력 PWM 그대로 전달
    steerServo.writeMicroseconds(constrain(servoPulse, 1000, 2000)); //혹시라도 1000uf 이하 2000uf 이상으로 나올 경우를 대비함.

    // 주행: 1/4으로 줄여서 출력 함.
    esc.writeMicroseconds(constrain(limitedmotorOutput, 1000, 2000));

    // 디버깅 출력을 200ms에 한 번씩만 출력
    if (millis() - lastDebugTime >= 200) {
      Serial.print("Servo PWM(Chanel 1): "); Serial.print(servoPulse);    
      Serial.print(" | Motor PWM(Chanel 3): "); Serial.print(motorPulse);
      Serial.print(" → Real Motor Output: "); Serial.print(limitedmotorOutput);
      Serial.println();
      lastDebugTime = millis();
    }
  }
}
