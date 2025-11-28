import sqlite3

conn = sqlite3.connect('data/quota_system.db')
cursor = conn.cursor()

print("=== 豆瓣插件配额规则 ===")
cursor.execute("SELECT * FROM quota_rules WHERE plugin_name='douban'")
rows = cursor.fetchall()

if rows:
    for row in rows:
        print(row)
else:
    print("没有找到豆瓣插件的配额规则")

conn.close()
