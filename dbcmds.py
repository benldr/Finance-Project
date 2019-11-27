from __future__ import print_function
from datetime import date, datetime, timedelta
from mysql.connector import errorcode

import mysql.connector
import os

cnx = 0
cursor = 0


def mysql_login():
    global cnx, cursor
    try:
        # Connect to MySQL
        cnx = mysql.connector.connect(host='localhost', user='root', password=os.environ.get("MySQL_Password"))

    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            print("Something is wrong with your username or password.", flush=True)
        elif err.errno == errorcode.ER_BAD_DB_ERROR:
            print("Database does not exist.", flush=True)
        else:
            print(err, flush=True)
    cursor = cnx.cursor()
    print("Logged in to MySQL on local host as user: root.")
    return cnx


def create_database(db_name):
    global cursor
    try:
        cursor.execute(
            "CREATE DATABASE {} DEFAULT CHARACTER SET 'utf8'".format(db_name))
    except mysql.connector.Error as err:
        print("Failed creating database: {}".format(err))
        exit(1)

# USE given database (after logging in to MySQL server).
def use_database(db_name):
    global cnx, cursor
    try:
        cursor.execute("USE {}".format(db_name))
        print("Using database {}.".format(db_name))
    except mysql.connector.Error as err:
        print("Database {} does not exist.".format(db_name))
        if err.errno == errorcode.ER_BAD_DB_ERROR:
            create_database(db_name)
            print("Database {} created successfully.".format(db_name))
            cnx.database = db_name
        else:
           print(err)
           exit(1)

TABLES = {}
TABLES['users'] = (
    "CREATE TABLE `users` ("
    "  `id` INTEGER NOT NULL AUTO_INCREMENT,"
    "  `username` TEXT NOT NULL,"
    "  `hash` TEXT NOT NULL,"
    "  `cash` REAL NOT NULL DEFAULT 10000.00,"
    "  PRIMARY KEY (`id`)"
    ") ENGINE=InnoDB")

TABLES['transactions'] = (
    "CREATE TABLE `transactions` ("
    "  `id` INTEGER NOT NULL,"
    "  `symbol` VARCHAR(255) NOT NULL,"
    "  `price` REAL,"
    "  `shares` INTEGER NOT NULL,"
    "  `datetime` DATETIME,"
    "  PRIMARY KEY (`datetime`)"
    ") ENGINE=InnoDB")


# Create one table using the description in the TABLES list.
def create_table(table_name):
    table_description = TABLES[table_name]
    try:
        print("Creating table {}: ".format(table_name), end='', flush=True)
        cursor.execute(table_description)
    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_TABLE_EXISTS_ERROR:
            print("already exists.", flush=True)
        else:
            print(err.msg, flush=True)
    else:
        print("OK", flush=True)


# Create tables in the finance database. 
# The table order may be important if there are foreign key constraints. 
def create_finance_tables():
    create_table('users')
    create_table('transactions')


def db_start():
    mysql_login()
    use_database('finance')
    create_finance_tables()

def db_info():
    try:
        print("\nTable: 'users'")
        cursor.execute("DESCRIBE users")
        rows = cursor.fetchall()
        #print(rows)
        for row in rows:
            print(row[0], end = '   ')
        print("\n")
        cursor.execute("SELECT * FROM users")
        rows = cursor.fetchall()
        #print(rows)
        for row in rows:
           print(row)

        print("\n\nTable: 'transactions'")
        cursor.execute("DESCRIBE transactions")
        rows = cursor.fetchall()
        for row in rows:
            print(row[0], end = '  ')
        print("\n")
        cursor.execute("SELECT * FROM transactions")
        rows = cursor.fetchall()
        for row in rows:
            print(row)
        print("\n")

    except mysql.connector.Error as err:
        print("Error: db_info() {}".format(err), flush=True)          

def db_drop():
    answer = input("Confirm deletion of 'finance' database [Y/N]. ")
    if answer != "Y" and answer != "y":
        print("Nothing done.")
        return
    try:
        cursor.execute("DROP DATABASE finance")
        print("Dropped 'finance' database.")
    except mysql.connector.Error as err:
        print("Error: db_drop() {}".format(err), flush=True)

def db_stop():
    global cnx, cursor
    cursor.close()
    cnx.close()
    print("Logged out of MySQL.", flush=True)


