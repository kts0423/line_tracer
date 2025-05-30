#include <Servo.h>

// 핀 설정
const int ESC_PIN    = 10;  // 주행용 ESC 제어 핀
const int SERVO_PIN  = 9;   // 조향 서보 제어 핀

Servo driveESC;
Servo steeringServo;

// ESC 제어 값
const int ESC_FORWARD  = 1560;  // 전진 (기존 1560보다 높임)
const int ESC_BACKWARD = 1400;  // 후진
const int ESC_STOP     = 1500;  // 중립

// 조향 설정
const int CENTER_ANGLE = 90;
int currentAngle = CENTER_ANGLE;

void setup() {
  Serial.begin(9600);
  driveESC.attach(ESC_PIN);
  steeringServo.attach(SERVO_PIN);

  // ESC 초기화 (중립값 유지)
  driveESC.writeMicroseconds(1500);
  steeringServo.writeMicroseconds(90);
  delay(2000);  // ESC 안정화 시간

  Serial.println("[OK] RC카 시작됨");
}

void loop() {
  static String input = "";

  // 시리얼 입력 수신
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      handleCommand(input);
      input = "";
    } else {
      input += c;
    }
  }
}

void handleCommand(String cmd) {
  cmd.trim();
  Serial.print("[RX] ");
  Serial.println(cmd);

  if (!cmd.startsWith("E:")) {
    Serial.println("[WARN] 잘못된 명령 포맷");
    return;
  }

  int spaceIdx = cmd.indexOf(' ');
  if (spaceIdx == -1) {
    Serial.println("[WARN] 명령 포맷 오류: 공백 없음");
    return;
  }

  String errStr = cmd.substring(2, spaceIdx);
  String dir = cmd.substring(spaceIdx + 1);
  int err = errStr.toInt();

  // 조향 각도 계산 및 적용
  int angle = CENTER_ANGLE - constrain(err, -50, 50);
  angle = constrain(angle, 60, 120);
  steeringServo.write(angle);
  Serial.print("↪ 조향: ");
  Serial.println(angle);

  // 주행 방향 처리
  if (dir == "F") {
    driveESC.writeMicroseconds(ESC_FORWARD);
    Serial.println("🚗 전진");
  } else if (dir == "B") {
    driveESC.writeMicroseconds(ESC_BACKWARD);
    Serial.println("⏪ 후진");
  } else if (dir == "S") {
    driveESC.writeMicroseconds(ESC_STOP);
    Serial.println("⛔ 정지");
  } else {
    Serial.print("[WARN] 알 수 없는 방향 명령: ");
    Serial.println(dir);
  }
}
