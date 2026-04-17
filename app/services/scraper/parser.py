import re

def safe_text(locator, selector):
    try:
        el = locator.query_selector(selector)
        return el.inner_text().strip() if el else ""
    except:
        return ""

def parse_place_details(page):
    try:
        # Wait for the title to be visible to ensure panel is loaded
        try:
            page.wait_for_selector('h1', timeout=10000)
        except:
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
        except:
            phone = ""
            
        # Website
        try:
            website_el = page.query_selector("a[data-tooltip*='website']")
            if website_el:
                website = website_el.get_attribute("href")
            else:
                website_el = page.query_selector("a[data-item-id='authority']")
                website = website_el.get_attribute("href") if website_el else ""
        except:
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
        except:
            address = ""
            
        # Operating Status & Weekly Hours
        status = ""  # Fix: initialize before try to avoid UnboundLocalError
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

                # Extract Weekly Hours Table
                try:
                    status_el.click()
                    page.wait_for_timeout(1000)
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

        return {
            "name": name,
            "rating": rating,
            "reviews": reviews,
            "phone": phone,
            "website": website,
            "address": address,
            "operating_status": status,
            "open_hours": open_hours,  # Fix: was collected but never returned
        }
    except Exception as e:
        print(f" [+] Error parsing place: {e}")
        return None