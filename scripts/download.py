#!/usr/bin/env python3
"""
小龙下载助手 v2.1 - 通用多线程加速下载工具
支持：GitHub镜像、普通文件、大文件分片、并发下载、断点续传、智能重试
"""

import urllib.request
import urllib.parse
import ssl
import os
import sys
import time
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============ 配置区 ============

# GitHub Releases 专用镜像
GITHUB_RELEASES_MIRRORS = [
    "https://ghfast.top/",
    "https://ghproxy.com/",
    "https://mirror.ghproxy.com/",
    "https://gh.api.99988866.xyz/",
    "https://ghps.cc/",
    "https://gh.idayer.com/",
    "https://ghproxy.net/",
]

# 通用文件下载加速源
GENERAL_MIRRORS = [
    "",
    "https://ghfast.top/",
    "https://mirror.ghproxy.com/",
]

# 配置参数
CHUNK_THRESHOLD = 50 * 1024 * 1024  # 50MB
CHUNK_SIZE = 10 * 1024 * 1024       # 10MB
DEFAULT_WORKERS = 8
MAX_WORKERS = DEFAULT_WORKERS
CONNECT_TIMEOUT = 30
READ_TIMEOUT = 60
MAX_RETRIES = 3
RETRY_DELAY = 2

# SSL 上下文
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# ============ 工具函数 ============

def format_size(size_bytes):
    """格式化文件大小"""
    if size_bytes <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = 0
    while size_bytes >= 1024 and idx < len(units) - 1:
        size_bytes /= 1024
        idx += 1
    return f"{size_bytes:.1f} {units[idx]}"


def format_time(seconds):
    """格式化时间"""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds/60:.0f}m{seconds%60:.0f}s"
    else:
        return f"{seconds/3600:.0f}h{(seconds%3600)/60:.0f}m"


def safe_print(msg):
    """安全输出"""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        try:
            print(msg.encode('gbk', errors='ignore').decode('gbk'), flush=True)
        except:
            print(msg.encode('ascii', errors='ignore').decode('ascii'), flush=True)


class ProgressBar:
    """进度条"""
    def __init__(self, total, desc="Download"):
        self.total = total
        self.desc = desc
        self.downloaded = 0
        self.start_time = time.time()
        self.lock = threading.Lock()
        self.last_print = 0
        self.done = False
    
    def update(self, n):
        with self.lock:
            self.downloaded += n
            now = time.time()
            if now - self.last_print < 0.5 and self.downloaded < self.total:
                return
            self.last_print = now
            
            if self.total > 0:
                percent = min(self.downloaded / self.total * 100, 100)
                elapsed = now - self.start_time
                speed = self.downloaded / (elapsed + 0.001)
                eta = (self.total - self.downloaded) / speed if speed > 0 else 0
                
                bar_len = 25
                filled = int(bar_len * min(self.downloaded / self.total, 1))
                bar = "=" * filled + ">" + " " * (bar_len - filled - 1)
                if filled == bar_len:
                    bar = "=" * bar_len
                
                safe_print(f"\r{self.desc} [{bar}] {percent:.1f}% | "
                          f"{format_size(self.downloaded)}/{format_size(self.total)} | "
                          f"{format_size(speed)}/s | {format_time(eta)}")
            else:
                safe_print(f"\r{self.desc} {format_size(self.downloaded)}")
    
    def finish(self):
        with self.lock:
            if not self.done:
                self.done = True
                elapsed = time.time() - self.start_time
                safe_print(f"\r{self.desc} [{'='*25}] 100.0% | "
                          f"{format_size(self.downloaded)} | "
                          f"{format_size(self.downloaded/elapsed)}/s | "
                          f"{format_time(elapsed)}")
                safe_print("")


# ============ 核心下载逻辑 ============

def get_mirrors(url):
    """获取镜像列表"""
    parsed = urllib.parse.urlparse(url)
    
    if 'github.com' in parsed.netloc and '/releases/download/' in parsed.path:
        return [url] + [m + url for m in GITHUB_RELEASES_MIRRORS]
    
    if 'raw.githubusercontent.com' in parsed.netloc:
        return [url] + [m + url for m in GITHUB_RELEASES_MIRRORS]
    
    if 'github.com' in parsed.netloc or 'githubusercontent.com' in parsed.netloc:
        return [url] + [m + url for m in GITHUB_RELEASES_MIRRORS]
    
    return [url] + [m + url for m in GENERAL_MIRRORS if m]


