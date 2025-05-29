# src/serial_comm.py
import time
import yaml

# serial 패키지가 없을 때를 위한 스텁
try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None
    class list_ports:
        @staticmethod
        def comports():
            return []

class SerialComm:
    """
    Arduino 자동 포트 탐색 & 안전한 시리얼 전송
    """
    def __init__(self, cfg_path="../config.yaml"):
        cfg = yaml.safe_load(open(cfg_path))
        scfg = cfg.get('serial', {})
        self.baud       = scfg.get('baudrate', 9600)
        self.throttle_s = scfg.get('throttle_ms', 20) / 1000.0
        self.last_sent  = 0.0
        self.ser        = self.find_port()

    def find_port(self):
        """comports() 스캔, Arduino로 추정되는 포트 열기"""
        for p in list_ports.comports():
            desc = getattr(p, 'description', '').lower()
            if any(tag in desc for tag in ('arduino', 'usb serial', 'ch340')):
                if serial:
                    try:
                        s = serial.Serial(p.device, self.baud, timeout=1)
                        time.sleep(2)
                        return s
                    except Exception:
                        continue
        return None

    def send(self, error_x):
        """
        error_x 값을 "<error_x>,<checksum>\n" 형태로 전송
        throttle_s보다 빠른 연속 전송은 무시
        연결 끊기면 재탐색 시도
        """
        now = time.time()
        if now - self.last_sent < self.throttle_s:
            return
        self.last_sent = now

        payload = str(error_x)
        cs = sum(payload.encode()) & 0xFF
        packet = f"{payload},{cs}\n"

        if self.ser:
            try:
                self.ser.write(packet.encode())
            except Exception:
                try:
                    self.ser.close()
                except:
                    pass
                self.ser = self.find_port()
