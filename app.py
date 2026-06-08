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
# LOGGING
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
        method
    ]

    if row_number:

        live_monitor.update(
            f"A{row_number}:E{row_number}",
            [values]
        )

    else:

        live_monitor.append_row(values)

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

        records = database.get_all_records()

        search_value = id_number.strip().upper()

        employee = None

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

                employee = row

                employee["PHOTO"] = get_employee_photo(
                    employee["ID Number"]
                )

                permit = str(
                    employee["Phone Permit"]
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

                break

        if employee:

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
# TEST
# ==========================================

@app.get("/test")
def test():

    return {
        "status": "working",
        "database": "connected"
    }