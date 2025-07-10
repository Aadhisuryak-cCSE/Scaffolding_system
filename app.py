from flask import Flask, render_template, request, redirect, url_for, flash, send_file,jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, IntegerField, FloatField, SubmitField, SelectField, DecimalField, DateField
from wtforms.validators import DataRequired, Email, NumberRange, Optional
from datetime import datetime, timedelta
from collections import defaultdict
from werkzeug.security import generate_password_hash, check_password_hash
from flask_migrate import Migrate
import pandas as pd
import io
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'sivaamohan@2002' 
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'  # Or your DB path
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='Staff')

class Stock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)

class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    vehicle_no = db.Column(db.String(50), nullable=True)  # new field
    phone = db.Column(db.String(20), nullable=True)
    address = db.Column(db.String(200), nullable=True)
    status = db.Column(db.String(20), default='Processing')  # Add this
    advance = db.Column(db.Float, default=0.0)
    advance_closed = db.Column(db.Boolean, default=False)


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    order_date = db.Column(db.DateTime, nullable=False)
    return_date = db.Column(db.DateTime, nullable=True)
    customer = db.relationship('Customer', backref='orders')
    order_items = db.relationship('OrderItem', backref='order', cascade='all, delete-orphan')

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    stock_id = db.Column(db.Integer, db.ForeignKey('stock.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    pending_amount = db.Column(db.Float, nullable=False)
    fine_amount = db.Column(db.Float, default=0.0)
    bonus_amount = db.Column(db.Float, default=0.0)
    used_days = db.Column(db.Integer, nullable=True)
    return_date = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='Pending')

    stock = db.relationship('Stock', backref='order_items')



class Shipment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(20), nullable=False)
    stock_id = db.Column(db.Integer, db.ForeignKey('stock.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    supplier = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(20), nullable=False, default='Pending')
    shipment_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    stock = db.relationship('Stock', backref='shipments')

# Forms
class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class StockForm(FlaskForm):
    name = StringField('Item Name', validators=[DataRequired()])
    category = StringField('Category', validators=[DataRequired()])
    quantity = IntegerField('Quantity', validators=[DataRequired(), NumberRange(min=0)])
    unit_price = FloatField('Unit Price', validators=[DataRequired(), NumberRange(min=0)])
    submit = SubmitField('Add Stock')

class CustomerForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    vehicle_no = StringField('Vehicle No')
    phone = StringField('Phone')
    address = StringField('Address')
    submit = SubmitField('Add Customer')

class OrderForm(FlaskForm):
    customer_id = SelectField('Customer', coerce=int, validators=[DataRequired()])
    advance = FloatField('Advance Amount', validators=[Optional()])
    order_date = DateField('Order Date', validators=[DataRequired()])
    submit = SubmitField('Create Order')

class OrderItemForm(FlaskForm):
    stock_id = SelectField('Stock', coerce=int, validators=[DataRequired()])
    quantity = IntegerField('Quantity', validators=[DataRequired(), NumberRange(min=1)])
    status = SelectField('Status', choices=[('Pending', 'Pending'), ('Delivered', 'Delivered')])
    submit = SubmitField('Add Item')


class ShipmentForm(FlaskForm):
    type = SelectField('Type', choices=[('Import', 'Import'), ('Export', 'Export')], validators=[DataRequired()])
    stock_id = SelectField('Stock Item', coerce=int, validators=[DataRequired()])
    quantity = IntegerField('Quantity', validators=[DataRequired(), NumberRange(min=1)])
    supplier = StringField('Supplier (Optional)')
    status = SelectField('Status', choices=[('Pending', 'Pending'), ('Delivered', 'Delivered')], validators=[DataRequired()])
    submit = SubmitField('Add Shipment')

class CheckForm(FlaskForm):
    id_type = SelectField('ID Type', choices=[('Customer', 'Customer'), ('Stock', 'Stock'), ('Shipment', 'Shipment')], validators=[DataRequired()])
    id_number = IntegerField('ID Number', validators=[DataRequired(), NumberRange(min=1)])
    submit = SubmitField('Check Details')

class ReturnForm(FlaskForm):
    return_date = DateField('Return Date', validators=[DataRequired()])
    submit = SubmitField('Submit Return')


# User Loader
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes
@app.route('/')
def index():
    return redirect(url_for('login'))


# API Login Route
@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({'success': False, 'message': 'Missing username or password'}), 400
    username = data['username']
    password = data['password']
    user = User.query.filter_by(username=username).first()
    if user and check_password_hash(user.password, password):
        login_user(user)
        return jsonify({'success': True, 'redirect': url_for('dashboard')})
    return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

@app.route('/login', methods=['GET', 'POST'])
def login():

    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        # print(check_password_hash(user.password, form.password.data))
        if user and check_password_hash(user.password, form.password.data):
            login_user(user)
            flash('Login successful', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid credentials', 'danger')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully', 'success')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    stock_count = Stock.query.count()
    customer_count = Customer.query.count()
    order_count = Order.query.count()
    shipment_count = Shipment.query.count()
    low_stock = Stock.query.filter(Stock.quantity < 10).count()
    if low_stock > 0:
        flash(f'Warning: {low_stock} stock items are below 10 units', 'warning')
    return render_template('dashboard.html', stock_count=stock_count, customer_count=customer_count,
                           order_count=order_count, shipment_count=shipment_count)

@app.route('/stock', methods=['GET', 'POST'])
@login_required
def stock():
    if current_user.role not in ['Admin', 'Manager']:
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))
    form = StockForm()
    if form.validate_on_submit():
        stock = Stock(name=form.name.data, category=form.category.data,
                      quantity=form.quantity.data, unit_price=form.unit_price.data)
        db.session.add(stock)
        db.session.commit()
        flash('Stock added successfully', 'success')
        return redirect(url_for('stock'))
    stocks = Stock.query.all()
    return render_template('stock.html', form=form, stocks=stocks)

