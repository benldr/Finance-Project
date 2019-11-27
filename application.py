import os
import Bens_environment_variables # ie passwords etc to be kept secret

#from cs50 import SQL
#from flaskext.mysql import MySQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd
from dbcmds import db_start, db_stop, db_insert_user, db_select_user, db_select_cash, db_update_cash, db_select_stock, db_select_all_stocks, db_insert_transaction, db_select_transactions

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Create the MySQL connection and cursor
db_start()

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")

# Global variable used to replace @login_required flask decorator which is broken ATM.
logged_in = False

@app.route("/")
#@login_required
def index():
    """Show portfolio of stocks"""
    if not logged_in:
         return redirect("/login")

    id = session["user_id"]
    # Determine spare cash available
    cash = db_select_cash(id)

    # Calculate number of shares per each symbol (only for symbols for which more than zero shares are owned)
    symbols_with_stock = db_select_all_stocks(id)

    list_of_totals = []

    for item in symbols_with_stock:
        # Retrieve data from API and return apology if not available.
        symbol_data=lookup(item["symbol"])
        if symbol_data == None:
            return apology("Could not retrieve data from IEX", 500)

        # Create new keys
        item["name"]=symbol_data["name"]
        item["price"]=symbol_data["price"]
        item["total"]=item["price"]*item["shares"]

        list_of_totals.append(item["total"])

    grand_total = sum(list_of_totals)+cash

    return render_template("index.html", cash=cash, symbols_with_stock=symbols_with_stock, grand_total=grand_total)


@app.route("/buy", methods=["GET", "POST"])
#@login_required
def buy():
    """Buy shares of stock"""
    if not logged_in:
         return redirect("/login")

    if request.method == "GET":
        return render_template("buy.html")
    else:
        shares = request.form.get("shares")
        # Return apology if shares box left empty
        if not shares:
            return apology("Number of shares must be specified")
        shares = int(shares)

        symbol = request.form.get("symbol")
        if not symbol:
            return apology("Must select a symbol")
        symbol = symbol.upper()
        symbol_data = lookup(symbol)
        if not symbol_data:
            return apology("Could not retrieve data from IEX")

        id = session["user_id"]
        price = symbol_data["price"]

        # Query database for cash
        cash = db_select_cash(id)
        resulting_cash = cash - price * shares

        if resulting_cash < 0:  # nb this assumes the cash column is available cash for spending so ensure i make this the case
            return apology("Insufficient Funds")

        # Add purchase to database
        db_update_cash(id, resulting_cash)
        db_insert_transaction(id, symbol, price, shares)

        flash("Successfully bought.")
        return redirect("/")


@app.route("/check", methods=["GET"])
def check():
    """Return true if username available, else false, in JSON format"""
    requested_username = request.args.get("username")

    row_with_requested_username = db_select_user(requested_username)

    if row_with_requested_username:
        username_available = False
    else:
        username_available = True
    return jsonify(username_available)


@app.route("/history")
#@login_required
def history():
    """Show history of transactions"""
    if not logged_in:
         return redirect("/login")

    transaction_info = db_select_transactions(session["user_id"])

    return render_template("history.html", transaction_info=transaction_info)


@app.route("/login", methods=["GET", "POST"])
def login():
    global logged_in
    """Log user in"""
    #print(session["user_id"])

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        data = db_select_user(request.form.get("username"))
        print(data)

        # Ensure username exists and password is correct
        if not data or not check_password_hash(data["hash"], request.form.get("password")):
            print("invalid username and/or password", flush=True)
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = data["id"]
        logged_in = True
        print("Logged in", flush=True)

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""
    global logged_in

    # Forget any user_id
    session.clear()

    logged_in = False

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
#@login_required
def quote():
    """Get stock quote."""
    if not logged_in:
         return redirect("/login")

    if request.method == "GET":
        return render_template("quote.html")
    else:
        symbol = request.form.get("symbol")
        if not symbol:
            return apology("Must select a symbol")
        symbol = symbol.upper()
        symbol_data = lookup(symbol)
        if not symbol_data:
            return apology("Could not retrieve data from IEX")

        return render_template("quoted.html", symbol_data=symbol_data)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    global logged_in

    if request.method == "GET":
        return render_template("register.html")
    else:
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        if not username or not password or not confirmation:
            return apology("All form fields must be completed.")

        elif password != confirmation:
            return apology("Password and repeated password do not match")

        # Check if username has been taken already (command will return an empty list aka false if no username exists)
        elif db_select_user(username):
            return apology("Username already taken")

        # Register user
        else:
            # Hash password
            hashed_password = generate_password_hash(password)

            # Add registration info to database
            try:
                cash = 10000.00
                primary_key_of_new_member = db_insert_user(username, hashed_password, cash)
            except RuntimeError:
                return apology("Could not add registration info to database", 500)

            # Remember which user has logged in
            session["user_id"] = primary_key_of_new_member

            logged_in = True

            flash("Successfully registered.")
            return redirect("/")


@app.route("/sell", methods=["GET", "POST"])
#@login_required
def sell():
    """Sell shares of stock"""
    if not logged_in:
         return redirect("/login")

    id=session["user_id"]
    if request.method == "GET":
        symbols_with_stock = db_select_all_stocks(id)
        return render_template("sell.html", symbols_with_stock=symbols_with_stock)
    else:
        symbol = request.form.get("symbol")
        if not symbol:
            return apology("Must select a symbol")
        symbol = symbol.upper()
        symbol_data = lookup(symbol)
        if not symbol_data:
            return apology("Could not retrieve data from IEX")

        shares_being_sold = request.form.get("shares")
        # Return apology if shares box left empty
        if not shares_being_sold:
            return apology("Number of shares must be specified")
        shares_being_sold = int(shares_being_sold)

        # Query database for number of shares held
        shares_owned = db_select_stock(id, symbol)
        # Return apology if currently have no shares for the symbol (not sure how this could happen) or if selling more shares than owned
        if (shares_owned < 1) or (shares_being_sold - shares_owned > 0):
            return apology("Selling more shares than shares owned")

        # Calculate resulting cash following sale
        cash = db_select_cash(id)
        resulting_cash = cash + symbol_data["price"]*shares_being_sold

        # Add sale to database
        db_update_cash(id, resulting_cash)

        db_insert_transaction(id, symbol, symbol_data["price"], -shares_being_sold)

        flash("Successfully sold.")
        return redirect("/")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = ServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)

# Run flask
app.run()