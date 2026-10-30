import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from typing import List, Optional, Tuple

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VizServer")

app = FastAPI()

# Mount static files (we'll serve the UI from a 'ui' directory)
UI_DIR = os.path.join(os.path.dirname(__file__), "ui")
if not os.path.exists(UI_DIR):
    os.makedirs(UI_DIR)

app.mount("/static", StaticFiles(directory=UI_DIR), name="static")

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.recorded_events: List[dict] = []
        # algorithm -> events of its latest run, for the UI's side-by-side comparison
        self.runs: dict = {}
        # wall time and coverage of the latest finished run per input, algorithm and hardware size
        self.scaling: dict = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        # Use a copy to avoid mutation errors if connections close during broadcast
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.warning(f"Failed to send message to a client: {e}")
                # Optional: self.disconnect(connection) if not already handled
            
    def record_event(self, data: dict):
        if data.get('type') == 'INIT':
            self.recorded_events = []
            algorithm = (data.get('config') or {}).get('algorithm', 'greedy')
            self.runs[algorithm] = self.recorded_events   # same list: later events land in both
        self.recorded_events.append(data)
        if data.get('type') == 'FINAL_SOLUTION' and self.recorded_events[0].get('type') == 'INIT':
            config = self.recorded_events[0].get('config') or {}
            unit = "pis" if "pis" in config else "cores" if "cores" in config else None
            if unit and data.get('elapsed_s') is not None:
                entry = {"dataset": config.get("dataset"), "algorithm": config.get("algorithm", "greedy"),
                         "t": config.get("t"), "unit": unit, "parallel": config[unit],
                         "cores_per_pi": config.get("cores_per_pi"), "machines": config.get("machines"),
                         "rounds": self.rounds(),
                         "work_s": self.work_seconds(config.get("cores_per_pi") or config.get("cores") or 1),
                         "elapsed_s": data["elapsed_s"], "coverage": data.get("coverage")}
                key = "|".join(str(entry[k]) for k in ("dataset", "algorithm", "t", "unit", "parallel"))
                self.scaling[key] = entry
        
    def rounds(self) -> int:
        """MapReduce rounds of the current run, counted as the UI counts them (numbered rounds or one per job)."""
        n = 0
        for e in self.recorded_events:
            if e.get('type') == 'ROUND':
                n = max(n, e['round']) if e.get('round') else n + 1
        return n

    def work_seconds(self, cores_per_machine: int) -> float:
        """
        Roughly how long the machines spent computing in the current run: per round, the busiest machine's
        partition times spread over its cores, summed over the rounds. The rest of the wall time is
        coordination: scheduling the jobs, shipping data to the workers, and the rounds on the driver.
        """
        total_ms = 0.0
        for e in self.recorded_events:
            if e.get('type') != 'ROUND':
                continue
            per_machine: dict = {}
            for p in e.get('partitions') or []:
                if isinstance(p.get('ms'), (int, float)):
                    key = p.get('ip') or p.get('host')
                    per_machine[key] = per_machine.get(key, 0.0) + p['ms']
            if per_machine:
                total_ms += max(per_machine.values()) / cores_per_machine
        return round(total_ms / 1000, 1)

    async def replay(self, websocket: WebSocket):
        for event in self.recorded_events:
            await websocket.send_text(json.dumps(event))
            await asyncio.sleep(0)  # the UI paces playback itself
        # Not recorded: tells this client the history is complete
        await websocket.send_text(json.dumps({"type": "REPLAY_DONE"}))

manager = ConnectionManager()

