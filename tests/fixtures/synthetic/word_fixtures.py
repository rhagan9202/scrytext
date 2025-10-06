"""Synthetic Word document content fixtures for testing.

These provide realistic Word document scenarios without requiring actual .docx files.
"""

from __future__ import annotations

# Sample text content extracted from Word documents
BUSINESS_LETTER_TEXT = """
TechCorp Industries
1000 Innovation Drive
Silicon Valley, CA 94025
Phone: (555) 123-4567
Email: info@techcorp.com

October 5, 2024

Ms. Jennifer Martinez
Director of Operations
GlobalTech Solutions
500 Market Street
San Francisco, CA 94102

Dear Ms. Martinez,

RE: Proposal for Cloud Infrastructure Migration

I am writing to present our comprehensive proposal for migrating your company's
infrastructure to a modern cloud-based architecture. Our team at TechCorp has
extensive experience in enterprise cloud migrations, having successfully completed
over 200 projects in the past five years.

Project Scope:
1. Assessment of current infrastructure
2. Cloud architecture design and planning
3. Data migration and testing
4. Training and knowledge transfer
5. Post-migration support (6 months)

Timeline: 6-8 months
Investment: $250,000 - $350,000

We believe this migration will provide your organization with increased scalability,
improved disaster recovery capabilities, and 40% cost savings over three years.

I would welcome the opportunity to discuss this proposal in detail. Please feel
free to contact me at john.smith@techcorp.com or (555) 123-4567.

Sincerely,

John Smith
Vice President, Cloud Solutions
TechCorp Industries
"""

MEETING_MINUTES_TEXT = """
MEETING MINUTES

Date: October 5, 2024
Time: 10:00 AM - 11:30 AM
Location: Conference Room B / Virtual (Zoom)
Meeting Type: Product Strategy Review

Attendees:
- Sarah Johnson (Product Manager) - Chair
- Michael Chen (Engineering Lead)
- Lisa Wang (UX Designer)
- David Brown (Marketing Director)
- Emily Davis (Sales VP)

Absent:
- Robert Taylor (Finance) - On leave

Agenda:
1. Q3 Product Performance Review
2. Q4 Feature Roadmap
3. Customer Feedback Analysis
4. Resource Allocation
5. Action Items Review

Discussion Summary:

1. Q3 Product Performance Review
   - User growth: 25,000 new signups (target was 20,000)
   - Monthly active users: 150,000 (+18% from Q2)
   - Customer satisfaction score: 4.3/5.0
   - Churn rate: 3.8% (within acceptable range)

2. Q4 Feature Roadmap
   - Priority 1: Mobile app redesign (Launch: November)
   - Priority 2: Advanced analytics dashboard (Launch: December)
   - Priority 3: API v3 release (Launch: January)

   Michael noted that mobile redesign is on track, but analytics dashboard
   may need additional resources to meet December deadline.

3. Customer Feedback Analysis
   Lisa presented findings from 50 user interviews:
   - Top request: Dark mode (mentioned by 80% of users)
   - Second request: Bulk operations (mentioned by 65%)
   - Third request: Integration with Slack (mentioned by 55%)

4. Resource Allocation
   Decision: Hire 2 additional frontend developers by mid-October
   Budget approved: $200,000 for Q4 development costs

Action Items:
1. [Michael] Provide resource estimate for analytics dashboard - Due: Oct 10
2. [Lisa] Create dark mode design mockups - Due: Oct 12
3. [David] Draft Q4 marketing campaign plan - Due: Oct 15
4. [Emily] Follow up with top 10 enterprise customers - Due: Oct 20
5. [Sarah] Schedule follow-up meeting for Oct 19

Next Meeting: October 19, 2024, 10:00 AM

Minutes prepared by: Sarah Johnson
Date: October 5, 2024
"""

