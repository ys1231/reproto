#!/usr/bin/env python3
"""
Protobuf重构器 - 命令行入口

从JADX反编译的Java源码自动重构Protobuf .proto文件
支持任意Android应用，完全基于Java字节码推断

Usage:
    python -m proto_reconstructor.main <java_sources_dir> <root_class> <output_dir> [--log-dir LOG_DIR]

Example:
    python -m proto_reconstructor.main ./out_jadx/sources com.example.Model ./protos_generated --log-dir ./logs

Author: AI Assistant
"""

import sys
import argparse
from pathlib import Path

# 导入项目模块
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.reconstructor import ProtoReconstructor
from utils.logger import setup_logger, get_logger


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='从JADX反编译的Java源码重构Protobuf .proto文件',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s ./out_jadx/sources com.example.Model ./protos_generated
  %(prog)s ./out_jadx/sources com.example.Model ./output --log-dir ./my_logs
  %(prog)s /path/to/jadx/sources com.truecaller.search.v1.models.SearchResult ./output
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


def validate_arguments(args):
    """验证命令行参数"""
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
    
    # 输出目录可以不存在，会自动创建
    output_path = Path(args.output_dir)
    if output_path.exists() and not output_path.is_dir():
        logger.error(f"输出路径存在但不是目录: {output_path}")
        sys.exit(1)
    
    # 验证日志目录
    log_path = Path(args.log_dir)
    try:
        log_path.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error(f"无法创建日志目录 {log_path}: {e}")
        sys.exit(1)
    
    return sources_path.resolve(), args.root_class, output_path.resolve()


def main():
    """主函数"""
    args = None
    try:
        # 解析参数
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
        
        # 创建重构器并执行
        reconstructor = ProtoReconstructor(sources_dir, output_dir)
        results = reconstructor.reconstruct_from_root(root_class)
        
        # 输出结果统计
        if results:
            logger.success("✅ 重构完成!")
            logger.info(f"📊 处理统计: 共处理 {len(results)} 个类型")
            
            message_count = sum(1 for r in results.values() if hasattr(r, 'fields'))
            enum_count = sum(1 for r in results.values() if hasattr(r, 'values'))
            
            logger.info(f"   - 消息类型: {message_count} 个")
            logger.info(f"   - 枚举类型: {enum_count} 个")
        else:
            logger.warning("⚠️  没有生成任何proto文件")
        
    except KeyboardInterrupt:
        if args:
            logger = get_logger("main")
            logger.warning("⚠️  操作被用户中断")
        else:
            print("\n⚠️  操作被用户中断")
        sys.exit(1)
    except Exception as e:
        if args:
            logger = get_logger("main")
            logger.error(f"❌ 重构失败: {e}")
            if args.verbose:
                logger.exception("详细错误信息:")
        else:
            print(f"\n❌ 重构失败: {e}")
            if hasattr(args, 'verbose') and args.verbose:
                import traceback
                traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main() 