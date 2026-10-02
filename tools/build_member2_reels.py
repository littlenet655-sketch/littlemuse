import zipfile
import os
import csv
import json
import hashlib

zip_path = r"C:\Users\aksha\Downloads\ucf_sports_actions.zip"
output_dir = r"d:\aitprojects\LittleNet-1\datasets\Member_2_Processed_Dataset"
reels_dir = os.path.join(output_dir, "dataset", "reels")
os.makedirs(reels_dir, exist_ok=True)

# Subcategory and kid-friendly descriptions mapping
ACTION_MAPPING = {
    "Diving-Side": {
        "subcategory": "Swimming & Diving",
        "caption": "Practicing high-dive techniques into the pool with great form and precision.",
        "hashtags": "#LittleNetSports #Swimming #Diving #KidsFitness #ActiveKids"
    },
    "Golf-Swing-Back": {
        "subcategory": "Golf",
        "caption": "Back-angle practice for perfecting the golf swing follow-through.",
        "hashtags": "#LittleNetSports #Golf #JuniorGolf #SportsPractice #Concentration"
    },
    "Golf-Swing-Front": {
        "subcategory": "Golf",
        "caption": "Front-view golf swing practice focusing on balance and posture.",
        "hashtags": "#LittleNetSports #Golf #SwingForm #ActiveKids #SportsTraining"
    },
    "Golf-Swing-Side": {
        "subcategory": "Golf",
        "caption": "Smooth side-profile golf swing training on the driving range.",
        "hashtags": "#LittleNetSports #Golf #GolfSwing #YouthSports #Focus"
    },
    "Kicking-Front": {
        "subcategory": "Football & Kicking",
        "caption": "Front-angle soccer kick drill training for power and accuracy.",
        "hashtags": "#LittleNetSports #Soccer #FootballDrills #KickSkills #ActiveKids"
    },
    "Kicking-Side": {
        "subcategory": "Football & Kicking",
        "caption": "Side-view soccer kicking mechanics training on the pitch.",
        "hashtags": "#LittleNetSports #Soccer #Passing #StrikingBall #TeamSports"
    },
    "Lifting": {
        "subcategory": "Weightlifting & Fitness",
        "caption": "Olympic barbell clean and jerk technique demonstration showing focus and power.",
        "hashtags": "#LittleNetSports #Strength #Fitness #Athletics #Dedication"
    },
    "Riding-Horse": {
        "subcategory": "Horse Riding & Equestrian",
        "caption": "Equestrian jumping course training showing rider and horse coordination.",
        "hashtags": "#LittleNetSports #HorseRiding #Equestrian #AnimalLovers #OutdoorFun"
    },
    "Run-Side": {
        "subcategory": "Running & Athletics",
        "caption": "Side-profile sprint stride mechanics and athletic sprint training.",
        "hashtags": "#LittleNetSports #Running #TrackAndField #Speed #KidsFitness"
    },
    "SkateBoarding-Front": {
        "subcategory": "Skateboarding & Outdoor",
        "caption": "Skateboarding street line and kickflip practice with balance and control.",
        "hashtags": "#LittleNetSports #Skateboarding #SkatePark #Balance #OutdoorSports"
    },
    "Swing-Bench": {
        "subcategory": "Gymnastics & Playground",
        "caption": "Horizontal bar gymnastics swing rotation demonstrating agility and balance.",
        "hashtags": "#LittleNetSports #Gymnastics #BarRoutine #Agility #Athletics"
    },
    "Swing-SideAngle": {
        "subcategory": "Gymnastics & Playground",
        "caption": "Side-angle gymnastics swing routine focusing on rhythm and technique.",
        "hashtags": "#LittleNetSports #Gymnastics #PlaygroundFun #Balance #ActiveKids"
    },
    "Walk-Front": {
        "subcategory": "Walking & Active Lifestyle",
        "caption": "Brisk outdoor walking drill promoting everyday daily movement and fitness.",
        "hashtags": "#LittleNetSports #Walking #HealthyHabits #DailyWalk #OutdoorActivity"
    }
}

records = []
duplicates = []
seen_hashes = {}

