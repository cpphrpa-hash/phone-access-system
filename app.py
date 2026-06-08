from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from datetime import datetime

# ==========================================
# FASTAPI
# ==========================================

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

# ==========================================
# CONFIG
# ==========================================

SHEET_ID = "138K3XCh1Z_YWDXD_SciP3Lvind_8BdLO1tQJlqOAqNE"

PHOTO_FOLDER_ID = "1ZXgDfX9FW0oM_QLl-jPQJlGKCbATs-xw"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# ==========================================
# GOOGLE AUTH
# ==========================================

creds = Credentials.from_service_account_file(
    "credentials.json",
    scopes=SCOPES
)

gc = gspread.authorize(creds)

spreadsheet = gc.open_by_key(SHEET_ID)

database = spreadsheet.worksheet("DATABASE")
logsheet = spreadsheet.worksheet("LOG")
violations = spreadsheet.worksheet("VIOLATIONS")
live_monitor = spreadsheet.worksheet("LIVE_MONITOR")

drive_service = build(
    "drive",
    "v3",
    credentials=creds
)

# ==========================================
# PHOTO LOOKUP
# ==========================================

def get_employee_photo(id_number):

    extensions = [
        "jpg",
        "jpeg",
        "png"
    ]

    for ext in extensions:

        filename = f"{id_number}.{ext}"

        query = (
            f"name='{filename}' and "
            f"'{PHOTO_FOLDER_ID}' in parents and "
            f"trashed=false"
        )

        result = drive_service.files().list(
            q=query,
            fields="files(id,name)"
        ).execute()

        files = result.get("files", [])

        if files:

            file_id = files[0]["id"]

            return (
                f"https://drive.google.com/thumbnail"
                f"?id={file_id}&sz=w1000"
            )

    return None

# ==========================================
# LOG
# ==========================================

def write_log(employee, method, result):

    timestamp = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    logsheet.append_row([
        timestamp,
        method,
        employee["ID Number"],
        employee["Name"],
        employee["Department"],
        result
    ])

# ==========================================
# VIOLATION
# ==========================================

def write_violation(employee, method):

    timestamp = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    violations.append_row([
        timestamp,
        employee["ID Number"],
        employee["Name"],
        employee["Department"],
        "Phone Not Allowed",
        method
    ])

# ==========================================
# LIVE MONITOR
# ==========================================

def update_live_monitor(employee, method, result):

    timestamp = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    records = live_monitor.get_all_records()

    row_number = None

    for idx, row in enumerate(records, start=2):

        if (
            str(row.get("ID Number", "")).strip()
            ==
            str(employee["ID Number"]).strip()
        ):

            row_number = idx
            break

    values = [
        employee["ID Number"],
        employee["Name"],
        timestamp,
        result,
        method,
        get_employee_photo(
        employee["ID Number"]
        )
    ]

    if row_number:

        live_monitor.update(
            f"A{row_number}:E{row_number}",
            [values]
        )

    else:

        live_monitor.append_row(values)

# ==========================================
# EMPLOYEE SEARCH
# ==========================================

def find_employee(search_value):

    records = database.get_all_records()

    search_value = str(
        search_value
    ).strip().upper()

    for row in records:

        db_id = str(
            row.get("ID Number", "")
        ).strip().upper()

        db_rfid = str(
            row.get("RFID UID", "")
        ).strip().upper()

        if (
            search_value == db_id
            or
            search_value == db_rfid
        ):

            row["PHOTO"] = get_employee_photo(
                row["ID Number"]
            )

            return row

    return None
# ==========================================
# HOME
# ==========================================

@app.get("/", response_class=HTMLResponse)
def home(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "employee": None,
            "message": ""
        }
    )

# ==========================================
# SCAN
# ==========================================

@app.post("/scan", response_class=HTMLResponse)
def scan(
    request: Request,
    id_number: str = Form(...)
):

    try:

        employee = find_employee(
            id_number
        )

        if employee:

            permit = str(
                employee.get(
                    "Phone Permit",
                    ""
                )
            ).upper()

            if permit == "YES":

                result = "ALLOWED"

            else:

                result = "DENIED"

            write_log(
                employee,
                "MANUAL",
                result
            )

            update_live_monitor(
                employee,
                "MANUAL",
                result
            )

            if result == "DENIED":

                write_violation(
                    employee,
                    "MANUAL"
                )

            return templates.TemplateResponse(
                request=request,
                name="index.html",
                context={
                    "employee": employee,
                    "message": ""
                }
            )

        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "employee": None,
                "message": "Employee Not Found"
            }
        )

    except Exception as e:

        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "employee": None,
                "message": str(e)
            }
        )

# ==========================================
# DASHBOARD
# ==========================================

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):

    try:

        employees = database.get_all_records()
        logs = logsheet.get_all_records()
        violation_rows = violations.get_all_records()

        total_employees = len(
            employees
        )

        allowed_today = 0
        denied_today = 0

        for row in logs:

            result = str(
                row.get(
                    "Result",
                    ""
                )
            ).upper()

            if result == "ALLOWED":

                allowed_today += 1

            elif result == "DENIED":

                denied_today += 1

        recent_logs = list(
            reversed(logs[-20:])
        )

        recent_violations = list(
            reversed(
                violation_rows[-20:]
            )
        )

        return templates.TemplateResponse(
            request=request,
            name="dashboard.html",
            context={
                "total_employees":
                total_employees,

                "allowed_today":
                allowed_today,

                "denied_today":
                denied_today,

                "violation_count":
                len(
                    violation_rows
                ),

                "recent_logs":
                recent_logs,

                "recent_violations":
                recent_violations
            }
        )

    except Exception as e:

        return HTMLResponse(
            f"""
            <h1>Dashboard Error</h1>
            <pre>{e}</pre>
            """
        )

# ==========================================
# LIVE MONITOR API
# ==========================================

@app.get("/api/live-monitor")
def api_live_monitor():

    try:

        records = (
            live_monitor
            .get_all_records()
        )

        records.reverse()

        return records[:50]

    except Exception as e:

        return {
            "error": str(e)
        }

# ==========================================
# RECENT LOGS API
# ==========================================

@app.get("/api/logs")
def api_logs():

    try:

        records = (
            logsheet
            .get_all_records()
        )

        records.reverse()

        return records[:50]

    except Exception as e:

        return {
            "error": str(e)
        }
@app.get("/live-monitor", response_class=HTMLResponse)
def live_monitor_page(request: Request):

    records = live_monitor.get_all_records()

    records.reverse()

    return templates.TemplateResponse(
        request=request,
        name="live_monitor.html",
        context={
            "records": records[:50]
        }
    )
# ==========================================
# TEST
# ==========================================
@app.get("/live-monitor", response_class=HTMLResponse)
def live_monitor_page(request: Request):

    records = live_monitor.get_all_records()

    records.reverse()

    return templates.TemplateResponse(
        request=request,
        name="live_monitor.html",
        context={
            "records": records[:50]
        }
    )
@app.get("/test")
def test():

    return {
        "status": "working",
        "database": "connected",
        "sheet_id": SHEET_ID
    }