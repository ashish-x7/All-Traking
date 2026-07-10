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
        invoice_no TEXT,
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
    # Migration step to add invoice_no if table already exists
    try:
        cursor.execute("ALTER TABLE shipments ADD COLUMN invoice_no TEXT;")
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

def find_col_value(row, aliases) -> str:
    # Normalized search over row keys
    row_dict = {str(k).strip().lower(): v for k, v in row.items()}
    for alias in aliases:
        norm_alias = alias.strip().lower()
        if norm_alias in row_dict:
            val = row_dict[norm_alias]
            if pd.notna(val):
                return str(val).strip()
    return ""

@app.post('/api/upload')
async def upload_file(file: UploadFile = File(...)):
    filename = file.filename
    ext = os.path.splitext(filename)[1].lower()
    
    if ext not in ['.csv', '.xlsx', '.xls']:
        raise HTTPException(status_code=400, detail="Unsupported file format. Please upload CSV or Excel.")

    contents = await file.read()
    shipments = []

    invoice_aliases = ['invoice no', 'invoice_no', 'invoice no.', 'invoice', 'invoice number', 'inv no', 'inv_no', 'invoice#', 'inv']
    awb_aliases = ['awb', 'awb no', 'awb no.', 'awb number', 'tracking number', 'tracking_number', 'tracking no', 'tracking_no', 'tracking #', 'waybill']
    courier_aliases = ['courier', 'courier partner', 'courier_partner', 'courier name', 'courier_name', 'partner', 'logistic', 'logistics']

    try:
        if ext == '.csv':
            decoded = contents.decode('utf-8')
            csv_reader = csv.DictReader(io.StringIO(decoded))
            for row in csv_reader:
                invoice = find_col_value(row, invoice_aliases)
                awb = find_col_value(row, awb_aliases)
                courier = find_col_value(row, courier_aliases)
                
                if awb:
                    clean_awb = clean_tracking_number(awb)
                    if clean_awb:
                        shipments.append({
                            "invoice_no": invoice,
                            "tracking_number": clean_awb,
                            "courier": courier if courier else "Delhivery",
                            "status": "Pending",
                            "last_location": "Awaiting scan",
                            "timestamp": "-",
                            "last_sync": "-"
                        })
        else:
            df = pd.read_excel(io.BytesIO(contents), dtype=str)
            for _, row in df.iterrows():
                # row can be converted to dict to use find_col_value
                row_dict = row.to_dict()
                invoice = find_col_value(row_dict, invoice_aliases)
                awb = find_col_value(row_dict, awb_aliases)
                courier = find_col_value(row_dict, courier_aliases)
                
                if awb and str(awb).strip():
                    clean_awb = clean_tracking_number(awb)
                    shipments.append({
                        "invoice_no": invoice,
                        "tracking_number": clean_awb,
                        "courier": courier if courier else "Delhivery",
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
        INSERT INTO shipments (task_id, invoice_no, tracking_number, courier, status, last_location, timestamp, last_sync)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (task_id, s.get("invoice_no", ""), s["tracking_number"], s["courier"], s["status"], s["last_location"], s["timestamp"], "-"))
        
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
    cursor.execute("SELECT invoice_no, tracking_number, courier, status, last_location, timestamp, last_sync FROM shipments WHERE task_id = ?", (task_id,))
    shipment_rows = cursor.fetchall()
    shipments = []
    for r in shipment_rows:
        shipments.append({
            "invoice_no": r[0] or "",
            "tracking_number": r[1],
            "courier": r[2],
            "status": r[3],
            "last_location": r[4],
            "timestamp": r[5],
            "last_sync": r[6] or "-"
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
    cursor.execute("SELECT invoice_no, tracking_number, courier, status, last_location, timestamp, last_sync FROM shipments WHERE task_id = ?", (task_id,))
    shipment_rows = cursor.fetchall()
    conn.close()
    
    if not shipment_rows:
        raise HTTPException(status_code=404, detail="Task ID not found")
        
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Tracking Results"

    # Define headers
    headers = ["Invoice No.", "AWB No.", "Courier Partner", "Status", "Last Location", "Timestamp", "Last Sync"]
    ws.append(headers)

    # Set Header styling (bold, light gray background, center align)
    header_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
    header_font = Font(name="Segoe UI", size=11, bold=True, color="334155")
    header_align = Alignment(horizontal="center", vertical="center")

    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_align

    # Add data rows with colors matching the frontend palette
    AWB_COLORS_HEX = [
        '1E40AF', '9D174D', '065F46', '92400E', '5B21B6',
        'C2410C', '155E75', '9F1239', '166534', '3730A3',
        '854D0E', '6B21A8', '134E4A', '991B1B', '075985',
        '86198F', '3F6212', '334155', 'BE123C', '115E59',
        'A21CAF', '14532D', '1E3A8A', '78350F', '831843',
        '4C1D95', '064E3B', '9A3412', '0F172A', '713F12'
    ]

    for idx, r in enumerate(shipment_rows):
        row_num = idx + 2
        row_color = AWB_COLORS_HEX[idx % len(AWB_COLORS_HEX)]
        row_font = Font(name="Segoe UI", size=11, color=row_color)
        
        # Write values
        values = [
            r[0] or "",
            r[1] or "",
            r[2] or "",
            r[3] or "",
            r[4] or "",
            r[5] or "",
            r[6] or "-"
        ]
        
        for col_idx, val in enumerate(values, start=1):
            cell = ws.cell(row=row_num, column=col_idx, value=val)
            cell.font = row_font
            # Alignments: Left align for text/location, Center for status/numbers/dates
            if col_idx in [1, 2, 4, 6, 7]: # Invoice, AWB, Status, Timestamp, Last Sync
                cell.alignment = Alignment(horizontal="center")
            else:
                cell.alignment = Alignment(horizontal="left")

    # Auto-adjust column widths
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            if cell.value:
                max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

    # Save to dynamic buffer
    out_buf = io.BytesIO()
    wb.save(out_buf)
    out_buf.seek(0)

    return StreamingResponse(
        out_buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=tracking_export_{task_id[:8]}.xlsx"}
    )



@app.get('/api/latest')
async def get_latest_task():
    """Return the most recent task's shipments so the UI can restore on page refresh."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get the most recent task
    cursor.execute("SELECT task_id FROM tasks ORDER BY created_at DESC LIMIT 1")
    task_row = cursor.fetchone()

    if not task_row:
        conn.close()
        return {"task_id": None, "shipments": [], "stats": {"total": 0, "delivered": 0, "transit": 0, "failed": 0, "api_calls": 0}}

    task_id = task_row[0]

    # Get shipments
    cursor.execute("SELECT invoice_no, tracking_number, courier, status, last_location, timestamp, last_sync FROM shipments WHERE task_id = ?", (task_id,))
    shipment_rows = cursor.fetchall()
    shipments = []
    for r in shipment_rows:
        shipments.append({
            "invoice_no": r[0] or "",
            "tracking_number": r[1],
            "courier": r[2],
            "status": r[3],
            "last_location": r[4],
            "timestamp": r[5],
            "last_sync": r[6] or "-"
        })

    # Get today's API calls count
    cursor.execute("SELECT COUNT(*) FROM api_usage WHERE timestamp >= datetime('now', 'start of day');")
    today_api_calls = cursor.fetchone()[0]

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


@app.delete('/api/clear')
async def clear_all_data():
    """Delete all tasks, shipments, and logs from the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM logs")
    cursor.execute("DELETE FROM shipments")
    cursor.execute("DELETE FROM tasks")
    conn.commit()
    conn.close()
    return {"status": "cleared"}
