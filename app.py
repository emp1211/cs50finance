import os
import logging

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# /////// INDEX (I.E. PORTFOLIO VIEW) ////////


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    transactions = "transactions_" + str(session["user_id"])
    holdings = "holdings_" + str(session["user_id"])

    portfolio = db.execute("SELECT * FROM ?", holdings)

    # Populate a list with all the stocks a user purchased
    stocks = []
    companies = []
    shares = []
    prices = []
    positions = []
    totalvalue = 0

    # Build the data for the portfolio: stock, shares, current_price, total_value
    for i in portfolio:
        stocks.append(i['stock'])  # Add ticker symbol from portfolio to list stocks
        tmpname = i['stock']  # Store ticker symbol
        shares.append(i['shares'])  # Add no. of shares from portfolio to list shares
        tmpshares = i['shares']  # Store no. of shares of current stock
        tmp = lookup(tmpname)  # Get quote of current stock in loop
        prices.append(tmp['price'])  # Add current price of current stock to list prices
        tmpprice = tmp['price']  # Store current market price of stock
        company = tmp['name']  # Store company name
        companies.append(company)  # Append to companies list
        tmpvalue = float(tmpshares) * tmpprice  # Calculate total value of current stock position
        totalvalue += tmpvalue  # Tally total account value each iteration of loop
        # Return a pseudo-object with table data for portfolio
        obj = {"symbol": tmpname, "company": company, "shares": tmpshares, "price": tmpprice, "value": tmpvalue}
        positions.append(obj)  # Append portfolio table data to list positions

    # Get users's cash from users table cash column
    cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
    tmpcash = cash[0]['cash']

    total = tmpcash + totalvalue

    return render_template("index.html", positions=positions, cash=tmpcash, total=total)


# //////////// BUY ////////////////


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "GET":
        return render_template("buy.html")

    elif request.method == "POST":

        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("must provide stock symbol", 400)

        # Ensure number of shares was submitted
        if not request.form.get("shares"):
            return apology("must provide number of shares", 400)

        # Check if user inputed text characters into shares field
        try:
            fl_shares = float(request.form.get("shares"))
        except ValueError:
            return apology("Must enter numeric characters for shares", 400)

        if fl_shares.is_integer() == False or fl_shares < 1:
            return apology("number of shares must be positive integer", 400)

        if lookup(request.form.get("symbol")) == None:
            return apology("invalid stock symbol", 400)

        # Get price from IEX API
        stockquote = lookup(request.form.get("symbol"))
        stockprice = stockquote['price']

        # Get number of shares from form input, cast as float
        #sharestype = type(request.form.get("shares"))
        shares = float(request.form.get("shares"))
        #str_shares = request.form.get("shares")

        # Get stock symbol from form input
        symbol = request.form.get("symbol").upper()

        # Calculate total cost of transaction
        totalpurchase = shares * stockprice

        # Set transaction type as variable
        buy = "buy"

        # Specify the name of user's transactions table as variable
        transactions = "transactions_" + str(session["user_id"])
        holdings = "holdings_" + str(session["user_id"])

        # Reset account balance from table users
        tmp = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
        balance = tmp[0].get('cash')

        if balance - totalpurchase > 0:
            newbalance = balance - totalpurchase
            db.execute("UPDATE users SET cash = ? WHERE id = ?", newbalance, session["user_id"])
            date = datetime.now()
            db.execute("INSERT INTO ? (transaction_type, symbol, cost_basis, shares, total, transaction_date) VALUES(?, ?, ?, ?, ?, ?)",
                       transactions, buy, symbol, stockprice, shares, totalpurchase, date)

            # Query holdings table
            stock_rows = db.execute("SELECT * FROM ? WHERE stock = ?", holdings, symbol)

            # If stock not owned: update holdings table with new purchase info
            if len(stock_rows) == 0:
                db.execute("INSERT INTO ? (stock, shares) VALUES(?, ?)", holdings, symbol, shares)

            # If stock already in portfolio: update number of shares for that particular stock in holdings_id table
            else:
                previous_shares = float(stock_rows[0]['shares'])
                total_shares = previous_shares + shares
                db.execute("UPDATE ? SET shares = ? WHERE stock = ?", holdings, total_shares, symbol)

        else:

            return apology("Request denied, transaction exceeds account balance", 400)

        flash("Bought!")
        return redirect("/")


# /////// HISTORY OF TRANSACTIONS ////////


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    transaction_info = []
    share_totals = []
    transactions = "transactions_" + str(session["user_id"])
    history = db.execute("SELECT * FROM ?", transactions)
    i = 0
    for row in history:
        if row['transaction_type'] == 'sell':
            negative_shares = row['shares'] * -1
            share_totals.append(negative_shares)
        else:
            share_totals.append(row['shares'])
        tmp_symbol = row.get('symbol')
        tmp_shares = share_totals[i]
        tmp_price = row.get('cost_basis')
        transacted = row['transaction_date']
        obj = {'symbol': tmp_symbol, 'shares': tmp_shares, 'price': tmp_price, 'transacted': transacted}
        transaction_info.append(obj)
        i += 1

    return render_template("history.html", transaction_info=transaction_info)


# /////// LOGIN ////////


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 400)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


# /////// LOGOUT ////////


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


