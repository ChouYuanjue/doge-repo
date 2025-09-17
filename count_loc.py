import os
import argparse
import re

# 要排除的目录和文件类型
EXCLUDE_DIRS = [
    '.git', '__pycache__', 'venv', 'node_modules', 'dist', 'build', 
    '.idea', '.vscode', 'logs', 'temp', 'cache', 
    'doge-v4/lyrics/data', 'doge-v4/mc/resource', 'doge-v4/rrpl/rrpl'
]
EXCLUDE_EXTENSIONS = [
    '.txt', '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.csv',
    '.jpg', '.jpeg', '.png', '.gif', '.svg', '.ico',
    '.zip', '.rar', '.tar', '.gz', '.7z',
    '.yaml', '.yml', '.xml', '.config',
    '.dll', '.jar', '.class', '.exe', '.bin',
    '.ttf', '.woff', '.woff2',
    '.epk', '.lock', '.xlsx',
    '.json', '.log', '.clc', '.cl', '.toml'
]

def count_lines_of_code(directory):
    total_lines = 0
    file_counts = {}
    extension_counts = {}
    
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        
        for file in files:
            _, ext = os.path.splitext(file.lower())
            file_path = os.path.join(root, file)
            if ext == '.json' and (file_path.endswith('doge-v3\\mirai-native\\epk\\v3_epk_config.json') or file_path.endswith('doge-v2\\v2_epk_config.json')):
                pass
            elif ext in EXCLUDE_EXTENSIONS:
                continue
            
            file_path = os.path.join(root, file)
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = len(f.readlines())
                    total_lines += lines

                    if file not in file_counts:
                        file_counts[file] = 0
                    file_counts[file] += lines

                    if ext not in extension_counts:
                        extension_counts[ext] = 0
                    extension_counts[ext] += lines
            except Exception as e:
                print(f"无法读取文件 {file_path}: {e}")
    
    return total_lines, file_counts, extension_counts

def generate_badge_url(count):
    return f"https://img.shields.io/badge/code%20lines-{count}-brightgreen"

def update_readme(readme_path, new_badge_url):
    try:
        with open(readme_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 使用正则表达式查找并替换所有可能的代码行数徽章链接
        badge_pattern = r"!\[Line of Codes\]\([^)]+\)"
        new_content = re.sub(badge_pattern, f"![Line of Codes]({new_badge_url})", content)
        
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        print(f"README.md已更新，新的代码行数徽章链接为: {new_badge_url}")
            
    except Exception as e:
        print(f"更新README.md时出错: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="统计项目代码行数并更新README中的徽章")
    parser.add_argument("--dir", default=".", help="要统计的项目目录")
    parser.add_argument("--readme", default="README.md", help="README文件路径")
    parser.add_argument("--no-update", action="store_true", help="只统计不更新README")
    args = parser.parse_args()
    
    # 获取绝对路径
    project_dir = os.path.abspath(args.dir)
    readme_path = os.path.abspath(args.readme if os.path.isabs(args.readme) else os.path.join(project_dir, args.readme))
    
    print(f"开始统计项目代码行数: {project_dir}")
    count, file_counts, extension_counts = count_lines_of_code(project_dir)
    
    print(f"总代码行数: {count:,}")
    print("按文件类型统计:")
    for ext, lines in sorted(extension_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {ext}: {lines:,} 行")
    
    badge_url = generate_badge_url(count)
    
    if not args.no_update:
        update_readme(readme_path, badge_url)
    else:
        print(f"生成的代码行数徽章链接为: {badge_url}")
        print("(未更新README.md)")