@app.route('/stock/export')
@login_required
def export_stock():
    if current_user.role not in ['Admin', 'Manager']:
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))
    stocks = Stock.query.all()
    df = pd.DataFrame([(s.id, s.name, s.category, s.quantity, s.unit_price) for s in stocks],
                      columns=['ID', 'Name', 'Category', 'Quantity', 'Unit Price'])
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    return send_file(output, download_name='stock_export.xlsx', as_attachment=True)

@app.route('/stock/import', methods=['GET', 'POST'])
@login_required
def import_stock():
    if current_user.role not in ['Admin', 'Manager']:
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        file = request.files['file']
        if file and file.filename.endswith('.xlsx'):
            df = pd.read_excel(file)
            for _, row in df.iterrows():
                stock = Stock(name=row['Name'], category=row['Category'],
                              quantity=row['Quantity'], unit_price=row['Unit Price'])
                db.session.add(stock)
            db.session.commit()
            flash('Stock imported successfully', 'success')
            return redirect(url_for('stock'))
        flash('Invalid file format', 'danger')
    return render_template('import.html', title='Import Stock')

@app.route('/customers', methods=['GET', 'POST'])
@login_required
def customers():
    if current_user.role not in ['Admin', 'Manager']:
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))
    form = CustomerForm()
    if form.validate_on_submit():
        customer = Customer(name=form.name.data, vehicle_no=form.vehicle_no.data,
                            phone=form.phone.data, address=form.address.data)
        db.session.add(customer)
        db.session.commit()
        flash('Customer added successfully', 'success')
        return redirect(url_for('customers'))
    customers = Customer.query.all()
    return render_template('customers.html', form=form, customers=customers)

