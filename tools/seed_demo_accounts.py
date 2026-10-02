import os, sys
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))
from dotenv import load_dotenv
load_dotenv('.env')

from database.connection import fetch_one, execute, get_db_connection
from auth.service import hash_password

DEMO_PASSWORD = os.getenv("LITTLENET_DEMO_PASSWORD", "")
if os.getenv("LITTLENET_ENABLE_DEMO_SEED", "").strip().lower() not in {"1", "true", "yes"}:
    raise SystemExit("Demo account seeding is disabled. Set LITTLENET_ENABLE_DEMO_SEED=1 only in an isolated demo database.")
if len(DEMO_PASSWORD) < 12:
    raise SystemExit("Set a non-committed LITTLENET_DEMO_PASSWORD of at least 12 characters before seeding demo accounts.")

def seed_demo_accounts():
    print("🔐 Seeding all Quick Demo Logins and Admin Accounts into Neon DB...")
    
    pwd_hash = hash_password(DEMO_PASSWORD)
    
    # 1. Parent: Akshay (akshaykammar31@gmail.com)
    parent_akshay = fetch_one("SELECT user_id FROM users WHERE LOWER(email)='akshaykammar31@gmail.com' OR LOWER(username)='akshay'")
    if not parent_akshay:
        p_row = execute(
            """INSERT INTO users (username, full_name, email, password_hash, role, age, account_status)
               VALUES ('akshay', 'Akshay Kammar', 'akshaykammar31@gmail.com', %s, 'PARENT', NULL, 'ACTIVE')
               RETURNING user_id""",
            (pwd_hash,),
            returning=True
        )
        parent_akshay_id = p_row['user_id']
        print(f"Created Parent: Akshay (ID: {parent_akshay_id})")
    else:
        parent_akshay_id = parent_akshay['user_id']
        execute("UPDATE users SET password_hash=%s, account_status='ACTIVE', role='PARENT', age=NULL WHERE user_id=%s", (pwd_hash, parent_akshay_id))
        print(f"Updated Parent: Akshay (ID: {parent_akshay_id})")

    # 2. Child: Akshu (Akshu)
    child_akshu = fetch_one("SELECT user_id FROM users WHERE LOWER(username)='akshu' OR LOWER(email)='akshu@kids.littlenet.internal'")
    if not child_akshu:
        c_row = execute(
            """INSERT INTO users (username, full_name, email, password_hash, role, age, account_status)
               VALUES ('Akshu', 'Akshu', 'akshu@kids.littlenet.internal', %s, 'CHILD', 11, 'ACTIVE')
               RETURNING user_id""",
            (pwd_hash,),
            returning=True
        )
        child_akshu_id = c_row['user_id']
        print(f"Created Child: Akshu (ID: {child_akshu_id})")
    else:
        child_akshu_id = child_akshu['user_id']
        execute("UPDATE users SET password_hash=%s, account_status='ACTIVE', role='CHILD', age=11 WHERE user_id=%s", (pwd_hash, child_akshu_id))
        print(f"Updated Child: Akshu (ID: {child_akshu_id})")

    # Profile for Akshu
    execute(
        """INSERT INTO child_profiles (child_id, parent_id, full_name, bio, profile_picture)
           VALUES (%s, %s, 'Akshu', 'Science & Coding student 🚀 • LittleNet explorer', 'uploads/profile_pictures/avatar_akshu.webp')
           ON CONFLICT (child_id) DO UPDATE SET
             parent_id=EXCLUDED.parent_id,
             full_name=EXCLUDED.full_name,
             bio=EXCLUDED.bio,
             profile_picture=EXCLUDED.profile_picture""",
        (child_akshu_id, parent_akshay_id)
    )

    # Link Akshu to Akshay
    execute(
        """INSERT INTO parent_child_map (
               child_id, parent_id, parent_name, parent_email, 
               approved, approved_at, approval_status, is_token_used,
               parent_verified, verified_parent_id, verified_at
           )
           VALUES (%s, %s, 'Akshay Kammar', 'akshaykammar31@gmail.com', TRUE, NOW(), 'APPROVED', TRUE, TRUE, %s, NOW())
           ON CONFLICT DO NOTHING""",
        (child_akshu_id, parent_akshay_id, parent_akshay_id)
    )
    execute(
        """UPDATE parent_child_map SET 
             parent_id=%s, approved=TRUE, approval_status='APPROVED', parent_verified=TRUE, is_token_used=TRUE, verified_parent_id=%s
           WHERE child_id=%s""",
        (parent_akshay_id, parent_akshay_id, child_akshu_id)
    )

    # 3. Parent: Mentor Parent (mentor_parent@ait.edu)
    mentor_parent = fetch_one("SELECT user_id FROM users WHERE LOWER(email)='mentor_parent@ait.edu' OR LOWER(username)='mentor_parent'")
    if not mentor_parent:
        m_row = execute(
            """INSERT INTO users (username, full_name, email, password_hash, role, age, account_status)
               VALUES ('mentor_parent', 'Mentor Parent', 'mentor_parent@ait.edu', %s, 'PARENT', NULL, 'ACTIVE')
               RETURNING user_id""",
            (pwd_hash,),
            returning=True
        )
        mentor_id = m_row['user_id']
        print(f"Created Parent: Mentor Parent (ID: {mentor_id})")
    else:
        mentor_id = mentor_parent['user_id']
        execute("UPDATE users SET password_hash=%s, account_status='ACTIVE', role='PARENT', age=NULL WHERE user_id=%s", (pwd_hash, mentor_id))
        print(f"Updated Parent: Mentor Parent (ID: {mentor_id})")

    # 4. Child: Star Student (ait_star_student)
    star = fetch_one("SELECT user_id FROM users WHERE LOWER(username)='ait_star_student' OR LOWER(email)='star_student@ait.edu'")
    if not star:
        s_row = execute(
            """INSERT INTO users (username, full_name, email, password_hash, role, age, account_status)
               VALUES ('ait_star_student', 'AIT Star Student', 'star_student@ait.edu', %s, 'CHILD', 13, 'ACTIVE')
               RETURNING user_id""",
            (pwd_hash,),
            returning=True
        )
        star_id = s_row['user_id']
        print(f"Created Child: Star Student (ID: {star_id})")
    else:
        star_id = star['user_id']
        execute("UPDATE users SET password_hash=%s, account_status='ACTIVE', role='CHILD' WHERE user_id=%s", (pwd_hash, star_id))
        print(f"Updated Child: Star Student (ID: {star_id})")

    execute(
        """INSERT INTO child_profiles (child_id, parent_id, full_name, bio, profile_picture)
           VALUES (%s, %s, 'AIT Star Student', 'Coding in Python 🐍 • Robotics & AI Explorer • Class 8', 'uploads/profile_pictures/ait_star_student.webp')
           ON CONFLICT (child_id) DO UPDATE SET
             parent_id=EXCLUDED.parent_id,
             full_name=EXCLUDED.full_name,
             bio=EXCLUDED.bio""",
        (star_id, mentor_id)
    )

    execute(
        """INSERT INTO parent_child_map (
               child_id, parent_id, parent_name, parent_email, 
               approved, approved_at, approval_status, is_token_used,
               parent_verified, verified_parent_id, verified_at
           )
           VALUES (%s, %s, 'Mentor Parent', 'mentor_parent@ait.edu', TRUE, NOW(), 'APPROVED', TRUE, TRUE, %s, NOW())
           ON CONFLICT DO NOTHING""",
        (star_id, mentor_id, mentor_id)
    )
    execute(
        """UPDATE parent_child_map SET 
             parent_id=%s, approved=TRUE, approval_status='APPROVED', parent_verified=TRUE, is_token_used=TRUE, verified_parent_id=%s
           WHERE child_id=%s""",
        (mentor_id, mentor_id, star_id)
    )

    # 5. Admin demo identity; password comes only from LITTLENET_DEMO_PASSWORD
    admin = fetch_one("SELECT user_id FROM users WHERE LOWER(email)='admin@littlenet.com' OR LOWER(username)='admin'")
    if not admin:
        a_row = execute(
            """INSERT INTO users (username, full_name, email, password_hash, role, age, account_status)
               VALUES ('admin', 'LittleNet Safety Admin', 'admin@littlenet.com', %s, 'ADMIN', NULL, 'ACTIVE')
               RETURNING user_id""",
            (pwd_hash,),
            returning=True
        )
        print(f"Created Admin: admin@littlenet.com (ID: {a_row['user_id']})")
    else:
        execute("UPDATE users SET password_hash=%s, account_status='ACTIVE', role='ADMIN', age=NULL WHERE user_id=%s", (pwd_hash, admin['user_id']))
        print(f"Updated Admin: admin@littlenet.com (ID: {admin['user_id']})")

    # 6. Update other kids passwords to Password123! as well
    for uname in ['maya_astronomy', 'leo_robotics', 'sam_origami']:
        execute("UPDATE users SET password_hash=%s, account_status='ACTIVE' WHERE LOWER(username)=%s", (pwd_hash, uname))

    # 7. Setup mutual friendships so Akshu sees everyone's posts & can chat
    all_kids = [child_akshu_id, star_id]
    for uname in ['maya_astronomy', 'leo_robotics', 'sam_origami']:
        u = fetch_one("SELECT user_id FROM users WHERE LOWER(username)=%s", (uname,))
        if u:
            all_kids.append(u['user_id'])

    for k1 in all_kids:
        for k2 in all_kids:
            if k1 != k2:
                execute(
                    """INSERT INTO followers (child_id, following_child_id, approved)
                       VALUES (%s, %s, TRUE)
                       ON CONFLICT (child_id, following_child_id) DO UPDATE SET approved=TRUE""",
                    (k1, k2)
                )

    print("Mutual follow relationships confirmed between all kids!")
    print("All demo accounts are seeded, active, and verified!")

if __name__ == '__main__':
    seed_demo_accounts()
