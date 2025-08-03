from pathlib import Path
import re
import httpx
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import astrbot.api.message_components as Comp
import hmac
import base64
import time
import json
from datetime import datetime
import hashlib
import uuid
class text2imgConfig:
    def __init__(self,
    width=512,
    height=512,
    steps=28,
    seed=-1,
    mgType=None,
    modelId=None,
    sd_loraModelId=None,
    sd_loraWeight=1,
    flux_loraModelId=None,
    flux_loraWeight=1,
    message_str=None,
    isS=False,
    isF=False,
    confyui_api=None,
    istranslate=True,
    translateType=None,
    img_url=None
    ):
        self.width = width
        self.height = height
        self.steps = steps
        self.seed = seed
        self.mgType = mgType
        self.modelId = modelId
        self.sd_loraModelId = sd_loraModelId
        self.sd_loraWeight = sd_loraWeight
        self.flux_loraModelId = flux_loraModelId
        self.flux_loraWeight = flux_loraWeight
        self.message_str = message_str
        self.isSdLora = isS
        self.isFluxLora = isF
        self.confyui_api = confyui_api
        self.istranslate = istranslate
        self.translateType = translateType
        self.img_url = img_url

@register("liblibApi", "machinad", "调用liblib进行文生图、图生图、可以自己换大模型,lora模型，支持contorlnet控制，支持自定义confyuiAPI", "1.1.4")
class liblibApi(Star):
    def __init__(self, context: Context, config: dict, interval=5):
        self.ak = config.get("AccessKey")#获取ak
        self.sk = config.get("SecretKey")#获取sk
        self.width= config.get("width")#获取宽度
        self.height = config.get("height")#获取高度
        self.steps = int(config.get("num_inference_steps"))#获取步数
        self.seed = config.get("seed")#获取种子
        self.imgType = config.get("text_imgType")#获取图片类型
        self.modelId = config.get("sd1.5/xl_config").get("modelId")#获取模型id
        self.sd_loraModelId = config.get("sd1.5/xl_config").get("sd_lora_modelid")#获取模型id
        self.sd_loraWeight = config.get("sd1.5/xl_config").get("sd_lora_scale")#获取权重
        self.flux_loraModelId = config.get("flux_config").get("flux_lora_modelid")#获取模型id
        self.flux_loraWeight = config.get("flux_config").get("flux_lora_scale")#获取权重
        self.isSdLora = config.get("sd1.5/xl_config").get("is_SdLora")#获取是否使用lora
        self.isFluxLora = config.get("flux_config").get("is_fluxLora")#获取是否使用lora
        self.confyui_api = config.get("confyui_overwriting")#获取confyui api
        self.istranslate = config.get("prompt_Translation").get("is_Translation")#获取是否翻译
        self.translateType = config.get("prompt_Translation").get("Translation_Type")#获取翻译类型
        self.time_stamp = int(datetime.now().timestamp() * 1000)#获取当前时间戳
        self.signature_nonce = uuid.uuid1()#获取uuid
        self.signature_img = self._hash_sk(self.sk, self.time_stamp, self.signature_nonce)#获取签名
        self.singature_confyui = self._hash_confyui(self.sk, self.time_stamp, self.signature_nonce)#获取签名,confyui专用
        self.signature_img_post = self._has_sk_imgPost(self.sk, self.time_stamp, self.signature_nonce)#获取图片上传签名
        self.signature_ultra_img = self._hash_ultra_sk(self.sk, self.time_stamp, self.signature_nonce)#获取签名,暂时无用，请忽略
        self.signature_status = self._hash_sk_status(self.sk, self.time_stamp, self.signature_nonce)#获取签名,用于获取状态
        self.signature_getVersion = self._has_sk_getVersion(self.sk, self.time_stamp, self.signature_nonce)#获取签名,用于获取版本
        self.interval = interval
        self.headers = {"Content-Type": "application/json"}
        self.text2img_url = self.get_image_url(self.ak, self.signature_img, self.time_stamp,self.signature_nonce)#获取文生图url
        self.confyui_url = self.get_confyui_url(self.ak, self.singature_confyui, self.time_stamp,self.signature_nonce)#confyui模式的url
        self.text2img_ultra_url = self.get_ultra_image_url(self.ak, self.signature_ultra_img, self.time_stamp,self.signature_nonce)#无用的url
        self.generate_url = self.get_generate_url(self.ak, self.signature_status, self.time_stamp,self.signature_nonce)#获取状态url
        self.imgPost_url = self.get_imgPost_url(self.ak, self.signature_img_post, self.time_stamp,self.signature_nonce)#图片上传url
        self.getVersion_url = self.get_getVersion_url(self.ak, self.signature_getVersion, self.time_stamp,self.signature_nonce)#获取版本url
        self.path = Path("./data/plugins_data/liblib")
        self.img_config = text2imgConfig()
        self.img_config.width = self.width
        self.img_config.height = self.height
        self.img_config.steps = self.steps
        self.img_config.seed = self.seed
        self.img_config.mgType = self.imgType
        self.img_config.modelId = self.modelId
        self.img_config.sd_loraModelId = self.sd_loraModelId
        self.img_config.sd_loraWeight = self.sd_loraWeight
        self.img_config.flux_loraModelId = self.flux_loraModelId
        self.img_config.flux_loraWeight = self.flux_loraWeight
        self.img_config.isSdLora = self.isSdLora
        self.img_config.isFluxLora = self.isFluxLora
        self.img_config.confyui_api = self.confyui_api
        self.img_config.istranslate = self.istranslate
        self.img_config.translateType = self.translateType
        super().__init__(context)
    def hmac_sha1(self, key, code):#加密
        hmac_code = hmac.new(key.encode(), code.encode(), hashlib.sha1)
        return hmac_code.digest()
    def _hash_sk(self, key, s_time, ro):
        """加密sk"""
        data = "/api/generate/webui/text2img" + "&" + str(s_time) + "&" + str(ro)
        s = base64.urlsafe_b64encode(self.hmac_sha1(key, data)).rstrip(b'=').decode()  # noqa: Q000
        return s
    def _hash_confyui(self,key,s_time,ro):
        """加密sk"""
        data = "/api/generate/comfyui/app" + "&" + str(s_time) + "&" + str(ro)
        s = base64.urlsafe_b64encode(self.hmac_sha1(key, data)).rstrip(b'=').decode()  # noqa: Q000
        return s
    def _hash_ultra_sk(self, key, s_time, ro):
        """加密sk"""
        data = "/api/generate/webui/text2img/ultra" + "&" + str(s_time) + "&" + str(ro)
        s = base64.urlsafe_b64encode(self.hmac_sha1(key, data)).rstrip(b'=').decode()  # noqa: Q000
        return s

    def _hash_sk_status(self, key, s_time, ro):
        """加密sk"""
        data = "/api/generate/webui/status" + "&" + str(s_time) + "&" + str(ro)
        s = base64.urlsafe_b64encode(self.hmac_sha1(key, data)).rstrip(b'=').decode()  # noqa: Q000
        return s
    def _has_sk_imgPost(self,key, s_time, ro):
        """加密sk"""
        data = "/api/generate/upload/signature"+"&"+str(s_time)+"&"+str(ro)
        s = base64.urlsafe_b64encode(self.hmac_sha1(key, data)).rstrip(b'=').decode()  # noqa: Q000
        return s
    def _has_sk_getVersion(self,key, s_time, ro):
        """加密sk"""
        data = "/api/model/version/get"+"&"+str(s_time)+"&"+str(ro)
        s = base64.urlsafe_b64encode(self.hmac_sha1(key, data)).rstrip(b'=').decode()  # noqa: Q000
        return s
    def get_image_url(self, ak, signature, time_stamp, signature_nonce):

        url = f"https://openapi.liblibai.cloud/api/generate/webui/text2img?AccessKey={ak}&Signature={signature}&Timestamp={time_stamp}&SignatureNonce={signature_nonce}"
        return url

    def get_confyui_url(self, ak, signature, time_stamp, signature_nonce):
        url = f"https://openapi.liblibai.cloud/api/generate/comfyui/app?AccessKey={ak}&Signature={signature}&Timestamp={time_stamp}&SignatureNonce={signature_nonce}"
        return url

    def get_ultra_image_url(self, ak, signature, time_stamp, signature_nonce):

        url = f"https://openapi.liblibai.cloud/api/generate/webui/text2img/ultra?AccessKey={ak}&Signature={signature}&Timestamp={time_stamp}&SignatureNonce={signature_nonce}"
        return url

    def get_generate_url(self, ak, signature, time_stamp, signature_nonce):

        url = f"https://openapi.liblibai.cloud/api/generate/webui/status?AccessKey={ak}&Signature={signature}&Timestamp={time_stamp}&SignatureNonce={signature_nonce}"
        return url
    def get_imgPost_url(self,ak,signature,time_stamp,signature_nonce):
        url = f"https://openapi.liblibai.cloud/api/generate/upload/signature?AccessKey={ak}&Signature={signature}&Timestamp={time_stamp}&SignatureNonce={signature_nonce}"
        return url
    def get_getVersion_url(self,ak,signature,time_stamp,signature_nonce):
        url = f"https://openapi.liblibai.cloud/api/model/version/get?AccessKey={ak}&Signature={signature}&Timestamp={time_stamp}&SignatureNonce={signature_nonce}"
        return url
    async def text2img(self, config: text2imgConfig):
        if config.mgType == "sd1.5/XL模式(可自定义模型)":
            progess = await self.text_to_image_sd(config)
            return progess
        elif config.mgType == "flux模式":
            progess = await self.text_to_image_flux(config)
            return progess
        elif config.mgType == "confyui模式":
            progess = await self.text_to_image_confyui(config)
            return progess
        else:
            return {"code": 1, "msg": "未设置类型"}
    async def run(self, data, url, timeout=240):
        """
        发送任务到生图接口，直到返回image为止，失败抛出异常信息
        """
        start_time = time.time()  # 记录开始时间
        # 这里提交任务，校验是否提交成功，并且获取任务ID
        async with httpx.AsyncClient() as client:
            logger.info("正在发起请求,请求体为"+str(data))
            response = await client.post(url=url, headers=self.headers, json=data)
            response.raise_for_status()
            progress = response.json()# 获取响应数据
            if progress["code"]==0:
                while True:
                    current_time = time.time()
                    if(current_time - start_time)>timeout:
                        logger.info(f"在发起生图任务后{current_time-start_time}秒，未获取到任务ID，已退出轮询。")
                        return {"code": 1, "msg": "任务已经超时，文生图失败"}
                    generate_uuid = progress["data"]["generateUuid"]# 获取任务ID
                    data = {"generateUuid":generate_uuid}# 装载任务ID
                    response = await client.post(url=self.generate_url, headers=self.headers, json=data)# 根据已创建的任务id发送请求，进行任务状态查询
                    response.raise_for_status()# 检查响应是否成功
                    progress = response.json()# 获取响应数据
                    try:
                        logger.info("当前任务状态为："+str(progress.get("data",{}).get("generateStatus",""))+"进度为："+str(progress.get("data",{}).get("percentCompleted","")*100)+"% 已经用时："+str(current_time-start_time)+"秒")
                    except Exception as e:
                        logger.info(f"任务状态查询失败，原因：{e}")
                    if progress["data"].get("images") and any(image for image in progress["data"]["images"] if image is not None):
                        logger.info("图片生成完成")
                        try:
                            logger.info("图片地址为："+str(progress.get("data",{}).get("images",[{}])[0].get("imageUrl",None)))
                            logger.info("返回原始数据："+str(progress))
                        except Exception:
                            logger.info("图片地址为获取失败")
                        return progress
                    time.sleep(self.interval)# 等待一段时间后再次轮询  # noqa: ASYNC251
            else:
                return {"code": {progress["code"]}, "msg": {progress["msg"]}}
    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
    @filter.command("lcha")
    async def lcha(self, event: AstrMessageEvent):
        """
        模型参数查询命令格式为/lcha f454f4a44bc440ca9427ca48c931598e
        """
        message = event.message_obj.message
        message_str = self.textFilter(message)
        parts = str(message_str).split(" ",1)
        prompt = parts[1].strip() if len(parts) > 1 else ""# 获取用户发送的消息
        data = {
            "versionUuid": str(prompt),
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(url=self.getVersion_url, headers=self.headers, json=data)
            response.raise_for_status()
            progress = response.json()
            logger.info("模型查询参数为"+str(progress))
            yield event.plain_result(
                f"已经查询到模型信息：\n"
                f"模型ID：{progress.get('data', {}).get('versionUuid')}\n"
                f"模型名称：{progress.get('data', {}).get('modelName')}\n"
                f"模型版本：{progress.get('data', {}).get('versionName')}\n"
                f"基础算法：{progress.get('data', {}).get('baseAlgoName')}\n"
                )
    def textFilter(self,message:list)->str:
        for msg in message:
            if msg.type == "Plain":
                return msg.text
        return None
    def imageFilter(self,message:list)->str:
        for msg in message:
            if msg.type == "Image":
                image_url = msg.url
                image_url = image_url.replace("https","http")
                return image_url
        return None
    @filter.command("ltran")
    async def ltran(self, event: AstrMessageEvent):
        """
        此指令仅翻译提示词。翻译命令格式为/ltran 一个女孩，带着墨镜
        """
        message = event.message_obj.message
        message_str = self.textFilter(message)
        parts = str(message_str).split(" ",1)
        prompt = parts[1].strip() if len(parts) > 1 else ""# 获取用户发送的消息
        config = text2imgConfig(message_str=prompt,istranslate=self.istranslate,translateType=self.translateType)# 获取一个新的用户消息实例
        text = await self.prompt_Translation(config)
        yield event.plain_result("翻译结果为："+text)
    @filter.command("lsd")
    async def lsd(self, event: AstrMessageEvent):
        """
        直接调用sd1.5/XL模式(可自定义模型)指令格式为：/lsd 一个女孩，带着墨镜
        """
        message = event.message_obj.message
        image_url = self.imageFilter(message)
        message_str = self.textFilter(message)
        parts = str(message_str).split(" ",1)
        prompt = parts[1].strip() if len(parts) > 1 else ""# 获取用户发送的消息
        self.img_config.img_url = image_url
        self.img_config.message_str = prompt
        progess = await self.text_to_image_sd(self.img_config)
        if progess.get("code") == 0:
            chain = [
                Comp.At(qq=event.get_sender_id()), # At 消息发送者
                Comp.Plain(f"图片已经生成:"
                           f"\n消耗点数：{progess.get('pointsCost')}，账户余额：{progess.get('accountBalance')}"
                           f"\n使用模型：{progess.get('modelName')}，使用算法：{progess.get('baseAlgoName')}"
                           f"\n提示词：{progess.get('prompt')}"
                           f"\n生图种子：{progess.get('seed')}"
                           ),
            ]
            for i in range(1, 5):
                url = progess.get(f"imageUrl_{i}","")
                if url:
                    chain.append(Comp.Image.fromURL(url))
            yield event.chain_result(chain)
        else:
            yield event.plain_result("图片生成失败，原因："+str(progess.get("msg")))
    @filter.command("lflux")
    async def lflux(self, event: AstrMessageEvent):
        """
        直接调用flux模式指令格式为：/lflux 一个女孩，带着墨镜
        """
        message = event.message_obj.message
        image_url = self.imageFilter(message)
        message_str = self.textFilter(message)
        if image_url is not None:
            logger.info("检测到有传入图片，但不支持controlnet，已忽略")
            yield event.plain_result("检测到有传入图片，但不支持controlnet，已忽略")
            pass
        parts = str(message_str).split(" ",1)
        prompt = parts[1].strip() if len(parts) > 1 else ""# 获取用户发送的消息
        self.img_config.img_url = image_url
        self.img_config.message_str = prompt
        progess = await self.text_to_image_flux(self.img_config)
        if progess.get("code") == 0:
            chain = [
                Comp.At(qq=event.get_sender_id()), # At 消息发送者
                Comp.Plain(f"图片已经生成:"
                           f"\n消耗点数：{progess.get('pointsCost')}，账户余额：{progess.get('accountBalance')}"
                           f"\n使用模型：flux，使用算法：F.1"
                           f"\n提示词：{progess.get('prompt')}"
                           f"\n生图种子：{progess.get('seed')}"
                           ),
            ]
            for i in range(1, 5):
                url = progess.get(f"imageUrl_{i}","")
                if url:
                    chain.append(Comp.Image.fromURL(url))
            yield event.chain_result(chain)
        else:
            yield event.plain_result("图片生成失败，原因："+str(progess.get("msg")))
    @filter.command("lcon")
    async def lcon(self, event: AstrMessageEvent):
        """
        直接调用confyui模式指令格式为：/lcon <提示词><图片>，该模式api默认为高清放大，需要自己去配置文件填写自己的confyui的api，具体使用方法参考文档
        """
        message = event.message_obj.message
        image_url = self.imageFilter(message)
        message_str = self.textFilter(message)
        parts = str(message_str).split(" ",1)
        prompt = parts[1].strip() if len(parts) > 1 else ""# 获取用户发送的消息
        self.img_config.img_url = image_url
        self.img_config.message_str = prompt
        progess = await self.text_to_image_confyui(self.img_config)
        if progess.get("code") == 0:
            chain = [
                Comp.At(qq=event.get_sender_id()), # At 消息发送者
                Comp.Plain(f"图片已经生成:"
                           f"\n消耗点数：{progess.get('pointsCost')}，账户余额：{progess.get('accountBalance')}"
                           f"\n提示词：{progess.get('prompt')}"
                           f"\n生图种子：{progess.get('seed')}"
                           ),
            ]
            for i in range(1, 5):
                url = progess.get(f"imageUrl_{i}","")
                if url:
                    chain.append(Comp.Image.fromURL(url))
            yield event.chain_result(chain)
        else:
            yield event.plain_result("图片生成失败，原因："+str(progess.get("msg")))
    @filter.command("limg")
    async def limg(self, event: AstrMessageEvent):
        """
        使用文生图，比如/limg 1girl或是/limg 一个男孩，穿红色衣服
        """
        message = event.message_obj.message# 用户发的消息对象
        image_url = self.imageFilter(message)
        message_str = self.textFilter(message)
        parts = str(message_str).split(" ",1)
        prompt = parts[1].strip() if len(parts) > 1 else ""# 获取用户发送的消息
        self.img_config.img_url = image_url
        self.img_config.message_str = prompt
        try:
            progess = await self.text2img(self.img_config)# 发送请求
        except Exception as e:
            yield event.plain_result(f"调用文生图接口失败，原因：{e}")
            return
        if progess.get("code") == 0:
            chain = [
                Comp.At(qq=event.get_sender_id()), # At 消息发送者
                Comp.Plain(f"图片已经生成:"
                           f"\n当前使用模式：{self.img_config.mgType}"
                           f"\n消耗点数：{progess.get('pointsCost')}，账户余额：{progess.get('accountBalance')}"
                           f"\n使用模型：{progess.get('modelName')}，使用算法：{progess.get('baseAlgoName')}"
                           f"\n提示词：{progess.get('prompt')}"
                           f"\n生图种子：{progess.get('seed')}"
                           )
            ]
            for i in range(1, 5):
                url = progess.get(f"imageUrl_{i}","")
                if url:
                    chain.append(Comp.Image.fromURL(url))
            yield event.chain_result(chain)
        else:
            yield event.plain_result("图片生成失败，原因："+str(progess.get("msg")))
    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
    async def text_to_image_confyui(self,config:text2imgConfig):
        """
        处理用户发送的消息，获取用户发送的消息和图片链接，构造请求数据,confyui模式
        """
        url = await self.get_signature_image_url(config.img_url,self.imgPost_url)
        prompt = await self.prompt_Translation(config)
        data = """{
            "templateUuid": "4df2efa0f18d46dc9758803e478eb51c",
            "generateParams": {
                "workflowUuid": "fa2e042e32fa4aabbbacc255b4ab2cca",
                "30":
                {
                    "class_type": "LoadImage",
                    "inputs":
                    {
                        "image": "{{img_url}}"
                        }
                    },
                "31":
                {
                    "class_type": "ImageScale",
                    "inputs":
                    {
                        "width": {{width}},
                        "height": {{height}}
                        }
                   }
            }
        }
        """
        if config.confyui_api is not None and config.confyui_api != "":
            api_str = str(config.confyui_api)
            api_str = api_str.replace("{{prompt}}", str(prompt))
            api_str = api_str.replace("{{height}}", str(config.height))
            api_str = api_str.replace("{{width}}", str(config.width))
            api_str = api_str.replace("{{steps}}", str(config.steps))
            api_str = api_str.replace("{{seed}}", str(config.seed))
            api_str = api_str.replace("{{img_url}}", str(url))
            try:
                base_json = json.loads(api_str)
            except Exception as e:
                logger.info(f"confyui模式调用文生图接口失败，原因：json类型设置错误{e}")
        else:
            if url is None:
                return {"code": 1, "msg": "confyui模式调用文生图接口失败，原因：图片链接为空,默认为图像放大api，需要传入图片"}
            api_str = data
            api_str = api_str.replace("{{prompt}}", str(prompt))
            api_str = api_str.replace("{{height}}", str(config.height))
            api_str = api_str.replace("{{width}}", str(config.width))
            api_str = api_str.replace("{{steps}}", str(config.steps))
            api_str = api_str.replace("{{seed}}", str(config.seed))
            api_str = api_str.replace("{{img_url}}", str(url))
            try:
                base_json = json.loads(api_str)
            except Exception as e:
                logger.info(f"confyui模式调用文生图接口失败，原因：json类型设置错误{e}")
        d_data = await self.run(base_json, self.confyui_url)
        re_data = {
            "code": d_data.get("code",1),
            "msg": d_data.get("msg",""),
            "pointsCost":d_data.get("data",{}).get("pointsCost",0),
            "accountBalance":d_data.get("data",{}).get("accountBalance",0),
            "imageUrl_1":"",
            "imageUrl_2":"",
            "imageUrl_3":"",
            "imageUrl_4":"",
            "seed":d_data.get("data",{}).get("images",[{}])[0].get("seed",None),
            "prompt":prompt,
            "modelName": "",
            "baseAlgoName": "",
            "loraModelName": "",
            "lorabaseAlgoName": ""
        }
        for i in range(0,len(d_data.get("data",{}).get("images",[{}]))):
            re_data["imageUrl_"+str(i+1)] = d_data.get("data",{}).get("images",[{}])[i].get("imageUrl",None)
        return re_data
    async def text_to_image_flux(self,config:text2imgConfig):
        """
        处理用户发送的消息，获取用户发送的消息和图片链接，构造请求数据,flux模式
        """
        data = {
            "templateUuid": "6f7c4652458d4802969f8d089cf5b91f",
            "generateParams":{
                "prompt":"",
                "steps": config.steps,
                "width": config.width,
                "height": config.height,
                "imgCount": 1,
                "seed": config.seed,
                "restoreFaces": 0,
                "additionalNetwork": [
                    {
                        "modelId": config.flux_loraModelId,
                        "weight": config.flux_loraWeight,
                    }
                ]
            }
        }
        loraid = await self.check_modelId(config.flux_loraModelId)
        if not config.isFluxLora:
            logger.info("未开启lora模型，移除lora")
            del data["generateParams"]["additionalNetwork"]
        elif loraid == "F.1":
            pass
        else:
            logger.info("lora模型类型错误，移除lora")
            del data["generateParams"]["additionalNetwork"]
        prompt = await self.prompt_Translation(config)
        data["generateParams"]["prompt"] = prompt
        logger.info("翻译完成，翻译结果为："+str(prompt))
        logger.info("请求数据"+str(data))
        d_data = await self.run(data, self.text2img_url)
        re_data = {
            "code": d_data.get("code",1),
            "msg": d_data.get("msg",""),
            "pointsCost":d_data.get("data",{}).get("pointsCost",0),
            "accountBalance":d_data.get("data",{}).get("accountBalance",0),
            "imageUrl_1":"",
            "imageUrl_2":"",
            "imageUrl_3":"",
            "imageUrl_4":"",
            "seed":d_data.get("data",{}).get("images",[{}])[0].get("seed",None),
            "prompt":prompt,
            "modelName": "",
            "baseAlgoName": "",
            "loraModelName": loraid["modelName"],
            "lorabaseAlgoName": ""
        }
        for i in range(0,len(d_data.get("data",{}).get("images",[{}]))):
            re_data["imageUrl_"+str(i+1)] = d_data.get("data",{}).get("images",[{}])[i].get("imageUrl",None)
        return re_data

    async def text_to_image_sd(self,config:text2imgConfig):
        """
        处理用户发送的消息，获取用户发送的消息和图片链接，构造请求数据,sd1.5/XL模式(可自定义模型)
        """
        data = {
            "generateParams":{
                "checkPointId": config.modelId,
                "vaeId": "",
                "prompt":"",
                "negativePrompt": "bad-artist, bad-artist-anime, bad-hands-5, bad-image-v2-39000, bad-picture-chill-75v, bad_prompt, bad_prompt_version2, badhandv4, NG_DeepNegative_V1_75T, EasyNegative,2girls, 3girls,,bad quality, poor quality, doll, disfigured, jpg, toy, bad anatomy, missing limbs, missing fingers, 3d, cgi",
                "clipSkip": 2,
                "sampler": 15,
                "steps": config.steps,
                "cfgScale": 7,
                "width": config.width,
                "height": config.height,
                "imgCount": 1,
                "randnSource": 0,
                "seed": config.seed,
                "restoreFaces": 0,
                "additionalNetwork":[
                    {
                        "modelId": config.sd_loraModelId,
                        "weight": config.sd_loraWeight
                    }
                ],
                "hiResFixInfo":{
                    "hiresSteps": 28,
                    "hiresDenoisingStrength": 0.45,
                    "upscaler": 10,
                    "resizedWidth": config.width*2,
                    "resizedHeight": config.height*2
                },
                "controlNet":[
                    {
                        "unitOrder": 1,
                        "sourceImage": "",
                        "width": config.width,
                        "height": config.height,
                        "preprocessor":11,
                        "annotationParameters": {
                            "openposeHand": {
                                "preprocessorResolution": 512
                            }
                        },
                        "model": "cf63d214734760dcdc108b1bd094921b",
                        "controlWeight": 1,
                        "startingControlStep": 0,
                        "endingControlStep": 1,
                        "pixelPerfect": 0,
                        "controlMode": 0,
                        "resizeMode": 1,
                        "maskImage": ""
                    },
                    {
                        "unitOrder": 2,
                        "sourceImage": "",
                        "width": config.width,
                        "height": config.height,
                        "preprocessor":3,
                        "annotationParameters": {
                            "depthLeres": {
                                "preprocessorResolution": 1024,
                                "removeNear": 0,
                                "removeBackground": 0
                            }
                        },
                        "model": "cf63d214734760dcdc108b1bd094921b",
                        "controlWeight": 0.6,
                        "startingControlStep": 0,
                        "endingControlStep": 1,
                        "pixelPerfect": 0,
                        "controlMode": 0,
                        "resizeMode": 1,
                        "maskImage": ""
                    }
                ]
            }
        }
        contorlNet_model = {
            "基础算法 v1.5":{
                "Depth":{
                    "control_v11f1p_sd15_depth":"cf63d214734760dcdc108b1bd094921b",
                    "t2iadapter_depth_sd15v2":"f08a4a889b56d4099e8a947503cabc14"
                },
                "OpenPose":{
                    "control_v11p_sd15_openpose":"b46dd34ef9c2fe189446599d62516cbf",
                    "t2iadapter_openpose_sd14v1":"5a8b19a8809e00be4e17517e8ab174ad",
                    "control_v11p_sd15_densepose_fp16":"3b4e0830d45c11ee9b5e00163e365853"
                },
                "vae":{
                    "vae-ft-mse-840000-ema-pruned.safetensors":"2c1a337416e029dd65ab58784e8a4763",
                    "klF8Anime2VAE_klF8Anime2VAE.ckpt":"d4a03b32d8d59552194a9453297180c1",
                    "color101VAE_v1.pt":"d9be20ad5a7195ff0d97925e5afc7912"
                 }
            },
            "基础算法 XL":{
                "Depth":{
                    "xinsir_controlnet_depth_sdxl_1.0":"6349e9dae8814084bd9c1585d335c24c"
                 },
                 "OpenPose":{
                    "xinsir_controlnet-openpose-sdxl-1.0":"23ef8ab803d64288afdb7106b8967a55"
                 },
                 "vae":{
                    "sd_xl_vae_1.0":"3cefd3e4af2b8effb230b960da41a980"
                 }
            }
        }
        modelid = await self.check_modelId(config.modelId)
        loraid = await self.check_modelId(config.sd_loraModelId)
        if not config.isSdLora:
            logger.info("未检测到lora模型，关闭lora")
            del data.get("generateParams")["additionalNetwork"]
        else:
            if modelid["code"] != 0 or loraid["code"] != 0:
                return {"code": 1, "msg": "模型ID获取错误"}
            if modelid["baseAlgoName"]!= "基础算法 v1.5" and modelid["baseAlgoName"]!= "基础算法 XL":
                return {"code": 1, "msg": "sd模式中只能使用基础算法 v1.5或基础算法 XL模型"}
            if modelid["baseAlgoName"] != loraid["baseAlgoName"]:
                return {"code": 1, "msg": "模型基础算法和lora模型基础算法不一致，请在配置文件中设置算法一致的模型"}
        if modelid["baseAlgoName"]== "基础算法 v1.5":
            data.get("generateParams")["vaeId"] = contorlNet_model.get(modelid["baseAlgoName"]).get("vae").get("vae-ft-mse-840000-ema-pruned.safetensors")
            data.get("generateParams")["controlNet"][0]["model"] = contorlNet_model.get(modelid["baseAlgoName"]).get("OpenPose").get("control_v11p_sd15_openpose")
            data.get("generateParams")["controlNet"][1]["model"] = contorlNet_model.get(modelid["baseAlgoName"]).get("Depth").get("control_v11f1p_sd15_depth")
            logger.info("检测到使用基础算法 v1.5模型，切换为control"+data.get("generateParams")["controlNet"][0]["model"])
        elif modelid["baseAlgoName"]== "基础算法 XL":
            #data.get("generateParams")["vaeId"] = contorlNet_model.get(modelid["baseAlgoName"]).get("vae").get("sd_xl_vae_1.0")
            data.get("generateParams")["controlNet"][0]["model"] = contorlNet_model.get(modelid["baseAlgoName"]).get("OpenPose").get("xinsir_controlnet-openpose-sdxl-1.0")
            data.get("generateParams")["controlNet"][1]["model"] = contorlNet_model.get(modelid["baseAlgoName"]).get("Depth").get("xinsir_controlnet_depth_sdxl_1.0")
            logger.info("检测到使用基础算法 XL模型，切换为control"+data.get("generateParams")["controlNet"][0]["model"])
        prompt = await self.prompt_Translation(config)
        if prompt is not None:
            data.get("generateParams")["prompt"] = prompt
        else:
            return {"code": 1, "msg": "翻译后提示词为空,请检查prompt_Translation函数"}
        if config.img_url is not None:
            logger.info("检测到图片链接，开始上传图片")
            image_url = await self.get_signature_image_url(config.img_url,self.imgPost_url)
            data.get("generateParams")["controlNet"][0]["sourceImage"] = image_url
            data.get("generateParams")["controlNet"][1]["sourceImage"] = image_url
        else:
            logger.info("未检测到图片链接,关闭controlnet")
            del data.get("generateParams")["controlNet"]
        logger.info("请求数据"+str(data))
        d_data = await self.run(data, self.text2img_url)
        re_data = {
            "code": d_data.get("code",1),
            "msg": d_data.get("msg",""),
            "pointsCost":d_data.get("data",{}).get("pointsCost",0),
            "accountBalance":d_data.get("data",{}).get("accountBalance",0),
            "imageUrl_1":"",
            "imageUrl_2":"",
            "imageUrl_3":"",
            "imageUrl_4":"",
            "seed":d_data.get("data",{}).get("images",[{}])[0].get("seed",None),
            "prompt":prompt,
            "modelName": modelid["modelName"],
            "baseAlgoName": modelid["baseAlgoName"],
            "loraModelName": loraid["modelName"],
            "lorabaseAlgoName": modelid["baseAlgoName"]
        }
        for i in range(0,len(d_data.get("data",{}).get("images",[{}]))):
            re_data["imageUrl_"+str(i+1)] = d_data.get("data",{}).get("images",[{}])[i].get("imageUrl",None)
        return re_data
    async def check_modelId(self,id:str):
        """
        检测模型ID
        """
        data = {
            "versionUuid": id,
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(url=self.getVersion_url, headers=self.headers, json=data)
            response.raise_for_status()
            progress = response.json()
            if progress["code"]==0:
                logger.info("模型ID检测成功")
                re_progress = {
                    "code": 0,
                    "msg": "模型ID检测成功",
                    "versionUuid": progress.get("data",{}).get("versionUuid",None),
                    "modelName": progress.get("data",{}).get("modelName",None),
                    "versionName": progress.get("data",{}).get("versionName",None),
                    "baseAlgoName": progress.get("data",{}).get("baseAlgoName",None)
                }
                return re_progress
            else:
                logger.info("模型ID检测失败，原因："+str(progress["msg"]))
                return {"code": 1, "msg": "模型ID检测失败，原因："+str(progress["msg"]),"versionUuid": "","modelName": "","versionName":"","baseAlgoName":""}
    async def prompt_Translation(self,config:text2imgConfig):
        """
        处理用户发送的消息，获取用户发送的消息和图片链接，构造请求数据
        """
        if self.has_chinese(config.message_str) and config.istranslate:
            logger.info("检测到中文，开始翻译提示词")
            if config.translateType is None:
                config.translateType = "sd格式提示词"
                logger.info("未设置翻译类型，默认使用sd格式提示词")
            if config.translateType == "sd格式提示词":
                sysPormpt = """
                stableDiffusion是一款利用深度学习的文生图模型，支持通过使用提示词来产生新的图像，描述要包含或省略的元素。我在这里引入StableDiffusion算法中的Prompt概念，又被称为提示符。
下面的prompt是用来指导AI绘画模型创作图像的。它们包含了图像的各种细节，如人物的外观、背景、颜色和光线效果，以及图像的主题和风格。这些prompt的格式经常包含括号内的加权数字，用于指定某些细节的重要性或强调。例如，"(masterpiece:1.5)"表示作品质量是非常重要的，多个括号也有类似作用。此外，如果使用中括号，如"{blue hair:white hair:0.3}"，这代表将蓝发和白发加以融合，蓝发占比为0.3。
以下是用prompt帮助AI模型生成图像的例子:(bestquality),highlydetailed,ultra-detailed,cold,solo,(1girl),(detailedeyes),(shinegoldeneyes),(longliverhair),expressionless,(long sleeves),(puffy sleeves),(white wings),shinehalo,(heavymetal:1.2),(metaljewelry),cross-lacedfootwear (chain),(Whitedoves:1.2)
对于结果，请直接输出提示词
                """
                logger.info("使用sd格式提示词")
            elif config.translateType == "英语直译(自然语言)":
                sysPormpt = """
                你是一个好用的翻译助手。请将我的中文翻译成英文。我发给你所有的话都是需要翻译的内容，你只需要回答翻译结果。翻译结果请符合中文的语言习惯。
                """
                logger.info("仅翻译成英语")
            elif config.translateType == "中译中(ai润色)":
                sysPormpt = """请对文字润色，润色结果请符合中文的语境习惯。请直接输出润色后的文字"""
                logger.info("仅进行ai润色")
            textA = await self.exextract_letters(config.message_str)#提取可能存在的lora提示词
            textB = await self.LLMmessage(config,sysPormpt)#获取翻译结果
            if textA == "":
                uprompt = textB#拼接翻译结果
            else:
                uprompt = textA + "," + textB#拼接翻译结果
            logger.info("翻译完成，翻译结果为："+str(uprompt))
            return uprompt
        else:
            logger.info("未检测到中文，不进行翻译")
            return config.message_str
    async def download_image(self, url: str):
        """
        下载图片并返回二进制数据
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url)
                response.raise_for_status()
            except Exception as e:
                logger.info(f"图片下载失败，原因：{e}")
                return None
            return response.content

    async def signature_image(self,url:str,name:str):
        """
        图片上传请求发起，获取回调签名参数，用于上传图片
        """
        data = {
            "name": name,
            "extension" : "png"
        }
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, headers=self.headers, json=data)
                response.raise_for_status()
                progress = response.json()
            except Exception as e:
                logger.info(f"图片上传请求发起失败，原因：{e}")
                return None
            return progress

    async def upload_image(self,progress:dict,image_file,save_path:bytes):
        """
        对图片二进制数据进行签名并上传
        """
        async with httpx.AsyncClient() as client:
            data = {
                "key": progress["data"]["key"],
                "policy": progress["data"]["policy"],
                "x-oss-date": progress["data"]["xOssDate"],
                "x-oss-expires": progress["data"]["xOssExpires"],
                "x-oss-signature": progress["data"]["xOssSignature"],
                "x-oss-credential": progress["data"]["xOssCredential"],
                "x-oss-signature-version": progress["data"]["xOssSignatureVersion"],
            }
            files = {
                "file": (image_file, save_path, "image/png")
            }
            try:
                response = await client.post(progress["data"]["postUrl"],data=data, files=files)
                response.raise_for_status()
                return progress.get("data").get("postUrl")+"/"+progress.get("data").get("key")
            except Exception as e:
                logger.info(f"图片上传失败，原因：{e}")
                return None

    async def get_signature_image_url(self,url:str,post_url):
        """
        该方法用于将消息平台的图片链接转换为liblib的api可以直接调用的图片链接
        该方法会先将图片下载到本地，然后再签名上传到服务器，最后返回图片链接
        """
        image_name = "image"+str(uuid.uuid1())
        image_file = image_name+"."+"png"
        imge_byte = await self.download_image(url)
        logger.info("图片二进制数据下载成功")
        if imge_byte is None:
            logger.info("图片二进制数据下载下载失败")
            return None
        progress = await self.signature_image(post_url,image_name)
        logger.info("图片上传请求发起成功")
        if progress is None:
            logger.info("图片上传请求发起失败,未获得签名数据")
            return None
        get_url = await self.upload_image(progress,image_file,imge_byte)
        logger.info("图片上传成功,图片链接为："+get_url)
        if get_url is None:
            logger.info("图片上传失败,未能获取到图片链接")
            return None
        return get_url

    async def exextract_letters(self,text):
        latters = re.findall(r"[a-zA-Z]", text)
        return "".join(latters)
    def has_chinese(self,text):
        """
        检查字符串中是否包含中文字符
        """
        for char in text:
            if "\u4e00" <= char <= "\u9fff":
                return True
        return False
    async def LLMmessage(self,event:text2imgConfig,sysPrompt):
        """
        调用LLM翻译提示词
        """
        Prompt = event.message_str
        Context = []
        llm_response = await self.context.get_using_provider().text_chat(
        prompt=Prompt,
        session_id=None, # 此已经被废弃
        contexts=Context, # 也可以用上面获得的用户当前的对话记录 context
        image_urls=[], # 图片链接，支持路径和网络链接
        system_prompt=sysPrompt  # 系统提示，可以不传
    )
        return llm_response.result_chain.chain[0].text