@app.route('/orders', methods=['GET', 'POST'])
@login_required
def orders():
    if current_user.role not in ['Admin', 'Manager']:
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))

    form = OrderForm()
    form.customer_id.choices = [(c.id, f"{c.id} - {c.name}") for c in Customer.query.all()]


    if form.validate_on_submit():
        customer = Customer.query.get(form.customer_id.data)

        # ✅ Add advance only once (on first order)
        if form.advance.data:
            if not customer.advance_closed and len(customer.orders) == 0:
                customer.advance = (customer.advance or 0) + float(form.advance.data)
             
            elif customer.advance_closed:
                customer.advance = float(form.advance.data)
                customer.advance_closed = False 

        order = Order(
            customer_id=form.customer_id.data,
            order_date=form.order_date.data
        )

        db.session.add(order)
        db.session.commit()
        flash('Order created. Now add items.', 'success')
        return redirect(url_for('add_order_item', order_id=order.id))

    orders = Order.query.order_by(Order.id).all()
    customer_totals = defaultdict(float)

    # ✅ Calculate total, bonus, pending for each order
    for order in orders:
        order.total_price = sum(item.total_price or 0.0 for item in order.order_items)
        customer_totals[order.customer_id] += order.total_price
       
    for idx, order in enumerate(orders):
        advance = order.customer.advance or 0.0
        total_spent = customer_totals[order.customer_id]
        bonus = max(advance - total_spent, 0)
        order.total_spent = total_spent
        order.bonus_amount = bonus if idx == 0 else None
        order.pending_amount = 0  # optional

    return render_template('orders.html', form=form, orders=orders)



@app.route('/order/<int:order_id>/add_item', methods=['GET', 'POST'])
@login_required
def add_order_item(order_id):
    order = Order.query.get_or_404(order_id)
    form = OrderItemForm()
    form.stock_id.choices = [(s.id, s.name) for s in Stock.query.all()]

    if form.validate_on_submit():
        stock = Stock.query.get(form.stock_id.data)
        total_price = stock.unit_price * form.quantity.data
        pending = total_price  # full price initially, will be adjusted later

        order_item = OrderItem(
            order_id=order_id,
            stock_id=form.stock_id.data,
            quantity=form.quantity.data,
            unit_price=stock.unit_price,
            total_price=total_price,
            pending_amount=pending,
            fine_amount=0.0,
            bonus_amount=0.0,
            used_days=0,
            status=form.status.data
        )

        stock.quantity -= form.quantity.data
        db.session.add(order_item)
        db.session.commit()

        flash('Item added to order.', 'success')
        return redirect(url_for('add_order_item', order_id=order_id))

    return render_template('add_item.html', form=form, order=order)


@app.route('/shipments', methods=['GET', 'POST'])
@login_required
def shipments():
    if current_user.role not in ['Admin', 'Manager']:
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))
    form = ShipmentForm()
    form.stock_id.choices = [(s.id, s.name) for s in Stock.query.all()]
    if form.validate_on_submit():
        shipment = Shipment(type=form.type.data, stock_id=form.stock_id.data,
                           quantity=form.quantity.data, supplier=form.supplier.data, status=form.status.data)  # Use user-selected status)
        stock = Stock.query.get(form.stock_id.data)
        if form.type.data == 'Import':
            if stock:
                stock.quantity += form.quantity.data
            else:
                flash('Stock item not found', 'danger')
                return redirect(url_for('shipments'))
        elif form.type.data == 'Export':
            if stock and stock.quantity >= form.quantity.data:
                stock.quantity -= form.quantity.data
            else:
                flash('Insufficient stock or stock not found', 'danger')
                return redirect(url_for('shipments'))
        db.session.add(shipment)
        db.session.commit()
        flash('Shipment added successfully', 'success')
        return redirect(url_for('shipments'))
    shipments = Shipment.query.all()
    return render_template('shipments.html', form=form, shipments=shipments)



