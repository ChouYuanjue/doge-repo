import json
import os
import random
import re
import time

import requests


def contains_chinese(text):
    """检测文本是否包含汉字"""
    for char in text:
        if '\u4e00' <= char <= '\u9fff':
            return True
    return False


# 设置歌词保存目录
LYRICS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "lyrics")
os.makedirs(LYRICS_DIR, exist_ok=True)

# 设置请求头，模拟浏览器行为
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Referer': 'https://www.google.com/',  # 默认 Referer
}


def get_artist_songs(artist_name="周杰伦"):
    """从网易云音乐获取歌手的所有歌曲列表"""
    print(f"正在从网易云音乐获取{artist_name}的歌曲列表...")

    try:
        # 使用网易云音乐的搜索 API
        search_url = f"https://music.163.com/api/search/get"
        params = {
            's': artist_name,
            'type': 100,  # 100 表示歌手
            'limit': 1
        }

        response = requests.get(search_url, headers=HEADERS, params=params)
        data = response.json()

        # 获取歌手 ID
        if 'result' in data and 'artists' in data['result'] and len(data['result']['artists']) > 0:
            artist_id = data['result']['artists'][0]['id']

            # 获取歌手的所有歌曲
            songs_url = f"https://music.163.com/api/v1/artist/{artist_id}"
            response = requests.get(songs_url, headers=HEADERS)
            data = response.json()

            songs = []
            if 'hotSongs' in data:
                for song in data['hotSongs']:
                    song_id = song.get('id')
                    song_name = song.get('name', '').strip()
                    if song_id and song_name:
                        songs.append({
                            'id': song_id,
                            'name': song_name
                        })

            print(f"网易云音乐: 共找到 {len(songs)} 首歌曲")
            return songs
        else:
            print(f"网易云音乐: 未找到歌手: {artist_name}")
            return []
    except Exception as e:
        print(f"网易云音乐: 获取歌曲列表出错: {str(e)}")
        return []


def get_song_lyrics(song_id):
    """从网易云音乐获取歌曲歌词"""
    lyrics_url = f"https://music.163.com/api/song/lyric"
    params = {
        'id': song_id,
        'lv': 1,
        'kv': 1,
        'tv': -1
    }

    try:
        response = requests.get(lyrics_url, headers=HEADERS, params=params)
        data = response.json()

        if 'lrc' in data and 'lyric' in data['lrc']:
            raw_lyrics = data['lrc']['lyric']

            # 处理歌词格式，去除时间标签
            processed_lyrics = []
            for line in raw_lyrics.split('\n'):
                # 去除时间标签 [00:00.000]
                line = re.sub(r'\[\d+:\d+\.\d+\]', '', line).strip()
                if line and not line.startswith('['):
                    processed_lyrics.append(line)

            return '\n'.join(processed_lyrics)
        else:
            return None
    except Exception as e:
        print(f"网易云音乐: 获取歌词出错: {str(e)}")
        return None


