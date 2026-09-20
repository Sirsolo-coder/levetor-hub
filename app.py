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
# SUPABASE STORAGE CONFIGURATION
# =========================================================

from supabase import create_client, Client  # type: ignore


SUPABASE_URL = os.getenv(
    "SUPABASE_URL"
)

SUPABASE_SERVICE_ROLE_KEY = os.getenv(
    "SUPABASE_SERVICE_ROLE_KEY"
)

SUPABASE_STORAGE_BUCKET = os.getenv(
    "SUPABASE_STORAGE_BUCKET",
    "product-images"
)


supabase: Client | None = None


if (
    SUPABASE_URL
    and SUPABASE_SERVICE_ROLE_KEY
):

    supabase = create_client(
        SUPABASE_URL,
        SUPABASE_SERVICE_ROLE_KEY
    )
# =========================================================
# GOOGLE AUTHENTICATION CONFIGURATION
# =========================================================

GOOGLE_WEB_CLIENT_ID = os.getenv(
    "GOOGLE_WEB_CLIENT_ID"
)
# =========================================================
# BREVO - PASSWORD RESET EMAIL
# =========================================================

BREVO_API_KEY = os.getenv("BREVO_API_KEY")
BREVO_SENDER_EMAIL = os.getenv(
    "BREVO_SENDER_EMAIL",
    "levetorglobalsolutions@gmail.com"
)
BREVO_SENDER_NAME = os.getenv(
    "BREVO_SENDER_NAME",
    "Levetor Hub"
)
PUBLIC_BASE_URL = os.getenv(
    "PUBLIC_BASE_URL",
    "http://127.0.0.1:5000"
)


