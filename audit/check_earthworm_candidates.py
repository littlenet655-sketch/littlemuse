import os
import zipfile
import hashlib

def get_sha256(data):
    return hashlib.sha256(data).hexdigest()

print("Checking candidate locations for earthworm / gardening images...")

# 1. Check inside database.zip
db_zip = r"D:\aitprojects\database.zip"
if os.path.exists(db_zip):
    print(f"\n--- Checking {db_zip} ---")
    with zipfile.ZipFile(db_zip, 'r') as zf:
        for name in zf.namelist():
            if any(k in name.lower() for k in ['worm', 'earthworm', 'vermi', 'garden']):
                print("  Found in database.zip:", name)

# 2. Check Member3Gardening.zip inside D:\aitprojects\database
gardening_zip = r"D:\aitprojects\database\Member3Gardening.zip"
if os.path.exists(gardening_zip):
    print(f"\n--- Checking {gardening_zip} ---")
    with zipfile.ZipFile(gardening_zip, 'r') as zf:
        for info in zf.infolist():
            data = zf.read(info.filename)
            h = get_sha256(data)
            print(f"  {info.filename} ({info.file_size} bytes, sha256={h[:12]}...)")

# 3. Check D:\aitprojects\LittleNet-complete and LittleNet-fixed-submission-ready
for folder in [r"D:\aitprojects\LittleNet-complete", r"D:\aitprojects\LittleNet-fixed-submission-ready"]:
    if os.path.exists(folder):
        print(f"\n--- Checking folder {folder} ---")
        for root, dirs, files in os.walk(folder):
            if '.git' in root or 'node_modules' in root or '.venv' in root:
                continue
            for f in files:
                if any(k in f.lower() for k in ['worm', 'earthworm', 'vermi', 'garden']) and f.lower().endswith(('.jpg', '.png', '.jpeg', '.webp')):
                    p = os.path.join(root, f)
                    with open(p, 'rb') as img_f:
                        h = get_sha256(img_f.read())
                    print(f"  Found: {p} ({os.path.getsize(p)} bytes, sha256={h[:12]}...)")