def get_qq_music_songs(artist_name="周杰伦"):
    """从 QQ 音乐获取歌手的所有歌曲列表"""
    print(f"正在从 QQ 音乐获取{artist_name}的歌曲列表...")

    # 首先搜索歌手
    search_url = "https://u.y.qq.com/cgi-bin/musicu.fcg"
    search_data = {
        "req_0": {
            "method": "DoSearchForQQMusicDesktop",
            "module": "music.search.SearchCgiService",
            "param": {
                "query": artist_name,
                "page_num": 1,
                "num_per_page": 20,
                "search_type": 9  # 9 表示歌手
            }
        }
    }

    params = {
        "data": json.dumps(search_data)
    }

    qq_headers = HEADERS.copy()
    qq_headers['Referer'] = 'https://y.qq.com/'

    try:
        response = requests.get(search_url, headers=qq_headers, params=params)
        data = response.json()

        # 解析搜索结果
        if ('req_0' in data and 'data' in data['req_0'] and 'body' in data['req_0']['data'] and
                'singer' in data['req_0']['data']['body'] and 'list' in data['req_0']['data']['body']['singer']):

            singer_list = data['req_0']['data']['body']['singer']['list']

            # 找到匹配的歌手
            singer_mid = None
            for singer in singer_list:
                singer_name = singer.get('name', '')
                if (singer_name.lower() == artist_name.lower() or
                        artist_name.lower() in singer_name.lower()):
                    singer_mid = singer.get('mid')
                    break

            if not singer_mid and len(singer_list) > 0:
                singer_mid = singer_list[0].get('mid')

            if singer_mid:
                # 获取歌手的所有歌曲
                songs_url = "https://u.y.qq.com/cgi-bin/musicu.fcg"
                songs_data = {
                    "comm": {
                        "ct": 24,
                        "cv": 0
                    },
                    "singer": {
                        "method": "GetSingerSongList",
                        "param": {
                            "singermid": singer_mid,
                            "order": 1,
                            "begin": 0,
                            "num": 100
                        },
                        "module": "musichall.song_list_server"
                    }
                }

                params = {
                    "data": json.dumps(songs_data)
                }

                response = requests.get(songs_url, headers=qq_headers, params=params)
                data = response.json()

                songs = []
                if ('singer' in data and 'data' in data['singer'] and
                        'songlist' in data['singer']['data']):
                    songlist = data['singer']['data']['songlist']
                    for song in songlist:
                        song_id = song.get('id', 0)
                        song_mid = song.get('mid', '')
                        song_name = song.get('name', '').strip()

                        if song_name and song_mid:
                            songs.append({
                                'id': song_id,
                                'mid': song_mid,
                                'name': song_name
                            })

                print(f"QQ 音乐: 共找到 {len(songs)} 首歌曲")
                return songs

        print(f"QQ 音乐: 未找到歌手: {artist_name}")
        return []
    except Exception as e:
        print(f"QQ 音乐: 获取歌曲列表出错: {str(e)}")
        return []


def get_qq_music_lyrics(song_mid):
    """从 QQ 音乐获取歌曲歌词"""
    lyrics_url = "https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg"
    params = {
        'songmid': song_mid,
        'g_tk': '5381',
        'loginUin': '0',
        'hostUin': '0',
        'format': 'json',
        'inCharset': 'utf8',
        'outCharset': 'utf-8',
        'notice': '0',
        'platform': 'yqq.json',
        'needNewCode': '0'
    }

    qq_headers = HEADERS.copy()
    qq_headers['Referer'] = 'https://y.qq.com/'

    try:
        response = requests.get(lyrics_url, headers=qq_headers, params=params)
        data = response.json()

        if 'lyric' in data and data.get('retcode', -1) == 0:
            # QQ 音乐返回的歌词是 Base64 编码的
            import base64
            raw_lyrics = base64.b64decode(data['lyric']).decode('utf-8')

            # 处理歌词格式，去除时间标签
            processed_lyrics = []
            for line in raw_lyrics.split('\n'):
                line = re.sub(r'\[\d+:\d+\.\d+\]', '', line).strip()
                if line and not line.startswith('['):
                    processed_lyrics.append(line)

            return '\n'.join(processed_lyrics)
        else:
            return None
    except Exception as e:
        print(f"QQ 音乐: 获取歌词出错: {str(e)}")
        return None


def get_kugou_songs(artist_name="周杰伦"):
    """从酷狗音乐获取歌手的所有歌曲列表"""
    print(f"正在从酷狗音乐获取{artist_name}的歌曲列表...")

    # 使用酷狗音乐搜索 API
    search_url = "http://mobilecdn.kugou.com/api/v3/search/song"
    params = {
        'format': 'json',
        'keyword': artist_name,
        'page': 1,
        'pagesize': 50,
        'showtype': 1
    }

    headers = HEADERS.copy()
    headers['Referer'] = 'https://www.kugou.com/'

    try:
        response = requests.get(search_url, headers=headers, params=params)
        data = response.json()

        songs = []
        if data.get('status') == 1 and 'data' in data and 'info' in data['data']:
            song_list = data['data']['info']

            for song in song_list:
                song_name = song.get('songname', '').strip()
                singer_name = song.get('singername', '')
                hash_value = song.get('hash', '')

                # 检查歌手名是否匹配
                if (artist_name.lower() in singer_name.lower() and
                        song_name and hash_value):
                    songs.append({
                        'id': hash_value,
                        'name': song_name,
                        'singer': singer_name
                    })

        # 搜索更多页
        if len(songs) < 100:
            for page in range(2, 4):  # 搜索更多页
                params['page'] = page
                time.sleep(random.uniform(0.5, 1.0))  # 避免请求过快

                try:
                    response = requests.get(search_url, headers=headers, params=params)
                    data = response.json()

                    if data.get('status') == 1 and 'data' in data and 'info' in data['data']:
                        song_list = data['data']['info']

                        for song in song_list:
                            song_name = song.get('songname', '').strip()
                            singer_name = song.get('singername', '')
                            hash_value = song.get('hash', '')

                            if (artist_name.lower() in singer_name.lower() and
                                    song_name and hash_value):
                                songs.append({
                                    'id': hash_value,
                                    'name': song_name,
                                    'singer': singer_name
                                })
                except:
                    break

        print(f"酷狗音乐: 共找到 {len(songs)} 首歌曲")
        return songs

    except Exception as e:
        print(f"酷狗音乐: 获取歌曲列表出错: {str(e)}")
        return []