###############################edit################################
@app.route('/edit_stock/<int:stock_id>', methods=['GET', 'POST'])
def edit_stock(stock_id=None):
    form = StockForm()
    if stock_id:
        stock_item = Stock.query.get(stock_id)
        ###db.query.get with 404(namma click pannura id)###
        if request.method == 'GET':
            form.name.data = stock_item.name
            form.category.data = stock_item.category
            form.quantity.data = stock_item.quantity
            form.unit_price.data = stock_item.unit_price
    else:
        stock_item = None

    if form.validate_on_submit():
        if stock_item:
            # Edit mode
            stock_item.name = form.name.data
            stock_item.category = form.category.data
            stock_item.quantity = form.quantity.data
            stock_item.unit_price = form.unit_price.data
            flash('Stock item updated!', 'success')
        else:
            # Create mode
            new_stock = Stock(
                name=form.name.data,
                category=form.category.data,
                quantity=form.quantity.data,
                unit_price=form.unit_price.data
            )
            db.session.add(new_stock)
            flash('Stock item added!', 'success')

        db.session.commit()
        return redirect(url_for('stock'))

    stocks = Stock.query.all()
    return render_template('stock.html', form=form, stocks=stocks)



@app.route('/delete_stock/<int:stock_id>', methods=['GET', 'POST'])
def delete_stock(stock_id=None):
    stock = Stock.query.get_or_404(stock_id)
    if stock.order_items:  # check for related orders
        flash('Cannot delete stock item because it is associated with existing orders.', 'danger')
        return redirect(url_for('stock'))
    
    db.session.delete(stock)
    db.session.commit()
    flash('Stock item deleted successfully.', 'success')
    return redirect(url_for('stock'))

    ######################delete and edit customer###########

@app.route('/edit_customer/<int:customer_id>', methods=['GET', 'POST'])
@login_required
def edit_customer(customer_id):
    if current_user.role not in ['Admin', 'Manager']:
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))

    customer = Customer.query.get_or_404(customer_id)
    form = CustomerForm(obj=customer)

    if request.method == 'GET':
        form.name.data = customer.name
        form.vehicle_no.data = customer.vehicle_no
        form.phone.data = customer.phone
        form.address.data = customer.address

    if form.validate_on_submit():
        customer.name = form.name.data
        customer.vehicle_no = form.vehicle_no.data
        customer.phone = form.phone.data
        customer.address = form.address.data
        db.session.commit()
        flash('Customer updated successfully!', 'success')
        return redirect(url_for('customers'))

    customers = Customer.query.all()
    return render_template('customers.html', form=form, customers=customers)


@app.route('/delete_customer/<int:customer_id>', methods=['GET', 'POST'])
@login_required
def delete_customer(customer_id=None):
    if current_user.role not in ['Admin', 'Manager']:
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))
    customer = Customer.query.get_or_404(customer_id)
    if customer.orders:  # Check for related orders
        flash('Cannot delete customer because they have associated orders.', 'danger')
        return redirect(url_for('customers'))
    db.session.delete(customer)
    db.session.commit()
    flash('Customer deleted successfully.', 'success')
    return redirect(url_for('customers'))

##################edit and delete order ##############

@app.route('/edit_order/<int:order_id>', methods=['GET', 'POST'])
@login_required
def edit_order(order_id):
    if current_user.role not in ['Admin', 'Manager']:
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))

    order = Order.query.get_or_404(order_id)
    form = OrderForm()
    form.customer_id.choices = [(c.id, c.name) for c in Customer.query.all()]

    if request.method == 'GET':
        form.customer_id.data = order.customer_id
        form.order_date.data = order.order_date
        form.advance.data = order.customer.advance

    if form.validate_on_submit():
        order.customer_id = form.customer_id.data
        order.order_date = form.order_date.data
        order.customer.advance = float(form.advance.data)
        db.session.commit()
        flash('Order updated successfully!', 'success')
        return redirect(url_for('add_items', order_id=order.id, edit_mode='true'))

    orders = Order.query.all()
    return render_template('orders.html', form=form, orders=orders, editing_order=order)