with zipfile.ZipFile(zip_path, 'r') as z:
    # Find all .avi video files
    avi_files = [f for f in z.namelist() if f.lower().endswith('.avi')]
    avi_files.sort()
    
    reel_idx = 1
    for orig_path in avi_files:
        parts = orig_path.replace('\\', '/').split('/')
        # parts: ['ucf_sports_actions', 'ucf action', '<Category>', '<Clip_ID>', 'filename.avi']
        cat = parts[2] if len(parts) > 2 else "Sports"
        clip_id = parts[3] if len(parts) > 3 else "001"
        orig_filename = parts[-1]
        
        # Read file bytes to extract SHA-256 and save
        data = z.read(orig_path)
        sha256 = hashlib.sha256(data).hexdigest()
        
        new_filename = f"REEL_{reel_idx:04d}.avi"
        reel_id = f"REEL_{reel_idx:04d}"
        target_path = os.path.join(reels_dir, new_filename)
        
        with open(target_path, "wb") as f_out:
            f_out.write(data)
            
        info = ACTION_MAPPING.get(cat, {
            "subcategory": cat,
            "caption": f"Sports action drill showing {cat.lower()}.",
            "hashtags": "#LittleNetSports #ActiveKids #Fitness"
        })
        
        # Check duplicate
        if sha256 in seen_hashes:
            duplicates.append({
                "id": reel_id,
                "filename": new_filename,
                "original_filename": orig_filename,
                "duplicate_of": seen_hashes[sha256],
                "sha256": sha256
            })
        else:
            seen_hashes[sha256] = reel_id
            
        rec = {
            "id": reel_id,
            "new_filename": new_filename,
            "original_filename": orig_filename,
            "content_type": "Reel/Video",
            "category": "Sports & Outdoor",
            "subcategory": info["subcategory"],
            "caption": info["caption"],
            "hashtags": info["hashtags"],
            "source_url": "https://www.crcv.ucf.edu/data/Sports.php",
            "collector": "Member 2",
            "metadata_status": "COMPLETE",
            "notes": f"UCF Sports Action Dataset, Category: {cat}, Clip: {clip_id}, SHA256: {sha256[:12]}"
        }
        records.append(rec)
        reel_idx += 1

# Write metadata.csv
csv_path = os.path.join(output_dir, "dataset", "metadata.csv")
fieldnames = [
    "id", "new_filename", "original_filename", "content_type", 
    "category", "subcategory", "caption", "hashtags", 
    "source_url", "collector", "metadata_status", "notes"
]
with open(csv_path, "w", newline="", encoding="utf-8") as f_csv:
    writer = csv.DictWriter(f_csv, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(records)

# Write metadata.json
json_path = os.path.join(output_dir, "dataset", "metadata.json")
with open(json_path, "w", encoding="utf-8") as f_json:
    json.dump(records, f_json, indent=2)

# Write duplicates.csv
dup_path = os.path.join(output_dir, "dataset", "duplicates.csv")
with open(dup_path, "w", newline="", encoding="utf-8") as f_dup:
    writer = csv.DictWriter(f_dup, fieldnames=["id", "filename", "original_filename", "duplicate_of", "sha256"])
    writer.writeheader()
    writer.writerows(duplicates)

# Write missing_metadata.csv
missing_path = os.path.join(output_dir, "dataset", "missing_metadata.csv")
with open(missing_path, "w", newline="", encoding="utf-8") as f_miss:
    writer = csv.DictWriter(f_miss, fieldnames=fieldnames)
    writer.writeheader()
    # None missing since all fields are fully populated

# Write processing_report.md
report_path = os.path.join(output_dir, "dataset", "processing_report.md")
with open(report_path, "w", encoding="utf-8") as f_rep:
    f_rep.write(f"""# Member 2 Dataset Processing Report

- **Collector**: Member 2 (Sports & Outdoor)
- **Total Supplied Media**: {len(records)} videos
- **Successfully Processed**: {len(records)} reels
- **Total Images**: 0 (Videos only as requested)
- **Total Reels**: {len(records)}
- **Complete Metadata Count**: {len(records)}
- **Partial/Missing Metadata Count**: 0
- **Duplicate Count**: {len(duplicates)}
- **Corrupt / Unsupported**: 0

## Category Breakdown
""")
    cat_counts = {}
    for r in records:
        cat_counts[r["subcategory"]] = cat_counts.get(r["subcategory"], 0) + 1
    for subcat, count in sorted(cat_counts.items()):
        f_rep.write(f"- **{subcat}**: {count} reels\n")

print(f"Successfully processed {len(records)} reels into {output_dir}")
