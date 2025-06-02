#include <Servo.h>

// ───── 핀 설정 ─────────────────────────────────────────────────────────────
const int ESC_PIN    = 10;  // 주행용 ESC 제어 핀 (PWM)
const int SERVO_PIN  = 9;   // 조향 서보 제어 핀 (PWM)

Servo driveESC;        // ESC 제어 객체
Servo steeringServo;   // 조향 서보 객체

// ───── 기준값 ───────────────────────────────────────────────────────────────
const int STOP_PWM      = 1500;  // ESC 중립(정지) 펄스
const int FORWARD_PWM   = 1560;  // ESC 전진 펄스
const int REVERSE_PWM   = 1440;  // ESC 후진 펄스

// ───── 조향 서보 보정 범위 ──────────────────────────────────────────────────
// Python 쪽 steer_angle은 50~130 범위로 전달됨
// 실제 서보 PWM(1100~1900) 범위에 “역순”으로 매핑하되(A→B, B→A),
// 여기에 추가로 trimOffset(트림)값을 더해 줄 것
const int STEER_ANGLE_MIN   = 50;   // Python에서 올 수 있는 최소 각도
const int STEER_ANGLE_MAX   = 130;  // Python에서 올 수 있는 최대 각도
const int SERVO_PWM_MIN     = 1100; // 서보가 최대 오른쪽(130도)일 때 펄스 (역순 매핑)
const int SERVO_PWM_MAX     = 1900; // 서보가 최대 왼쪽(50도)일 때 펄스

// ───── 트림(보정)값 ─────────────────────────────────────────────────────────
//  - positive 값: “중립(90)”에 더해서 오른쪽으로 보정 
//  - negative 값: “중립(90)”에 더해서 왼쪽으로 보정
// 예를 들어 trim = +5 면, Python에서 90을 보내도 실제 매핑 시에는 95로 조향됨.
int steerTrim = 0;

// ───── 상태 저장 변수 ─────────────────────────────────────────────────────
int     currentAngle  = 90;   // “실제 적용할” 조향 각도 (Python → Arduino)
String  currentDir    = "S";  // “현재” 진행 방향 ("F"/"B"/"S")
bool    hasNewCommand = false; // 새로운 명령이 들어왔는지 플래그

// ─────────────────────────────────────────────────────────────────────────────
// setup(): 처음 한 번 실행
//  - 시리얼 통신 시작
//  - ESC/서보 attach, 중립 상태(정지)로 초기화
// ─────────────────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(9600);

  driveESC.attach(ESC_PIN);
  steeringServo.attach(SERVO_PIN);

  // 초기 중립 상태 → ESC 정지, 서보 중립(90도 + trim)
  driveESC.writeMicroseconds(STOP_PWM);

  // 1) “currentAngle + trim” 을 먼저 구하고
  int initialTrimmed = constrain(currentAngle + steerTrim,
                                 STEER_ANGLE_MIN, STEER_ANGLE_MAX);
  // 2) 그 값을 (역순) map() 해서 PWM 출력
  int initPWM = map(initialTrimmed,
                    STEER_ANGLE_MIN, STEER_ANGLE_MAX,
                    SERVO_PWM_MAX, SERVO_PWM_MIN);
  steeringServo.writeMicroseconds(initPWM);

  delay(2000);  // ESC 초기화를 위한 대기(2초)

  Serial.println("[OK] RC카 준비 완료");
  Serial.print("[TRIM] 현재 트림값 = ");
  Serial.println(steerTrim);
}

