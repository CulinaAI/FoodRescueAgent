"""
Mock Reddit monitor — posts every 45s with matched food images.
Images pre-generated and stored in /app/images_b64.json
"""
import json, time, itertools, httpx

API = "http://localhost:8080"
HEADERS = {"X-API-Key": "fR4_s3cr3t_k3y_999", "Content-Type": "application/json"}

# Load pre-generated food images (matched to post content)
with open("/app/images_b64.json") as f:
    IMGS = json.load(f)

# (subreddit, author, text, image_key)
POSTS = [
    (
        "noscrapleftbehind", "fridge_rescue_22",
        "Leftover roast chicken, sad looking broccoli, half a can of coconut milk. Any rescue recipe ideas?",
        "chicken_broccoli",
    ),
    (
        "EatCheapAndHealthy", "budget_cook_94",
        "Spinach wilting fast, eggs near expiry, have some feta and garlic. Don't want to waste — what should I make?",
        "spinach_eggs",
    ),
    (
        "mealprepsunday", "plant_pete_42",
        "Bought too much zucchini and bell peppers on sale. They will go bad by tomorrow. Help me use them up!",
        "zucchini_peppers",
    ),
    (
        "ZeroWaste", "eco_kitchen_mom",
        "3 overripe bananas, Greek yogurt expiring tomorrow, frozen berries. Smoothie or something baked?",
        "banana_yogurt",
    ),
    (
        "noscrapleftbehind", "food_saver_uk",
        "Sweet potatoes starting to sprout, kale wilting badly. Need a recipe fast before they go to waste!",
        "sweet_potato_kale",
    ),
    (
        "EatCheapAndHealthy", "thrifty_eats",
        "Half a cabbage going limp, carrots softening, got eggs and some soy sauce. What can I cook tonight?",
        "cabbage_carrots",
    ),
    (
        "mealprepsunday", "sarah_meal_prep",
        "Help! My avocados are super overripe, I have cherry tomatoes and red onion going bad too. Need quick ideas!",
        "avocado_tomato",
    ),
    (
        "ZeroWaste", "green_kitchen_life",
        "Mushrooms need to be used today, have leftover pasta, cream cheese expiring. What can I make?",
        "mushroom_pasta",
    ),
]

counter = itertools.count(1)
post_cycle = itertools.cycle(POSTS)

print("Mock monitor started — posting every 45 seconds.")
while True:
    n = next(counter)
    subreddit, author, text, img_key = next(post_cycle)
    img_b64 = IMGS.get(img_key)

    print(f"\n[#{n}] r/{subreddit} — {text[:55]}...")

    payload = {
        "text": text,
        "platform": "reddit",
        "idempotency_key": f"mock_{n:04d}_{int(time.time())}",
        "source_metadata": {
            "subreddit": subreddit,
            "post_title": text[:80],
            "post_url": f"https://reddit.com/r/{subreddit}/comments/mock{n:04d}",
            "reddit_post_id": f"mock{n:04d}",
        },
        "images": [img_b64] if img_b64 else [],
    }

    try:
        r = httpx.post(f"{API}/analyze", headers=HEADERS, json=payload, timeout=120)
        d = r.json()
        ingr = [x.get("name", "?") for x in d.get("ingredients", [])[:3]]
        print(f"     ✅ HTTP {r.status_code} | ingredients: {ingr}")
    except Exception as e:
        print(f"     ❌ {e}")

    print(f"     Next in 45s...")
    time.sleep(45)
