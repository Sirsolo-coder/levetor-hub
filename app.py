from flask import ( # type: ignore
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    jsonify
)

from database import init_db, get_db  # type: ignore

import os
import uuid
import secrets
import json
import requests # type: ignore
from dotenv import load_dotenv # type: ignore
from datetime import datetime, timedelta

from werkzeug.security import ( # type: ignore
    generate_password_hash,
    check_password_hash
)  # type: ignore

from werkzeug.utils import secure_filename  # type: ignore

from flask_cors import CORS # type: ignore
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired # type: ignore
from google.oauth2 import id_token  # type: ignore
from google.auth.transport import requests as google_requests  # type: ignore
from firebase_notifications import send_customer_notification
# =========================================================
# PAYSTACK CONFIGURATION
# =========================================================

load_dotenv()

PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
PAYSTACK_PUBLIC_KEY = os.getenv("PAYSTACK_PUBLIC_KEY")

PAYSTACK_BASE_URL = "https://api.paystack.co"
# =========================================================
# GOOGLE AUTHENTICATION CONFIGURATION
# =========================================================

GOOGLE_WEB_CLIENT_ID = os.getenv(
    "GOOGLE_WEB_CLIENT_ID"
)

# =========================================================
# FLASK APPLICATION
# =========================================================

app = Flask(__name__)

CORS(app)


# =========================================================
# SECRET KEY
# =========================================================

app.secret_key = os.getenv("FLASK_SECRET_KEY") or "levetor-hub-secret-key"

# =========================================================
# MOBILE API TOKEN AUTHENTICATION
# =========================================================

API_TOKEN_MAX_AGE = int(os.getenv("API_TOKEN_MAX_AGE", str(60 * 60 * 24 * 30)))
api_token_serializer = URLSafeTimedSerializer(
    app.secret_key,
    salt="levetor-hub-mobile-api"
)


def create_api_token(customer_id):
    return api_token_serializer.dumps({"customer_id": int(customer_id)})


def get_bearer_customer_id():
    authorization = request.headers.get("Authorization", "").strip()

    if not authorization.lower().startswith("bearer "):
        return None

    token = authorization[7:].strip()

    if not token:
        return None

    try:
        data = api_token_serializer.loads(
            token,
            max_age=API_TOKEN_MAX_AGE
        )
        return int(data["customer_id"])
    except (BadSignature, SignatureExpired, KeyError, TypeError, ValueError):
        return None


def require_customer(customer_id):
    authenticated_customer_id = get_bearer_customer_id()

    if authenticated_customer_id is None:
        return jsonify({
            "success": False,
            "message": "Authentication required. Please login again."
        }), 401

    try:
        requested_customer_id = int(customer_id)
    except (TypeError, ValueError):
        return jsonify({
            "success": False,
            "message": "Invalid customer ID."
        }), 400

    if authenticated_customer_id != requested_customer_id:
        return jsonify({
            "success": False,
            "message": "You are not authorized to access this account."
        }), 403

    return None



# =========================================================
# IMAGE UPLOAD SETTINGS
# =========================================================

UPLOAD_FOLDER = os.path.join(
    app.root_path,
    "static",
    "uploads"
)

ALLOWED_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg",
    "webp"
}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)


def allowed_file(filename):

    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in ALLOWED_EXTENSIONS
    )


# =========================================================
# ADMIN ACCESS CHECK
# =========================================================

def admin_required():

    if not session.get("is_admin"):

        flash(
            "Please login as administrator first.",
            "danger"
        )

        return False

    return True


# =========================================================
# INITIALIZE DATABASE
# =========================================================

init_db()


# =========================================================
# HOME PAGE
# =========================================================

@app.route("/")
def home():

    conn = get_db()

    products = conn.execute("""
        SELECT *
        FROM products
        ORDER BY created_at DESC
    """).fetchall()

    conn.close()

    return render_template(
        "index.html",
        products=products
    )


# =========================================================
# MOBILE APP - GET ALL PRODUCTS
# =========================================================
@app.route("/api/health")
def api_health():
    return jsonify({
        "success": True,
        "message": "Levetor Hub API is running."
    })
@app.route("/api/products", methods=["GET"])
def api_products():

    conn = get_db()

    products = conn.execute("""
        SELECT
            id,
            name,
            category,
            brand,
            model,
            description,
            price,
            stock,
            image,
            condition,
            warranty,
            created_at
        FROM products
        ORDER BY created_at DESC
    """).fetchall()

    conn.close()

    products_list = []

    for product in products:

        products_list.append({
            "id": product["id"],
            "name": product["name"],
            "category": product["category"],
            "brand": product["brand"],
            "model": product["model"],
            "description": product["description"],
            "price": product["price"],
            "stock": product["stock"],
            "image": product["image"],
            "condition": product["condition"],
            "warranty": product["warranty"],
            "created_at": product["created_at"]
        })

    return jsonify(products_list)


# =========================================================
# MOBILE APP - GET SINGLE PRODUCT
# =========================================================

@app.route(
    "/api/products/<int:product_id>",
    methods=["GET"]
)
def api_product_details(product_id):

    conn = get_db()

    product = conn.execute("""
        SELECT *
        FROM products
        WHERE id = ?
    """, (
        product_id,
    )).fetchone()

    conn.close()

    if product is None:

        return jsonify({
            "success": False,
            "error": "Product not found"
        }), 404

    return jsonify({
        "success": True,
        "product": {
            "id": product["id"],
            "name": product["name"],
            "category": product["category"],
            "brand": product["brand"],
            "model": product["model"],
            "description": product["description"],
            "price": product["price"],
            "stock": product["stock"],
            "image": product["image"],
            "condition": product["condition"],
            "warranty": product["warranty"],
            "created_at": product["created_at"]
        }
    })


# =========================================================
# SHOP PAGE
# =========================================================

@app.route("/shop")
def shop():

    search = request.args.get(
        "search",
        ""
    ).strip()

    category = request.args.get(
        "category",
        ""
    ).strip()

    conn = get_db()

    query = """
        SELECT *
        FROM products
        WHERE 1=1
    """

    params = []

    # CATEGORY FILTER

    if category:

        query += """
            AND category = ?
        """

        params.append(category)

    # SEARCH FILTER

    if search:

        query += """
            AND (
                name LIKE ?
                OR brand LIKE ?
                OR model LIKE ?
                OR description LIKE ?
            )
        """

        search_term = f"%{search}%"

        params.extend([
            search_term,
            search_term,
            search_term,
            search_term
        ])

    query += """
        ORDER BY created_at DESC
    """

    products = conn.execute(
        query,
        params
    ).fetchall()

    conn.close()

    return render_template(
        "products.html",
        products=products
    )


# =========================================================
# ADMIN LOGIN
# =========================================================

@app.route(
    "/admin/login",
    methods=["GET", "POST"]
)
def admin_login():

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        ).strip()

        # Admin credentials are loaded from environment variables.
        admin_username = os.getenv("ADMIN_USERNAME", "admin")
        admin_password = os.getenv("ADMIN_PASSWORD")

        if (
            admin_password
            and username == admin_username
            and password == admin_password
        ):

            session["is_admin"] = True

            flash(
                "Welcome to Levetor Hub Admin Dashboard.",
                "success"
            )

            return redirect(
                url_for("admin")
            )

        flash(
            "Invalid username or password.",
            "danger"
        )

    return render_template(
        "admin/login.html"
    )


# =========================================================
# ADMIN LOGOUT
# =========================================================

@app.route("/admin/logout")
def admin_logout():

    session.pop(
        "is_admin",
        None
    )

    flash(
        "You have been logged out.",
        "success"
    )

    return redirect(
        url_for("home")
    )


# =========================================================
# ADMIN DASHBOARD
# =========================================================

@app.route("/admin")
def admin():

    if "is_admin" not in session:

        flash(
            "You must be an administrator to access this page.",
            "danger"
        )

        return redirect(
            url_for("home")
        )

    conn = get_db()

    # TOTAL PRODUCTS

    product_count = conn.execute("""
        SELECT COUNT(*) AS count
        FROM products
    """).fetchone()["count"]

    # TOTAL ORDERS

    order_count = conn.execute("""
        SELECT COUNT(*) AS count
        FROM orders
    """).fetchone()["count"]

    # TOTAL CUSTOMERS

    customer_count = conn.execute("""
        SELECT COUNT(*) AS count
        FROM customers
    """).fetchone()["count"]

    # TOTAL REVENUE

    revenue = conn.execute("""
        SELECT
            COALESCE(
                SUM(total_amount),
                0
            ) AS total
        FROM orders
        WHERE payment_status = 'Paid'
    """).fetchone()["total"]

    # RECENT ORDERS

    recent_orders = conn.execute("""
        SELECT
            orders.id,
            orders.total_amount,
            orders.payment_status,
            orders.order_status,
            orders.created_at,
            customers.fullname
        FROM orders

        LEFT JOIN customers
        ON orders.customer_id = customers.id

        ORDER BY orders.created_at DESC

        LIMIT 10
    """).fetchall()

    # PRODUCTS

    products = conn.execute("""
        SELECT *
        FROM products
        ORDER BY created_at DESC
    """).fetchall()

    conn.close()

    return render_template(
        "admin/dashboard.html",

        product_count=product_count,
        order_count=order_count,
        customer_count=customer_count,
        revenue=revenue,

        recent_orders=recent_orders,

        products=products
    )


# =========================================================
# ADD PRODUCT
# =========================================================