// ─────────────────────────────────────────────────────────────────────────────
// serialEvent(): 시리얼 버퍼에 데이터가 들어올 때 자동 호출
//  - 한 줄('\n' 또는 '\r')씩 읽어서 handleCommand()로 넘겨 줌
// ─────────────────────────────────────────────────────────────────────────────
void serialEvent() {
  static String input = "";
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (input.length() > 0) {
        handleCommand(input);
        input = "";
        hasNewCommand = true;  // 새로운 명령 들어왔음을 표시
      }
    } else {
      input += c;
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// loop(): 반복 실행
//  - hasNewCommand == true 일 때만 ESC/서보를 업데이트
//  - 루프 사이에 짧은 delay를 주어 지나치게 빠르게 도는 걸 방지
// ─────────────────────────────────────────────────────────────────────────────
void loop() {
  if (hasNewCommand) {
    // 받은 명령 디버그 출력
    Serial.print("[UPDATE] angle=");
    Serial.print(currentAngle);
    Serial.print("  dir=");
    Serial.println(currentDir);

    // ── (1) 조향(Servo) 업데이트 ─────────────────────────────────────────────
    //  a) “currentAngle + trim” 을 먼저 계산
    int trimmedAngle = currentAngle + steerTrim;
    //  b) 범위(50~130)로 제한
    trimmedAngle = constrain(trimmedAngle, STEER_ANGLE_MIN, STEER_ANGLE_MAX);
    //  c) 역순 map: [50 ←→ 130] → [1900 ←→ 1100]
    int pwmServo = map(trimmedAngle,
                       STEER_ANGLE_MIN, STEER_ANGLE_MAX,
                       SERVO_PWM_MAX, SERVO_PWM_MIN);
    steeringServo.writeMicroseconds(pwmServo);
    Serial.print("🧭 조향 PWM → ");
    Serial.print(pwmServo);
    Serial.print("  (trimmedAngle=");
    Serial.print(trimmedAngle);
    Serial.println(")");

    // ── (2) 속도(ESC) 업데이트 ───────────────────────────────────────────────
    int pwmESC = STOP_PWM;
    if      (currentDir == "F") pwmESC = FORWARD_PWM;
    else if (currentDir == "B") pwmESC = REVERSE_PWM;
    else                         pwmESC = STOP_PWM;

    // (앞뒤 반전 시 보호용 중립 펄스)
    static String prevDir = "S";
    if ((prevDir == "F" && currentDir == "B") ||
        (prevDir == "B" && currentDir == "F")) {
      driveESC.writeMicroseconds(STOP_PWM);
      delay(200);  // 200ms 동안 정지 펄스 유지 (ESC 보호)
    }
    driveESC.writeMicroseconds(pwmESC);
    Serial.print("⚡ ESC PWM → ");
    Serial.println(pwmESC);

    prevDir = currentDir;
    Serial.println("-----------------------------");

    hasNewCommand = false;
  }

  // 너무 빠르게 도는 걸 방지하기 위해 짧게 대기
  delay(20);
}

// ─────────────────────────────────────────────────────────────────────────────
// handleCommand(cmd):
//  - Python에서 보낸 “E:<angle> D:<dir>” 문자열을 파싱
//  - currentAngle 과 currentDir 을 업데이트
// ─────────────────────────────────────────────────────────────────────────────
void handleCommand(String cmd) {
  cmd.trim();
  Serial.print("[RX] ");
  Serial.println(cmd);

  int e_idx = cmd.indexOf("E:");
  int d_idx = cmd.indexOf("D:");
  if (e_idx != -1 && d_idx != -1) {
    // ── (1) 조향 각도 파싱 ─────────────────────────────────────────────────
    int angle = cmd.substring(e_idx + 2, d_idx).toInt();
    angle = constrain(angle, STEER_ANGLE_MIN, STEER_ANGLE_MAX);
    currentAngle = angle;

    // ── (2) 진행 방향 파싱 ─────────────────────────────────────────────────
    String dir = cmd.substring(d_idx + 2);
    dir.trim();
    dir.toUpperCase();
    if (dir == "F" || dir == "B" || dir == "S") {
      currentDir = dir;
    } else {
      currentDir = "S";
    }

  } else {
    // 포맷이 이상하면 즉시 정지 & 중립으로 강제
    currentDir = "S";
    currentAngle = 90;  // 서보 중립
    Serial.println("⛔ 알 수 없는 명령, 정지 처리 → " + cmd);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
