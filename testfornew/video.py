import numpy as np
import subprocess, shlex

# 검은 프레임 10장을 생성 (160×120, RGB24)
frames = [np.zeros((120,160,3), dtype=np.uint8) for _ in range(10)]

ffmpeg_cmd = (
    "ffmpeg -y -f rawvideo -pix_fmt rgb24 -s 160x120 -r 5 -i - "
    "-c:v libx264 -preset ultrafast -tune zerolatency "
    "-movflags frag_keyframe+empty_moov+default_base_moof "
    "-f mp4 out_test.mp4"
)
proc = subprocess.Popen(shlex.split(ffmpeg_cmd), stdin=subprocess.PIPE, stderr=subprocess.PIPE)
for f in frames:
    proc.stdin.write(f.tobytes())
proc.stdin.close()
proc.wait()

print("→ out_test.mp4 생성 완료")
