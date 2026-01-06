Deploying on Render (Step-by-Step)

🔹 Step 1: Create PostgreSQL Database on Render
Log in to Render

Go to Dashboard → New → PostgreSQL

Choose:

Database Name (e.g. fastapi-db)

Region (same as backend)

Click Create Database

📌 After creation, Render will provide:

Internal Database URL

External Database URL

👉 Use the Internal Database URL


🔹 Step 2: Create Web Service (FastAPI)

Go to Dashboard → New → Web Service

Connect your GitHub repository

Configure:

Setting	Value
Runtime	Python
Build Command	pip install -r requirements.txt
Start Command	uvicorn app.main:app --host 0.0.0.0 --port 10000

🔹 Step 3: Set Environment Variables on Render

Inside your Web Service → Environment:

Add the following:

✅ OPENAI_API_KEY
sk-xxxxxxxxxxxxxxxxxxxx

✅ DATABASE_URL

Paste the Internal Database URL from the PostgreSQL service:
ex: postgresql://intelligent_news_db_user:hgPEfNMSQZNQQVzz4j98k3953mW9TGZz@dpg-d550763uibrs738pkpsg-a/intelligent_news_db

🔹 Step 4: Deploy

Click Deploy

Wait for build to finish

Render will provide a live URL:

https://your-service-name.onrender.com

Here is my github username: honeydev783