import asyncio
import json
import logging
import os
import subprocess
from typing import List

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
        self.recorded_events.append(data)
        
    async def replay(self, websocket: WebSocket):
        for event in self.recorded_events:
            await websocket.send_text(json.dumps(event))
            await asyncio.sleep(0.05) 

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

@app.post("/update")
async def update_event(request: Request):
    """endpoint for the Spark driver to push updates"""
    data = await request.json()
    logger.info(f"Received update: {data.get('type')}")
    
    # Record and Broadcast
    manager.record_event(data)
    await manager.broadcast(json.dumps(data))
    
    return {"status": "ok"}

@app.post("/run")
async def run_algorithm(request: Request):
    """Trigger the Spark job"""
    try:
        # Get job size from request body
        try:
            body = await request.json()
            job_size = body.get('size', 'small')  # Default to small
        except:
            job_size = 'small'
        
        # Detect environment and build appropriate command
        script_dir = os.path.dirname(os.path.abspath(__file__))
        main_py_path = os.path.join(script_dir, "main.py")
        
        # Detect if we're on Pi cluster or local Windows/Mac
        is_pi_cluster = os.path.exists("/home/pi/spark-env/bin/python")
        
        if is_pi_cluster:
            # Pi cluster: use virtual env python and cluster mode
            cmd = [
                "/home/pi/spark-env/bin/python", 
                main_py_path, 
                "--cluster", 
                "--ui-url", "http://127.0.0.1:8000",
                "--size", job_size
            ]
            logger.info(f"Running on Pi cluster (cluster mode) with {job_size} dataset")
        else:
            # Local machine: use current python and local mode
            import sys
            cmd = [
                sys.executable,  # Current Python interpreter
                main_py_path,
                # No --cluster flag (runs in local mode)
                "--ui-url", "http://127.0.0.1:8000",
                "--size", job_size
            ]
            logger.info(f"Running on local machine (local mode) with {job_size} dataset")
        
        logger.info(f"Command: {' '.join(cmd)}")
        
        # Run as subprocess
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            cwd=script_dir  # Set working directory to script location
        )
        logger.info(f"Started Spark job via UI request (PID: {process.pid})")
        
        return {"status": "started", "pid": process.pid, "size": job_size}
    except Exception as e:
        logger.error(f"Failed to start job: {e}")
        return {"status": "error", "message": str(e)}

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
            "completedapps": master_data.get("completedapps", [])
        }
    except Exception as e:
        logger.error(f"Failed to fetch cluster status: {e}")
        return {"status": "error", "message": str(e), "workers": []}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