# /////// QUOTE ////////


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    if request.method == "GET":
        return render_template("quote.html")

    elif request.method == "POST":

        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("must provide stock symbol", 400)

        # Ensures stock symbol is valid
        elif lookup(request.form.get("symbol")) == None:
            return apology("invalid stock symbol", 400)

        quoted = lookup(request.form.get("symbol"))
        return render_template("quoted.html", quoted=quoted)


# /////// REGISTER ////////


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "GET":
        return render_template("register.html")

    elif request.method == "POST":

        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Ensure password was confirmed
        elif not request.form.get("confirmation"):
            return apology("must confirm password", 400)

        # Get user input from register.html form
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # Query database for proposed username
        rows = db.execute("SELECT * FROM users WHERE username = ?", username)

        # Ensure username does not already exist
        if len(rows) != 0:
            return apology("username already taken", 400)

        # Confirm password
        if password != confirmation:
            return apology("passwords must match", 400)

        # Insert new user into table
        db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", username, generate_password_hash(password))

        # Log user in and create their two unique tables: transactions_id and holdings_id
        rows = db.execute("SELECT * FROM users WHERE username = ?", username)
        session["user_id"] = rows[0]["id"]
        tablename = "transactions_" + str(session["user_id"])
        tablename2 = "holdings_" + str(session["user_id"])
        db.execute("CREATE TABLE ? (transaction_no INTEGER PRIMARY KEY, transaction_type TEXT NOT NULL, symbol TEXT NOT NULL, cost_basis FLOAT NOT NULL, shares FLOAT NOT NULL, total FLOAT NOT NULL, transaction_date TEXT NOT NULL)", tablename)
        db.execute("CREATE TABLE ? (stock TEXT NOT NULL, shares FLOAT NOT NULL)", tablename2)

        flash("Registered!")
        return redirect("/")


# /////// SELL ////////


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    holdings = "holdings_" + str(session["user_id"])
    transactions = "transactions_" + str(session["user_id"])
    portfolio = db.execute("SELECT * FROM ?", holdings)
    stocks = []
    for row in portfolio:
        stocks.append(row['stock'])

    if request.method == "GET":
        return render_template("sell.html", stocks=stocks)

    elif request.method == "POST":
        sell = "sell"

        if not request.form.get("symbol"):
            return apology("Must enter a stock symbol", 400)

        if not request.form.get("shares"):
            return apology("Must enter number of shares", 400)

        # Check if user inputed text characters into shares field
        try:
            fl_shares = float(request.form.get("shares"))
        except ValueError:
            return apology("Must enter numeric characters for shares", 400)

        if fl_shares.is_integer() == False or fl_shares < 1:
            return apology("number of shares must be positive integer", 400)

        if lookup(request.form.get("symbol")) == None:
            return apology("invalid stock symbol", 400)

        if request.form.get("symbol") not in stocks:
            return apology("Not owned in portfolio", 400)
        elif request.form.get("symbol") in stocks:
            stock_to_sell = request.form.get("symbol")
            shares_to_sell = float(request.form.get("shares"))
            shares_dict = db.execute("SELECT shares FROM ? WHERE stock = ?", holdings, stock_to_sell)
            shares_owned = shares_dict[0]['shares']

            if shares_owned >= shares_to_sell:
                updated_shares = shares_owned - shares_to_sell
                db.execute("UPDATE ? SET shares = ? WHERE stock = ?", holdings, updated_shares, stock_to_sell)
                if updated_shares == 0:
                    db.execute("DELETE FROM ? WHERE shares = 0", holdings)

                # Get stock quote from IEX
                stockquote = lookup(stock_to_sell)
                stockprice = stockquote['price']
                total_sale = shares_to_sell * stockprice

                # Get cash balance from table users 'cash' column
                tmp = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
                balance = tmp[0].get('cash')
                new_balance = balance + total_sale

                date = datetime.now()
                db.execute("INSERT INTO ? (transaction_type, symbol, cost_basis, shares, total, transaction_date) VALUES(?, ?, ?, ?, ?, ?)",
                           transactions, sell, stock_to_sell, stockprice, shares_to_sell, total_sale, date)

                # Update cash balance in users table
                db.execute("UPDATE users SET cash = ?", new_balance)
            else:
                return apology("More shares to sell than owned", 400)

        flash("Sold!")
        return redirect("/")


# ////////// MAKE CONTRIBUTION TO ACCOUNT //////////


@app.route("/contribute", methods=["GET", "POST"])
def contribute():
    """Add cash too account"""

    if request.method == "GET":
        return render_template("contribute.html")

    if request.method == "POST":
        # Ensure symbol was submitted
        if not request.form.get("cash"):
            return apology("Must enter amount of cash to add", 400)

        # Check if user inputed text characters into shares field
        try:
            amount = float(request.form.get("cash"))
        except ValueError:
            return apology("Must enter numeric characters for amount to contribute", 400)

        if not amount > 0:
            return apology("Must enter positive number", 400)

        # Get current cash balance from users table
        row = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
        cash_balance = row[0]['cash']

        # Add new cash contribution to current balance
        updated_cash = cash_balance + amount

        # Update cash balance in users table
        db.execute("UPDATE users SET cash = ? WHERE id = ?", updated_cash, session["user_id"])

        # Flash message and redirect to index/portfolio
        flash("Cash added!")
        return redirect("/")