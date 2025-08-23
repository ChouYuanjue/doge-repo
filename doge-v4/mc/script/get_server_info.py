import asyncio
import aiohttp
from mcstatus import JavaServer
import socket
import base64
from pathlib import Path
import re
from astrbot.api import logger

csu_host = 'csu-mc.org'
csu_get_players = 'https://map.magicalsheep.cn/tiles/players.json'


async def get_server_status(host):
    try:
        # 调用mcstatus获取服务器信息
        server = await JavaServer.async_lookup(host)
        # 使用异步方法查询服务器状态
        status = await server.async_status()
        players_list = []
        latency = int(status.latency)
        plays_max = status.players.max
        plays_online = status.players.online
        server_version = status.version.name

        # 保存服务器图标
        if status.icon:
            icon_data = status.icon.split(",")[1]
        else:
            image_path = Path(__file__).resolve().parent.parent / 'resource' / 'default_icon.png'
            with open(image_path, 'rb') as image_file:
                # 读取图片文件内容
                image_data = image_file.read()
                # 对图片数据进行 Base64 编码
                base64_encoded = base64.b64encode(image_data)
            # 将编码后的字节数据转换为字符串
            icon_data = base64_encoded.decode('utf-8')

        # 查询服务器状态
        if status.players.sample:
            for player in status.players.sample:
                players_list.append(player.name)
        
        #自定义查询
        if host == csu_host:
                players_list = await fetch_players_names(csu_get_players)
                
        # 对玩家列表进行字母顺序排序
        players_list.sort()
        
        return {
            "players_list": players_list,  # 玩家昵称列表
            "latency": latency,  # 延迟
            "plays_max": plays_max,  # 最大玩家数
            "plays_online": plays_online,  # 在线玩家数
            "server_version": server_version,  # 服务器游戏版本
            "icon_base64": icon_data,  # 服务器图标base64
        }

    except (socket.gaierror, ConnectionRefusedError) as e:
        logger.error(f"连接服务器失败: {e}")
        return None
    except asyncio.TimeoutError:
        logger.error(f"获取服务器状态超时")
        return None
    except Exception as e:
        logger.error(f"获取服务器状态时发生未知错误: {e}")
        return None


async def main():
    host = "csu-mc.org"  # 请替换为实际的服务器地址
    result = await get_server_status(host)
    if result:
        print(result['players_list'])
    else:
        print("未获取到服务器状态信息")


# 为csu定制
async def fetch_players_names(url: str) -> list[str]:
    """
    异步获取并解析玩家名称列表并且屏蔽bot_开头的玩家名称

    :param url: 数据接口URL
    :return: 玩家名称列表
    """
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            # 检查响应状态码
            if response.status != 200:
                raise ValueError(f"请求失败，状态码: {response.status}")

            # 解析JSON数据
            data = await response.json()

            # 提取所有name字段
            names = [player["name"] for player in data.get("players", [])]

            # 使用正则表达式过滤掉以 'bot_' 开头的名称
            pattern = re.compile(r'^bot_')

            filtered_names = [name for name in names if not pattern.match(name)]

            return filtered_names


if __name__ == "__main__":
    asyncio.run(main())