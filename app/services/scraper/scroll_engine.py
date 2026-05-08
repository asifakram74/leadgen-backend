import time


def scroll_results(page, max_scrolls=1500, on_links=None):
    """
    Scrolls the Google Maps sidebar and streams links as they appear.
    """
    last_height = 0
    same_count = 0
    found_links = set()

    feed = page.locator("div[role='feed']")

    for i in range(max_scrolls):
        try:
            feed.hover()
            if i == 0:
                feed.click() # Focus the feed panel once
            
            import random
            if i > 0 and i % 3 == 0:
                page.mouse.wheel(delta_x=0, delta_y=-300)
                time.sleep(0.3)
                page.mouse.move(random.randint(200, 500), random.randint(200, 500))
                
            page.keyboard.press("End") # Physically push the End key to force native browser scrolling
            feed.evaluate("el => el.scrollTo(0, el.scrollHeight)")
        except Exception:
            break

        # Sleep to allow map XHR requests - reduced for Nitro speed
        time.sleep(0.3)

        try:
            new_height = feed.evaluate("el => el.scrollHeight")
        except Exception:
            break

        # End-of-list detection — check for Google's "end" messages
        try:
            end_indicators = ["You've reached the end", "No more results", "refined your search"]
            for text in end_indicators:
                if page.get_by_text(text).is_visible():
                    return
        except Exception:
            pass

        if new_height == last_height:
            same_count += 1
        else:
            same_count = 0

        # Break on height identicalness if it has been stuck for 15 loops
        if same_count >= 15:
            loading = page.locator("div.qjESne").first
            try:
                if not loading.is_visible(timeout=500):
                    break
                else:
                    same_count -= 2 
                    time.sleep(0.5) 
            except Exception:
                break 

        last_height = new_height
