# Restaurant Money Engine 🍽️💰

A professional multi-restaurant SaaS platform designed to monitor food costs, optimize menu margins, and model financial performance.

## 🛠️ Technology Stack

| Layer | Technology | Hosting |
|---|---|---|
| **Frontend** | HTML5, CSS3, Vanilla JavaScript | Vercel |
| **Backend** | Python Flask, Flask-CORS | Render |
| **Database** | PostgreSQL | Supabase |
| **Authentication** | Supabase Auth | Supabase |
| **Storage** | Supabase Storage | Supabase |

---

## 📂 Project Structure

```
Restaurant-Money-Engine/
│
├── frontend/               # Client-side web application (deployed to Vercel)
│   ├── index.html          # Executive Dashboard UI Shell
│   ├── css/
│   │   └── style.css       # Executive Dark Theme design system
│   ├── js/                 # Modular Vanilla ES Modules
│   │   ├── api.js          # API client, Supabase JWT auth & Toast manager
│   │   ├── dashboard.js    # Prime Cost KPIs, visual health gauge & daily entry
│   │   ├── matrix.js       # Kasavana-Smith 2x2 Matrix visualization
│   │   ├── menu.js         # Menu catalog CRUD & Recipe portion costing
│   │   ├── simulation.js   # What-if profit sliders & forecast delta engine
│   │   └── app.js          # Main coordinator & tab manager
│   └── assets/
│       └── logo.svg        # Brand icon
│
├── backend/                # Server-side API service (deployed to Render)
│   ├── app.py              # Flask app factory, CORS & root routes
│   ├── config.py           # Environment-based configuration loader
│   ├── requirements.txt    # Python dependencies (supabase, psycopg2-binary, Flask)
│   ├── routes/             # API blueprints
│   │   ├── __init__.py
│   │   ├── health.py       # Health check route (/health)
│   │   ├── engine.py       # Core Engine API (/api/v1/daily-financials, /api/v1/menu-matrix)
│   │   ├── menu.py         # Phase 3 Menu & Recipe Costing (/api/v1/menu)
│   │   └── simulation.py   # Phase 3 What-If Simulation (/api/v1/simulation)
│   ├── services/           # Business logic & integrations
│   │   ├── __init__.py
│   │   ├── supabase_client.py # Singleton Supabase client
│   │   └── money_engine.py # Prime cost, Kasavana-Smith, recipe auto-costing & simulation
│   └── middleware/         # Auth, tenancy, & request handling
│       ├── __init__.py
│       └── auth.py         # Multi-tenant @require_auth decorator
│
├── database/               # Database migrations & schemas
│   └── migrations/
│       └── 003_recipes.sql # Recipes & RLS tenant isolation schema
│
├── .env.example            # Environment variables template
├── .gitignore              # Git ignore rules for Python, secrets, and IDEs
└── README.md               # Documentation & setup instructions
```

---

## 🚀 Local Development Setup

### 1. Clone & Configure Environment

```bash
# Copy example environment file
cp .env.example .env
```

Edit `.env` to configure your local ports and Supabase credentials when ready.

---

### 2. Backend Setup (Flask)

```bash
# Create and activate virtual environment
python -m venv .venv

# Windows (PowerShell):
.venv\Scripts\activate

# macOS / Linux:
source .venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt

# Start the Flask API
python -m backend.app
```

The API will start at: `http://127.0.0.1:5000`

#### Verify Health Endpoint:
```bash
curl http://127.0.0.1:5000/health
```

Expected JSON response:
```json
{
  "environment": "development",
  "service": "Restaurant Money Engine API",
  "status": "healthy",
  "version": "1.0.0"
}
```

---

## 🔑 REST API Endpoints (Multi-Tenant & Authenticated)

All `/api/v1/*` endpoints require a Supabase JWT Bearer token:
`Authorization: Bearer <SUPABASE_JWT_TOKEN>`

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Public service health status check |
| `POST` | `/api/v1/daily-financials` | Records gross sales, COGS, and labor costs; returns Prime Cost metrics & health status |
| `GET` | `/api/v1/menu-matrix` | Queries tenant's menu items & sales logs; returns 4-quadrant Kasavana-Smith Matrix |
| `GET` | `/api/v1/menu/` | List tenant's menu items with selling price, cost price, and margins |
| `POST` | `/api/v1/menu/` | Create a new menu item |
| `PUT` | `/api/v1/menu/<item_id>` | Update pricing, category, name, or active status |
| `DELETE` | `/api/v1/menu/<item_id>` | Soft-delete / archive menu item (`is_active = false`) |
| `GET` | `/api/v1/menu/<item_id>/recipe` | Retrieve ingredient breakdown and calculated recipe portion cost |
| `POST` | `/api/v1/menu/<item_id>/recipe` | Upsert recipe ingredients and auto-recalculate menu item `cost_price` |
| `POST` | `/api/v1/simulation/run` | Run what-if simulation (ingredient inflation, price changes, labor shifts) |

---

---

## ☁️ Cloud Production Deployment Guide

### 1. Render Deployment (Backend API)
The backend is pre-configured with Infrastructure-as-Code (`render.yaml`) and `Procfile` for one-click deployment:

1. Link your GitHub repository to [Render](https://render.com).
2. Create a new **Web Service** or select **Blueprint** using `render.yaml`.
3. Set the following Environment Variables in the Render dashboard:
   - `FLASK_ENV`: `production`
   - `SECRET_KEY`: `<generate-secure-random-key>`
   - `SUPABASE_URL`: `https://your-project.supabase.co`
   - `SUPABASE_ANON_KEY`: `<your-supabase-anon-key>`
   - `SUPABASE_SERVICE_ROLE_KEY`: `<your-supabase-service-role-key>`
   - `CORS_ORIGINS`: `https://your-app.vercel.app`
4. Render will automatically build via `pip install -r backend/requirements.txt` and start the Gunicorn cluster:
   ```bash
   gunicorn "backend.app:create_app()" --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120
   ```
5. Health checks automatically ping `/health`.

---

### 2. Vercel Deployment (Frontend Web App)
The client application is pre-configured for Vercel edge deployment via `vercel.json`:

1. Import your GitHub repository to [Vercel](https://vercel.com).
2. Framework Preset: **Other**.
3. Root Directory: `./` (or `frontend`).
4. (Optional) Set Environment Variable in Vercel:
   - `API_BASE_URL`: `https://your-backend.onrender.com`
5. Click **Deploy**. Vercel will apply static asset caching rules and route clean client URLs to `frontend/index.html`.

---

### 3. Supabase Database & Demo Data
1. Execute the database extensions migration in the Supabase SQL Editor:
   - Run `database/migrations/003_recipes.sql`.
2. Seed initial demo data for testing:
   ```bash
   python database/seed_demo_data.py
   ```
3. To purge demo data at any time:
   ```bash
   python database/seed_demo_data.py --clean
   ```

---

## 🔒 Production Security Hardening

The application enforces strict enterprise security headers on all responses:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- `Referrer-Policy: strict-origin-when-cross-origin`
- Flask `DEBUG` mode is strictly disabled when `FLASK_ENV=production`.
- CORS is restricted to authorized Vercel production domains and local ports.

---

### 3. Frontend Setup

The frontend is pure HTML5, CSS3, and Vanilla JavaScript.

To run locally:
- Serve the `frontend/` directory with any static server (e.g. VS Code Live Server, `npx serve frontend`, or Python's `python -m http.server 3000 --directory frontend`).
- Open `http://localhost:3000` (or `frontend/index.html`) in your browser to verify it connects to `http://127.0.0.1:5000/health`.
