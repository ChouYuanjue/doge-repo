from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from urllib.parse import quote
import asyncio
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import tempfile
import os
import base64

@register("complex_plotter", "runnel", "复函数绘图插件", "1.0.0")
class ComplexPlotterPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.chrome_options = Options()
        self.chrome_options.add_argument("--headless")
        self.chrome_options.add_argument("--no-sandbox")
        self.chrome_options.add_argument("--disable-dev-shm-usage")
        self.chrome_options.add_argument("--window-size=1080,1080")
        self.chrome_options.binary_location = "/usr/bin/chromium" 

    @filter.command_group("complex")
    def complex(self):
        pass

    @complex.command("plot")
    async def complex_plot(self, event: AstrMessageEvent):
        try:
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
            yield event.plain_result(f"生成图像时出错: {str(e)}")

    @complex.command("custom")  # 待大幅度修改以节约内存和时间
    async def complex_custom(self, event: AstrMessageEvent):
        try:
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
            yield event.plain_result(f"执行自定义代码时出错: {str(e)}")

    async def capture_screenshot(self, url):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._capture_screenshot_sync, url)

    def _capture_screenshot_sync(self, url):
        driver = webdriver.Chrome(options=self.chrome_options)
        try:
            driver.get(url)
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "canvas"))
            )

            screenshot = driver.get_screenshot_as_png()
        
            return screenshot
        finally:
            driver.quit()

    async def execute_custom_code(self, code):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._execute_custom_code_sync, code)

    def _execute_custom_code_sync(self, code):
        driver = webdriver.Chrome(options=self.chrome_options)
        try:
            driver.get("https://samuelj.li/complex-function-plotter/")
            
            element = driver.find_element(By.CSS_SELECTOR, ".MuiButtonBase-root:nth-child(1) > .MuiIconButton-label > .MuiSvgIcon-root:nth-child(1) > path")
            actions = ActionChains(driver)
            actions.move_to_element(element).perform()
            driver.find_element(By.CSS_SELECTOR, ".MuiButtonBase-root:nth-child(1) > .MuiIconButton-label > .MuiSvgIcon-root:nth-child(1) > path").click()
            
            element = driver.find_element(By.CSS_SELECTOR, "body")
            actions = ActionChains(driver)
            actions.move_to_element(element, 0, 0).perform()
            
            element = driver.find_element(By.XPATH, "(//input[@value=''])[6]")
            actions = ActionChains(driver)
            actions.move_to_element(element).perform()
            driver.find_element(By.XPATH, "(//input[@value=''])[6]").click()
            
            element = driver.find_element(By.CSS_SELECTOR, "body")
            actions = ActionChains(driver)
            actions.move_to_element(element, 0, 0).perform()
            
            code_editor = driver.find_element(By.CSS_SELECTOR, ".npm__react-simple-code-editor__textarea")
            code_editor.click()
            code_editor.clear()
            code_editor.send_keys(code)
            
            driver.find_element(By.CSS_SELECTOR, ".MuiButtonBase-root:nth-child(1) > .MuiIconButton-label > .MuiSvgIcon-root:nth-child(1) > path").click()
            
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "canvas"))
            )
            
            screenshot = driver.get_screenshot_as_png()
            return screenshot
        finally:
            driver.quit()

    async def terminate(self):
        pass