def send_password_reset_email(
    recipient_email,
    reset_link
):

    if not BREVO_API_KEY:
        return False, "Brevo API key is not configured."

    if not BREVO_SENDER_EMAIL:
        return False, "Brevo sender email is not configured."

    payload = {
        "sender": {
            "name": BREVO_SENDER_NAME,
            "email": BREVO_SENDER_EMAIL
        },
        "to": [
            {
                "email": recipient_email
            }
        ],
        "subject": "Reset Your Levetor Hub Password",
        "htmlContent": f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport"
          content="width=device-width, initial-scale=1.0">
    <title>Reset Your Password</title>
</head>

<body style="
    margin:0;
    padding:0;
    background:#f4f6f8;
    font-family:Arial,Helvetica,sans-serif;
">

    <div style="
        max-width:600px;
        margin:40px auto;
        background:#ffffff;
        border-radius:12px;
        padding:32px;
        box-shadow:0 4px 18px rgba(0,0,0,0.08);
    ">

        <h1 style="
            margin-top:0;
            color:#111827;
        ">
            Levetor Hub
        </h1>

        <h2 style="
            color:#1f2937;
        ">
            Password Reset Request
        </h2>

        <p style="
            color:#4b5563;
            line-height:1.6;
        ">
            We received a request to reset the password
            for your Levetor Hub account.
        </p>

        <p style="
            color:#4b5563;
            line-height:1.6;
        ">
            Click the button below to create a new password.
        </p>

        <div style="
            text-align:center;
            margin:30px 0;
        ">

            <a href="{reset_link}"
               style="
                   display:inline-block;
                   padding:14px 24px;
                   background:#111827;
                   color:#ffffff;
                   text-decoration:none;
                   border-radius:8px;
                   font-weight:bold;
               ">
                Reset My Password
            </a>

        </div>

        <p style="
            color:#6b7280;
            font-size:14px;
            line-height:1.6;
        ">
            This password reset link will expire in
            <strong>30 minutes</strong>.
        </p>

        <p style="
            color:#6b7280;
            font-size:14px;
            line-height:1.6;
        ">
            If you did not request a password reset,
            you can safely ignore this email.
        </p>

        <hr style="
            border:0;
            border-top:1px solid #e5e7eb;
            margin:30px 0;
        ">

        <p style="
            color:#9ca3af;
            font-size:12px;
            text-align:center;
        ">
            Levetor Hub<br>
            Every Gadget You Love, One Hub.
        </p>

    </div>

</body>
</html>
""",
        "textContent": (
            "Levetor Hub Password Reset\n\n"
            "We received a request to reset your password.\n\n"
            f"Reset your password using this link:\n{reset_link}\n\n"
            "This link expires in 30 minutes.\n\n"
            "If you did not request this, you can ignore this email."
        )
    }

    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json"
    }

    try:

        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers=headers,
            json=payload,
            timeout=15
        )

        if 200 <= response.status_code < 300:

            return True, None

        try:
            error_data = response.json()
        except Exception:
            error_data = response.text

        return False, (
            f"Brevo email failed "
            f"({response.status_code}): {error_data}"
        )

    except requests.RequestException as exc:

        return False, (
            f"Unable to connect to Brevo: {exc}"
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
# SUPABASE PRODUCT IMAGE HELPERS
# =========================================================

def upload_product_image(image):
    """
    Upload a product image to Supabase Storage
    and return its public URL.
    """

    if supabase is None:
        raise RuntimeError(
            "Supabase Storage is not configured."
        )

    original_filename = secure_filename(
        image.filename or ""
    )

    if not original_filename:
        raise ValueError(
            "Invalid image filename."
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

    file_data = image.read()

    content_types = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp"
    }

    content_type = content_types.get(
        extension,
        "application/octet-stream"
    )

    supabase.storage.from_(
        SUPABASE_STORAGE_BUCKET
    ).upload(
        image_filename,
        file_data,
        {
            "content-type": content_type,
            "upsert": "false"
        }
    )

    public_url = supabase.storage.from_(
        SUPABASE_STORAGE_BUCKET
    ).get_public_url(
        image_filename
    )

    return public_url


def delete_product_image(image_value):
    """
    Delete a product image from Supabase Storage.

    Accepts either:
    - a full Supabase public URL
    - an old filename
    """

    if supabase is None:
        return

    if not image_value:
        return

    image_value = str(image_value).strip()

    if not image_value:
        return

    try:

        if "/storage/v1/object/public/" in image_value:

            path = image_value.split(
                f"/storage/v1/object/public/{SUPABASE_STORAGE_BUCKET}/",
                1
            )[1]

        else:

            path = image_value

        path = path.lstrip("/")

        if not path:
            return

        supabase.storage.from_(
            SUPABASE_STORAGE_BUCKET
        ).remove(
            [path]
        )

    except Exception as exc:

        print(
            "Supabase image deletion warning:",
            exc
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

        # =====================================================
        # VALIDATION
        # =====================================================

        if not name or not category or not price:

            flash(
                "Product name, category and price are required.",
                "danger"
            )

            return redirect(
                url_for("add_product")
            )

        # =====================================================
        # CONVERT NUMBERS
        # =====================================================

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

        # =====================================================
        # IMAGE UPLOAD - SUPABASE STORAGE
        # =====================================================

        image_url = None

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

            try:

                image_url = upload_product_image(
                    image
                )

            except Exception as exc:

                print(
                    "Supabase product image upload error:",
                    exc
                )

                flash(
                    "Product image upload failed. Please try again.",
                    "danger"
                )

                return redirect(
                    url_for("add_product")
                )

        # =====================================================
        # SAVE PRODUCT
        # =====================================================

        conn = None

        try:

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
                image_url,
                condition,
                warranty
            ))

            conn.commit()

        except Exception as exc:

            print(
                "Product creation error:",
                exc
            )

            if conn:

                try:
                    conn.rollback()
                except Exception:
                    pass

            # Remove uploaded image if database save failed
            if image_url:

                try:
                    delete_product_image(
                        image_url
                    )
                except Exception as cleanup_exc:

                    print(
                        "Supabase image cleanup warning:",
                        cleanup_exc
                    )

            flash(
                "Unable to add product. Please try again.",
                "danger"
            )

            return redirect(
                url_for("add_product")
            )

        finally:

            if conn:

                try:
                    conn.close()
                except Exception:
                    pass

        # =====================================================
        # SUCCESS
        # =====================================================

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
# CUSTOMER WEB AUTHENTICATION
# =========================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def customer_login():

    if session.get("customer_id"):

        return redirect(
            url_for("customer_account")
        )

    if request.method == "POST":

        email = str(
            request.form.get(
                "email",
                ""
            )
        ).strip().lower()

        password = str(
            request.form.get(
                "password",
                ""
            )
        )

        if not email or not password:

            flash(
                "Email and password are required.",
                "danger"
            )

            return render_template(
                "customer_login.html",
                google_web_client_id=GOOGLE_WEB_CLIENT_ID
            )

        conn = get_db()

        customer = conn.execute(
            """
            SELECT
                id,
                fullname,
                email,
                phone,
                address,
                password_hash
            FROM customers
            WHERE email = ?
            """,
            (
                email,
            )
        ).fetchone()

        conn.close()

        if customer is None:

            flash(
                "Invalid email or password.",
                "danger"
            )

            return render_template(
                "customer_login.html",
                google_web_client_id=GOOGLE_WEB_CLIENT_ID
            )

        password_hash = customer["password_hash"]

        if not password_hash:

            flash(
                "This account does not have a password. "
                "Please use Continue with Google.",
                "warning"
            )

            return render_template(
                "customer_login.html",
                google_web_client_id=GOOGLE_WEB_CLIENT_ID
            )

        if not check_password_hash(
            password_hash,
            password
        ):

            flash(
                "Invalid email or password.",
                "danger"
            )

            return render_template(
                "customer_login.html",
                google_web_client_id=GOOGLE_WEB_CLIENT_ID
            )

        session["customer_id"] = int(
            customer["id"]
        )

        session["customer_fullname"] = (
            customer["fullname"]
        )

        session["customer_email"] = (
            customer["email"]
        )

        session.modified = True

        flash(
            f"Welcome back, {customer['fullname']}!",
            "success"
        )

        return redirect(
            url_for("customer_account")
        )

    return render_template(
        "customer_login.html",
        google_web_client_id=GOOGLE_WEB_CLIENT_ID
    )
# =========================================================
# BROWSER - CUSTOMER REGISTRATION
# =========================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def customer_register():

    if session.get("customer_id"):

        return redirect(
            url_for("customer_account")
        )

    if request.method == "POST":

        fullname = str(
            request.form.get(
                "fullname",
                ""
            )
        ).strip()

        email = str(
            request.form.get(
                "email",
                ""
            )
        ).strip().lower()

        phone = str(
            request.form.get(
                "phone",
                ""
            )
        ).strip()

        address = str(
            request.form.get(
                "address",
                ""
            )
        ).strip()

        password = str(
            request.form.get(
                "password",
                ""
            )
        )

        confirm_password = str(
            request.form.get(
                "confirm_password",
                ""
            )
        )

        if not fullname or not email or not phone or not password:

            flash(
                "Full name, email, phone and password are required.",
                "danger"
            )

            return render_template(
                "register.html"
            )

        if len(password) < 8:

            flash(
                "Password must be at least 8 characters.",
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

        conn = get_db()

        existing_customer = conn.execute(
            """
            SELECT id
            FROM customers
            WHERE email = ?
            """,
            (
                email,
            )
        ).fetchone()

        if existing_customer:

            conn.close()

            flash(
                "An account with this email already exists. "
                "Please login instead.",
                "warning"
            )

            return render_template(
                "register.html"
            )

        password_hash = generate_password_hash(
            password
        )

        cursor = conn.execute(
            """
            INSERT INTO customers
            (
                fullname,
                email,
                phone,
                address,
                password_hash
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                fullname,
                email,
                phone,
                address,
                password_hash
            )
        )

        conn.commit()

        customer_id = cursor.lastrowid

        conn.close()

        session["customer_id"] = int(
            customer_id
        )

        session["customer_fullname"] = fullname
        session["customer_email"] = email

        session.modified = True

        flash(
            "Account created successfully. Welcome to Levetor Hub!",
            "success"
        )

        return redirect(
            url_for("customer_account")
        )

    return render_template(
        "register.html"
    )