@app.route(
    "/admin/add-product",
    methods=["GET", "POST"]
)
def add_product():

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        category = request.form.get(
            "category",
            ""
        ).strip()

        brand = request.form.get(
            "brand",
            ""
        ).strip()

        model = request.form.get(
            "model",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        price = request.form.get(
            "price",
            "0"
        ).strip()

        stock = request.form.get(
            "stock",
            "0"
        ).strip()

        condition = request.form.get(
            "condition",
            "New"
        ).strip()

        warranty = request.form.get(
            "warranty",
            ""
        ).strip()

        # VALIDATION

        if not name or not category or not price:

            flash(
                "Product name, category and price are required.",
                "danger"
            )

            return redirect(
                url_for("add_product")
            )

        # CONVERT NUMBERS

        try:

            price = float(price)
            stock = int(stock)

        except ValueError:

            flash(
                "Price and stock must contain valid numbers.",
                "danger"
            )

            return redirect(
                url_for("add_product")
            )

        # IMAGE UPLOAD

        image_filename = None

        image = request.files.get("image")

        if image and image.filename:

            if not allowed_file(
                image.filename
            ):

                flash(
                    "Invalid image format. Use PNG, JPG, JPEG or WEBP.",
                    "danger"
                )

                return redirect(
                    url_for("add_product")
                )

            original_filename = secure_filename(
                image.filename
            )

            extension = original_filename.rsplit(
                ".",
                1
            )[1].lower()

            image_filename = (
                str(uuid.uuid4())
                + "."
                + extension
            )

            image.save(
                os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    image_filename
                )
            )

        # SAVE PRODUCT

        conn = get_db()

        conn.execute("""
            INSERT INTO products
            (
                name,
                category,
                brand,
                model,
                description,
                price,
                stock,
                image,
                condition,
                warranty
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            name,
            category,
            brand,
            model,
            description,
            price,
            stock,
            image_filename,
            condition,
            warranty
        ))

        conn.commit()
        conn.close()

        flash(
            "Product added successfully!",
            "success"
        )

        return redirect(
            url_for("admin")
        )

    return render_template(
        "admin/add_product.html"
    )


# =========================================================
# ADD TO CART
# =========================================================

@app.route(
    "/cart/add/<int:product_id>",
    methods=["POST"]
)
def add_to_cart(product_id):

    conn = get_db()

    product = conn.execute("""
        SELECT *
        FROM products
        WHERE id = ?
    """, (
        product_id,
    )).fetchone()

    conn.close()

    if product is None:

        flash(
            "Product not found.",
            "danger"
        )

        return redirect(
            url_for("shop")
        )

    if product["stock"] <= 0:

        flash(
            "This product is currently out of stock.",
            "danger"
        )

        return redirect(
            url_for(
                "product_details",
                product_id=product_id
            )
        )

    try:

        quantity = int(
            request.form.get(
                "quantity",
                1
            )
        )

    except ValueError:

        quantity = 1

    if quantity < 1:

        quantity = 1

    if quantity > product["stock"]:

        quantity = product["stock"]

    cart = session.get(
        "cart",
        {}
    )

    product_key = str(product_id)

    current_quantity = cart.get(
        product_key,
        0
    )

    new_quantity = (
        current_quantity
        + quantity
    )

    if new_quantity > product["stock"]:

        new_quantity = product["stock"]

    cart[product_key] = new_quantity

    session["cart"] = cart

    session.modified = True

    flash(
        f"{product['name']} added to your cart.",
        "success"
    )

    return redirect(
        url_for("cart")
    )


# =========================================================
# CART
# =========================================================

@app.route("/cart")
def cart():

    cart = session.get(
        "cart",
        {}
    )

    cart_items = []

    total = 0

    conn = get_db()

    for product_id, quantity in cart.items():

        product = conn.execute("""
            SELECT *
            FROM products
            WHERE id = ?
        """, (
            int(product_id),
        )).fetchone()

        if product is None:

            continue

        subtotal = (
            product["price"]
            * quantity
        )

        total += subtotal

        cart_items.append({
            "product": product,
            "quantity": quantity,
            "subtotal": subtotal
        })

    conn.close()

    return render_template(
        "cart.html",
        cart_items=cart_items,
        total=total
    )


# =========================================================
# INCREASE CART QUANTITY
# =========================================================

@app.route(
    "/cart/increase/<int:product_id>"
)
def increase_cart(product_id):

    cart = session.get(
        "cart",
        {}
    )

    product_key = str(product_id)

    if product_key in cart:

        conn = get_db()

        product = conn.execute("""
            SELECT stock
            FROM products
            WHERE id = ?
        """, (
            product_id,
        )).fetchone()

        conn.close()

        if product:

            current_quantity = cart[
                product_key
            ]

            if current_quantity < product["stock"]:

                cart[
                    product_key
                ] = current_quantity + 1

            else:

                flash(
                    "You cannot add more than the available stock.",
                    "warning"
                )

    session["cart"] = cart

    return redirect(
        url_for("cart")
    )


# =========================================================
# DECREASE CART QUANTITY
# =========================================================

@app.route(
    "/cart/decrease/<int:product_id>"
)
def decrease_cart(product_id):

    cart = session.get(
        "cart",
        {}
    )

    product_key = str(product_id)

    if product_key in cart:

        if cart[product_key] > 1:

            cart[product_key] -= 1

    session["cart"] = cart

    return redirect(
        url_for("cart")
    )


# =========================================================
# REMOVE FROM CART
# =========================================================

@app.route(
    "/cart/remove/<int:product_id>",
    methods=["POST"]
)
def remove_from_cart(product_id):

    cart = session.get(
        "cart",
        {}
    )

    product_key = str(product_id)

    if product_key in cart:

        del cart[product_key]

    session["cart"] = cart

    session.modified = True

    flash(
        "Product removed from cart.",
        "success"
    )

    return redirect(
        url_for("cart")
    )


# =========================================================
# PRODUCT DETAILS
# =========================================================

@app.route(
    "/product/<int:product_id>"
)
def product_details(product_id):

    conn = get_db()

    product = conn.execute("""
        SELECT *
        FROM products
        WHERE id = ?
    """, (
        product_id,
    )).fetchone()

    conn.close()

    if product is None:

        return "Product not found", 404

    return render_template(
        "product_details.html",
        product=product
    )


# =========================================================
# MOBILE APP - CUSTOMER REGISTRATION
# =========================================================

@app.route(
    "/api/register",
    methods=["POST"]
)
def api_register():

    data = request.get_json(
        silent=True
    )

    if not data:

        return jsonify({
            "success": False,
            "message": "No registration data received."
        }), 400

    fullname = str(
        data.get(
            "fullname",
            ""
        )
    ).strip()

    email = str(
        data.get(
            "email",
            ""
        )
    ).strip().lower()

    phone = str(
        data.get(
            "phone",
            ""
        )
    ).strip()

    address = str(
        data.get(
            "address",
            ""
        )
    ).strip()

    password = str(
        data.get(
            "password",
            ""
        )
    )

    confirm_password = str(
        data.get(
            "confirm_password",
            data.get(
                "confirmPassword",
                ""
            )
        )
    )

    # VALIDATION

    if not fullname:

        return jsonify({
            "success": False,
            "message": "Full name is required."
        }), 400

    if not email:

        return jsonify({
            "success": False,
            "message": "Email is required."
        }), 400

    if not phone:

        return jsonify({
            "success": False,
            "message": "Phone number is required."
        }), 400

    if not password:

        return jsonify({
            "success": False,
            "message": "Password is required."
        }), 400

    if len(password) < 8:

        return jsonify({
            "success": False,
            "message": "Password must contain at least 8 characters."
        }), 400

    if confirm_password and password != confirm_password:

        return jsonify({
            "success": False,
            "message": "Passwords do not match."
        }), 400

    conn = get_db()

    try:

        existing_customer = conn.execute("""
            SELECT id
            FROM customers
            WHERE email = ?
        """, (
            email,
        )).fetchone()

        if existing_customer:

            conn.close()

            return jsonify({
                "success": False,
                "message": "An account with this email already exists."
            }), 409

        password_hash = generate_password_hash(
            password
        )

        cursor = conn.execute("""
            INSERT INTO customers
            (
                fullname,
                email,
                phone,
                address,
                password_hash
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            fullname,
            email,
            phone,
            address,
            password_hash
        ))

        customer_id = cursor.lastrowid

        conn.commit()
        conn.close()

        return jsonify({
            "success": True,
            "message": "Account created successfully.",
            "customer_id": customer_id,
            "token": create_api_token(customer_id),
            "fullname": fullname,
            "email": email,
            "phone": phone,
            "address": address
        }), 201

    except Exception as e:

        conn.rollback()
        conn.close()

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================================================
# MOBILE APP - CUSTOMER LOGIN
# =========================================================

@app.route(
    "/api/login",
    methods=["POST"]
)
def api_login():

    data = request.get_json(
        silent=True
    )

    if not data:

        return jsonify({
            "success": False,
            "message": "No login data received."
        }), 400

    email = str(
        data.get(
            "email",
            ""
        )
    ).strip().lower()

    password = str(
        data.get(
            "password",
            ""
        )
    )

    if not email or not password:

        return jsonify({
            "success": False,
            "message": "Email and password are required."
        }), 400

    conn = get_db()

    customer = conn.execute("""
        SELECT *
        FROM customers
        WHERE email = ?
    """, (
        email,
    )).fetchone()

    conn.close()

    if customer is None:

        return jsonify({
            "success": False,
            "message": "Invalid email or password."
        }), 401

    password_hash = customer["password_hash"]

    if not password_hash:

        return jsonify({
            "success": False,
            "message": "This account does not have a password."
        }), 401

    if not check_password_hash(
        password_hash,
        password
    ):

        return jsonify({
            "success": False,
            "message": "Invalid email or password."
        }), 401

    return jsonify({
        "success": True,
        "message": "Login successful.",
        "token": create_api_token(customer["id"]),
        "customer": {
            "id": customer["id"],
            "fullname": customer["fullname"],
            "email": customer["email"],
            "phone": customer["phone"],
            "address": customer["address"]
        }
    }), 200

# =========================================================
# MOBILE APP - GOOGLE LOGIN / REGISTRATION
# =========================================================

