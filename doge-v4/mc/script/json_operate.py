import json
import asyncio
from pathlib import Path
import aiofiles
from typing import Dict, Any, Optional, Tuple, List
import logging
import time
from datetime import datetime, timedelta

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 配置版本常量
CURRENT_VERSION = "2.1"
DEFAULT_CONFIG = {
    "version": CURRENT_VERSION,
    "next_id": 1,
    "servers": {},
    "last_cleanup": None
}

# 自动清理配置
AUTO_CLEANUP_DAYS = 10  # 10天未查询成功自动删除

def is_old_format(data: Dict[str, Any]) -> bool:
    """
    检查是否为旧版格式（直接以服务器名称为键）
    
    Args:
        data: 要检查的数据
        
    Returns:
        bool: 是否为旧版格式
    """
    if not data:
        return False
    
    # 检查是否有version字段
    if "version" in data:
        return False
    
    # 检查是否直接以服务器名称为键
    for key, value in data.items():
        if isinstance(value, dict) and "name" in value and "host" in value:
            return True
    
    return False

def migrate_old_format(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    将旧版格式迁移到新版格式
    
    Args:
        data: 旧版格式的数据
        
    Returns:
        Dict[str, Any]: 新版格式的数据
    """
    logger.info("检测到旧版配置格式，开始自动迁移...")
    
    new_data = DEFAULT_CONFIG.copy()
    next_id = 1
    
    for name, server_info in data.items():
        if isinstance(server_info, dict) and "name" in server_info and "host" in server_info:
            new_data["servers"][str(next_id)] = {
                "id": next_id,
                "name": server_info["name"],
                "host": server_info["host"]
            }
            next_id += 1
    
    new_data["next_id"] = next_id
    logger.info(f"迁移完成，共迁移 {len(data)} 个服务器配置")
    return new_data

async def write_json(json_path: str, new_data: Dict[str, Any]) -> None:
    """
    异步写入JSON数据到文件

    Args:
        json_path: JSON文件路径
        new_data: 要写入的数据字典

    Raises:
        IOError: 当文件写入失败时抛出
    """
    try:
        # 确保目录存在
        Path(json_path).parent.mkdir(parents=True, exist_ok=True)
        
        # 异步写入，禁止转义
        async with aiofiles.open(json_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(new_data, indent=4, ensure_ascii=False))
        logger.info(f"成功写入JSON文件: {json_path}")
    except Exception as e:
        logger.error(f"写入JSON文件失败: {e}")
        raise IOError(f"写入JSON文件失败: {e}")

async def read_json(json_path: str) -> Dict[str, Any]:
    """
    异步读取JSON文件内容，自动处理版本迁移

    Args:
        json_path: JSON文件路径

    Returns:
        解析后的JSON数据字典

    Raises:
        IOError: 当文件读取失败时抛出
        json.JSONDecodeError: 当JSON解析失败时抛出
    """
    try:
        if not Path(json_path).exists():
            logger.info(f"JSON文件不存在，创建新文件: {json_path}")
            await write_json(json_path=json_path, new_data=DEFAULT_CONFIG)
            return DEFAULT_CONFIG

        async with aiofiles.open(json_path, 'r', encoding='utf-8') as f:
            content = await f.read()
            logger.info(f"读取到的JSON内容: {content}")
            data = json.loads(content)
            
            # 检查是否为旧版格式，如果是则自动迁移
            if is_old_format(data):
                data = migrate_old_format(data)
                # 保存迁移后的数据
                await write_json(json_path, data)
                logger.info("旧版配置已自动迁移并保存")
            
            # 确保数据格式正确
            if "version" not in data:
                data["version"] = CURRENT_VERSION
            if "next_id" not in data:
                data["next_id"] = 1
            if "servers" not in data:
                data["servers"] = {}
            
            logger.info(f"成功读取JSON文件: {json_path}, 数据: {data}")
            return data
    except json.JSONDecodeError as e:
        logger.error(f"JSON解析失败: {e}, 文件内容: {content if 'content' in locals() else '无法读取'}")
        raise json.JSONDecodeError(f"JSON解析失败: {e}", e.doc, e.pos)
    except Exception as e:
        logger.error(f"读取JSON文件失败: {e}, 文件路径: {json_path}")
        raise IOError(f"读取JSON文件失败: {e}")

def get_server_by_name(data: Dict[str, Any], name: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    """
    通过服务器名称查找服务器信息
    
    Args:
        data: 配置数据
        name: 服务器名称
        
    Returns:
        Optional[Tuple[str, Dict[str, Any]]]: (id, server_info) 或 None
    """
    servers = data.get("servers", {})
    for server_id, server_info in servers.items():
        if server_info.get("name") == name:
            return server_id, server_info
    return None

def get_server_by_id(data: Dict[str, Any], server_id: str) -> Optional[Dict[str, Any]]:
    """
    通过服务器ID查找服务器信息
    
    Args:
        data: 配置数据
        server_id: 服务器ID
        
    Returns:
        Optional[Dict[str, Any]]: 服务器信息或None
    """
    servers = data.get("servers", {})
    return servers.get(server_id)

async def add_data(json_path: str, name: str, host: str) -> bool:
    """
    向JSON文件添加新的服务器数据

    Args:
        json_path: JSON文件路径
        name: 服务器名称
        host: 服务器主机地址

    Returns:
        bool: 添加是否成功
    """
    try:
        data = await read_json(json_path)
        
        # 检查服务器名称是否已存在
        existing_server = get_server_by_name(data, name)
        if existing_server:
            logger.warning(f"服务器名称已存在: {name} (ID: {existing_server[0]})")
            return False

        # 分配新的ID
        server_id = str(data["next_id"])
        data["next_id"] += 1
        
        # 添加新服务器
        current_time = int(time.time())
        data["servers"][server_id] = {
            "id": int(server_id),
            "name": name,
            "host": host,
            "created_time": current_time,
            "last_success_time": current_time,
            "last_failed_time": None,
            "failed_count": 0
        }
        
        await write_json(json_path, data)
        logger.info(f"成功添加服务器数据: {name} (ID: {server_id})")
        return True
    except Exception as e:
        logger.error(f"添加服务器数据失败: {e}")
        return False

async def del_data(json_path: str, identifier: str) -> bool:
    """
    从JSON文件中删除服务器数据（支持通过ID或名称删除）

    Args:
        json_path: JSON文件路径
        identifier: 要删除的服务器ID或名称

    Returns:
        bool: 删除是否成功
    """
    try:
        data = await read_json(json_path)
        servers = data.get("servers", {})
        
        # 首先尝试作为ID查找
        if identifier in servers:
            server_info = servers[identifier]
            del servers[identifier]
            await write_json(json_path, data)
            logger.info(f"成功删除服务器数据: {server_info['name']} (ID: {identifier})")
            return True
        
        # 如果不是ID，尝试作为名称查找
        existing_server = get_server_by_name(data, identifier)
        if existing_server:
            server_id, server_info = existing_server
            del servers[server_id]
            await write_json(json_path, data)
            logger.info(f"成功删除服务器数据: {server_info['name']} (ID: {server_id})")
            return True
        
        logger.warning(f"服务器不存在: {identifier}")
        return False
    except Exception as e:
        logger.error(f"删除服务器数据失败: {e}")
        return False

async def update_data(json_path: str, identifier: str, new_name: Optional[str] = None, new_host: Optional[str] = None) -> bool:
    """
    更新服务器数据（支持通过ID或名称更新）

    Args:
        json_path: JSON文件路径
        identifier: 要更新的服务器ID或名称
        new_name: 新的服务器名称（可选）
        new_host: 新的服务器主机地址（可选）

    Returns:
        bool: 更新是否成功
    """
    try:
        data = await read_json(json_path)
        servers = data.get("servers", {})
        
        # 查找服务器
        server_id = None
        server_info = None
        
        # 首先尝试作为ID查找
        if identifier in servers:
            server_id = identifier
            server_info = servers[identifier]
        else:
            # 如果不是ID，尝试作为名称查找
            existing_server = get_server_by_name(data, identifier)
            if existing_server:
                server_id, server_info = existing_server
        
        if not server_info:
            logger.warning(f"服务器不存在: {identifier}")
            return False
        
        # 检查新名称是否与其他服务器冲突
        if new_name and new_name != server_info["name"]:
            existing_server = get_server_by_name(data, new_name)
            if existing_server and existing_server[0] != server_id:
                logger.warning(f"服务器名称已存在: {new_name}")
                return False
        
        # 更新数据
        if new_name is not None:
            server_info["name"] = new_name
        if new_host is not None:
            server_info["host"] = new_host
        
        await write_json(json_path, data)
        logger.info(f"成功更新服务器数据: {server_info['name']} (ID: {server_id})")
        return True
    except Exception as e:
        logger.error(f"更新服务器数据失败: {e}")
        return False

async def get_all_servers(json_path: str) -> Dict[str, Dict[str, Any]]:
    """
    获取所有服务器信息

    Args:
        json_path: JSON文件路径

    Returns:
        Dict[str, Dict[str, Any]]: 所有服务器信息 {id: server_info}
    """
    try:
        data = await read_json(json_path)
        return data.get("servers", {})
    except Exception as e:
        logger.error(f"获取服务器列表失败: {e}")
        return {}

async def update_server_status(json_path: str, identifier: str, success: bool) -> bool:
    """
    更新服务器查询状态

    Args:
        json_path: JSON文件路径
        identifier: 服务器ID或名称
        success: 查询是否成功

    Returns:
        bool: 更新是否成功
    """
    try:
        data = await read_json(json_path)
        servers = data.get("servers", {})
        
        # 查找服务器
        server_id = None
        server_info = None
        
        # 首先尝试作为ID查找
        if identifier in servers:
            server_id = identifier
            server_info = servers[identifier]
        else:
            # 如果不是ID，尝试作为名称查找
            existing_server = get_server_by_name(data, identifier)
            if existing_server:
                server_id, server_info = existing_server
        
        if not server_info:
            logger.warning(f"服务器不存在: {identifier}")
            return False
        
        current_time = int(time.time())
        
        if success:
            # 查询成功
            server_info["last_success_time"] = current_time
            server_info["failed_count"] = 0
            logger.info(f"更新服务器 {server_info['name']} (ID: {server_id}) 查询成功状态")
        else:
            # 查询失败
            server_info["last_failed_time"] = current_time
            server_info["failed_count"] = server_info.get("failed_count", 0) + 1
            logger.info(f"更新服务器 {server_info['name']} (ID: {server_id}) 查询失败状态，失败次数: {server_info['failed_count']}")
        
        await write_json(json_path, data)
        return True
    except Exception as e:
        logger.error(f"更新服务器状态失败: {e}")
        return False

async def auto_cleanup_servers(json_path: str) -> List[Dict[str, Any]]:
    """
    自动清理长时间未查询成功的服务器

    Args:
        json_path: JSON文件路径

    Returns:
        List[Dict[str, Any]]: 被删除的服务器列表
    """
    try:
        data = await read_json(json_path)
        servers = data.get("servers", {})
        
        if not servers:
            return []
        
        current_time = int(time.time())
        cutoff_time = current_time - (AUTO_CLEANUP_DAYS * 24 * 3600)  # 10天前的时间戳
        deleted_servers = []
        
        # 检查每个服务器
        servers_to_delete = []
        for server_id, server_info in servers.items():
            last_success_time = server_info.get("last_success_time", 0)
            
            # 如果最后成功时间超过10天，标记为删除
            if last_success_time < cutoff_time:
                servers_to_delete.append((server_id, server_info))
        
        # 删除标记的服务器
        for server_id, server_info in servers_to_delete:
            del servers[server_id]
            deleted_servers.append({
                "id": server_id,
                "name": server_info["name"],
                "host": server_info["host"],
                "last_success_time": server_info.get("last_success_time"),
                "failed_count": server_info.get("failed_count", 0)
            })
            logger.info(f"自动删除长时间未查询成功的服务器: {server_info['name']} (ID: {server_id})")
        
        if deleted_servers:
            # 更新最后清理时间
            data["last_cleanup"] = current_time
            await write_json(json_path, data)
            logger.info(f"自动清理完成，删除了 {len(deleted_servers)} 个服务器")
        
        return deleted_servers
    except Exception as e:
        logger.error(f"自动清理服务器失败: {e}")
        return []

async def get_server_info(json_path: str, identifier: str) -> Optional[Dict[str, Any]]:
    """
    获取指定服务器的信息（支持通过ID或名称查找）

    Args:
        json_path: JSON文件路径
        identifier: 服务器ID或名称

    Returns:
        Optional[Dict[str, Any]]: 服务器信息或None
    """
    try:
        data = await read_json(json_path)
        servers = data.get("servers", {})
        
        # 首先尝试作为ID查找
        if identifier in servers:
            return servers[identifier]
        
        # 如果不是ID，尝试作为名称查找
        existing_server = get_server_by_name(data, identifier)
        if existing_server:
            return existing_server[1]
        
        return None
    except Exception as e:
        logger.error(f"获取服务器信息失败: {e}")
        return None
