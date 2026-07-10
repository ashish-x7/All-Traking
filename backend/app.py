import os
import sys
import uuid
import csv
import io
import time
import asyncio
import sqlite3
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
from services.tracking_service import TrackingService
from scrapers.factory import ScraperFactory

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

DB_PATH = "tracking.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()
    # Create tasks table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        task_id TEXT PRIMARY KEY,
        status TEXT,
        progress INTEGER,
        current_action TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    # Create shipments table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS shipments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT,
        tracking_number TEXT,
        courier TEXT,
        status TEXT,
        last_location TEXT,
        timestamp TEXT,
        last_sync TEXT,
        FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
    );
    """)
    # Migration step to add last_sync if table already exists
    try:
        cursor.execute("ALTER TABLE shipments ADD COLUMN last_sync TEXT;")
    except sqlite3.OperationalError:
        pass
    # Create logs table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT,
        message TEXT,
        level TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
    );
    """)
    # Create api_usage table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS api_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    # Prune task data older than 24 hours
    cursor.execute("DELETE FROM tasks WHERE created_at < datetime('now', '-24 hours');")
    conn.commit()
    conn.close()

# Initialize DB on startup
init_db()

class StartTrackRequest(BaseModel):
    task_id: str

class SyncSingleRequest(BaseModel):
    task_id: str
    tracking_number: str
    courier: str

@app.get('/')
def root():
    return FileResponse("static/index.html")

