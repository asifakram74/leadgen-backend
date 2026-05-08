from concurrent.futures import ThreadPoolExecutor

# Website workers
website_executor = ThreadPoolExecutor(
    max_workers=8
)

# AI workers
ai_executor = ThreadPoolExecutor(
    max_workers=4
)