@app.route(
    "/api/auth/google",
    methods=["POST"]
)
def api_google_auth():

    data = request.get_json(
        silent=True
    )

    if not data:

        return jsonify({
            "success": False,
            "message": "No Google authentication data received."
        }), 400

    google_token = str(
        data.get(
            "id_token",
            ""
        )
    ).strip()

    if not google_token:

        return jsonify({
            "success": False,
            "message": "Google ID token is required."
        }), 400

    if not GOOGLE_WEB_CLIENT_ID:

        return jsonify({
            "success": False,
            "message": (
                "Google authentication is not configured "
                "on the server."
            )
        }), 500

    try:

        # =================================================
        # VERIFY GOOGLE ID TOKEN
        # =================================================

        google_user = id_token.verify_oauth2_token(
            google_token,
            google_requests.Request(),
            GOOGLE_WEB_CLIENT_ID
        )

    except ValueError:

        return jsonify({
            "success": False,
            "message": "Invalid or expired Google account token."
        }), 401

    except Exception:

        return jsonify({
            "success": False,
            "message": "Could not verify your Google account."
        }), 401

    # =====================================================
    # GET VERIFIED GOOGLE INFORMATION
    # =====================================================

    google_id = str(
        google_user.get(
            "sub",
            ""
        )
    ).strip()

    email = str(
        google_user.get(
            "email",
            ""
        )
    ).strip().lower()

    fullname = str(
        google_user.get(
            "name",
            ""
        )
    ).strip()

    email_verified = google_user.get(
        "email_verified",
        False
    )

    if not google_id or not email:

        return jsonify({
            "success": False,
            "message": (
                "Google did not provide the required "
                "account information."
            )
        }), 400

    if not email_verified:

        return jsonify({
            "success": False,
            "message": (
                "Your Google email address "
                "has not been verified."
            )
        }), 400

    if not fullname:

        fullname = email.split("@")[0]

    conn = get_db()

    try:

        # =================================================
        # FIRST: FIND CUSTOMER BY GOOGLE ID
        # =================================================

        customer = conn.execute("""
            SELECT *
            FROM customers
            WHERE google_id = ?
        """, (
            google_id,
        )).fetchone()

        # =================================================
        # IF NOT FOUND, FIND CUSTOMER BY EMAIL
        # =================================================

        if customer is None:

            customer = conn.execute("""
                SELECT *
                FROM customers
                WHERE email = ?
            """, (
                email,
            )).fetchone()

        # =================================================
        # EXISTING CUSTOMER
        # =================================================

        if customer is not None:

            customer_id = customer["id"]

            # Link Google account to existing customer

            conn.execute("""
                UPDATE customers
                SET
                    google_id = ?,
                    auth_provider = ?
                WHERE id = ?
            """, (
                google_id,
                "password_google"
                if customer["password_hash"]
                else "google",
                customer_id
            ))

            conn.commit()

            updated_customer = conn.execute("""
                SELECT
                    id,
                    fullname,
                    email,
                    phone,
                    address
                FROM customers
                WHERE id = ?
            """, (
                customer_id,
            )).fetchone()

            conn.close()

            return jsonify({
                "success": True,
                "message": "Google login successful.",
                "is_new_customer": False,
                "token": create_api_token(customer_id),
                "customer": {
                    "id": updated_customer["id"],
                    "fullname": updated_customer["fullname"],
                    "email": updated_customer["email"],
                    "phone": updated_customer["phone"],
                    "address": updated_customer["address"]
                }
            }), 200

        # =================================================
        # NEW GOOGLE CUSTOMER
        # =================================================

        cursor = conn.execute("""
            INSERT INTO customers
            (
                fullname,
                email,
                phone,
                address,
                password_hash,
                google_id,
                auth_provider
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            fullname,
            email,
            "",
            "",
            None,
            google_id,
            "google"
        ))

        customer_id = cursor.lastrowid

        conn.commit()

        new_customer = conn.execute("""
            SELECT
                id,
                fullname,
                email,
                phone,
                address
            FROM customers
            WHERE id = ?
        """, (
            customer_id,
        )).fetchone()

        conn.close()

        return jsonify({
            "success": True,
            "message": "Google account registered successfully.",
            "is_new_customer": True,
            "token": create_api_token(customer_id),
            "customer": {
                "id": new_customer["id"],
                "fullname": new_customer["fullname"],
                "email": new_customer["email"],
                "phone": new_customer["phone"],
                "address": new_customer["address"]
            }
        }), 201

    except Exception as e:

        conn.rollback()
        conn.close()

        return jsonify({
            "success": False,
            "message": (
                f"Google authentication failed: {str(e)}"
            )
        }), 500
    # =========================================================
# MOBILE APP - FORGOT PASSWORD
# =========================================================

@app.route(
    "/api/forgot-password",
    methods=["POST"]
)
def api_forgot_password():

    data = request.get_json(
        silent=True
    )

    if not data:

        return jsonify({
            "success": False,
            "message": "No password reset data received."
        }), 400

    email = str(
        data.get(
            "email",
            ""
        )
    ).strip().lower()

    if not email:

        return jsonify({
            "success": False,
            "message": "Email address is required."
        }), 400

    conn = get_db()

    customer = conn.execute("""
        SELECT
            id,
            email
        FROM customers
        WHERE email = ?
    """, (
        email,
    )).fetchone()

    if customer is None:

        conn.close()

        return jsonify({
            "success": False,
            "message": (
                "No account was found with that "
                "email address."
            )
        }), 404

    # =====================================================
    # CREATE SECURE RESET TOKEN
    # =====================================================

    reset_token = secrets.token_urlsafe(
        32
    )

    reset_expiry = (
        datetime.now()
        + timedelta(minutes=30)
    )

    conn.execute("""
        UPDATE customers
        SET
            reset_token = ?,
            reset_token_expiry = ?
        WHERE id = ?
    """, (
        reset_token,
        reset_expiry,
        customer["id"]
    ))

    conn.commit()
    conn.close()

    # =====================================================
    # CREATE RESET LINK
    # =====================================================

    reset_link = url_for(
        "reset_password",
        token=reset_token,
        _external=True
    )

    return jsonify({
        "success": True,
        "message": (
            "Password reset link generated successfully."
        ),
        "reset_link": reset_link,
        "expires_in_minutes": 30
    }), 200
# =========================================================
# MOBILE APP - CUSTOMER PROFILE
# =========================================================

@app.route(
    "/api/customers/<int:customer_id>",
    methods=["GET"]
)
def api_get_customer(customer_id):

    auth_error = require_customer(customer_id)

    if auth_error:
        return auth_error

    conn = get_db()

    customer = conn.execute("""
        SELECT
            id,
            fullname,
            email,
            phone,
            address,
            created_at
        FROM customers
        WHERE id = ?
    """, (
        customer_id,
    )).fetchone()

    conn.close()

    if customer is None:

        return jsonify({
            "success": False,
            "message": "Customer not found."
        }), 404

    return jsonify({
        "success": True,
        "customer": {
            "id": customer["id"],
            "fullname": customer["fullname"],
            "email": customer["email"],
            "phone": customer["phone"],
            "address": customer["address"],
            "created_at": customer["created_at"]
        }
    })


# =========================================================
# MOBILE APP - CREATE ORDER API
# =========================================================
# =========================================================
# MOBILE APP - UPDATE CUSTOMER PROFILE
# =========================================================

@app.route(
    "/api/customers/<int:customer_id>",
    methods=["PUT"]
)
def api_update_customer(customer_id):

    auth_error = require_customer(customer_id)

    if auth_error:
        return auth_error

    data = request.get_json(
        silent=True
    )

    if not data:
        return jsonify({
            "success": False,
            "message": "No profile data received."
        }), 400

    fullname = str(
        data.get(
            "fullname",
            ""
        )
    ).strip()

    email = str(
        data.get(
            "email",
            ""
        )
    ).strip().lower()

    phone = str(
        data.get(
            "phone",
            ""
        )
    ).strip()

    address = str(
        data.get(
            "address",
            ""
        )
    ).strip()

    if not fullname:
        return jsonify({
            "success": False,
            "message": "Full name is required."
        }), 400

    if not email:
        return jsonify({
            "success": False,
            "message": "Email is required."
        }), 400

    if not phone:
        return jsonify({
            "success": False,
            "message": "Phone number is required."
        }), 400

    conn = get_db()

    try:

        customer = conn.execute("""
            SELECT id
            FROM customers
            WHERE id = ?
        """, (
            customer_id,
        )).fetchone()

        if customer is None:
            conn.close()

            return jsonify({
                "success": False,
                "message": "Customer not found."
            }), 404

        existing_email = conn.execute("""
            SELECT id
            FROM customers
            WHERE email = ?
            AND id != ?
        """, (
            email,
            customer_id,
        )).fetchone()

        if existing_email:
            conn.close()

            return jsonify({
                "success": False,
                "message": "This email is already being used by another account."
            }), 409

        conn.execute("""
            UPDATE customers
            SET
                fullname = ?,
                email = ?,
                phone = ?,
                address = ?
            WHERE id = ?
        """, (
            fullname,
            email,
            phone,
            address,
            customer_id,
        ))

        conn.commit()

        updated_customer = conn.execute("""
            SELECT
                id,
                fullname,
                email,
                phone,
                address
            FROM customers
            WHERE id = ?
        """, (
            customer_id,
        )).fetchone()

        conn.close()

        return jsonify({
            "success": True,
            "message": "Profile updated successfully.",
            "customer": {
                "id": updated_customer["id"],
                "fullname": updated_customer["fullname"],
                "email": updated_customer["email"],
                "phone": updated_customer["phone"],
                "address": updated_customer["address"]
            }
        }), 200

    except Exception as e:

        conn.rollback()
        conn.close()

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500
    # =========================================================
# MOBILE APP - REGISTER FCM DEVICE TOKEN
# =========================================================

@app.route(
    "/api/customers/<int:customer_id>/fcm-token",
    methods=["POST"]
)
def api_register_fcm_token(customer_id):

    auth_error = require_customer(customer_id)

    if auth_error:
        return auth_error

    data = request.get_json(
        silent=True
    )

    if not data:

        return jsonify({
            "success": False,
            "message": "No notification data received."
        }), 400

    fcm_token = str(
        data.get(
            "fcm_token",
            ""
        )
    ).strip()

    if not fcm_token:

        return jsonify({
            "success": False,
            "message": "FCM token is required."
        }), 400

    if len(fcm_token) > 4096:

        return jsonify({
            "success": False,
            "message": "Invalid FCM token."
        }), 400

    conn = get_db()

    try:

        customer = conn.execute(
            """
            SELECT id
            FROM customers
            WHERE id = ?
            """,
            (customer_id,)
        ).fetchone()

        if customer is None:

            conn.close()

            return jsonify({
                "success": False,
                "message": "Customer not found."
            }), 404

        conn.execute(
            """
            UPDATE customers
            SET fcm_token = ?
            WHERE id = ?
            """,
            (
                fcm_token,
                customer_id
            )
        )

        conn.commit()
        conn.close()

        return jsonify({
            "success": True,
            "message": "Notification device registered successfully.",
            "customer_id": customer_id
        }), 200

    except Exception as e:

        conn.rollback()
        conn.close()

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500
# =========================================================
# MOBILE APP - GET CUSTOMER NOTIFICATIONS
# =========================================================

@app.route(
    "/api/customers/<int:customer_id>/notifications",
    methods=["GET"]
)
def api_get_customer_notifications(customer_id):

    auth_error = require_customer(customer_id)

    if auth_error:
        return auth_error

    conn = get_db()

    customer = conn.execute("""
        SELECT id
        FROM customers
        WHERE id = ?
    """, (
        customer_id,
    )).fetchone()

    if customer is None:

        conn.close()

        return jsonify({
            "success": False,
            "message": "Customer not found."
        }), 404

    notifications = conn.execute("""
        SELECT
            id,
            customer_id,
            title,
            body,
            notification_type,
            data,
            is_read,
            created_at
        FROM notifications
        WHERE customer_id = ?
        ORDER BY created_at DESC, id DESC
    """, (
        customer_id,
    )).fetchall()

    unread_count = conn.execute("""
        SELECT COUNT(*) AS count
        FROM notifications
        WHERE customer_id = ?
        AND is_read = 0
    """, (
        customer_id,
    )).fetchone()["count"]

    conn.close()

    result = []

    for notification in notifications:

        notification_data = {}

        raw_data = notification["data"]

        if raw_data:

            try:

                parsed_data = json.loads(
                    raw_data
                )

                if isinstance(
                    parsed_data,
                    dict
                ):
                    notification_data = parsed_data

            except (
                ValueError,
                TypeError
            ):

                notification_data = {}

        result.append({
            "id": notification["id"],
            "customer_id": notification["customer_id"],
            "title": notification["title"],
            "body": notification["body"],
            "notification_type": (
                notification["notification_type"]
                or "general"
            ),
            "data": notification_data,
            "is_read": bool(
                notification["is_read"]
            ),
            "created_at": notification["created_at"]
        })

    return jsonify({
        "success": True,
        "notifications": result,
        "unread_count": unread_count
    }), 200


# =========================================================
# MOBILE APP - MARK ONE NOTIFICATION AS READ
# =========================================================

@app.route(
    "/api/customers/<int:customer_id>/notifications/<int:notification_id>/read",
    methods=["PUT"]
)
def api_mark_notification_read(
    customer_id,
    notification_id
):

    auth_error = require_customer(customer_id)

    if auth_error:
        return auth_error

    conn = get_db()

    notification = conn.execute("""
        SELECT
            id
        FROM notifications
        WHERE id = ?
        AND customer_id = ?
    """, (
        notification_id,
        customer_id
    )).fetchone()

    if notification is None:

        conn.close()

        return jsonify({
            "success": False,
            "message": "Notification not found."
        }), 404

    conn.execute("""
        UPDATE notifications
        SET is_read = 1
        WHERE id = ?
        AND customer_id = ?
    """, (
        notification_id,
        customer_id
    ))

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "message": "Notification marked as read."
    }), 200


# =========================================================
# MOBILE APP - MARK ALL NOTIFICATIONS AS READ
# =========================================================

@app.route(
    "/api/customers/<int:customer_id>/notifications/read-all",
    methods=["PUT"]
)
def api_mark_all_notifications_read(
    customer_id
):

    auth_error = require_customer(customer_id)

    if auth_error:
        return auth_error

    conn = get_db()

    customer = conn.execute("""
        SELECT id
        FROM customers
        WHERE id = ?
    """, (
        customer_id,
    )).fetchone()

    if customer is None:

        conn.close()

        return jsonify({
            "success": False,
            "message": "Customer not found."
        }), 404

    conn.execute("""
        UPDATE notifications
        SET is_read = 1
        WHERE customer_id = ?
    """, (
        customer_id,
    ))

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "message": (
            "All notifications marked as read."
        )
    }), 200
    
@app.route(
    "/api/orders",
    methods=["POST"]
)
def api_create_order():

    data = request.get_json(
        silent=True
    )

    if not data:

        return jsonify({
            "success": False,
            "message": "No order data received."
        }), 400

    customer_id = data.get(
        "customer_id"
    )

    fullname = str(
        data.get(
            "fullname",
            ""
        )
    ).strip()

    email = str(
        data.get(
            "email",
            ""
        )
    ).strip().lower()

    phone = str(
        data.get(
            "phone",
            ""
        )
    ).strip()

    address = str(
        data.get(
            "address",
            ""
        )
    ).strip()

    items = data.get(
        "items",
        []
    )

    if not isinstance(
        items,
        list
    ) or not items:

        return jsonify({
            "success": False,
            "message": "Your cart is empty."
        }), 400

    conn = get_db()

    try:

        # =================================================
        # VERIFY CUSTOMER TOKEN WHEN CUSTOMER ID IS PROVIDED
        # =================================================

        if customer_id is not None:
            auth_error = require_customer(customer_id)
            if auth_error:
                conn.close()
                return auth_error

        # =================================================
        # VERIFY CUSTOMER IF CUSTOMER ID WAS PROVIDED
        # =================================================

        existing_customer = None

        if customer_id is not None:

            try:

                customer_id = int(
                    customer_id
                )

            except (
                ValueError,
                TypeError
            ):

                conn.close()

                return jsonify({
                    "success": False,
                    "message": "Invalid customer ID."
                }), 400

            existing_customer = conn.execute("""
                SELECT *
                FROM customers
                WHERE id = ?
            """, (
                customer_id,
            )).fetchone()

            if existing_customer is None:

                conn.close()

                return jsonify({
                    "success": False,
                    "message": "Customer account not found."
                }), 404

        else:

            # Guest/mobile order

            if not fullname or not phone or not address:

                conn.close()

                return jsonify({
                    "success": False,
                    "message": (
                        "Full name, phone number and "
                        "address are required."
                    )
                }), 400

        cart_items = []

        total = 0

        # =================================================
        # VERIFY PRODUCTS AND STOCK
        # =================================================

        for item in items:

            try:

                product_id = int(
                    item.get(
                        "product_id",
                        0
                    )
                )

                quantity = int(
                    item.get(
                        "quantity",
                        0
                    )
                )

            except (
                ValueError,
                TypeError
            ):

                conn.rollback()
                conn.close()

                return jsonify({
                    "success": False,
                    "message": "Invalid product or quantity."
                }), 400

            if (
                product_id <= 0
                or quantity <= 0
            ):

                conn.rollback()
                conn.close()

                return jsonify({
                    "success": False,
                    "message": "Invalid product or quantity."
                }), 400

            product = conn.execute("""
                SELECT *
                FROM products
                WHERE id = ?
            """, (
                product_id,
            )).fetchone()

            if product is None:

                conn.rollback()
                conn.close()

                return jsonify({
                    "success": False,
                    "message": (
                        f"Product {product_id} was not found."
                    )
                }), 404

            if product["stock"] < quantity:

                conn.rollback()
                conn.close()

                return jsonify({
                    "success": False,
                    "message": (
                        f"Insufficient stock for "
                        f"{product['name']}. "
                        f"Available stock: "
                        f"{product['stock']}"
                    )
                }), 400

            subtotal = (
                product["price"]
                * quantity
            )

            total += subtotal

            cart_items.append({
                "product": product,
                "quantity": quantity
            })

        # =================================================
        # CREATE CUSTOMER FOR GUEST ORDER
        # =================================================

        if existing_customer is None:

            # Reuse an existing customer when a matching email exists.
            existing_by_email = None
            if email:
                existing_by_email = conn.execute("""
                    SELECT * FROM customers WHERE email = ?
                """, (email,)).fetchone()

            if existing_by_email is not None:
                customer_id = existing_by_email["id"]
                conn.execute("""
                    UPDATE customers
                    SET fullname = ?, phone = ?, address = ?
                    WHERE id = ?
                """, (fullname, phone, address, customer_id))
            else:
                cursor = conn.execute("""
                    INSERT INTO customers
                    (fullname, email, phone, address)
                    VALUES (?, ?, ?, ?)
                """, (fullname, email, phone, address))
                customer_id = cursor.lastrowid

        else:
            # Use existing customer information.
            customer_id = existing_customer["id"]

        # =================================================
        # CREATE ORDER
        # =================================================

        cursor = conn.execute("""
            INSERT INTO orders
            (
                customer_id,
                total_amount,
                payment_status,
                order_status
            )
            VALUES (?, ?, ?, ?)
        """, (
            customer_id,
            total,
            "Pending",
            "Pending"
        ))

        order_id = cursor.lastrowid

        # =================================================
        # CREATE ORDER ITEMS + REDUCE STOCK
        # =================================================

        for item in cart_items:

            product = item["product"]

            quantity = item["quantity"]

            conn.execute("""
                INSERT INTO order_items
                (
                    order_id,
                    product_id,
                    quantity,
                    price
                )
                VALUES (?, ?, ?, ?)
            """, (
                order_id,
                product["id"],
                quantity,
                product["price"]
            ))

        # Commit the complete order once, after every item has been inserted.
        conn.commit()

        # =================================================
        # SEND ORDER RECEIVED NOTIFICATION
        # =================================================

        try:
            send_customer_notification(
                conn,
                customer_id,
                "Order Received",
                (
                    f"Your Levetor Hub order "
                    f"#{order_id} has been received "
                    f"successfully."
                ),
                {
                    "type": "order_created",
                    "order_id": str(order_id),
                    "customer_id": str(customer_id),
                }
            )
        except Exception as notification_error:
            print(
                "Order notification failed:",
                notification_error
            )

        conn.close()

        return jsonify({
            "success": True,
            "message": "Order placed successfully.",
            "order_id": order_id,
            "total_amount": total,
            "payment_status": "Pending",
            "order_status": "Pending",
            "customer_id": customer_id
        }), 201

    except Exception as e:

        conn.rollback()
        conn.close()

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================================================
# MOBILE APP - GET CUSTOMER ORDERS
# =========================================================

@app.route(
    "/api/orders/<int:customer_id>",
    methods=["GET"]
)
def api_get_orders(customer_id):

    auth_error = require_customer(customer_id)

    if auth_error:
        return auth_error

    conn = get_db()

    orders = conn.execute("""
        SELECT
            id,
            customer_id,
            total_amount,
            payment_status,
            order_status,
            created_at
        FROM orders
        WHERE customer_id = ?
        ORDER BY created_at DESC
    """, (
        customer_id,
    )).fetchall()

    result = []

    for order in orders:

        items = conn.execute("""
            SELECT
                order_items.product_id,
                order_items.quantity,
                order_items.price,
                products.name,
                products.brand,
                products.model,
                products.image
            FROM order_items

            LEFT JOIN products
            ON order_items.product_id = products.id

            WHERE order_items.order_id = ?
        """, (
            order["id"],
        )).fetchall()

        order_items = []

        for item in items:

            order_items.append({
                "product_id": item["product_id"],
                "name": item["name"],
                "brand": item["brand"],
                "model": item["model"],
                "image": item["image"],
                "quantity": item["quantity"],
                "price": item["price"]
            })

        result.append({
            "id": order["id"],
            "customer_id": order["customer_id"],
            "total_amount": order["total_amount"],
            "payment_status": order["payment_status"],
            "order_status": order["order_status"],
            "created_at": order["created_at"],
            "items": order_items
        })

    conn.close()

    return jsonify(result)


# =========================================================
# EDIT PRODUCT
# =========================================================

@app.route(
    "/admin/edit-product/<int:product_id>",
    methods=["GET", "POST"]
)
def edit_product(product_id):

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )

    conn = get_db()

    product = conn.execute("""
        SELECT *
        FROM products
        WHERE id = ?
    """, (
        product_id,
    )).fetchone()

    if product is None:

        conn.close()

        flash(
            "Product not found.",
            "danger"
        )

        return redirect(
            url_for("admin")
        )

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        category = request.form.get(
            "category",
            ""
        ).strip()

        brand = request.form.get(
            "brand",
            ""
        ).strip()

        model = request.form.get(
            "model",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        price = request.form.get(
            "price",
            "0"
        ).strip()

        stock = request.form.get(
            "stock",
            "0"
        ).strip()

        condition = request.form.get(
            "condition",
            "New"
        ).strip()

        warranty = request.form.get(
            "warranty",
            ""
        ).strip()

        if not name or not category or not price:

            conn.close()

            flash(
                "Product name, category and price are required.",
                "danger"
            )

            return redirect(
                url_for(
                    "edit_product",
                    product_id=product_id
                )
            )

        try:

            price = float(price)
            stock = int(stock)

        except ValueError:

            conn.close()

            flash(
                "Price and stock must contain valid numbers.",
                "danger"
            )

            return redirect(
                url_for(
                    "edit_product",
                    product_id=product_id
                )
            )

        image_filename = product["image"]

        image = request.files.get(
            "image"
        )

        if image and image.filename:

            if not allowed_file(
                image.filename
            ):

                conn.close()

                flash(
                    "Invalid image format. Use PNG, JPG, JPEG or WEBP.",
                    "danger"
                )

                return redirect(
                    url_for(
                        "edit_product",
                        product_id=product_id
                    )
                )

            original_filename = secure_filename(
                image.filename
            )

            extension = original_filename.rsplit(
                ".",
                1
            )[1].lower()

            image_filename = (
                str(uuid.uuid4())
                + "."
                + extension
            )

            image.save(
                os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    image_filename
                )
            )

            old_image = product["image"]

            if old_image:

                old_image_path = os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    old_image
                )

                if os.path.exists(
                    old_image_path
                ):

                    try:

                        os.remove(
                            old_image_path
                        )

                    except OSError:

                        pass

        conn.execute("""
            UPDATE products

            SET
                name = ?,
                category = ?,
                brand = ?,
                model = ?,
                description = ?,
                price = ?,
                stock = ?,
                image = ?,
                condition = ?,
                warranty = ?

            WHERE id = ?
        """, (
            name,
            category,
            brand,
            model,
            description,
            price,
            stock,
            image_filename,
            condition,
            warranty,
            product_id
        ))

        conn.commit()
        conn.close()

        flash(
            "Product updated successfully!",
            "success"
        )

        return redirect(
            url_for("admin")
        )

    conn.close()

    return render_template(
        "admin/edit_product.html",
        product=product
    )


# =========================================================
# DELETE PRODUCT
# =========================================================

@app.route(
    "/admin/delete-product/<int:product_id>",
    methods=["POST"]
)
def delete_product(product_id):

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )

    conn = get_db()

    product = conn.execute("""
        SELECT *
        FROM products
        WHERE id = ?
    """, (
        product_id,
    )).fetchone()

    if product is None:

        conn.close()

        flash(
            "Product not found.",
            "danger"
        )

        return redirect(
            url_for("admin")
        )

    image = product["image"]

    if image:

        image_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            image
        )

        if os.path.exists(
            image_path
        ):

            try:

                os.remove(
                    image_path
                )

            except OSError:

                pass

    conn.execute("""
        DELETE FROM products
        WHERE id = ?
    """, (
        product_id,
    ))

    conn.commit()
    conn.close()

    flash(
        "Product deleted successfully.",
        "success"
    )

    return redirect(
        url_for("admin")
    )


# =========================================================
# UPDATE CART QUANTITY
# =========================================================

@app.route(
    "/cart/update/<int:product_id>",
    methods=["POST"]
)
def update_cart(product_id):

    action = request.form.get(
        "action"
    )

    cart = session.get(
        "cart",
        {}
    )

    product_key = str(
        product_id
    )

    if product_key not in cart:

        flash(
            "Product is not in your cart.",
            "danger"
        )

        return redirect(
            url_for("cart")
        )

    # INCREASE

    if action == "increase":

        conn = get_db()

        product = conn.execute("""
            SELECT stock
            FROM products
            WHERE id = ?
        """, (
            product_id,
        )).fetchone()

        conn.close()

        if product:

            if cart[product_key] < product["stock"]:

                cart[product_key] += 1

            else:

                flash(
                    "You cannot exceed available stock.",
                    "warning"
                )

    # DECREASE

    elif action == "decrease":

        cart[product_key] -= 1

        if cart[product_key] <= 0:

            del cart[product_key]

    session["cart"] = cart

    return redirect(
        url_for("cart")
    )


# =========================================================
# CHECKOUT
# =========================================================

@app.route(
    "/checkout",
    methods=["GET", "POST"]
)
def checkout():

    cart = session.get(
        "cart",
        {}
    )

    if not cart:

        flash(
            "Your cart is empty. Add a product before checkout.",
            "warning"
        )

        return redirect(
            url_for("shop")
        )

    conn = get_db()

    cart_items = []

    total = 0

    for product_id, quantity in cart.items():

        product = conn.execute("""
            SELECT *
            FROM products
            WHERE id = ?
        """, (
            int(product_id),
        )).fetchone()

        if product is None:

            continue

        if quantity > product["stock"]:

            quantity = product["stock"]

            if quantity <= 0:

                continue

            cart[
                str(product_id)
            ] = quantity

        subtotal = (
            product["price"]
            * quantity
        )

        total += subtotal

        cart_items.append({
            "product": product,
            "quantity": quantity,
            "subtotal": subtotal
        })

    session["cart"] = cart

    if not cart_items:

        conn.close()

        session.pop(
            "cart",
            None
        )

        flash(
            "The products in your cart are no longer available.",
            "warning"
        )

        return redirect(
            url_for("shop")
        )

    # =====================================================
    # SUBMIT ORDER
    # =====================================================

    if request.method == "POST":

        fullname = request.form.get(
            "fullname",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip()

        phone = request.form.get(
            "phone",
            ""
        ).strip()

        address = request.form.get(
            "address",
            ""
        ).strip()

        if not fullname or not phone or not address:

            conn.close()

            flash(
                "Full name, phone number and delivery address are required.",
                "danger"
            )

            return render_template(
                "checkout.html",
                cart_items=cart_items,
                total=total,
                fullname=fullname,
                email=email,
                phone=phone,
                address=address
            )

        # CREATE CUSTOMER

        cursor = conn.execute("""
            INSERT INTO customers
            (
                fullname,
                email,
                phone,
                address
            )
            VALUES (?, ?, ?, ?)
        """, (
            fullname,
            email,
            phone,
            address
        ))

        customer_id = cursor.lastrowid

        # CREATE ORDER

        cursor = conn.execute("""
            INSERT INTO orders
            (
                customer_id,
                total_amount,
                payment_status,
                order_status
            )
            VALUES (?, ?, ?, ?)
        """, (
            customer_id,
            total,
            "Pending",
            "Pending"
        ))

        order_id = cursor.lastrowid

        # CREATE ORDER ITEMS

        for item in cart_items:

            product = item["product"]

            conn.execute("""
                INSERT INTO order_items
                (
                    order_id,
                    product_id,
                    quantity,
                    price
                )
                VALUES (?, ?, ?, ?)
            """, (
                order_id,
                product["id"],
                item["quantity"],
                product["price"]
            ))

            conn.execute("""
                UPDATE products
                SET stock = stock - ?
                WHERE id = ?
            """, (
                item["quantity"],
                product["id"]
            ))

        conn.commit()
        conn.close()

        session.pop(
            "cart",
            None
        )

        session[
            "last_order_id"
        ] = order_id

        flash(
            "Your order has been placed successfully!",
            "success"
        )

        return redirect(
            url_for(
                "order_success",
                order_id=order_id
            )
        )

    conn.close()

    return render_template(
        "checkout.html",
        cart_items=cart_items,
        total=total
    )


# =========================================================
# ORDER SUCCESS
# =========================================================

@app.route(
    "/order-success/<int:order_id>"
)
def order_success(order_id):

    conn = get_db()

    order = conn.execute("""
        SELECT
            orders.*,
            customers.fullname,
            customers.email,
            customers.phone,
            customers.address
        FROM orders

        JOIN customers
        ON orders.customer_id = customers.id

        WHERE orders.id = ?
    """, (
        order_id,
    )).fetchone()

    if order is None:

        conn.close()

        return "Order not found", 404

    order_items = conn.execute("""
        SELECT
            order_items.*,
            products.name,
            products.brand
        FROM order_items

        JOIN products
        ON order_items.product_id = products.id

        WHERE order_items.order_id = ?
    """, (
        order_id,
    )).fetchall()

    conn.close()

    return render_template(
        "order_success.html",
        order=order,
        order_items=order_items
    )


# =========================================================
# ADMIN ORDERS
# =========================================================

@app.route("/admin/orders")
def admin_orders():

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )

    conn = get_db()

    orders = conn.execute("""
        SELECT
            orders.id,
            orders.total_amount,
            orders.payment_status,
            orders.order_status,
            orders.created_at,
            customers.fullname,
            customers.phone,
            customers.email
        FROM orders

        LEFT JOIN customers
        ON orders.customer_id = customers.id

        ORDER BY orders.created_at DESC
    """).fetchall()

    conn.close()

    return render_template(
        "admin/orders.html",
        orders=orders
    )


# =========================================================
# ADMIN ORDER DETAILS
# =========================================================

@app.route(
    "/admin/orders/<int:order_id>"
)
def admin_order_details(order_id):

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )

    conn = get_db()

    order = conn.execute("""
        SELECT
            orders.*,
            customers.fullname,
            customers.email,
            customers.phone,
            customers.address
        FROM orders

        LEFT JOIN customers
        ON orders.customer_id = customers.id

        WHERE orders.id = ?
    """, (
        order_id,
    )).fetchone()

    if order is None:

        conn.close()

        return "Order not found", 404

    order_items = conn.execute("""
        SELECT
            order_items.id,
            order_items.quantity,
            order_items.price,
            products.name,
            products.brand,
            products.model
        FROM order_items

        LEFT JOIN products
        ON order_items.product_id = products.id

        WHERE order_items.order_id = ?
    """, (
        order_id,
    )).fetchall()

    conn.close()

    return render_template(
        "admin/order_details.html",
        order=order,
        order_items=order_items
    )


# =========================================================
# UPDATE ORDER STATUS
# =========================================================

@app.route(
    "/admin/orders/<int:order_id>/status",
    methods=["POST"]
)
def update_order_status(order_id):

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )

    status = request.form.get(
        "order_status",
        ""
    ).strip()

    allowed_statuses = [
        "Pending",
        "Processing",
        "Delivered",
        "Cancelled"
    ]

    if status not in allowed_statuses:

        flash(
            "Invalid order status.",
            "danger"
        )

        return redirect(
            url_for(
                "admin_order_details",
                order_id=order_id
            )
        )

    conn = get_db()

    order = conn.execute("""
        SELECT
            id,
            customer_id
        FROM orders
        WHERE id = ?
    """, (
        order_id,
    )).fetchone()

    if order is None:

        conn.close()

        flash(
            "Order not found.",
            "danger"
        )

        return redirect(
            url_for("admin_orders")
        )

    # =====================================================
    # ACTUALLY SAVE THE NEW ORDER STATUS
    # =====================================================

    conn.execute("""
        UPDATE orders
        SET order_status = ?
        WHERE id = ?
    """, (
        status,
        order_id
    ))

    conn.commit()

    # =====================================================
    # SEND ORDER STATUS NOTIFICATION
    # =====================================================

    try:

        send_customer_notification(
            conn,
            order["customer_id"],
            "Order Update",
            (
                f"Your Levetor Hub order "
                f"#{order_id} is now "
                f"{status}."
            ),
            {
                "type": "order_status",
                "order_id": str(order_id),
                "customer_id": str(
                    order["customer_id"]
                ),
                "status": status,
            }
        )

    except Exception as notification_error:

        print(
            "Order status notification failed:",
            notification_error
        )

    conn.close()

    flash(
        f"Order #{order_id} status updated to {status}.",
        "success"
    )

    return redirect(
        url_for(
            "admin_order_details",
            order_id=order_id
        )
    )

# =========================================================
# UPDATE PAYMENT STATUS
# =========================================================

@app.route(
    "/admin/orders/<int:order_id>/payment-status",
    methods=["POST"]
)
def update_payment_status(order_id):

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )

    payment_status = request.form.get(
        "payment_status",
        ""
    ).strip()

    allowed_statuses = [
        "Pending",
        "Paid",
        "Failed",
        "Refunded"
    ]

    if payment_status not in allowed_statuses:

        flash(
            "Invalid payment status.",
            "danger"
        )

        return redirect(
            url_for(
                "admin_order_details",
                order_id=order_id
            )
        )

    conn = get_db()

    order = conn.execute("""
        SELECT id
        FROM orders
        WHERE id = ?
    """, (
        order_id,
    )).fetchone()

    if order is None:

        conn.close()

        flash(
            "Order not found.",
            "danger"
        )

        return redirect(
            url_for("admin_orders")
        )

    conn.execute("""
        UPDATE orders
        SET payment_status = ?
        WHERE id = ?
    """, (
        payment_status,
        order_id
    ))

    conn.commit()
    conn.close()

    flash(
        f"Order #{order_id} payment status updated to {payment_status}.",
        "success"
    )

    return redirect(
        url_for(
            "admin_order_details",
            order_id=order_id
        )
    )
# =========================================================
# CUSTOMER REGISTRATION - WEBSITE
# =========================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if "customer_id" in session:

        return redirect(
            url_for("customer_account")
        )

    if request.method == "POST":

        fullname = request.form.get(
            "fullname",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        phone = request.form.get(
            "phone",
            ""
        ).strip()

        address = request.form.get(
            "address",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        confirm_password = request.form.get(
            "confirm_password",
            ""
        )

        if (
            not fullname
            or not email
            or not phone
            or not password
        ):

            flash(
                "Please fill in all required fields.",
                "danger"
            )

            return render_template(
                "register.html"
            )

        if password != confirm_password:

            flash(
                "Passwords do not match.",
                "danger"
            )

            return render_template(
                "register.html"
            )

        if len(password) < 8:

            flash(
                "Password must contain at least 8 characters.",
                "danger"
            )

            return render_template(
                "register.html"
            )

        conn = get_db()

        existing_customer = conn.execute("""
            SELECT id
            FROM customers
            WHERE email = ?
        """, (
            email,
        )).fetchone()

        if existing_customer:

            conn.close()

            flash(
                "An account with this email already exists.",
                "danger"
            )

            return render_template(
                "register.html"
            )

        password_hash = generate_password_hash(
            password
        )

        cursor = conn.execute("""
            INSERT INTO customers
            (
                fullname,
                email,
                phone,
                address,
                password_hash
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            fullname,
            email,
            phone,
            address,
            password_hash
        ))

        customer_id = cursor.lastrowid

        conn.commit()
        conn.close()

        session[
            "customer_id"
        ] = customer_id

        session[
            "customer_name"
        ] = fullname

        session[
            "customer_email"
        ] = email

        flash(
            "Your account has been created successfully!",
            "success"
        )

        return redirect(
            url_for("customer_account")
        )

    return render_template(
        "register.html"
    )