@app.get("/")
async def get():
    # Serve index.html if it exists, otherwise return a placeholder
    index_path = os.path.join(UI_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse(content="<h1>UI not found. Please create ui/index.html</h1>")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("action") == "replay":
                    await manager.replay(websocket)
            except:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/runs")
async def get_runs():
    """Latest run of each algorithm, so the UI can compare them side by side."""
    return manager.runs

@app.post("/update")
async def update_event(request: Request):
    """endpoint for the Spark driver to push updates"""
    data = await request.json()
    logger.info(f"Received update: {data.get('type')}")
    
    # Record and Broadcast
    manager.record_event(data)
    await manager.broadcast(json.dumps(data))
    
    return {"status": "ok"}

ALGORITHMS = ("greedy", "theorem8", "alg5")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Detect if we're on Pi cluster or local Windows/Mac
IS_PI_CLUSTER = os.path.exists("/home/pi/spark-env/bin/python")


def build_command(algorithm: str, job_size: str, t: int, parallel: Optional[int]) -> List[str]:
    """
    main.py runs every algorithm: greedy (threshold greedy, many rounds), theorem8 (Algorithms 6 + 7,
    two rounds) or alg5 (Algorithm 5, 2t + 2 rounds). parallel is the number of Pis (cluster) or
    cores (local) to run on; None uses all of them.
    """
    main_py_path = os.path.join(SCRIPT_DIR, "main.py")
    extra_args = ["--algorithm", algorithm]
    if algorithm == "alg5":
        extra_args += ["--t", str(t)]
    if IS_PI_CLUSTER:
        # Pi cluster: use virtual env python and cluster mode
        cmd = ["/home/pi/spark-env/bin/python", main_py_path, "--cluster"]
        if parallel:
            extra_args += ["--pis", str(parallel)]
    else:
        # Local machine: use current python and local mode (no --cluster flag)
        cmd = [sys.executable, main_py_path]
        if parallel:
            extra_args += ["--cores", str(parallel)]
    return cmd + ["--ui-url", "http://127.0.0.1:8000", "--size", job_size] + extra_args


def start_job(algorithm: str, job_size: str, t: int, parallel: Optional[int]) -> subprocess.Popen:
    cmd = build_command(algorithm, job_size, t, parallel)
    logger.info(f"Command: {' '.join(cmd)}")
    # Run as subprocess. Output goes to a log file: an unread PIPE fills up and stalls the job.
    log_path = os.path.join(SCRIPT_DIR, f"last_run_{algorithm}.log")
    with open(log_path, "w") as log_file:
        process = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            cwd=SCRIPT_DIR  # Set working directory to script location
        )
    logger.info(f"Started Spark job (PID: {process.pid}), log: {log_path}")
    return process


def parse_run_request(body: dict) -> Tuple[str, str, int]:
    job_size = body.get('size', 'small')
    if job_size not in ('small', 'medium', 'large'):
        job_size = 'small'
    algorithm = body.get('algorithm', 'greedy')
    if algorithm not in ALGORITHMS:
        algorithm = 'greedy'
    try:
        t = max(1, min(6, int(body.get('t', 2))))   # Algorithm 5's number of thresholds
    except Exception:
        t = 2
    return job_size, algorithm, t


def parse_parallel(value) -> Optional[int]:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return None


@app.post("/run")
async def run_algorithm(request: Request):
    """Trigger the Spark job"""
    try:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if analysis["running"]:
            return {"status": "busy", "message": "A full analysis is running"}
        job_size, algorithm, t = parse_run_request(body)
        process = start_job(algorithm, job_size, t, parse_parallel(body.get('parallel')))
        return {"status": "started", "pid": process.pid, "size": job_size, "algorithm": algorithm}
    except Exception as e:
        logger.error(f"Failed to start job: {e}")
        return {"status": "error", "message": str(e)}


# ---------- Full analysis: every algorithm on 1, 2, ... N Pis (or cores) ----------

def alive_workers() -> int:
    """Workers the local Spark master lists as alive (0 when there is no master)."""
    import urllib.request
    try:
        with urllib.request.urlopen("http://127.0.0.1:8080/json/", timeout=5) as response:
            workers = json.loads(response.read()).get("workers", [])
        return sum(1 for w in workers if w.get("state") == "ALIVE")
    except Exception:
        return 0


def parallel_ladder() -> List[int]:
    """The hardware sizes the analysis compares: 1..N Pis, or 1, 2, 4, ... cores up to all of them."""
    if IS_PI_CLUSTER:
        return list(range(1, max(1, alive_workers()) + 1))
    cores = os.cpu_count() or 1
    ladder = [1]
    while ladder[-1] * 2 < cores:
        ladder.append(ladder[-1] * 2)
    return ladder + ([cores] if cores > 1 else [])


