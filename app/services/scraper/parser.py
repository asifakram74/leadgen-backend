import re


def safe_text(locator, selector):
    try:
        el = locator.query_selector(selector)
        return el.inner_text().strip() if el else ""
    except Exception:
        return ""


def parse_place_details(page):
    try:
        # Wait for the title to be visible to ensure panel is loaded
        try:
            page.wait_for_selector('h1', timeout=6000)
        except Exception:
            pass

        name = safe_text(page, "h1")
        
        # Ratings and reviews
        rating = safe_text(page, "div.F7nice > span:first-child")
        if not rating:
            rating_el = page.query_selector("span[aria-label*='stars']")
            rating = rating_el.get_attribute("aria-label").split(' ')[0] if rating_el else ""
            
        reviews = safe_text(page, "div.F7nice > span:last-child")
        if not reviews:
            reviews_el = page.query_selector("span[aria-label*='reviews']")
            reviews = reviews_el.get_attribute("aria-label").split(' ')[0] if reviews_el else ""

        if reviews:
            reviews = reviews.replace('(', '').replace(')', '')

        # Phone
        try:
            phone_el = page.query_selector("button[data-tooltip*='phone number']")
            if phone_el:
                phone_raw = phone_el.inner_text().strip()
                match = re.search(r'[\+\(]?[1-9][0-9 .\-\(\)]{8,}[0-9]', phone_raw)
                phone = match.group(0) if match else phone_raw.split("\n")[-1].strip()
            else:
                phone_el = page.query_selector("button[data-item-id*='phone:tel:']")
                phone_raw = phone_el.query_selector("div.fontBodyMedium").inner_text().strip() if phone_el and phone_el.query_selector("div.fontBodyMedium") else ""
                match = re.search(r'[\+\(]?[1-9][0-9 .\-\(\)]{8,}[0-9]', phone_raw)
                phone = match.group(0) if match else phone_raw.split("\n")[-1].strip()
        except Exception:
            phone = ""
            
        # Website
        try:
            website_el = page.query_selector("a[data-tooltip*='website']")
            if website_el:
                website = website_el.get_attribute("href")
            else:
                website_el = page.query_selector("a[data-item-id='authority']")
                website = website_el.get_attribute("href") if website_el else ""
        except Exception:
            website = ""
            
        # Address
        try:
            address_el = page.query_selector("button[data-tooltip*='address']")
            if address_el:
                address = address_el.inner_text().strip()
                address = address.replace('\ue0c8', '').strip() # removing common map icon
            else:
                address_el = page.query_selector("button[data-item-id*='address']")
                address = address_el.query_selector("div.fontBodyMedium").inner_text().strip() if address_el and address_el.query_selector("div.fontBodyMedium") else ""
            # Clean up newlines usually present with icons
            address = address.split("\n")[-1].strip() if address else ""
        except Exception:
            address = ""
            
        # Operating Status & Weekly Hours
        status = ""
        open_hours = ""
        try:
            status_el = page.query_selector("div[data-item-id='oh'], button[data-item-id='oh']")
            if status_el:
                status_raw = status_el.inner_text().strip()
                status_lines = [line.strip() for line in status_raw.split('\n') if line.strip()]
                for line in status_lines:
                    if "open" in line.lower() or "close" in line.lower() or any(c.isalpha() for c in line):
                        status = line.replace('\u202f', ' ').strip()
                        break

                # Extract Weekly Hours Table (No fast_mode check)
                try:
                    status_el.click()
                    page.wait_for_timeout(200)
                    trs = page.query_selector_all("tr")
                    hours_list = []
                    for tr in trs:
                        text = tr.inner_text().replace('\n', ' ').strip()
                        if any(day in text.lower() for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']):
                            clean_text = re.sub(r'[^\x00-\x7F]+', '', text).strip()
                            if clean_text:
                                hours_list.append(clean_text)
                    open_hours = " | ".join(hours_list)
                except Exception:
                    pass
            else:
                # Fallback for places without expandable OH dropdown
                body_text = page.locator("body").inner_text()
                for line in body_text.split('\n'):
                    cl = line.strip()
                    ll = cl.lower()
                    if ('open' in ll or 'close' in ll) and len(cl) < 40 and ('am' in ll or 'pm' in ll or '24 hours' in ll or 'now' in ll):
                        status = cl.replace('\u202f', ' ').strip()
                        break

            # Overrides for specific explicit close states
            perm_closed = page.query_selector("span:has-text('Permanently closed'), div:has-text('Permanently closed')")
            if perm_closed and perm_closed.is_visible():
                status = "Permanently closed"

            temp_closed = page.query_selector("span:has-text('Temporarily closed'), div:has-text('Temporarily closed')")
            if temp_closed and temp_closed.is_visible():
                status = "Temporarily closed"
        except Exception:
            pass

        # Category
        category = safe_text(page, "button[data-item-id='address']").split('\n')[0] if not name else safe_text(page, "button.DkEaL")
        if not category:
            category_el = page.query_selector("button[data-tooltip*='Category']")
            category = category_el.inner_text().strip() if category_el else ""

        # Price Level
        price_level = safe_text(page, "span[aria-label*='Price:']")
        
        # Plus Code
        plus_code = safe_text(page, "button[data-tooltip*='plus code']")

        # Social Links (from Google Maps metadata if available)
        socials = {}
        try:
            # Expanded search for social footprints
            social_els = page.query_selector_all("a[data-tooltip*='social'], a[href*='facebook.com'], a[href*='instagram.com'], a[href*='linkedin.com'], a[href*='twitter.com'], a[href*='x.com'], a[href*='tiktok.com'], a[href*='youtube.com'], a[href*='upwork.com'], a[href*='snapchat.com'], a[href*='threads.net'], a[href*='pinterest.com'], a[href*='yelp.com']")
            for s_el in social_els:
                href = s_el.get_attribute("href")
                if not href: continue
                url_l = href.lower()
                if "facebook.com" in url_l: socials["Facebook"] = href
                elif "instagram.com" in url_l: socials["Instagram"] = href
                elif "linkedin.com" in url_l: socials["LinkedIn"] = href
                elif "twitter.com" in url_l or "x.com" in url_l: socials["X"] = href
                elif "tiktok.com" in url_l: socials["TikTok"] = href
                elif "youtube.com" in url_l: socials["YouTube"] = href
                elif "upwork.com" in url_l: socials["Upwork"] = href
                elif "snapchat.com" in url_l: socials["Snapchat"] = href
                elif "threads.net" in url_l: socials["Threads"] = href
                elif "pinterest.com" in url_l: socials["Pinterest"] = href
                elif "yelp.com" in url_l: socials["Yelp"] = href
        except Exception:
            pass

        return {
            "name": name,
            "category": category,
            "rating": rating,
            "reviews": reviews,
            "price_level": price_level,
            "phone": phone,
            "website": website,
            "address": address,
            "plus_code": plus_code,
            "social_links": ", ".join([f"{k}: {v}" for k, v in socials.items()]),
            "operating_status": status,
            "open_hours": open_hours,
            "maps_url": page.url,
            "emails": "",
            "whatsapp": "",
            "generated_site_url": "",
            "generated_domain": ""
        }
    except Exception as e:
        print(f" [+] Error parsing place: {e}")
        return None