# =========================================================
# BROWSER - FORGOT PASSWORD
# =========================================================

@app.route(
    "/forgot-password",
    methods=["GET", "POST"]
)
def forgot_password():

    if request.method == "POST":

        email = str(
            request.form.get(
                "email",
                ""
            )
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

        customer = conn.execute(
            """
            SELECT
                id,
                email
            FROM customers
            WHERE email = ?
            """,
            (
                email,
            )
        ).fetchone()

        if customer is None:

            conn.close()

            flash(
                "No account was found with that email address.",
                "danger"
            )

            return render_template(
                "forgot_password.html"
            )

        # -------------------------------------------------
        # CREATE SECURE RESET TOKEN
        # -------------------------------------------------

        reset_token = secrets.token_urlsafe(
            32
        )

        reset_expiry = (
            datetime.now()
            + timedelta(minutes=30)
        )

        conn.execute(
            """
            UPDATE customers
            SET
                reset_token = ?,
                reset_token_expiry = ?
            WHERE id = ?
            """,
            (
                reset_token,
                reset_expiry,
                customer["id"]
            )
        )

        conn.commit()
        conn.close()

        # -------------------------------------------------
        # CREATE PRODUCTION RESET LINK
        # -------------------------------------------------

        reset_link = (
            PUBLIC_BASE_URL.rstrip("/")
            + "/reset-password/"
            + reset_token
        )

        # -------------------------------------------------
        # SEND EMAIL
        # -------------------------------------------------

        email_sent, email_error = (
            send_password_reset_email(
                customer["email"],
                reset_link
            )
        )

        if not email_sent:

            # Invalidate the token if email delivery failed.

            conn = get_db()

            conn.execute(
                """
                UPDATE customers
                SET
                    reset_token = NULL,
                    reset_token_expiry = NULL
                WHERE id = ?
                """,
                (
                    customer["id"],
                )
            )

            conn.commit()
            conn.close()

            app.logger.error(
                "Password reset email failed: %s",
                email_error
            )

            flash(
                "We could not send the password reset email. "
                "Please try again later.",
                "danger"
            )

            return render_template(
                "forgot_password.html"
            )

        # -------------------------------------------------
        # EMAIL SENT
        # -------------------------------------------------

        flash(
            "Password reset instructions have been sent "
            "to your email address.",
            "success"
        )

        return redirect(
            url_for("customer_login")
        )

    return render_template(
        "forgot_password.html"
    )


# =========================================================
# BROWSER - RESET PASSWORD
# =========================================================

@app.route(
    "/reset-password/<token>",
    methods=["GET", "POST"]
)
def reset_password(token):

    conn = get_db()

    customer = conn.execute(
        """
        SELECT
            id,
            email,
            reset_token,
            reset_token_expiry
        FROM customers
        WHERE reset_token = ?
        """,
        (
            token,
        )
    ).fetchone()

    conn.close()

    if customer is None:

        flash(
            "This password reset link is invalid.",
            "danger"
        )

        return redirect(
            url_for("customer_login")
        )

    expiry_value = customer[
        "reset_token_expiry"
    ]

    try:

        expiry = datetime.fromisoformat(
            str(expiry_value)
        )

    except (ValueError, TypeError):

        flash(
            "This password reset link is invalid.",
            "danger"
        )

        return redirect(
            url_for("customer_login")
        )

    if datetime.now() > expiry:

        flash(
            "This password reset link has expired. "
            "Please request a new one.",
            "danger"
        )

        return redirect(
            url_for("forgot_password")
        )

    if request.method == "POST":

        password = str(
            request.form.get(
                "password",
                ""
            )
        )

        confirm_password = str(
            request.form.get(
                "confirm_password",
                ""
            )
        )

        if len(password) < 8:

            flash(
                "Password must be at least 8 characters.",
                "danger"
            )

            return render_template(
                "reset_password.html"
            )

        if password != confirm_password:

            flash(
                "Passwords do not match.",
                "danger"
            )

            return render_template(
                "reset_password.html"
            )

        password_hash = generate_password_hash(
            password
        )

        conn = get_db()

        conn.execute(
            """
            UPDATE customers
            SET
                password_hash = ?,
                reset_token = NULL,
                reset_token_expiry = NULL
            WHERE id = ?
            """,
            (
                password_hash,
                customer["id"]
            )
        )

        conn.commit()
        conn.close()

        flash(
            "Your password has been reset successfully. "
            "You can now login.",
            "success"
        )

        return redirect(
            url_for("customer_login")
        )

    return render_template(
        "reset_password.html"
    )


# =========================================================
# BROWSER - GOOGLE LOGIN
# =========================================================

@app.route(
    "/auth/google",
    methods=["POST"]
)
def customer_google_login():

    if not GOOGLE_WEB_CLIENT_ID:

        return jsonify({
            "success": False,
            "message": "Google authentication is not configured."
        }), 500

    data = request.get_json(
        silent=True
    ) or {}

    google_token = str(
        data.get(
            "id_token",
            ""
        )
    ).strip()

    if not google_token:

        return jsonify({
            "success": False,
            "message": "Google authentication token is required."
        }), 400

    try:

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
            "message": "Google account information is incomplete."
        }), 400

    if not email_verified:

        return jsonify({
            "success": False,
            "message": "Your Google email address is not verified."
        }), 400

    if not fullname:

        fullname = email.split("@")[0]

    conn = get_db()

    customer = conn.execute(
        """
        SELECT
            id,
            fullname,
            email,
            phone,
            address,
            password_hash,
            google_id,
            auth_provider
        FROM customers
        WHERE google_id = ?
        """,
        (
            google_id,
        )
    ).fetchone()

    if customer is None:

        customer = conn.execute(
            """
            SELECT
                id,
                fullname,
                email,
                phone,
                address,
                password_hash,
                google_id,
                auth_provider
            FROM customers
            WHERE email = ?
            """,
            (
                email,
            )
        ).fetchone()

    if customer:

        auth_provider = (
            "password_google"
            if customer["password_hash"]
            else "google"
        )

        conn.execute(
            """
            UPDATE customers
            SET
                google_id = ?,
                auth_provider = ?
            WHERE id = ?
            """,
            (
                google_id,
                auth_provider,
                customer["id"]
            )
        )

        conn.commit()

        customer_id = int(
            customer["id"]
        )

        customer_name = (
            customer["fullname"]
            or fullname
        )

        customer_email = (
            customer["email"]
            or email
        )

    else:

        cursor = conn.execute(
            """
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
            """,
            (
                fullname,
                email,
                "",
                "",
                None,
                google_id,
                "google"
            )
        )

        conn.commit()

        customer_id = int(
            cursor.lastrowid
        )

        customer_name = fullname
        customer_email = email

    conn.close()

    session["customer_id"] = customer_id
    session["customer_fullname"] = customer_name
    session["customer_email"] = customer_email
    session.modified = True

    return jsonify({
        "success": True,
        "message": "Google login successful.",
        "customer": {
            "id": customer_id,
            "fullname": customer_name,
            "email": customer_email
        }
    }), 200

