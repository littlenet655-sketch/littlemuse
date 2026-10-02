from pathlib import Path
import sys,html
if len(sys.argv)!=2 or not sys.argv[1].startswith('https://'):raise SystemExit('Usage: python tools/set_backend_url.py https://your-backend.example.com/')
p=Path(__file__).parents[1]/'android/app/src/main/res/values/strings.xml';u=sys.argv[1].rstrip('/')+'/';p.write_text(f'<resources><string name="app_name">LittleNet</string><string name="backend_url">{html.escape(u)}</string></resources>');print('APK backend set to',u)
