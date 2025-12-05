"""
自动打卡脚本 - 支持无限次登录尝试版本
使用 Playwright 进行自动化打卡
支持验证码识别和 GitHub Actions 定时运行
"""

import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta
from playwright.async_api import async_playwright, Page, Browser
import logging

# 北京时区 (UTC+8)
BEIJING_TZ = timezone(timedelta(hours=8))

# 配置日志 - 只输出到控制台，GitHub Actions 会自动记录
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # 只保留控制台输出，不生成日志文件
    ]
)
logger = logging.getLogger(__name__)

# 尝试导入 ddddocr 用于验证码识别
try:
    import ddddocr
    ocr = ddddocr.DdddOcr(show_ad=False)
    logger.info("ddddocr 库已加载，将使用自动验证码识别")
except ImportError:
    ocr = None
    logger.warning("ddddocr 库未安装，将需要手动输入验证码")
except Exception as e:
    ocr = None
    logger.warning(f"ddddocr 初始化失败: {e}")


class AutoCheckin:
    """自动打卡类"""
    
    def __init__(self, username: str, password: str, headless: bool = True):
        """
        初始化自动打卡
        
        Args:
            username: 用户名
            password: 密码
            headless: 是否无头模式运行
        """
        self.username = username
        self.password = password
        self.headless = headless
        self.login_url = "https://qd.dxssxdk.com/lanhu_yonghudenglu"
        self.browser: Browser = None
        self.page: Page = None
        
    async def init_browser(self):
        """初始化浏览器"""
        logger.info("正在启动浏览器...")
        playwright = await async_playwright().start()
        
        # 启动浏览器
        self.browser = await playwright.chromium.launch(
            headless=self.headless,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        
        # 创建上下文和页面
        context = await self.browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        self.page = await context.new_page()
        logger.info("浏览器启动成功")
        
    async def solve_captcha(self) -> str:
        """
        识别验证码
        
        Returns:
            验证码文本
        """
        try:
            # 等待验证码图片加载
            await self.page.wait_for_selector('div.captcha-image img', timeout=5000)
            
            # 获取验证码图片
            captcha_img = await self.page.query_selector('div.captcha-image img')
            
            if not captcha_img:
                logger.error("未找到验证码图片元素")
                return ""
            
            # 获取图片的 base64 数据
            src = await captcha_img.get_attribute('src')
            
            if not src or not src.startswith('data:image'):
                logger.error("验证码图片格式不正确")
                return ""
            
            # 提取 base64 数据
            import base64
            base64_data = src.split(',')[1]
            img_data = base64.b64decode(base64_data)
            
            # 验证码图片不再保存到文件（减少 I/O）
            # logger.debug("验证码已识别（不保存文件）")
            
            # 使用 OCR 识别验证码
            if ocr:
                captcha_text = ocr.classification(img_data)
                logger.info(f"验证码识别结果: {captcha_text}")
                return captcha_text
            else:
                # 如果没有 OCR，返回空字符串
                logger.warning("OCR 不可用，无法自动识别验证码")
                return ""
                
        except Exception as e:
            logger.error(f"验证码识别失败: {e}")
            return ""
    
    async def login_unlimited(self) -> bool:
        """
        登录系统 - 无限次重试直到成功
        
        Returns:
            是否登录成功
        """
        logger.info(f"正在打开登录页面: {self.login_url}")
        
        try:
            # 访问登录页面
            await self.page.goto(self.login_url, wait_until='networkidle', timeout=30000)
            logger.info("登录页面加载完成")
            
            # 等待页面加载
            await asyncio.sleep(2)
            
            attempt = 0
            while True:
                attempt += 1
                logger.info(f"登录尝试 {attempt} - 无限次重试模式")
                
                try:
                    # 等待用户名输入框
                    await self.page.wait_for_selector('input[type="text"][placeholder="请输入用户名"]', timeout=10000)
                    
                    # 填写用户名
                    await self.page.fill('input[type="text"][placeholder="请输入用户名"]', self.username)
                    logger.info(f"已填写用户名: {self.username}")
                    
                    # 填写密码
                    await self.page.fill('input[type="password"][placeholder="请输入密码"]', self.password)
                    logger.info("已填写密码")
                    
                    # 识别验证码
                    captcha_text = await self.solve_captcha()
                    
                    if not captcha_text:
                        logger.error("验证码识别失败，跳过本次尝试")
                        # 刷新页面重试
                        await self.page.reload(wait_until='networkidle')
                        await asyncio.sleep(2)
                        continue
                    
                    # 填写验证码
                    await self.page.fill('input[type="text"][placeholder="请输入验证码"]', captcha_text)
                    logger.info(f"已填写验证码: {captcha_text}")
                    
                    # 点击登录按钮
                    # 查找登录按钮（可能是 button 或其他元素）
                    login_button = await self.page.query_selector('button:has-text("登录"), button:has-text("登錄"), .login-btn, .submit-btn')
                    
                    if login_button:
                        await login_button.click()
                        logger.info("已点击登录按钮")
                    else:
                        # 尝试按回车键提交
                        await self.page.press('input[type="text"][placeholder="请输入验证码"]', 'Enter')
                        logger.info("已按回车键提交登录")
                    
                    # 等待登录结果
                    await asyncio.sleep(3)
                    
                    # 检查是否有弹窗需要关闭
                    try:
                        # 查找"我知道了"按钮
                        know_button = await self.page.wait_for_selector(
                            'button.van-button.van-button--default.van-button--large.van-dialog__confirm:has-text("我知道了")',
                            timeout=5000
                        )
                        if know_button:
                            await know_button.click()
                            logger.info("已关闭提示弹窗")
                            await asyncio.sleep(1)
                    except:
                        logger.info("没有发现提示弹窗")
                    
                    # 检查是否登录成功（通过 URL 变化或特定元素判断）
                    current_url = self.page.url
                    
                    if current_url != self.login_url:
                        logger.info(f"登录成功！当前页面: {current_url}")
                        return True
                    else:
                        # 检查是否有错误提示
                        logger.warning("登录可能失败，准备重试...")
                        await asyncio.sleep(2)
                        
                except Exception as e:
                    logger.error(f"登录过程出错: {e}")
                    await asyncio.sleep(2)
            
        except Exception as e:
            logger.error(f"登录失败: {e}")
            return False
    
    async def do_checkin(self) -> bool:
        """
        执行打卡操作
        
        Returns:
            是否打卡成功
        """
        try:
            logger.info("开始执行打卡操作...")
            
            # 等待页面加载
            await asyncio.sleep(3)
            
            # 截图已禁用（减少 I/O）
            
            # 打印当前 URL
            logger.info(f"当前页面 URL: {self.page.url}")
            
            # 第一步：点击"账号列表"导航
            logger.info("第一步：查找并点击'账号列表'导航...")
            account_list_clicked = False
            
            try:
                # 方式1: 通过文本查找
                account_nav = await self.page.wait_for_selector('span.nav-text:has-text("账号列表")', timeout=10000)
                if account_nav:
                    # 点击父元素（导航项）
                    await account_nav.click()
                    logger.info("✓ 已点击'账号列表'导航")
                    await asyncio.sleep(3)
                    account_list_clicked = True
                    
                    # 截图已禁用（减少 I/O）
            except Exception as e:
                logger.warning(f"点击账号列表失败，尝试其他方式: {e}")
                
                # 方式2: 查找所有导航项，点击第二个
                try:
                    nav_items = await self.page.query_selector_all('.nav-item')
                    if len(nav_items) >= 2:
                        await nav_items[1].click()  # 第二个是账号列表
                        logger.info("✓ 通过索引点击了'账号列表'导航")
                        await asyncio.sleep(3)
                        account_list_clicked = True
                except Exception as e2:
                    logger.error(f"无法点击账号列表: {e2}")
            
            if not account_list_clicked:
                logger.error("❌ 未能点击账号列表，但继续尝试...")
            
            # 第二步：查找并点击展开按钮
            logger.info("第二步：查找并点击'展开'按钮...")
            expand_clicked = False
            
            try:
                expand_button = await self.page.wait_for_selector('.expand-icon, img[alt="展开"], .icon-image', timeout=10000)
                if expand_button:
                    await expand_button.click()
                    logger.info("✓ 已点击'展开'按钮")
                    await asyncio.sleep(3)
                    expand_clicked = True
                    
                    # 截图已禁用（减少 I/O）
            except Exception as e:
                logger.warning(f"未找到展开按钮或已展开: {e}")
            
            # 第三步：查找并点击提交打卡按钮
            logger.info("第三步：查找并点击'提交打卡'按钮...")
            submit_button = None
            
            # 尝试多种方式查找提交按钮
            selectors = [
                'button.action-btn:has-text("提交打卡")',
                'button:has-text("提交打卡")',
                'button:has-text("打卡")',
                'button:has-text("提交")',
                '.action-btn',
                'button[class*="action"]',
                'button[class*="submit"]'
            ]
            
            for selector in selectors:
                try:
                    submit_button = await self.page.wait_for_selector(selector, timeout=3000)
                    if submit_button:
                        text = await submit_button.inner_text()
                        logger.info(f"✓ 通过选择器 '{selector}' 找到按钮: {text}")
                        break
                except:
                    continue
            
            # 如果还是没找到，列出所有按钮
            if not submit_button:
                try:
                    logger.info("尝试查找所有按钮...")
                    all_buttons = await self.page.query_selector_all('button')
                    logger.info(f"页面上共有 {len(all_buttons)} 个按钮")
                    
                    for idx, btn in enumerate(all_buttons):
                        try:
                            text = await btn.inner_text()
                            classes = await btn.get_attribute('class')
                            logger.info(f"按钮 {idx}: 文本='{text}', class='{classes}'")
                            
                            if '提交打卡' in text:
                                submit_button = btn
                                logger.info(f"✓ 找到'提交打卡'按钮: {text}")
                                break
                        except:
                            continue
                except Exception as e:
                    logger.warning(f"列出按钮时出错: {e}")
            
            # 第四步：点击提交按钮
            if submit_button:
                # 截图已禁用（减少 I/O）
                
                # 点击提交按钮
                await submit_button.click()
                logger.info("✓ 已点击'提交打卡'按钮")
                await asyncio.sleep(3)
                
                # 截图已禁用（减少 I/O）
                
                # 检查是否有成功提示或弹窗
                try:
                    # 查找可能的成功提示
                    success_indicators = [
                        'text="成功"',
                        'text="已提交"',
                        'text="打卡成功"',
                        '.success',
                        '.toast'
                    ]
                    
                    for indicator in success_indicators:
                        try:
                            element = await self.page.wait_for_selector(indicator, timeout=2000)
                            if element:
                                text = await element.inner_text()
                                logger.info(f"✓ 发现成功提示: {text}")
                                break
                        except:
                            continue
                except:
                    pass
                
                logger.info("=" * 50)
                logger.info("✅ 打卡操作已完成！")
                logger.info("=" * 50)
                return True
            else:
                logger.error("❌ 未找到'提交打卡'按钮")
                
                # 截图和 HTML 保存已禁用（减少 I/O）
                
                return False
                
        except Exception as e:
            logger.error(f"❌ 打卡操作失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            # 截图已禁用（减少 I/O）
            
            return False
    
    async def run(self) -> bool:
        """
        运行自动打卡流程
        
        Returns:
            是否成功
        """
        playwright = None
        try:
            # 初始化浏览器
            playwright = await async_playwright().start()
            
            # 启动浏览器
            self.browser = await playwright.chromium.launch(
                headless=self.headless,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            
            # 创建上下文和页面
            context = await self.browser.new_context(
                viewport={'width': 1280, 'height': 720},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
            self.page = await context.new_page()
            logger.info("浏览器启动成功")
            
            # 登录 - 使用无限重试模式
            if not await self.login_unlimited():
                logger.error("登录失败，终止打卡流程")
                return False
            
            # 执行打卡
            if not await self.do_checkin():
                logger.error("打卡失败")
                return False
            
            logger.info("✅ 自动打卡完成！")
            return True
            
        except Exception as e:
            logger.error(f"自动打卡流程出错: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
            
        finally:
            # 关闭浏览器
            try:
                if self.page:
                    await asyncio.sleep(2)  # 等待一下再关闭
                if self.browser:
                    await self.browser.close()
                    logger.info("浏览器已关闭")
                if playwright:
                    await playwright.stop()
            except Exception as e:
                logger.warning(f"关闭浏览器时出错: {e}")


import requests
import urllib.parse

def send_notification(app_token: str, uid: str, title: str, message: str):
    """
    发送 WxPusher 通知
    
    Args:
        app_token: WxPusher App Token
        uid: WxPusher User ID (UID)
        title: 标题
        message: 内容
    """
    if not app_token or not uid:
        return
        
    url = "https://wxpusher.zjiecode.com/api/send/message"
    
    try:
        # 构造 JSON 数据
        data = {
            "appToken": app_token,
            "content": f"# {title}\n\n{message}",
            "summary": title,
            "contentType": 3,  # 3 表示 Markdown
            "uids": [uid],
            "verifyPay": False
        }
        
        # 发送 POST 请求
        response = requests.post(url, json=data, timeout=10)
        result = response.json()
        
        if result.get('code') == 1000:
            logger.info("✅ WxPusher 通知发送成功")
        else:
            logger.warning(f"⚠️ WxPusher 通知发送失败: {result.get('msg')}")
            
    except Exception as e:
        logger.warning(f"⚠️ 发送通知时出错: {e}")

async def main():
    """主函数"""
    # 从环境变量读取账号密码（用于 GitHub Actions）
    username = os.getenv('CHECKIN_USERNAME', '')
    password = os.getenv('CHECKIN_PASSWORD', '')
    
    # 读取 WxPusher 配置
    wxpusher_app_token = os.getenv('WXPUSHER_APP_TOKEN', '')
    wxpusher_uid = os.getenv('WXPUSHER_UID', '')
    
    # 如果环境变量没有设置，从命令行参数读取
    if not username or not password:
        if len(sys.argv) >= 3:
            username = sys.argv[1]
            password = sys.argv[2]
        else:
            logger.error("请设置环境变量 CHECKIN_USERNAME 和 CHECKIN_PASSWORD，或通过命令行参数提供")
            logger.error("用法: python auto_checkin.py <用户名> <密码>")
            return
    
    # 判断运行环境
    is_github_actions = os.getenv('GITHUB_ACTIONS') == 'true'
    is_container = os.getenv('CONTAINER_ENV') == 'true' or os.path.exists('/.dockerenv')
    # 默认使用 headless 模式，除非明确设置 HEADLESS=false
    use_headless = os.getenv('HEADLESS', 'true').lower() != 'false'
    
    # 使用北京时间
    now_beijing = datetime.now(BEIJING_TZ)
    
    # 确定环境名称
    if is_github_actions:
        env_name = "GitHub Actions"
    elif is_container:
        env_name = "容器"
    else:
        env_name = "本地"
    
    logger.info(f"========== 自动打卡开始 (无限重试版) ==========")
    logger.info(f"时间: {now_beijing.strftime('%Y-%m-%d %H:%M:%S')} (北京时间)")
    logger.info(f"用户: {username}")
    logger.info(f"环境: {env_name}")
    logger.info(f"Headless 模式: {use_headless}")
    logger.info(f"重试策略: 无限次重试直到登录成功")
    if wxpusher_app_token and wxpusher_uid:
        logger.info("通知: 已配置 WxPusher")
    
    # 创建自动打卡实例
    checkin = AutoCheckin(
        username=username,
        password=password,
        headless=use_headless  # GitHub Actions 或容器环境中使用无头模式
    )
    
    # 运行打卡
    success = await checkin.run()
    
    # 获取当前北京时间信息
    now_beijing = datetime.now(BEIJING_TZ)
    current_hour = now_beijing.hour
    date_str = now_beijing.strftime('%Y年%m月%d日')  # 年月日
    time_str = now_beijing.strftime('%H:%M:%S')      # 时分秒
    
    # 根据北京时间判断是上班打卡还是下班打卡
    # 8:00 打卡时间范围: 0:00-12:00
    # 17:00 打卡时间范围: 12:00-23:59
    if current_hour < 12:
        checkin_type = "上班"
    else:
        checkin_type = "下班"
    
    if success:
        title = f"{checkin_type}打卡成功 ✅"
        message = f"""**{checkin_type}打卡成功！**

📅 **日期**: {date_str}
⏰ **时间**: {time_str} (北京时间)
👤 **用户**: {username}
✨ **状态**: 打卡成功"""
        
        logger.info(f"========== {checkin_type}打卡成功！ ==========")
        send_notification(wxpusher_app_token, wxpusher_uid, title, message)
    else:
        title = f"{checkin_type}打卡失败 ❌"
        message = f"""**{checkin_type}打卡失败！**

📅 **日期**: {date_str}
⏰ **时间**: {time_str} (北京时间)
👤 **用户**: {username}
❌ **状态**: 打卡失败，请检查日志

请及时处理或手动打卡。"""
        
        logger.error(f"========== {checkin_type}打卡失败！ ==========")
        send_notification(wxpusher_app_token, wxpusher_uid, title, message)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