@app.route("/logout")
def customer_logout():

    session.pop(
        "customer_id",
        None
    )

    session.pop(
        "customer_fullname",
        None
    )

    session.pop(
        "customer_email",
        None
    )

    session.modified = True

    flash(
        "You have been logged out successfully.",
        "success"
    )

    return redirect(
        url_for("home")
    )


# =========================================================
# CUSTOMER ACCOUNT
# =========================================================

@app.route("/account")
def customer_account():

    customer_id = session.get(
        "customer_id"
    )

    if not customer_id:

        flash(
            "Please login to access your account.",
            "warning"
        )

        return redirect(
            url_for("customer_login")
        )

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

    if customer is None:

        conn.close()

        session.pop(
            "customer_id",
            None
        )

        session.pop(
            "customer_fullname",
            None
        )

        session.pop(
            "customer_email",
            None
        )

        flash(
            "Your account could not be found. Please login again.",
            "danger"
        )

        return redirect(
            url_for("customer_login")
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
        LIMIT 5
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

    return render_template(
        "account.html",
        customer=customer,
        orders=orders,
        unread_count=unread_count
    )

# =========================================================
# CUSTOMER EDIT PROFILE
# =========================================================

@app.route(
    "/edit-profile",
    methods=["GET", "POST"]
)
def edit_profile():

    customer_id = session.get(
        "customer_id"
    )

    if not customer_id:

        flash(
            "Please login to edit your profile.",
            "warning"
        )

        return redirect(
            url_for("customer_login")
        )

    conn = get_db()

    customer = conn.execute(
        """
        SELECT
            id,
            fullname,
            email,
            phone,
            address
        FROM customers
        WHERE id = ?
        """,
        (
            customer_id,
        )
    ).fetchone()

    if customer is None:

        conn.close()

        session.pop(
            "customer_id",
            None
        )

        session.pop(
            "customer_fullname",
            None
        )

        session.pop(
            "customer_email",
            None
        )

        flash(
            "Customer account could not be found.",
            "danger"
        )

        return redirect(
            url_for("customer_login")
        )

    if request.method == "POST":

        fullname = (
            request.form.get(
                "fullname",
                ""
            ).strip()
        )

        email = (
            request.form.get(
                "email",
                ""
            ).strip().lower()
        )

        phone = (
            request.form.get(
                "phone",
                ""
            ).strip()
        )

        address = (
            request.form.get(
                "address",
                ""
            ).strip()
        )

        if not fullname:

            flash(
                "Full name is required.",
                "danger"
            )

            conn.close()

            return render_template(
                "edit_profile.html",
                customer=customer
            )

        if not phone:

            flash(
                "Phone number is required.",
                "danger"
            )

            conn.close()

            return render_template(
                "edit_profile.html",
                customer=customer
            )

        # -------------------------------------------------
        # Check whether another customer already uses
        # the submitted email address.
        # -------------------------------------------------

        if email:

            existing_customer = conn.execute(
                """
                SELECT id
                FROM customers
                WHERE LOWER(email) = ?
                AND id != ?
                LIMIT 1
                """,
                (
                    email,
                    customer_id
                )
            ).fetchone()

            if existing_customer:

                flash(
                    "That email address is already being used by another account.",
                    "danger"
                )

                conn.close()

                return render_template(
                    "edit_profile.html",
                    customer=customer
                )

        # -------------------------------------------------
        # Update customer profile
        # -------------------------------------------------

        conn.execute(
            """
            UPDATE customers
            SET
                fullname = ?,
                email = ?,
                phone = ?,
                address = ?
            WHERE id = ?
            """,
            (
                fullname,
                email if email else None,
                phone,
                address,
                customer_id
            )
        )

        conn.commit()
        conn.close()

        # -------------------------------------------------
        # Keep the browser session synchronized
        # -------------------------------------------------

        session["customer_fullname"] = fullname
        session["customer_email"] = email

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
# CUSTOMER ORDERS
# =========================================================

@app.route("/my-orders")
def customer_orders():

    customer_id = session.get(
        "customer_id"
    )

    if not customer_id:

        flash(
            "Please login to view your orders.",
            "warning"
        )

        return redirect(
            url_for("customer_login")
        )

    conn = get_db()

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

    order_items = {}

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

        order_items[order["id"]] = items

    conn.close()

    return render_template(
        "customer_orders.html",
        orders=orders,
        order_items=order_items
    )

# =========================================================
# CUSTOMER ORDER DETAILS
# =========================================================

@app.route(
    "/my-orders/<int:order_id>"
)
def customer_order_details(
    order_id
):

    customer_id = session.get(
        "customer_id"
    )

    if not customer_id:

        flash(
            "Please login to view your order.",
            "warning"
        )

        return redirect(
            url_for("customer_login")
        )

    conn = get_db()

    # -----------------------------------------------------
    # Get the order
    # -----------------------------------------------------

    order = conn.execute("""
        SELECT
            id,
            customer_id,
            total_amount,
            payment_status,
            order_status,
            created_at
        FROM orders
        WHERE id = ?
        AND customer_id = ?
        LIMIT 1
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
            url_for("customer_orders")
        )

    # -----------------------------------------------------
    # Get order items
    # -----------------------------------------------------

    order_items = conn.execute("""
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
        order_id,
    )).fetchall()

    conn.close()

    return render_template(
        "customer_order_details.html",
        order=order,
        order_items=order_items
    )