@app.route('/delete_order/<int:order_id>', methods=['POST', 'GET'])
@login_required
def delete_order(order_id):
    order = Order.query.get_or_404(order_id)
    customer = order.customer

    # Calculate total of this order
    total_order_price = sum(item.total_price or 0 for item in order.order_items)

    # If customer.advance is None, treat it as 0.0
    customer.advance = customer.advance or 0.0

    # Reverse advance used in this order only if needed (optional)
    if customer.advance >= total_order_price:
        customer.advance -= total_order_price
    else:
        customer.advance = 0.0

    # Delete all related order items
    for item in order.order_items:
        db.session.delete(item)

    db.session.delete(order)
    db.session.commit()
    flash('Order deleted successfully.', 'success')
    return redirect(url_for('orders'))



##################### edit and delete shipments #############

@app.route('/edit_shipment/<int:shipment_id>', methods=['GET', 'POST'])
@login_required
def edit_shipment(shipment_id=None):
    if current_user.role not in ['Admin', 'Manager']:
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))
    form = ShipmentForm()
    form.stock_id.choices = [(s.id, s.name) for s in Stock.query.all()]
    shipment = Shipment.query.get_or_404(shipment_id) if shipment_id else None

    if request.method == 'GET' and shipment:
        form.type.data = shipment.type
        form.stock_id.data = shipment.stock_id
        form.quantity.data = shipment.quantity
        form.supplier.data = shipment.supplier
        form.status.data = shipment.status

    if form.validate_on_submit():
        stock = Stock.query.get(form.stock_id.data)
        if stock:
            # Restore original stock quantity if editing
            if shipment:
                if shipment.type == 'Import':
                    stock.quantity -= shipment.quantity
                elif shipment.type == 'Export':
                    stock.quantity += shipment.quantity
            # Check stock availability for new values
            if form.type.data == 'Export' and stock.quantity < form.quantity.data:
                flash('Insufficient stock for export', 'danger')
                return render_template('shipments.html', form=form, shipments=Shipment.query.all())
            # Update shipment details
            if shipment:
                # Edit mode
                shipment.type = form.type.data
                shipment.stock_id = form.stock_id.data
                shipment.quantity = form.quantity.data
                shipment.supplier = form.supplier.data
                shipment.status = form.status.data
                flash('Shipment updated successfully!', 'success')
            else:
                # Create mode (optional)
                new_shipment = Shipment(
                    type=form.type.data,
                    stock_id=form.stock_id.data,
                    quantity=form.quantity.data,
                    supplier=form.supplier.data,
                    status=form.status.data
                )
                db.session.add(new_shipment)
                flash('Shipment added successfully!', 'success')
            # Update stock quantity based on new values
            if form.type.data == 'Import':
                stock.quantity += form.quantity.data
            elif form.type.data == 'Export':
                stock.quantity -= form.quantity.data
            db.session.commit()
            return redirect(url_for('shipments'))
        else:
            flash('Stock item not found', 'danger')
    shipments = Shipment.query.all()
    return render_template('shipments.html', form=form, shipments=shipments)

@app.route('/delete_shipment/<int:shipment_id>', methods=['GET', 'POST'])
@login_required
def delete_shipment(shipment_id=None):
    if current_user.role not in ['Admin', 'Manager']:
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))
    shipment = Shipment.query.get_or_404(shipment_id)
    # Restore stock quantity before deletion
    stock = Stock.query.get(shipment.stock_id)
    if stock:
        if shipment.type == 'Import':
            stock.quantity -= shipment.quantity
        elif shipment.type == 'Export':
            stock.quantity += shipment.quantity
    db.session.delete(shipment)
    db.session.commit()
    flash('Shipment deleted successfully.', 'success')
    return redirect(url_for('shipments'))