TECHNICAL_SPECIFICATION_TEXT = """
TECHNICAL SPECIFICATION DOCUMENT
Project: User Authentication System v2.0

Document Version: 1.3
Last Updated: October 5, 2024
Author: Engineering Team
Status: Under Review

1. OVERVIEW

This document specifies the requirements and design for the new authentication
system that will support multi-factor authentication, OAuth integration, and
enhanced security features.

2. FUNCTIONAL REQUIREMENTS

2.1 User Registration
- Email-based registration with verification
- Password requirements: minimum 12 characters, 1 uppercase, 1 lowercase,
  1 number, 1 special character
- CAPTCHA integration to prevent bot signups
- Optional social login (Google, GitHub, Microsoft)

2.2 Authentication Methods
- Username/password authentication
- Two-factor authentication (TOTP, SMS, Email)
- Biometric authentication (fingerprint, face ID) for mobile
- Single Sign-On (SSO) via SAML 2.0
- OAuth 2.0 / OpenID Connect support

2.3 Session Management
- JWT-based token authentication
- Refresh token rotation
- Configurable session timeout (default: 30 minutes)
- Device fingerprinting for suspicious activity detection

3. NON-FUNCTIONAL REQUIREMENTS

3.1 Performance
- Authentication request: < 200ms (p95)
- Token generation: < 50ms (p95)
- Support 10,000 concurrent authentication requests

3.2 Security
- Password hashing: bcrypt with cost factor 12
- Token encryption: AES-256-GCM
- Rate limiting: 5 failed attempts per 15 minutes
- HTTPS/TLS 1.3 required for all endpoints
- OWASP compliance for all authentication flows

3.3 Availability
- 99.9% uptime SLA
- Automatic failover to backup authentication service
- Database replication for high availability

4. API ENDPOINTS

POST /auth/register
POST /auth/login
POST /auth/logout
POST /auth/refresh
POST /auth/2fa/enable
POST /auth/2fa/verify
GET  /auth/user/profile
PUT  /auth/user/password

5. DATABASE SCHEMA

Table: users
- id (UUID, primary key)
- email (VARCHAR, unique, indexed)
- password_hash (VARCHAR)
- created_at (TIMESTAMP)
- updated_at (TIMESTAMP)
- email_verified (BOOLEAN)
- mfa_enabled (BOOLEAN)
- mfa_secret (VARCHAR, encrypted)

Table: sessions
- id (UUID, primary key)
- user_id (UUID, foreign key)
- token_hash (VARCHAR)
- device_info (JSONB)
- ip_address (VARCHAR)
- expires_at (TIMESTAMP)
- created_at (TIMESTAMP)

6. TESTING STRATEGY

- Unit tests: 90% code coverage minimum
- Integration tests for all API endpoints
- Security testing: OWASP ZAP automated scans
- Load testing: 10,000 concurrent users
- Penetration testing by third-party security firm

7. DEPLOYMENT PLAN

Phase 1 (Week 1): Deploy to staging environment
Phase 2 (Week 2): Security audit and testing
Phase 3 (Week 3): Gradual rollout to 10% of users
Phase 4 (Week 4): Full production deployment

8. DEPENDENCIES

- Node.js 18.x
- PostgreSQL 15.x
- Redis 7.x
- AWS KMS for key management
- Twilio for SMS delivery
"""