# =========================================================
# CUSTOMER LOGIN - WEBSITE
# =========================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if "customer_id" in session:

        return redirect(
            url_for("customer_account")
        )

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        if not email or not password:

            flash(
                "Email and password are required.",
                "danger"
            )

            return render_template(
                "login.html"
            )

        conn = get_db()

        customer = conn.execute("""
            SELECT *
            FROM customers
            WHERE email = ?
        """, (
            email,
        )).fetchone()

        conn.close()

        if customer is None:

            flash(
                "Invalid email or password.",
                "danger"
            )

            return render_template(
                "login.html"
            )

        if not customer["password_hash"]:

            flash(
                "This account does not have a password. Please contact support.",
                "danger"
            )

            return render_template(
                "login.html"
            )

        if not check_password_hash(
            customer["password_hash"],
            password
        ):

            flash(
                "Invalid email or password.",
                "danger"
            )

            return render_template(
                "login.html"
            )

        session[
            "customer_id"
        ] = customer["id"]

        session[
            "customer_name"
        ] = customer["fullname"]

        session[
            "customer_email"
        ] = customer["email"]

        flash(
            f"Welcome back, {customer['fullname']}!",
            "success"
        )

        next_page = session.pop(
            "login_next",
            None
        )

        if next_page == "checkout":

            return redirect(
                url_for("checkout")
            )

        return redirect(
            url_for("customer_account")
        )

    return render_template(
        "login.html"
    )


