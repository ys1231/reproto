"""
核心处理模块

包含Protobuf重构的核心逻辑：
- 信息解码器：解码Google Protobuf Lite的字节码
- 重构器：管理整个重构过程和依赖发现
"""

from .info_decoder import InfoDecoder
from .reconstructor import ProtoReconstructor, JavaSourceAnalyzer

__all__ = [
    'InfoDecoder',
    'ProtoReconstructor', 
    'JavaSourceAnalyzer'
]