analysis = {"running": False, "size": None, "t": 2, "plan": [], "done": 0, "current": None, "unit": None}
analysis_job: dict = {"task": None, "process": None}


async def run_analysis(job_size: str, t: int, plan: List[Tuple[str, int]]):
    try:
        for algorithm, parallel in plan:
            analysis["current"] = {"algorithm": algorithm, "parallel": parallel, "started_at": time.time()}
            process = start_job(algorithm, job_size, t, parallel)
            analysis_job["process"] = process
            while process.poll() is None:
                await asyncio.sleep(1)
            analysis["done"] += 1
    finally:
        analysis["running"] = False
        analysis["current"] = None
        analysis_job["process"] = None


@app.post("/analysis")
async def start_analysis(request: Request):
    """Run every algorithm on every hardware size, one run after another."""
    if analysis["running"]:
        return {"status": "busy", **analysis}
    try:
        body = await request.json()
    except Exception:
        body = {}
    job_size, _, t = parse_run_request(body)
    plan = [(a, n) for a in ALGORITHMS for n in parallel_ladder()]
    analysis.update(running=True, size=job_size, t=t, plan=plan, done=0, current=None,
                    unit="pis" if IS_PI_CLUSTER else "cores")
    analysis_job["task"] = asyncio.create_task(run_analysis(job_size, t, plan))
    return {"status": "started", **analysis}


@app.post("/analysis/stop")
async def stop_analysis():
    task, process = analysis_job["task"], analysis_job["process"]
    if task:
        task.cancel()
    if process and process.poll() is None:
        process.terminate()
    analysis["running"] = False
    return {"status": "stopped"}


@app.get("/analysis")
async def get_analysis():
    """Progress of the full analysis, and the wall time of every finished run per hardware size."""
    return {**analysis, "now": time.time(), "results": list(manager.scaling.values())}


@app.get("/cluster-status")
async def cluster_status():
    """Proxy to Spark Master JSON API with enhanced worker metrics"""
    import urllib.request
    import json as json_lib
    try:
        # Spark Master API
        master_url = "http://127.0.0.1:8080/json/"
        
        with urllib.request.urlopen(master_url) as response:
            data = response.read()
            master_data = json_lib.loads(data)
        
        # Enhance worker data with resource usage
        workers = master_data.get("workers", [])
        enhanced_workers = []
        
        for worker in workers:
            worker_info = {
                "id": worker.get("id", ""),
                "host": worker.get("host", ""),
                "port": worker.get("port", 0),
                "cores": worker.get("cores", 0),
                "coresused": worker.get("coresused", 0),
                "memory": worker.get("memory", 0),
                "memoryused": worker.get("memoryused", 0),
                "state": worker.get("state", "UNKNOWN")
            }
            
            # Calculate usage percentages
            if worker_info["cores"] > 0:
                worker_info["cpu_percent"] = round((worker_info["coresused"] / worker_info["cores"]) * 100, 1)
            else:
                worker_info["cpu_percent"] = 0
                
            if worker_info["memory"] > 0:
                worker_info["memory_percent"] = round((worker_info["memoryused"] / worker_info["memory"]) * 100, 1)
            else:
                worker_info["memory_percent"] = 0
            
            # Format memory in human-readable format
            worker_info["memory_mb"] = worker_info["memory"]
            worker_info["memoryused_mb"] = worker_info["memoryused"]
            
            enhanced_workers.append(worker_info)
        
        return {
            "status": master_data.get("status", "UNKNOWN"),
            "workers": enhanced_workers,
            "cores": master_data.get("cores", 0),
            "coresused": master_data.get("coresused", 0),
            "memory": master_data.get("memory", 0),
            "memoryused": master_data.get("memoryused", 0),
            "activeapps": master_data.get("activeapps", []),
            "completedapps": master_data.get("completedapps", []),
            "is_pi_cluster": IS_PI_CLUSTER,
            "local_cores": os.cpu_count()
        }
    except Exception as e:
        logger.error(f"Failed to fetch cluster status: {e}")
        return {"status": "error", "message": str(e), "workers": [],
                "is_pi_cluster": IS_PI_CLUSTER, "local_cores": os.cpu_count()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