# =========================================================
# CUSTOMER ACCOUNT
# =========================================================

@app.route("/account")
def customer_account():

    if "customer_id" not in session:

        flash(
            "Please login to access your account.",
            "warning"
        )

        return redirect(
            url_for("login")
        )

    customer_id = session[
        "customer_id"
    ]

    conn = get_db()

    customer = conn.execute("""
        SELECT *
        FROM customers
        WHERE id = ?
    """, (
        customer_id,
    )).fetchone()

    if customer is None:

        conn.close()

        session.clear()

        flash(
            "Your account could not be found.",
            "danger"
        )

        return redirect(
            url_for("login")
        )

    orders = conn.execute("""
        SELECT *
        FROM orders
        WHERE customer_id = ?
        ORDER BY created_at DESC
    """, (
        customer_id,
    )).fetchall()

    conn.close()

    return render_template(
        "account.html",
        customer=customer,
        orders=orders
    )


# =========================================================
# EDIT CUSTOMER PROFILE
# =========================================================

@app.route(
    "/account/edit",
    methods=["GET", "POST"]
)
def edit_profile():

    if "customer_id" not in session:

        flash(
            "Please login to edit your profile.",
            "warning"
        )

        return redirect(
            url_for("login")
        )

    customer_id = session[
        "customer_id"
    ]

    conn = get_db()

    customer = conn.execute("""
        SELECT *
        FROM customers
        WHERE id = ?
    """, (
        customer_id,
    )).fetchone()

    if customer is None:

        conn.close()

        session.clear()

        flash(
            "Your account could not be found.",
            "danger"
        )

        return redirect(
            url_for("login")
        )

    if request.method == "POST":

        fullname = request.form.get(
            "fullname",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip()

        phone = request.form.get(
            "phone",
            ""
        ).strip()

        address = request.form.get(
            "address",
            ""
        ).strip()

        if not fullname or not phone:

            flash(
                "Full name and phone number are required.",
                "danger"
            )

            conn.close()

            return render_template(
                "edit_profile.html",
                customer=customer
            )

        conn.execute("""
            UPDATE customers
            SET
                fullname = ?,
                email = ?,
                phone = ?,
                address = ?
            WHERE id = ?
        """, (
            fullname,
            email,
            phone,
            address,
            customer_id
        ))

        conn.commit()
        conn.close()

        session[
            "customer_name"
        ] = fullname

        session[
            "customer_email"
        ] = email

        flash(
            "Your profile has been updated successfully.",
            "success"
        )

        return redirect(
            url_for("customer_account")
        )

    conn.close()

    return render_template(
        "edit_profile.html",
        customer=customer
    )


# =========================================================
# CUSTOMER ORDER DETAILS
# =========================================================

@app.route(
    "/account/order/<int:order_id>"
)
def customer_order_details(order_id):

    if "customer_id" not in session:

        flash(
            "Please login to view your order.",
            "warning"
        )

        return redirect(
            url_for("login")
        )

    customer_id = session[
        "customer_id"
    ]

    conn = get_db()

    order = conn.execute("""
        SELECT *
        FROM orders
        WHERE id = ?
        AND customer_id = ?
    """, (
        order_id,
        customer_id
    )).fetchone()

    if order is None:

        conn.close()

        flash(
            "Order not found.",
            "danger"
        )

        return redirect(
            url_for("customer_account")
        )

    order_items = conn.execute("""
        SELECT
            order_items.*,
            products.name,
            products.image
        FROM order_items

        JOIN products
        ON order_items.product_id = products.id

        WHERE order_items.order_id = ?
    """, (
        order_id,
    )).fetchall()

    customer = conn.execute("""
        SELECT *
        FROM customers
        WHERE id = ?
    """, (
        customer_id,
    )).fetchone()

    conn.close()

    return render_template(
        "order_details.html",
        order=order,
        order_items=order_items,
        customer=customer
    )


# =========================================================
# CUSTOMER LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.pop(
        "customer_id",
        None
    )

    session.pop(
        "customer_name",
        None
    )

    session.pop(
        "customer_email",
        None
    )

    flash(
        "You have been logged out successfully.",
        "success"
    )

    return redirect(
        url_for("home")
    )


