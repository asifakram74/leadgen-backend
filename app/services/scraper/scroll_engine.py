import time

def scroll_results(page, max_scrolls=1500):
    """
    Scrolls Google Maps sidebar efficiently until new results stop loading.
    Loops until the end of the list is reached or no new items appear.
    """

    last_height = 0
    same_count = 0

    feed = page.locator("div[role='feed']")

    for i in range(max_scrolls):
        try:
            feed.evaluate("el => el.scrollBy(0, el.scrollHeight)")
        except:
            break

        # Slightly faster scroll interval
        time.sleep(0.7)

        try:
            new_height = feed.evaluate("el => el.scrollHeight")
        except:
            break

        # Proactive end detection
        try:
            # Look for various "end of list" or "no more results" indicators
            end_indicators = [
                "You've reached the end of the list",
                "No more results",
                "refined your search"
            ]
            for text in end_indicators:
                if page.get_by_text(text).is_visible():
                    print(f" [*] Reached the end of the list: '{text}'")
                    return
        except:
            pass

        if new_height == last_height:
            same_count += 1
        else:
            same_count = 0

        # If height hasn't changed for 3 checks, we are likely done
        if same_count >= 3:
            # One last check for hidden loading spinners
            loading = page.locator("div.qjESne").first
            if not loading.is_visible(timeout=500):
                break
            else:
                time.sleep(1.0) # Wait a bit more if loading is visible

        last_height = new_height