import re
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import time

def extract_website_details(page, url):
    """
    Visits the url using the given playwright page.
    Extracts emails and social links using Regex and BeautifulSoup.
    """
    details = {
        "emails": [],
        "social_links": [],
        "whatsapp": []
    }
    
    if not url:
        return details
        
    if not url.startswith('http'):
        url = 'https://' + url
    
    try:
        # Visit the page
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        
        # Short wait for any dynamic content after load
        time.sleep(0.5)
        
        content = page.content()
        soup = BeautifulSoup(content, 'html.parser')

        # 1. Extract Emails
        email_pattern = r'[a-zA-Z0-9.\-_]+@[a-zA-Z0-9.\-_]+\.[a-zA-Z]{2,}'
        
        # Find emails in 'mailto:' links
        mailtos = soup.select('a[href^="mailto:"]')
        for a in mailtos:
            href = a.get('href', '').replace('mailto:', '').split('?')[0].strip()
            if re.match(email_pattern, href):
                email_lower = href.lower()
                if email_lower not in details["emails"]:
                    details["emails"].append(email_lower)
        
        # Find emails in raw text (can be somewhat noisy, but useful)
        text_content = soup.get_text(separator=' ')
        found_emails = re.findall(email_pattern, text_content)
        for email in found_emails:
            # Basic filtering to avoid image extensions and common false positives
            if not email.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.js', '.css', 'example.com')):
                email_lower = email.lower()
                if email_lower not in details["emails"]:
                    details["emails"].append(email_lower)

        # 2. Extract Social Links & WhatsApp
        social_domains = ['facebook.com', 'instagram.com', 'twitter.com', 'x.com', 'linkedin.com', 'youtube.com', 'tiktok.com']
        whatsapp_domains = ['wa.me', 'api.whatsapp.com', 'whatsapp.com']
        
        links = soup.find_all('a', href=True)
        for link in links:
            href = link['href']
            parsed_href = urlparse(href)
            
            # Check WhatsApp
            is_whatsapp = False
            for w_domain in whatsapp_domains:
                if w_domain in parsed_href.netloc or w_domain in href:
                    if href not in details["whatsapp"]:
                        details["whatsapp"].append(href)
                    is_whatsapp = True
                    break
            
            if is_whatsapp:
                continue
                
            # Check if domain matches any of the social domains
            for domain in social_domains:
                if domain in parsed_href.netloc:
                    if href not in details["social_links"]:
                        details["social_links"].append(href)
                    break
                        
    except Exception as e:
        print(f" [+] Error scraping website {url}: {str(e)}")
        
    return details
