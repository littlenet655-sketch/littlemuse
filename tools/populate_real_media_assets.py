import os, sys, urllib.request, ssl, psycopg2, dotenv
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from io import BytesIO

sys.stdout.reconfigure(encoding='utf-8')
dotenv.load_dotenv('.env')

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# Ensure directories exist locally
for d in [
    'uploads/posts', 'uploads/stories', 'uploads/profile_pictures',
    'static/demo/posts', 'static/demo/stories', 'static/demo/profile_pictures'
]:
    os.makedirs(d, exist_ok=True)

print("🎨 Curating Genuine High-Fidelity Kid-Safe Media Assets...")

def fetch_and_save(url, out_path, size=(600, 600), is_story=False):
    """Download image with fallback to beautiful generative gradient artwork."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
            data = r.read()
        im = Image.open(BytesIO(data)).convert('RGB')
        # Smart crop & resize
        w, h = im.size
        target_w, target_h = size
        scale = max(target_w / w, target_h / h)
        im_resized = im.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
        # Center crop
        cw, ch = im_resized.size
        left = (cw - target_w) // 2
        top = (ch - target_h) // 2
        im_cropped = im_resized.crop((left, top, left + target_w, top + target_h))
        im_cropped.save(out_path, 'WEBP', quality=85)
        # Also copy to static/demo
        demo_path = out_path.replace('uploads/', 'static/demo/')
        im_cropped.save(demo_path, 'WEBP', quality=85)
        return True
    except Exception as e:
        print(f"  [WARN] Failed {url[:40]}: {e}. Generating fallback artwork...")
        # Generative gradient fallback
        im = Image.new('RGB', size, color=(30, 41, 59))
        draw = ImageDraw.Draw(im)
        for y in range(size[1]):
            r = int(30 + (y / size[1]) * 100)
            g = int(41 + (y / size[1]) * 80)
            b = int(59 + (y / size[1]) * 150)
            draw.line([(0, y), (size[0], y)], fill=(r, g, b))
        im.save(out_path, 'WEBP', quality=85)
        demo_path = out_path.replace('uploads/', 'static/demo/')
        im.save(demo_path, 'WEBP', quality=85)
        return False

# 1. Curate Student Profile Pictures
PROFILE_PICTURES = [
    ("Akshu", "https://images.unsplash.com/photo-1539571696357-5a69c17a67c6?w=400&auto=format&fit=crop&q=80", "uploads/profile_pictures/avatar_akshu.webp"),
    ("ait_star_student", "https://images.unsplash.com/photo-1517841905240-472988babdf9?w=400&auto=format&fit=crop&q=80", "uploads/profile_pictures/avatar_star_student.webp"),
    ("maya_astronomy", "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400&auto=format&fit=crop&q=80", "uploads/profile_pictures/avatar_maya.webp"),
    ("leo_robotics", "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400&auto=format&fit=crop&q=80", "uploads/profile_pictures/avatar_leo.webp"),
    ("sam_origami", "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=400&auto=format&fit=crop&q=80", "uploads/profile_pictures/avatar_sam.webp"),
    ("download", "https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=400&auto=format&fit=crop&q=80", "uploads/profile_pictures/download.webp"),
]

print("1. Fetching authentic student profile pictures...")
for name, url, path in PROFILE_PICTURES:
    fetch_and_save(url, path, size=(300, 300))
    print(f"   ✓ Profile pic saved: {path}")

# 2. Curate 1:1 Feed Posts (Square 600x600)
FEED_POSTS = [
    ("uploads/posts/space_pillars.webp", "https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=600&auto=format&fit=crop&q=80"),
    ("uploads/posts/space_galaxy.webp", "https://images.unsplash.com/photo-1462331940025-496dfbfc7564?w=600&auto=format&fit=crop&q=80"),
    ("uploads/posts/robot_arduino.webp", "https://images.unsplash.com/photo-1555255707-c07966088b7b?w=600&auto=format&fit=crop&q=80"),
    ("uploads/posts/origami_crane.webp", "https://images.unsplash.com/photo-1582738411706-bfc8e691d1c2?w=600&auto=format&fit=crop&q=80"),
    ("uploads/posts/coding_python.webp", "https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?w=600&auto=format&fit=crop&q=80"),
    ("uploads/posts/space_nebula.webp", "https://images.unsplash.com/photo-1446776811953-b23d57bd21aa?w=600&auto=format&fit=crop&q=80"),
    ("uploads/posts/robot_rover.webp", "https://images.unsplash.com/photo-1485827404703-89b55fcc595e?w=600&auto=format&fit=crop&q=80"),
    ("uploads/posts/origami_modular.webp", "https://images.unsplash.com/photo-1513519245088-0e12902e5a38?w=600&auto=format&fit=crop&q=80"),
    ("uploads/posts/coding_matrix.webp", "https://images.unsplash.com/photo-1555066931-4365d14bab8c?w=600&auto=format&fit=crop&q=80"),
    ("uploads/posts/science_planet.webp", "https://images.unsplash.com/photo-1614728894747-a83421e2b9c9?w=600&auto=format&fit=crop&q=80"),
]

print("2. Fetching high-quality square feed posts...")
for path, url in FEED_POSTS:
    fetch_and_save(url, path, size=(600, 600))
    print(f"   ✓ Post saved: {path}")

# 3. Curate Vertical 9:16 Stories (450x800)
STORY_POSTS = [
    ("uploads/stories/story_moon.webp", "https://images.unsplash.com/photo-1532693322450-2cb5c511067d?w=500&auto=format&fit=crop&q=80"),
    ("uploads/stories/story_circuit.webp", "https://images.unsplash.com/photo-1518770660439-4636190af475?w=500&auto=format&fit=crop&q=80"),
    ("uploads/stories/story_craft.webp", "https://images.unsplash.com/photo-1520697830682-bbb6e85e2b0b?w=500&auto=format&fit=crop&q=80"),
    ("uploads/stories/story_code.webp", "https://images.unsplash.com/photo-1542838132-92c53300491e?w=500&auto=format&fit=crop&q=80"),
]

print("3. Fetching full-height story visuals...")
for path, url in STORY_POSTS:
    fetch_and_save(url, path, size=(450, 800), is_story=True)
    print(f"   ✓ Story saved: {path}")

# 4. Connect to PostgreSQL and update DB references
print("4. Updating PostgreSQL database with real media paths and profile pics...")
db_url = os.environ.get('DATABASE_URL')
conn = psycopg2.connect(db_url)
cur = conn.cursor()

# Ensure child_profiles exist with authentic profile pictures
USER_PROFILES = [
    ("Akshu", "Akshay", "uploads/profile_pictures/avatar_akshu.webp", "Science & Coding student 🚀 • LittleNet demo account"),
    ("ait_star_student", "AIT Star Student", "uploads/profile_pictures/avatar_star_student.webp", "Coding in Python 🐍 • Robotics & AI Explorer • Class 8"),
    ("maya_astronomy", "Maya Sharma", "uploads/profile_pictures/avatar_maya.webp", "Stargazer 🔭 • James Webb telescope fan • Learning astrophysics"),
    ("leo_robotics", "Leo D'Souza", "uploads/profile_pictures/avatar_leo.webp", "Arduino & ROS Robotics Builder 🤖 • Science fair winner"),
    ("sam_origami", "Samantha Rao", "uploads/profile_pictures/avatar_sam.webp", "Origami Artist 🎨 • 3D Modular Paper Craft • DIY Maker")
]

for username, full_name, avatar_path, bio in USER_PROFILES:
    cur.execute("SELECT user_id FROM users WHERE username=%s", (username,))
    row = cur.fetchone()
    if row:
        uid = row[0]
        cur.execute("""
            INSERT INTO child_profiles (child_id, full_name, profile_picture, bio)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (child_id) DO UPDATE SET
                full_name = EXCLUDED.full_name,
                profile_picture = EXCLUDED.profile_picture,
                bio = EXCLUDED.bio
        """, (uid, full_name, avatar_path, bio))
        print(f"   ✓ Updated child_profile for {username} (id={uid}) -> {avatar_path}")

# Map posts to genuine images
POST_IMAGE_MAPPINGS = [
    # Maya Astronomy
    ("The Pillars of Creation", "uploads/posts/space_pillars.webp"),
    ("Venus is longer than", "uploads/posts/space_galaxy.webp"),
    # Leo Robotics
    ("obstacle-avoidance robot", "uploads/posts/robot_arduino.webp"),
    ("lidar sensor", "uploads/stories/story_circuit.webp"),
    # Samantha Origami
    ("Golden Crane", "uploads/posts/origami_crane.webp"),
    ("origami peacock", "uploads/stories/story_craft.webp"),
    # AIT Star Student
    ("python turtle graphics", "uploads/posts/coding_python.webp"),
    ("level 10 of Python", "uploads/stories/story_code.webp"),
    # Moon story
    ("Stargazing tonight", "uploads/stories/story_moon.webp"),
]

for caption_sub, img_path in POST_IMAGE_MAPPINGS:
    cur.execute("""
        UPDATE posts 
        SET media_path = %s 
        WHERE caption ILIKE %s
    """, (img_path, f"%{caption_sub}%"))

# For any remaining feed posts without specific mapping, assign a nice space/tech image
cur.execute("UPDATE posts SET media_path = 'uploads/posts/space_nebula.webp' WHERE media_path LIKE '%post_maya%'")
cur.execute("UPDATE posts SET media_path = 'uploads/posts/robot_rover.webp' WHERE media_path LIKE '%post_leo%'")
cur.execute("UPDATE posts SET media_path = 'uploads/posts/origami_modular.webp' WHERE media_path LIKE '%post_sam%'")
cur.execute("UPDATE posts SET media_path = 'uploads/posts/coding_matrix.webp' WHERE media_path LIKE '%post_ait%'")

conn.commit()
cur.close()
conn.close()
print("✅ Database updated successfully with genuine media paths!")
