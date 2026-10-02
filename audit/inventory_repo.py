import os
import ast
import json

root_dir = "."
inventory = {
    "backend_entrypoints": [],
    "blueprints_routes": [],
    "auth": [],
    "parent": [],
    "child": [],
    "chat_messages": [],
    "posts_reels_stories": [],
    "quiz_learning": [],
    "admin_moderator": [],
    "database_schema_migrations": [],
    "services": [],
    "ai_providers_client": [],
    "safety_modules": [],
    "r2_object_storage": [],
    "modal_deployment": [],
    "railway_vercel_deployment": [],
    "flutter_source": [],
    "android_runner_build": [],
    "ci_workflows": [],
    "tests": [],
    "tools_audits": [],
    "html_jinja_templates": [],
    "static_assets": [],
    "model_files": [],
    "dataset_ingestion": []
}

for root, dirs, files in os.walk(root_dir):
    if '.git' in root or '.venv' in root or 'node_modules' in root or '__pycache__' in root:
        continue
    for f in files:
        rel = os.path.relpath(os.path.join(root, f), root_dir).replace("\\", "/")
        lower = rel.lower()

        if rel in ["app.py", "main.py", "wsgi.py", "ai_server.py", "modal_ai.py", "run_server.py"]:
            inventory["backend_entrypoints"].append(rel)
        elif "route" in lower or "blueprint" in lower or lower.startswith("routes/"):
            inventory["blueprints_routes"].append(rel)
        elif "auth" in lower or "otp" in lower or "login" in lower:
            inventory["auth"].append(rel)
        elif "parent" in lower:
            inventory["parent"].append(rel)
        elif "child" in lower:
            inventory["child"].append(rel)
        elif "chat" in lower or "message" in lower:
            inventory["chat_messages"].append(rel)
        elif any(k in lower for k in ["post", "reel", "story", "stories", "feed"]):
            inventory["posts_reels_stories"].append(rel)
        elif any(k in lower for k in ["quiz", "learning"]):
            inventory["quiz_learning"].append(rel)
        elif any(k in lower for k in ["admin", "moderator", "moderation"]):
            inventory["admin_moderator"].append(rel)
        elif any(k in lower for k in ["schema", "migration", "database/"]):
            inventory["database_schema_migrations"].append(rel)
        elif lower.startswith("services/"):
            inventory["services"].append(rel)
        elif "modal" in lower or "ai_server" in lower:
            inventory["modal_deployment"].append(rel)
        elif "vercel" in lower or "railway" in lower or "procfile" in lower or "dockerfile" in lower:
            inventory["railway_vercel_deployment"].append(rel)
        elif lower.startswith("mobile_flutter/lib/") or lower.startswith("mobile_flutter/test/"):
            inventory["flutter_source"].append(rel)
        elif lower.startswith("android/") or lower.startswith("mobile_flutter/android/"):
            inventory["android_runner_build"].append(rel)
        elif lower.startswith(".github/"):
            inventory["ci_workflows"].append(rel)
        elif lower.startswith("tests/") or lower.startswith("test/"):
            inventory["tests"].append(rel)
        elif lower.startswith("tools/"):
            inventory["tools_audits"].append(rel)
        elif lower.endswith(".html") or "template" in lower:
            inventory["html_jinja_templates"].append(rel)
        elif lower.startswith("static/") or lower.endswith((".css", ".js", ".svg", ".ico")):
            inventory["static_assets"].append(rel)
        elif lower.endswith((".pt", ".onnx", ".tflite", ".bin", ".weights")):
            inventory["model_files"].append(rel)
        elif "dataset" in lower or "ingest" in lower or "curated" in lower:
            inventory["dataset_ingestion"].append(rel)
        elif lower.startswith("safety/"):
            inventory["safety_modules"].append(rel)
        elif "r2" in lower or "s3" in lower or "storage" in lower:
            inventory["r2_object_storage"].append(rel)

print("Inventory summary:")
for k, v in inventory.items():
    print(f"  {k:30}: {len(v)} files")

with open("audit/inventory_data.json", "w", encoding="utf-8") as f:
    json.dump(inventory, f, indent=2)
