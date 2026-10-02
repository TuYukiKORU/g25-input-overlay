"""Measure the actual desktop process tree with isolated, sample-based UDP replay.

Development only: pip install psutil. The injector and sampler are outside the
app's process tree. No production recordings or game settings are changed.
"""
import argparse
import bisect
import json
import os
from pathlib import Path
import shutil
import socket
import statistics
import struct
import subprocess
import sys
import threading
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2), encoding='utf-8')
    temporary.replace(path)


def worker(directory, port):
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / 'backend'))
    import telemetry
    telemetry.PORT = port
    import desktop
    import webview
    original_start = webview.start

    def control(window):
        window.events.loaded.wait(40)
        write_json(directory / 'ready.json', {'pid': os.getpid(), 'url': window.get_current_url().split('/analysis')[0]})
        sequence = None
        while True:
            try:
                command = json.loads((directory / 'control.json').read_text())
                if command['sequence'] != sequence:
                    sequence = command['sequence']
                    action = command['action']
                    if action == 'close':
                        window.destroy()
                        return
                    if action == 'minimize':
                        window.minimize()
                    if action == 'restore':
                        window.restore()
                    if action == 'probe':
                        write_json(directory / 'dom.json', window.evaluate_js("({hidden:document.hidden,charts:document.querySelectorAll('canvas').length,lap:document.querySelector('#lapSelect')?.value,language:document.documentElement.lang})"))
            except (FileNotFoundError, json.JSONDecodeError):
                pass
            time.sleep(.1)

    def start(**kwargs):
        return original_start(**kwargs, func=control, args=(webview.windows[-1],))
    webview.start = start
    return desktop.run(argparse.Namespace(data_dir=directory / 'data', demo=False, smoke_report=None))


