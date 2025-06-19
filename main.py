import sqlite3
import json
from datetime import datetime, timedelta

class PharmacyInventorySystem:
    def __init__(self, db_name='pharmacy.db'):
        self.conn = sqlite3.connect(db_name)
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
                sale_date DATE DEFAULT CURRENT_DATE,
                FOREIGN KEY (inventory_id) REFERENCES inventory(id)
            )
        ''')

        self.conn.commit()

    def load_medicine_data(self, json_file):
        """Load medicine data from JSON file into database"""
        try:
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

    def sell_medicine(self, inventory_id, quantity):
        """Sell medicine and update inventory"""
        # Check available quantity
        self.cursor.execute('SELECT quantity FROM inventory WHERE id = ?', (inventory_id,))
        available = self.cursor.fetchone()[0]

        if available < quantity:
            return False, "Not enough stock"

        # Get selling price
        self.cursor.execute('SELECT selling_price FROM inventory WHERE id = ?', (inventory_id,))
        selling_price = self.cursor.fetchone()[0]

        # Record sale
        self.cursor.execute('''
            INSERT INTO sales (inventory_id, quantity, sale_price)
            VALUES (?, ?, ?)
        ''', (inventory_id, quantity, selling_price))

        # Update inventory
        self.cursor.execute('''
            UPDATE inventory SET quantity = quantity - ? 
            WHERE id = ?
        ''', (quantity, inventory_id))

        self.conn.commit()
        return True, f"Sold {quantity} items. Total: {quantity * selling_price:.2f}"

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

        self.cursor.execute(f'''
            SELECT s.sale_date, m.name, SUM(s.quantity) AS total_quantity, 
                   SUM(s.quantity * s.sale_price) AS total_sales,
                   SUM(s.quantity * (s.sale_price - i.purchase_price)) AS profit
            FROM sales s
            JOIN inventory i ON s.inventory_id = i.id
            JOIN medicines m ON i.medicine_id = m.id
            WHERE s.sale_date >= {date_filter}
            GROUP BY s.sale_date, m.name
            ORDER BY s.sale_date DESC
        ''')
        return self.cursor.fetchall()

    def get_expiring_medicines(self, days=30):
        """Get medicines expiring within specified days"""
        self.cursor.execute('''
            SELECT m.name, i.quantity, i.expiry_date
            FROM inventory i
            JOIN medicines m ON i.medicine_id = m.id
            WHERE date(i.expiry_date) BETWEEN date('now') AND date('now', ?)
            ORDER BY i.expiry_date
        ''', (f'+{days} days',))
        return self.cursor.fetchall()

    def close(self):
        """Close database connection"""
        self.conn.close()

# CLI Interface
def main():
    pharmacy = PharmacyInventorySystem()

    while True:
        print("\nPharmacy Inventory System")
        print("1. Search Medicines")
        print("2. Add to Inventory")
        print("3. View Inventory")
        print("4. Sell Medicine")
        print("5. Sales Report")
        print("6. Expiry Alerts")
        print("7. Exit")

        choice = input("Enter your choice: ")

        if choice == '1':
            name = input("Enter medicine name: ")
            results = pharmacy.search_medicine(name)
            if results:
                print("\nSearch Results:")
                for med in results:
                    print(f"{med[0]}: {med[1]} ({med[2]}) - {med[4]} - {med[5]} - Price: {med[6]}")
            else:
                print("No medicines found")

        elif choice == '2':
            med_id = int(input("Enter medicine ID: "))
            quantity = int(input("Enter quantity: "))
            expiry = input("Enter expiry date (YYYY-MM-DD): ")
            cost = float(input("Enter purchase price per unit: "))
            sell = float(input("Enter selling price per unit: "))

            inv_id = pharmacy.add_to_inventory(med_id, quantity, expiry, cost, sell)
            print(f"Added to inventory. Inventory ID: {inv_id}")

        elif choice == '3':
            inventory = pharmacy.get_inventory()
            if inventory:
                print("\nCurrent Inventory:")
                print("ID  | Name                | Qty | Expiry     | Cost  | Price | Status")
                for item in inventory:
                    print(f"{item[0]:<4} {item[1][:20]:<20} {item[2]:<4} {item[3]} ${item[4]:<6.2f} ${item[5]:<6.2f} {item[6]}")
            else:
                print("Inventory is empty")

        elif choice == '4':
            inv_id = int(input("Enter inventory ID: "))
            quantity = int(input("Enter quantity to sell: "))

            success, message = pharmacy.sell_medicine(inv_id, quantity)
            print(message)

        elif choice == '5':
            period = input("Report period (daily/weekly/monthly): ").lower()
            report = pharmacy.get_sales_report(period)

            if report:
                print(f"\n{period.capitalize()} Sales Report:")
                print("Date       | Medicine          | Qty | Sales    | Profit")
                for row in report:
                    print(f"{row[0]} {row[1][:15]:<15} {row[2]:<4} ${row[3]:<8.2f} ${row[4]:<8.2f}")
            else:
                print("No sales data found")

        elif choice == '6':
            days = int(input("Show expiring within how many days? (30): ") or 30)
            expiring = pharmacy.get_expiring_medicines(days)

            if expiring:
                print(f"\nMedicines Expiring within {days} days:")
                print("Name                | Qty | Expiry")
                for med in expiring:
                    print(f"{med[0][:20]:<20} {med[1]:<4} {med[2]}")
            else:
                print("No expiring medicines found")

        elif choice == '7':
            pharmacy.close()
            print("Exiting system")
            break

        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    main()