"""Synthetic PDF content fixtures for testing.

These provide realistic PDF content scenarios without requiring actual PDF files.
"""

from __future__ import annotations

# Sample text content that would be extracted from PDFs
SIMPLE_DOCUMENT_TEXT = """
Invoice #INV-2024-001

Date: October 5, 2024
Due Date: November 5, 2024

Bill To:
Acme Corporation
123 Business Ave
Suite 100
San Francisco, CA 94102

Items:
1. Professional Services - Web Development    $5,000.00
2. Consulting Hours (40 hrs @ $150/hr)        $6,000.00
3. Cloud Hosting (Monthly)                      $500.00

Subtotal:                                     $11,500.00
Tax (8.5%):                                    $977.50
Total Due:                                    $12,477.50

Payment Terms: Net 30
Payment Methods: Bank Transfer, Check

Thank you for your business!
"""

MULTI_PAGE_REPORT_TEXT = """
=== Page 1 ===
QUARTERLY FINANCIAL REPORT
Q3 2024

Executive Summary

This report provides a comprehensive overview of the company's financial
performance for the third quarter of 2024. Key highlights include:

• Revenue growth of 15% year-over-year
• Operating margin improvement to 22%
• Successful product launch in EMEA region
• Strong cash flow generation

=== Page 2 ===
Financial Metrics

Revenue: $45.2M (+15% YoY)
Cost of Goods Sold: $25.1M
Gross Profit: $20.1M
Operating Expenses: $10.5M
Operating Income: $9.6M
Net Income: $7.8M

Key Performance Indicators:
- Customer Acquisition Cost: $850
- Lifetime Value: $12,500
- Churn Rate: 3.2%
- Monthly Recurring Revenue: $15.1M

=== Page 3 ===
Regional Breakdown

North America: $28.5M (63%)
Europe: $10.2M (23%)
Asia Pacific: $6.5M (14%)

Top Product Lines:
1. Enterprise Software: $20.1M
2. Cloud Services: $15.3M
3. Professional Services: $9.8M

Outlook for Q4 2024:
Expected revenue range: $48M - $52M
Planned investments in R&D and sales expansion
"""

TECHNICAL_DOCUMENT_TEXT = """
API DOCUMENTATION
Version 2.1.0

Authentication

All API requests must include an API key in the header:
Authorization: Bearer YOUR_API_KEY

Base URL: https://api.example.com/v2

Endpoints:

GET /users
Retrieve list of users
Parameters:
  - page (integer): Page number (default: 1)
  - limit (integer): Items per page (default: 20)
  - sort (string): Sort field (default: created_at)

Response:
{
  "users": [...],
  "pagination": {
    "page": 1,
    "total": 150,
    "hasNext": true
  }
}

POST /users
Create a new user
Request Body:
{
  "username": "string",
  "email": "string",
  "password": "string"
}

Response: 201 Created

Rate Limiting:
- 1000 requests per hour per API key
- 429 status code returned when limit exceeded
"""

FORM_WITH_TABLES_TEXT = """
Employee Performance Review
Q3 2024

Employee Information:
Name: Sarah Johnson
Employee ID: EMP-2847
Department: Engineering
Position: Senior Software Engineer
Review Period: July 1 - September 30, 2024

Performance Ratings:

Category                    Rating (1-5)    Comments
Technical Skills            5               Excellent problem-solving
Code Quality                4               Consistent, maintainable code
Communication               4               Clear documentation
Leadership                  5               Mentors junior developers
Project Delivery            5               All projects on time

Goals Achievement:
✓ Complete microservices migration - 100%
✓ Reduce technical debt - 85%
✓ Mentor 2 junior engineers - 100%
✗ Obtain AWS certification - Deferred to Q4

Overall Rating: 4.6 / 5.0

Reviewer: Michael Chen
Date: October 1, 2024
"""

RESEARCH_PAPER_ABSTRACT = """
Abstract

Title: Machine Learning Approaches for Anomaly Detection in Time Series Data

Authors: Dr. Jane Smith¹, Prof. Robert Johnson², Dr. Maria Garcia¹

¹ Department of Computer Science, University of Technology
² Institute for Advanced Computing, State University

This paper presents a comprehensive study of machine learning techniques
for detecting anomalies in multivariate time series data. We evaluate
five state-of-the-art algorithms: LSTM Autoencoders, Isolation Forests,
One-Class SVM, Prophet, and Transformer-based models.

Our experimental results, based on three real-world datasets from IoT
sensors, financial markets, and network traffic, demonstrate that LSTM
Autoencoders achieve the highest F1-score (0.94) while maintaining
computational efficiency. We also introduce a novel hybrid approach
combining attention mechanisms with autoencoding, achieving 97% accuracy
with 30% faster inference time.

Keywords: anomaly detection, time series, deep learning, LSTM, autoencoders

1. Introduction

Time series anomaly detection is critical for many applications including
fraud detection, system monitoring, and predictive maintenance. Traditional
statistical methods often fail to capture complex patterns in high-dimensional
data...

[Full paper continues for 12 pages]
"""

# Edge cases
EMPTY_PDF_TEXT = ""

PDF_WITH_SPECIAL_CHARACTERS = """
Special Characters Test Document

Mathematical symbols: ∑ ∫ ∂ √ ≈ ≠ ≤ ≥ ∞ π θ λ
Currency: $ € £ ¥ ₹ ₽
Arrows: → ← ↑ ↓ ⇒ ⇐ ↔
Greek letters: α β γ δ ε ζ η θ ι κ λ μ ν ξ ο π ρ σ τ υ φ χ ψ ω

Superscript: x² + y² = z²
Subscript: H₂O, CO₂

Fractions: ½ ⅓ ¼ ¾ ⅛
Degrees: 90° 180° 360°

Copyright © 2024 | Trademark ™ | Registered ®
"""

PDF_WITH_UNICODE = """
Multilingual Document

English: Hello, World!
Spanish: ¡Hola, Mundo!
French: Bonjour, Monde!
German: Hallo, Welt!
Italian: Ciao, Mondo!
Portuguese: Olá, Mundo!
Russian: Привет, мир!
Arabic: مرحبا بالعالم
Hebrew: שלום עולם
Chinese: 你好世界
Japanese: こんにちは世界
Korean: 안녕하세요 세계
Hindi: नमस्ते दुनिया
Thai: สวัสดีชาวโลก
"""

# Metadata that would be extracted from PDF properties
SIMPLE_DOCUMENT_METADATA = {
    "title": "Invoice INV-2024-001",
    "author": "Billing System",
    "subject": "Monthly Invoice",
    "creator": "InvoiceGenerator v2.1",
    "producer": "PDF Library 3.0",
    "creation_date": "2024-10-05T10:30:00",
    "modification_date": "2024-10-05T10:30:00",
    "page_count": 1,
    "file_size": 45678,
}

TECHNICAL_DOCUMENT_METADATA = {
    "title": "API Documentation v2.1.0",
    "author": "Engineering Team",
    "subject": "REST API Reference",
    "keywords": ["API", "REST", "documentation", "endpoints"],
    "creator": "DocGen Pro",
    "producer": "Adobe PDF 1.7",
    "creation_date": "2024-09-15T14:20:00",
    "modification_date": "2024-10-01T09:45:00",
    "page_count": 25,
    "file_size": 1234567,
}