def make_request(url, headers=None, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT), 
                 method=None, data=None):
    """创建 HTTP 请求"""
    req = urllib.request.Request(url, method=method, data=data)
    req.add_header('User-Agent', 
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    req.add_header('Accept', '*/*')
    req.add_header('Accept-Encoding', 'identity')
    req.add_header('Connection', 'keep-alive')
    
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    
    return req


def download_with_retry(url, output_path, headers=None, progress=None, 
                        retries=MAX_RETRIES):
    """带重试的下载"""
    temp_path = str(output_path) + ".tmp"
    
    for attempt in range(retries):
        try:
            req = make_request(url, headers)
            
            with urllib.request.urlopen(req, context=ssl_context, 
                                       timeout=CONNECT_TIMEOUT) as resp:
                total = int(resp.headers.get('Content-Length', 0))
                
                with open(temp_path, 'wb') as f:
                    downloaded = 0
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress:
                            progress.update(len(chunk))
                
                os.replace(temp_path, output_path)
                return True, downloaded
                
        except Exception as e:
            error_str = str(e).lower()
            if 'timed out' in error_str:
                err_msg = "timeout"
            elif 'refused' in error_str:
                err_msg = "refused"
            elif 'reset' in error_str:
                err_msg = "reset"
            elif 'certificate' in error_str:
                err_msg = "ssl error"
            else:
                err_msg = str(e)[:50]
            
            safe_print(f"  Retry {attempt+1}/{retries}: {err_msg}")
            
            if attempt < retries - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
    
    if os.path.exists(temp_path):
        os.remove(temp_path)
    return False, 0


def get_file_info(url):
    """获取文件信息"""
    mirrors = get_mirrors(url)
    
    for try_url in mirrors:
        try:
            req = make_request(try_url, method='HEAD')
            with urllib.request.urlopen(req, context=ssl_context, 
                                       timeout=CONNECT_TIMEOUT) as resp:
                size = int(resp.headers.get('Content-Length', 0))
                accept_ranges = resp.headers.get('Accept-Ranges', '') == 'bytes'
                content_type = resp.headers.get('Content-Type', '')
                return size, accept_ranges, content_type, try_url
        except:
            continue
    
    return 0, False, '', url


def download_single(url, output_path, progress=None):
    """单线程多镜像下载"""
    mirrors = get_mirrors(url)
    
    for i, try_url in enumerate(mirrors):
        safe_print(f"[Mirror {i+1}/{len(mirrors)}] {try_url[:65]}...")
        
        success, size = download_with_retry(try_url, output_path, 
                                           progress=progress, retries=MAX_RETRIES)
        
        if success:
            return True, size
        
        safe_print(f"  -> Failed, trying next...")
    
    return False, 0


def download_chunk_task(args):
    """分片下载任务"""
    url, start, end, chunk_file, chunk_id = args
    
    headers = {'Range': f'bytes={start}-{end}'}
    
    for attempt in range(3):
        try:
            req = make_request(url, headers)
            with urllib.request.urlopen(req, context=ssl_context,
                                       timeout=CONNECT_TIMEOUT) as resp:
                with open(chunk_file, 'wb') as f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
            return True, chunk_id, chunk_file
        except Exception as e:
            if attempt < 2:
                time.sleep(1)
    
    return False, chunk_id, str(e)


def download_multi_thread(url, output_path, file_size, progress=None):
    """多线程分片下载"""
    # 计算分片
    num_chunks = min((file_size + CHUNK_SIZE - 1) // CHUNK_SIZE, MAX_WORKERS * 2)
    chunk_size = file_size // num_chunks
    
    safe_print(f"[Multi-thread] {num_chunks} chunks, {MAX_WORKERS} workers")
    
    chunks_dir = str(output_path) + ".chunks"
    os.makedirs(chunks_dir, exist_ok=True)
    
    # 准备任务
    tasks = []
    for i in range(num_chunks):
        start = i * chunk_size
        end = min(start + chunk_size - 1, file_size - 1)
        if i == num_chunks - 1:
            end = file_size - 1
        
        chunk_file = os.path.join(chunks_dir, f"chunk_{i:04d}")
        tasks.append((url, start, end, chunk_file, i))
    
    # 下载
    completed = 0
    failed = []
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(download_chunk_task, task): task[4] 
                  for task in tasks}
        
        for future in as_completed(futures):
            success, chunk_id, result = future.result()
            
            if success:
                completed += 1
                if progress:
                    progress.update(chunk_size)
            else:
                failed.append(chunk_id)
                safe_print(f"  Chunk {chunk_id+1} failed: {result}")
    
    if failed:
        safe_print(f"[ERROR] {len(failed)} chunks failed")
        import shutil
        shutil.rmtree(chunks_dir, ignore_errors=True)
        return False
    
    # 合并
    safe_print("[Merge] Combining chunks...")
    with open(output_path, 'wb') as outfile:
        for i in range(num_chunks):
            chunk_file = os.path.join(chunks_dir, f"chunk_{i:04d}")
            with open(chunk_file, 'rb') as infile:
                outfile.write(infile.read())
    
    import shutil
    shutil.rmtree(chunks_dir, ignore_errors=True)
    
    if progress:
        progress.finish()
    
    return True


def download_file(url, output_path=None, use_multi_thread=True):
    """智能下载主函数"""
    # 确定输出路径
    if output_path is None:
        parsed = urllib.parse.urlparse(url)
        filename = os.path.basename(parsed.path)
        if not filename or '.' not in filename:
            filename = "download"
        output_path = os.path.join(os.getcwd(), filename)
    
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    safe_print(f"{'='*60}")
    safe_print(f"URL: {url}")
    safe_print(f"Output: {output_path}")
    safe_print(f"{'='*60}")
    
    # 检查已存在
    if output_path.exists():
        safe_print(f"[Note] File exists: {output_path}")
        try:
            resp = input("Overwrite? (y/n): ").strip().lower()
            if resp != 'y':
                safe_print("Cancelled.")
                return False, str(output_path), 0
        except EOFError:
            # 非交互环境，默认覆盖
            safe_print("[Auto] Non-interactive mode, overwriting...")
    
    # 获取文件信息
    safe_print("[Info] Checking...")
    file_size, accept_ranges, content_type, working_url = get_file_info(url)
    
    if file_size > 0:
        safe_print(f"[Info] Size: {format_size(file_size)} | Range: {'Yes' if accept_ranges else 'No'}")
    else:
        safe_print("[Info] Size unknown")
    
    # 选择下载策略
    start_time = time.time()
    
    if use_multi_thread and file_size > CHUNK_THRESHOLD and accept_ranges:
        safe_print(f"[Mode] Multi-thread ({MAX_WORKERS} workers)")
        progress = ProgressBar(file_size)
        success = download_multi_thread(working_url, output_path, file_size, progress)
        downloaded_size = file_size if success else 0
    else:
        if file_size > 0:
            safe_print(f"[Mode] Single-thread + mirrors")
            progress = ProgressBar(file_size)
        else:
            safe_print(f"[Mode] Single-thread")
            progress = ProgressBar(0)
        
        success, downloaded_size = download_single(working_url, output_path, progress)
        if success and progress:
            progress.finish()
    
    elapsed = time.time() - start_time
    
    if success:
        actual_size = output_path.stat().st_size
        safe_print(f"{'='*60}")
        safe_print(f"[SUCCESS] Done!")
        safe_print(f"  File: {output_path}")
        safe_print(f"  Size: {format_size(actual_size)}")
        safe_print(f"  Time: {format_time(elapsed)}")
        safe_print(f"  Speed: {format_size(actual_size/elapsed)}/s")
        safe_print(f"{'='*60}")
        return True, str(output_path), actual_size
    else:
        safe_print(f"[FAILED] All sources failed")
        return False, str(output_path), 0


def download_batch(urls, output_dir=None):
    """批量下载"""
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    
    results = []
    for i, url in enumerate(urls, 1):
        safe_print(f"\n[{i}/{len(urls)}] {url}")
        
        if output_dir:
            parsed = urllib.parse.urlparse(url)
            filename = os.path.basename(parsed.path) or "download"
            output_path = os.path.join(output_dir, filename)
        else:
            output_path = None
        
        success, path, size = download_file(url, output_path)
        results.append((url, success, path, size))
    
    safe_print(f"\n{'='*60}")
    safe_print(f"Summary: {sum(1 for r in results if r[1])}/{len(urls)} success")
    total = sum(r[3] for r in results if r[1])
    safe_print(f"Total: {format_size(total)}")
    safe_print(f"{'='*60}")
    
    return results


# ============ 命令行入口 ============

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='小龙下载助手 v2.1 - 多线程加速下载',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s https://github.com/.../file.zip
  %(prog)s https://example.com/file.exe -o D:\\Downloads\\
  %(prog)s url1 url2 url3 -o D:\\Downloads\\
  %(prog)s -f urls.txt
  %(prog)s https://.../bigfile.zip --workers 16
        """)
    
    parser.add_argument('urls', nargs='*', help='下载链接')
    parser.add_argument('-o', '--output', help='输出路径')
    parser.add_argument('-f', '--file', help='URL 列表文件')
    parser.add_argument('--no-multi-thread', action='store_true', 
                       help='禁用多线程')
    parser.add_argument('--workers', type=int, default=DEFAULT_WORKERS,
                       help=f'线程数 (默认 {DEFAULT_WORKERS})')
    parser.add_argument('--timeout', type=int, default=CONNECT_TIMEOUT,
                       help=f'超时秒数 (默认 {CONNECT_TIMEOUT})')
    
    args = parser.parse_args()
    
    # 收集 URL
    urls = []
    if args.urls:
        urls.extend(args.urls)
    if args.file:
        with open(args.file, 'r') as f:
            urls.extend(line.strip() for line in f if line.strip() and not line.startswith('#'))
    
    if not urls:
        parser.print_help()
        sys.exit(1)
    
    # 设置参数
    import types
    current_module = sys.modules[__name__]
    current_module.MAX_WORKERS = args.workers
    current_module.CONNECT_TIMEOUT = args.timeout
    
    # 执行
    if len(urls) == 1 and args.output and not os.path.isdir(args.output):
        download_file(urls[0], args.output, not args.no_multi_thread)
    elif len(urls) == 1:
        download_file(urls[0], args.output, not args.no_multi_thread)
    else:
        download_batch(urls, args.output)


if __name__ == '__main__':
    main()
