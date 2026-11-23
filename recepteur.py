import gi, time, numpy as np
gi.require_version('Gst', '1.0')
from gi.repository import Gst
Gst.init(None)

pipeline = Gst.parse_launch(
    'udpsrc port=5000 caps="application/x-rtp,media=video,encoding-name=H264,payload=96,clock-rate=90000" '
    '! rtpjitterbuffer latency=50 ! rtph264depay ! h264parse ! avdec_h264 '
    '! videoconvert ! video/x-raw,format=GRAY8 ! appsink name=sink max-buffers=1 drop=true sync=false'
)
sink = pipeline.get_by_name("sink")
pipeline.set_state(Gst.State.PLAYING)
print("En attente du flux sur le port 5000... (Ctrl+C pour arrêter)")

try:
    while True:
        sample = sink.emit("try-pull-sample", Gst.SECOND)  # attend 1 s maximum
        if sample is None:
            print("Aucune image reçue depuis 1 s (l'émetteur Windows tourne-t-il ?)")
            continue
        t = time.perf_counter()
        s = sample.get_caps().get_structure(0)
        w, h = s.get_value("width"), s.get_value("height")
        buf = sample.get_buffer()
        ok, info = buf.map(Gst.MapFlags.READ)
        img = np.frombuffer(info.data, np.uint8).reshape(h, w).copy()
        buf.unmap(info)
        print(f"{t:.3f} s  |  {w}x{h}  |  luminosité moyenne = {img.mean():.1f}")
except KeyboardInterrupt:
    print("Arrêt.")
finally:
    pipeline.set_state(Gst.State.NULL)
