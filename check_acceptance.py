"""
UNIPORT Unified Portal System - Bulk Acceptance Status Checker
================================================================
Logs into https://ups.uniport.edu.ng/auth/starthere (Admission portal)
for each JAMB registration number, checks the acceptance page for
all profile details and acceptance status, and outputs results to a CSV file.

Input:  reg_number_files  (one reg number per line, first line header)
Output: acceptance_results.csv
"""

import csv
import os
import re
import sys
import time
import random
import logging
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# Force UTF-8 output on Windows
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# --- Configuration -----------------------------------------------------------
BASE_URL = "https://ups.uniport.edu.ng"
ADMISSION_PAGE = f"{BASE_URL}/auth/starthere"
ADMISSION_AUTH_URL = f"{BASE_URL}/auth/start"
ACCEPTANCE_URL = f"{BASE_URL}/admission/acceptance"

INPUT_FILE = Path(__file__).parent / "reg_number_files"
OUTPUT_FILE = Path(__file__).parent / "acceptance_results.csv"
LOG_FILE = Path(__file__).parent / "checker.log"

# Polite delay between requests (seconds)
MIN_DELAY = 1.2
MAX_DELAY = 2.5

# Retry settings
MAX_RETRIES = 3
RETRY_BACKOFF = 4  # seconds