class Replay:
    def __init__(self, port):
        source = next((ROOT / '.build-assets/test-laps').glob('*track-3/**/lap_008.json'))
        self.lap = json.loads(source.read_text())
        self.samples = self.lap['samples']
        self.times = [x['lap_time_ms'] for x in self.samples]
        self.duration = self.lap['lapTimeMs']
        self.port, self.rate, self.frames, self.packets = port, 0, 0, 0
        self.stop = threading.Event()

    def packet(self, packet_id, size):
        data = bytearray(29 + size)
        struct.pack_into('<H', data, 0, 2025)
        data[2], data[6] = 25, packet_id
        struct.pack_into('<Q', data, 7, 0xBEEFCAFE)
        struct.pack_into('<I', data, 19, self.frames)
        return data

    def send(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        elapsed = 0
        deadline = time.perf_counter()
        try:
            while not self.stop.is_set():
                rate = self.rate
                if not rate:
                    self.stop.wait(.02)
                    deadline = time.perf_counter()
                    continue
                current = int(elapsed * 1000) % self.duration
                lap_number = 1 + int(elapsed * 1000) // self.duration
                sample = self.samples[max(0, bisect.bisect_right(self.times, current) - 1)]
                packets = []
                data = self.packet(0, 22 * 60)
                struct.pack_into('<3f', data, 29, sample['position']['x'], 0, sample['position']['z'])
                struct.pack_into('<f', data, 69, sample.get('longitudinal_g', 0))
                packets.append(data)
                data = self.packet(6, 22 * 60)
                struct.pack_into('<HfffBbHB', data, 29, sample['speed'], sample['throttle'], 0, sample['brake'], 0, 5, 11000, int(sample.get('drs', 0)))
                packets.append(data)
                data = self.packet(7, 22 * 55)
                struct.pack_into('<fff', data, 34, sample.get('fuel_in_tank_kg', 10), 100, 5)
                data[54:57] = bytes([19, 17, 2])
                struct.pack_into('<ffB', data, 62, sample.get('ers_mguk_power', 0), sample.get('ers_store_energy_j', 0), sample.get('ers_mode', 1))
                packets.append(data)
                data = self.packet(13, 217)
                struct.pack_into('<8f', data, 77, *sample['wheel_speed'].values(), *sample['wheel_slip_ratio'].values())
                packets.append(data)
                data = self.packet(2, 22 * 57)
                struct.pack_into('<II', data, 29, self.duration, current)
                struct.pack_into('<f', data, 49, sample['lap_distance'])
                data[62] = lap_number
                packets.append(data)
                if self.frames % rate == 0:
                    data = self.packet(1, 666)
                    data[32], data[35], data[36] = 30, 1, 3
                    data[694] = 1
                    struct.pack_into('<III', data, 670, 1, 2, 3)
                    packets.append(data)
                    data = self.packet(5, 22 * 50)
                    struct.pack_into('<BBBBffffBBBBBBBBBffffBf', data, 29, 20,18,75,30,-3.5,-2,.1,.2,10,8,12,9,20,45,100,57,70,22.1,22.2,23.1,23.2,4,5.5)
                    packets.append(data)
                    data = self.packet(10, 22 * 46)
                    struct.pack_into('<4f', data, 29, *sample['tyre_wear'].values())
                    packets.append(data)
                for data in packets:
                    sock.sendto(data, ('127.0.0.1', self.port))
                self.frames += 1
                self.packets += len(packets)
                elapsed += 1 / rate
                deadline += 1 / rate
                self.stop.wait(max(0, deadline - time.perf_counter()))
        finally:
            sock.close()


def benchmark(directory, seconds):
    import psutil
    directory.mkdir(parents=True, exist_ok=False)
    shutil.copytree(ROOT / '.build-assets/test-laps', directory / 'data/sessions')
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    app = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--worker', '--output', str(directory), '--port', str(port)], creationflags=subprocess.CREATE_NO_WINDOW)
    sequence = 0
    def command(action):
        nonlocal sequence
        sequence += 1
        write_json(directory / 'control.json', {'sequence': sequence, 'action': action})
    replay = Replay(port)
    sender = threading.Thread(target=replay.send)
    results = {'logical_cpus': psutil.cpu_count(), 'physical_memory_bytes': psutil.virtual_memory().total,
               'method': 'Source desktop + all child WebView2 processes; replay injector excluded; full 22-car packet layouts with recorded Bahrain player samples; five high-rate packet types plus three 1 Hz types; isolated UDP port.', 'phases': []}
    try:
        limit = time.monotonic() + 60
        while not (directory / 'ready.json').exists():
            if app.poll() is not None or time.monotonic() > limit:
                raise RuntimeError('Desktop did not become ready')
            time.sleep(.25)
        ready = json.loads((directory / 'ready.json').read_text())
        parent = psutil.Process(ready['pid'])
        def api(route, data=None):
            request = Request(ready['url'] + route, data=json.dumps(data).encode() if data else None, headers={'Content-Type': 'application/json'})
            with urlopen(request, timeout=40) as response:
                return json.load(response)
        results['initial_laps'] = len(api('/api/laps'))
        sender.start()
        print('Window ready; warming up', flush=True)
        time.sleep(8)
        for label, rate, minimized in [('idle',0,False), ('recording_60hz',60,False), ('minimized_60hz',60,True), ('recording_120hz',120,False), ('analysis_60hz',60,False)]:
            command('minimize' if minimized else 'restore')
            replay.rate = rate
            time.sleep(2)
            print(f'Measuring {label}: {seconds}s', flush=True)
            observations, previous = [], {}
            primed = time.perf_counter()
            for process in [parent] + parent.children(recursive=True):
                try:
                    value = process.cpu_times()
                    previous[process.pid] = (value.user + value.system, primed)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            began = time.perf_counter()
            sent_before = replay.packets
            if label == 'analysis_60hz':
                session = '2026-08-14_16-52-57_session-c8f4d34b_track-15'
                results['analysis_job'] = api(f'/api/sessions/{session}/analysis', {'track_id':15, 'force':True})
            while time.perf_counter() - began < seconds:
                processes = [parent] + parent.children(recursive=True)
                cpu = private = rss = 0
                sampled = 0
                now = time.perf_counter()
                for process in processes:
                    try:
                        value = process.cpu_times()
                        total = value.user + value.system
                        last = previous.get(process.pid)
                        if last:
                            cpu += (total - last[0]) / (now - last[1]) * 100 / psutil.cpu_count()
                        previous[process.pid] = (total, now)
                        memory = process.memory_info()
                        private += memory.private
                        rss += memory.rss
                        sampled += 1
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                observations.append({'cpu':cpu, 'private_mb':private / 1048576, 'rss_mb':rss / 1048576, 'processes':sampled})
                time.sleep(.5)
            command('probe')
            time.sleep(.3)
            cpu_values = sorted(x['cpu'] for x in observations[1:])
            result = {'phase':label, 'seconds':round(time.perf_counter()-began,2), 'rate_hz':rate,
                      'packets_sent':replay.packets-sent_before, 'cpu_mean_percent':round(statistics.mean(cpu_values),3),
                      'cpu_p95_percent':round(cpu_values[int(.95*(len(cpu_values)-1))],3), 'cpu_peak_percent':round(max(cpu_values),3),
                      'private_mean_mb':round(statistics.mean(x['private_mb'] for x in observations),1),
                      'private_peak_mb':round(max(x['private_mb'] for x in observations),1),
                      'working_set_peak_mb':round(max(x['rss_mb'] for x in observations),1),
                      'process_count':max(x['processes'] for x in observations), 'health':api('/api/recording-health')}
            if (directory / 'dom.json').exists():
                result['dom'] = json.loads((directory / 'dom.json').read_text())
            results['phases'].append(result)
            if label == 'analysis_60hz':
                results['analysis_final_status'] = api(f'/api/sessions/{session}/analysis/status?track_id=15')
            write_json(directory / 'results.json', results)
            print(json.dumps({key:value for key,value in result.items() if key not in ('health','dom')}), flush=True)
        results['final_laps'] = len(api('/api/laps'))
        results['new_recording_bytes'] = sum(p.stat().st_size for p in (directory / 'data/sessions').glob('*beefcafe*/*/laps/*.json'))
    finally:
        replay.stop.set()
        if sender.is_alive():
            sender.join(5)
        command('close')
        try:
            app.wait(20)
        except subprocess.TimeoutExpired:
            app.terminate()
            results['close_timeout'] = True
        results['exit_code'] = app.poll()
        write_json(directory / 'results.json', results)
    print(f'Report: {directory / "results.json"}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=35)
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--port', type=int)
    args = parser.parse_args()
    if args.worker:
        raise SystemExit(worker(args.output.resolve(), args.port))
    benchmark(args.output.resolve(), args.seconds)
