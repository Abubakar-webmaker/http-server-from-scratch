"""Application request handlers.

This module contains all business logic handlers for HTTP endpoints.
Separated from server.py to maintain clear separation of concerns:
- Transport layer (sockets) stays in server.py
- Application layer (handlers) is here
- Request orchestration is in dispatcher.py
"""

import json
from http.response import Response


# In-memory data stores
users = [
    {"id": 1, "name": "Ali"},
]

products = [
    {"id": 1, "name": "Laptop"},
    {"id": 2, "name": "Keyboard"},
]


def home(request):
    """Handle GET / - return HTML homepage."""
    return Response(
        200,
        "<html><body><h1>Hello World</h1></body></html>",
        {"Content-Type": "text/html; charset=utf-8"},
    )


def get_users(request):
    """Handle GET /users - return list of all users as JSON."""
    return Response(
        200,
        json.dumps(users),
        {"Content-Type": "application/json"},
    )


def create_user(request):
    """Handle POST /users - create new user from JSON body."""
    try:
        data = json.loads(request.body.decode("utf-8"))

        if not isinstance(data, dict) or not data.get("name"):
            return Response(400, "Invalid user data")

        user = {
            "id": len(users) + 1,
            "name": data["name"],
        }

        users.append(user)

        return Response(
            201,
            json.dumps(user),
            {"Content-Type": "application/json"},
        )

    except (ValueError, UnicodeDecodeError):
        return Response(400, "Invalid JSON")


def get_products(request):
    """Handle GET /products - return list of all products as JSON."""
    return Response(
        200,
        json.dumps(products),
        {"Content-Type": "application/json"},
    )


def get_user(request, id):
    """Handle GET /users/:id - return specific user by ID."""
    user = next(
        (item for item in users if str(item["id"]) == id),
        None,
    )

    if user is None:
        return Response(404, "User not found")

    return Response(
        200,
        json.dumps(user),
        {"Content-Type": "application/json"},
    )


def get_product(request, id):
    """Handle GET /products/:id - return specific product by ID."""
    product = next(
        (item for item in products if str(item["id"]) == id),
        None,
    )

    if product is None:
        return Response(404, "Product not found")

    return Response(
        200,
        json.dumps(product),
        {"Content-Type": "application/json"},
    )


def get_user_post(request, id, post_id):
    """Handle GET /users/:id/posts/:post_id - return nested resource."""
    return Response(
        200,
        json.dumps({
            "user_id": id,
            "post_id": post_id,
        }),
        {"Content-Type": "application/json"},
    )
