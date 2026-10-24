# UNIPORT Unified Portal System — Admission & Acceptance Verification Dashboard

Executive-grade, automated web platform for University of Port Harcourt (UNIPORT) admission acceptance verification, clearance tracking, and student dossier retrieval.

---

## Key Features

1. **Real-time Batch Checking Engine**:
   - Polite scraping with CSRF token retrieval and session reuse.
   - Batch controls: **Start**, **Pause**, **Resume**, **Stop**, and **Reset**.
   - Automated pause & resume without losing progress.

2. **Instant Student Lookup**:
   - Live query for any JAMB registration number on demand.
   - Immediate retrieval of passport photo, UTME score, faculty, department, course, admission status, acceptance status, and portal user ID.

3. **Interactive Clearance Table**:
   - Instant search across name, registration number, course, faculty, or department.
   - Multi-status filtering (Admitted, Accepted, Not Accepted, Login Failed).
   - Faculty dropdown filter.
   - Click any record to inspect the student's full photo clearance dossier in an executive modal.

4. **Live Activity Console**:
   - Real-time scrolling event feed with color-coded severity logs.
   - Auto-scroll lock and clear logs control.

5. **Data Export Center**:
   - 1-click Download as CSV (`acceptance_results.csv`).
   - 1-click Download as JSON format.

6. **Queue Management**:
   - Upload `.txt` or `.csv` files with registration numbers.
   - Paste registration numbers directly in the modal.
   - Option to append or replace queue.

---

## Running Locally

To start the dashboard locally:

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the application
python app.py
```

Then open your browser at **http://localhost:8000**.

---

## Deploying to Render (Free Cloud Hosting)

This repository includes `render.yaml` and `Procfile` configured for deployment on [Render](https://render.com).

### Method A: Blueprint Deployment (Recommended & Fastest)

1. Push this project to your GitHub / GitLab account.
2. Go to your [Render Dashboard](https://dashboard.render.com/).
3. Click **New +** and select **Blueprint**.
4. Connect your repository.
5. Render will automatically detect `render.yaml`, set up the Python web service, install `requirements.txt`, and start `uvicorn app:app --host 0.0.0.0 --port $PORT`.
6. Click **Apply**. Within 2 minutes, your dashboard will be live with a free `https://<your-app>.onrender.com` URL!

### Method B: Manual Web Service Deployment

1. On the Render Dashboard, click **New +** > **Web Service**.
2. Connect your Git repository.
3. Configure the settings:
   - **Name**: `uniport-ups-dashboard` (or any name you prefer)
   - **Environment**: `Python`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app:app --host 0.0.0.0 --port $PORT`
   - **Health Check Path**: `/healthz`
4. Click **Create Web Service**.

---

## File Structure

```
Unified Portal System/
├── app.py                 # FastAPI backend & portal scraper engine
├── check_acceptance.py     # Standalone CLI script
├── reg_number_files       # Input registration numbers
├── acceptance_results.csv # Saved results CSV
├── requirements.txt       # Python dependencies for Render
├── Procfile               # Web process definition for Render
├── render.yaml            # Render Blueprint configuration
├── templates/
│   └── index.html         # Modern executive UI dashboard
└── static/
    ├── css/
    │   └── style.css      # CSS design system (dark obsidian theme)
    └── js/
        └── dashboard.js   # Client application & live polling
```
