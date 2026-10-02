import os, sys, uuid, random, io
from datetime import datetime, timedelta
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))
from dotenv import load_dotenv
load_dotenv('.env')

from database.connection import fetch_all, fetch_one, execute, get_db_connection
from auth.service import hash_password
from PIL import Image, ImageDraw, ImageFont

# Ensure upload folders exist
os.makedirs("uploads/posts", exist_ok=True)
os.makedirs("uploads/stories", exist_ok=True)
os.makedirs("uploads/profile_pictures", exist_ok=True)

print("🚀 Seeding Authentic Instagram Demo Content for LittleNet...")


# Demo accounts specification
DEMO_USERS = [
    {
        "username": "ait_star_student",
        "full_name": "AIT Star Student",
        "email": "star_student@ait.edu",
        "bio": "Coding in Python 🐍 • Robotics & AI Explorer • Class 8",
        "role": "CHILD",
        "age": 13,
        "avatar_color": (59, 130, 246)
    },
    {
        "username": "maya_astronomy",
        "full_name": "Maya Sharma",
        "email": "maya_astro@kids.littlenet.internal",
        "bio": "Stargazer 🔭 • James Webb telescope fan • Learning astrophysics",
        "role": "CHILD",
        "age": 12,
        "avatar_color": (139, 92, 246)
    },
    {
        "username": "leo_robotics",
        "full_name": "Leo D'Souza",
        "email": "leo_robot@kids.littlenet.internal",
        "bio": "Building Arduino robots 🤖 • 3D Printing • Future engineer",
        "role": "CHILD",
        "age": 11,
        "avatar_color": (16, 185, 129)
    },
    {
        "username": "sam_origami",
        "full_name": "Samantha Rao",
        "email": "sam_origami@kids.littlenet.internal",
        "bio": "Paper artist 🎨 • Origami master • Creative DIY & Painting",
        "role": "CHILD",
        "age": 10,
        "avatar_color": (244, 63, 94)
    }
]

# Helper to create lightweight vibrant avatar images
def create_avatar(name, color, out_path):
    img = Image.new("RGB", (200, 200), color=color)
    draw = ImageDraw.Draw(img)
    initial = name[0].upper()
    # Draw simple circular badge with letter
    draw.ellipse([(15, 15), (185, 185)], fill=color, outline=(255, 255, 255), width=6)
    # Simple placeholder circle inside
    draw.ellipse([(50, 50), (150, 150)], fill=(255, 255, 255, 200))
    img.save(out_path, "WEBP", quality=85)
    return out_path

# Helper to create lightweight educational Instagram photo
def create_post_image(title, subtitle, bg_color, icon_text, out_path):
    img = Image.new("RGB", (600, 600), color=bg_color)
    draw = ImageDraw.Draw(img)
    # Draw subtle background pattern
    for r in range(20, 300, 40):
        draw.arc([(300 - r, 300 - r), (300 + r, 300 + r)], start=0, end=360, fill=(255, 255, 255), width=2)
    # Draw central emblem
    draw.ellipse([(200, 180), (400, 380)], fill=(255, 255, 255))
    draw.rectangle([(60, 440), (540, 540)], fill=(0, 0, 0, 180))
    img.save(out_path, "WEBP", quality=80)
    return out_path

# Ensure main parent (User 33 / akshay) exists
parent = fetch_one("SELECT user_id, email, full_name FROM users WHERE user_id=33 OR email='akshaykammar31@gmail.com'")
parent_id = parent['user_id'] if parent else None
parent_email = parent['email'] if parent else "akshaykammar31@gmail.com"
parent_name = parent['full_name'] if parent else "Akshay"

# 1. Ensure demo users exist
user_id_map = {}
akshu = fetch_one("SELECT user_id FROM users WHERE username='Akshu'")
if akshu:
    user_id_map["Akshu"] = akshu['user_id']

