import sys
import os
sys.path.insert(0, os.path.abspath("."))
import yaml
from safety.policy_config import load_policy

policy = load_policy()
print("Policy Loaded successfully:")
print("  Policy name:", policy["policy_name"])
print("  Fail closed:", policy["fail_closed"])
print("  Thresholds:", policy["thresholds"])
print("  Adult block threshold:", policy["thresholds"]["adult_block"])
print("  Weapon block threshold:", policy["thresholds"]["weapon_block"])
print("  Weapon review threshold:", policy["thresholds"]["weapon_review"])

# Count labels in object_families
object_families = policy["object_families"]
print(f"\nObject Families count: {len(object_families)}")
total_labels = []
for fam_name, fam_data in object_families.items():
    labels = fam_data.get("labels", [])
    action = fam_data.get("action")
    total_labels.extend(labels)
    print(f"  - {fam_name:12} ({action:5}): {len(labels)} labels")

unique_configured_labels = set(total_labels)
print(f"\nTOTAL CONFIGURED OBJECT LABELS: {len(unique_configured_labels)}")

# Check loaded YOLO model coverage
model_coverage = {}
try:
    from ultralytics import YOLO
    model_path = os.path.join("models", "yolov8n.pt")
    if os.path.exists(model_path):
        model = YOLO(model_path)
        model_classes = model.names
        print(f"\nLOADED YOLO MODEL ({model_path}):")
        print(f"  Model type: YOLOv8n (COCO pre-trained)")
        print(f"  Total classes exposed by model: {len(model_classes)}")
        
        # Check intersection with configured labels
        model_class_set = set(str(v).lower().strip() for v in model_classes.values())
        matched = set()
        for cl in unique_configured_labels:
            if cl in model_class_set or any(cl in mc or mc in cl for mc in model_class_set):
                matched.add(cl)
        
        print(f"  Configured labels matching model vocabulary: {len(matched)}")
        print(f"  Configured labels NOT in standard COCO-80: {len(unique_configured_labels - matched)}")
        print("  Notice: COCO-80 contains general classes ('knife', 'scissors', etc.). Specialized weapon classes ('grenade', 'rpg', etc.) are in YAML policy for multi-model / expanded detector support.")
    else:
        print(f"YOLO model file not found at {model_path}")
except Exception as e:
    print(f"Could not load YOLO model: {e}")
