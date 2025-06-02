#include <Servo.h>

// ───── 핀 설정 ─────────────────────────────────────────────────────────────
const int ESC_PIN    = 10;   // 주행용 ESC 제어 핀 (PWM)
const int SERVO_PIN  = 9;    // 조향 서보 제어 핀 (PWM)

// ───── 제어 객체 ────────────────────────────────────────────────────────────
Servo driveESC;
Servo steeringServo;

// ───── 기준값 ───────────────────────────────────────────────────────────────
const int STOP_PWM      = 1500;  // ESC 중립(정지) 펄스
const int FORWARD_PWM   = 1550;  // ESC 전진 펄스
const int REVERSE_PWM   = 1437;  // ESC 후진 펄스

// ───── 조향 서보 보정 범위 ──────────────────────────────────────────────────
// 이제 steer_angle이 0~180 범위로 전달됨.
// 실제 서보 PWM(1100~1900)으로 역순 매핑 + 트림 적용
const int STEER_ANGLE_MIN   =   0;   // Python 최소
const int STEER_ANGLE_MAX   = 180;   // Python 최대
const int SERVO_PWM_MIN     = 1100;  // 매핑 시 “오른쪽 끝”(180) 대응
const int SERVO_PWM_MAX     = 1900;  // 매핑 시 “왼쪽 끝”(0) 대응

// ───── 보정 오프셋 ─────────────────────────────────────────────────────────
int steerCalibration = 0;  // 예: 0, +5, -5 등

// ───── 상태 저장 변수 ─────────────────────────────────────────────────────
int     currentAngle  =  90;   // “실제 적용할” 조향 각도 (Python에서 넘어온 숫자)
char    currentDir    =  'S';  // 현재 진행 방향 ('F'/'B'/'S')
bool    hasNewCommand = false; // 새로운 명령 여부

// ───── 시리얼 수신 버퍼 ─────────────────────────────────────────────────────
static const uint8_t RECV_BUF_SIZE = 32;
char recvBuf[RECV_BUF_SIZE];
uint8_t recvIdx = 0;

// ─────────────────────────────────────────────────────────────────────────────
// setup(): 보드 초기화 시 한 번 실행
//  - 시리얼 통신 시작 (115200bps)
//  - ESC/서보 attach, 무조건 1500µs로 중립 위치 세팅
// ─────────────────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);

  driveESC.attach(ESC_PIN);
  steeringServo.attach(SERVO_PIN);

  // ESC 정지(1500µs), 서보 중립(1500µs)으로 초기화
  driveESC.writeMicroseconds(STOP_PWM);
  steeringServo.writeMicroseconds(1500);

  delay(2000);  // ESC 캘리브레이션 대기 (2초)

  Serial.println("[OK] RC카 준비 완료");
  Serial.print("[TRIM] 현재 보정값 = ");
  Serial.println(steerCalibration);
}

// ─────────────────────────────────────────────────────────────────────────────
// loop(): 반복 실행
//  - 비동기적으로 시리얼 버퍼에서 한 문장씩 조립
//  - 한 문장이 완성되면 parseCommand() 호출
//  - hasNewCommand가 true일 때만 ESC/서보 업데이트
//  - 불필요한 delay 최소화
// ─────────────────────────────────────────────────────────────────────────────
void loop() {
  // (1) 비동기 시리얼 읽기: 바이트 단위로 버퍼에 저장. '\n' 만나면 명령으로 처리.
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') {
      // CR 무시
      continue;
    }
    if (c == '\n') {
      // 줄 끝, 수신 버퍼가 비어 있지 않으면 명령 파싱
      if (recvIdx > 0) {
        recvBuf[recvIdx] = '\0';
        parseCommand(recvBuf);
        recvIdx = 0;
        hasNewCommand = true;
      }
    } else {
      // 바이트 저장, 버퍼가 가득 차면 인덱스 리셋 (오버플로우 방지)
      if (recvIdx < RECV_BUF_SIZE - 1) {
        recvBuf[recvIdx++] = c;
      } else {
        // 버퍼 가득 찼으면 초기화 (유효하지 않은 긴 메시지)
        recvIdx = 0;
      }
    }
  }

  // (2) 새로운 명령이 있을 때만 ESC/서보 업데이트
  if (hasNewCommand) {
    // ── (a) 조향 업데이트 ─────────────────────────────────────────────────
    int adjustedAngle = currentAngle + steerCalibration;
    adjustedAngle = constrain(adjustedAngle, STEER_ANGLE_MIN, STEER_ANGLE_MAX);
    // 역순 매핑: [0 → 1900] … [180 → 1100]
    int pwmServo = map(adjustedAngle,
                       STEER_ANGLE_MIN, STEER_ANGLE_MAX,
                       SERVO_PWM_MAX, SERVO_PWM_MIN);
    steeringServo.writeMicroseconds(pwmServo);

    // ── (b) ESC(속도) 업데이트 ─────────────────────────────────────────────
    int pwmESC = STOP_PWM;
    if (currentDir == 'F')      pwmESC = FORWARD_PWM;
    else if (currentDir == 'B') pwmESC = REVERSE_PWM;
    else                        pwmESC = STOP_PWM;

    // 전진↔후진 전환 시 잠깐 중립 펄스(100ms)
    static char prevDir = 'S';
    if ((prevDir == 'F' && currentDir == 'B') ||
        (prevDir == 'B' && currentDir == 'F')) {
      driveESC.writeMicroseconds(STOP_PWM);
      delay(100);  // 100ms 대기
    }
    driveESC.writeMicroseconds(pwmESC);

    prevDir = currentDir;
    hasNewCommand = false;
  }

  // (3) 짧은 루프 지연: 과부하 방지
  delay(5);
}

// ─────────────────────────────────────────────────────────────────────────────
// parseCommand(buf):
//  - recvBuf에 저장된 "E:<angle> D:<dir>" 문자열을 파싱
//  - currentAngle, currentDir 업데이트
// ─────────────────────────────────────────────────────────────────────────────
void parseCommand(const char* buf) {
  // 예: "E:75 D:F"
  const char* pE = strstr(buf, "E:");
  const char* pD = strstr(buf, "D:");
  if (pE && pD) {
    // E: 바로 뒤 숫자를 읽어서 angle로 변환
    int angle = atoi(pE + 2);
    angle = constrain(angle, STEER_ANGLE_MIN, STEER_ANGLE_MAX);
    currentAngle = angle;

    // D: 바로 뒤 문자를 dir로 저장('F','B','S')
    char dir = *(pD + 2);
    if (dir == 'F' || dir == 'B' || dir == 'S') {
      currentDir = dir;
    } else {
      currentDir = 'S';
    }
  } else {
    // 형식이 맞지 않으면 정지 명령으로 간주
    currentDir = 'S';
    currentAngle = 90;
  }
}
