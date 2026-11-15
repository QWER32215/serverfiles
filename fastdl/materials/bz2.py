import os
import subprocess
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

def compress_single_file(file_path, seven_zip_path, output_folder=None):
    """
    压缩单个.vtf文件为.bz2文件
    
    Args:
        file_path (Path): .vtf文件路径
        seven_zip_path (str): 7zip可执行文件路径
        output_folder (Path): 输出文件夹路径，None表示与源文件相同目录
    
    Returns:
        tuple: (文件名, 成功状态, 原始大小, 压缩后大小)
    """
    try:
        # 确定输出路径 - 保持原名称加上.vtf.bz2后缀
        if output_folder:
            output_file = output_folder / (file_path.name + ".bz2")
        else:
            output_file = file_path.parent / (file_path.name + ".bz2")
        
        # 如果输出文件已存在，询问是否覆盖
        if output_file.exists():
            print(f"  ⚠ {output_file.name} 已存在，跳过")
            return (file_path.name, False, file_path.stat().st_size, 0)
        
        # 构建7zip命令 - 压缩单个文件
        cmd = [
            seven_zip_path,
            "a",  # 添加文件到压缩包
            "-tbzip2",  # 使用bzip2格式
            "-mx=9",  # 最大压缩率
            str(output_file),
            str(file_path)
        ]
        
        # 执行压缩
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0 and output_file.exists():
            original_size = file_path.stat().st_size
            compressed_size = output_file.stat().st_size
            return (file_path.name, True, original_size, compressed_size)
        else:
            return (file_path.name, False, 0, 0)
            
    except subprocess.TimeoutExpired:
        print(f"  ❌ {file_path.name}: 压缩超时")
        return (file_path.name, False, 0, 0)
    except Exception as e:
        print(f"  ❌ {file_path.name}: 压缩失败 - {e}")
        return (file_path.name, False, 0, 0)

def compress_vtf_files_separately(folder_path, output_folder=None, seven_zip_path=None, max_workers=4):
    """
    将文件夹下每个.vtf文件单独压缩成.bz2文件
    
    Args:
        folder_path (str): 包含.vtf文件的文件夹路径
        output_folder (str): 输出文件夹路径，None表示与源文件相同目录
        seven_zip_path (str): 7zip可执行文件路径，如果为None则尝试自动查找
        max_workers (int): 并行压缩的线程数
    
    Returns:
        bool: 是否全部成功
    """
    
    # 转换为Path对象
    folder = Path(folder_path)
    
    # 检查文件夹是否存在
    if not folder.exists():
        print(f"错误: 文件夹 '{folder_path}' 不存在")
        return False
    
    if not folder.is_dir():
        print(f"错误: '{folder_path}' 不是一个文件夹")
        return False
    
    # 处理输出文件夹
    if output_folder:
        output_dir = Path(output_folder)
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"输出目录: {output_dir}")
    else:
        output_dir = None
    
    # 查找所有.vtf文件
    vtf_files = list(folder.glob("*.vtf"))
    
    if not vtf_files:
        print(f"在文件夹 '{folder_path}' 中没有找到.vtf文件")
        return False
    
    print(f"找到 {len(vtf_files)} 个.vtf文件:")
    for file in vtf_files[:10]:  # 只显示前10个
        size_mb = file.stat().st_size / (1024 * 1024)
        print(f"  - {file.name} ({size_mb:.2f} MB)")
    if len(vtf_files) > 10:
        print(f"  ... 还有 {len(vtf_files) - 10} 个文件")
    
    # 查找7zip
    if seven_zip_path is None:
        # 常见的7zip安装路径
        possible_paths = [
            "7z",
            "7za",
            r"C:\Program Files\7-Zip\7z.exe",
            r"C:\Program Files (x86)\7-Zip\7z.exe",
            "/usr/bin/7z",
            "/usr/local/bin/7z"
        ]
        
        for path in possible_paths:
            try:
                subprocess.run([path, "--help"], 
                             capture_output=True, 
                             timeout=5,
                             check=False)
                seven_zip_path = path
                break
            except (subprocess.SubprocessError, FileNotFoundError):
                continue
        
        if seven_zip_path is None:
            print("错误: 找不到7zip，请安装7zip或指定7zip路径")
            print("下载地址: https://www.7-zip.org/")
            return False
    
    print(f"\n使用7zip: {seven_zip_path}")
    print(f"开始压缩 {len(vtf_files)} 个文件 (使用 {max_workers} 个线程)...\n")
    
    # 统计信息
    success_count = 0
    fail_count = 0
    total_original_size = 0
    total_compressed_size = 0
    
    # 使用线程池进行并行压缩
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有压缩任务
        futures = {
            executor.submit(compress_single_file, vtf_file, seven_zip_path, output_dir): vtf_file
            for vtf_file in vtf_files
        }
        
        # 处理完成的任务
        completed = 0
        for future in as_completed(futures):
            completed += 1
            filename, success, original_size, compressed_size = future.result()
            
            if success:
                success_count += 1
                total_original_size += original_size
                total_compressed_size += compressed_size
                ratio = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0
                print(f"[{completed}/{len(vtf_files)}] ✓ {filename} → {filename}.bz2: {original_size/1024:.1f}KB → {compressed_size/1024:.1f}KB (节省 {ratio:.1f}%)")
            else:
                fail_count += 1
                print(f"[{completed}/{len(vtf_files)}] ✗ {filename}: 压缩失败")
    
    # 输出统计信息
    print("\n" + "="*60)
    print("压缩完成!")
    print(f"成功: {success_count} 个文件")
    print(f"失败: {fail_count} 个文件")
    
    if success_count > 0:
        total_saved = total_original_size - total_compressed_size
        total_ratio = (1 - total_compressed_size / total_original_size) * 100 if total_original_size > 0 else 0
        print(f"\n统计信息:")
        print(f"  原始总大小: {total_original_size / (1024*1024):.2f} MB")
        print(f"  压缩后总大小: {total_compressed_size / (1024*1024):.2f} MB")
        print(f"  节省空间: {total_saved / (1024*1024):.2f} MB ({total_ratio:.1f}%)")
    
    return fail_count == 0

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='将文件夹下每个.vtf文件单独压缩为.bz2文件 (文件名格式: 原名称.vtf.bz2)')
    parser.add_argument('folder', help='包含.vtf文件的文件夹路径')
    parser.add_argument('-o', '--output', help='输出文件夹路径 (默认: 与源文件相同目录)')
    parser.add_argument('-7z', '--sevenzip', help='7zip可执行文件路径')
    parser.add_argument('-w', '--workers', type=int, default=4, 
                       help='并行压缩的线程数 (默认: 4)')
    
    args = parser.parse_args()
    
    success = compress_vtf_files_separately(
        folder_path=args.folder,
        output_folder=args.output,
        seven_zip_path=args.sevenzip,
        max_workers=args.workers
    )
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()