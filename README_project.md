# 🚗 RC-Car Line Tracing 프로젝트

## 목차
- [소개](#소개)
- [시스템 구성](#시스템-구성)
- [하드웨어 요구사항](#하드웨어-요구사항)
- [소프트웨어 요구사항](#소프트웨어-요구사항)
- [설치 및 실행 방법](#설치-및-실행-방법)
- [아두이노 핀 구성 및 연결](#아두이노-핀-구성-및-연결)
- [구현 세부 내용](#구현-세부-내용)
  - [1. flask_camera_stream 모듈](#1-flask_camera_stream-모듈)
  - [2. rc_car_integrated 모듈](#2-rc_car_integrated-모듈)
  - [3. ROI 모듈](#3-ROI-모듈)
  - [4. testfornew 모듈](#4-testfornew-모듈)
- [파일 구조](#파일-구조)
- [테스트 및 결과](#테스트-및-결과)
- [향후 개선점](#향후-개선점)
- [라이선스](#라이선스)

---

## 소개
본 프로젝트는 **Raspberry Pi 5**의 **Pi Camera**와 **OpenCV**를 이용해 바닥의 검은 선을 검출하고, **Arduino Uno**로 모터·서보를 제어하여 RC Car가 자동으로 선을 따라 주행하도록 구현한 시스템입니다.
Flask/WebSocket 기반 웹 UI를 통해 **실시간 카메라 스트리밍**과 **수동·자동 모드 전환** 기능을 지원합니다.

---

## 시스템 구성

| 모듈명                   | 역할                                                         |
|--------------------------|--------------------------------------------------------------|
| flask_camera_stream      | Pi Camera 영상 WebSocket 스트리밍 및 웹 뷰어                 |
| rc_car_integrated        | OpenCV 기반 라인 검출 → PID 제어 → Arduino 제어               |
| ROI                      | Region-of-Interest 기반 파라미터 테스트                      |
| testfornew               | 신규 기능(영상 업로드·처리·로깅) 테스트용                     |
| 공통 Arduino 스케치      | 각 모듈별 `arduino/` 폴더 내 C 코드로 모터·ESC 제어 샘플      |

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

3. **Arduino 스케치 업로드**  
   각 모듈별 `*/arduino/*.c` 파일을 Arduino IDE 또는 CLI로 컴파일·업로드합니다.  
   ```bash
   arduino-cli compile --fqbn arduino:avr:uno rc_car_integrated/arduino
   arduino-cli upload -p /dev/ttyACM0 --fqbn arduino:avr:uno rc_car_integrated/arduino
   ```

4. **모듈별 서버 실행**  
   ```bash
   cd flask_camera_stream && python app.py  
   cd ../rc_car_integrated && python app.py  
   cd ../ROI && python app.py  
   cd ../testfornew && python app.py  
   ```

5. **웹 브라우저에서 확인**  
   ```
   http://<Raspberry_Pi_IP>:5000
   ```

---