# =========================================================
# FORGOT PASSWORD
# =========================================================

@app.route(
    "/forgot-password",
    methods=["GET", "POST"]
)
def forgot_password():

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        if not email:

            flash(
                "Please enter your email address.",
                "danger"
            )

            return render_template(
                "forgot_password.html"
            )

        conn = get_db()

        customer = conn.execute("""
            SELECT id, email
            FROM customers
            WHERE email = ?
        """, (
            email,
        )).fetchone()

        if customer is None:

            conn.close()

            flash(
                "No account was found with that email address.",
                "danger"
            )

            return render_template(
                "forgot_password.html"
            )

        reset_token = secrets.token_urlsafe(
            32
        )

        reset_expiry = (
            datetime.now()
            + timedelta(minutes=30)
        )

        conn.execute("""
            UPDATE customers
            SET
                reset_token = ?,
                reset_token_expiry = ?
            WHERE id = ?
        """, (
            reset_token,
            reset_expiry,
            customer["id"]
        ))

        conn.commit()
        conn.close()

        reset_link = url_for(
            "reset_password",
            token=reset_token,
            _external=True
        )

        return render_template(
            "reset_link.html",
            reset_link=reset_link
        )

    return render_template(
        "forgot_password.html"
    )


# =========================================================
# RESET PASSWORD
# =========================================================