# CSV column definition
CSV_FIELDS = [
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

# --- Logging Setup ------------------------------------------------------------
log = logging.getLogger("ups-checker")
log.setLevel(logging.INFO)

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(
    logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%H:%M:%S")
)
log.addHandler(console_handler)

# File handler
file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(
    logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%H:%M:%S")
)
log.addHandler(file_handler)


def load_reg_numbers(filepath: Path) -> list[str]:
    """Read registration numbers from input file, skipping headers."""
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    reg_numbers = []
    for line in lines:
        cleaned = line.strip().replace("\r", "")
        if not cleaned or cleaned.upper() in ("REG NUMB", "REG NUMBER", "REG_NUMBER"):
            continue
        reg_numbers.append(cleaned)

    log.info(f"Loaded {len(reg_numbers)} registration numbers from {filepath.name}")
    return reg_numbers


def get_csrf_token(session: requests.Session) -> str | None:
    """Fetch the admission login page and extract the CSRF token."""
    try:
        resp = session.get(ADMISSION_PAGE, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        csrf_input = soup.find("input", {"name": "csrf_token"})
        if csrf_input and csrf_input.get("value"):
            return csrf_input["value"]

        log.warning("CSRF token not found on admission page")
        return None
    except requests.RequestException as e:
        log.error(f"Failed to load admission page: {e}")
        return None


def attempt_login(
    session: requests.Session, reg_number: str, csrf_token: str
) -> requests.Response | None:
    """Submit the admission login form and return the response."""
    payload = {
        "csrf_token": csrf_token,
        "registration_number": reg_number,
        "password": reg_number,
    }

    headers = {
        "Referer": ADMISSION_PAGE,
        "Origin": BASE_URL,
        "Content-Type": "application/x-www-form-urlencoded",
    }

    try:
        resp = session.post(
            ADMISSION_AUTH_URL,
            data=payload,
            headers=headers,
            timeout=30,
            allow_redirects=True,
        )
        return resp
    except requests.RequestException as e:
        log.error(f"  Login request failed for {reg_number}: {e}")
        return None


def extract_admission_data(html: str, final_url: str) -> dict:
    """
    Parse the acceptance page HTML and extract all profile and admission fields.
    
    Fields available on /admission/acceptance:
      - Surname (#surname)
      - Other Names (#othernames)
      - Degree Type (#degree)
      - Program Type (#program)
      - Faculty (#faculty)
      - Department (#department)
      - Degree Course (#course)
      - Admission Mode (#mode)
      - Registration Number (#reg_no)
      - UTME Score (#score)
      - Admission Status (#admission_status)
      - Acceptance Status (#acceptance_status)
      - Email (#email)
      - Phone (#phone)
      - User ID (#userid)
      - Photo URL (img with utmedetails)
    """
    soup = BeautifulSoup(html, "html.parser")
    page_text_lower = soup.get_text(separator=" ", strip=True).lower()

    data = {
        "login_result": "UNKNOWN",
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
    }

    # --- Check for login failure ---
    if "error=invalid" in final_url or "error=" in final_url:
        error_elem = soup.find("p", style=lambda s: s and "red" in s.lower() if s else False)
        err_msg = error_elem.get_text(strip=True) if error_elem else "Invalid credentials"
        data["login_result"] = "LOGIN_FAILED"
        data["error_message"] = err_msg
        return data

    # Check if still on login/starthere page
    if "starthere" in final_url or ("admission registration" in page_text_lower and "enter registration number" in page_text_lower):
        data["login_result"] = "LOGIN_FAILED"
        data["error_message"] = "Redirected back to login page (invalid credentials)"
        return data

    # --- Extract structured input fields from acceptance page ---
    input_field_map = {
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

    found_count = 0
    for input_id, key in input_field_map.items():
        elem = soup.find("input", {"id": input_id})
        if elem and elem.get("value"):
            data[key] = elem["value"].strip()
            found_count += 1

    # Extract photo URL if present
    photo_img = soup.find("img", src=lambda s: s and "utmedetails" in s if s else False)
    if photo_img and photo_img.get("src"):
        data["photo_url"] = photo_img["src"].strip()

    if found_count > 0 or data["admission_status"]:
        data["login_result"] = "SUCCESS"
    elif "admission" in final_url:
        data["login_result"] = "SUCCESS"
        data["error_message"] = "Acceptance page loaded but form fields empty"
    else:
        data["login_result"] = "UNKNOWN"
        title = soup.find("title")
        data["error_message"] = f"Unexpected page: {title.get_text(strip=True) if title else final_url}"

    return data


def check_single_reg(reg_number: str, index: int, total: int) -> dict:
    """Check acceptance status and profile details for a single registration number."""
    result = {
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

    log.info(f"[{index}/{total}] Checking {reg_number}...")

    for attempt in range(1, MAX_RETRIES + 1):
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;"
                    "q=0.9,image/webp,*/*;q=0.8"
                ),
                "Accept-Language": "en-US,en;q=0.5",
            }
        )

        try:
            # Step 1: CSRF token
            csrf_token = get_csrf_token(session)
            if not csrf_token:
                result["error_message"] = "Could not retrieve CSRF token"
                if attempt < MAX_RETRIES:
                    log.warning(f"  Attempt {attempt}/{MAX_RETRIES} -- no CSRF, retrying in {RETRY_BACKOFF}s...")
                    time.sleep(RETRY_BACKOFF)
                    continue
                break

            # Step 2: Login via /auth/start
            resp = attempt_login(session, reg_number, csrf_token)
            if resp is None:
                result["error_message"] = "Login request failed"
                if attempt < MAX_RETRIES:
                    log.warning(f"  Attempt {attempt}/{MAX_RETRIES} -- request failed, retrying in {RETRY_BACKOFF}s...")
                    time.sleep(RETRY_BACKOFF)
                    continue
                break

            final_url = resp.url
            page_html = resp.text

            # Step 3: If logged in but not directly on /admission/acceptance, navigate to it
            if "/admission/acceptance" not in final_url and "error" not in final_url and "starthere" not in final_url:
                try:
                    acc_resp = session.get(ACCEPTANCE_URL, timeout=30)
                    page_html = acc_resp.text
                    final_url = acc_resp.url
                except requests.RequestException:
                    pass

            # Step 4: Extract all profile and status fields
            data = extract_admission_data(page_html, final_url)

            # Update result dictionary
            for key in (
                "login_result", "surname", "other_names", "degree_type",
                "program_type", "faculty", "department", "course",
                "admission_mode", "utme_score", "admission_status",
                "acceptance_status", "email", "phone", "user_id",
                "photo_url", "error_message"
            ):
                result[key] = data[key]

            # Log clean output
            if data["login_result"] == "LOGIN_FAILED":
                log.warning(f"  [X] {reg_number} -- Login failed: {data['error_message']}")
            elif data["login_result"] == "SUCCESS":
                name = f"{data['surname']} {data['other_names']}".strip()
                log.info(
                    f"  [OK] {reg_number} -- {name} | "
                    f"Status: {data['admission_status']} | "
                    f"Acceptance: {data['acceptance_status']} | "
                    f"Score: {data['utme_score']} | "
                    f"{data['faculty']} -> {data['course']}"
                )
            else:
                log.warning(f"  [?] {reg_number} -- {data['error_message']}")

            break  # Success / finished this reg number

        except Exception as e:
            result["error_message"] = str(e)
            log.error(f"  Attempt {attempt}/{MAX_RETRIES} error: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF)
        finally:
            session.close()

    return result


def write_results(results: list[dict]):
    """Write results list to CSV file."""
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)


def main():
    """Main execution loop."""
    print("=" * 75)
    print("  UNIPORT Unified Portal System -- Acceptance Status & Profile Extractor")
    print("  Admission Portal: /auth/starthere -> /admission/acceptance")
    print("=" * 75)
    print()

    if not INPUT_FILE.exists():
        log.error(f"Input file not found: {INPUT_FILE}")
        sys.exit(1)

    reg_numbers = load_reg_numbers(INPUT_FILE)
    if not reg_numbers:
        log.error("No registration numbers found in input file")
        sys.exit(1)

    total = len(reg_numbers)
    results = []
    start_time = time.time()

    for i, reg in enumerate(reg_numbers, 1):
        res = check_single_reg(reg, i, total)
        results.append(res)

        # Write intermediate CSV results continuously
        write_results(results)

        # Progress reporting
        elapsed = time.time() - start_time
        avg_time = elapsed / i
        eta_min = (avg_time * (total - i)) / 60
        log.info(
            f"  Progress: {i}/{total} ({i * 100 / total:.1f}%) -- ETA: {eta_min:.1f} min"
        )

        if i < total:
            time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

    # Summary
    print()
    print("=" * 75)
    print("  RUN COMPLETED -- RESULTS SUMMARY")
    print("=" * 75)

    login_ok = sum(1 for r in results if r["login_result"] == "SUCCESS")
    login_fail = sum(1 for r in results if r["login_result"] == "LOGIN_FAILED")
    login_err = sum(1 for r in results if r["login_result"] not in ("SUCCESS", "LOGIN_FAILED"))

    print(f"  Total Processed:    {len(results)}/{total}")
    print(f"  Successful Logins:  {login_ok}")
    print(f"  Failed Logins:      {login_fail}")
    print(f"  Network/Errors:     {login_err}")

    if login_ok > 0:
        print("\n  Acceptance Status Counts:")
        counts: dict[str, int] = {}
        for r in results:
            if r["login_result"] == "SUCCESS":
                s = r["acceptance_status"] or "UNKNOWN"
                counts[s] = counts.get(s, 0) + 1
        for st, c in sorted(counts.items()):
            print(f"    {st:30s} : {c}")

    print(f"\n  CSV File: {OUTPUT_FILE}")
    print(f"  Log File: {LOG_FILE}")
    print("=" * 75)


if __name__ == "__main__":
    main()
