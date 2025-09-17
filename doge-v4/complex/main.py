# 修复导入部分，使用正确的导入路径
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.event import filter, AstrMessageEvent 
from urllib.parse import quote
import asyncio
import tempfile
import os
import re
import base64
import json
import yaml  
import time
import random
from playwright.async_api import async_playwright

@register("complex_plotter", "runnel", "复函数绘图插件", "2.0.0")
class ComplexPlotterPlugin(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        self.config = config if config is not None else {}
        self.playwright = None
        self.browser = None
        self.is_initialized = False
        # 添加auto_cleanup_files属性，避免初始化错误
        self.auto_cleanup_files = True
        # 从配置中获取代理设置，默认不使用代理
        self.proxy = self.config.get("proxy", None)
        
        # Mihomo订阅相关配置
        self.mihomo_subscription_url = self.config.get("mihomo_subscription_url", "")
        self.update_interval = self.config.get("update_interval", 3600)  # 默认每小时更新一次
        self.test_url = self.config.get("test_url", "https://www.google.com")  # 测试节点可用性的目标URL
        self.test_timeout = self.config.get("test_timeout", 10)  # 节点测试超时时间(秒)
        
        # 存储订阅节点和当前使用的代理
        self.nodes = []
        self.current_node = None
        self.last_update_time = 0
        
        # 启动定时更新任务
        if self.mihomo_subscription_url:
            asyncio.create_task(self.auto_update_subscription())

    async def initialize(self):
        """初始化Playwright并检查浏览器驱动是否已安装"""
        if self.is_initialized:
            return
            
        try:
            # 初始化Playwright
            self.playwright = await async_playwright().start()
            
            # 浏览器启动参数
            launch_options = {
                "headless": True,
                "args": [
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--window-size=1080,1080"
                ]
            }
            
            # 如果配置了代理，添加代理设置
            proxy_config = await self.get_effective_proxy()
            if proxy_config:
                launch_options["proxy"] = proxy_config
            
            # 启动浏览器
            self.browser = await self.playwright.chromium.launch(**launch_options)
            self.is_initialized = True
            logger.info("Playwright initialized successfully for complex plotter")
        except Exception as e:
            if "Executable doesn't exist at" in str(e):
                error_message = (
                    "Playwright浏览器驱动未找到，请按照以下说明安装。\n\n"
                    "--- 本地/虚拟机安装 ---\n"
                    "在终端中运行以下命令：\n"
                    "   python -m playwright install --with-deps\n\n"
                    "--- Docker容器用户 ---\n"
                    "要安装并持久化驱动，请按照以下两个步骤操作：\n\n"
                    "步骤1：在运行的容器中安装驱动（一次性操作）。\n"
                    "   找到您的容器名称/ID（例如，使用'docker ps'）并运行：\n"
                    "   docker exec -it <your_container_name_or_id> python -m playwright install --with-deps\n\n"
                    "步骤2：通过映射卷来持久化驱动。\n"
                    "   创建容器时，将主机目录映射到'/root/.cache/ms-playwright'。\n"
                    "   docker-compose.yml示例：\n"
                    "     services:\n"
                    "       your_service:\n"
                    "         volumes:\n"
                    "           - ./playwright_cache:/root/.cache/ms-playwright\n\n"
                    "   这样即使容器重启，驱动程序也会保持可用。"
                )
                logger.error(error_message)
                raise RuntimeError(error_message)
            else:
                logger.error(f"初始化Playwright时发生错误：{str(e)}")
                raise

    @filter.command_group("complex")
    def complex(self):
        pass

    @complex.command("plot")
    async def complex_plot(self, event: AstrMessageEvent):
        # 可以重新添加类型注解了，因为已经正确导入了AstrMessageEvent
        try:
            if not self.is_initialized:
                await self.initialize()
                
            message = event.message_str or ""
            eq = message[len("/complex plot"):].strip()
            encoded_eq = quote(eq)
            url = f"https://samuelj.li/complex-function-plotter/#{encoded_eq}"
            
            screenshot_data = await self.capture_screenshot(url)
        
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp.write(screenshot_data)
                tmp_path = tmp.name
            
            yield event.image_result(tmp_path)

            os.unlink(tmp_path)
            
        except Exception as e:
            logger.error(f"complex plot error: {str(e)}")
            # 确保使用正确的方式返回错误信息
            if hasattr(event, 'plain_result'):
                yield event.plain_result(f"生成图像时出错: {str(e)}")
            else:
                # 回退到使用reply方法
                yield event.reply(f"生成图像时出错: {str(e)}")

    @complex.command("custom")
    async def complex_custom(self, event: AstrMessageEvent):
        # 可以重新添加类型注解了
        try:
            if not self.is_initialized:
                await self.initialize()
                
            message = event.message_str or ""
            code = message[len("/complex custom"):].strip()
            screenshot_data = await self.execute_custom_code(code)
            
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp.write(screenshot_data)
                tmp_path = tmp.name
            
            yield event.image_result(tmp_path)
            
            os.unlink(tmp_path)
            
        except Exception as e:
            logger.error(f"complex custom error: {str(e)}")
            # 确保使用正确的方式返回错误信息
            if hasattr(event, 'plain_result'):
                yield event.plain_result(f"执行自定义代码时出错: {str(e)}")
            else:
                # 回退到使用reply方法
                yield event.reply(f"执行自定义代码时出错: {str(e)}")

    async def capture_screenshot(self, url):
        """使用Playwright捕获指定URL的截图"""
        page = None
        retry_count = 0
        max_retries = 2
        screenshot = None
        
        while retry_count <= max_retries and screenshot is None:
            try:
                page = await self.browser.new_page()
                await page.set_viewport_size({"width": 1080, "height": 1080})
                
                # 增加超时时间到120秒，并使用更灵活的等待策略
                # 先等待导航完成，再等待特定元素出现
                await page.goto(url, wait_until="load", timeout=120000)  # 使用"load"而不是"domcontentloaded"
                
                # 更宽松地等待画布元素加载，允许更多时间
                await page.wait_for_selector("canvas", timeout=30000)
                
                # 增加等待时间确保图像渲染完成
                await page.wait_for_timeout(3000)  # 额外等待3秒
                
                # 截取全屏
                screenshot = await page.screenshot(full_page=True)
                logger.info(f"成功捕获 {url} 的截图，重试次数: {retry_count}")
                return screenshot
            except Exception as e:
                retry_count += 1
                error_msg = str(e)
                logger.warning(f"捕获截图失败 (尝试 {retry_count}/{max_retries}): {error_msg}")
                if retry_count > max_retries:
                    logger.error(f"达到最大重试次数，截图失败: {error_msg}")
                    raise
                # 指数退避等待
                await page.wait_for_timeout(1000 * (2 ** (retry_count - 1)))
            finally:
                if page:
                    await page.close()

    async def execute_custom_code(self, code):
        """使用Playwright执行自定义代码并捕获截图"""
        page = None
        retry_count = 0
        max_retries = 2
        screenshot = None
        
        while retry_count <= max_retries and screenshot is None:
            try:
                page = await self.browser.new_page()
                await page.set_viewport_size({"width": 1080, "height": 1080})
                
                # 访问指定URL
                await page.goto("https://samuelj.li/complex-function-plotter/#z", wait_until="load", timeout=120000)
                
                # 点击无文本按钮
                await page.get_by_role("button").filter(has_text=re.compile(r"^$")).click()
                
                # 点击"Custom Function"按钮
                await page.get_by_role("button", name="Custom Function").click()
                
                # 操作textarea
                await page.locator("textarea").click()
                await page.locator("textarea").press("ControlOrMeta+a")
                await page.locator("textarea").fill(code)
                await page.locator("#app-bar").get_by_role("button").filter(has_text=re.compile(r"^$")).click()
                # 等待画布元素加载完成
                await page.wait_for_selector("canvas", timeout=30000)
                
                # 等待绘图完成
                await page.wait_for_timeout(3000)  # 额外等待3秒确保图像渲染完成
                
                # 截取全屏
                screenshot = await page.screenshot(full_page=True)
                logger.info(f"成功执行自定义代码并捕获截图，重试次数: {retry_count}")
                return screenshot
            except Exception as e:
                retry_count += 1
                error_msg = str(e)
                logger.warning(f"执行自定义代码失败 (尝试 {retry_count}/{max_retries}): {error_msg}")
                if retry_count > max_retries:
                    logger.error(f"达到最大重试次数，执行自定义代码失败: {error_msg}")
                    raise
                # 指数退避等待
                await asyncio.sleep(1000 * (2 ** (retry_count - 1)) / 1000)  # 转换为秒
            finally:
                if page:
                    await page.close()

    async def terminate(self):
        """插件停用时关闭浏览器和Playwright"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        self.is_initialized = False
        logger.info("Complex plotter plugin terminated, browser and playwright closed")

    async def get_effective_proxy(self):
        """获取当前有效的代理配置"""
        # 优先使用测试通过的mihomo节点
        if self.current_node:
            return self.current_node
        
        # 如果没有可用的mihomo节点，使用手动配置的代理
        if self.proxy:
            # 检查代理格式是否正确
            if "://" in self.proxy:
                # 解析代理URL
                import urllib.parse
                parsed = urllib.parse.urlparse(self.proxy)
                proxy_options = {
                    "server": f"{parsed.scheme}://{parsed.netloc}"
                }
                # 如果有用户名和密码
                if parsed.username and parsed.password:
                    proxy_options["username"] = parsed.username
                    proxy_options["password"] = parsed.password
                logger.info(f"使用手动配置的代理服务器: {parsed.scheme}://{parsed.netloc}")
                return proxy_options
            else:
                logger.warning(f"代理格式不正确: {self.proxy}，应包含协议前缀如 http:// 或 socks5://")
        
        return None
        
    async def auto_update_subscription(self):
        """定时更新mihomo订阅"""
        while True:
            try:
                # 检查是否需要更新
                current_time = time.time()
                if current_time - self.last_update_time >= self.update_interval:
                    await self.update_and_test_nodes()
                    self.last_update_time = current_time
                
                # 等待一段时间后再次检查
                await asyncio.sleep(60)  # 每分钟检查一次是否需要更新
            except Exception as e:
                logger.error(f"自动更新订阅时发生错误: {str(e)}")
                await asyncio.sleep(60)  # 出错时等待一分钟后重试
        
    async def update_and_test_nodes(self):
        """更新mihomo订阅并测试节点可用性"""
        if not self.mihomo_subscription_url:
            logger.warning("mihomo订阅URL未配置，跳过更新")
            return
        
        try:
            logger.info(f"开始更新mihomo订阅: {self.mihomo_subscription_url}")
            
            # 创建调试文件路径 - 修改为保存在插件本文件夹下
            import os
            import datetime
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            # 获取当前文件所在目录（插件目录）
            plugin_dir = os.path.dirname(os.path.abspath(__file__))
            debug_file_path = os.path.join(plugin_dir, f'mihomo_subscription_debug_{timestamp}.txt')
            
            # 获取订阅内容
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(self.mihomo_subscription_url) as response:
                    if response.status == 200:
                        subscription_content = await response.text()
                        with open(debug_file_path, 'w', encoding='utf-8', errors='replace') as f:
                            f.write(f"=== 调试信息 - {timestamp} ===\n")
                            f.write(f"=== 请求URL ===\n{self.mihomo_subscription_url}\n\n")
                            f.write(f"=== 原始订阅内容（完整） ===\n{subscription_content}\n\n")
                            f.write(f"=== 原始订阅内容（前500字符） ===\n{subscription_content[:500]}\n\n")
                            f.write(f"=== 原始订阅内容长度 ===\n{len(subscription_content)} 字符\n\n")
                        logger.debug(f"订阅内容已写入调试文件: {debug_file_path}")
                        try:
                            decoded_content = None
                            clash_config = None
                            
                            # 尝试直接处理原始内容
                            try:
                                # 首先尝试将内容直接作为YAML处理，因为Clash订阅通常是YAML格式
                                clash_config = yaml.safe_load(subscription_content)
                                decoded_content = subscription_content
                                logger.debug("原始内容已经是有效的YAML格式")
                            except yaml.YAMLError:
                                # YAML解析失败，尝试作为base64编码处理
                                logger.debug("原始内容不是有效YAML，尝试base64解码")
                                
                                # 预处理订阅内容，清理非base64字符和空白字符
                                import re
                                # 只保留base64有效字符（A-Z, a-z, 0-9, +, /, =）
                                clean_content = re.sub(r'[^A-Za-z0-9+/=]', '', subscription_content)
                                
                                # 处理base64填充问题
                                padding_needed = (4 - len(clean_content) % 4) % 4
                                clean_content += '=' * padding_needed
                                
                                try:
                                    # 尝试解码base64
                                    decoded_bytes = base64.b64decode(clean_content)
                                    
                                    # 尝试多种编码进行解码
                                    encoding_options = ['utf-8', 'latin-1', 'cp1252']
                                    for encoding in encoding_options:
                                        try:
                                            decoded_content = decoded_bytes.decode(encoding)
                                            logger.debug(f"使用{encoding}编码成功解码订阅内容")
                                            break
                                        except UnicodeDecodeError:
                                            continue
                                except Exception as e:
                                    logger.error(f"base64解码失败: {str(e)}")
                                    return
                            
                            # 如果解码成功，继续处理
                            if decoded_content and clash_config is None:
                                # 清理不可接受的字符，特别是控制字符和制表符
                                decoded_content = re.sub(r'[\x00-\x1f\x7f-\x9f\t]', ' ', decoded_content)
                                # 将多个空格替换为单个空格
                                decoded_content = re.sub(r'\s+', ' ', decoded_content)
                                
                                # 再次尝试解析
                                try:
                                    clash_config = yaml.safe_load(decoded_content)
                                    logger.debug("使用YAML格式解析订阅内容成功")
                                except yaml.YAMLError:
                                    try:
                                        clash_config = json.loads(decoded_content)
                                        logger.debug("使用JSON格式解析订阅内容成功")
                                    except json.JSONDecodeError:
                                        logger.error("所有解码和解析尝试均失败")
                                        return
                            
                            # 提取代理节点
                            if clash_config:
                                self.nodes = self._extract_proxy_nodes(clash_config)
                                logger.info(f"成功解析到 {len(self.nodes)} 个代理节点")
                            else:
                                logger.error("解析失败，未获取到有效的配置数据")
                                return
                        except Exception as e:
                            logger.error(f"解析订阅内容失败: {str(e)}")
                            # 输出部分订阅内容用于调试
                            logger.debug(f"订阅内容前100字符: {subscription_content[:100]}")
                            return
                    else:
                        logger.error(f"获取订阅内容失败，状态码: {response.status}")
                        return
                    
                    # 测试节点可用性
                    if self.nodes:
                        await self._test_nodes()
        except Exception as e:
            logger.error(f"更新订阅时发生错误: {str(e)}")
    
    def _extract_proxy_nodes(self, clash_config):
        """从Clash配置中提取代理节点，支持多种协议"""
        nodes = []
        # 检查是否存在proxies字段
        if "proxies" in clash_config:
            for proxy in clash_config["proxies"]:
                # 支持的代理类型列表
                supported_types = ["http", "https", "socks5", "ss", "vmess", "trojan"]
                
                if proxy["type"] in supported_types:
                    node = {
                        "name": proxy.get("name", f"{proxy['type']}-{proxy.get('server', 'unknown')}"),
                        "type": proxy["type"],
                        "server": proxy.get("server"),
                        "port": proxy.get("port")
                    }
                    
                    # 根据不同协议类型添加特定字段
                    if proxy["type"] in ["http", "https", "socks5"]:
                        # 这些协议的标准格式，可直接用于Playwright
                        node["proxy_url"] = f"{proxy['type']}://{proxy['server']}:{proxy['port']}"
                        # 添加认证信息
                        if "username" in proxy and "password" in proxy:
                            node["username"] = proxy["username"]
                            node["password"] = proxy["password"]
                            node["proxy_url"] = f"{proxy['type']}://{proxy['username']}:{proxy['password']}@{proxy['server']}:{proxy['port']}"
                    elif proxy["type"] == "ss":
                        # Shadowsocks协议
                        node["cipher"] = proxy.get("cipher")
                        node["password"] = proxy.get("password")
                        # 为了能在Playwright中使用，我们需要构建一个兼容格式
                        # 注意：Playwright可能不直接支持SS，这里保留完整信息供未来扩展
                    elif proxy["type"] == "vmess":
                        # V2Ray协议
                        node["uuid"] = proxy.get("uuid")
                        node["alterId"] = proxy.get("alterId")
                        node["security"] = proxy.get("security", "auto")
                        node["network"] = proxy.get("network", "tcp")
                    elif proxy["type"] == "trojan":
                        # Trojan协议
                        node["password"] = proxy.get("password")
                        node["sni"] = proxy.get("sni")
                        node["skip-cert-verify"] = proxy.get("skip-cert-verify", False)
                    
                    # 通用字段
                    if "udp" in proxy:
                        node["udp"] = proxy["udp"]
                    
                    nodes.append(node)
        return nodes
    
    async def _test_nodes(self):
        """测试代理节点可用性"""
        logger.info(f"开始测试 {len(self.nodes)} 个代理节点")
        
        # 创建一个临时浏览器实例来测试节点
        test_playwright = await async_playwright().start()
        
        available_nodes = []
        
        for node in self.nodes:
            try:
                start_time = time.time()
                
                # 配置浏览器使用当前节点
                browser = await test_playwright.chromium.launch(
                    headless=True,
                    args=["--no-sandbox"],
                    proxy=node
                )
                
                # 创建页面并测试连接
                page = await browser.new_page()
                await page.goto(self.test_url, wait_until="domcontentloaded", timeout=self.test_timeout * 1000)
                
                # 计算响应时间
                response_time = time.time() - start_time
                
                # 关闭浏览器
                await browser.close()
                
                logger.info(f"节点 {node['name']} 测试通过，响应时间: {response_time:.2f}s")
                available_nodes.append((node, response_time))
            except Exception:
                # 节点测试失败，忽略错误
                continue
        
        # 关闭测试用的Playwright实例
        await test_playwright.stop()
        
        if available_nodes:
            # 按响应时间排序，选择最快的节点
            available_nodes.sort(key=lambda x: x[1])
            best_node = available_nodes[0][0]
            
            logger.info(f"选择最佳节点: {best_node['name']}")
            
            # 更新当前使用的节点
            self.current_node = best_node
            
            # 如果浏览器已经初始化，重启浏览器以应用新的代理设置
            if self.is_initialized and self.browser:
                logger.info("重启浏览器以应用新的代理设置")
                await self.browser.close()
                self.browser = None
                await self.initialize()
        else:
            logger.warning("没有测试通过的代理节点")
            self.current_node = None