@app.route(
    "/reset-password/<token>",
    methods=["GET", "POST"]
)
def reset_password(token):

    conn = get_db()

    customer = conn.execute("""
        SELECT *
        FROM customers
        WHERE reset_token = ?
    """, (
        token,
    )).fetchone()

    if customer is None:

        conn.close()

        flash(
            "This password reset link is invalid.",
            "danger"
        )

        return redirect(
            url_for("forgot_password")
        )

    expiry = customer[
        "reset_token_expiry"
    ]

    if not expiry:

        conn.close()

        flash(
            "This password reset link is invalid.",
            "danger"
        )

        return redirect(
            url_for("forgot_password")
        )

    try:

        expiry_datetime = datetime.fromisoformat(
            str(expiry)
        )

    except (
        ValueError,
        TypeError
    ):

        conn.close()

        flash(
            "This password reset link is invalid.",
            "danger"
        )

        return redirect(
            url_for("forgot_password")
        )

    if datetime.now() > expiry_datetime:

        conn.close()

        flash(
            "This password reset link has expired. Please request a new one.",
            "danger"
        )

        return redirect(
            url_for("forgot_password")
        )

    if request.method == "POST":

        password = request.form.get(
            "password",
            ""
        )

        confirm_password = request.form.get(
            "confirm_password",
            ""
        )

        if not password or not confirm_password:

            conn.close()

            flash(
                "Please enter and confirm your new password.",
                "danger"
            )

            return render_template(
                "reset_password.html"
            )

        if password != confirm_password:

            conn.close()

            flash(
                "Passwords do not match.",
                "danger"
            )

            return render_template(
                "reset_password.html"
            )

        if len(password) < 8:

            conn.close()

            flash(
                "Password must contain at least 8 characters.",
                "danger"
            )

            return render_template(
                "reset_password.html"
            )

        password_hash = generate_password_hash(
            password
        )

        conn.execute("""
            UPDATE customers
            SET
                password_hash = ?,
                reset_token = NULL,
                reset_token_expiry = NULL
            WHERE id = ?
        """, (
            password_hash,
            customer["id"]
        ))

        conn.commit()
        conn.close()

        flash(
            "Your password has been reset successfully. You can now login.",
            "success"
        )

        return redirect(
            url_for("login")
        )

    conn.close()

    return render_template(
        "reset_password.html"
    )


# =========================================================
# MY ACCOUNT
# =========================================================

@app.route("/my-account")
def my_account():

    if "customer_id" not in session:

        flash(
            "Please login to access your account.",
            "warning"
        )

        return redirect(
            url_for("login")
        )

    customer_id = session[
        "customer_id"
    ]

    conn = get_db()

    customer = conn.execute("""
        SELECT *
        FROM customers
        WHERE id = ?
    """, (
        customer_id,
    )).fetchone()

    if customer is None:

        conn.close()

        session.pop(
            "customer_id",
            None
        )

        flash(
            "Your account could not be found.",
            "danger"
        )

        return redirect(
            url_for("login")
        )

    orders = conn.execute("""
        SELECT
            id,
            total_amount,
            payment_status,
            order_status,
            created_at
        FROM orders
        WHERE customer_id = ?
        ORDER BY created_at DESC
    """, (
        customer_id,
    )).fetchall()

    conn.close()

    return render_template(
        "my_account.html",
        customer=customer,
        orders=orders
    )
# =========================================================
# PAYSTACK PAYMENT INITIALIZATION
# =========================================================

@app.route(
    "/api/payments/initialize",
    methods=["POST"]
)
def initialize_paystack_payment():

    data = request.get_json(
        silent=True
    )

    if not data:

        return jsonify({
            "success": False,
            "message": "No payment data received."
        }), 400

    try:

        order_id = int(
            data.get(
                "order_id",
                0
            )
        )

    except (
        ValueError,
        TypeError
    ):

        return jsonify({
            "success": False,
            "message": "Invalid order ID."
        }), 400

    if order_id <= 0:

        return jsonify({
            "success": False,
            "message": "Invalid order ID."
        }), 400

    conn = get_db()

    # Payment initialization is an authenticated customer operation.
    authenticated_customer_id = get_bearer_customer_id()
    if authenticated_customer_id is None:
        conn.close()
        return jsonify({
            "success": False,
            "message": "Authentication required. Please login again."
        }), 401

    order = conn.execute("""
        SELECT
            orders.id,
            orders.customer_id,
            orders.total_amount,
            orders.payment_status,
            orders.paystack_reference,
            customers.fullname,
            customers.email,
            customers.phone
        FROM orders
        LEFT JOIN customers
        ON orders.customer_id = customers.id
        WHERE orders.id = ?
    """, (
        order_id,
    )).fetchone()

    conn.close()

    if order is None:

        return jsonify({
            "success": False,
            "message": "Order not found."
        }), 404

    if int(order["customer_id"]) != authenticated_customer_id:
        return jsonify({
            "success": False,
            "message": "You are not authorized to pay for this order."
        }), 403

    if order["payment_status"] == "Paid":

        return jsonify({
            "success": False,
            "message": "This order has already been paid."
        }), 400

    if not PAYSTACK_SECRET_KEY:

        return jsonify({
            "success": False,
            "message": "Paystack secret key is not configured."
        }), 500

    email = order["email"]

    if not email:

        return jsonify({
            "success": False,
            "message": (
                "A valid customer email address "
                "is required for payment."
            )
        }), 400

    try:

        amount_kobo = int(
            round(
                float(
                    order["total_amount"]
                ) * 100
            )
        )

    except (
        ValueError,
        TypeError
    ):

        return jsonify({
            "success": False,
            "message": "Invalid order amount."
        }), 400

    if amount_kobo <= 0:

        return jsonify({
            "success": False,
            "message": "Order amount must be greater than zero."
        }), 400

    reference = (
        order["paystack_reference"]
        or
        f"LEVETOR-{order_id}-{uuid.uuid4().hex[:12].upper()}"
    )

    headers = {
        "Authorization": (
            f"Bearer {PAYSTACK_SECRET_KEY}"
        ),
        "Content-Type": "application/json"
    }

    payload = {
        "email": email,
        "amount": amount_kobo,
        "reference": reference,
        "metadata": {
            "order_id": order_id,
            "customer_id": order["customer_id"],
            "fullname": order["fullname"],
            "phone": order["phone"]
        }
    }

    try:

        response = requests.post(
            f"{PAYSTACK_BASE_URL}/transaction/initialize",
            json=payload,
            headers=headers,
            timeout=30
        )

        response_data = response.json()

    except requests.RequestException as e:

        return jsonify({
            "success": False,
            "message": (
                f"Could not connect to Paystack: {str(e)}"
            )
        }), 502

    except ValueError:

        return jsonify({
            "success": False,
            "message": "Invalid response received from Paystack."
        }), 502

    if not response_data.get("status"):

        return jsonify({
            "success": False,
            "message": response_data.get(
                "message",
                "Paystack payment initialization failed."
            )
        }), 400

    paystack_data = response_data.get(
        "data",
        {}
    )

    authorization_url = paystack_data.get(
        "authorization_url"
    )

    returned_reference = paystack_data.get(
        "reference",
        reference
    )

    if not authorization_url:

        return jsonify({
            "success": False,
            "message": (
                "Paystack did not return "
                "a payment authorization URL."
            )
        }), 502

    conn = get_db()

    try:

        conn.execute("""
            UPDATE orders
            SET paystack_reference = ?
            WHERE id = ?
        """, (
            returned_reference,
            order_id
        ))

        conn.commit()

    except Exception as e:

        conn.rollback()
        conn.close()

        return jsonify({
            "success": False,
            "message": (
                f"Could not save Paystack reference: {str(e)}"
            )
        }), 500

    conn.close()

    return jsonify({
        "success": True,
        "message": "Paystack payment initialized successfully.",
        "order_id": order_id,
        "reference": returned_reference,
        "authorization_url": authorization_url,
        "access_code": paystack_data.get(
            "access_code"
        ),
        "amount": order["total_amount"],
        "currency": "NGN",
        "public_key": PAYSTACK_PUBLIC_KEY
    }), 200


