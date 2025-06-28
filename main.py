#!/usr/bin/env python3
"""
Protobuf重构器 - 命令行入口

从JADX反编译的Java源码自动重构Protobuf .proto文件
支持任意Android应用，完全基于Java字节码推断

Usage:
    python -m reproto.main <java_sources_dir> <root_class> <output_dir> [--log-dir LOG_DIR]

Example:
    python -m reproto.main ./out_jadx/sources com.example.Model ./protos_generated --log-dir ./logs

Author: AI Assistant
"""

import sys
import argparse
import traceback
from pathlib import Path

# 确保项目根目录在Python路径中
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 智能导入：同时支持相对导入（包环境）和绝对导入（开发环境）
try:
    # 相对导入（包环境）
    from .core.reconstructor import ProtoReconstructor
    from .utils.logger import setup_logger, get_logger
    from .utils.report_utils import print_results_summary
    from .utils.version_checker import check_version_on_startup
except ImportError:
    # 绝对导入（开发环境）
    from core.reconstructor import ProtoReconstructor
    from utils.logger import setup_logger, get_logger
    from utils.report_utils import print_results_summary
    from utils.version_checker import check_version_on_startup


def parse_arguments() -> argparse.Namespace:
    """
    解析命令行参数
    
    Returns:
        解析后的命令行参数对象
    """
    parser = argparse.ArgumentParser(
        description='从JADX反编译的Java源码重构Protobuf .proto文件',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s ./out_jadx/sources com.example.Model ./protos_generated
  %(prog)s ./out_jadx/sources com.example.Model ./output --log-dir ./my_logs
  %(prog)s /path/to/jadx/sources com.example.messaging.v1.models.MessageData ./output
        """
    )
    
    parser.add_argument(
        'sources_dir',
        type=str,
        help='JADX反编译的Java源码目录路径'
    )
    
    parser.add_argument(
        'root_class',
        type=str,
        help='要重构的根类完整类名 (如: com.example.Model)'
    )
    
    parser.add_argument(
        'output_dir',
        type=str,
        help='生成的proto文件输出目录路径'
    )
    
    parser.add_argument(
        '--log-dir',
        type=str,
        default='./logs',
        help='日志文件输出目录 (默认: ./logs)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='显示详细的处理信息'
    )
    
    return parser.parse_args()


def validate_arguments(args: argparse.Namespace) -> tuple[Path, str, Path]:
    """
    验证命令行参数的有效性
    
    Args:
        args: 解析后的命令行参数
        
    Returns:
        验证后的路径元组: (sources_path, root_class, output_path)
        
    Raises:
        SystemExit: 当参数无效时退出程序
    """
    logger = get_logger("main")
    
    # 验证源码目录
    sources_path = Path(args.sources_dir)
    if not sources_path.exists():
        logger.error(f"源码目录不存在: {sources_path}")
        sys.exit(1)
    
    if not sources_path.is_dir():
        logger.error(f"源码路径不是目录: {sources_path}")
        sys.exit(1)
    
    # 验证根类名格式
    if not args.root_class or '.' not in args.root_class:
        logger.error(f"根类名格式无效: {args.root_class}")
        logger.error("应该是完整的类名，如: com.example.Model")
        sys.exit(1)
    
    # 验证输出目录
    output_path = Path(args.output_dir)
    if output_path.exists() and not output_path.is_dir():
        logger.error(f"输出路径存在但不是目录: {output_path}")
        sys.exit(1)
    
    # 创建日志目录
    log_path = Path(args.log_dir)
    try:
        log_path.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error(f"无法创建日志目录 {log_path}: {e}")
        sys.exit(1)
    
    return sources_path.resolve(), args.root_class, output_path.resolve()


def main() -> None:
    """
    主函数：协调整个重构过程
    
    处理流程：
    1. 解析和验证命令行参数
    2. 初始化日志系统
    3. 启动版本检测（异步）
    4. 创建重构器并执行重构
    5. 输出结果统计信息
    """
    args = None
    try:
        # 解析和验证参数
        args = parse_arguments()
        
        # 初始化日志系统
        setup_logger(args.log_dir)
        logger = get_logger("main")
        
        # 启动版本检测（异步，不阻塞主程序）
        check_version_on_startup()
        
        # 验证参数
        sources_dir, root_class, output_dir = validate_arguments(args)
        
        # 显示启动信息
        logger.info("🚀 开始Proto重构任务")
        logger.info(f"📁 源码目录: {sources_dir}")
        logger.info(f"📁 输出目录: {output_dir}")
        logger.info(f"📁 日志目录: {args.log_dir}")
        logger.info(f"🎯 根类: {root_class}")
        
        # 创建重构器并执行重构
        reconstructor = ProtoReconstructor(sources_dir, output_dir)
        reconstructor._verbose = args.verbose  # 传递verbose标志
        results = reconstructor.reconstruct_from_root(root_class)
        
        # 输出结果统计
        print_results_summary(reconstructor, results, logger, args.verbose)
        
    except KeyboardInterrupt:
        # 处理用户中断
        if args:
            logger = get_logger("main")
            logger.warning("⚠️  操作被用户中断")
        else:
            print("\n⚠️  操作被用户中断")
        sys.exit(1)
        
    except Exception as e:
        # 处理其他异常
        if args:
            logger = get_logger("main")
            logger.error(f"❌ 重构失败: {e}")
            if args.verbose:
                logger.exception("详细错误信息:")
        else:
            print(f"\n❌ 重构失败: {e}")
            if hasattr(args, 'verbose') and args.verbose:
                traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main() 