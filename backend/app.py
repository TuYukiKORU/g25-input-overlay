import socket
import struct
import threading
import time
from flask import Flask, jsonify, render_template_string

PORT = 20777
HEADER_SIZE = 29
CAR_TELEMETRY_PACKET_ID = 6
CAR_TELEMETRY_DATA_SIZE = 60
LAP_DATA_PACKET_ID = 2
LAP_DATA_SIZE = 57
CAR_STATUS_PACKET_ID = 7
CAR_STATUS_DATA_SIZE = 55

latest = {
    "speed": 0,
    "gear": 0,
    "throttle": 0,
    "brake": 0,
    "steer": 0,
    "rpm": 0,
    "lap_time": "--:--.---",
    "drs": 0,
    "ers": 0,
    "ers_percent": 0,
    "updated": 0,
}

app = Flask(__name__)

HTML = """
<!doctype html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    * { box-sizing: border-box; }

    body {
      margin: 0;
      background:
        radial-gradient(circle at top, #202020, #050505 70%);
      color: white;
      font-family: Arial, sans-serif;
      overflow: hidden;
    }

    .dash {
      height: 100vh;
      padding: 18px;
      display: grid;
      grid-template-rows: 1.2fr 0.9fr 1.2fr 1.3fr 1.3fr;
      gap: 14px;
    }

    .panel {
      background: rgba(20, 20, 20, 0.92);
      border: 1px solid #333;
      border-radius: 18px;
      box-shadow: 0 0 18px rgba(255,255,255,0.05);
      padding: 14px;
    }

    .top {
      display: grid;
      grid-template-columns: 1fr 1fr 2fr;
      gap: 14px;
    }

    .drs.active {
      color: #7CFF3A;
      box-shadow: 0 0 30px rgba(124,255,58,0.75);
      border-color: #7CFF3A;
    }

    .ers.active {
      color: #FFD21F;
      box-shadow: 0 0 30px rgba(255,210,31,0.75);
      border-color: #FFD21F;
    }

    .label {
      color: #aaa;
      font-size: 18px;
      letter-spacing: 2px;
    }

    .big {
      font-size: 46px;
      font-weight: 900;
      margin-top: 10px;
    }

    .lap .time {
      font-size: 64px;
      font-weight: 900;
      letter-spacing: 3px;
    }

    .middle {
      display: grid;
      grid-template-columns: 1fr 0.8fr 2fr;
      gap: 14px;
    }

    .speed-value {
      font-size: 58px;
      font-weight: 900;
    }

    .gear-value {
      font-size: 68px;
      font-weight: 900;
    }

    .rpm-value {
      font-size: 42px;
      font-weight: 900;
    }

    .rpm-bar {
      display: flex;
      gap: 4px;
      margin-top: 14px;
    }

    .rpm-block {
      flex: 1;
      height: 24px;
      background: #222;
      border-radius: 4px;
    }

    .rpm-block.on.green { background: #72ff28; }
    .rpm-block.on.yellow { background: #ffd21f; }
    .rpm-block.on.red { background: #ff3030; }

    .graph-panel {
        position: relative;
        min-height: 0;
        overflow: hidden;
    }

    canvas {
      width: 100%;
      height: 100%;
      display: block;
    }

    .graph-title {
      position: absolute;
      top: 12px;
      left: 16px;
      font-size: 20px;
      font-weight: bold;
      letter-spacing: 2px;
    }

    .graph-value {
      position: absolute;
      top: 12px;
      right: 16px;
      font-size: 24px;
      font-weight: bold;
    }

    .throttle-color { color: #72ff28; }
    .brake-color { color: #ff3030; }
  </style>
</head>

<body>
  <div class="dash">

    <div class="top">
      <div id="drsPanel" class="panel drs">
        <div class="label">DRS</div>
        <div class="big" id="drsText">OFF</div>
      </div>

      <div id="ersPanel" class="panel ers">
        <div class="label">ERS</div>
        <div class="big" id="ersPercent">100%</div>
      </div>

      <div class="panel lap">
        <div class="label">LAP TIME</div>
        <div class="time" id="lapTime">--:--.---</div>
      </div>
    </div>

    <div class="middle">
      <div class="panel">
        <div class="label">SPEED</div>
        <div><span id="speed" class="speed-value">0</span> km/h</div>
      </div>

      <div class="panel">
        <div class="label">GEAR</div>
        <div id="gear" class="gear-value">N</div>
      </div>

      <div class="panel">
        <div class="label">RPM</div>
        <div><span id="rpm" class="rpm-value">0</span></div>
        <div id="rpmBar" class="rpm-bar"></div>
      </div>
    </div>

    <div class="panel graph-panel">
      <div class="graph-title throttle-color">THROTTLE</div>
      <div class="graph-value throttle-color"><span id="throttleValue">0</span>%</div>
      <canvas id="throttleGraph"></canvas>
    </div>

    <div class="panel graph-panel">
      <div class="graph-title brake-color">BRAKE</div>
      <div class="graph-value brake-color"><span id="brakeValue">0</span>%</div>
      <canvas id="brakeGraph"></canvas>
    </div>

  </div>

<script>
const throttleHistory = Array(160).fill(0);
const brakeHistory = Array(160).fill(0);

const rpmBar = document.getElementById("rpmBar");
for (let i = 0; i < 24; i++) {
  const b = document.createElement("div");
  b.className = "rpm-block";
  rpmBar.appendChild(b);
}

function drawGraph(canvas, data, color) {
  const ctx = canvas.getContext("2d");
  const rect = canvas.parentElement.getBoundingClientRect();
  canvas.width = rect.width;
  canvas.height = rect.height;

  const w = canvas.width;
  const h = canvas.height;

  ctx.clearRect(0, 0, w, h);

  ctx.strokeStyle = "rgba(255,255,255,0.12)";
  ctx.lineWidth = 1;
  for (let i = 1; i < 4; i++) {
    const y = h * i / 4;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
    ctx.stroke();
  }

  ctx.strokeStyle = color;
  ctx.lineWidth = 3;
  ctx.beginPath();

  data.forEach((v, i) => {
    const x = i / (data.length - 1) * w;
    const y = h - (v / 100) * h;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });

  ctx.stroke();
}

function formatGear(g) {
  if (g === 0) return "N";
  if (g === -1) return "R";
  return g;
}

async function update() {
  const r = await fetch('/api');
  const d = await r.json();

  document.getElementById('speed').textContent = d.speed;
  document.getElementById('gear').textContent = formatGear(d.gear);
  document.getElementById('rpm').textContent = d.rpm;
  document.getElementById('throttleValue').textContent = d.throttle;
  document.getElementById('brakeValue').textContent = d.brake;

  document.getElementById('lapTime').textContent = d.lap_time || "--:--.---";

  const drsActive = d.drs === true || d.drs === 1;
  const ersActive = d.ers === true || d.ers > 0;
  const ersPercent = d.ers_percent ?? 0;

  document.getElementById('drsPanel').classList.toggle('active', drsActive);
  document.getElementById('drsText').textContent = drsActive ? "ACTIVE" : "OFF";

  document.getElementById('ersPanel').classList.toggle('active', ersActive);
  document.getElementById('ersPercent').textContent = ersPercent + "%";

  const rpmBlocks = document.querySelectorAll(".rpm-block");
  const rpmPercent = Math.min(d.rpm / 13000, 1);
  const onCount = Math.round(rpmPercent * rpmBlocks.length);

  rpmBlocks.forEach((b, i) => {
    b.className = "rpm-block";
    if (i < onCount) {
      if (i < 14) b.classList.add("on", "green");
      else if (i < 20) b.classList.add("on", "yellow");
      else b.classList.add("on", "red");
    }
  });

  throttleHistory.push(d.throttle);
  throttleHistory.shift();

  brakeHistory.push(d.brake);
  brakeHistory.shift();

  drawGraph(document.getElementById("throttleGraph"), throttleHistory, "#72ff28");
  drawGraph(document.getElementById("brakeGraph"), brakeHistory, "#ff3030");
}

setInterval(update, 50);
</script>
</body>
</html>
"""

