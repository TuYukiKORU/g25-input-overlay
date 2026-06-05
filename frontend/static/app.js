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