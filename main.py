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

from core.reconstructor import ProtoReconstructor
from utils.logger import setup_logger, get_logger


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


def print_results_summary(reconstructor: ProtoReconstructor, results: dict, logger, verbose: bool) -> None:
    """
    打印重构结果的详细统计信息
    
    Args:
        reconstructor: 重构器实例
        results: 重构结果字典
        logger: 日志记录器
        verbose: 是否显示详细信息
    """
    if not results:
        logger.error("❌ 没有生成任何proto文件!")
        logger.error("请检查:")
        logger.error("  1. 根类名是否正确")
        logger.error("  2. Java源码目录是否包含对应的文件")
        logger.error("  3. 类是否为protobuf消息类")
        
        # 显示详细的失败信息
        if hasattr(reconstructor, 'failed_classes') and reconstructor.failed_classes:
            logger.error("失败的类:")
            for failed_class, reason in reconstructor.failed_classes.items():
                logger.error(f"  • {failed_class}: {reason}")
        
        sys.exit(1)
    
    # 统计成功和失败的数量
    success_count = len(results)
    failed_count = len(reconstructor.failed_classes) if hasattr(reconstructor, 'failed_classes') else 0
    total_attempted = success_count + failed_count
    
    logger.success("✅ 重构完成!")
    logger.info(f"📊 处理统计: 共尝试处理 {total_attempted} 个类型")
    
    # 统计消息和枚举数量
    message_count = sum(1 for r in results.values() if hasattr(r, 'fields'))
    enum_count = sum(1 for r in results.values() if hasattr(r, 'values'))
    
    logger.info(f"   - ✅ 成功: {success_count} 个 (消息: {message_count}, 枚举: {enum_count})")
    
    # 显示失败的类
    if hasattr(reconstructor, 'failed_classes') and reconstructor.failed_classes:
        logger.warning(f"   - ❌ 失败: {failed_count} 个")
        for failed_class, reason in reconstructor.failed_classes.items():
            logger.warning(f"     • {failed_class}: {reason}")
    
    # 显示跳过的类
    if hasattr(reconstructor, 'skipped_classes') and reconstructor.skipped_classes:
        skipped_count = len(reconstructor.skipped_classes)
        logger.info(f"   - ⏭️  跳过: {skipped_count} 个 (基础类型或已处理)")
        if verbose:
            for skipped_class, reason in reconstructor.skipped_classes.items():
                logger.info(f"     • {skipped_class}: {reason}")


def main() -> None:
    """
    主函数：协调整个重构过程
    
    处理流程：
    1. 解析和验证命令行参数
    2. 初始化日志系统
    3. 创建重构器并执行重构
    4. 输出结果统计信息
    """
    args = None
    try:
        # 解析和验证参数
        args = parse_arguments()
        
        # 初始化日志系统
        setup_logger(args.log_dir)
        logger = get_logger("main")
        
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