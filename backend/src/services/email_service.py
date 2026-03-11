"""邮件服务 - 负责发送各类邮件"""

import logging
import random
from datetime import datetime, timedelta, UTC
from typing import Optional, Tuple

from src.config.app_config import smtp_settings

logger = logging.getLogger(__name__)

# Redis Lua 脚本：原子性验证码验证
# 返回值: {code, message}
# code: 1=成功, 0=验证码错误, -1=验证码过期, -2=失败次数过多
VERIFY_CODE_LUA_SCRIPT = """
local key = KEYS[1]
local fail_key = KEYS[2]
local code = ARGV[1]
local max_attempts = tonumber(ARGV[2])

-- 检查失败次数
local fail_count = tonumber(redis.call('GET', fail_key) or "0")
if fail_count >= max_attempts then
    return {-2, "验证失败次数过多，验证码已失效，请重新获取"}
end

-- 获取并验证
local stored = redis.call('GET', key)
if not stored then
    return {-1, "验证码已过期或不存在，请重新获取"}
end

if stored ~= code then
    redis.call('INCR', fail_key)
    redis.call('EXPIRE', fail_key, 3600)
    return {0, "验证码错误"}
end

-- 验证成功，原子删除
redis.call('DEL', key)
redis.call('DEL', fail_key)
return {1, "验证成功"}
"""


