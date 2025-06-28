"""
工具模块

包含各种辅助工具和实用程序：
- 日志系统：统一的日志管理
- 文件缓存：优化文件I/O性能
- 类型工具：类型转换和命名规范处理
- 内置Proto：Google Protobuf标准类型支持
- 报告工具：重构结果统计和展示
- 版本检测：通用版本更新检测系统
"""

# 智能导入：同时支持相对导入（包环境）和绝对导入（开发环境）
try:
    # 相对导入（包环境）
    from .logger import setup_logger, get_logger
    from .file_cache import get_file_cache
    from .type_utils import type_mapper, naming_converter, field_name_processor
    from .builtin_proto import get_builtin_manager
    from .type_index import get_type_index
    from .report_utils import print_results_summary
    from .version_checker import (
        VersionChecker, create_version_checker, check_pypi_version,
        check_reproto_version, check_version_on_startup, get_package_version
    )
except ImportError:
    # 绝对导入（开发环境）
    from utils.logger import setup_logger, get_logger
    from utils.file_cache import get_file_cache
    from utils.type_utils import type_mapper, naming_converter, field_name_processor
    from utils.builtin_proto import get_builtin_manager
    from utils.type_index import get_type_index
    from utils.report_utils import print_results_summary
    from utils.version_checker import (
        VersionChecker, create_version_checker, check_pypi_version,
        check_reproto_version, check_version_on_startup, get_package_version
    )

__all__ = [
    'setup_logger',
    'get_logger', 
    'get_file_cache',
    'type_mapper',
    'naming_converter',
    'field_name_processor',
    'get_builtin_manager',
    'get_type_index',
    'print_results_summary',
    'VersionChecker',
    'create_version_checker',
    'check_pypi_version',
    'check_reproto_version',
    'check_version_on_startup',
    'get_package_version'
]



