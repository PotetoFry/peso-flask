from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from functools import wraps
import os

# ============================================================
# APP SETUP
# ============================================================

app = Flask(__name__)

@app.context_processor
def inject_currency():
    return dict(CURRENCY_SYMBOL='₱')

app.config['SECRET_KEY'] = '3a1b9e0f2c4d6a7b8e9f0a1b2c3d4e5f6a7b8e9f0a1b2c3d4e5f6a7b8e9f0a1b'
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///finance.db')

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


# ============================================================
# MODELS
# ============================================================

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='user')

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)


class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    type = db.Column(db.String(10), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200))
    date = db.Column(db.DateTime, default=datetime.utcnow)


class Budget(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    limit_amount = db.Column(db.Float, nullable=False)
    period = db.Column(db.String(20), default='monthly')

    def get_remaining_budget(self):
        user_transactions = Transaction.query.filter_by(user_id=self.user_id, category=self.category).all()
        total_expense = sum(tx.amount for tx in user_transactions if tx.type == 'expense')
        return self.limit_amount - total_expense

    def is_exceeded(self):
        return self.get_remaining_budget() < 0

class Goal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    target_amount = db.Column(db.Float, nullable=False)
    current_amount = db.Column(db.Float, default=0.0)

    def get_progress(self):
        if self.target_amount <= 0:
            return 0
        # Multiplying by 100.0 forces floating-point math
        progress = (self.current_amount / self.target_amount) * 100.0
        # Cap at 100% so the bar doesn't grow off the screen
        return min(progress, 100.0)

    def add_contribution(self, amount):
        self.current_amount += amount
        db.session.commit()


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)


class SystemLog(db.Model):
    """Model to track admin activity for the system logs."""
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(255), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


# ============================================================
# SECURITY & HELPERS
# ============================================================

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Access denied. Admins only.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)

    return decorated_function


def log_activity(description):
    """Helper function to insert a log entry."""
    new_log = SystemLog(description=description)
    db.session.add(new_log)
    db.session.commit()


# ============================================================
# AUTH ROUTES
# ============================================================

@app.route('/')
def home():
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('admin_panel'))
        return redirect(url_for('dashboard'))
    return redirect(url_for('register'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        typed_name = request.form['name']
        typed_email = request.form['email']
        typed_password = request.form['password']

        if User.query.filter_by(email=typed_email).first():
            flash('Email already registered....')
            return redirect(url_for('register'))
        else:
            new_user = User(name=typed_name, email=typed_email)
            new_user.set_password(typed_password)
            db.session.add(new_user)
            db.session.commit()

            # Log registration
            log_activity(f"New user registered: {typed_email}")

            flash('Registration successful! Please log in.')
            return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        typed_email = request.form['email']
        typed_password = request.form['password']
        user = User.query.filter_by(email=typed_email).first()

        if user and user.check_password(typed_password):
            login_user(user)
            if user.role == 'admin':
                return redirect(url_for('admin_panel'))
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password.')
            return redirect(url_for('login'))
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))


# ============================================================
# DASHBOARD ROUTE
# ============================================================

@app.route('/dashboard')
@login_required
def dashboard():
    user_transactions = Transaction.query.filter_by(user_id=current_user.id).all()
    total_income = sum(tx.amount for tx in user_transactions if tx.type == 'income')
    total_expense = sum(tx.amount for tx in user_transactions if tx.type == 'expense')
    net_balance = total_income - total_expense

    user_goals = Goal.query.filter_by(user_id=current_user.id).all()
    total_goals = sum(g.current_amount for g in user_goals)
    available_to_spend = net_balance - total_goals

    return render_template('dashboard.html',
                           net_balance=net_balance,
                           total_income=total_income,
                           total_expenses=total_expense,
                           transactions=user_transactions,
                           available_to_spend=available_to_spend)


# ============================================================
# TRANSACTION ROUTES
# ============================================================

@app.route('/transactions')
@login_required
def transactions():
    all_categories = Category.query.all()
    user_transactions = Transaction.query.filter_by(user_id=current_user.id).order_by(Transaction.date.desc()).all()
    return render_template('transactions.html', transactions=user_transactions, categories=all_categories)


@app.route('/transactions/add', methods=['GET', 'POST'])
@login_required
def add_transaction():
    if request.method == 'POST':
        amount = float(request.form['amount'])
        type = request.form['type']
        category = request.form['category']
        description = request.form['description']
        date = datetime.strptime(request.form['date'], '%Y-%m-%d')

        transaction = Transaction(amount=amount, type=type, category=category, description=description, date=date,
                                  user_id=current_user.id)
        db.session.add(transaction)
        db.session.commit()
        return redirect(url_for('transactions'))

    all_categories = Category.query.all()
    return render_template('add_transaction.html', categories=all_categories)


@app.route('/transactions/delete/<int:transaction_id>')
@login_required
def delete_transaction(transaction_id):
    transaction = Transaction.query.get(transaction_id)
    if transaction and transaction.user_id == current_user.id:
        db.session.delete(transaction)
        db.session.commit()
    return redirect(url_for('transactions'))


# ============================================================
# BUDGET & GOAL ROUTES
# ============================================================

@app.route('/budgets')
@login_required
def budgets():
    user_budgets = Budget.query.filter_by(user_id=current_user.id).all()
    all_categories = Category.query.all()
    return render_template('budgets.html', budgets=user_budgets, categories=all_categories)


@app.route('/budgets/add', methods=['POST'])
@login_required
def add_budget():
    new_budget = Budget(
        user_id=current_user.id,
        category=request.form['category'],
        limit_amount=float(request.form['limit_amount']),
        period=request.form['period']
    )
    db.session.add(new_budget)
    db.session.commit()
    return redirect(url_for('budgets'))


