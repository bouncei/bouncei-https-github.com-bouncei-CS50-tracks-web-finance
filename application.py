import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

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

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # Query database for transaction's symbol, name, shares and cash made by current user
    rows = db.execute("SELECT symbol, name, shares FROM portfolio WHERE users_id = :users_id", users_id=session["user_id"])
    cash = db.execute("SELECT cash FROM users WHERE id = :idSession", idSession=session["user_id"])
    cashAvailable = cash[0]["cash"]

    # Loop to build an array with real time share price
    realTimePrice = []
    for row in rows:
        response = lookup(row["symbol"])
        realTimePrice.append(response["price"])

    # Loop to build an array with real time total share price
    realTimeTotalShares = []
    for row, price in zip(rows, realTimePrice):
        totalShares = row["shares"] * price
        realTimeTotalShares.append(totalShares)

    totalInvestment = cashAvailable + sum(realTimeTotalShares)

    return render_template("index.html", rows=rows, cashAvailable=cashAvailable,
        realTimePrice=realTimePrice,
        realTimeTotalShares=realTimeTotalShares,
        totalInvestment=totalInvestment)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        # Get response from api
        response = lookup(request.form.get("symbol"))

        # Make sure the symbol is correct
        if not response:
            return apology("Symbol doesn't exist!", 403)

        # Query database for cash available
        cash = db.execute("SELECT cash FROM users WHERE id = :idSession", idSession=session["user_id"])
        cashAvailable = cash[0]["cash"]

        # Check if user has enough cash to perform buy action
        if cashAvailable < (response["price"] * int(request.form.get("shares"))):
            return apology("Insufficient cash available!", 409)

        # Insert current buy data into history database
        shares = int(request.form.get("shares"))
        price = response["price"]
        total = price * shares
        db.execute("INSERT INTO history (users_id, symbol, name, shares, price, total) VALUES (:users_id, :symbol, :name, :shares, :price, :total)",
            users_id=session["user_id"],
            symbol=response["symbol"],
            name=response["name"],
            shares=shares,
            price=price,
            total=total)

        # Update current buy data into portfolio database
        rows = db.execute("SELECT * FROM portfolio WHERE users_id = :users_id AND symbol = :symbol",
            users_id=session["user_id"],
            symbol=response["symbol"])
        if not rows:
            db.execute("INSERT INTO portfolio (users_id, symbol, name, shares) VALUES (:users_id, :symbol, :name, :shares)",
                users_id=session["user_id"],
                symbol=response["symbol"],
                name=response["name"],
                shares=shares)
        else:
            oldShares = db.execute("SELECT shares FROM portfolio WHERE users_id = :users_id AND symbol = :symbol",
                users_id=session["user_id"],
                symbol=response["symbol"])
            oldShares = oldShares[0]["shares"]
            newShares = oldShares + shares
            db.execute("UPDATE portfolio SET shares = :newShares WHERE users_id = :users_id AND symbol = :symbol",
                newShares=newShares,
                users_id=session["user_id"],
                symbol=response["symbol"])

        # Update total cash in account
        cashAvailable = cashAvailable - total
        db.execute("UPDATE users SET cash = :cashAvailable WHERE id = :idSession",
            cashAvailable=cashAvailable,
            idSession=session["user_id"])

        # Return user to home page
        flash("Bought!")
        return redirect("/")
    else:
        # Check if user has clicked buy button from navbar or from index page button to buy more of specific share
        # and send the symbol to HTML for autocompletion
        if not request.args.get("symbol"):
            return render_template("buy.html", sentSymbol=None)
        else:
            sentSymbol = request.args.get("symbol")
            return render_template("buy.html", sentSymbol=sentSymbol)


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    # Query database for history of all transactions
    rows = db.execute("SELECT * FROM history WHERE users_id = :users_id", users_id=session["user_id"])
    return render_template("history.html", rows=rows)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

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
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        # Get response from api
        response = lookup(request.form.get("symbol"))

        # Make sure the symbol is correct
        if not response:
            return apology("Symbol doesn't exist!", 403)
        else:
            return render_template("quoted.html", companyName=response["name"], price=response["price"], symbol=response["symbol"])
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        # Ensure the password and confirmation match
        if request.form.get("confirmation") != request.form.get("password"):
            return apology("Incorrect and/or missing confirmation", 403)

        # Query database for username
        row = db.execute("SELECT * FROM users WHERE username = :username", username = request.form.get("username"))

        # Ensure the username don't already exists
        if len(row) != 0:
            return apology("Username already taken!", 409)

        # Register the new user in database
        username = request.form.get("username")
        password = generate_password_hash(request.form.get("password"))
        db.execute("INSERT INTO users (username, hash) VALUES (:username, :password)", username=username, password=password)
        flash("Registered!")
        return redirect("/")
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        # Check if the user have any shares of requested symbol
        rows = db.execute("SELECT symbol FROM portfolio WHERE users_id = :users_id AND symbol = :symbol", users_id=session["user_id"], symbol=request.form.get("symbol"))
        if not rows:
            return apology("You don't own any share of that stock", 403)

        # Check if user have that many shares of selected symbol
        shares = db.execute("SELECT shares FROM portfolio WHERE users_id = :users_id AND symbol = :symbol", users_id=session["user_id"], symbol=request.form.get("symbol"))
        sharesBought = shares[0]["shares"]
        if int(request.form.get("shares")) > sharesBought:
            return apology(f"You only own {sharesBought} share(s) of that stock", 403)

        # Get response from api
        response = lookup(request.form.get("symbol"))

        # Insert current sell into history database
        sharesToSell = -int(request.form.get("shares"))
        price = response["price"]
        total = price * -sharesToSell
        db.execute("INSERT INTO history (users_id, symbol, name, shares, price, total) VALUES (:users_id, :symbol, :name, :shares, :price, :total)",
            users_id=session["user_id"],
            symbol=response["symbol"],
            name=response["name"],
            shares=sharesToSell,
            price=price,
            total=total)

        # Update current sell data into portfolio database
        newShares = sharesBought + sharesToSell # sharesToSell is already negative
        if newShares == 0:
            db.execute("DELETE FROM portfolio WHERE users_id = :users_id AND symbol = :symbol",
                users_id=session["user_id"],
                symbol=response["symbol"])
        else:
            db.execute("UPDATE portfolio SET shares = :newShares WHERE users_id = :users_id AND symbol = :symbol",
                newShares=newShares,
                users_id=session["user_id"],
                symbol=response["symbol"])

        # Update total cash in account
        cash = db.execute("SELECT cash FROM users WHERE id = :users_id", users_id=session["user_id"])
        cashAvailable = cash[0]["cash"]
        newCash = cashAvailable + total
        db.execute("UPDATE users SET cash = :newCash WHERE id = :users_id",
            newCash=newCash,
            users_id=session["user_id"])

        # Return user to index page
        flash("Sold!")
        return redirect("/")
    else:
        # Check if user has clicked sell button from navbar or from index page button to sell more of specific share
        # and send the symbol to HTML for autocompletion
        if not request.args.get("symbol"):
            rows = db.execute("SELECT DISTINCT symbol FROM portfolio WHERE users_id = :users_id", users_id=session["user_id"])
            return render_template("sell.html", rows=rows, sentSymbol=None)
        else:
            rows = db.execute("SELECT DISTINCT symbol FROM portfolio WHERE users_id = :users_id", users_id=session["user_id"])
            sentSymbol = request.args.get("symbol")
            rows.remove({"symbol":sentSymbol})
            return render_template("sell.html", rows=rows, sentSymbol=sentSymbol)

@app.route("/changepassword", methods=["GET", "POST"])
@login_required
def change():
    if request.method == 'GET':
        return render_template("change_password.html")
    else:
        old_password = request.form.get("old-password")
        users = db.execute("SELECT hash FROM users WHERE id = ?", session["user_id"])
        correct_password_hash = users[0]["hash"]

        new_password = request.form.get("newpassword")
        confirm_password = request.form.get("confirm_password")
        new_password_hash = generate_password_hash(new_password)

        if check_password_hash(correct_password_hash, old_password) and new_password == confirm_password:
            db.execute("UPDATE users SET hash = ? WHERE id = ?", new_password_hash, session["user_id"])
            return redirect("/login")
        else:
            return apology("Passwords don't match")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