# Fetch user data if any.
def db_select_user(username):
    try:
        # Fetch column names for user table.
        cursor.execute("DESCRIBE users")
        rows = cursor.fetchall()
        columns = []
        for row in rows:
            columns.append(row[0])

        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        rows = cursor.fetchall()
        if rows:
            # Only expecting one table row per user.
            user_data = rows[0]
        else:
            user_data =  []

        # Convert simple list into a list of dictionary structures.
        data_out = {}
        for i in range(len(user_data)):
            data_out[str(columns[i])] = user_data[i]
 
        return data_out

    except mysql.connector.Error as err:
        print("Error: db_select_user(username={}) {}".format(username, err), flush=True)
        user_data = []
    return user_data

# Check user's cash balance.
def db_select_cash(id):
    cursor.execute("SELECT cash FROM users WHERE id=%s", (id,))
    rows = cursor.fetchall()
    if rows:
        cash = float(rows[0][0])  
    else:
        print("Error: db_select_cash(id={})".format(id), flush=True)
        cash = 0
    return cash

# Update user's cash balance.
def db_update_cash(id, cash):
    try:
        cursor.execute("UPDATE users SET cash=%s WHERE id=%s", (cash, id))
        cnx.commit()
        error = 0
    except mysql.connector.Error as err:
        print("Error: db_update_cash(id={}, cash={}) {}".format(id, cash, err), flush=True)
        error = -1
    return error

# Insert new user into users table, automatically creating user id.
def db_insert_user(username, hash, cash):
    try:
        add_user = ("INSERT INTO users "
                    "(username, hash, cash) "
                    "VALUES (%s, %s, %s)")
        data_user = (username, hash, cash)
        cursor.execute(add_user, data_user)
        cnx.commit()
        # Query database for user ID
        cursor.execute("SELECT id, username FROM users WHERE username = %s", (username,))
        rows = cursor.fetchall()
        id = rows[0][0]
        return id
    except mysql.connector.Error as err:
        print("Error: db_insert_user(username={}, hash={}, cash={}) {}".format(username, hash, cash, err), flush=True)
        return -1


# Insert purchase or sale into transactions table.
def db_insert_transaction(id, symbol, price, shares):
    try:
        now = datetime.now()
        add_transaction = ("INSERT INTO transactions "
                           "(id, symbol, price, shares, datetime) "
                           "VALUES(%s, %s, %s, %s, %s)")
        data_transaction = (id, symbol, price, shares, now)
        cursor.execute(add_transaction, data_transaction)
        cnx.commit()
        return 0
    except mysql.connector.Error as err:
        print("Error: db_insert_transaction(id={}, symbol={}, price={}, shares={}) {}".format(id, symbol, price, shares, err), flush=True)
        return -1

# Fetch a list of all this user's transactions
def db_select_transactions(id):
    try:
        # Fetch column names.
        cursor.execute("DESCRIBE transactions")
        rows = cursor.fetchall()
        columns = []
        for row in rows:
            columns.append(row[0])
 
        # Query database for all this user's transactions
        cursor.execute("SELECT * FROM transactions WHERE id=%s ORDER BY datetime DESC", (id,))
        rows = cursor.fetchall() 

        # Convert simple list into a list of dictionary structures.
        rows_out = []
        for row in rows:
            row_out = {}
            for i in range(len(columns)):
                row_out[str(columns[i])] = row[i]
            rows_out.append(row_out)    
        return rows_out

    except mysql.connector.Error as err:
        print("Error: db_select_transaction(id={}) {}".format(id, err), flush=True)
        return []

# Fetch the stock symbols and number of shares for the current user.
def db_select_all_stocks(id):
    try:
        # Fetch total holdings for each stock held by the user.
        cursor.execute("SELECT symbol, SUM(shares) FROM transactions WHERE id=%s GROUP BY symbol HAVING SUM(shares)>0", (id,))
        rows = cursor.fetchall()

        # Convert simple list into a list of dictionary structures.
        rows_out = []
        for row in rows:
            row_out = {"symbol": row[0], "shares": int(row[1])}
            rows_out.append(row_out)    
        return rows_out

    except mysql.connector.Error as err:
        print("Error: db_select_all_stocks(id={}) {}".format(id, err), flush=True)
        return []

# Fetch the number of shares held for the current user and given stock symbol.
def db_select_stock(id, symbol):
    try:
        cursor.execute("SELECT SUM(shares) FROM transactions WHERE id=%s AND symbol=%s GROUP BY symbol", (id, symbol))
        rows = cursor.fetchall()
        # print(rows, flush=True)
        if rows:
            holding = int(rows[0][0])
            return holding
        
    except mysql.connector.Error as err:
        print("Error: db_select_stock(id={}, symbol=()) {}".format(id, symbol, err), flush=True)
    return 0