def get_kugou_lyrics(song_hash):
    """从酷狗音乐获取歌曲歌词"""
    headers = HEADERS.copy()
    headers['Referer'] = 'https://www.kugou.com/'

    try:
        # 获取歌词
        lyrics_url = "http://krcs.kugou.com/search"
        lyrics_params = {
            'ver': 1,
            'man': 'yes',
            'client': 'mobi',
            'hash': song_hash
        }

        response = requests.get(lyrics_url, headers=headers, params=lyrics_params)
        data = response.json()

        if 'candidates' in data and len(data['candidates']) > 0:
            # 获取第一个候选歌词
            candidate = data['candidates'][0]
            lyrics_id = candidate.get('id')
            access_key = candidate.get('accesskey')

            if lyrics_id and access_key:
                # 获取具体歌词内容
                download_url = "http://lyrics.kugou.com/download"
                download_params = {
                    'ver': 1,
                    'client': 'pc',
                    'id': lyrics_id,
                    'accesskey': access_key,
                    'fmt': 'lrc',
                    'charset': 'utf8'
                }

                download_response = requests.get(download_url, headers=headers, params=download_params)
                download_data = download_response.json()

                if download_data.get('status') == 200 and 'content' in download_data:
                    import base64
                    # 解码 Base64 编码的歌词
                    encoded_lyrics = download_data['content']
                    raw_lyrics = base64.b64decode(encoded_lyrics).decode('utf-8')

                    # 处理歌词格式，去除时间标签
                    processed_lyrics = []
                    for line in raw_lyrics.split('\n'):
                        line = re.sub(r'\[\d+:\d+\.\d+\]', '', line).strip()
                        if line and not line.startswith('['):
                            processed_lyrics.append(line)

                    return '\n'.join(processed_lyrics)

        return None
    except Exception as e:
        print(f"酷狗音乐: 获取歌词出错: {str(e)}")
        return None


def _filter_lyrics_for_storage(lyrics):
    """过滤歌词用于存储，去除作词作曲等信息行，保持歌词文件纯粹"""
    lines = lyrics.split('\n')
    filtered_lines = []

    for line in lines:
        line = line.strip()
        if not line:  # 跳过空行
            continue

        # 过滤掉信息行
        if (':' in line or '：' in line or  # 包含冒号的信息行（作词：、作曲：等）
                ' - ' in line or  # 包含连字符的标题行（歌曲-歌手）
                '(' in line and ')' in line or  # 包含括号的标题行
                re.match(r'^[A-Za-z\s:]+$', line)):  # 纯英文信息行
            continue
            # 检测行内是否有空格分隔的多句歌词
        if ' ' in line:
            # 只有包含汉字的歌词才进行空格拆分，英文歌不拆分
            if contains_chinese(line):
                # 将一行拆分成多句，但只有当看起来像歌词时才拆分
                # 避免拆分普通的句子
                parts = [part.strip() for part in line.split(' ') if part.strip()]
                # 如果拆分后的部分都比较短且没有特殊字符，认为是多句歌词
                if all(len(part) < 20 and not any(c in part for c in ':：()[]{}') for part in parts):
                    filtered_lines.extend(parts)
                else:
                    filtered_lines.append(line)
            else:
                filtered_lines.append(line)
        else:
            filtered_lines.append(line)

    # 进一步过滤无效句子
    final_lines = []
    for line in filtered_lines:
        if (line and
                len(line) > 1 and  # 过滤单字符
                not line.isdigit() and  # 过滤纯数字
                not all(c in '()[]{}' for c in line)):  # 过滤纯括号
            final_lines.append(line)

    return '\n'.join(final_lines)


