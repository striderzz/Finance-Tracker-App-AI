import json
import os
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_sqlalchemy import SQLAlchemy
from openai import OpenAI
from sqlalchemy import func
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "instance", "app.db")
DEFAULT_CATEGORIES = [
    "Food",
    "Transport",
    "Shopping",
    "Bills",
    "Entertainment",
    "Health",
    "Education",
    "Travel",
    "Rent",
    "Groceries",
    "Other",
]


db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message_category = "warning"


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    monthly_budget = db.Column(db.Numeric(10, 2), default=Decimal("0.00"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    expenses = db.relationship("Expense", backref="user", lazy=True, cascade="all, delete-orphan")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    expense_date = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
    login_manager.init_app(app)

    with app.app_context():
        os.makedirs(os.path.join(BASE_DIR, "instance"), exist_ok=True)
        db.create_all()

    register_routes(app)
    return app


def register_routes(app: Flask):
    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))
        return render_template("index.html")

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            monthly_budget = request.form.get("monthly_budget", "0")

            if not name or not email or not password:
                flash("Please fill in all required fields.", "danger")
                return render_template("register.html")

            if User.query.filter_by(email=email).first():
                flash("An account with that email already exists.", "danger")
                return render_template("register.html")

            user = User(
                name=name,
                email=email,
                monthly_budget=parse_decimal(monthly_budget, default=Decimal("0.00")),
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash("Registration successful. Please log in.", "success")
            return redirect(url_for("login"))

        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            user = User.query.filter_by(email=email).first()

            if user and user.check_password(password):
                login_user(user)
                flash(f"Welcome back, {user.name}!", "success")
                return redirect(url_for("dashboard"))

            flash("Invalid email or password.", "danger")

        return render_template("login.html")

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        flash("You have been logged out.", "info")
        return redirect(url_for("login"))

    @app.route("/dashboard")
    @login_required
    def dashboard():
        today = datetime.utcnow().date()
        month_start = today.replace(day=1)
        month_expenses = (
            Expense.query.filter(
                Expense.user_id == current_user.id,
                Expense.expense_date >= month_start,
                Expense.expense_date <= today,
            )
            .order_by(Expense.expense_date.desc(), Expense.created_at.desc())
            .all()
        )

        all_expenses = (
            Expense.query.filter_by(user_id=current_user.id)
            .order_by(Expense.expense_date.desc(), Expense.created_at.desc())
            .limit(20)
            .all()
        )

        total_spent = sum((expense.amount for expense in month_expenses), Decimal("0.00"))
        budget = Decimal(current_user.monthly_budget or 0)
        remaining_budget = budget - total_spent

        category_rows = (
            db.session.query(Expense.category, func.sum(Expense.amount))
            .filter(
                Expense.user_id == current_user.id,
                Expense.expense_date >= month_start,
                Expense.expense_date <= today,
            )
            .group_by(Expense.category)
            .order_by(func.sum(Expense.amount).desc())
            .all()
        )
        category_labels = [row[0] for row in category_rows]
        category_values = [float(row[1]) for row in category_rows]

        last_7_days = []
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            daily_total = (
                db.session.query(func.sum(Expense.amount))
                .filter(Expense.user_id == current_user.id, Expense.expense_date == day)
                .scalar()
                or Decimal("0.00")
            )
            last_7_days.append({"label": day.strftime("%b %d"), "amount": float(daily_total)})

        budget_chart = build_budget_chart(total_spent=total_spent, budget=budget)

        return render_template(
            "dashboard.html",
            month_expenses=month_expenses,
            all_expenses=all_expenses,
            total_spent=float(total_spent),
            budget=float(budget),
            remaining_budget=float(remaining_budget),
            category_labels=json.dumps(category_labels),
            category_values=json.dumps(category_values),
            trend_labels=json.dumps([item["label"] for item in last_7_days]),
            trend_values=json.dumps([item["amount"] for item in last_7_days]),
            budget_chart_labels=json.dumps(budget_chart["labels"]),
            budget_chart_values=json.dumps(budget_chart["values"]),
            today=today,
        )

    @app.route("/expenses/add", methods=["GET", "POST"])
    @login_required
    def add_expense():
        if request.method == "POST":
            amount_raw = request.form.get("amount", "")
            description = request.form.get("description", "").strip()
            category = request.form.get("category", "").strip()
            expense_date_raw = request.form.get("expense_date", "")

            if not amount_raw or not description or not expense_date_raw:
                flash("Amount, description, and date are required.", "danger")
                return render_template(
                    "add_expense.html",
                    today=datetime.utcnow().date(),
                    categories=DEFAULT_CATEGORIES,
                )

            amount = parse_decimal(amount_raw)
            if amount is None or amount <= 0:
                flash("Please enter a valid amount greater than 0.", "danger")
                return render_template(
                    "add_expense.html",
                    today=datetime.utcnow().date(),
                    categories=DEFAULT_CATEGORIES,
                )

            expense_date = parse_date(expense_date_raw)
            if not expense_date:
                flash("Please enter a valid expense date.", "danger")
                return render_template(
                    "add_expense.html",
                    today=datetime.utcnow().date(),
                    categories=DEFAULT_CATEGORIES,
                )

            if not category:
                category = suggest_category_with_ai(description) or "Other"

            expense = Expense(
                amount=amount,
                category=category,
                description=description,
                expense_date=expense_date,
                user_id=current_user.id,
            )
            db.session.add(expense)
            db.session.commit()
            flash("Expense added successfully.", "success")
            return redirect(url_for("dashboard"))

        return render_template("add_expense.html", today=datetime.utcnow().date(), categories=DEFAULT_CATEGORIES)

    @app.route("/expenses/<int:expense_id>/edit", methods=["GET", "POST"])
    @login_required
    def edit_expense(expense_id: int):
        expense = Expense.query.filter_by(id=expense_id, user_id=current_user.id).first_or_404()

        if request.method == "POST":
            amount_raw = request.form.get("amount", "")
            description = request.form.get("description", "").strip()
            category = request.form.get("category", "").strip() or "Other"
            expense_date_raw = request.form.get("expense_date", "")

            amount = parse_decimal(amount_raw)
            expense_date = parse_date(expense_date_raw)

            if amount is None or amount <= 0 or not description or not expense_date:
                flash("Please provide valid data for all fields.", "danger")
                return render_template("edit_expense.html", expense=expense, categories=DEFAULT_CATEGORIES)

            expense.amount = amount
            expense.description = description
            expense.category = category
            expense.expense_date = expense_date
            db.session.commit()
            flash("Expense updated successfully.", "success")
            return redirect(url_for("dashboard"))

        return render_template("edit_expense.html", expense=expense, categories=DEFAULT_CATEGORIES)

    @app.route("/expenses/<int:expense_id>/delete", methods=["POST"])
    @login_required
    def delete_expense(expense_id: int):
        expense = Expense.query.filter_by(id=expense_id, user_id=current_user.id).first_or_404()
        db.session.delete(expense)
        db.session.commit()
        flash("Expense deleted.", "info")
        return redirect(url_for("dashboard"))

    @app.route("/budget", methods=["POST"])
    @login_required
    def update_budget():
        raw_budget = request.form.get("monthly_budget", request.form.get("budget", "0"))
        monthly_budget = parse_decimal(raw_budget, default=None)
        if monthly_budget is None or monthly_budget < 0:
            flash("Please enter a valid monthly budget.", "danger")
            return redirect(url_for("dashboard"))

        user = db.session.get(User, current_user.id)
        if user is None:
            flash("Unable to update budget for this account.", "danger")
            return redirect(url_for("dashboard"))

        user.monthly_budget = monthly_budget.quantize(Decimal("0.01"))
        db.session.commit()
        flash(f"Monthly budget updated to ${float(user.monthly_budget):.2f}.", "success")
        return redirect(url_for("dashboard"))

    @app.route("/database")
    @login_required
    def database_view():
        expenses = (
            Expense.query.filter_by(user_id=current_user.id)
            .order_by(Expense.expense_date.desc(), Expense.created_at.desc())
            .all()
        )
        total_records = len(expenses)
        total_amount = sum((expense.amount for expense in expenses), Decimal("0.00"))
        return render_template(
            "database.html",
            expenses=expenses,
            total_records=total_records,
            total_amount=float(total_amount),
        )

    @app.route("/insights")
    @login_required
    def insights():
        expenses = (
            Expense.query.filter_by(user_id=current_user.id)
            .order_by(Expense.expense_date.desc(), Expense.created_at.desc())
            .limit(50)
            .all()
        )

        ai_response = None
        error_message = None
        budget = Decimal(current_user.monthly_budget or 0)
        total_spent = sum((expense.amount for expense in expenses), Decimal("0.00"))
        budget_chart = build_budget_chart(total_spent=total_spent, budget=budget)
        category_rows = {}
        for expense in expenses:
            category_rows[expense.category] = category_rows.get(expense.category, 0.0) + float(expense.amount)
        sorted_categories = sorted(category_rows.items(), key=lambda item: item[1], reverse=True)

        if not expenses:
            error_message = "Add a few expenses first to generate AI insights."
        else:
            ai_response = generate_ai_insights(expenses, budget)
            if ai_response is None:
                error_message = "OpenAI insights are unavailable right now. Add your API key in .env and try again."

        return render_template(
            "insights.html",
            expenses=expenses,
            ai_response=ai_response,
            error_message=error_message,
            total_spent=float(total_spent),
            budget=float(budget),
            chart_category_labels=json.dumps([item[0] for item in sorted_categories]),
            chart_category_values=json.dumps([round(item[1], 2) for item in sorted_categories]),
            budget_chart_labels=json.dumps(budget_chart["labels"]),
            budget_chart_values=json.dumps(budget_chart["values"]),
        )


def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


def suggest_category_with_ai(description: str):
    client = get_openai_client()
    if client is None:
        return None

    try:
        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            input=(
                "Classify the following expense description into exactly one short category from this list: "
                "Food, Transport, Shopping, Bills, Entertainment, Health, Education, Travel, Rent, Groceries, Other. "
                f"Description: {description}. Respond with only the category name."
            ),
            max_output_tokens=12,
        )
        category = response.output_text.strip()
        return category if category else None
    except Exception:
        return None


