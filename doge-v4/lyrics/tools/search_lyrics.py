import json
import os
import re

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


def search_song_lyrics(song_name, music_source=None, artist_name=None):
    """使用多个平台搜索单首歌曲的歌词"""
    print(f"正在搜索歌曲《{song_name}》的歌词...")
    if artist_name:
        print(f"指定歌手: {artist_name}")
    if music_source:
        print(f"指定音乐源: {music_source}")

    # 设置请求头
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Referer': 'https://www.google.com/',
    }

    # 根据指定的音乐源选择性搜索
    platforms = []
    if music_source:
        # 只搜索指定的平台
        if music_source.lower() in ['netease', '网易云', '网易']:
            platforms.append('netease')
        elif music_source.lower() in ['qq', 'qq音乐', 'qqmusic']:
            platforms.append('qq')
        elif music_source.lower() in ['kugou', '酷狗', '酷狗音乐']:
            platforms.append('kugou')
    else:
        # 不指定平台，按默认顺序尝试所有平台
        platforms = ['netease', 'qq', 'kugou']

    # 按指定顺序尝试不同平台
    for platform in platforms:
        try:
            if platform == 'netease':
                print("尝试从网易云音乐搜索...")
                lyrics = search_netease(song_name, artist_name, headers)
                if lyrics:
                    print("网易云音乐: 成功获取歌词")
                    return lyrics
            elif platform == 'qq':
                print("尝试从 QQ 音乐搜索...")
                lyrics = search_qq(song_name, artist_name, headers)
                if lyrics:
                    print("QQ 音乐: 成功获取歌词")
                    return lyrics
            elif platform == 'kugou':
                print("尝试从酷狗音乐搜索...")
                lyrics = search_kugou(song_name, artist_name, headers)
                if lyrics:
                    print("酷狗音乐: 成功获取歌词")
                    return lyrics
        except Exception as e:
            print(f"{platform}搜索出错: {str(e)}")
            import traceback
            traceback.print_exc()

    if music_source:
        print(f"未能从{music_source}找到歌词")
    else:
        print("未能从任何平台找到歌词")
    return None


def search_netease(song_name, artist_name=None, headers=None):
    """从网易云音乐搜索歌词"""
    if headers is None:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': 'https://www.google.com/',
        }

    try:
        search_term = f"{song_name} {artist_name if artist_name else ''}"

        # 搜索歌曲
        search_url = f"https://music.163.com/api/search/get?s={search_term}&type=1&limit=10"
        response = requests.get(search_url, headers=headers)
        data = response.json()

        if 'result' in data and 'songs' in data['result'] and len(data['result']['songs']) > 0:
            # 找到匹配的歌曲
            for song in data['result']['songs']:
                song_id = song['id']
                found_song_name = song['name']
                found_artist_name = song['artists'][0]['name'] if song['artists'] else ''

                # 如果指定了歌手，检查是否匹配
                if artist_name and artist_name.lower() not in found_artist_name.lower():
                    continue

                print(f"找到歌曲: {found_song_name} - {found_artist_name}")

                # 获取歌词
                lyrics_url = f"https://music.163.com/api/song/lyric?id={song_id}&lv=1&kv=1&tv=-1"
                response = requests.get(lyrics_url, headers=headers)
                lyrics_data = response.json()

                if 'lrc' in lyrics_data and 'lyric' in lyrics_data['lrc']:
                    raw_lyrics = lyrics_data['lrc']['lyric']

                    # 处理歌词格式，去除时间标签
                    processed_lyrics = []
                    for line in raw_lyrics.split('\n'):
                        line = re.sub(r'\[\d+:\d+\.\d+\]', '', line).strip()
                        if line and not line.startswith('['):
                            processed_lyrics.append(line)

                    lyrics = '\n'.join(processed_lyrics)

                    return lyrics

        print("网易云音乐: 未找到歌词")
        return None
    except Exception as e:
        print(f"网易云音乐搜索出错: {str(e)}")
        return None