for du in DEMO_USERS:
    u = fetch_one("SELECT user_id FROM users WHERE username=%s", (du['username'],))
    if not u:
        avatar_file = f"uploads/profile_pictures/{du['username']}.webp"
        create_avatar(du['full_name'], du['avatar_color'], avatar_file)
        pw_hash = hash_password("Child@123")
        uid_row = execute(
            """INSERT INTO users(username, full_name, email, password_hash, role, age, account_status)
               VALUES(%s, %s, %s, %s, 'CHILD', %s, 'ACTIVE') RETURNING user_id""",
            (du['username'], du['full_name'], du['email'], pw_hash, du['age']),
            returning=True
        )
        uid = uid_row['user_id'] if uid_row else None
        execute(
            """INSERT INTO child_profiles(child_id, parent_id, full_name, bio, profile_picture)
               VALUES(%s, %s, %s, %s, %s) ON CONFLICT (child_id) DO UPDATE SET bio=EXCLUDED.bio""",
            (uid, parent_id, du['full_name'], du['bio'], avatar_file)
        )
        if parent_id:
            execute(
                """INSERT INTO parent_child_map(child_id, parent_id, parent_name, parent_email, approved, approved_at, approval_status, is_token_used)
                   VALUES(%s, %s, %s, %s, TRUE, NOW(), 'APPROVED', TRUE) ON CONFLICT DO NOTHING""",
                (uid, parent_id, parent_name, parent_email)
            )
        user_id_map[du['username']] = uid
    else:
        user_id_map[du['username']] = u['user_id']

print(f"✅ Active child creators mapped: {user_id_map}")

# 2. Link all demo users as approved friends with Akshu so feeds and stories populate!
if "Akshu" in user_id_map:
    akshu_id = user_id_map["Akshu"]
    for uname, uid in user_id_map.items():
        if uid != akshu_id:
            execute(
                """INSERT INTO followers(child_id, following_child_id, approved)
                   VALUES(%s, %s, TRUE) ON CONFLICT(child_id, following_child_id) DO UPDATE SET approved=TRUE""",
                (akshu_id, uid)
            )
            execute(
                """INSERT INTO followers(child_id, following_child_id, approved)
                   VALUES(%s, %s, TRUE) ON CONFLICT(child_id, following_child_id) DO UPDATE SET approved=TRUE""",
                (uid, akshu_id)
            )
    print("✅ Mutual follow relationships established!")

# 3. Pre-stack Instagram Posts
POSTS_DATA = [
    {
        "author": "maya_astronomy",
        "caption": "The Pillars of Creation captured by James Webb Telescope! 🌌✨ Over 6,500 light years away in the Eagle Nebula. Notice the dense gas and dust where new stars are forming!",
        "category": "Science",
        "bg_color": (15, 23, 42),
        "title": "Pillars of Creation",
        "likes": 48,
        "comments": [
            ("Akshu", "This is so beautiful! Is this real infrared photography?"),
            ("ait_star_student", "Yes! JWST NIRCam camera captured this spectrum!"),
            ("leo_robotics", "Space exploration is unreal 🚀")
        ]
    },
    {
        "author": "leo_robotics",
        "caption": "Built my first obstacle-avoidance robot using Arduino Uno and ultrasonic sensors! 🤖 Check it out turning when it detects the book in front of it!",
        "category": "Technology",
        "bg_color": (16, 185, 129),
        "title": "Arduino Robot V1",
        "likes": 64,
        "comments": [
            ("Akshu", "Super cool Leo! How did you program the servo motor?"),
            ("ait_star_student", "Clean breadboard wiring too! Great job!")
        ]
    },
    {
        "author": "sam_origami",
        "caption": "Folded a 3D Golden Crane using traditional Japanese washi paper! 🕊️ Took 45 folds and zero glue. What should I fold next?",
        "category": "Art",
        "bg_color": (244, 63, 94),
        "title": "Origami Golden Crane",
        "likes": 53,
        "comments": [
            ("maya_astronomy", "Fold a rocket or planet next! 🚀"),
            ("Akshu", "Can you make a tutorial reel on this?")
        ]
    },
    {
        "author": "ait_star_student",
        "caption": "Created a python turtle graphics animation that draws complex fractal spirals! 💻🎨 Math and programming make the best art.",
        "category": "Coding",
        "bg_color": (59, 130, 246),
        "title": "Python Turtle Fractals",
        "likes": 77,
        "comments": [
            ("leo_robotics", "Fractal geometry is awesome!"),
            ("Akshu", "Share the code on your profile please!")
        ]
    },
    {
        "author": "maya_astronomy",
        "caption": "Fun fact: A day on Venus is longer than a year on Venus! It takes Venus 243 Earth days to rotate once, but only 225 Earth days to orbit the Sun ☀️🔭",
        "category": "Education",
        "bg_color": (217, 119, 6),
        "title": "Venus Planet Facts",
        "likes": 39,
        "comments": [
            ("sam_origami", "Whoa, mind blown 🤯"),
            ("ait_star_student", "Plus it rotates backwards compared to Earth!")
        ]
    }
]

