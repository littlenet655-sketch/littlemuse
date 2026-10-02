import os
import subprocess
import time

ADB = r"C:\Users\aksha\AppData\Local\Android\Sdk\platform-tools\adb.exe"
OUT_DIR = r"audit\ui_final"
os.makedirs(OUT_DIR, exist_ok=True)

screens = [
    "01_login.png",
    "02_parent_signup.png",
    "03_email_otp.png",
    "04_parent_device_auth.png",
    "05_child_enrollment.png",
    "06_home.png",
    "07_search_explore.png",
    "08_feed.png",
    "09_reels.png",
    "10_create_post.png",
    "11_comments.png",
    "12_messages.png",
    "13_chat.png",
    "14_profile.png",
    "15_edit_profile.png",
    "16_settings.png",
    "17_privacy.png",
    "18_safety.png",
    "19_notifications.png",
    "20_screen_time.png",
    "21_parent_controls_info.png",
    "22_blocked_users.png",
    "23_muted_users.png",
    "24_help_about.png",
    "25_learning.png",
    "26_quiz.png",
    "27_discovery.png",
    "28_followers_following.png",
    "29_requests.png",
    "30_parent_dashboard.png",
    "31_parent_controls.png",
    "32_parent_screen_time.png",
    "33_parent_safety_review.png",
    "34_parent_follow_requests.png",
    "35_moderator_dashboard.png",
    "36_moderation_queue.png",
    "37_incident_detail.png",
    "38_user_admin.png",
    "39_moderator_audit.png",
]

# Stop and restart the app to begin fresh from screen 0
print("Restarting showcase app on connected physical device...")
subprocess.run([ADB, "shell", "am", "force-stop", "com.example.littlenet_native"], check=True)
subprocess.run([ADB, "shell", "am", "start", "-n", "com.example.littlenet_native/.MainActivity"], check=True)

# Allow 1.5 seconds for first screen to render
time.sleep(1.5)

print(f"Starting binary capture of {len(screens)} screens directly from device...")

for i, name in enumerate(screens):
    target = os.path.join(OUT_DIR, name)
    # capture screenshot in raw binary
    raw_png = subprocess.check_output([ADB, "exec-out", "screencap", "-p"])
    with open(target, "wb") as f:
        f.write(raw_png)
    print(f"[{i+1}/{len(screens)}] Captured {name} ({len(raw_png)} bytes)")
    # match the 2.5s showcase advancement timer
    time.sleep(2.5)

print("All screenshots successfully captured in pure binary PNG format!")