def clean_tracking_number(awb_val) -> str:
    if pd.isna(awb_val):
        return ""
    s = str(awb_val).strip()
    if not s:
        return ""
        
    # If string contains scientific notation (e.g. 1.95e+14)
    if 'e' in s.lower():
        try:
            val = float(s)
            return str(int(val)) if val.is_integer() else f"{val:.0f}"
        except ValueError:
            pass
            
    # If float-like (e.g. 195042600200336.0)
    try:
        val = float(s)
        if val.is_integer():
            return str(int(val))
    except ValueError:
        pass
        
    return s

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
                awb = row.get('AWB') or row.get('Tracking Number') or row.get('tracking_number') or row.get('awb')
                courier = row.get('Courier') or row.get('courier') or row.get('Courier Partner')
                
                if awb:
                    clean_awb = clean_tracking_number(awb)
                    if clean_awb:
                        shipments.append({
                            "tracking_number": clean_awb,
                            "courier": str(courier or "Delhivery").strip(),
                            "status": "Pending",
                            "last_location": "Awaiting scan",
                            "timestamp": "-",
                            "last_sync": "-"
                        })
        else:
            df = pd.read_excel(io.BytesIO(contents))
            for _, row in df.iterrows():
                awb = row.get('AWB') or row.get('Tracking Number') or row.get('tracking_number') or row.get('awb')
                courier = row.get('Courier') or row.get('courier') or row.get('Courier Partner')
                
                if pd.notna(awb):
                    clean_awb = clean_tracking_number(awb)
                    if clean_awb:
                        shipments.append({
                            "tracking_number": clean_awb,
                            "courier": str(courier if pd.notna(courier) else "Delhivery").strip(),
                            "status": "Pending",
                            "last_location": "Awaiting scan",
                            "timestamp": "-",
                            "last_sync": "-"
                        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error parsing tracking sheet: {str(e)}")

    if not shipments:
        raise HTTPException(status_code=400, detail="No tracking numbers found in the uploaded sheet. Please check headers (AWB, Courier).")

    task_id = str(uuid.uuid4())
    
    # Save upload to database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO tasks (task_id, status, progress, current_action) VALUES (?, ?, ?, ?)", (task_id, "pending", 0, "Ready to start"))
    
    for s in shipments:
        cursor.execute("""
        INSERT INTO shipments (task_id, tracking_number, courier, status, last_location, timestamp, last_sync)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (task_id, s["tracking_number"], s["courier"], s["status"], s["last_location"], s["timestamp"], "-"))
        
    cursor.execute("INSERT INTO logs (task_id, message, level) VALUES (?, ?, ?)", (task_id, f"Successfully parsed {filename}. Found {len(shipments)} records.", "success"))
    cursor.execute("INSERT INTO logs (task_id, message, level) VALUES (?, ?, ?)", (task_id, "Ready to begin courier web scraping simulation.", "info"))
    
    # Get today's API calls count
    cursor.execute("SELECT COUNT(*) FROM api_usage WHERE timestamp >= datetime('now', 'start of day');")
    today_api_calls = cursor.fetchone()[0]

    conn.commit()
    conn.close()

    # Calculate stats
    delivered = sum(1 for s in shipments if s["status"].lower() == "delivered")
    transit = sum(1 for s in shipments if s["status"].lower() in ["in transit", "out for delivery", "picked up", "out for pickup"])
    failed = sum(1 for s in shipments if "failed" in s["status"].lower() or "invalid" in s["status"].lower() or "error" in s["status"].lower())

    stats = {
        "total": len(shipments),
        "delivered": delivered,
        "transit": transit,
        "failed": failed,
        "api_calls": today_api_calls
    }

    return {"task_id": task_id, "shipments": shipments, "stats": stats}


# Real background task runner calling TrackingService
async def run_tracking_simulation(task_id: str):
    # Retrieve shipments from database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT tracking_number, courier, status, last_location, timestamp, last_sync FROM shipments WHERE task_id = ?", (task_id,))
    rows = cursor.fetchall()
    conn.close()
    
    shipments = []
    for r in rows:
        shipments.append({
            "tracking_number": r[0],
            "courier": r[1],
            "status": r[2],
            "last_location": r[3],
            "timestamp": r[4],
            "last_sync": r[5] or "-"
        })
        
    # Set status to running
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE tasks SET status = ? WHERE task_id = ?", ("running", task_id))
    conn.commit()
    conn.close()
    
    # We define progress callback to update SQLite task
    async def progress_callback(progress, current_action, log_message, log_level):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE tasks SET progress = ?, current_action = ? WHERE task_id = ?", (progress, current_action, task_id))
        
        # Update shipments status in database
        for s in shipments:
            cursor.execute("""
            UPDATE shipments 
            SET status = ?, last_location = ?, timestamp = ?, last_sync = ? 
            WHERE task_id = ? AND tracking_number = ?
            """, (s["status"], s["last_location"], s["timestamp"], s.get("last_sync", "-"), task_id, s["tracking_number"]))
            
        cursor.execute("INSERT INTO logs (task_id, message, level) VALUES (?, ?, ?)", (task_id, log_message, log_level))
        conn.commit()
        conn.close()

    try:
        await TrackingService.track_shipments(shipments, task_id, progress_callback)
        conn = sqlite3.connect(DB_PATH)
        conn.execute("UPDATE tasks SET status = ? WHERE task_id = ?", ("completed", task_id))
        conn.commit()
        conn.close()
    except Exception as e:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE tasks SET status = ? WHERE task_id = ?", ("failed", task_id))
        cursor.execute("INSERT INTO logs (task_id, message, level) VALUES (?, ?, ?)", (task_id, f"Fatal tracking engine error: {str(e)}", "error"))
        conn.commit()
        conn.close()


@app.post('/api/track/start')
async def start_tracking(body: StartTrackRequest, background_tasks: BackgroundTasks):
    task_id = body.task_id
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM tasks WHERE task_id = ?", (task_id,))
    exists = cursor.fetchone()
    conn.close()
    
    if not exists:
        raise HTTPException(status_code=404, detail="Task ID not found")
    
    background_tasks.add_task(run_tracking_simulation, task_id)
    return {"status": "started"}


@app.post('/api/track/sync_single')
async def sync_single_shipment(body: SyncSingleRequest):
    task_id = body.task_id
    awb = body.tracking_number
    courier = body.courier
    
    scraper = ScraperFactory.get_scraper(courier)
    if not scraper:
        raise HTTPException(status_code=400, detail=f"Courier '{courier}' not supported")
        
    try:
        result = await scraper.track(awb)
        
        from datetime import datetime
        last_sync_str = datetime.now().strftime("%d-%m-%Y %I:%M:%S %p")
        
        # Update database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO api_usage DEFAULT VALUES;")
        cursor.execute("""
        UPDATE shipments 
        SET status = ?, last_location = ?, timestamp = ?, last_sync = ? 
        WHERE task_id = ? AND tracking_number = ?
        """, (result.get("status"), result.get("last_location"), result.get("timestamp"), last_sync_str, task_id, awb))
        
        # Log the manual update
        cursor.execute("""
        INSERT INTO logs (task_id, message, level) 
        VALUES (?, ?, ?)
        """, (task_id, f"Manually synced {courier} AWB {awb}. Status: {result.get('status')}", "success"))
        
        # Get today's API calls count
        cursor.execute("SELECT COUNT(*) FROM api_usage WHERE timestamp >= datetime('now', 'start of day');")
        today_api_calls = cursor.fetchone()[0]

        conn.commit()
        conn.close()
        
        return {
            "status": result.get("status"),
            "last_location": result.get("last_location"),
            "timestamp": result.get("timestamp"),
            "last_sync": last_sync_str,
            "api_calls": today_api_calls
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scrape error: {str(e)}")


@app.get('/api/track/progress')
async def get_progress(task_id: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT status, progress, current_action FROM tasks WHERE task_id = ?", (task_id,))
    task_row = cursor.fetchone()
    if not task_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Task ID not found")
        
    status, progress, current_action = task_row
    
    # Get shipments
    cursor.execute("SELECT tracking_number, courier, status, last_location, timestamp, last_sync FROM shipments WHERE task_id = ?", (task_id,))
    shipment_rows = cursor.fetchall()
    shipments = []
    for r in shipment_rows:
        shipments.append({
            "tracking_number": r[0],
            "courier": r[1],
            "status": r[2],
            "last_location": r[3],
            "timestamp": r[4],
            "last_sync": r[5] or "-"
        })
        
    # Get logs
    cursor.execute("SELECT message, level FROM logs WHERE task_id = ? ORDER BY id ASC", (task_id,))
    log_rows = cursor.fetchall()
    logs = [{"message": r[0], "level": r[1]} for r in log_rows]
    
    # Clear logs for this poll (so they are only displayed once on console)
    cursor.execute("DELETE FROM logs WHERE task_id = ?", (task_id,))
    
    # Get today's API calls count
    cursor.execute("SELECT COUNT(*) FROM api_usage WHERE timestamp >= datetime('now', 'start of day');")
    today_api_calls = cursor.fetchone()[0]
    
    conn.commit()
    conn.close()
    
    # Calculate stats
    delivered = sum(1 for s in shipments if s["status"].lower() == "delivered")
    transit = sum(1 for s in shipments if s["status"].lower() in ["in transit", "out for delivery", "picked up", "out for pickup"])
    failed = sum(1 for s in shipments if "failed" in s["status"].lower() or "invalid" in s["status"].lower() or "error" in s["status"].lower())
    
    stats = {
        "total": len(shipments),
        "delivered": delivered,
        "transit": transit,
        "failed": failed,
        "api_calls": today_api_calls
    }
    
    return {
        "status": status,
        "progress": progress,
        "current_action": current_action,
        "shipments": shipments,
        "stats": stats,
        "logs": logs
    }


@app.get('/api/export')
async def export_results(task_id: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT tracking_number, courier, status, last_location, timestamp, last_sync FROM shipments WHERE task_id = ?", (task_id,))
    shipment_rows = cursor.fetchall()
    conn.close()
    
    if not shipment_rows:
        raise HTTPException(status_code=404, detail="Task ID not found")
        
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["tracking_number", "courier", "status", "last_location", "timestamp", "last_sync"])
    writer.writeheader()
    for r in shipment_rows:
        writer.writerow({
            "tracking_number": r[0],
            "courier": r[1],
            "status": r[2],
            "last_location": r[3],
            "timestamp": r[4],
            "last_sync": r[5] or "-"
        })
        
    output.seek(0)
    
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8')),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=tracking_export_{task_id[:8]}.csv"}
    )