for p in POSTS_DATA:
    author_id = user_id_map.get(p["author"])
    if not author_id:
        continue
    # Create image
    img_name = f"post_{p['author']}_{uuid.uuid4().hex[:6]}.webp"
    img_path = f"uploads/posts/{img_name}"
    create_post_image(p["title"], p["category"], p["bg_color"], "✨", img_path)

    # Insert post
    post_row = execute(
        """INSERT INTO posts(child_id, media_type, media_path, caption, content_category, audience_age_group, moderation_status, is_safe, is_story, is_reel)
           VALUES(%s, 'IMAGE', %s, %s, %s, 'ALL', 'ALLOWED', TRUE, FALSE, FALSE) RETURNING post_id""",
        (author_id, img_path, p["caption"], p["category"]),
        returning=True
    )
    post_id = post_row['post_id'] if post_row else None
    
    # Insert safety verification event
    execute(
        """INSERT INTO moderation_events(content_type, content_id, child_id, decision, risk_score)
           VALUES('POST', %s, %s, 'ALLOW', 0.01)""",
        (post_id, author_id)
    )

    # Insert likes from other friends
    for other_user, other_id in user_id_map.items():
        if other_id != author_id:
            execute(
                """INSERT INTO likes(post_id, child_id)
                   VALUES(%s, %s) ON CONFLICT DO NOTHING""",
                (post_id, other_id)
            )

    # Insert comments
    for c_author, c_text in p["comments"]:
        c_id = user_id_map.get(c_author)
        if c_id:
            execute(
                """INSERT INTO comments(post_id, child_id, comment_text, moderation_status)
                   VALUES(%s, %s, %s, 'ALLOWED')""",
                (post_id, c_id, c_text)
            )

print("✅ Pre-stacked Instagram feed posts, likes & comments created!")

# 4. Pre-stack Stories
STORIES_DATA = [
    ("maya_astronomy", "Stargazing tonight! Moon at 85% illumination 🌕", (30, 41, 59), "Science"),
    ("leo_robotics", "Testing the new lidar sensor for my rover 🤖", (5, 150, 105), "Technology"),
    ("sam_origami", "Starting a giant origami peacock today! 🦚", (225, 29, 72), "Art"),
    ("ait_star_student", "Just passed level 10 of Python code challenges! 🏆", (37, 99, 235), "Coding")
]

for author, caption, color, cat in STORIES_DATA:
    author_id = user_id_map.get(author)
    if not author_id:
        continue
    img_name = f"story_{author}_{uuid.uuid4().hex[:6]}.webp"
    img_path = f"uploads/stories/{img_name}"
    create_post_image("Story", "Daily Share", color, "📸", img_path)

    s_row = execute(
        """INSERT INTO posts(child_id, media_type, media_path, caption, content_category, moderation_status, is_safe, is_story, is_reel)
           VALUES(%s, 'IMAGE', %s, %s, %s, 'ALLOWED', TRUE, TRUE, FALSE) RETURNING post_id""",
        (author_id, img_path, caption, cat),
        returning=True
    )
    s_id = s_row['post_id'] if s_row else None
    execute(
        """INSERT INTO moderation_events(content_type, content_id, child_id, decision, risk_score)
           VALUES('STORY', %s, %s, 'ALLOW', 0.01)""",
        (s_id, author_id)
    )

print("✅ Active 24-hour Stories pre-stacked!")
print("🎉 All demo content seeded successfully! Under 2MB storage utilized.")