def main():
    """主函数，爬取指定歌手的所有歌词"""
    # 让用户输入歌手名称
    artist_name = input("请输入要爬取歌词的歌手名称 (默认：周杰伦): ").strip() or "周杰伦"

    # 选择歌词源
    source = input("请选择歌词数据来源 (1: 网易云音乐, 2: QQ 音乐, 3: 酷狗音乐): ").strip()

    if source == "1":
        print(f"使用网易云音乐爬取{artist_name}的歌词...")
        songs = get_artist_songs(artist_name)
    elif source == "2":
        print(f"使用 QQ 音乐爬取{artist_name}的歌词...")
        songs = get_qq_music_songs(artist_name)
    elif source == "3":
        print(f"使用酷狗音乐爬取{artist_name}的歌词...")
        songs = get_kugou_songs(artist_name)
    else:
        print(f"无效的选择，默认使用网易云音乐")
        songs = get_artist_songs(artist_name)

    if not songs:
        print(f"未找到{artist_name}的歌曲，程序退出")
        return

    # 询问用户是否要限制爬取数量
    limit_str = input(f"找到 {len(songs)} 首歌曲。请输入要爬取的数量 (默认全部): ").strip()
    limit = None
    if limit_str and limit_str.isdigit():
        limit = int(limit_str)
        if limit > 0 and limit < len(songs):
            songs = songs[:limit]
            print(f"将爬取前 {limit} 首歌曲")

    # 添加随机延时，防止被封 IP
    delay_min = 1
    delay_max = 3
    delay_str = input(f"请输入请求间隔时间范围（秒），格式为'最小值-最大值'(默认: {delay_min}-{delay_max}): ").strip()
    if delay_str and '-' in delay_str:
        try:
            min_val, max_val = map(float, delay_str.split('-'))
            if 0 <= min_val < max_val:
                delay_min = min_val
                delay_max = max_val
        except:
            pass
    print(f"请求间隔时间设置为: {delay_min}-{delay_max}秒")

    success_count = 0
    for i, song in enumerate(songs):
        song_name = song['name']
        song_id = song['id']

        # 处理歌名中的非法字符，防止保存文件出错
        safe_song_name = re.sub(r'[\\/:*?"<>|]', '_', song_name)

        # 避免频繁请求被封 IP
        time.sleep(random.uniform(delay_min, delay_max))

        # 根据不同来源获取歌词
        lyrics = None
        if source == "1":
            lyrics = get_song_lyrics(song_id)
        elif source == "2":
            lyrics = get_qq_music_lyrics(song.get('mid', ''))
        elif source == "3":
            lyrics = get_kugou_lyrics(song_id)

        if lyrics:
            # 过滤歌词，去除作词作曲等信息
            filtered_lyrics = _filter_lyrics_for_storage(lyrics)

            # 保存歌词到文件
            file_path = os.path.join(LYRICS_DIR, f"{safe_song_name}.txt")
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(filtered_lyrics)
                print(f"✓ 歌词已保存到: {file_path}")
                success_count += 1
            except Exception as e:
                print(f"× 保存歌词失败: {str(e)}")
        else:
            print(f"× 未找到歌曲《{song_name}》的歌词")

        # 显示进度
        progress = (i + 1) / len(songs) * 100
        print(f"当前进度: {progress:.1f}%")

    print(f"\n爬取完成！共成功获取 {success_count}/{len(songs)} 首歌曲的歌词")
    print(f"歌词文件已保存在: {LYRICS_DIR}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n用户中断，程序退出")
    except Exception as e:
        print(f"程序发生错误: {str(e)}")
        import traceback

        traceback.print_exc()
    finally:
        input("\n按 Enter 键退出...")
