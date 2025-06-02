#include <Servo.h>

// ───── 핀 설정 ─────
const int ESC_PIN    = 10;  // 주행용 ESC 제어 핀
const int SERVO_PIN  = 9;   // 조향 서보 제어 핀

Servo driveESC;
Servo steeringServo;

// ───── 기준값 ─────
const int STOP_PWM      = 1500;  // 중립(정지) 펄스
const int FORWARD_PWM   = 1560;  // 전진 펄스
const int REVERSE_PWM   = 1440;  // 후진 펄스

// ───── 조향 서보 보정 범위 ─────
// Python 쪽에서 steer_angle은 50~130 범위로 설정됨
// 이를 서보 PWM(예: 1100~1900)으로 매핑
const int STEER_ANGLE_MIN   = 50;   // Python 출력 최소 각도
const int STEER_ANGLE_MAX   = 130;  // Python 출력 최대 각도
const int SERVO_PWM_MIN     = 1100; // 서보가 최대 왼쪽(50도)일 때 펄스
const int SERVO_PWM_MAX     = 1900; // 서보가 최대 오른쪽(130도)일 때 펄스

int currentAngle     = 90;  // “현재” 조향 각도 (Python의 steer_angle)
String currentDir    = "S"; // “현재” 진행 방향 ("F"/"B"/"S")

void setup() {
  Serial.begin(9600);
  driveESC.attach(ESC_PIN);
  steeringServo.attach(SERVO_PIN);

  // 초기 상태: 정지 & 중립 조향
  driveESC.writeMicroseconds(STOP_PWM);
  steeringServo.writeMicroseconds(
      map(currentAngle,
          STEER_ANGLE_MIN, STEER_ANGLE_MAX,
          SERVO_PWM_MIN, SERVO_PWM_MAX)
  );
  delay(2000);  // ESC 캘리브레이션 대기

  Serial.println("[OK] RC카 준비 완료");
}

void loop() {
  static String input = "";

  // 시리얼로부터 한 줄(개행 포함)씩 버퍼링
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

// ─────────────────────────────────────────────────────────────────────────────
// handleCommand: Python에서 보낸 "E:<angle> D:<dir>" 형태 명령을 파싱해
//                조향 서보와 ESC(주행)를 제어함.
//    - angle:  50~130 범위의 정수, 90일 때 서보 중립
//    - dir:    "F" 전진, "B" 후진, "S" 정지
// ─────────────────────────────────────────────────────────────────────────────
void handleCommand(String cmd) {
  cmd.trim();
  Serial.println("[RX] " + cmd);

  int e_idx = cmd.indexOf("E:");
  int d_idx = cmd.indexOf("D:");

  // "E:" 와 "D:" 모두 존재하면 유효 명령으로 간주
  if (e_idx != -1 && d_idx != -1) {
    // ─ 조향 각도 파싱 ─
    int angle = cmd.substring(e_idx + 2, d_idx).toInt();
    // Python 쪽 steer_angle이 50~130 범위임을 가정
    angle = constrain(angle, STEER_ANGLE_MIN, STEER_ANGLE_MAX);

    // ─ 진행 방향 파싱 ─
    String dir = cmd.substring(d_idx + 2);
    dir.toUpperCase();  // 혹시 소문자 들어올 경우 대비

    // ─ 조향 제어 ─
    if (angle != currentAngle) {
      // steer_angle(50~130) → 서보 PWM(1100~1900)으로 매핑
      int pwm = map(angle,
                    STEER_ANGLE_MIN, STEER_ANGLE_MAX,
                    SERVO_PWM_MIN, SERVO_PWM_MAX);
      steeringServo.writeMicroseconds(pwm);
      currentAngle = angle;
      Serial.print("🧭 조향(PWM): ");
      Serial.println(pwm);
    }

    // ─ 속도(ESC) 제어 ─
    if (dir != currentDir) {
      int pwm = STOP_PWM;

      if (dir == "F") {
        pwm = FORWARD_PWM;
      } else if (dir == "B") {
        pwm = REVERSE_PWM;
      } else if (dir == "S") {
        pwm = STOP_PWM;
      } else {
        // 알 수 없는 방향이면 정지
        pwm = STOP_PWM;
        dir = "S";
      }

      // 방향 전환 시 ESC 보호를 위해 중간에 정지
      if ((currentDir == "F" && dir == "B") ||
          (currentDir == "B" && dir == "F")) {
        driveESC.writeMicroseconds(STOP_PWM);
        delay(300);
      }

      driveESC.writeMicroseconds(pwm);
      currentDir = dir;
      Serial.print("⚡ 주행: ");
      Serial.println(dir);
    }

  } else {
    // 유효하지 않은 포맷이면 즉시 정지
    driveESC.writeMicroseconds(STOP_PWM);
    currentDir = "S";
    Serial.println("⛔ 정지: 알 수 없는 명령 → " + cmd);
  }
}

// ─────────────────────────────────────────────────────────────────────────────