# =========================================================
# CUSTOMER NOTIFICATIONS
# =========================================================

@app.route("/notifications")
def customer_notifications():

    customer_id = session.get(
        "customer_id"
    )

    if not customer_id:

        flash(
            "Please login to view your notifications.",
            "warning"
        )

        return redirect(
            url_for("customer_login")
        )

    conn = get_db()

    notifications = conn.execute("""
        SELECT
            id,
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

    conn.close()

    return render_template(
        "notifications.html",
        notifications=notifications
    )


# =========================================================
# MARK ONE WEB NOTIFICATION AS READ
# =========================================================

@app.route(
    "/notifications/<int:notification_id>/read",
    methods=["POST"]
)
def customer_mark_notification_read(
    notification_id
):

    customer_id = session.get(
        "customer_id"
    )

    if not customer_id:

        flash(
            "Please login to continue.",
            "warning"
        )

        return redirect(
            url_for("customer_login")
        )

    conn = get_db()

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

    return redirect(
        url_for("customer_notifications")
    )


# =========================================================
# MARK ALL WEB NOTIFICATIONS AS READ
# =========================================================

@app.route(
    "/notifications/read-all",
    methods=["POST"]
)
def customer_mark_all_notifications_read():

    customer_id = session.get(
        "customer_id"
    )

    if not customer_id:

        flash(
            "Please login to continue.",
            "warning"
        )

        return redirect(
            url_for("customer_login")
        )

    conn = get_db()

    conn.execute("""
        UPDATE notifications
        SET is_read = 1
        WHERE customer_id = ?
    """, (
        customer_id,
    ))

    conn.commit()
    conn.close()

    flash(
        "All notifications marked as read.",
        "success"
    )

    return redirect(
        url_for("customer_notifications")
    )


# =========================================================
# CUSTOMER NAVBAR CONTEXT
# =========================================================

@app.context_processor
def inject_customer_nav_data():

    customer_id = session.get(
        "customer_id"
    )

    customer_nav = None
    customer_unread_notifications = 0

    if customer_id:

        conn = get_db()

        customer_nav = conn.execute("""
            SELECT
                id,
                fullname,
                email
            FROM customers
            WHERE id = ?
        """, (
            customer_id,
        )).fetchone()

        if customer_nav:

            customer_unread_notifications = conn.execute("""
                SELECT COUNT(*) AS count
                FROM notifications
                WHERE customer_id = ?
                AND is_read = 0
            """, (
                customer_id,
            )).fetchone()["count"]

        conn.close()

    return {
        "customer_nav": customer_nav,
        "customer_unread_notifications": (
            customer_unread_notifications
        )
    }
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
    # CREATE PRODUCTION RESET LINK
    # =====================================================

    reset_link = (
        PUBLIC_BASE_URL.rstrip("/")
        + "/reset-password/"
        + reset_token
    )

    # =====================================================
    # SEND PASSWORD RESET EMAIL
    # =====================================================

    email_sent, email_error = (
        send_password_reset_email(
            customer["email"],
            reset_link
        )
    )

    if not email_sent:

        # Invalidate the token because the customer
        # did not receive the reset link.

        conn = get_db()

        conn.execute("""
            UPDATE customers
            SET
                reset_token = NULL,
                reset_token_expiry = NULL
            WHERE id = ?
        """, (
            customer["id"],
        ))

        conn.commit()
        conn.close()

        app.logger.error(
            "API password reset email failed: %s",
            email_error
        )

        return jsonify({
            "success": False,
            "message": (
                "We could not send the password reset email. "
                "Please try again later."
            )
        }), 500

    # =====================================================
    # SUCCESS
    # =====================================================

    return jsonify({
        "success": True,
        "message": (
            "Password reset instructions have been "
            "sent to your email address."
        ),
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

        # =====================================================
        # VALIDATION
        # =====================================================

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

        # =====================================================
        # CONVERT NUMBERS
        # =====================================================

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

        # =====================================================
        # KEEP EXISTING IMAGE
        # =====================================================

        image_url = product["image"]

        image = request.files.get(
            "image"
        )

        uploaded_new_image = False

        # =====================================================
        # NEW IMAGE - SUPABASE STORAGE
        # =====================================================

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

            try:

                image_url = upload_product_image(
                    image
                )

                uploaded_new_image = True

            except Exception as exc:

                print(
                    "Supabase product image upload error:",
                    exc
                )

                conn.close()

                flash(
                    "Product image upload failed. Please try again.",
                    "danger"
                )

                return redirect(
                    url_for(
                        "edit_product",
                        product_id=product_id
                    )
                )

        # =====================================================
        # UPDATE PRODUCT
        # =====================================================

        try:

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
                image_url,
                condition,
                warranty,
                product_id
            ))

            conn.commit()

        except Exception as exc:

            print(
                "Product update error:",
                exc
            )

            try:
                conn.rollback()
            except Exception:
                pass

            # If a new image was uploaded but the database
            # update failed, remove the new image.
            if uploaded_new_image:

                try:

                    delete_product_image(
                        image_url
                    )

                except Exception as cleanup_exc:

                    print(
                        "Supabase new image cleanup warning:",
                        cleanup_exc
                    )

            conn.close()

            flash(
                "Unable to update product. Please try again.",
                "danger"
            )

            return redirect(
                url_for(
                    "edit_product",
                    product_id=product_id
                )
            )

        conn.close()

        # =====================================================
        # DELETE OLD IMAGE AFTER SUCCESSFUL DATABASE UPDATE
        # =====================================================

        if uploaded_new_image:

            old_image = product["image"]

            if old_image and old_image != image_url:

                try:

                    delete_product_image(
                        old_image
                    )

                except Exception as cleanup_exc:

                    print(
                        "Supabase old image cleanup warning:",
                        cleanup_exc
                    )

        # =====================================================
        # SUCCESS
        # =====================================================

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

    # =====================================================
    # DELETE PRODUCT FROM DATABASE
    # =====================================================

    try:

        conn.execute("""
            DELETE FROM products
            WHERE id = ?
        """, (
            product_id,
        ))

        conn.commit()

    except Exception as exc:

        print(
            "Product deletion error:",
            exc
        )

        try:
            conn.rollback()
        except Exception:
            pass

        conn.close()

        flash(
            "Unable to delete product. Please try again.",
            "danger"
        )

        return redirect(
            url_for("admin")
        )

    conn.close()

    # =====================================================
    # DELETE PRODUCT IMAGE FROM SUPABASE STORAGE
    # =====================================================

    if image:

        try:

            delete_product_image(
                image
            )

        except Exception as cleanup_exc:

            print(
                "Supabase product image deletion warning:",
                cleanup_exc
            )

    # =====================================================
    # SUCCESS
    # =====================================================

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

    # =====================================================
    # VALIDATE CART AGAINST CURRENT STOCK
    # =====================================================

    for product_id, quantity in cart.items():

        try:

            product_id = int(product_id)
            quantity = int(quantity)

        except (
            ValueError,
            TypeError
        ):

            continue

        if quantity <= 0:

            continue

        product = conn.execute("""
            SELECT *
            FROM products
            WHERE id = ?
        """, (
            product_id,
        )).fetchone()

        if product is None:

            continue

        # Keep cart quantity within available stock.
        if quantity > product["stock"]:

            quantity = product["stock"]

            if quantity <= 0:

                continue

            cart[
                str(product_id)
            ] = quantity

        subtotal = (
            float(product["price"])
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
    # SUBMIT CHECKOUT
    # =====================================================

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

        # -------------------------------------------------
        # REQUIRED INFORMATION
        # -------------------------------------------------

        if (
            not fullname
            or not email
            or not phone
            or not address
        ):

            conn.close()

            flash(
                "Full name, email, phone number and delivery address are required.",
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

        # -------------------------------------------------
        # BASIC EMAIL VALIDATION
        # -------------------------------------------------

        if (
            "@" not in email
            or "." not in email.split("@")[-1]
        ):

            conn.close()

            flash(
                "Please enter a valid email address.",
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

        # -------------------------------------------------
        # PAYSTACK CONFIGURATION
        # -------------------------------------------------

        if not PAYSTACK_SECRET_KEY:

            conn.close()

            flash(
                "Payment service is currently unavailable. Please try again later.",
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

        # =================================================
        # CREATE CUSTOMER + PENDING ORDER
        # =================================================

        try:

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

            # -------------------------------------------------
            # CREATE ORDER ITEMS
            #
            # IMPORTANT:
            # STOCK IS NOT DEDUCTED HERE.
            #
            # Stock will only be deducted after Paystack
            # successfully verifies the payment.
            # -------------------------------------------------

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

            conn.commit()

        except Exception as e:

            try:
                conn.rollback()
            except Exception:
                pass

            conn.close()

            print(
                "Web checkout order creation failed:",
                e
            )

            flash(
                "We could not create your order. Please try again.",
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

        conn.close()

        # =================================================
        # INITIALIZE PAYSTACK
        # =================================================

        try:

            amount_kobo = int(
                round(
                    float(total) * 100
                )
            )

            reference = (
                f"LEVETOR-WEB-{order_id}-"
                f"{uuid.uuid4().hex[:12].upper()}"
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
                "callback_url": url_for(
                    "paystack_web_callback",
                    _external=True
                ),
                "metadata": {
                    "order_id": order_id,
                    "customer_id": customer_id,
                    "fullname": fullname,
                    "phone": phone
                }
            }

            response = requests.post(
                f"{PAYSTACK_BASE_URL}/transaction/initialize",
                json=payload,
                headers=headers,
                timeout=30
            )

            response_data = response.json()

        except requests.RequestException as e:

            response_data = None

            print(
                "Paystack connection error:",
                e
            )

        except ValueError:

            response_data = None

            print(
                "Invalid Paystack response."
            )

        except Exception as e:

            response_data = None

            print(
                "Paystack initialization error:",
                e
            )

        # =================================================
        # INITIALIZATION FAILED
        # =================================================

        if (
            not response_data
            or not response_data.get("status")
        ):

            cleanup_conn = get_db()

            try:

                cleanup_conn.execute(
                    "BEGIN IMMEDIATE"
                )

                cleanup_conn.execute("""
                    DELETE FROM order_items
                    WHERE order_id = ?
                """, (
                    order_id,
                ))

                cleanup_conn.execute("""
                    DELETE FROM orders
                    WHERE id = ?
                """, (
                    order_id,
                ))

                cleanup_conn.execute("""
                    DELETE FROM customers
                    WHERE id = ?
                """, (
                    customer_id,
                ))

                cleanup_conn.commit()

            except Exception as cleanup_error:

                try:
                    cleanup_conn.rollback()
                except Exception:
                    pass

                print(
                    "Checkout cleanup failed:",
                    cleanup_error
                )

            finally:

                cleanup_conn.close()

            message = (
                response_data.get(
                    "message",
                    "Payment initialization failed."
                )
                if response_data
                else
                "Could not connect to the payment service."
            )

            flash(
                f"Payment could not be started: {message}",
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

        # =================================================
        # GET PAYSTACK AUTHORIZATION URL
        # =================================================

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

            flash(
                "Paystack did not return a payment page. Please try again.",
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

        # =================================================
        # SAVE PAYSTACK REFERENCE
        # =================================================

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

            try:
                conn.rollback()
            except Exception:
                pass

            conn.close()

            print(
                "Could not save Paystack reference:",
                e
            )

            flash(
                "Could not prepare your payment. Please try again.",
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

        conn.close()

        # =================================================
        # REMEMBER ORDER
        # =================================================

        session[
            "last_order_id"
        ] = order_id

        session[
            "web_payment_order_id"
        ] = order_id

        # =================================================
        # REDIRECT TO PAYSTACK
        # =================================================

        return redirect(
            authorization_url
        )

    # =====================================================
    # GET CHECKOUT PAGE
    # =====================================================

    conn.close()

    return render_template(
        "checkout.html",
        cart_items=cart_items,
        total=total
    )



# =========================================================
# PAYSTACK WEB CALLBACK / PAYMENT VERIFICATION
# =========================================================

@app.route(
    "/payments/paystack/callback"
)
def paystack_web_callback():

    reference = request.args.get(
        "reference",
        ""
    ).strip()

    if not reference:
        flash(
            "No payment reference was received.",
            "danger"
        )
        return redirect(url_for("checkout"))

    if not PAYSTACK_SECRET_KEY:
        flash(
            "Payment service is currently unavailable.",
            "danger"
        )
        return redirect(url_for("checkout"))

    # -----------------------------------------------------
    # VERIFY TRANSACTION WITH PAYSTACK
    # -----------------------------------------------------

    try:

        headers = {
            "Authorization": (
                f"Bearer {PAYSTACK_SECRET_KEY}"
            )
        }

        response = requests.get(
            f"{PAYSTACK_BASE_URL}/transaction/verify/{reference}",
            headers=headers,
            timeout=30
        )

        response_data = response.json()

    except requests.RequestException as e:

        print(
            "Paystack verification connection error:",
            e
        )

        flash(
            "We could not verify your payment. Please try again.",
            "danger"
        )

        return redirect(url_for("checkout"))

    except ValueError as e:

        print(
            "Invalid Paystack verification response:",
            e
        )

        flash(
            "Invalid payment verification response.",
            "danger"
        )

        return redirect(url_for("checkout"))

    except Exception as e:

        print(
            "Paystack verification error:",
            e
        )

        flash(
            "Payment verification failed. Please try again.",
            "danger"
        )

        return redirect(url_for("checkout"))

    # -----------------------------------------------------
    # VERIFY PAYSTACK TRANSACTION STATUS
    # -----------------------------------------------------

    if not response_data.get("status"):

        print(
            "Paystack verification failed:",
            response_data
        )

        flash(
            response_data.get(
                "message",
                "Payment verification failed."
            ),
            "danger"
        )

        return redirect(url_for("checkout"))

    paystack_data = response_data.get(
        "data",
        {}
    )

    transaction_status = paystack_data.get(
        "status"
    )

    verified_reference = paystack_data.get(
        "reference"
    )

    if (
        transaction_status != "success"
        or verified_reference != reference
    ):

        print(
            "Unsuccessful Paystack transaction:",
            paystack_data
        )

        flash(
            "Payment was not successful.",
            "danger"
        )

        return redirect(url_for("checkout"))

    # -----------------------------------------------------
    # FIND ORDER
    # -----------------------------------------------------

    conn = get_db()

    try:

        order = conn.execute(
            """
            SELECT
                id,
                customer_id,
                total_amount,
                payment_status,
                order_status,
                paystack_reference
            FROM orders
            WHERE paystack_reference = ?
            """,
            (
                reference,
            )
        ).fetchone()

        if order is None:

            conn.close()

            print(
                "Paystack callback order not found:",
                reference
            )

            flash(
                "We could not find the order for this payment.",
                "danger"
            )

            return redirect(url_for("checkout"))

        # -------------------------------------------------
        # PREVENT DOUBLE STOCK DEDUCTION
        # -------------------------------------------------

        if order["payment_status"] == "Paid":

            conn.close()

            return redirect(
                url_for(
                    "order_success",
                    order_id=order["id"]
                )
            )

        # -------------------------------------------------
        # VERIFY PAYMENT AMOUNT
        # -------------------------------------------------

        expected_amount = int(
            round(
                float(order["total_amount"]) * 100
            )
        )

        paid_amount = int(
            paystack_data.get(
                "amount",
                0
            )
        )

        if paid_amount != expected_amount:

            print(
                "Paystack amount mismatch:",
                {
                    "order_id": order["id"],
                    "expected": expected_amount,
                    "received": paid_amount
                }
            )

            conn.close()

            flash(
                "The payment amount could not be verified.",
                "danger"
            )

            return redirect(url_for("checkout"))

        # -------------------------------------------------
        # GET ORDER ITEMS
        # -------------------------------------------------

        order_items = conn.execute(
            """
            SELECT
                product_id,
                quantity
            FROM order_items
            WHERE order_id = ?
            """,
            (
                order["id"],
            )
        ).fetchall()

        # -------------------------------------------------
        # VERIFY STOCK AND DEDUCT
        # -------------------------------------------------

        for item in order_items:

            product = conn.execute(
                """
                SELECT
                    id,
                    stock
                FROM products
                WHERE id = ?
                """,
                (
                    item["product_id"],
                )
            ).fetchone()

            if product is None:

                raise Exception(
                    f"Product {item['product_id']} "
                    "not found during payment verification."
                )

            if product["stock"] < item["quantity"]:

                raise Exception(
                    f"Insufficient stock for product "
                    f"{item['product_id']}."
                )

            conn.execute(
                """
                UPDATE products
                SET stock = stock - ?
                WHERE id = ?
                """,
                (
                    item["quantity"],
                    item["product_id"]
                )
            )

        # -------------------------------------------------
        # MARK ORDER AS PAID
        # -------------------------------------------------

        conn.execute(
            """
            UPDATE orders
            SET
                payment_status = ?,
                order_status = ?
            WHERE id = ?
            """,
            (
                "Paid",
                "Processing",
                order["id"]
            )
        )

        conn.commit()

        # -------------------------------------------------
        # SAVE SUCCESSFUL ORDER IN SESSION
        # -------------------------------------------------

        session[
            "last_order_id"
        ] = order["id"]

        session[
            "web_payment_order_id"
        ] = order["id"]

        # -------------------------------------------------
        # CLEAR WEB CART
        # -------------------------------------------------

        session.pop(
            "cart",
            None
        )

        conn.close()

        flash(
            "Payment successful. Your order has been received.",
            "success"
        )

        return redirect(
            url_for(
                "order_success",
                order_id=order["id"]
            )
        )

    except Exception as e:

        try:
            conn.rollback()
        except Exception:
            pass

        conn.close()

        print(
            "Payment processing error:",
            e
        )

        flash(
            "Payment was received but could not be completed automatically. Please contact support.",
            "danger"
        )

        return redirect(url_for("checkout"))


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

# =========================================================
# ADMIN DELETE SELECTED ORDERS
# =========================================================

@app.route(
    "/admin/orders/delete-selected",
    methods=["POST"]
)
def delete_selected_admin_orders():

    if not admin_required():

        return redirect(
            url_for("admin_login")
        )

    order_ids = request.form.getlist(
        "order_ids"
    )

    if not order_ids:

        flash(
            "No orders were selected.",
            "warning"
        )

        return redirect(
            url_for("admin_orders")
        )

    conn = get_db()

    try:

        for order_id in order_ids:

            order = conn.execute(
                """
                SELECT
                    id,
                    payment_status,
                    paystack_reference
                FROM orders
                WHERE id = ?
                """,
                (order_id,)
            ).fetchone()

            if not order:
                continue

            order_items = conn.execute(
                """
                SELECT
                    product_id,
                    quantity
                FROM order_items
                WHERE order_id = ?
                """,
                (order_id,)
            ).fetchall()

            if (
                order["payment_status"] == "Paid"
                and order["paystack_reference"]
            ):

                for item in order_items:

                    conn.execute(
                        """
                        UPDATE products
                        SET stock = stock + ?
                        WHERE id = ?
                        """,
                        (
                            item["quantity"],
                            item["product_id"]
                        )
                    )

            conn.execute(
                """
                DELETE FROM order_items
                WHERE order_id = ?
                """,
                (order_id,)
            )

            conn.execute(
                """
                DELETE FROM orders
                WHERE id = ?
                """,
                (order_id,)
            )

        conn.commit()

        flash(
            f"{len(order_ids)} selected order(s) deleted successfully.",
            "success"
        )

    except Exception:

        conn.rollback()

        raise

    finally:

        conn.close()

    return redirect(
        url_for("admin_orders")
    )

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
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=os.getenv("FLASK_DEBUG", "false").lower() == "true"
    )




