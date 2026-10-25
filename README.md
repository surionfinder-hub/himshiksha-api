# HimShiksha Python Conversion API (Render Deployment Guide)

This is the standalone Python conversion microservice for **HimShiksha**. It runs on [Render](https://render.com) (Free Tier) to power heavy document processing, high-fidelity PDF creation, Devanagari/Hindi Unicode rendering, scanned-PDF detection, and up to 100-file batch merges with zero permanent file storage.

---

## 1. Architecture & Security Overview

- **Stateless & Ephemeral**: Converted files are processed in memory and streamed directly back to the client. Temporary buffers are freed immediately. Render's filesystem is **never** used as persistent storage.
- **Authentication**: All conversion endpoints require the `X-HimShiksha-Key` HTTP header, matched against `HIMSHIKSHA_API_KEY`.
- **Safeguards**:
  - Max single file size: 10 MB
  - Max batch total: 100 MB
  - Max files per batch: 100
- **Cold-Start Awareness**: Free-tier web services on Render sleep after 15 minutes of inactivity. Cold boots take ~30–50 seconds. The `/health` endpoint is used by the frontend to detect cold starts and display a waking message to users.

---

## 2. Step-by-Step Render Deployment Guide

### Option A: Using Render Blueprint (Recommended 1-Click)
1. Fork or push this repository to your GitHub account (`https://github.com/<your-username>/converter-website`).
2. Log in to [Render Dashboard](https://dashboard.render.com).
3. Click **New +** -> **Blueprint**.
4. Select your GitHub repository. Render will automatically detect `render-api/render.yaml`.
5. Under Environment Variables, set:
   - `HIMSHIKSHA_API_KEY`: Set your private shared secret key (e.g. `himshiksha_render_secret_key_2026`).
6. Click **Apply**. Render will automatically build the dependencies and start the service.

### Option B: Manual Web Service Setup
1. On Render, click **New +** -> **Web Service**.
2. Connect your GitHub repository.
3. Configure the service settings:
   - **Name**: `himshiksha-api`
   - **Region**: Choose closest to your users (e.g. `Oregon (US West)` or `Frankfurt (EU)`)
   - **Branch**: `main`
   - **Root Directory**: `render-api`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1`
   - **Plan**: `Free` ($0/month)
4. Add Environment Variables:
   - `PYTHON_VERSION`: `3.10.12`
   - `HIMSHIKSHA_API_KEY`: `<your_secure_secret_key>`
5. Click **Create Web Service**.
6. Once deployed, Render will provide your public URL (e.g. `https://himshiksha-api.onrender.com`).

---

## 3. Connecting Render API to the HimShiksha Website

In your HimShiksha PHP website `config/config.php` (or via environment variables):

```php
'render' => [
    'enabled' => true,
    'api_url' => 'https://himshiksha-api.onrender.com', // Your live Render URL
    'api_key' => 'himshiksha_render_secret_key_2026',    // Must match HIMSHIKSHA_API_KEY
    'timeout' => 90,                                    // Accounts for Render cold start (30-60s)
],
```

---

## 4. API Endpoints Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Health check, uptime telemetry, and cold start verification. |
| `POST` | `/api/convert/txt-to-pdf` | Multi-page PDF generation with Hindi/Devanagari font embedding and page breaks. |
| `POST` | `/api/convert/pdf-to-txt` | Selectable text extraction and scanned document detection. |
| `POST` | `/api/convert/pdf-merge` | Combine up to 100 PDF documents into a single PDF. |
| `POST` | `/api/convert/images-to-pdf` | Combine up to 100 JPG/PNG images into a single PDF. |
| `POST` | `/api/convert/pdf-to-images` | Render PDF pages as JPG/PNG packaged into a ZIP archive. |
| `POST` | `/api/convert/image-format` | Convert between JPG, PNG, and WebP with quality and transparency controls. |
| `POST` | `/api/convert/batch-images` | Batch convert up to 100 images into a downloadable ZIP archive. |