def format_lap_time(ms):
    minutes = ms // 60000
    seconds = (ms % 60000) / 1000
    return f"{minutes}:{seconds:06.3f}"

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/api")
def api():
    return jsonify(latest)

def udp_loop():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", PORT))

    while True:
        data, addr = sock.recvfrom(4096)

        packet_id = data[6]
        player_car_index = data[27]

        if packet_id == CAR_TELEMETRY_PACKET_ID:
            offset = HEADER_SIZE + player_car_index * CAR_TELEMETRY_DATA_SIZE

            speed, throttle, steer, brake, clutch, gear, rpm, drs = struct.unpack_from(
                "<HfffBbHB",
                data,
                offset
            )

            latest["speed"] = speed
            latest["gear"] = gear
            latest["throttle"] = round(throttle * 100)
            latest["brake"] = round(brake * 100)
            latest["steer"] = round(steer, 2)
            latest["rpm"] = rpm
            latest["drs"] = drs
            latest["updated"] = time.time()

        elif packet_id == LAP_DATA_PACKET_ID:
            offset = HEADER_SIZE + player_car_index * LAP_DATA_SIZE

            current_lap_time_ms = struct.unpack_from("<I", data, offset + 4)[0]

            latest["lap_time"] = format_lap_time(current_lap_time_ms)

        elif packet_id == CAR_STATUS_PACKET_ID:
            offset = HEADER_SIZE + player_car_index * CAR_STATUS_DATA_SIZE

            ers_store_energy = struct.unpack_from("<f", data, offset + 37)[0]
            ers_deploy_mode = struct.unpack_from("<B", data, offset + 41)[0]

            # 最大4MJとして％表示
            latest["ers_percent"] = round((ers_store_energy / 4000000) * 100)

            # 0 = none, 1 = medium, 2 = hotlap, 3 = overtake
            latest["ers"] = 1 if ers_deploy_mode > 2 else 0

if __name__ == "__main__":
    threading.Thread(target=udp_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=5000)