@app.route('/budgets/delete/<int:budget_id>')
@login_required
def delete_budget(budget_id):
    budget = Budget.query.get_or_404(budget_id)
    if budget.user_id == current_user.id:
        db.session.delete(budget)
        db.session.commit()
        flash("Budget deleted successfully.")
    return redirect(url_for('budgets'))


@app.route('/goals')
@login_required
def goals():
    all_goals = Goal.query.filter_by(user_id=current_user.id).all()
    return render_template('goals.html', goals=all_goals)


@app.route('/goals/add', methods=['POST'])
@login_required
def add_goal():
    new_goal = Goal(user_id=current_user.id, name=request.form['name'],
                    target_amount=float(request.form['target_amount']))
    db.session.add(new_goal)
    db.session.commit()
    return redirect(url_for('goals'))


@app.route('/goals/contribute/<int:goal_id>', methods=['POST'])
@login_required
def contribute_goal(goal_id):
    goal = Goal.query.get(goal_id)
    if goal and goal.user_id == current_user.id:
        goal.add_contribution(float(request.form['amount']))
    return redirect(url_for('goals'))


# ============================================================
# REPORTS ROUTE
# ============================================================

@app.route('/reports')
@login_required
def reports():
    transactions = Transaction.query.filter_by(user_id=current_user.id).all()
    income_data, expense_data = {}, {}

    for tx in transactions:
        if tx.type == 'income':
            income_data[tx.category] = income_data.get(tx.category, 0) + tx.amount
        else:
            expense_data[tx.category] = expense_data.get(tx.category, 0) + tx.amount

    return render_template('reports.html',
                           income_labels=list(income_data.keys()), income_values=list(income_data.values()),
                           expense_labels=list(expense_data.keys()), expense_values=list(expense_data.values()))


# ============================================================
# ADMIN ROUTES & ACTIONS
# ============================================================

@app.route('/admin')
@login_required
@admin_required
def admin_panel():
    all_users = User.query.all()
    total_tx_count = Transaction.query.count()

    # Calculate Wealth & Balances
    all_transactions = Transaction.query.all()
    total_income = sum(tx.amount for tx in all_transactions if tx.type == 'income')
    total_expense = sum(tx.amount for tx in all_transactions if tx.type == 'expense')
    platform_wealth = total_income - total_expense

    user_count = len(all_users)
    avg_balance = platform_wealth / user_count if user_count > 0 else 0

    # Fetch recent system logs
    recent_logs = SystemLog.query.order_by(SystemLog.timestamp.desc()).limit(15).all()

    return render_template(
        'admin.html',
        users=all_users,
        total_tx_count=total_tx_count,
        platform_wealth=platform_wealth,
        avg_balance=avg_balance,
        logs=recent_logs
    )


@app.route('/admin/categories/add', methods=['POST'])
@login_required
@admin_required
def admin_add_category():
    cat_name = request.form.get('category_name').strip()
    if cat_name:
        if not Category.query.filter_by(name=cat_name).first():
            db.session.add(Category(name=cat_name))
            db.session.commit()
            log_activity(f"Admin '{current_user.name}' created category '{cat_name}'")
            flash(f"Category '{cat_name}' successfully added!", "success")
        else:
            flash("That category already exists.", "danger")
    return redirect(url_for('admin_panel'))


@app.route('/admin/users/add-admin', methods=['POST'])
@login_required
@admin_required
def admin_create_user():
    name = request.form.get('name')
    email = request.form.get('email')
    password = request.form.get('password')

    if User.query.filter_by(email=email).first():
        flash("Email is already registered.", "danger")
    else:
        new_admin = User(name=name, email=email, role='admin')
        new_admin.set_password(password)
        db.session.add(new_admin)
        db.session.commit()
        log_activity(f"Admin '{current_user.name}' provisioned new admin account '{email}'")
        flash(f"Successfully provisioned administrative credentials for {name}!", "success")

    return redirect(url_for('admin_panel'))


@app.route('/admin/users/delete/<int:target_user_id>', methods=['POST'])
@login_required
@admin_required
def admin_delete_user(target_user_id):
    if target_user_id == current_user.id:
        flash("You cannot delete your own active session.", "danger")
        return redirect(url_for('admin_panel'))

    user = User.query.get_or_404(target_user_id)

    # Safely clear out all user dependencies before deleting the user
    Transaction.query.filter_by(user_id=user.id).delete()
    Budget.query.filter_by(user_id=user.id).delete()
    Goal.query.filter_by(user_id=user.id).delete()

    db.session.delete(user)
    db.session.commit()

    log_activity(f"Admin '{current_user.name}' permanently deleted user account '{user.email}'")
    flash(f"User {user.name} and all their data has been permanently deleted.", "success")
    return redirect(url_for('admin_panel'))


# ============================================================
# RUN APP & DATABASE SEEDING
# ============================================================

if __name__ == '__main__':
    with app.app_context():
        db.create_all()

        default_categories = [
            "Food & Dining", "Rent & Housing", "Utilities",
            "Salary & Earnings", "Entertainment", "Transportation",
            "Savings", "Other"
        ]
        for cat_name in default_categories:
            if not Category.query.filter_by(name=cat_name).first():
                db.session.add(Category(name=cat_name))

        admin_email = "admin@pesoapp.com"
        if not User.query.filter_by(email=admin_email).first():
            admin_user = User(name="System Admin", email=admin_email, role="admin")
            admin_user.set_password("admin@123")
            db.session.add(admin_user)
            log_activity("System initialized default master admin account.")

        db.session.commit()

    app.run(debug=True)