# =========================================================
# PAYSTACK PAYMENT VERIFICATION
# =========================================================

@app.route(
    "/api/payments/verify/<reference>",
    methods=["GET"]
)
def verify_paystack_payment(reference):

    reference = str(reference).strip()

    if not reference:
        return jsonify({
            "success": False,
            "message": "Payment reference is required."
        }), 400

    if not PAYSTACK_SECRET_KEY:
        return jsonify({
            "success": False,
            "message": "Paystack secret key is not configured."
        }), 500

    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(
            f"{PAYSTACK_BASE_URL}/transaction/verify/{reference}",
            headers=headers,
            timeout=30
        )
        response_data = response.json()
    except requests.RequestException as e:
        return jsonify({
            "success": False,
            "message": f"Could not connect to Paystack: {str(e)}"
        }), 502
    except ValueError:
        return jsonify({
            "success": False,
            "message": "Invalid response received from Paystack."
        }), 502

    if not response_data.get("status"):
        return jsonify({
            "success": False,
            "message": response_data.get(
                "message",
                "Payment verification failed."
            )
        }), 400

    payment_data = response_data.get("data") or {}
    payment_status = payment_data.get("status")

    if payment_status != "success":
        return jsonify({
            "success": False,
            "message": (
                "Payment has not been completed. "
                f"Paystack status: {payment_status}"
            ),
            "payment_status": payment_status,
            "reference": reference
        }), 400

    # -----------------------------------------------------
    # Resolve order from our stored reference first.
    # -----------------------------------------------------
    conn = get_db()

    order = conn.execute("""
        SELECT
            id,
            customer_id,
            total_amount,
            payment_status,
            order_status,
            paystack_reference
        FROM orders
        WHERE paystack_reference = ?
    """, (reference,)).fetchone()

    metadata = payment_data.get("metadata") or {}

    # Fallback to Paystack metadata if our reference was not stored.
    if order is None:
        try:
            metadata_order_id = int(metadata.get("order_id"))
        except (ValueError, TypeError):
            metadata_order_id = 0

        if metadata_order_id <= 0:
            conn.close()
            return jsonify({
                "success": False,
                "message": (
                    "Payment was successful, but the related "
                    "order could not be found."
                ),
                "reference": reference
            }), 404

        order = conn.execute("""
            SELECT
                id,
                customer_id,
                total_amount,
                payment_status,
                order_status,
                paystack_reference
            FROM orders
            WHERE id = ?
        """, (metadata_order_id,)).fetchone()

    if order is None:
        conn.close()
        return jsonify({
            "success": False,
            "message": "Order not found."
        }), 404

    # -----------------------------------------------------
    # Strict reference and metadata validation.
    # -----------------------------------------------------
    if order["paystack_reference"] and order["paystack_reference"] != reference:
        conn.close()
        return jsonify({
            "success": False,
            "message": "Payment reference does not match the order."
        }), 400

    try:
        metadata_order_id = int(metadata.get("order_id"))
    except (ValueError, TypeError):
        metadata_order_id = None

    if metadata_order_id is not None and metadata_order_id != int(order["id"]):
        conn.close()
        return jsonify({
            "success": False,
            "message": "Paystack order metadata does not match the order."
        }), 400

    try:
        metadata_customer_id = int(metadata.get("customer_id"))
    except (ValueError, TypeError):
        metadata_customer_id = None

    if (
        metadata_customer_id is not None
        and metadata_customer_id != int(order["customer_id"])
    ):
        conn.close()
        return jsonify({
            "success": False,
            "message": "Paystack customer metadata does not match the order."
        }), 400

    # Paystack should report the same reference that we initialized.
    returned_reference = str(payment_data.get("reference", "")).strip()
    if returned_reference and returned_reference != reference:
        conn.close()
        return jsonify({
            "success": False,
            "message": "Paystack returned a different payment reference."
        }), 400

    # -----------------------------------------------------
    # Verify exact payment amount and currency.
    # -----------------------------------------------------
    try:
        expected_amount = int(round(float(order["total_amount"]) * 100))
        paid_amount = int(payment_data.get("amount", 0))
    except (ValueError, TypeError):
        conn.close()
        return jsonify({
            "success": False,
            "message": "Invalid payment amount."
        }), 400

    if paid_amount != expected_amount:
        conn.close()
        return jsonify({
            "success": False,
            "message": "Payment amount does not match the order amount.",
            "expected_amount": expected_amount,
            "paid_amount": paid_amount
        }), 400

    payment_currency = str(payment_data.get("currency", "NGN")).upper()
    if payment_currency != "NGN":
        conn.close()
        return jsonify({
            "success": False,
            "message": "Payment currency is not supported for this order.",
            "currency": payment_currency
        }), 400

    # -----------------------------------------------------
    # Idempotency + atomic stock deduction.
    # BEGIN IMMEDIATE prevents two verification requests from
    # checking the same stock and both deducting it.
    # -----------------------------------------------------
    try:
        conn.execute("BEGIN IMMEDIATE")

        locked_order = conn.execute("""
            SELECT
                id,
                customer_id,
                total_amount,
                payment_status,
                order_status,
                paystack_reference
            FROM orders
            WHERE id = ?
        """, (order["id"],)).fetchone()

        if locked_order is None:
            conn.rollback()
            conn.close()
            return jsonify({
                "success": False,
                "message": "Order not found."
            }), 404

        if locked_order["payment_status"] == "Paid":
            conn.rollback()
            conn.close()
            return jsonify({
                "success": True,
                "message": "Payment was already verified.",
                "order_id": locked_order["id"],
                "reference": reference,
                "payment_status": "Paid",
                "order_status": locked_order["order_status"],
                "amount": locked_order["total_amount"],
                "currency": payment_currency
            }), 200

        order_items = conn.execute("""
            SELECT
                order_items.product_id,
                order_items.quantity,
                order_items.price,
                products.name,
                products.stock
            FROM order_items
            INNER JOIN products
                ON order_items.product_id = products.id
            WHERE order_items.order_id = ?
        """, (locked_order["id"],)).fetchall()

        if not order_items:
            conn.rollback()
            conn.close()
            return jsonify({
                "success": False,
                "message": "The order contains no items."
            }), 400

        for item in order_items:
            if item["stock"] < item["quantity"]:
                conn.rollback()
                conn.close()
                return jsonify({
                    "success": False,
                    "message": (
                        f"Insufficient stock for {item['name']}. "
                        f"Available stock: {item['stock']}"
                    )
                }), 409

        for item in order_items:
            conn.execute("""
                UPDATE products
                SET stock = stock - ?
                WHERE id = ?
            """, (item["quantity"], item["product_id"]))

        conn.execute("""
            UPDATE orders
            SET
                payment_status = ?,
                paystack_reference = ?
            WHERE id = ?
              AND payment_status != 'Paid'
        """, ("Paid", reference, locked_order["id"]))

        conn.commit()

        # Notification is intentionally after the transaction commits.
        try:
            send_customer_notification(
                conn,
                locked_order["customer_id"],
                "Payment Successful",
                (
                    f"Your payment of ₦{locked_order['total_amount']:,.0f} "
                    f"for order #{locked_order['id']} has been confirmed."
                ),
                {
                    "type": "payment_success",
                    "order_id": str(locked_order["id"]),
                    "customer_id": str(locked_order["customer_id"]),
                    "reference": reference,
                }
            )
        except Exception as notification_error:
            print("Payment notification failed:", notification_error)

        conn.close()

        return jsonify({
            "success": True,
            "message": "Payment verified and order confirmed successfully.",
            "order_id": locked_order["id"],
            "reference": reference,
            "payment_status": "Paid",
            "order_status": locked_order["order_status"],
            "amount": locked_order["total_amount"],
            "currency": payment_currency,
            "paid_at": payment_data.get("paid_at")
        }), 200

    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        conn.close()
        return jsonify({
            "success": False,
            "message": f"Could not finalize payment: {str(e)}"
        }), 500

# =========================================================
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=os.getenv("FLASK_DEBUG", "false").lower() == "true"
    )