"""
UNIPORT Unified Portal System - Acceptance Checker Web Dashboard
==================================================================
Production-ready FastAPI Web Application deployable on Render,
providing real-time batch checking, filtered CSV/JSON downloads,
immutable run history snapshots with 1-click rerun/redownload,
interactive student dossiers, and instant single-reg lookup.
"""

import asyncio
import csv
import io
import json
import logging
import os
import random
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# --- Environment & Paths -----------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)
(STATIC_DIR / "css").mkdir(exist_ok=True)
(STATIC_DIR / "js").mkdir(exist_ok=True)

HISTORY_DIR = BASE_DIR / "history" / "runs"
HISTORY_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_INPUT_FILE = BASE_DIR / "reg_number_files"
DEFAULT_OUTPUT_FILE = BASE_DIR / "acceptance_results.csv"

PORTAL_BASE = "https://ups.uniport.edu.ng"
ADMISSION_PAGE = f"{PORTAL_BASE}/auth/starthere"
ADMISSION_AUTH_URL = f"{PORTAL_BASE}/auth/start"
ACCEPTANCE_URL = f"{PORTAL_BASE}/admission/acceptance"

# --- FastAPI App -------------------------------------------------------------
app = FastAPI(
    title="UNIPORT UPS Acceptance Checker Dashboard",
    description="Full-featured management & monitoring GUI for UNIPORT admission acceptance status.",
    version="2.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

CSV_HEADERS = [
    "reg_number",
    "login_result",
    "surname",
    "other_names",
    "degree_type",
    "program_type",
    "faculty",
    "department",
    "course",
    "admission_mode",
    "utme_score",
    "admission_status",
    "acceptance_status",
    "email",
    "phone",
    "user_id",
    "photo_url",
    "error_message",
    "timestamp",
]

# --- App State & Manager -----------------------------------------------------
class SystemState:
    def __init__(self):
        self.lock = threading.Lock()
        self.is_running = False
        self.is_paused = False
        self.stop_requested = False
        
        self.current_run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.reg_numbers: list[str] = []
        self.results: list[dict] = []
        self.results_by_reg: dict[str, dict] = {}
        
        self.current_index = 0
        self.total_count = 0
        self.start_time: Optional[float] = None
        self.elapsed_seconds = 0.0
        
        self.min_delay = 1.2
        self.max_delay = 2.5
        
        # Ring buffer for recent activity logs
        self.logs: list[dict] = []
        self.max_logs = 300
        
        # Load initial data from disk
        self._load_initial_data()

    def _load_initial_data(self):
        # 1. Load reg numbers if file exists
        if DEFAULT_INPUT_FILE.exists():
            try:
                with open(DEFAULT_INPUT_FILE, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        c = line.strip().replace("\r", "")
                        if c and c.upper() not in ("REG NUMB", "REG NUMBER", "REG_NUMBER"):
                            self.reg_numbers.append(c)
                self.total_count = len(self.reg_numbers)
            except Exception as e:
                self.add_log("ERROR", f"Could not load default reg numbers: {e}")

        # 2. Load existing results if file exists
        if DEFAULT_OUTPUT_FILE.exists():
            try:
                with open(DEFAULT_OUTPUT_FILE, "r", encoding="utf-8", errors="replace") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        reg = row.get("reg_number")
                        if reg:
                            self.results.append(row)
                            self.results_by_reg[reg] = row
                self.add_log("INFO", f"Loaded {len(self.results)} existing results from CSV.")
                # Save initial run snapshot if not yet in history
                if self.results and not list(HISTORY_DIR.glob("*.json")):
                    self.save_run_snapshot("Initial Workspace Snapshot")
            except Exception as e:
                self.add_log("ERROR", f"Could not load previous CSV: {e}")

    def add_log(self, level: str, message: str, reg_number: str = ""):
        log_entry = {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "level": level,
            "message": message,
            "reg_number": reg_number,
        }
        with self.lock:
            self.logs.append(log_entry)
            if len(self.logs) > self.max_logs:
                self.logs.pop(0)

    def get_stats(self) -> dict:
        with self.lock:
            total_items = self.total_count
            checked = len(self.results)
            success_logins = sum(1 for r in self.results if r.get("login_result") == "SUCCESS")
            failed_logins = sum(1 for r in self.results if r.get("login_result") == "LOGIN_FAILED")
            admitted = sum(1 for r in self.results if "ADMITTED" in (r.get("admission_status") or "").upper())
            accepted = sum(1 for r in self.results if (r.get("acceptance_status") or "").strip().upper() == "ACCEPTED")
            not_accepted = sum(1 for r in self.results if "NOT ACCEPTED" in (r.get("acceptance_status") or "").strip().upper())
            
            elapsed = self.elapsed_seconds
            if self.is_running and self.start_time:
                elapsed = time.time() - self.start_time

            rate = (self.current_index / elapsed) if elapsed > 0 else 0
            eta_seconds = ((total_items - self.current_index) / rate) if rate > 0 and self.current_index < total_items else 0

            return {
                "run_id": self.current_run_id,
                "is_running": self.is_running,
                "is_paused": self.is_paused,
                "current_index": self.current_index,
                "total_items": total_items,
                "checked": checked,
                "success_logins": success_logins,
                "failed_logins": failed_logins,
                "admitted": admitted,
                "accepted": accepted,
                "not_accepted": not_accepted,
                "elapsed_seconds": int(elapsed),
                "eta_seconds": int(eta_seconds),
                "speed_per_min": round(rate * 60, 1),
                "progress_percent": round((self.current_index / total_items * 100), 1) if total_items > 0 else 0,
            }

    def save_run_snapshot(self, custom_label: str = ""):
        """Save an immutable snapshot of the current run to history/runs/."""
        if not self.results and not self.reg_numbers:
            return None

        run_id = self.current_run_id or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        snapshot_file = HISTORY_DIR / f"{run_id}.json"
        
        checked = len(self.results)
        admitted = sum(1 for r in self.results if "ADMITTED" in (r.get("admission_status") or "").upper())
        accepted = sum(1 for r in self.results if (r.get("acceptance_status") or "").strip().upper() == "ACCEPTED")
        not_accepted = sum(1 for r in self.results if "NOT ACCEPTED" in (r.get("acceptance_status") or "").strip().upper())
        failed = sum(1 for r in self.results if r.get("login_result") == "LOGIN_FAILED")

        data = {
            "run_id": run_id,
            "label": custom_label or f"Run ({datetime.now().strftime('%b %d, %Y - %H:%M')})",
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "stats": {
                "total_queue": len(self.reg_numbers),
                "checked": checked,
                "admitted": admitted,
                "accepted": accepted,
                "not_accepted": not_accepted,
                "failed_logins": failed,
            },
            "reg_numbers": list(self.reg_numbers),
            "results": list(self.results),
        }

        try:
            with open(snapshot_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.add_log("INFO", f"Saved run snapshot: {snapshot_file.name}")
            return run_id
        except Exception as e:
            self.add_log("ERROR", f"Failed to save run snapshot: {e}")
            return None


state = SystemState()

# --- Uniport Portal Scraping Engine ------------------------------------------
def create_portal_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    return session


def fetch_csrf_token(session: requests.Session) -> Optional[str]:
    try:
        resp = session.get(ADMISSION_PAGE, timeout=25)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        csrf_elem = soup.find("input", {"name": "csrf_token"})
        if csrf_elem and csrf_elem.get("value"):
            return csrf_elem["value"]
        return None
    except Exception:
        return None


def execute_portal_check(reg_number: str) -> dict:
    """Perform full login and profile extraction for a registration number."""
    record = {
        "reg_number": reg_number,
        "login_result": "ERROR",
        "surname": "",
        "other_names": "",
        "degree_type": "",
        "program_type": "",
        "faculty": "",
        "department": "",
        "course": "",
        "admission_mode": "",
        "utme_score": "",
        "admission_status": "",
        "acceptance_status": "",
        "email": "",
        "phone": "",
        "user_id": "",
        "photo_url": "",
        "error_message": "",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    session = create_portal_session()
    try:
        csrf_token = fetch_csrf_token(session)
        if not csrf_token:
            record["error_message"] = "Failed to obtain portal CSRF security token"
            return record

        payload = {
            "csrf_token": csrf_token,
            "registration_number": reg_number,
            "password": reg_number,
        }
        headers = {
            "Referer": ADMISSION_PAGE,
            "Origin": PORTAL_BASE,
            "Content-Type": "application/x-www-form-urlencoded",
        }

        resp = session.post(
            ADMISSION_AUTH_URL,
            data=payload,
            headers=headers,
            timeout=30,
            allow_redirects=True,
        )

        final_url = resp.url
        page_html = resp.text
        soup = BeautifulSoup(page_html, "html.parser")
        text_lower = soup.get_text(" ", strip=True).lower()

        if "error=invalid" in final_url or "error=" in final_url:
            err_p = soup.find("p", style=lambda s: s and "red" in s.lower() if s else False)
            record["login_result"] = "LOGIN_FAILED"
            record["error_message"] = err_p.get_text(strip=True) if err_p else "Invalid credentials"
            return record

        if "starthere" in final_url or ("admission registration" in text_lower and "enter registration number" in text_lower):
            record["login_result"] = "LOGIN_FAILED"
            record["error_message"] = "Invalid credentials (redirected to starthere)"
            return record

        if "/admission/acceptance" not in final_url and "error" not in final_url:
            try:
                acc_resp = session.get(ACCEPTANCE_URL, timeout=25)
                soup = BeautifulSoup(acc_resp.text, "html.parser")
            except Exception:
                pass

        field_map = {
            "surname": "surname",
            "othernames": "other_names",
            "degree": "degree_type",
            "program": "program_type",
            "faculty": "faculty",
            "department": "department",
            "course": "course",
            "mode": "admission_mode",
            "score": "utme_score",
            "admission_status": "admission_status",
            "acceptance_status": "acceptance_status",
            "email": "email",
            "phone": "phone",
            "userid": "user_id",
        }

        extracted_count = 0
        for input_id, key in field_map.items():
            el = soup.find("input", {"id": input_id})
            if el and el.get("value"):
                record[key] = el["value"].strip()
                extracted_count += 1

        photo_img = soup.find("img", src=lambda s: s and "utmedetails" in s if s else False)
        if photo_img and photo_img.get("src"):
            record["photo_url"] = photo_img["src"].strip()

        if extracted_count > 0 or record["admission_status"]:
            record["login_result"] = "SUCCESS"
        else:
            record["login_result"] = "SUCCESS"
            record["error_message"] = "Acceptance page reached, but form data was empty."

        return record

    except requests.Timeout:
        record["error_message"] = "Portal connection timed out"
        return record
    except Exception as e:
        record["error_message"] = str(e)
        return record
    finally:
        session.close()


# --- Background Worker Loop --------------------------------------------------
def background_checker_loop():
    """Worker loop that iterates through registration numbers in state."""
    state.add_log("INFO", f"Batch check started with {len(state.reg_numbers)} items.")
    state.start_time = time.time()

    checked_set = set(state.results_by_reg.keys())
    total = len(state.reg_numbers)

    for idx, reg in enumerate(state.reg_numbers, 1):
        if state.stop_requested:
            state.add_log("WARNING", "Batch check was stopped by user.")
            break

        while state.is_paused:
            if state.stop_requested:
                break
            time.sleep(0.5)

        if state.stop_requested:
            break

        state.current_index = idx

        # Skip if already checked
        if reg in checked_set and state.results_by_reg[reg].get("login_result") in ("SUCCESS", "LOGIN_FAILED"):
            continue

        state.add_log("INFO", f"Checking [{idx}/{total}]...", reg_number=reg)
        record = execute_portal_check(reg)

        with state.lock:
            if reg in state.results_by_reg:
                for i, r in enumerate(state.results):
                    if r.get("reg_number") == reg:
                        state.results[i] = record
                        break
            else:
                state.results.append(record)
            state.results_by_reg[reg] = record

            try:
                with open(DEFAULT_OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=CSV_HEADERS, extrasaction="ignore")
                    writer.writeheader()
                    writer.writerows(state.results)
            except Exception as e:
                state.add_log("ERROR", f"CSV write error: {e}")

        if record["login_result"] == "SUCCESS":
            name = f"{record['surname']} {record['other_names']}".strip()
            state.add_log(
                "SUCCESS",
                f"{name} | Admitted: {record['admission_status']} | Acceptance: {record['acceptance_status']} | Course: {record['course']}",
                reg_number=reg,
            )
        elif record["login_result"] == "LOGIN_FAILED":
            state.add_log("WARNING", f"Login failed: {record['error_message']}", reg_number=reg)
        else:
            state.add_log("ERROR", f"Error: {record['error_message']}", reg_number=reg)

        delay = random.uniform(state.min_delay, state.max_delay)
        time.sleep(delay)

    state.is_running = False
    state.is_paused = False
    state.stop_requested = False
    state.elapsed_seconds = time.time() - (state.start_time or time.time())
    state.add_log("INFO", "Batch run completed.")
    
    # Automatically archive completed run into history
    state.save_run_snapshot(f"Batch Run ({len(state.results)} items)")


# --- API Models --------------------------------------------------------------
class RegListUpload(BaseModel):
    reg_numbers: list[str]
    replace: bool = False

class SingleCheckRequest(BaseModel):
    reg_number: str

class SettingsUpdate(BaseModel):
    min_delay: float
    max_delay: float


def filter_data(data: list[dict], search: str = "", status_filter: str = "ALL", faculty_filter: str = "ALL") -> list[dict]:
    """Helper to apply uniform search and filters across table and export endpoints."""
    filtered = []
    search_lower = search.strip().lower()
    for row in data:
        if search_lower:
            combined = f"{row.get('reg_number','')} {row.get('surname','')} {row.get('other_names','')} {row.get('department','')} {row.get('course','')} {row.get('faculty','')}".lower()
            if search_lower not in combined:
                continue

        if status_filter == "ADMITTED":
            if "ADMITTED" not in (row.get("admission_status") or "").upper():
                continue
        elif status_filter == "ACCEPTED":
            if (row.get("acceptance_status") or "").strip().upper() != "ACCEPTED":
                continue
        elif status_filter == "NOT_ACCEPTED":
            if "NOT ACCEPTED" not in (row.get("acceptance_status") or "").strip().upper():
                continue
        elif status_filter == "LOGIN_FAILED":
            if row.get("login_result") != "LOGIN_FAILED":
                continue

        if faculty_filter != "ALL" and faculty_filter:
            if (row.get("faculty") or "").strip() != faculty_filter:
                continue

        filtered.append(row)
    return filtered


# --- API Routes --------------------------------------------------------------
@app.get("/healthz")
@app.get("/api/health")
def health():
    return {"status": "ok", "service": "uniport-ups-checker", "timestamp": time.time()}


@app.get("/api/stats")
def get_stats():
    return state.get_stats()


@app.get("/api/logs")
def get_logs():
    with state.lock:
        return {"logs": state.logs}


@app.get("/api/results")
def get_results(
    search: str = "",
    status_filter: str = "ALL",
    faculty_filter: str = "ALL",
    page: int = 1,
    page_size: int = 50,
):
    with state.lock:
        data = list(state.results)

    filtered = filter_data(data, search, status_filter, faculty_filter)
    total_records = len(filtered)
    faculties = sorted(list({r.get("faculty") for r in data if r.get("faculty")}))

    start = (page - 1) * page_size
    end = start + page_size
    page_records = filtered[start:end]

    return {
        "total": total_records,
        "page": page,
        "page_size": page_size,
        "total_pages": (total_records + page_size - 1) // page_size if total_records > 0 else 1,
        "records": page_records,
        "faculties": faculties,
    }


@app.post("/api/check-single")
def check_single(req: SingleCheckRequest):
    reg = req.reg_number.strip().upper()
    if not reg:
        raise HTTPException(status_code=400, detail="Registration number is required")

    state.add_log("INFO", f"Single live check requested for {reg}", reg_number=reg)
    result = execute_portal_check(reg)
    
    with state.lock:
        if reg in state.results_by_reg:
            for i, r in enumerate(state.results):
                if r.get("reg_number") == reg:
                    state.results[i] = result
                    break
        else:
            state.results.append(result)
        state.results_by_reg[reg] = result

    return {"status": "ok", "data": result}


@app.post("/api/control/start")
def start_checker():
    with state.lock:
        if state.is_running:
            if state.is_paused:
                state.is_paused = False
                state.add_log("INFO", "Batch checking resumed.")
                return {"status": "ok", "message": "Resumed"}
            return {"status": "already_running", "message": "Already running"}

        if not state.reg_numbers:
            raise HTTPException(status_code=400, detail="No registration numbers in queue. Please load or upload numbers first.")

        state.is_running = True
        state.is_paused = False
        state.stop_requested = False
        state.current_run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        thread = threading.Thread(target=background_checker_loop, daemon=True)
        thread.start()

    return {"status": "ok", "message": "Checker started in background", "run_id": state.current_run_id}


@app.post("/api/control/pause")
def pause_checker():
    with state.lock:
        if not state.is_running:
            return {"status": "not_running", "message": "Checker is not running"}
        state.is_paused = not state.is_paused
        status_text = "paused" if state.is_paused else "resumed"
        state.add_log("INFO", f"Checker {status_text}.")
    return {"status": "ok", "is_paused": state.is_paused}


@app.post("/api/control/stop")
def stop_checker():
    with state.lock:
        if not state.is_running:
            return {"status": "not_running", "message": "Checker is not running"}
        state.stop_requested = True
        state.is_paused = False
        state.add_log("WARNING", "Stop signal received. Saving snapshot...")
        state.save_run_snapshot("Stopped Batch Run")
    return {"status": "ok", "message": "Stop signal sent"}


@app.post("/api/control/reset")
def reset_results():
    with state.lock:
        if state.is_running:
            raise HTTPException(status_code=400, detail="Cannot reset while checker is running. Stop it first.")
        
        # Save snapshot of current run to history before clearing
        if state.results:
            state.save_run_snapshot(f"Archived Before Reset ({len(state.results)} items)")

        state.results = []
        state.results_by_reg = {}
        state.current_index = 0
        state.logs = []
        state.current_run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        if DEFAULT_OUTPUT_FILE.exists():
            try:
                DEFAULT_OUTPUT_FILE.unlink()
            except Exception:
                pass
        state.add_log("INFO", "Results and logs cleared. Previous run archived in History.")
    return {"status": "ok", "message": "Results reset and archived to history"}


@app.post("/api/upload-regs")
def upload_regs(data: RegListUpload):
    cleaned = []
    for item in data.reg_numbers:
        r = item.strip().upper().replace("\r", "")
        if r and r not in ("REG NUMB", "REG NUMBER", "REG_NUMBER"):
            cleaned.append(r)

    seen = set()
    unique_regs = []
    for r in cleaned:
        if r not in seen:
            seen.add(r)
            unique_regs.append(r)

    with state.lock:
        if data.replace:
            state.reg_numbers = unique_regs
        else:
            current_set = set(state.reg_numbers)
            for r in unique_regs:
                if r not in current_set:
                    state.reg_numbers.append(r)
                    current_set.add(r)
        
        state.total_count = len(state.reg_numbers)
        state.add_log("INFO", f"Queue updated: now contains {len(state.reg_numbers)} registration numbers.")

    return {"status": "ok", "count": len(state.reg_numbers), "added": len(unique_regs)}


@app.post("/api/settings")
def update_settings(cfg: SettingsUpdate):
    if cfg.min_delay < 0.5 or cfg.max_delay < cfg.min_delay:
        raise HTTPException(status_code=400, detail="Invalid delay values")
    state.min_delay = cfg.min_delay
    state.max_delay = cfg.max_delay
    state.add_log("INFO", f"Settings updated: Delay set to {cfg.min_delay}s - {cfg.max_delay}s")
    return {"status": "ok", "min_delay": state.min_delay, "max_delay": state.max_delay}


# --- Filtered & All Export Routes --------------------------------------------
@app.get("/api/export/csv")
def export_csv(
    search: str = "",
    status_filter: str = "ALL",
    faculty_filter: str = "ALL",
    filtered_only: bool = False,
):
    with state.lock:
        data = list(state.results)

    if filtered_only:
        data = filter_data(data, search, status_filter, faculty_filter)

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_HEADERS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(data)

    output.seek(0)
    suffix = "filtered_" if filtered_only else "all_"
    filename = f"uniport_acceptance_{suffix}{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/api/export/json")
def export_json(
    search: str = "",
    status_filter: str = "ALL",
    faculty_filter: str = "ALL",
    filtered_only: bool = False,
):
    with state.lock:
        data = list(state.results)

    if filtered_only:
        data = filter_data(data, search, status_filter, faculty_filter)

    suffix = "filtered_" if filtered_only else "all_"
    filename = f"uniport_acceptance_{suffix}{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    return JSONResponse(
        content=data,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# --- Run History Endpoints ---------------------------------------------------
@app.get("/api/history")
def list_history():
    """List all saved historical runs with metadata."""
    runs = []
    for p in sorted(HISTORY_DIR.glob("*.json"), key=os.path.getmtime, reverse=True):
        try:
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
                runs.append({
                    "run_id": d.get("run_id", p.stem),
                    "label": d.get("label", p.stem),
                    "saved_at": d.get("saved_at", ""),
                    "stats": d.get("stats", {}),
                    "record_count": len(d.get("results", [])),
                    "queue_count": len(d.get("reg_numbers", [])),
                })
        except Exception:
            continue
    return {"runs": runs}


@app.get("/api/history/{run_id}")
def get_history_detail(run_id: str):
    p = HISTORY_DIR / f"{run_id}.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="Historical run not found")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


@app.post("/api/history/{run_id}/restore")
def restore_history_run(run_id: str, load_results: bool = True):
    """Restore a historical run into the active workspace for viewing or rerun."""
    p = HISTORY_DIR / f"{run_id}.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="Historical run not found")

    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)

    with state.lock:
        if state.is_running:
            raise HTTPException(status_code=400, detail="Cannot restore run while a check is currently running. Stop it first.")

        # Archive current state first if it has unarchived data
        if state.results:
            state.save_run_snapshot(f"Snapshot before restoring {run_id}")

        state.current_run_id = data.get("run_id", run_id)
        state.reg_numbers = list(data.get("reg_numbers", []))
        state.total_count = len(state.reg_numbers)

        if load_results:
            state.results = list(data.get("results", []))
            state.results_by_reg = {r.get("reg_number"): r for r in state.results if r.get("reg_number")}
            state.current_index = len(state.results)
        else:
            state.results = []
            state.results_by_reg = {}
            state.current_index = 0

        # Also write to acceptance_results.csv
        try:
            with open(DEFAULT_OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_HEADERS, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(state.results)
        except Exception:
            pass

        state.add_log("INFO", f"Restored historical run: {data.get('label', run_id)} ({len(state.results)} results loaded)")

    return {"status": "ok", "message": f"Run {run_id} restored successfully", "stats": state.get_stats()}


@app.get("/api/history/{run_id}/export/csv")
def export_history_csv(run_id: str):
    p = HISTORY_DIR / f"{run_id}.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="Historical run not found")

    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_HEADERS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(data.get("results", []))

    output.seek(0)
    filename = f"uniport_{run_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/api/history/{run_id}/export/json")
def export_history_json(run_id: str):
    p = HISTORY_DIR / f"{run_id}.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="Historical run not found")

    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)

    filename = f"uniport_{run_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    return JSONResponse(
        content=data.get("results", []),
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.delete("/api/history/{run_id}")
def delete_history_run(run_id: str):
    p = HISTORY_DIR / f"{run_id}.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="Historical run not found")
    try:
        p.unlink()
        state.add_log("INFO", f"Deleted historical run {run_id}")
        return {"status": "ok", "message": f"Run {run_id} deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/", response_class=HTMLResponse)
def index():
    html_file = BASE_DIR / "templates" / "index.html"
    if html_file.exists():
        return HTMLResponse(content=html_file.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Loading Dashboard...</h1>")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print(f"Starting UNIPORT Dashboard on http://0.0.0.0:{port}")
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
