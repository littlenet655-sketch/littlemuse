"""Create or reset a LittleNet ADMIN account without hand-editing PostgreSQL."""
import argparse
import bcrypt
from database.connection import fetch_one, execute

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--email',required=True)
    ap.add_argument('--password',required=True)
    ap.add_argument('--name',default='LittleNet Admin')
    args=ap.parse_args()
    email=args.email.strip().lower()
    if len(args.password)<8: raise SystemExit('Password must be at least 8 characters.')
    h=bcrypt.hashpw(args.password.encode(),bcrypt.gensalt()).decode()
    row=fetch_one('SELECT user_id FROM users WHERE email=%s',(email,))
    if row:
        execute("UPDATE users SET full_name=%s,password_hash=%s,role='ADMIN',account_status='ACTIVE' WHERE user_id=%s",(args.name,h,row['user_id']))
        print(f'Admin updated: {email}')
    else:
        username='admin_'+email.split('@')[0]
        execute("INSERT INTO users(username,full_name,email,password_hash,role,account_status) VALUES(%s,%s,%s,%s,'ADMIN','ACTIVE')",(username,args.name,email,h))
        print(f'Admin created: {email}')
if __name__=='__main__':main()