PROJECT_PROPOSAL_TEXT = """
PROJECT PROPOSAL

Title: Customer Analytics Platform
Department: Data Science & Analytics
Submitted by: Analytics Team
Date: October 5, 2024

EXECUTIVE SUMMARY

We propose building a comprehensive customer analytics platform that will
enable data-driven decision making across marketing, sales, and product teams.
This platform will consolidate data from multiple sources and provide real-time
insights into customer behavior, preferences, and lifetime value.

PROBLEM STATEMENT

Currently, our customer data is fragmented across 7 different systems:
- CRM (Salesforce)
- E-commerce platform (Shopify)
- Support tickets (Zendesk)
- Email marketing (Mailchimp)
- Web analytics (Google Analytics)
- Mobile app analytics (Mixpanel)
- Payment processing (Stripe)

This fragmentation leads to:
- Inconsistent reporting (estimates vary by up to 20%)
- Delayed insights (reports take 3-5 days to generate)
- Inability to track customer journey across touchpoints
- Missed opportunities for personalization and retention

PROPOSED SOLUTION

A unified analytics platform with the following components:

1. Data Integration Layer
   - Real-time connectors for all data sources
   - ETL pipelines with data quality checks
   - Customer identity resolution and matching

2. Data Warehouse
   - Cloud-based data warehouse (Snowflake)
   - Dimensional data model
   - Automated data refresh every hour

3. Analytics Engine
   - Customer segmentation algorithms
   - Predictive models for churn and LTV
   - Recommendation engine
   - Anomaly detection

4. Visualization Layer
   - Interactive dashboards
   - Self-service reporting
   - Automated alerts for key metrics
   - Mobile app for executives

BENEFITS

Quantifiable:
- Reduce reporting time from 3-5 days to real-time
- Improve marketing ROI by 25% through better targeting
- Reduce churn by 15% through proactive interventions
- Increase cross-sell revenue by 20%

Qualitative:
- Unified view of customer across all touchpoints
- Faster decision making with real-time insights
- Improved collaboration across teams
- Foundation for AI/ML initiatives

TIMELINE

Phase 1: Foundation (Months 1-3)
- Data integration for top 3 sources
- Basic data warehouse setup
- Initial dashboards

Phase 2: Expansion (Months 4-6)
- Complete data integration
- Advanced analytics features
- Self-service reporting

Phase 3: Intelligence (Months 7-9)
- Predictive models
- Recommendation engine
- Mobile app

BUDGET

Software & Infrastructure: $150,000
External Consultants: $200,000
Internal Resources (6 FTE): $450,000
Training & Change Management: $50,000
Total: $850,000

ROI: Expected 250% ROI within 24 months

RISKS & MITIGATION

Risk: Data quality issues
Mitigation: Implement comprehensive data validation and cleansing

Risk: User adoption challenges
Mitigation: Extensive training and change management program

Risk: Technical complexity
Mitigation: Phased approach with regular checkpoints

RECOMMENDATION

We recommend approval of this project given the significant strategic value
and strong ROI. The unified analytics platform will become a competitive
advantage and enable data-driven growth.

Approvals Required:
□ VP of Data & Analytics
□ CTO
□ CFO
□ CEO
"""

# Edge cases
EMPTY_DOCUMENT_TEXT = ""

DOCUMENT_WITH_TABLES = """
Sales Report Q3 2024

Regional Performance:

Region          Revenue      Growth    Market Share
North America   $25.5M       +12%      35%
Europe          $18.2M       +8%       28%
Asia Pacific    $12.8M       +22%      20%
Latin America   $5.5M        +15%      12%
Middle East     $3.2M        +18%      5%
Total           $65.2M       +14%      100%

Product Line Performance:

Product         Units Sold   Revenue     Margin
Enterprise      1,250        $35.2M      45%
Professional    3,480        $18.5M      38%
Standard        8,920        $11.5M      32%

Top 5 Customers by Revenue:
1. GlobalCorp     - $5.2M
2. TechGiant      - $4.8M
3. InnovateInc    - $3.9M
4. DataSystems    - $3.5M
5. CloudServices  - $3.1M
"""

# Metadata that would be extracted from Word documents
BUSINESS_LETTER_METADATA = {
    "title": "Cloud Infrastructure Migration Proposal",
    "author": "John Smith",
    "company": "TechCorp Industries",
    "created": "2024-10-05T09:15:00",
    "modified": "2024-10-05T09:45:00",
    "page_count": 2,
    "word_count": 287,
    "character_count": 1654,
}

MEETING_MINUTES_METADATA = {
    "title": "Product Strategy Review - Q3 2024",
    "author": "Sarah Johnson",
    "created": "2024-10-05T11:30:00",
    "modified": "2024-10-05T14:20:00",
    "page_count": 3,
    "word_count": 512,
    "character_count": 3245,
    "revision": 2,
}
