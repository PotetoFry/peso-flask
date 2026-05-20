from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

# ============================================================
# APP SETUP
# ============================================================

app = Flask(__name__)


@app.context_processor
def inject_currency():
    print("DEBUG: The Context Processor is RUNNING!")
    return dict(CURRENCY_SYMBOL='₱')


app.config['SECRET_KEY'] = 'change-this-to-a-random-string'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///finance.db'

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'  # redirect here if not logged in


# ============================================================
# MODELS  (your database tables)
# ============================================================

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='user')  # 'user' or 'admin'

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def to_safe_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'role': self.role
        }


class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    type = db.Column(db.String(10), nullable=False)  # 'income' or 'expense'
    category = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200))
    date = db.Column(db.DateTime, default=datetime.utcnow)

    def is_expense(self):
        return self.type == 'expense'

    def is_income(self):
        return self.type == 'income'


class Budget(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    limit_amount = db.Column(db.Float, nullable=False)
    period = db.Column(db.String(20), default='monthly')  # 'monthly', 'weekly'

    def get_remaining_budget(self):
        user_transactions = Transaction.query.filter_by(user_id=self.user_id, category=self.category).all()
        total_expense = 0
        for transaction in user_transactions:
            if transaction.type == 'expense':
                total_expense += transaction.amount
        return self.limit_amount - total_expense

    def is_exceeded(self):
        # FIX: Now returns True if you have spent more than your limit!
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


# ============================================================
# LOGIN MANAGER
# ============================================================

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ============================================================
# AUTH ROUTES
# ============================================================

@app.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('register'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        typed_name = request.form['name']
        typed_email = request.form['email']
        typed_password = request.form['password']

        existing_user = User.query.filter_by(email=typed_email).first()
        if existing_user:
            flash('Email already registered....')
            return redirect(url_for('register'))
        else:
            hashed_password = generate_password_hash(typed_password)
            new_user = User(name=typed_name, email=typed_email, password_hash=hashed_password)
            db.session.add(new_user)
            db.session.commit()
            flash('Registration successful! Please log in.')
            return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        typed_email = request.form['email']
        typed_password = request.form['password']

        existing_user = User.query.filter_by(email=typed_email).first()
        if existing_user and check_password_hash(existing_user.password_hash, typed_password):
            login_user(existing_user)
            print("Logged in successfully")
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
    total_income = 0
    total_expense = 0

    user_transactions = Transaction.query.filter_by(user_id=current_user.id).all()
    for transaction in user_transactions:
        if transaction.type == 'income':
            total_income += transaction.amount
        else:
            total_expense += transaction.amount

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

    # FIX: Must pass categories to the GET request so the dropdown works!
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
# BUDGET ROUTES
# ============================================================

@app.route('/budgets')
@login_required
def budgets():
    user_budgets = Budget.query.filter_by(user_id=current_user.id).all()
    all_categories = Category.query.all()
    return render_template('budgets.html', budgets=user_budgets, categories=all_categories)


# FIX: Changed to POST only since the form is on the main budgets page!
@app.route('/budgets/add', methods=['POST'])
@login_required
def add_budget():
    category = request.form['category']
    limit_amount = float(request.form['limit_amount'])
    period = request.form['period']

    new_budget = Budget(user_id=current_user.id, category=category, limit_amount=limit_amount, period=period)
    db.session.add(new_budget)
    db.session.commit()
    return redirect(url_for('budgets'))


@app.route('/budgets/delete/<int:budget_id>')
@login_required
def delete_budget(budget_id):
    budget = Budget.query.get_or_404(budget_id)
    if budget.user_id != current_user.id:
        flash("You are not authorized to delete this.")
        return redirect(url_for('budgets'))

    db.session.delete(budget)
    db.session.commit()
    flash("Budget deleted successfully.")
    return redirect(url_for('budgets'))


# ============================================================
# GOAL ROUTES
# ============================================================

@app.route('/goals')
@login_required
def goals():
    all_goals = Goal.query.filter_by(user_id=current_user.id).all()
    return render_template('goals.html', goals=all_goals)


# FIX: Changed to POST only since the form is on the main goals page!
@app.route('/goals/add', methods=['POST'])
@login_required
def add_goal():
    name = request.form['name']
    target_amount = float(request.form['target_amount'])

    new_goal = Goal(user_id=current_user.id, name=name, target_amount=target_amount)
    db.session.add(new_goal)
    db.session.commit()
    return redirect(url_for('goals'))


@app.route('/goals/contribute/<int:goal_id>', methods=['POST'])
@login_required
def contribute_goal(goal_id):
    goal = Goal.query.get(goal_id)
    amount = float(request.form['amount'])

    if goal.user_id != current_user.id:
        flash("You are not authorized to contribute this.")
    else:
        goal.add_contribution(amount)
        # Note: commit is handled inside add_contribution

    return redirect(url_for('goals'))


# ============================================================
# ADMIN ROUTES
# ============================================================

@app.route('/admin')
@login_required
def admin_panel():
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    return render_template('admin.html')


# ============================================================
# REPORTS ROUTE
# ============================================================

@app.route('/reports')
@login_required
def reports():
    transactions = Transaction.query.filter_by(user_id=current_user.id).all()

    income_data = {}
    expense_data = {}

    for tx in transactions:
        if tx.type == 'income':
            income_data[tx.category] = income_data.get(tx.category, 0) + tx.amount
        else:
            expense_data[tx.category] = expense_data.get(tx.category, 0) + tx.amount

    return render_template('reports.html',
                           income_labels=list(income_data.keys()),
                           income_values=list(income_data.values()),
                           expense_labels=list(expense_data.keys()),
                           expense_values=list(expense_data.values()))


# ============================================================
# RUN THE APP
# ============================================================

if __name__ == '__main__':
    with app.app_context():
        # FIX: Missing db.create_all() added back!
        db.create_all()

        default_categories = [
            "Food & Dining", "Rent & Housing", "Utilities",
            "Salary & Earnings", "Entertainment", "Transportation",
            "Savings", "Other"
        ]

        for cat_name in default_categories:
            if not Category.query.filter_by(name=cat_name).first():
                db.session.add(Category(name=cat_name))

        db.session.commit()

    app.run(debug=True)