"""
模型定义模块

包含Protobuf消息、字段、枚举等数据结构的定义
所有具体的类定义都在相应的子模块中
"""

# 智能导入：同时支持相对导入（包环境）和绝对导入（开发环境）
try:
    # 相对导入（包环境）
    from .message_definition import (
        MessageDefinition, 
        FieldDefinition, 
        OneofDefinition, 
        EnumDefinition, 
        EnumValueDefinition
    )
except ImportError:
    # 绝对导入（开发环境）
    from models.message_definition import (
        MessageDefinition, 
        FieldDefinition, 
        OneofDefinition, 
        EnumDefinition, 
        EnumValueDefinition
    )

__all__ = [
    'MessageDefinition',
    'FieldDefinition', 
    'OneofDefinition',
    'EnumDefinition',
    'EnumValueDefinition'
] 