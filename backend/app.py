import threading
from flask import Flask, jsonify, render_template
from state import latest
from telemetry import udp_loop

app = Flask(
    __name__,
    template_folder="../frontend/templates",
    static_folder="../frontend/static"
)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api")
def api():
    return jsonify(latest)

if __name__ == "__main__":
    threading.Thread(target=udp_loop, args=(latest,), daemon=True).start()
    app.run(host="0.0.0.0", port=5000)