def search_kugou(song_name, artist_name=None, headers=None):
    """从酷狗音乐搜索歌词"""
    if headers is None:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': 'https://www.kugou.com/',
        }

    try:
        search_term = f"{song_name} {artist_name if artist_name else ''}"

        # 酷狗音乐搜索API
        search_url = "http://mobilecdn.kugou.com/api/v3/search/song"
        params = {
            'format': 'json',
            'keyword': search_term,
            'page': 1,
            'pagesize': 20,
            'showtype': 1
        }

        response = requests.get(search_url, headers=headers, params=params)

        if response.text and response.text.strip():
            try:
                data = response.json()

                if data.get('status') == 1 and 'data' in data and 'info' in data['data']:
                    songs = data['data']['info']

                    # 找到匹配的歌曲
                    for song in songs:
                        found_song_name = song.get('songname', '')
                        found_artist_name = song.get('singername', '')
                        hash_value = song.get('hash', '')

                        # 优化歌手匹配逻辑
                        if artist_name:
                            if not (artist_name.lower() in found_artist_name.lower() or
                                    found_artist_name.lower() in artist_name.lower() or
                                    any(word in found_artist_name.lower() for word in artist_name.lower().split())):
                                continue

                        # 优化歌曲名匹配
                        if song_name.lower() not in found_song_name.lower():
                            continue

                        print(f"找到歌曲: {found_song_name} - {found_artist_name}")

                        # 获取歌词
                        lyrics_url = "http://krcs.kugou.com/search"
                        lyrics_params = {
                            'ver': 1,
                            'man': 'yes',
                            'client': 'mobi',
                            'keyword': f"{found_song_name} {found_artist_name}",
                            'duration': song.get('duration', ''),
                            'hash': hash_value
                        }

                        lyrics_response = requests.get(lyrics_url, headers=headers, params=lyrics_params)

                        if lyrics_response.text:
                            try:
                                lyrics_data = lyrics_response.json()

                                if 'candidates' in lyrics_data and len(lyrics_data['candidates']) > 0:
                                    # 获取第一个候选歌词
                                    candidate = lyrics_data['candidates'][0]
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

                                        download_response = requests.get(download_url, headers=headers,
                                                                         params=download_params)

                                        if download_response.text:
                                            try:
                                                download_data = download_response.json()

                                                if download_data.get('status') == 200 and 'content' in download_data:
                                                    import base64
                                                    # 解码Base64编码的歌词
                                                    encoded_lyrics = download_data['content']
                                                    raw_lyrics = base64.b64decode(encoded_lyrics).decode('utf-8')

                                                    # 处理歌词格式，去除时间标签
                                                    processed_lyrics = []
                                                    for line in raw_lyrics.split('\n'):
                                                        line = re.sub(r'\[\d+:\d+\.\d+\]', '', line).strip()
                                                        if line and not line.startswith('['):
                                                            processed_lyrics.append(line)

                                                    lyrics = '\n'.join(processed_lyrics)

                                                    if lyrics.strip():
                                                        return lyrics
                                            except Exception as e:
                                                print(f"酷狗音乐: 解析歌词内容失败: {str(e)}")
                                                continue
                            except Exception as e:
                                print(f"酷狗音乐: 解析歌词搜索结果失败: {str(e)}")
                                continue
            except Exception as e:
                print(f"酷狗音乐: 解析搜索结果 JSON 失败: {str(e)}")

        print("酷狗音乐: 未找到歌词")
        return None
    except Exception as e:
        print(f"酷狗音乐搜索出错: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def search_qq(song_name, artist_name=None, headers=None):
    """从 QQ 音乐搜索歌词"""
    if headers is None:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': 'https://www.google.com/',
        }

    try:
        search_term = f"{song_name} {artist_name if artist_name else ''}"

        qq_headers = headers.copy()
        qq_headers['Referer'] = 'https://y.qq.com/'

        # 搜索歌曲
        search_url = "https://u.y.qq.com/cgi-bin/musicu.fcg"
        search_data = {
            "req_0": {
                "method": "DoSearchForQQMusicDesktop",
                "module": "music.search.SearchCgiService",
                "param": {
                    "query": search_term,
                    "page_num": 1,
                    "num_per_page": 20,
                    "search_type": 0
                }
            }
        }

        params = {
            "data": json.dumps(search_data)
        }

        response = requests.get(search_url, headers=qq_headers, params=params)
        data = response.json()

        # 解析搜索结果
        if ('req_0' in data and 'data' in data['req_0'] and 'body' in data['req_0']['data'] and
                'song' in data['req_0']['data']['body'] and 'list' in data['req_0']['data']['body']['song']):
            song_list = data['req_0']['data']['body']['song']['list']

            for song in song_list:
                found_song_name = song.get('title', '')
                song_mid = song.get('mid', '')

                # 优化歌手匹配逻辑
                if artist_name:
                    found_artist = False
                    singer_names = []
                    for singer in song.get('singer', []):
                        singer_name = singer.get('name', '')
                        singer_names.append(singer_name)
                        if (artist_name.lower() in singer_name.lower() or
                                singer_name.lower() in artist_name.lower()):
                            found_artist = True
                            break

                    if not found_artist:
                        full_singer_name = ' '.join(singer_names)
                        if not (artist_name.lower() in full_singer_name.lower() or
                                any(word in full_singer_name.lower() for word in artist_name.lower().split())):
                            continue

                # 优化歌曲名匹配
                if song_name.lower() not in found_song_name.lower():
                    continue

                print(f"找到歌曲: {found_song_name} - {' '.join([s.get('name', '') for s in song.get('singer', [])])}")

                # 获取歌词
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

                qq_headers['Referer'] = 'https://y.qq.com/'

                response = requests.get(lyrics_url, headers=qq_headers, params=params)

                try:
                    lyrics_data = response.json()
                    if 'lyric' in lyrics_data and lyrics_data.get('retcode', -1) == 0:
                        # QQ 音乐返回的歌词是 Base64 编码的
                        import base64
                        raw_lyrics = base64.b64decode(lyrics_data['lyric']).decode('utf-8')

                        # 处理歌词格式，去除时间标签
                        processed_lyrics = []
                        for line in raw_lyrics.split('\n'):
                            line = re.sub(r'\[\d+:\d+\.\d+\]', '', line).strip()
                            if line and not line.startswith('['):
                                processed_lyrics.append(line)

                        lyrics = '\n'.join(processed_lyrics)

                        if lyrics.strip():
                            return lyrics
                except Exception as e:
                    print(f"QQ 音乐: 解析歌词失败: {str(e)}")
                    continue

        print("QQ 音乐: 未找到歌词")
        return None
    except Exception as e:
        print(f"QQ 音乐搜索出错: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def search_and_save_lyrics(song_name, artist_name=None, music_source=None, custom_lyrics_dir=None):
    """搜索歌词并保存到歌词库，返回 (是否成功, 文件路径, 预览内容)"""
    print(f"search_and_save_lyrics: 歌名='{song_name}', 歌手='{artist_name}', 音乐源='{music_source}'")
    lyrics = search_song_lyrics(song_name, music_source, artist_name)

    if not lyrics:
        return False, None, None

    # 过滤歌词，去除作词作曲等信息行，保持歌词文件纯粹
    filtered_lyrics = _filter_lyrics_for_storage(lyrics)

    # 生成文件名
    file_name = song_name
    if artist_name:
        file_name = f"{song_name} - {artist_name}"

    # 处理文件名中的非法字符
    file_name = re.sub(r'[\\/:*?"<>|]', '_', file_name)

    # 确定保存目录 - 如果传入了自定义目录则使用，否则使用默认目录
    lyrics_dir = custom_lyrics_dir if custom_lyrics_dir else LYRICS_DIR
    
    # 保存到歌词库
    file_path = os.path.join(lyrics_dir, f"{file_name}.txt")

    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(filtered_lyrics)

        # 生成预览
        preview_lines = filtered_lyrics.split('\n')[:5]
        preview = '\n'.join(preview_lines)
        if len(filtered_lyrics.split('\n')) > 5:
            preview += '\n...'

        return True, file_path, preview
    except Exception as e:
        print(f"保存歌词失败: {str(e)}")
        return False, None, filtered_lyrics


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
    print("=" * 50)
    print("歌词搜索工具 - 自动保存到歌词库")
    print("=" * 50)

    while True:
        # 从控制台获取输入
        song_name = input("\n请输入歌曲名称 (输入q退出): ").strip()
        if song_name.lower() == 'q':
            break
        artist_name = input("请输入歌手名称 (可选，直接回车跳过): ").strip()
        if not artist_name:
            artist_name = None

        music_source = input("请输入音乐源 (可选，直接回车跳过): ").strip()
        if not music_source:
            music_source = None

        # 搜索歌词并保存
        success, file_path, preview = search_and_save_lyrics(song_name, artist_name, music_source)

        if success:
            print(f"\n歌词已保存到: {file_path}")

            # 预览歌词
            print("\n歌词预览:")
            print(preview)
        else:
            if preview:  # preview 包含了歌词内容但保存失败
                print("\n保存歌词失败，但获取到了歌词内容:")
                print(preview)
            else:
                print(f"\n未找到《{song_name}》的歌词")

        print("\n" + "-" * 50)


if __name__ == "__main__":
    main()
