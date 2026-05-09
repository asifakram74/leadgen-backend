# LeadStation Pro - Enterprise Backend (API)

LeadStation Pro is a high-performance B2B leads intelligence platform. This repository contains the **Commercial Core API** responsible for deep Google Maps scraping, CRM data management, and secure identity mapping.

## 🛠️ Technology Stack

*   **Framework**: [FastAPI](https://fastapi.tiangolo.com/) (High-performance Python web framework)
*   **Database**: [SQLite](https://www.sqlite.org/) with [SQLAlchemy ORM](https://www.sqlalchemy.org/)
*   **Scraping Engine**: [Playwright](https://playwright.dev/) with [Playwright-Stealth](https://github.com/berstend/puppeteer-extra/tree/master/packages/puppeteer-extra-plugin-stealth)
*   **Security**: [JOSE (JWT)](https://python-jose.readthedocs.io/) for encrypted identity tokens & [Passlib](https://passlib.readthedocs.io/) (Bcrypt)
*   **Mailing**: [FastAPI-Mail](https://github.com/sabuhish/fastapi-mail) for asynchronous SMTP delivery
*   **Configuration**: [Pydantic Settings](https://docs.pydantic.dev/latest/usage/pydantic_settings/) for secure environment variable management

## 🚀 Key Features

*   **Invisible Scraping**: Mimics human behavior to bypass anti-bot detection on Google Maps.
*   **AI Website Analysis**: Integrated GPT-powered engine to audit lead websites for health and performance.
*   **Landing Page Builder**: Automated generation of Tailwind-based landing pages for B2B leads.
*   **CRM Mapping**: Securely stores and evaluates lead trustworthiness (Ratings/Reviews).
*   **Automated Verification**: SMTP-integrated onboarding with beautiful HTML templates.
*   **Export Engine**: Real-time CSV and JSON data extraction into organized storage.

## 📦 Setup & Installation

1.  **Clone the Repository**:
    ```bash
    git clone https://github.com/your-username/leadstation-backend.git
    cd leadstation-backend
    ```

2.  **Initialize Virtual Environment**:
    ```bash
    python -m venv venv
    ./venv/Scripts/activate  # Windows
    source venv/bin/activate # Linux/Mac
    ```

3.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    playwright install chromium
    ```

4.  **Configure Environment**:
    Rename `.env.example` to `.env` and fill in your SMTP credentials and `SECRET_KEY`.

5.  **Run Development Server**:
    ```bash
    python main.py
    ```

## 🌐 API Documentation
Once running, access the interactive documentation at:
- Swagger UI: `http://localhost:8001/docs`
- Redoc: `http://localhost:8001/redoc`
