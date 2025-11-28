import sqlite3
from datetime import datetime

conn = sqlite3.connect('data/quota_system.db')
cursor = conn.cursor()

print("=== 更新豆瓣插件配额规则 ===")

# 更新搜索配额为无限制
cursor.execute("""
    UPDATE quota_rules 
    SET daily_limit = -1, 
        description = '搜索豆瓣（无限制）',
        updated_at = ?
    WHERE plugin_name = 'douban' 
    AND action_type = 'douban_search'
""", (datetime.now().isoformat(),))

# 更新查看详情配额
cursor.execute("""
    UPDATE quota_rules 
    SET daily_limit = CASE 
        WHEN tier = 0 THEN 30
        ELSE -1
    END,
    description = '查看豆瓣评分详情',
    updated_at = ?
    WHERE plugin_name = 'douban' 
    AND action_type = 'douban_view'
""", (datetime.now().isoformat(),))

conn.commit()

print(f"更新了 {cursor.rowcount} 条记录")

# 验证更新
print("\n=== 更新后的配额规则 ===")
cursor.execute("SELECT tier, action_type, daily_limit, description FROM quota_rules WHERE plugin_name='douban' ORDER BY tier, action_type")
rows = cursor.fetchall()
for row in rows:
    tier_name = ['免费', '高级', 'VIP'][row[0]]
    print(f"{tier_name} - {row[1]}: 每日{row[2]}次 ({row[3]})")

conn.close()
print("\n✅ 配额规则更新完成！")
