"""Synthetic data fixtures for REST adapter testing.

These fixtures provide realistic test data for HTTP/REST API ingestion scenarios.
"""

from __future__ import annotations

# Sample JSON responses for various API scenarios
VALID_USER_API_RESPONSE = {
    "users": [
        {
            "id": 1,
            "username": "jdoe",
            "email": "john.doe@example.com",
            "firstName": "John",
            "lastName": "Doe",
            "phone": "+1-555-0123",
            "address": {
                "street": "123 Main St",
                "city": "Springfield",
                "state": "IL",
                "zipCode": "62701",
                "country": "USA",
            },
            "createdAt": "2024-01-15T10:30:00Z",
            "isActive": True,
            "roles": ["user", "subscriber"],
        },
        {
            "id": 2,
            "username": "asmith",
            "email": "alice.smith@example.com",
            "firstName": "Alice",
            "lastName": "Smith",
            "phone": "+1-555-0456",
            "address": {
                "street": "456 Oak Ave",
                "city": "Portland",
                "state": "OR",
                "zipCode": "97201",
                "country": "USA",
            },
            "createdAt": "2024-02-20T14:45:00Z",
            "isActive": True,
            "roles": ["user", "admin"],
        },
    ],
    "metadata": {"total": 2, "page": 1, "pageSize": 10},
}

PAGINATED_PRODUCTS_PAGE_1 = {
    "products": [
        {
            "id": "prod-001",
            "name": "Laptop Pro 15",
            "category": "Electronics",
            "price": 1299.99,
            "currency": "USD",
            "stock": 45,
            "manufacturer": "TechCorp",
            "ratings": {"average": 4.5, "count": 127},
        },
        {
            "id": "prod-002",
            "name": "Wireless Mouse",
            "category": "Electronics",
            "price": 29.99,
            "currency": "USD",
            "stock": 250,
            "manufacturer": "PeripheralCo",
            "ratings": {"average": 4.2, "count": 89},
        },
    ],
    "pagination": {"page": 1, "perPage": 2, "total": 5, "hasNext": True},
}

PAGINATED_PRODUCTS_PAGE_2 = {
    "products": [
        {
            "id": "prod-003",
            "name": "USB-C Cable",
            "category": "Accessories",
            "price": 15.99,
            "currency": "USD",
            "stock": 500,
            "manufacturer": "CableMakers",
            "ratings": {"average": 4.7, "count": 203},
        },
        {
            "id": "prod-004",
            "name": "Mechanical Keyboard",
            "category": "Electronics",
            "price": 149.99,
            "currency": "USD",
            "stock": 78,
            "manufacturer": "KeyTech",
            "ratings": {"average": 4.8, "count": 156},
        },
    ],
    "pagination": {"page": 2, "perPage": 2, "total": 5, "hasNext": True},
}

WEATHER_API_RESPONSE = {
    "location": {
        "city": "San Francisco",
        "state": "CA",
        "country": "US",
        "lat": 37.7749,
        "lon": -122.4194,
    },
    "current": {
        "temperature": 68.5,
        "feelsLike": 67.2,
        "humidity": 75,
        "pressure": 1015,
        "windSpeed": 12.5,
        "windDirection": "NW",
        "conditions": "Partly Cloudy",
        "visibility": 10.0,
        "uvIndex": 6,
    },
    "forecast": [
        {
            "date": "2024-10-06",
            "high": 72,
            "low": 58,
            "conditions": "Sunny",
            "precipChance": 10,
        },
        {
            "date": "2024-10-07",
            "high": 70,
            "low": 56,
            "conditions": "Cloudy",
            "precipChance": 30,
        },
    ],
    "timestamp": "2024-10-05T15:30:00Z",
}

ERROR_RESPONSES = {
    "404": {"error": {"code": "NOT_FOUND", "message": "Resource not found"}, "status": 404},
    "401": {"error": {"code": "UNAUTHORIZED", "message": "Invalid API key"}, "status": 401},
    "429": {
        "error": {"code": "RATE_LIMIT", "message": "Too many requests"},
        "status": 429,
        "retryAfter": 60,
    },
    "500": {
        "error": {"code": "INTERNAL_ERROR", "message": "Internal server error"},
        "status": 500,
    },
}

# Edge cases
EMPTY_RESPONSE = {"data": [], "count": 0}

MALFORMED_JSON = '{"incomplete": "json", "missing'

DEEPLY_NESTED_DATA = {
    "level1": {
        "level2": {
            "level3": {"level4": {"level5": {"value": "deep_value", "data": [1, 2, 3, 4, 5]}}}
        }
    }
}

UNICODE_DATA = {
    "messages": [
        {"lang": "en", "text": "Hello, World!"},
        {"lang": "es", "text": "¡Hola, Mundo!"},
        {"lang": "zh", "text": "你好世界"},
        {"lang": "ar", "text": "مرحبا بالعالم"},
        {"lang": "ja", "text": "こんにちは世界"},
        {"lang": "emoji", "text": "👋🌍🎉"},
    ]
}

LARGE_ARRAY_DATA = {
    "items": [{"id": i, "value": f"item_{i}", "score": i * 1.5} for i in range(1000)]
}

NULL_AND_MISSING_FIELDS = {
    "records": [
        {"id": 1, "name": "Complete", "email": "complete@test.com", "phone": "555-0001"},
        {"id": 2, "name": "No Email", "email": None, "phone": "555-0002"},
        {"id": 3, "name": "No Phone", "email": "nophone@test.com"},
        {"id": 4, "name": None, "email": None, "phone": None},
    ]
}
