
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import sqlite3
import json
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

class PharmacyInventorySystem:
    def __init__(self, db_name='pharmacy.db'):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()
        self.load_medicine_data('medicines.json')

    def create_tables(self):
        """Create database tables if they don't exist"""
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS medicines (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                generic_name TEXT,
                type TEXT,
                power TEXT,
                company TEXT,
                price TEXT
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY,
                medicine_id INTEGER,
                quantity INTEGER NOT NULL,
                expiry_date DATE NOT NULL,
                purchase_price REAL NOT NULL,
                selling_price REAL NOT NULL,
                purchase_date DATE DEFAULT CURRENT_DATE,
                FOREIGN KEY (medicine_id) REFERENCES medicines(id)
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY,
                inventory_id INTEGER,
                quantity INTEGER NOT NULL,
                sale_price REAL NOT NULL,
                customer_name TEXT,
                sale_date DATE DEFAULT CURRENT_DATE,
                sale_time TIME DEFAULT CURRENT_TIME,
                total_amount REAL NOT NULL,
                FOREIGN KEY (inventory_id) REFERENCES inventory(id)
            )
        ''')

        # Add missing columns to existing tables
        # Check and add missing columns one by one
        self.cursor.execute("PRAGMA table_info(sales)")
        existing_columns = [column[1] for column in self.cursor.fetchall()]
        
        if 'customer_name' not in existing_columns:
            self.cursor.execute('ALTER TABLE sales ADD COLUMN customer_name TEXT')
        
        if 'sale_time' not in existing_columns:
            self.cursor.execute('ALTER TABLE sales ADD COLUMN sale_time TEXT')
            
        if 'total_amount' not in existing_columns:
            self.cursor.execute('ALTER TABLE sales ADD COLUMN total_amount REAL')

        self.conn.commit()

    def load_medicine_data(self, json_file):
        """Load medicine data from JSON file into database"""
        try:
            # Check if medicines table is empty
            self.cursor.execute('SELECT COUNT(*) FROM medicines')
            count = self.cursor.fetchone()[0]
            
            if count == 0:  # Only load if table is empty
                with open(json_file, 'r') as f:
                    medicines = json.load(f)

                for med in medicines:
                    self.cursor.execute('''
                        INSERT OR IGNORE INTO medicines (name, generic_name, type, power, company, price)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (med['name'], med.get('generic_name'), med.get('type'), 
                          med.get('power'), med.get('company'), med.get('price')))

                self.conn.commit()
                print(f"Loaded {len(medicines)} medicines into database")
        except FileNotFoundError:
            print("Medicine data file not found")

    def search_medicine(self, name):
        """Search medicines by name"""
        self.cursor.execute('''
            SELECT * FROM medicines 
            WHERE name LIKE ? 
            ORDER BY name
        ''', (f'%{name}%',))
        return self.cursor.fetchall()

    def add_to_inventory(self, medicine_id, quantity, expiry_date, purchase_price, selling_price):
        """Add medicine to inventory"""
        expiry_date = datetime.strptime(expiry_date, '%Y-%m-%d').date()
        self.cursor.execute('''
            INSERT INTO inventory (medicine_id, quantity, expiry_date, purchase_price, selling_price)
            VALUES (?, ?, ?, ?, ?)
        ''', (medicine_id, quantity, expiry_date, purchase_price, selling_price))
        self.conn.commit()
        return self.cursor.lastrowid

    def sell_medicine(self, inventory_id, quantity, customer_name=""):
        """Sell medicine and update inventory"""
        # Check available quantity
        self.cursor.execute('SELECT quantity FROM inventory WHERE id = ?', (inventory_id,))
        result = self.cursor.fetchone()
        if not result:
            return False, "Inventory item not found"
        
        available = result[0]

        if available < quantity:
            return False, "Not enough stock"

        # Get selling price
        self.cursor.execute('SELECT selling_price FROM inventory WHERE id = ?', (inventory_id,))
        selling_price = self.cursor.fetchone()[0]
        
        total_amount = quantity * selling_price

        # Record sale with current time
        current_time = datetime.now().strftime('%H:%M:%S')
        self.cursor.execute('''
            INSERT INTO sales (inventory_id, quantity, sale_price, customer_name, total_amount, sale_time)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (inventory_id, quantity, selling_price, customer_name, total_amount, current_time))

        # Update inventory
        self.cursor.execute('''
            UPDATE inventory SET quantity = quantity - ? 
            WHERE id = ?
        ''', (quantity, inventory_id))

        self.conn.commit()
        return True, f"Sold {quantity} items to {customer_name}. Total: ${total_amount:.2f}"

    def get_inventory(self, low_stock_threshold=10):
        """Get current inventory with expiry alerts"""
        self.cursor.execute('''
            SELECT i.id, m.name, i.quantity, i.expiry_date, 
                   i.purchase_price, i.selling_price,
                   CASE 
                       WHEN i.quantity <= ? THEN 'LOW'
                       WHEN date(i.expiry_date) < date('now', '+30 days') THEN 'NEAR_EXPIRY'
                       ELSE 'OK'
                   END AS status
            FROM inventory i
            JOIN medicines m ON i.medicine_id = m.id
            WHERE i.quantity > 0
            ORDER BY i.expiry_date
        ''', (low_stock_threshold,))
        return self.cursor.fetchall()

    def get_sales_report(self, period='daily'):
        """Generate sales report for specified period"""
        if period == 'daily':
            date_filter = "date('now')"
        elif period == 'weekly':
            date_filter = "date('now', '-7 days')"
        elif period == 'monthly':
            date_filter = "date('now', 'start of month')"
        else:
            return []

        # Check if new columns exist
        self.cursor.execute("PRAGMA table_info(sales)")
        columns = [column[1] for column in self.cursor.fetchall()]
        
        if 'sale_time' in columns and 'customer_name' in columns and 'total_amount' in columns:
            # Use new format with all columns
            self.cursor.execute(f'''
                SELECT s.sale_date, s.sale_time, m.name, s.customer_name, s.quantity, 
                       s.total_amount, (s.quantity * (s.sale_price - i.purchase_price)) AS profit
                FROM sales s
                JOIN inventory i ON s.inventory_id = i.id
                JOIN medicines m ON i.medicine_id = m.id
                WHERE s.sale_date >= {date_filter}
                ORDER BY s.sale_date DESC, s.sale_time DESC
            ''')
        else:
            # Use old format for compatibility
            self.cursor.execute(f'''
                SELECT s.sale_date, '', m.name, '', s.quantity, 
                       (s.quantity * s.sale_price) as total_amount, 
                       (s.quantity * (s.sale_price - i.purchase_price)) AS profit
                FROM sales s
                JOIN inventory i ON s.inventory_id = i.id
                JOIN medicines m ON i.medicine_id = m.id
                WHERE s.sale_date >= {date_filter}
                ORDER BY s.sale_date DESC
            ''')
        return self.cursor.fetchall()

    def get_expiring_medicines(self, days=30):
        """Get medicines expiring within specified days"""
        self.cursor.execute('''
            SELECT m.name, i.quantity, i.expiry_date,
                   CAST(julianday(i.expiry_date) - julianday('now') AS INTEGER) as days_remaining
            FROM inventory i
            JOIN medicines m ON i.medicine_id = m.id
            WHERE date(i.expiry_date) BETWEEN date('now') AND date('now', ?)
            ORDER BY i.expiry_date
        ''', (f'+{days} days',))
        return self.cursor.fetchall()

# Initialize the pharmacy system
pharmacy = PharmacyInventorySystem()

@app.route('/')
def dashboard():
    """Dashboard with overview"""
    inventory = pharmacy.get_inventory()
    expiring = pharmacy.get_expiring_medicines(30)
    sales = pharmacy.get_sales_report('daily')
    
    # Statistics
    total_medicines = len(inventory)
    low_stock_count = len([item for item in inventory if item[6] == 'LOW'])
    expiring_count = len(expiring)
    
    # Calculate total sales safely
    total_sales = 0
    if sales:
        for sale in sales:
            if len(sale) > 5 and sale[5] is not None:
                total_sales += sale[5]
    
    return render_template('dashboard.html', 
                         inventory=inventory[:10],  # Show first 10 items
                         expiring=expiring[:5],     # Show first 5 expiring
                         sales=sales[:5],           # Show first 5 sales
                         total_medicines=total_medicines,
                         low_stock_count=low_stock_count,
                         expiring_count=expiring_count,
                         total_sales=total_sales,
                         current_time=datetime.now())

@app.route('/search')
def search():
    """Search medicines page"""
    query = request.args.get('q', '')
    results = []
    if query:
        results = pharmacy.search_medicine(query)
    return render_template('search.html', results=results, query=query)

@app.route('/inventory')
def inventory():
    """Inventory management page"""
    inventory_items = pharmacy.get_inventory()
    return render_template('inventory.html', inventory=inventory_items)

@app.route('/add_inventory', methods=['GET', 'POST'])
def add_inventory():
    """Add medicine to inventory"""
    if request.method == 'POST':
        try:
            medicine_id = int(request.form['medicine_id'])
            quantity = int(request.form['quantity'])
            expiry_date = request.form['expiry_date']
            purchase_price = float(request.form['purchase_price'])
            selling_price = float(request.form['selling_price'])
            
            inv_id = pharmacy.add_to_inventory(medicine_id, quantity, expiry_date, purchase_price, selling_price)
            flash(f'Medicine added to inventory successfully! Inventory ID: {inv_id}', 'success')
            return redirect(url_for('inventory'))
        except Exception as e:
            flash(f'Error adding to inventory: {str(e)}', 'error')
    
    # Get all medicines for dropdown
    pharmacy.cursor.execute('SELECT id, name FROM medicines ORDER BY name')
    medicines = pharmacy.cursor.fetchall()
    return render_template('add_inventory.html', medicines=medicines)

@app.route('/sell', methods=['GET', 'POST'])
def sell():
    """Sell medicine"""
    if request.method == 'POST':
        try:
            inventory_id = int(request.form['inventory_id'])
            quantity = int(request.form['quantity'])
            customer_name = request.form.get('customer_name', '')
            
            success, message = pharmacy.sell_medicine(inventory_id, quantity, customer_name)
            if success:
                flash(message, 'success')
            else:
                flash(message, 'error')
            return redirect(url_for('inventory'))
        except Exception as e:
            flash(f'Error processing sale: {str(e)}', 'error')
    
    # Get available inventory for dropdown
    inventory_items = pharmacy.get_inventory()
    return render_template('sell.html', inventory=inventory_items)

@app.route('/reports')
def reports():
    """Sales reports page"""
    period = request.args.get('period', 'daily')
    sales_data = pharmacy.get_sales_report(period)
    return render_template('reports.html', sales=sales_data, period=period)

@app.route('/expiry')
def expiry():
    """Expiry alerts page"""
    days = int(request.args.get('days', 30))
    expiring_medicines = pharmacy.get_expiring_medicines(days)
    return render_template('expiry.html', expiring=expiring_medicines, days=days)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