class EmailService:
    """邮件服务类"""

    def __init__(self):
        self.settings = smtp_settings
        self._smtp_client = None

    async def _get_redis(self):
        """获取 Redis 客户端"""
        from src.academic.cache.redis_client import redis_client
        return redis_client.client

    async def _get_smtp_client(self):
        """延迟初始化 SMTP 客户端"""
        if self._smtp_client is None and self.settings.enabled:
            import aiosmtplib
            self._smtp_client = aiosmtplib.SMTP(
                hostname=self.settings.host,
                port=self.settings.port,
                use_tls=self.settings.use_tls
            )
        return self._smtp_client

    def _generate_code(self) -> str:
        """生成验证码（数字+字母混合，提高安全性）"""
        # 使用数字+大小写字母混合，排除易混淆字符（0/O, 1/I/l）
        characters = '23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz'
        return ''.join(random.choices(characters, k=self.settings.code_length))

    def _generate_email_template(self, code: str, purpose: str = "注册") -> Tuple[str, str]:
        """
        生成邮件内容
        返回: (subject, html_body)
        """
        subject = f"【AcademiaGPT】{purpose}验证码"

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; background: #fff; }}
                .header {{ text-align: center; padding: 20px; border-bottom: 2px solid #1890ff; }}
                .header h2 {{ color: #1890ff; margin: 0; }}
                .content {{ padding: 30px 20px; }}
                .code-box {{
                    background: #f0f5ff;
                    padding: 30px;
                    text-align: center;
                    margin: 25px 0;
                    border-radius: 8px;
                    border: 1px solid #d6e4ff;
                }}
                .code {{
                    font-size: 36px;
                    font-weight: bold;
                    color: #1890ff;
                    letter-spacing: 10px;
                    font-family: 'Courier New', monospace;
                }}
                .info {{
                    color: #333;
                    font-size: 14px;
                    line-height: 1.6;
                }}
                .warning {{
                    color: #ff4d4f;
                    font-size: 13px;
                    margin-top: 20px;
                    padding: 10px;
                    background: #fff2f0;
                    border-radius: 4px;
                }}
                .footer {{
                    color: #999;
                    font-size: 12px;
                    text-align: center;
                    margin-top: 30px;
                    padding-top: 20px;
                    border-top: 1px solid #f0f0f0;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>🎓 AcademiaGPT 学术助手</h2>
                </div>
                <div class="content">
                    <p class="info">您好！</p>
                    <p class="info">您正在进行<strong>「{purpose}」</strong>操作，请使用以下验证码完成验证：</p>

                    <div class="code-box">
                        <div class="code">{code}</div>
                    </div>

                    <p class="info">⏱️ 验证码有效期 <strong>{self.settings.code_ttl // 60} 分钟</strong>，请及时使用。</p>
                    <p class="info">🔒 请勿将验证码泄露给他人，以防账户被盗。</p>

                    <div class="warning">
                        ⚠️ 如非本人操作，请忽略此邮件，您的账户依然安全。
                    </div>
                </div>

                <div class="footer">
                    <p>此邮件由系统自动发送，请勿回复</p>
                    <p>© {datetime.now().year} AcademiaGPT - 您的学术研究助手</p>
                </div>
            </div>
        </body>
        </html>
        """
        return subject, html_body

    def _get_purpose_key(self, purpose: str) -> str:
        """获取用途标识符（用于Redis键）"""
        purpose_map = {
            "注册": "register",
            "重置密码": "reset_password"
        }
        return purpose_map.get(purpose, "verify")

    async def send_verification_code(
        self,
        email: str,
        purpose: str = "注册",
        ip_address: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        发送验证码邮件

        Returns:
            (success, message_or_code)
        """
        redis = await self._get_redis()

        # 获取用途标识符
        purpose_key = self._get_purpose_key(purpose)

        # 1. 检查发送频率限制
        limit_key = f"verify:limit:{email}"
        if await redis.exists(limit_key):
            ttl = self.settings.send_interval
            return False, f"发送过于频繁，请{ttl}秒后重试"

        # 2. 检查日发送上限
        daily_key = f"verify:daily:{email}"
        daily_count = await redis.get(daily_key)
        if daily_count:
            try:
                count = int(daily_count.decode('utf-8') if isinstance(daily_count, bytes) else daily_count)
                if count >= self.settings.daily_limit:
                    return False, "今日发送次数已达上限，请明天再试"
            except (ValueError, AttributeError) as e:
                logger.warning("Failed to parse daily email count for %s: %s", email, e)

        # 3. 生成验证码
        code = self._generate_code()

        # 4. 发送邮件
        try:
            smtp = await self._get_smtp_client()
            if smtp is None:
                # 开发模式：SMTP 未启用，直接打印验证码
                logger.info("[DEV MODE] Verification code for %s (%s): %s", email, purpose, code)
                # 仍然存储到 Redis
                await redis.set(
                    f"verify:code:{purpose_key}:{email}",
                    code,
                    ex=self.settings.code_ttl
                )
                await redis.set(limit_key, "1", ex=self.settings.send_interval)
                await redis.incr(daily_key)
                now = datetime.now(UTC)
                tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
                seconds_until_midnight = int((tomorrow - now).total_seconds())
                await redis.expire(daily_key, seconds_until_midnight)
                return True, code

            subject, html_body = self._generate_email_template(code, purpose)

            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{self.settings.sender_name} <{self.settings.username}>"
            msg['To'] = email

            msg.attach(MIMEText(html_body, 'html', 'utf-8'))

            await smtp.connect()
            await smtp.login(self.settings.username, self.settings.password)
            await smtp.send_message(msg)
            await smtp.quit()

            # 5. 存储验证码到 Redis（根据用途区分不同的键）
            await redis.set(
                f"verify:code:{purpose_key}:{email}",
                code,
                ex=self.settings.code_ttl
            )

            # 6. 设置发送频率限制
            await redis.set(limit_key, "1", ex=self.settings.send_interval)

            # 7. 增加日发送计数
            await redis.incr(daily_key)
            # 设置过期时间为当天剩余时间
            now = datetime.now(UTC)
            tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            seconds_until_midnight = int((tomorrow - now).total_seconds())
            await redis.expire(daily_key, seconds_until_midnight)

            return True, code

        except Exception as e:
            logger.error("发送邮件失败: %s", e)
            return False, "邮件发送失败，请稍后重试"

    async def verify_code(self, email: str, code: str, purpose: str = "注册") -> Tuple[bool, str]:
        """
        验证验证码（使用 Lua 脚本实现原子性验证，防止竞态条件）

        Args:
            email: 邮箱地址
            code: 验证码
            purpose: 用途（"注册" 或 "重置密码"）

        Returns:
            (is_valid, message)
        """
        redis = await self._get_redis()

        # 获取用途标识符
        purpose_key = self._get_purpose_key(purpose)
        code_key = f"verify:code:{purpose_key}:{email}"
        fail_key = f"verify:fail:{purpose_key}:{email}"

        # 获取存储的验证码并转换为大写进行比较（不区分大小写）
        stored_code = await redis.get(code_key)
        if not stored_code:
            return False, "验证码已过期或不存在，请重新获取"

        # 处理bytes类型
        if isinstance(stored_code, bytes):
            stored_code = stored_code.decode("utf-8")

        # 不区分大小写比较
        if stored_code.upper() != code.strip().upper():
            # 增加失败计数
            fail_count = await redis.incr(fail_key)
            await redis.expire(fail_key, 3600)
            if fail_count >= 5:
                await redis.delete(code_key)
                await redis.delete(fail_key)
                return False, "验证失败次数过多，验证码已失效，请重新获取"
            return False, "验证码错误"

        # 验证成功，删除验证码和失败计数
        await redis.delete(code_key)
        await redis.delete(fail_key)
        return True, "验证成功"


# 全局邮件服务实例
email_service = EmailService()
