"""
自动日报脚本
使用 Playwright 进行自动化日报提交
支持验证码识别和 GitHub Actions 定时运行
"""

import asyncio
import os
import sys
import json
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


class AutoDailyReport:
    """自动日报类"""
    
    def __init__(self, username: str, password: str, headless: bool = True):
        """
        初始化自动日报
        
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
                    
                    # 检查是否登录成功
                    current_url = self.page.url
                    
                    if current_url != self.login_url:
                        logger.info(f"登录成功！当前页面: {current_url}")
                        return True
                    else:
                        logger.warning("登录可能失败，准备重试...")
                        await asyncio.sleep(2)
                        
                except Exception as e:
                    logger.error(f"登录过程出错: {e}")
                    await asyncio.sleep(2)
            
        except Exception as e:
            logger.error(f"登录失败: {e}")
            return False
    
    async def check_today_report_submitted(self) -> bool:
        """
        检查今天的日报是否已提交
        
        Returns:
            True: 已提交, False: 未提交
        """
        try:
            logger.info("检查今天的日报是否已提交...")
            
            # 点击"最近记录"标签
            recent_tab = await self.page.wait_for_selector('div.tab-item:has-text("最近记录")', timeout=10000)
            if recent_tab:
                await recent_tab.click()
                logger.info("已点击'最近记录'标签")
                await asyncio.sleep(2)
            
            # 点击刷新按钮
            try:
                refresh_button = await self.page.wait_for_selector('button.refresh-btn', timeout=5000)
                if refresh_button:
                    await refresh_button.click()
                    logger.info("已点击刷新按钮")
                    await asyncio.sleep(2)
            except:
                logger.warning("未找到刷新按钮")
            
            # 获取今天的日期（北京时间）
            today = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
            logger.info(f"今天的日期: {today} (北京时间)")
            
            # 查找最新的报告日期
            try:
                report_date_element = await self.page.wait_for_selector('span.report-date', timeout=5000)
                if report_date_element:
                    report_date = await report_date_element.inner_text()
                    logger.info(f"最新报告日期: {report_date}")
                    
                    if report_date == today:
                        logger.info("✅ 今天的日报已提交")
                        return True
                    else:
                        logger.info("❌ 今天的日报未提交")
                        return False
            except:
                logger.info("未找到报告记录，今天的日报未提交")
                return False
                
        except Exception as e:
            logger.error(f"检查日报状态时出错: {e}")
            return False
    
    async def submit_daily_report(self) -> bool:
        """
        提交日报
        
        Returns:
            是否提交成功
        """
        try:
            logger.info("开始提交日报...")
            
            # 等待页面加载
            await asyncio.sleep(3)
            
            # 截图已禁用（减少 I/O）
            
            # 第一步：点击"账号列表"导航
            logger.info("第一步：查找并点击'账号列表'导航...")
            try:
                account_nav = await self.page.wait_for_selector('span.nav-text:has-text("账号列表")', timeout=10000)
                if account_nav:
                    await account_nav.click()
                    logger.info("✓ 已点击'账号列表'导航")
                    await asyncio.sleep(3)
            except Exception as e:
                logger.warning(f"点击账号列表失败: {e}")
            
            # 第一步半：点击"展开"按钮
            logger.info("第一步半：查找并点击'展开'按钮...")
            try:
                # 尝试多种选择器来定位展开按钮
                expand_button = None
                
                # 方法1：通过 data-v-4e8cfa01 属性和 class 定位
                try:
                    expand_button = await self.page.wait_for_selector('div.expand-icon', timeout=5000)
                except:
                    pass
                
                # 方法2：通过 img 的 alt 属性定位
                if not expand_button:
                    try:
                        expand_button = await self.page.wait_for_selector('img[alt="展开"]', timeout=5000)
                        # 如果找到的是 img，需要点击其父元素 div
                        expand_button = await expand_button.evaluate_handle('el => el.parentElement')
                    except:
                        pass
                
                # 方法3：通过包含 Frame.png 的 img 定位
                if not expand_button:
                    try:
                        expand_button = await self.page.wait_for_selector('img[src*="Frame.png"]', timeout=5000)
                        expand_button = await expand_button.evaluate_handle('el => el.parentElement')
                    except:
                        pass
                
                if expand_button:
                    await expand_button.click()
                    logger.info("✓ 已点击'展开'按钮")
                    await asyncio.sleep(2)
                else:
                    logger.warning("未找到'展开'按钮，继续执行后续步骤")
                    
            except Exception as e:
                logger.warning(f"点击展开按钮失败: {e}，继续执行后续步骤")
            
            # 第二步：点击"生成报告"按钮
            logger.info("第二步：查找并点击'生成报告'按钮...")
            try:
                report_button = None
                
                # 尝试多种选择器来定位"生成报告"按钮
                selectors = [
                    'button.action-btn:has-text("生成报告")',  # 原始选择器
                    'button:has-text("生成报告")',  # 简化选择器
                    'div.account-actions button:has-text("生成报告")',  # 通过父容器定位
                    '//button[contains(text(), "生成报告")]',  # XPath
                ]
                
                for selector in selectors:
                    try:
                        if selector.startswith('//'):
                            # XPath 选择器
                            report_button = await self.page.wait_for_selector(f'xpath={selector}', timeout=3000)
                        else:
                            # CSS 选择器
                            report_button = await self.page.wait_for_selector(selector, timeout=3000)
                        
                        if report_button:
                            logger.info(f"✓ 使用选择器找到'生成报告'按钮: {selector}")
                            break
                    except:
                        continue
                
                if report_button:
                    await report_button.click()
                    logger.info("✓ 已点击'生成报告'按钮")
                    await asyncio.sleep(3)
                    
                    # 截图已禁用（减少 I/O）
                else:
                    logger.error("未找到'生成报告'按钮（尝试了所有选择器）")
                    # 截图已禁用（减少 I/O）
                    return False
                    
            except Exception as e:
                logger.error(f"查找'生成报告'按钮时出错: {e}")
                return False
            
            # 第三步：检查今天的日报是否已提交
            has_submitted = await self.check_today_report_submitted()
            if has_submitted:
                logger.info("✅ 今天的日报已提交，无需重复提交")
                return True
            
            # 第四步：点击"确认"按钮（如果有弹窗）
            try:
                confirm_button = await self.page.wait_for_selector('button.van-dialog__confirm:has-text("确认")', timeout=3000)
                if confirm_button:
                    await confirm_button.click()
                    logger.info("✓ 已点击确认按钮")
                    await asyncio.sleep(2)
            except:
                logger.info("没有发现确认弹窗")
            
            # 第五步：切换回"生成报告"标签
            try:
                generate_tab = await self.page.wait_for_selector('div.tab-item:has-text("生成报告")', timeout=5000)
                if generate_tab:
                    await generate_tab.click()
                    logger.info("✓ 已切换到'生成报告'标签")
                    await asyncio.sleep(2)
            except:
                logger.warning("未找到'生成报告'标签")
            
            # 第六步：点击"AI生成报告"按钮
            logger.info("第六步：点击'AI生成报告'按钮...")
            try:
                ai_button = await self.page.wait_for_selector('button.ai-generate-btn:has-text("AI生成报告")', timeout=10000)
                if ai_button:
                    await ai_button.click()
                    logger.info("✓ 已点击'AI生成报告'按钮")
                    
                    # 等待AI生成中提示
                    try:
                        generating_toast = await self.page.wait_for_selector('div.van-toast__text:has-text("AI生成中")', timeout=5000)
                        if generating_toast:
                            logger.info("⏳ AI正在生成报告...")
                    except:
                        pass
                    
                    # 等待AI生成完成（最多等待60秒）
                    logger.info("等待AI生成完成...")
                    for i in range(60):
                        try:
                            complete_toast = await self.page.wait_for_selector('div.van-toast__text:has-text("AI生成完成")', timeout=1000)
                            if complete_toast:
                                logger.info("✓ AI生成完成")
                                await asyncio.sleep(2)
                                break
                        except:
                            continue
                    else:
                        logger.warning("AI生成可能超时，但继续尝试提交")
                    
            except Exception as e:
                logger.error(f"点击AI生成报告按钮失败: {e}")
                return False
            
            # 第七步：点击"提交报告"按钮
            logger.info("第七步：点击'提交报告'按钮...")
            try:
                submit_button = await self.page.wait_for_selector('button.submit-btn:has-text("提交报告")', timeout=10000)
                if submit_button:
                    # 截图已禁用（减少 I/O）
                    
                    await submit_button.click()
                    logger.info("✓ 已点击'提交报告'按钮")
                    await asyncio.sleep(3)
                    
                    # 检查是否有成功提示
                    try:
                        success_toast = await self.page.wait_for_selector('div.van-toast__text:has-text("报告提交成功")', timeout=5000)
                        if success_toast:
                            logger.info("✅ 报告提交成功！")
                            
                            # 截图已禁用（减少 I/O）
                            
                            return True
                    except:
                        logger.warning("未检测到成功提示，但提交操作已执行")
                        return True
                        
            except Exception as e:
                logger.error(f"点击提交报告按钮失败: {e}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 提交日报失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            # 截图已禁用（减少 I/O）
            
            return False
    
    async def run(self) -> bool:
        """
        运行自动日报流程
        
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
                logger.error("登录失败，终止日报流程")
                return False
            
            # 提交日报
            if not await self.submit_daily_report():
                logger.error("日报提交失败")
                return False
            
            logger.info("✅ 自动日报完成！")
            return True
            
        except Exception as e:
            logger.error(f"自动日报流程出错: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
            
        finally:
            # 关闭浏览器
            try:
                if self.page:
                    await asyncio.sleep(2)
                if self.browser:
                    await self.browser.close()
                    logger.info("浏览器已关闭")
                if playwright:
                    await playwright.stop()
            except Exception as e:
                logger.warning(f"关闭浏览器时出错: {e}")


import requests

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
    config = {}
    # 尝试从 config.json 加载配置
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        logger.info("已从 config.json 加载配置")
    except FileNotFoundError:
        logger.info("config.json 未找到，将尝试从环境变量或命令行参数读取")
    except json.JSONDecodeError:
        logger.warning("config.json 格式错误，将忽略")

    # 优先使用配置文件，然后是环境变量，最后是命令行参数
    username = config.get('username') or os.getenv('CHECKIN_USERNAME', '')
    password = config.get('password') or os.getenv('CHECKIN_PASSWORD', '')
    
    # 读取 WxPusher 配置
    wxpusher_app_token = config.get('wxpusher_app_token') or os.getenv('WXPUSHER_APP_TOKEN', '')
    wxpusher_uid = config.get('wxpusher_uid') or os.getenv('WXPUSHER_UID', '')
    
    # 如果配置和环境变量都没有，则尝试从命令行参数读取
    if not username or not password:
        if len(sys.argv) >= 3:
            username = sys.argv[1]
            password = sys.argv[2]
        else:
            logger.error("未找到有效的凭据。请创建 config.json，或设置环境变量，或通过命令行参数提供")
            logger.error("用法: python auto_daily_report.py [用户名] [密码]")
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
    
    logger.info(f"========== 自动日报开始 ==========")
    logger.info(f"时间: {now_beijing.strftime('%Y-%m-%d %H:%M:%S')} (北京时间)")
    logger.info(f"用户: {username}")
    logger.info(f"环境: {env_name}")
    logger.info(f"Headless 模式: {use_headless}")
    if wxpusher_app_token and wxpusher_uid:
        logger.info("通知: 已配置 WxPusher")
    
    # 创建自动日报实例
    report = AutoDailyReport(
        username=username,
        password=password,
        headless=use_headless  # GitHub Actions 或容器环境中使用无头模式
    )
    
    # 运行日报
    success = await report.run()
    
    # 获取当前北京时间信息
    now_beijing = datetime.now(BEIJING_TZ)
    date_str = now_beijing.strftime('%Y年%m月%d日')  # 年月日
    time_str = now_beijing.strftime('%H:%M:%S')      # 时分秒
    
    if success:
        title = "日报完成 ✅"
        message = f"""**日报提交完成！**

📅 **日期**: {date_str}
⏰ **时间**: {time_str} (北京时间)
👤 **用户**: {username}
✨ **状态**: 日报已成功提交"""
        
        logger.info(f"========== 日报完成！ ==========")
        send_notification(wxpusher_app_token, wxpusher_uid, title, message)
    else:
        title = "日报未完成 ❌"
        message = f"""**日报提交失败！**

📅 **日期**: {date_str}
⏰ **时间**: {time_str} (北京时间)
👤 **用户**: {username}
❌ **状态**: 日报提交失败，请检查日志

请及时处理或手动提交日报。"""
        
        logger.error(f"========== 日报未完成！ ==========")
        send_notification(wxpusher_app_token, wxpusher_uid, title, message)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
