"""
核心处理模块

包含Protobuf重构的核心逻辑：
- 信息解码器：解码Google Protobuf Lite的字节码
- 重构器：管理整个重构过程和依赖发现
"""

# 智能导入：同时支持相对导入（包环境）和绝对导入（开发环境）
try:
    # 相对导入（包环境）
    from .info_decoder import InfoDecoder
    from .reconstructor import ProtoReconstructor, JavaSourceAnalyzer
except ImportError:
    # 绝对导入（开发环境）
    from core.info_decoder import InfoDecoder
    from core.reconstructor import ProtoReconstructor, JavaSourceAnalyzer

__all__ = [
    'InfoDecoder',
    'ProtoReconstructor', 
    'JavaSourceAnalyzer'
]



