#include <Servo.h>

// ───── 핀 설정 ─────
const int ESC_PIN = 10;     // 주행용 ESC 제어 핀
const int SERVO_PIN = 9;    // 조향 서보 제어 핀

Servo driveESC;
Servo steeringServo;

// ───── 기본값 ─────
const int STOP_PWM = 1500;
int current_angle = 90;
int current_speed = STOP_PWM;

void setup() {
  Serial.begin(9600);
  driveESC.attach(ESC_PIN);
  steeringServo.attach(SERVO_PIN);

  // 초기값 설정
  driveESC.writeMicroseconds(STOP_PWM);
  steeringServo.write(current_angle);
  delay(2000);  // ESC 초기화 대기

  Serial.println("[OK] RC카 준비 완료");
}

void loop() {
  static String input = "";

  // 시리얼 데이터 수신
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (input.length() > 0) {
        handleCommand(input);
        input = "";
      }
    } else {
      input += c;
    }
  }
}

// ───── 명령 처리 함수 ─────
void handleCommand(String cmd) {
  cmd.trim();
  Serial.println("[RX] " + cmd);

  if (cmd.startsWith("E:") && cmd.indexOf("S:") > 0) {
    int e_idx = cmd.indexOf("E:");
    int s_idx = cmd.indexOf("S:");
    int angle = cmd.substring(e_idx + 2, s_idx).toInt();
    int speed = cmd.substring(s_idx + 2).toInt();

    // ─ 조향 제어 ─
    steeringServo.write(angle);
    current_angle = angle;
    Serial.print("🧭 조향: ");
    Serial.println(angle);

    // ─ 속도 제어 ─
    bool direction_change = (speed < STOP_PWM && current_speed > STOP_PWM) ||
                            (speed > STOP_PWM && current_speed < STOP_PWM);

    if (direction_change) {
      driveESC.writeMicroseconds(STOP_PWM);
      delay(300);  // 방향 전환 시 ESC 보호
    }

    // 항상 속도 명령 실행
    driveESC.writeMicroseconds(speed);
    current_speed = speed;
    Serial.print("⚡ 속도 PWM: ");
    Serial.println(speed);

  } else {
    // ─ 잘못된 명령 처리: 정지 ─
    driveESC.writeMicroseconds(STOP_PWM);
    current_speed = STOP_PWM;
    Serial.println("⛔ 정지: 알 수 없는 명령");
  }
}
