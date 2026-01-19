"""
Telegram Mini App API 路由

提供 Telegram Mini App 所需的 REST API 接口：
1. 身份认证 - 验证 Telegram initData
2. 用户信息 - 获取用户资料、积分、配额
3. 签到功能 - 每日签到、补签、排行榜
"""

import hashlib
import hmac
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, unquote

import jwt
from quart import g, jsonify, request

from astrbot import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle

from .route import Response, Route, RouteContext

# 添加插件路径
plugin_root = Path(__file__).parent.parent.parent.parent / "data" / "plugins"
if str(plugin_root) not in sys.path:
    sys.path.insert(0, str(plugin_root))


class MiniAppRoute(Route):
    """Telegram Mini App API 路由"""

    def __init__(
        self, context: RouteContext, core_lifecycle: AstrBotCoreLifecycle
    ) -> None:
        super().__init__(context)
        self.core_lifecycle = core_lifecycle
        self._db = None
        self._points_manager = None
        self._checkin_manager = None
        self._init_managers()

        self.routes = [
            # 认证
            ("/miniapp/auth", ("POST", self.auth)),
            # 用户
            ("/miniapp/user/profile", ("GET", self.get_profile)),
            ("/miniapp/user/points", ("GET", self.get_points)),
            # 签到
            ("/miniapp/checkin/daily", ("POST", self.daily_checkin)),
            ("/miniapp/checkin/status", ("GET", self.get_checkin_status)),
            ("/miniapp/checkin/calendar", ("GET", self.get_checkin_calendar)),
            ("/miniapp/checkin/leaderboard", ("GET", self.get_leaderboard)),
            ("/miniapp/checkin/makeup", ("POST", self.makeup_checkin)),
        ]
        self.register_routes()

        # 注册中间件
        self.app.before_request(self.miniapp_auth_middleware)

        logger.info("[MiniApp] Mini App API 路由已注册")

    def _init_managers(self):
        """初始化数据库和管理器"""
        try:
            from common.database_manager import DatabaseManager
            from common.points_manager import PointsManager

            # 获取数据路径
            data_path = self.config.get("data_path", "data")
            quota_db_path = os.path.join(data_path, "quota_system.db")

            self._db = DatabaseManager(quota_db_path)
            self._points_manager = PointsManager(self._db)

            # 初始化签到管理器
            from astrbot_plugin_checkin.checkin_manager import CheckinManager

            checkin_config = self._get_checkin_config()
            self._checkin_manager = CheckinManager(
                db_manager=self._db,
                points_manager=self._points_manager,
                config=checkin_config,
            )

            logger.info("[MiniApp] 管理器初始化完成")
        except ImportError as e:
            logger.warning(f"[MiniApp] 部分模块未安装，功能可能受限: {e}")
        except Exception as e:
            logger.error(f"[MiniApp] 管理器初始化失败: {e}")

    def _get_checkin_config(self) -> dict:
        """获取签到配置"""
        return {
            "rewards": {
                "base_points": 10,
                "random_points_min": 1,
                "random_points_max": 20,
                "lucky_chance": 0.1,
                "lucky_multiplier": 2.0,
                "perfect_month_bonus": 200,
                "streak_bonus": {"3": 1.2, "7": 1.5, "15": 1.8, "30": 2.0},
            },
            "makeup": {"enabled": True, "max_days": 7, "cost": 50},
        }

    # ==================== 中间件 ====================

    async def miniapp_auth_middleware(self):
        """Mini App 认证中间件"""
        # 只处理 /api/miniapp/ 路径
        if not request.path.startswith("/api/miniapp/"):
            return None

        # 登录接口不需要认证
        if request.path == "/api/miniapp/auth":
            return None

        # 验证 JWT token
        token = request.headers.get("Authorization")
        if not token:
            return jsonify(Response().error("未授权").__dict__), 401

        token = token.removeprefix("Bearer ")

        try:
            jwt_secret = self.config.get("dashboard", {}).get("jwt_secret")
            if not jwt_secret:
                return jsonify(Response().error("服务器配置错误").__dict__), 500

            payload = jwt.decode(token, jwt_secret, algorithms=["HS256"])

            # 检查是否是 Mini App token
            if payload.get("type") != "miniapp":
                return jsonify(Response().error("无效的 Token 类型").__dict__), 401

            g.tg_user_id = payload.get("tg_user_id")
            g.user_id = payload.get("user_id")  # AstrBot 内部用户 ID
            g.username = payload.get("username")

        except jwt.ExpiredSignatureError:
            return jsonify(Response().error("Token 已过期").__dict__), 401
        except jwt.InvalidTokenError:
            return jsonify(Response().error("无效的 Token").__dict__), 401

        return None

    # ==================== 认证 API ====================

    async def auth(self):
        """
        验证 Telegram initData 并返回 JWT token

        POST /api/miniapp/auth
        Body: { "init_data": "Telegram initData string" }
        """
        try:
            data = await request.json
            init_data = data.get("init_data", "")

            if not init_data:
                return jsonify(Response().error("缺少 init_data").__dict__)

            # 获取 Bot Token
            bot_token = self._get_bot_token()
            if not bot_token:
                logger.error("[MiniApp] Bot Token 未配置")
                return jsonify(Response().error("服务器配置错误").__dict__)

            # 验证 initData
            user_data = self._validate_init_data(init_data, bot_token)
            if not user_data:
                return jsonify(Response().error("身份验证失败").__dict__)

            tg_user_id = str(user_data.get("id"))
            username = user_data.get("username", "")
            first_name = user_data.get("first_name", "")

            # 生成 AstrBot 内部用户 ID
            user_id = f"telegram_{tg_user_id}"

            # 确保用户存在于数据库
            await self._ensure_user_exists(user_id, username or first_name, tg_user_id)

            # 生成 JWT token
            token = self._generate_miniapp_token(tg_user_id, user_id, username)

            return jsonify(
                Response()
                .ok(
                    {
                        "token": token,
                        "user": {
                            "tg_user_id": tg_user_id,
                            "user_id": user_id,
                            "username": username,
                            "first_name": first_name,
                        },
                    }
                )
                .__dict__
            )

        except Exception as e:
            logger.error(f"[MiniApp] 认证失败: {e}")
            return jsonify(Response().error(f"认证失败: {e!s}").__dict__)

    def _get_bot_token(self) -> str | None:
        """获取 Telegram Bot Token"""
        # 从配置中获取 Telegram 平台的 Bot Token
        miniapp_config = self.config.get("miniapp", {})
        if miniapp_config.get("bot_token"):
            return miniapp_config["bot_token"]

        # 尝试从 Telegram 平台配置获取
        platforms = self.config.get("platform", [])
        for platform in platforms:
            if platform.get("adapter") == "telegram":
                return platform.get("bot_token")

        return None

    def _validate_init_data(self, init_data: str, bot_token: str) -> dict | None:
        """
        验证 Telegram initData 签名

        参考: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
        """
        try:
            # 解析 initData
            parsed = dict(parse_qsl(init_data, keep_blank_values=True))

            # 获取 hash
            received_hash = parsed.pop("hash", None)
            if not received_hash:
                logger.warning("[MiniApp] initData 缺少 hash")
                return None

            # 构建 data_check_string
            data_check_string = "\n".join(
                f"{k}={v}" for k, v in sorted(parsed.items())
            )

            # 计算 secret_key
            secret_key = hmac.new(
                b"WebAppData", bot_token.encode(), hashlib.sha256
            ).digest()

            # 计算签名
            computed_hash = hmac.new(
                secret_key, data_check_string.encode(), hashlib.sha256
            ).hexdigest()

            # 验证签名
            if not hmac.compare_digest(computed_hash, received_hash):
                logger.warning("[MiniApp] initData 签名验证失败")
                return None

            # 检查 auth_date (可选：检查时间有效性)
            auth_date = int(parsed.get("auth_date", 0))
            if auth_date:
                now = int(datetime.now().timestamp())
                # 允许 24 小时的时间差
                if now - auth_date > 86400:
                    logger.warning("[MiniApp] initData 已过期")
                    return None

            # 解析用户数据
            user_str = parsed.get("user", "")
            if user_str:
                return json.loads(unquote(user_str))

            return None

        except Exception as e:
            logger.error(f"[MiniApp] 验证 initData 失败: {e}")
            return None

    def _generate_miniapp_token(
        self, tg_user_id: str, user_id: str, username: str
    ) -> str:
        """生成 Mini App 专用 JWT token"""
        jwt_secret = self.config.get("dashboard", {}).get("jwt_secret")
        if not jwt_secret:
            raise ValueError("JWT secret not configured")

        payload = {
            "type": "miniapp",
            "tg_user_id": tg_user_id,
            "user_id": user_id,
            "username": username,
            "exp": datetime.utcnow() + timedelta(days=7),
        }

        return jwt.encode(payload, jwt_secret, algorithm="HS256")

    async def _ensure_user_exists(
        self, user_id: str, username: str, tg_user_id: str
    ) -> None:
        """确保用户存在于数据库"""
        if not self._db:
            return

        try:
            with self._db.get_connection() as conn:
                cursor = conn.cursor()

                # 检查用户是否存在
                cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
                if cursor.fetchone():
                    # 更新最后活跃时间
                    cursor.execute(
                        "UPDATE users SET last_active_at = ? WHERE user_id = ?",
                        (datetime.now(), user_id),
                    )
                else:
                    # 创建新用户
                    cursor.execute(
                        """
                        INSERT INTO users (user_id, username, platform, platform_user_id, created_at, last_active_at)
                        VALUES (?, ?, 'telegram', ?, ?, ?)
                        """,
                        (user_id, username, tg_user_id, datetime.now(), datetime.now()),
                    )

                conn.commit()
        except Exception as e:
            logger.error(f"[MiniApp] 创建/更新用户失败: {e}")

    # ==================== 用户 API ====================

    async def get_profile(self):
        """
        获取用户资料

        GET /api/miniapp/user/profile
        """
        user_id = g.get("user_id")
        if not user_id:
            return jsonify(Response().error("未登录").__dict__)

        try:
            profile = {"user_id": user_id, "username": g.get("username", "")}

            # 获取积分信息
            if self._points_manager:
                account = await self._points_manager.get_account_info(user_id)
                if account:
                    profile["points"] = {
                        "balance": account.get("balance", 0),
                        "total_earned": account.get("total_earned", 0),
                        "total_spent": account.get("total_spent", 0),
                    }

            # 获取签到统计
            if self._checkin_manager:
                stats = self._checkin_manager._get_user_stats(user_id)
                if stats:
                    profile["checkin_stats"] = {
                        "total_days": stats.get("total_days", 0),
                        "current_streak": stats.get("current_streak", 0),
                        "max_streak": stats.get("max_streak", 0),
                        "last_checkin_date": stats.get("last_checkin_date"),
                    }

            return jsonify(Response().ok(profile).__dict__)

        except Exception as e:
            logger.error(f"[MiniApp] 获取用户资料失败: {e}")
            return jsonify(Response().error(f"获取失败: {e!s}").__dict__)

    async def get_points(self):
        """
        获取积分信息

        GET /api/miniapp/user/points
        """
        user_id = g.get("user_id")
        if not user_id:
            return jsonify(Response().error("未登录").__dict__)

        try:
            if not self._points_manager:
                return jsonify(Response().error("积分系统未初始化").__dict__)

            account = await self._points_manager.get_account_info(user_id)

            if account:
                return jsonify(
                    Response()
                    .ok(
                        {
                            "balance": account.get("balance", 0),
                            "total_earned": account.get("total_earned", 0),
                            "total_spent": account.get("total_spent", 0),
                        }
                    )
                    .__dict__
                )
            else:
                return jsonify(
                    Response()
                    .ok({"balance": 0, "total_earned": 0, "total_spent": 0})
                    .__dict__
                )

        except Exception as e:
            logger.error(f"[MiniApp] 获取积分失败: {e}")
            return jsonify(Response().error(f"获取失败: {e!s}").__dict__)

    # ==================== 签到 API ====================

    async def daily_checkin(self):
        """
        每日签到

        POST /api/miniapp/checkin/daily
        """
        user_id = g.get("user_id")
        if not user_id:
            return jsonify(Response().error("未登录").__dict__)

        try:
            if not self._checkin_manager:
                return jsonify(Response().error("签到系统未初始化").__dict__)

            result = await self._checkin_manager.daily_checkin(user_id)

            # 解析结果
            success = "✅" in result

            return jsonify(
                Response().ok({"success": success, "message": result}).__dict__
            )

        except Exception as e:
            logger.error(f"[MiniApp] 签到失败: {e}")
            return jsonify(Response().error(f"签到失败: {e!s}").__dict__)

    async def get_checkin_status(self):
        """
        获取今日签到状态

        GET /api/miniapp/checkin/status
        """
        user_id = g.get("user_id")
        if not user_id:
            return jsonify(Response().error("未登录").__dict__)

        try:
            if not self._checkin_manager:
                return jsonify(Response().error("签到系统未初始化").__dict__)

            today = date.today()
            is_checked = self._checkin_manager._is_checked_in_today(user_id, today)
            stats = self._checkin_manager._get_user_stats(user_id)

            return jsonify(
                Response()
                .ok(
                    {
                        "is_checked_today": is_checked,
                        "current_streak": stats.get("current_streak", 0)
                        if stats
                        else 0,
                        "total_days": stats.get("total_days", 0) if stats else 0,
                    }
                )
                .__dict__
            )

        except Exception as e:
            logger.error(f"[MiniApp] 获取签到状态失败: {e}")
            return jsonify(Response().error(f"获取失败: {e!s}").__dict__)

    async def get_checkin_calendar(self):
        """
        获取签到日历

        GET /api/miniapp/checkin/calendar?month=2024-01
        """
        user_id = g.get("user_id")
        if not user_id:
            return jsonify(Response().error("未登录").__dict__)

        try:
            if not self._db:
                return jsonify(Response().error("数据库未初始化").__dict__)

            # 获取月份参数
            month_str = request.args.get("month", "")
            if month_str:
                year, month = map(int, month_str.split("-"))
            else:
                today = date.today()
                year, month = today.year, today.month

            # 查询本月签到记录
            first_day = date(year, month, 1)
            if month == 12:
                last_day = date(year + 1, 1, 1) - timedelta(days=1)
            else:
                last_day = date(year, month + 1, 1) - timedelta(days=1)

            with self._db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT checkin_date, points_earned, is_lucky, streak_days
                    FROM checkin_records
                    WHERE user_id = ? AND checkin_date >= ? AND checkin_date <= ?
                    ORDER BY checkin_date
                    """,
                    (user_id, first_day, last_day),
                )

                records = []
                for row in cursor.fetchall():
                    records.append(
                        {
                            "date": row["checkin_date"],
                            "points": row["points_earned"],
                            "is_lucky": bool(row["is_lucky"]),
                            "streak": row["streak_days"],
                        }
                    )

            return jsonify(
                Response()
                .ok(
                    {
                        "year": year,
                        "month": month,
                        "records": records,
                        "total_days": len(records),
                    }
                )
                .__dict__
            )

        except Exception as e:
            logger.error(f"[MiniApp] 获取签到日历失败: {e}")
            return jsonify(Response().error(f"获取失败: {e!s}").__dict__)

    async def get_leaderboard(self):
        """
        获取签到排行榜

        GET /api/miniapp/checkin/leaderboard?type=streak&limit=20
        """
        try:
            if not self._db:
                return jsonify(Response().error("数据库未初始化").__dict__)

            rank_type = request.args.get("type", "streak")  # streak | total | points
            limit = min(int(request.args.get("limit", 20)), 100)

            with self._db.get_connection() as conn:
                cursor = conn.cursor()

                if rank_type == "streak":
                    # 连续签到排行
                    cursor.execute(
                        """
                        SELECT cs.user_id, u.username, cs.current_streak as value
                        FROM checkin_stats cs
                        LEFT JOIN users u ON cs.user_id = u.user_id
                        ORDER BY cs.current_streak DESC
                        LIMIT ?
                        """,
                        (limit,),
                    )
                elif rank_type == "total":
                    # 累计签到排行
                    cursor.execute(
                        """
                        SELECT cs.user_id, u.username, cs.total_days as value
                        FROM checkin_stats cs
                        LEFT JOIN users u ON cs.user_id = u.user_id
                        ORDER BY cs.total_days DESC
                        LIMIT ?
                        """,
                        (limit,),
                    )
                else:  # points
                    # 积分排行
                    cursor.execute(
                        """
                        SELECT pa.user_id, u.username, pa.balance as value
                        FROM points_accounts pa
                        LEFT JOIN users u ON pa.user_id = u.user_id
                        ORDER BY pa.balance DESC
                        LIMIT ?
                        """,
                        (limit,),
                    )

                leaderboard = []
                for idx, row in enumerate(cursor.fetchall(), 1):
                    leaderboard.append(
                        {
                            "rank": idx,
                            "user_id": row["user_id"],
                            "username": row["username"] or "匿名用户",
                            "value": row["value"],
                        }
                    )

            return jsonify(
                Response()
                .ok({"type": rank_type, "leaderboard": leaderboard})
                .__dict__
            )

        except Exception as e:
            logger.error(f"[MiniApp] 获取排行榜失败: {e}")
            return jsonify(Response().error(f"获取失败: {e!s}").__dict__)

    async def makeup_checkin(self):
        """
        补签

        POST /api/miniapp/checkin/makeup
        Body: { "date": "2024-01-15" 或 "1" (昨天) }
        """
        user_id = g.get("user_id")
        if not user_id:
            return jsonify(Response().error("未登录").__dict__)

        try:
            if not self._checkin_manager:
                return jsonify(Response().error("签到系统未初始化").__dict__)

            data = await request.json
            date_str = data.get("date", "")

            if not date_str:
                return jsonify(Response().error("请指定补签日期").__dict__)

            result = await self._checkin_manager.makeup_checkin(user_id, date_str)

            success = "✅" in result

            return jsonify(
                Response().ok({"success": success, "message": result}).__dict__
            )

        except Exception as e:
            logger.error(f"[MiniApp] 补签失败: {e}")
            return jsonify(Response().error(f"补签失败: {e!s}").__dict__)
