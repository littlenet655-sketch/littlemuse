$adb = "C:\Users\aksha\AppData\Local\Android\Sdk\platform-tools\adb.exe"
$outDir = "audit\ui_final"

if (-not (Test-Path $outDir)) {
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
}

$screens = @(
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
    "39_moderator_audit.png"
)

Write-Host "Starting capture sequence for $($screens.Count) screens..."

# Initial delay for first screen to settle
Start-Sleep -Milliseconds 1200

for ($i = 0; $i -lt $screens.Count; $i++) {
    $name = $screens[$i]
    $targetPath = Join-Path $outDir $name
    Write-Host "Capturing ($($i+1)/$($screens.Count)): $name"
    
    # Capture via adb
    & $adb exec-out screencap -p > $targetPath
    
    # Wait for next screen transition (matches 2500ms showcase timer)
    Start-Sleep -Milliseconds 2500
}

Write-Host "Capture sequence complete! All screens written to $outDir."
