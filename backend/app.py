import os
import sys
import uuid
import csv
import io
import time
import asyncio
from typing import List, Optional
from pydantic import BaseModel
import pandas as pd

# Set event loop policy on Windows for Playwright subprocess support
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="TrackShip API")

# Allow CORS for development ease
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure folders exist
os.makedirs("uploads", exist_ok=True)
os.makedirs("outputs", exist_ok=True)

# Mount static folder
app.mount("/static", StaticFiles(directory="static"), name="static")

# In-memory database to store tracking tasks
# In production, this would be a database/redis store
TASKS = {}

class StartTrackRequest(BaseModel):
    task_id: str

@app.get('/')
def root():
    return FileResponse("static/index.html")

@app.post('/api/upload')
async def upload_file(file: UploadFile = File(...)):
    filename = file.filename
    ext = os.path.splitext(filename)[1].lower()
    
    if ext not in ['.csv', '.xlsx', '.xls']:
        raise HTTPException(status_code=400, detail="Unsupported file format. Please upload CSV or Excel.")

    contents = await file.read()
    shipments = []

    try:
        if ext == '.csv':
            decoded = contents.decode('utf-8')
            csv_reader = csv.DictReader(io.StringIO(decoded))
            for row in csv_reader:
                # support common column names for AWB/Tracking number and Courier
                awb = row.get('AWB') or row.get('Tracking Number') or row.get('tracking_number') or row.get('awb')
                courier = row.get('Courier') or row.get('courier') or row.get('Courier Partner')
                
                if awb:
                    shipments.append({
                        "tracking_number": str(awb).strip(),
                        "courier": str(courier or "Delhivery").strip(),
                        "status": "Pending",
                        "last_location": "Awaiting scan",
                        "timestamp": "-"
                    })
        else:
            # Excel files
            df = pd.read_excel(io.BytesIO(contents))
            for _, row in df.iterrows():
                awb = row.get('AWB') or row.get('Tracking Number') or row.get('tracking_number') or row.get('awb')
                courier = row.get('Courier') or row.get('courier') or row.get('Courier Partner')
                
                if pd.notna(awb):
                    shipments.append({
                        "tracking_number": str(int(awb) if isinstance(awb, float) and awb.is_integer() else awb).strip(),
                        "courier": str(courier if pd.notna(courier) else "Delhivery").strip(),
                        "status": "Pending",
                        "last_location": "Awaiting scan",
                        "timestamp": "-"
                    })

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error parsing tracking sheet: {str(e)}")

    if not shipments:
        raise HTTPException(status_code=400, detail="No tracking numbers found in the uploaded sheet. Please check headers (AWB, Courier).")

    task_id = str(uuid.uuid4())
    TASKS[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "progress": 0,
        "current_action": "Ready to start",
        "shipments": shipments,
        "logs": [
            {"message": f"Successfully parsed {filename}. Found {len(shipments)} records.", "level": "success"},
            {"message": "Ready to begin courier web scraping simulation.", "level": "info"}
        ],
        "stats": {
            "total": len(shipments),
            "delivered": 0,
            "transit": 0,
            "failed": 0
        }
    }

    return {"task_id": task_id, "shipments": shipments}


from services.tracking_service import TrackingService

# Real background task runner calling TrackingService
async def run_tracking_simulation(task_id: str):
    task = TASKS.get(task_id)
    if not task:
        return

    shipments = task["shipments"]
    task["status"] = "running"
    
    # We define progress callback to update in-memory task
    async def progress_callback(progress, current_action, log_message, log_level):
        task["progress"] = progress
        task["current_action"] = current_action
        task["logs"].append({"message": log_message, "level": log_level})
        
        # Calculate stats
        delivered = sum(1 for s in shipments if s["status"].lower() == "delivered")
        transit = sum(1 for s in shipments if s["status"].lower() in ["in transit", "out for delivery", "picked up", "out for pickup"])
        failed = sum(1 for s in shipments if "failed" in s["status"].lower() or "invalid" in s["status"].lower() or "error" in s["status"].lower())
        
        task["stats"] = {
            "total": len(shipments),
            "delivered": delivered,
            "transit": transit,
            "failed": failed
        }

    try:
        await TrackingService.track_shipments(shipments, task_id, progress_callback)
        task["status"] = "completed"
    except Exception as e:
        task["status"] = "failed"
        task["logs"].append({"message": f"Fatal tracking engine error: {str(e)}", "level": "error"})



@app.post('/api/track/start')
async def start_tracking(body: StartTrackRequest, background_tasks: BackgroundTasks):
    task_id = body.task_id
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="Task ID not found")
    
    background_tasks.add_task(run_tracking_simulation, task_id)
    return {"status": "started"}


@app.get('/api/track/progress')
async def get_progress(task_id: str):
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="Task ID not found")
    
    task = TASKS[task_id]
    
    # We yield logs and clear them so they are only displayed once on the client console
    response_logs = list(task["logs"])
    task["logs"] = [] # clear logs to avoid duplicate printing in polling
    
    return {
        "status": task["status"],
        "progress": task["progress"],
        "current_action": task["current_action"],
        "shipments": task["shipments"],
        "stats": task["stats"],
        "logs": response_logs
    }


@app.get('/api/export')
async def export_results(task_id: str):
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="Task ID not found")
    
    task = TASKS[task_id]
    shipments = task["shipments"]
    
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["tracking_number", "courier", "status", "last_location", "timestamp"])
    writer.writeheader()
    for s in shipments:
        writer.writerow(s)
        
    output.seek(0)
    
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8')),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=tracking_export_{task_id[:8]}.csv"}
    )

