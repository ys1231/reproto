"""
结果报告工具模块

提供重构结果的统计、报告和展示功能
"""

import sys
from typing import Dict, Any, TYPE_CHECKING

# 智能导入：同时支持相对导入（包环境）和绝对导入（开发环境）
if TYPE_CHECKING:
    try:
        # 相对导入（包环境）
        from ..core.reconstructor import ProtoReconstructor
    except ImportError:
        # 绝对导入（开发环境）
        from core.reconstructor import ProtoReconstructor


def print_results_summary(reconstructor: 'ProtoReconstructor', results: Dict[str, Any], logger, verbose: bool) -> None:
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