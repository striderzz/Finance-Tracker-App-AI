# AI Expense Tracker

A full end-to-end **Flask + Bootstrap + OpenAI + SQLite** project you can run in **VSCode**.

## Features
- User registration and login
- Add, edit, and delete expenses
- Monthly budget tracking
- Dashboard with charts
- Automatic AI category suggestion when category is left blank
- AI-generated spending insights and recommendations
- SQLite database for easy local setup

## Tech Stack
- Flask
- Flask-Login
- Flask-SQLAlchemy
- Bootstrap 5
- Chart.js
- OpenAI API
- SQLite

## Project Structure
```bash
ai_expense_tracker/
│── app.py
│── requirements.txt
│── .env.example
│── README.md
│── instance/
│── static/
│   └── css/
│       └── styles.css
└── templates/
    ├── base.html
    ├── index.html
    ├── login.html
    ├── register.html
    ├── dashboard.html
    ├── add_expense.html
    ├── edit_expense.html
    └── insights.html
```

## How to Run in VSCode

### 1. Open the project folder in VSCode

### 2. Create virtual environment
```bash
python -m venv venv
```

### 3. Activate virtual environment
**Windows PowerShell**
```bash
venv\Scripts\Activate.ps1
```

**Windows CMD**
```bash
venv\Scripts\activate
```

**Mac/Linux**
```bash
source venv/bin/activate
```

### 4. Install dependencies
```bash
pip install -r requirements.txt
```

### 5. Create `.env`
Copy `.env.example` to `.env` and add your key:
```env
SECRET_KEY=super-secret
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4.1-mini
```

### 6. Run the app
```bash
python app.py
```

Then open:
```bash
http://127.0.0.1:5000
```

## Notes
- The app works without an OpenAI key for normal expense tracking.
- AI category suggestion and AI insights need `OPENAI_API_KEY`.
- Database file is automatically created in `instance/app.db`.

## Good Resume Description
Built a full-stack **AI Expense Tracker** with Flask, Bootstrap, SQLite, and OpenAI API, supporting authentication, expense CRUD workflows, chart-based analytics, monthly budget tracking, and AI-generated financial insights.