@app.route('/check', methods=['GET', 'POST'])
@login_required
def check():
    form = CheckForm()
    results = None
    customer = None
    stock = None
    shipment = None
    id_type = None
    customer_label = ''
    customer_status = ''
    customer_bonus = 0

    if form.validate_on_submit():
        id_type = form.id_type.data
        id_number = form.id_number.data

        if id_type == 'Customer':
            customer = Customer.query.get(id_number)
    if customer:
        orders = customer.orders
        results = orders
        customer_label = f"Customer ID: {customer.id} ({customer.name})"
        customer_status = customer.status

        # Calculate total spent and allocate advance
        all_items = []
        for order in orders:
            all_items.extend(order.order_items)

        remaining_advance = customer.advance
        for item in all_items:
            if remaining_advance >= item.total_price:
                item.advance = item.total_price
                item.pending_amount = 0
                item.bonus_amount = 0
                remaining_advance -= item.total_price
            else:
                item.advance = remaining_advance
                item.pending_amount = item.total_price - remaining_advance
                item.bonus_amount = 0
                remaining_advance = 0

        # Assign the final bonus to all_items[-1] (or customer-level if needed)
            if all_items:
                all_items[-1].bonus_amount = remaining_advance

            else:
                flash('Customer not found', 'danger')

    elif id_type == 'Stock':
        stock = Stock.query.get(id_number)
        if stock:
            order_items = OrderItem.query.filter_by(stock_id=id_number).all()
            results = order_items
        else:
            flash('Stock item not found', 'danger')

    elif id_type == 'Shipment':
        shipment = Shipment.query.get(id_number)
        if shipment:
            results = [shipment]
        else:
            flash('Shipment not found', 'danger')

    return render_template(
        'check.html',
        form=form,
        results=results,
        customer=customer,
        stock=stock,
        shipment=shipment,
        id_type=id_type,
        customer_label=customer_label,
        customer_status=customer_status,
        customer_bonus=customer_bonus  # 👉 Pass to template (optional use)
    )




@app.route('/return/<int:order_id>', methods=['GET', 'POST'])
@login_required
def return_order(order_id):
    order = Order.query.get_or_404(order_id)
    customer = order.customer
    form = ReturnForm()

    if form.validate_on_submit():
        return_date = form.return_date.data
        order.return_date = return_date

        # ✅ Recalculate based on current order only
        total_advance = customer.advance or 0.0
        total_price = sum(item.total_price or 0.0 for item in order.order_items)

        # Update used_days, return_date per item
        for item in order.order_items:
            order_date = order.order_date
            if hasattr(order_date, 'date'):
                order_date = order_date.date()
            item.used_days = (return_date - order_date).days
            item.return_date = return_date
            item.fine_amount = 0

        # ✅ Clear all previous bonuses/pendings
        for item in order.order_items:
            item.bonus_amount = 0.0
            item.pending_amount = 0.0

        # ✅ Apply new bonus/pending based on rule
        bonus, pending = calculate_bonus_and_pending(total_advance, total_price)

        # Distribute bonus and pending to first item only
        if order.order_items:
            first_item = order.order_items[0]
            first_item.bonus_amount = bonus
            first_item.pending_amount = pending

        db.session.commit()
        flash("Return processed successfully", "success")
        return redirect(url_for('orders'))

    return render_template('return_order.html', form=form, order=order)


# ✅ Add this function anywhere below your route definitions (e.g., bottom of app.py)
def calculate_bonus_and_pending(advance, total_price):
    if advance > total_price:
        return advance - total_price, 0.0
    elif total_price > advance:
        return 0.0, total_price - advance
    else:
        return 0.0, 0.0
    
@app.route('/settle_advance/<int:customer_id>', methods=['POST'])
@login_required
def settle_advance(customer_id):
    customer = Customer.query.get_or_404(customer_id)

    customer.advance_closed = True


    db.session.commit()
    flash(f"Advance settled for {customer.name}. New orders will start fresh.", 'success')
    return redirect(url_for('orders'))


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', password=generate_password_hash('admin123'), role='Admin')
            db.session.add(admin)
            db.session.commit()
    app.run(debug=True, host='0.0.0.0', port=9000)