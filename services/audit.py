from database.connection import execute

def log(child_id,activity_type,data='{}'):
    execute('INSERT INTO activity_logs(child_id,activity_type,activity_data) VALUES(%s,%s,%s::jsonb)',(child_id,activity_type,data if isinstance(data,str) else __import__('json').dumps(data, default=str)))