def generate_ai_insights(expenses, monthly_budget: Decimal):
    client = get_openai_client()
    if client is None:
        return None

    payload = [
        {
            "date": expense.expense_date.isoformat(),
            "amount": float(expense.amount),
            "category": expense.category,
            "description": expense.description,
        }
        for expense in expenses
    ]

    prompt = f"""
You are a financial insights assistant for a personal expense tracker.
Analyze the following recent expenses and produce:
1. A short summary of current spending behavior.
2. Top 3 spending categories.
3. 3 practical recommendations to save money.
4. A warning if spending appears to exceed a monthly budget of {float(monthly_budget):.2f}.
5. A one-line action plan for the next 7 days.

Return your answer in clean markdown with headings and bullet points.
Expense data:
{json.dumps(payload, indent=2)}
"""
    try:
        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            input=prompt,
            max_output_tokens=500,
        )
        return response.output_text.strip()
    except Exception:
        return None


def parse_decimal(value: str, default=None):
    if value is None:
        return default
    cleaned = str(value).replace(",", "").replace("$", "").strip()
    if cleaned == "":
        return default
    try:
        return Decimal(cleaned)
    except (InvalidOperation, TypeError, ValueError):
        return default


def parse_date(value: str):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def build_budget_chart(total_spent: Decimal, budget: Decimal):
    spent = float(total_spent)
    budget_value = float(budget)
    if budget_value <= 0:
        return {
            "labels": ["Spent"],
            "values": [round(spent, 2)],
        }
    if spent <= budget_value:
        return {
            "labels": ["Spent", "Remaining"],
            "values": [round(spent, 2), round(budget_value - spent, 2)],
        }
    return {
        "labels": ["Budget", "Overspend"],
        "values": [round(budget_value, 2), round(spent - budget_value, 2)],
    }


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
