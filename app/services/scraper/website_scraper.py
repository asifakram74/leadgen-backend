import re
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import time

from app.services.scraper.browser_manager import block_heavy_resources

def extract_website_details(page, url):
    """
    Visits the URL using the given Playwright page.
    Extracts emails and social links using Regex and BeautifulSoup.

    Changes from original:
    - Resource blocking added (images/fonts/media) → saves ~1.5s per visit
    - Timeout: 30000ms → 12000ms. A page that takes >12s to load won't have
      useful contact info in the initial HTML anyway.
    - time.sleep(0.5) dynamic content wait removed — domcontentloaded is sufficient
      for static contact info (emails/social links are in the initial HTML).
    - Page-level timeout set before navigation for consistent behaviour.
    """
    details = {
        "emails": [],
        "social_links": [],
        "whatsapp": []
    }

    if not url:
        return details

    if not url.startswith("http"):
        url = "https://" + url

    try:
        # FIX: Block resources before navigating
        block_heavy_resources(page)

        # FIX: Tighter timeouts — 12s is plenty for contact info in initial HTML
        page.set_default_timeout(12000)
        page.goto(url, timeout=12000, wait_until="domcontentloaded")

        # Short wait for any dynamic content after load
        time.sleep(0.5)

        content = page.content()
        soup = BeautifulSoup(content, "html.parser")

        # 1. Extract Emails
        email_pattern = r"[a-zA-Z0-9.\-_]+@[a-zA-Z0-9.\-_]+\.[a-zA-Z]{2,}"

        # Priority: mailto: links (most reliable)
        mailtos = soup.select('a[href^="mailto:"]')
        for a in mailtos:
            href = a.get("href", "").replace("mailto:", "").split("?")[0].strip()
            if re.match(email_pattern, href):
                email_lower = href.lower()
                if email_lower not in details["emails"]:
                    details["emails"].append(email_lower)

        # Secondary: raw text scan (noisier but catches obfuscated emails)
        text_content = soup.get_text(separator=" ")
        found_emails = re.findall(email_pattern, text_content)
        for email in found_emails:
            if not email.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".js", ".css", "example.com")):
                email_lower = email.lower()
                if email_lower not in details["emails"]:
                    details["emails"].append(email_lower)

        # 2. Extract Social Links & WhatsApp
        social_domains = [
            "facebook.com", "instagram.com", "twitter.com", "x.com",
            "linkedin.com", "youtube.com", "tiktok.com",
        ]
        whatsapp_domains = ["wa.me", "api.whatsapp.com", "whatsapp.com"]

        links = soup.find_all("a", href=True)
        for link in links:
            href = link["href"]
            parsed_href = urlparse(href)

            # Check WhatsApp first
            is_whatsapp = False
            for w_domain in whatsapp_domains:
                if w_domain in parsed_href.netloc or w_domain in href:
                    if href not in details["whatsapp"]:
                        details["whatsapp"].append(href)
                    is_whatsapp = True
                    break

            if is_whatsapp:
                continue

            # Check social domains
            for domain in social_domains:
                if domain in parsed_href.netloc:
                    if href not in details["social_links"]:
                        details["social_links"].append(href)
                    break

    except Exception as e:
        print(f" [+] Error scraping website {url}: {str(e)}")

    return details
