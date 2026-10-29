# Deployment Guide: Render & Vercel

This guide provides step-by-step instructions to deploy the **Physical Chatbot Trigger** project on **Render** and **Vercel**.

---

## Overview of Deployment Options

| Option | Frontend | Backend | Best For |
|---|---|---|---|
| **Option 1: All-in-One on Render** | Render | Render (`backend/local_server.py`) | **Easiest setup**. 1 service, 0 CORS issues, includes `/alerts` history. |
| **Option 2: All-in-One on Vercel** | Vercel CDN | Vercel Serverless (`api/alert.py`) | **Fastest load times**, global edge CDN, zero server maintenance. |
| **Option 3: Split Architecture** | Vercel CDN | Render Web Service | Traditional Jamstack (Vercel static frontend + Render Python API). |

---

## Option 1: Deploy on Render (All-in-One Fullstack)

Render hosts your Python server, which serves both the frontend web app and handles Discord alerts.

### Step 1: Push Project to GitHub
1. Create a repository on [GitHub](https://github.com/new).
2. Push your project code:
   ```bash
   git init
   git add .
   git commit -m "Prepare for Render and Vercel deployment"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
   git push -u origin main
   ```

### Step 2: Create a Web Service on Render
1. Go to [render.com](https://render.com) and sign in.
2. Click **New +** → **Web Service**.
3. Choose **Build and deploy from a Git repository** and connect your GitHub repo.

### Step 3: Configure Service Settings
Fill in the following fields:

* **Name:** `physical-chatbot-trigger` (or any name you choose)
* **Region:** Closest to you (e.g., Oregon, Frankfurt, Singapore)
* **Branch:** `main`
* **Root Directory:** *(leave blank)*
* **Runtime:** `Python 3`
* **Build Command:**
  ```bash
  pip install -r requirements.txt
  ```
* **Start Command:**
  ```bash
  python backend/local_server.py
  ```
* **Instance Type:** `Free`

### Step 4: Add Environment Variables
Under the **Environment Variables** section, click **Add Environment Variable**:

* **Key:** `DISCORD_WEBHOOK_URL`
* **Value:** `https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN`

*(Optional: `PORT` is automatically managed by Render, and `local_server.py` will read it automatically).*

### Step 5: Deploy
1. Click **Create Web Service**.
2. Render will build and deploy your app. Once deployed, Render will provide a public URL like:
   `https://physical-chatbot-trigger.onrender.com`
3. Click the URL: your dashboard is live and can trigger real alerts!

---

## Option 2: Deploy on Vercel (All-in-One Serverless)

Vercel serves the static frontend via global edge CDN and routes `/alert` directly to the serverless Python function in `api/alert.py`.

### Step 1: Push Project to GitHub
Ensure your repository is pushed to GitHub (same as Option 1).

### Step 2: Import into Vercel
1. Go to [vercel.com](https://vercel.com) and log in.
2. Click **Add New…** → **Project**.
3. Import your GitHub repository.

### Step 3: Project Configuration
* **Project Name:** `physical-chatbot-trigger`
* **Framework Preset:** `Other`
* **Root Directory:** `./` *(Leave as root — `vercel.json` automatically handles routing)*
* **Build Command:** *(Leave default / blank)*
* **Output Directory:** *(Leave default / blank)*

### Step 4: Add Environment Variables
In the **Environment Variables** section on Vercel:

* **Name:** `DISCORD_WEBHOOK_URL`
* **Value:** `https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN`
* Click **Add**.

### Step 5: Deploy
1. Click **Deploy**.
2. In about 30–60 seconds, your site will be live at `https://your-project.vercel.app`!
3. Open the link and click **Send Alert** to test Discord notifications.

---

## Option 3: Split Deployment (Frontend on Vercel + Backend on Render)

If you prefer keeping static assets on Vercel and running the dedicated Python server on Render:

1. **Deploy Backend to Render** following **Option 1**, but take note of your Render backend URL (e.g. `https://my-backend.onrender.com`).
2. **Update Frontend Configuration:**
   Open `frontend/script.js` and set:
   ```javascript
   const BACKEND_API_URL = 'https://my-backend.onrender.com';
   ```
   Commit and push the change to GitHub.
3. **Deploy Frontend to Vercel:**
   - In Vercel, set **Root Directory** to `frontend`.
   - Click **Deploy**.
   - Your Vercel frontend will now communicate directly with your Render backend.

---

## Verification & Testing

Once deployed to either platform:
1. Open your live deployment URL in your browser.
2. Verify the top right status badge shows **API Online**.
3. Click one of the presets (e.g. **Emergency Alert** 🚨) or write a custom message.
4. Click **Send Alert**.
5. Check your Discord channel — the rich embed notification will appear within seconds!

