"""
Protobuf文件生成器

根据解析出的消息定义生成标准的.proto文件
支持完整的Protobuf语法，包括包声明、导入、Java选项和消息定义
集成Google Protobuf Well-Known Types支持

Author: AI Assistant
"""

import re
from typing import Dict, Set, List, Union, Optional

# 智能导入：同时支持相对导入（包环境）和绝对导入（开发环境）
try:
    # 相对导入（包环境）
    from ..models.message_definition import MessageDefinition, FieldDefinition, EnumDefinition, EnumValueDefinition
    from ..utils.type_utils import type_mapper, naming_converter, field_name_processor, TypeMapper
    from ..utils.logger import get_logger
except ImportError:
    # 绝对导入（开发环境）
    from models.message_definition import MessageDefinition, FieldDefinition, EnumDefinition, EnumValueDefinition
    from utils.type_utils import type_mapper, naming_converter, field_name_processor, TypeMapper
    from utils.logger import get_logger

# 常量定义
BASIC_PROTO_TYPES = {
    'string', 'int32', 'int64', 'uint32', 'uint64', 'sint32', 'sint64',
    'fixed32', 'fixed64', 'sfixed32', 'sfixed64', 'bool', 'float', 'double', 'bytes'
}

BASIC_JAVA_TYPES = {
    'string', 'int', 'long', 'boolean', 'bool', 'float', 'double', 'bytes',
    'int32', 'int64', 'uint32', 'uint64', 'sint32', 'sint64',
    'fixed32', 'fixed64', 'sfixed32', 'sfixed64'
}

class ProtoGenerator:
    """
    Protobuf文件生成器
    
    功能：
    - 生成标准格式的.proto文件
    - 自动处理导入依赖
    - 智能类型推断（枚举和消息类型）
    - 符合Protobuf命名规范
    """
    
    def generate_proto_file(self, message_def: MessageDefinition, 
                           all_messages: Dict[str, MessageDefinition],
                           all_enums: Dict[str, EnumDefinition] = None) -> str:
        """
        生成完整的proto文件内容
        
        Args:
            message_def: 要生成的消息定义
            all_messages: 所有消息定义的字典，用于依赖解析
            all_enums: 所有枚举定义的字典，用于依赖解析
            
        Returns:
            完整的proto文件内容字符串
        """
        try:
            if not message_def:
                raise ValueError("消息定义不能为空")
            
            if not message_def.name:
                raise ValueError("消息名称不能为空")
                
            lines = []
            
            # 1. 文件头
            lines.extend(self._generate_file_header())
            
            # 2. 包声明
            if message_def.package_name:
                lines.extend(self._generate_package_declaration(message_def.package_name))
            
            # 3. 导入语句
            imports = self._collect_imports(message_def, all_messages, all_enums)
            if imports:
                lines.extend(self._generate_imports(imports))
            
            # 4. Java选项
            if message_def.package_name:
                lines.extend(self._generate_java_options(message_def.package_name))
            
            # 5. 消息定义
            lines.extend(self._generate_message_definition(message_def, all_enums))
            
            return '\n'.join(lines)
            
        except Exception as e:
            logger = get_logger("proto_generator")
            logger.error(f"❌ 生成proto文件失败 {message_def.name if message_def else 'Unknown'}: {e}")
            raise
    
    def generate_enum_proto_file(self, enum_def: EnumDefinition, 
                                all_messages: Dict[str, MessageDefinition] = None,
                                all_enums: Dict[str, EnumDefinition] = None) -> str:
        """
        生成单个枚举的proto文件内容
        
        Args:
            enum_def: 要生成的枚举定义
            all_messages: 所有消息定义的字典（用于兼容性）
            all_enums: 所有枚举定义的字典（用于兼容性）
            
        Returns:
            完整的proto文件内容字符串
        """
        try:
            if not enum_def:
                raise ValueError("枚举定义不能为空")
            
            if not enum_def.name:
                raise ValueError("枚举名称不能为空")
                
            if not enum_def.values:
                raise ValueError(f"枚举 {enum_def.name} 没有定义任何值")
                
            lines = []
            
            # 1. 文件头
            lines.extend(self._generate_file_header())
            
            # 2. 包声明
            if enum_def.package_name:
                lines.extend(self._generate_package_declaration(enum_def.package_name))
            
            # 3. Java选项
            if enum_def.package_name:
                lines.extend(self._generate_java_options(enum_def.package_name))
            
            # 4. 枚举定义
            lines.extend(self._generate_enum_definition(enum_def))
            
            return '\n'.join(lines)
            
        except Exception as e:
            logger = get_logger("proto_generator")
            logger.error(f"❌ 生成枚举proto文件失败 {enum_def.name if enum_def else 'Unknown'}: {e}")
            raise
    
    def generate_enums_file(self, enum_defs: List[EnumDefinition], package_name: str) -> str:
        """
        生成包含多个枚举的enums.proto文件
        
        Args:
            enum_defs: 枚举定义列表
            package_name: 包名
            
        Returns:
            完整的proto文件内容字符串
        """
        lines = []
        
        # 1. 文件头
        lines.extend(self._generate_file_header())
        
        # 2. 包声明
        if package_name:
            lines.extend(self._generate_package_declaration(package_name))
        
        # 3. Java选项
        if package_name:
            lines.extend(self._generate_java_options(package_name))
        
        # 4. 所有枚举定义
        for i, enum_def in enumerate(enum_defs):
            if i > 0:
                lines.append('')  # 枚举之间添加空行
            lines.extend(self._generate_enum_definition(enum_def))
        
        return '\n'.join(lines)
    
    def _generate_file_header(self) -> List[str]:
        """生成proto文件头"""
        return ['syntax = "proto3";', '']
    
    def _generate_package_declaration(self, package_name: str) -> List[str]:
        """生成包声明"""
        return [f'package {package_name};', '']
    
    def _generate_imports(self, imports: Set[str]) -> List[str]:
        """生成导入语句"""
        lines = []
        for import_path in sorted(imports):
            lines.append(f'import "{import_path}";')
        lines.append('')
        return lines
    
    def _generate_java_options(self, package_name: str) -> List[str]:
        """生成Java编译选项"""
        return [
            f'option java_package = "{package_name}";',
            'option java_multiple_files = true;',
            ''
        ]
    
    def _generate_message_definition(self, message_def: MessageDefinition, all_enums: Dict[str, EnumDefinition] = None) -> List[str]:
        """
        生成消息定义
        
        Args:
            message_def: 消息定义对象
            all_enums: 所有枚举定义的字典
            
        Returns:
            消息定义的行列表
        """
        # 清理消息名称中的$符号
        clean_name = naming_converter.clean_proto_name(message_def.name)
        
        lines = []
        
        # 如果是内部类、匿名类或包含$的特殊类，添加原始Java类名注释
        if message_def.full_name and ('$' in message_def.full_name or 'Anonymous' in message_def.full_name):
            lines.append(f'// 原始Java类: {message_def.full_name}')
        
        lines.append(f'message {clean_name} {{')
        
        # 生成oneof字段（oneof字段内部也按tag排序）
        for oneof in message_def.oneofs:
            lines.extend(self._generate_oneof_definition(oneof, all_enums))
        
        # 生成常规字段（按tag排序）
        sorted_fields = sorted(message_def.fields, key=lambda field: field.tag)
        for field in sorted_fields:
            lines.append(self._generate_field_definition(field, all_enums))
        
        lines.append('}')
        return lines
    
    def _generate_enum_definition(self, enum_def: EnumDefinition) -> List[str]:
        """
        生成枚举定义
        
        Args:
            enum_def: 枚举定义对象
            
        Returns:
            枚举定义的行列表
        """
        # 清理枚举名称中的$符号
        clean_name = naming_converter.clean_proto_name(enum_def.name)
        
        lines = []
        
        # 如果是内部类、匿名类或包含$的特殊enum，添加原始Java类名注释
        if enum_def.full_name and ('$' in enum_def.full_name or 'Anonymous' in enum_def.full_name):
            lines.append(f'// 原始Java类: {enum_def.full_name}')
        
        lines.append(f'enum {clean_name} {{')
        
        # 生成枚举值（按value排序）
        sorted_values = sorted(enum_def.values, key=lambda enum_value: enum_value.value)
        for enum_value in sorted_values:
            lines.append(f'  {enum_value.name} = {enum_value.value};')
        
        lines.append('}')
        return lines
    
    def _generate_oneof_definition(self, oneof, all_enums: Dict[str, EnumDefinition] = None) -> List[str]:
        """生成oneof字段定义（字段按tag排序）"""
        lines = [f'  oneof {oneof.name} {{']
        
        # 对oneof内部的字段按tag排序
        sorted_fields = sorted(oneof.fields, key=lambda field: field.tag)
        for field in sorted_fields:
            field_type = self._resolve_field_type(field, all_enums)
            lines.append(f'    {field_type} {field.name} = {field.tag};')
        
        lines.append('  }')
        return lines
    
    def _generate_field_definition(self, field: FieldDefinition, all_enums: Dict[str, EnumDefinition] = None) -> str:
        """
        生成单个字段定义
        
        Args:
            field: 字段定义对象
            all_enums: 所有枚举定义的字典
            
        Returns:
            字段定义字符串
        """
        try:
            if not field:
                raise ValueError("字段定义不能为空")
                
            if not field.name:
                raise ValueError("字段名称不能为空")
                
            if field.tag is None or field.tag <= 0:
                raise ValueError(f"字段 {field.name} 的标签无效: {field.tag}")
                
            if not field.type_name:
                raise ValueError(f"字段 {field.name} 的类型不能为空")
            
            field_type = self._resolve_field_type(field, all_enums)
            
            if not field_type:
                raise ValueError(f"字段 {field.name} 无法解析类型: {field.type_name}")
            
            if field.rule == 'repeated':
                return f'  repeated {field_type} {field.name} = {field.tag};'
            else:
                return f'  {field_type} {field.name} = {field.tag};'
                
        except Exception as e:
            logger = get_logger("proto_generator")
            logger.error(f"❌ 生成字段定义失败 {field.name if field else 'Unknown'}: {e}")
            raise
    
    def _collect_imports(self, message_def: MessageDefinition, 
                        all_messages: Dict[str, MessageDefinition],
                        all_enums: Dict[str, EnumDefinition] = None) -> Set[str]:
        """
        收集需要导入的proto文件
        
        Args:
            message_def: 当前消息定义
            all_messages: 所有消息定义的字典
            all_enums: 所有枚举定义的字典
            
        Returns:
            导入路径的集合
        """
        imports = set()
        
        # 检查常规字段依赖
        for field in message_def.fields:
            import_path = self._get_field_import_path(field, message_def.package_name, all_messages, all_enums)
            if import_path:
                imports.add(import_path)
        
        # 检查oneof字段依赖
        for oneof in message_def.oneofs:
            for field in oneof.fields:
                import_path = self._get_field_import_path(field, message_def.package_name, all_messages, all_enums)
                if import_path:
                    imports.add(import_path)
        
        return imports
    
    def _get_field_import_path(self, field: FieldDefinition, current_package: str, 
                              all_messages: Dict[str, MessageDefinition],
                              all_enums: Dict[str, EnumDefinition] = None) -> str:
        """
        根据字段获取导入路径
        
        Args:
            field: 字段定义
            current_package: 当前包名
            all_messages: 所有消息定义
            all_enums: 所有枚举定义
            
        Returns:
            导入路径字符串，如果不需要导入则返回None
        """
        if not field.type_name:
            return None
            
        # 检查基础类型
        if field.type_name in BASIC_PROTO_TYPES:
            return None
        
        # 处理map类型：map<string, Contact> -> 提取值类型Contact
        if field.type_name.startswith('map<'):
            return self._handle_map_type_import(field.type_name, current_package, all_messages)
        
        # 检查是否为Google Protobuf内置类型
        builtin_import = self._handle_builtin_type_import(field.type_name)
        if builtin_import:
            return builtin_import
        
        # 跳过通用类型标识符
        generic_types = {'enum', 'message'}
        if field.type_name in generic_types:
            return None
        
        # 检查是否为枚举类型
        if all_enums:
            for enum_full_name, enum_def in all_enums.items():
                enum_class_name = enum_full_name.split('.')[-1]
                if field.type_name == enum_class_name or field.type_name == enum_def.name:
                    return self._class_name_to_import_path(enum_full_name)
        
        # 优先使用字段定义中保存的完整类名信息（用于内部类等特殊情况）
        if hasattr(field, 'full_class_name') and field.full_class_name:
            return self._class_name_to_import_path(field.full_class_name)
        
        # 解析完整类名（消息类型）
        full_class_name = self._resolve_full_class_name(field.type_name, current_package, all_messages)
        if full_class_name:
            return self._class_name_to_import_path(full_class_name)
        
        return None
    
    def _handle_builtin_type_import(self, type_name: str) -> Optional[str]:
        """
        处理Google Protobuf内置类型的导入
        
        Args:
            type_name: 类型名
            
        Returns:
            导入路径，如果不是内置类型则返回None
        """
        if not type_name.startswith('google.protobuf.'):
            return None
            
        try:
            from utils.builtin_proto import get_builtin_manager
            builtin_manager = get_builtin_manager()
            if builtin_manager.is_builtin_type(type_name):
                import_path = builtin_manager.get_import_path(type_name)
                if import_path:
                    # 确保内置proto文件被拷贝到输出目录
                    builtin_manager.ensure_builtin_proto_file(type_name)
                    return import_path
        except (ImportError, ValueError) as e:
            # 如果内置管理器不可用，记录错误但继续处理
            logger = get_logger("proto_generator")
            logger.warning(f"内置proto管理器不可用: {e}")
        
        return None
    
    def _handle_map_type_import(self, map_type: str, current_package: str, 
                               all_messages: Dict[str, MessageDefinition]) -> Optional[str]:
        """
        处理map类型的导入
        
        Args:
            map_type: map类型字符串，如"map<string, Contact>"
            current_package: 当前包名
            all_messages: 所有消息定义
            
        Returns:
            导入路径，如果不需要导入则返回None
        """
        # 解析map类型：map<key_type, value_type>
        import re
        match = re.match(r'map<([^,]+),\s*([^>]+)>', map_type)
        if not match:
            return None
            
        key_type, value_type = match.groups()
        key_type = key_type.strip()
        value_type = value_type.strip()
        
        # 检查值类型是否为Google Protobuf内置类型
        builtin_import = self._handle_builtin_type_import(value_type)
        if builtin_import:
            return builtin_import
        
        # 只处理值类型的导入（键类型通常是基础类型）
        if value_type not in BASIC_PROTO_TYPES:
            full_class_name = self._resolve_full_class_name(value_type, current_package, all_messages)
            if full_class_name:
                return self._class_name_to_import_path(full_class_name)
        
        return None
    
    def _resolve_full_class_name(self, type_name: str, current_package: str, 
                                all_messages: Dict[str, MessageDefinition]) -> str:
        """
        解析字段类型名为完整的类名
        
        Args:
            type_name: 字段类型名
            current_package: 当前包名
            all_messages: 所有消息定义
            
        Returns:
            完整的类名，如果是基础类型则返回None
        """
        # 检查是否为基础类型
        if type_name in BASIC_JAVA_TYPES:
            return None
        
        # 如果是完整的类名，直接返回
        if '.' in type_name:
            return type_name
        
        # 如果是简单类名，在all_messages中查找
        for full_name, msg_def in all_messages.items():
            if msg_def.name == type_name:
                return full_name
                
        # 如果找不到，假设在当前包中
        return f"{current_package}.{type_name}"
    
    def _class_name_to_import_path(self, class_name: str) -> str:
        """
        根据类名生成导入路径
        
        Args:
            class_name: 完整的Java类名
            
        Returns:
            proto导入路径
        """
        # com.example.Service$SkipRecovery -> com/example/service_skip_recovery.proto
        # 注意：这里要使用完整的类名（包含$符号）来生成文件名，与实际文件名保持一致
        parts = class_name.split('.')
        # 使用完整的类名部分（可能包含$）来生成proto文件名
        class_part = parts[-1]
        proto_name = self._to_snake_case(class_part) + '.proto'
        package_path = '/'.join(parts[:-1])
        return f"{package_path}/{proto_name}"
    
    def _resolve_field_type(self, field: FieldDefinition, all_enums: Dict[str, EnumDefinition] = None) -> str:
        """
        解析字段的最终类型名
        
        Args:
            field: 字段定义对象
            
        Returns:
            最终的proto类型名
        """
        # 基础类型直接映射
        basic_type = self._get_basic_proto_type(field.type_name)
        if basic_type:
            return basic_type
        
        # 处理map类型：map<string, Contact> -> map<string, Contact>
        if field.type_name.startswith('map<'):
            # 解析map类型并清理值类型名
            import re
            match = re.match(r'map<([^,]+),\s*([^>]+)>', field.type_name)
            if match:
                key_type, value_type = match.groups()
                key_type = key_type.strip()
                value_type = value_type.strip()
                
                # 如果值类型是完整类名，提取简单类型名
                if '.' in value_type:
                    value_type = value_type.split('.')[-1]
                
                return f"map<{key_type}, {value_type}>"
            return field.type_name
        
        # 枚举类型：根据字段名生成枚举类型名
        if field.type_name == 'enum':
            return self._generate_enum_type_name(field.name)
        
        # 消息类型：根据字段名生成消息类型名  
        if field.type_name == 'message':
            return self._generate_message_type_name(field.name)
        
        # 检查是否为枚举类型，如果是则使用清理后的枚举名
        if all_enums:
            for enum_full_name, enum_def in all_enums.items():
                enum_class_name = enum_full_name.split('.')[-1]  # 获取类名部分
                if field.type_name == enum_class_name:
                    # 使用清理后的枚举名，去掉$符号
                    return naming_converter.clean_proto_name(enum_def.name)
        
        # 已知的具体类型名，处理Google Protobuf类型和普通类型
        if '.' in field.type_name:
            # 如果是Google Protobuf类型，保持完整的类型名
            if field.type_name.startswith('google.protobuf.'):
                return field.type_name
            # 其他类型提取简单类型名，并清理$符号
            simple_name = field.type_name.split('.')[-1]
            return naming_converter.clean_proto_name(simple_name)
        else:
            # 清理简单类型名中的$符号
            return naming_converter.clean_proto_name(field.type_name)
    
    def _get_basic_proto_type(self, type_name: str) -> str:
        """
        获取基础proto类型
        
        Args:
            type_name: 类型名
            
        Returns:
            基础proto类型，如果不是基础类型则返回None
        """
        return type_mapper.java_to_proto_type(type_name) if type_mapper.is_java_basic_type(type_name) else None
    
    def _generate_enum_type_name(self, field_name: str) -> str:
        """
        根据字段名生成枚举类型名
        
        Args:
            field_name: 字段名
            
        Returns:
            枚举类型名（PascalCase）
        """
        return field_name_processor.generate_type_name_from_field(field_name, 'enum')
    
    def _generate_message_type_name(self, field_name: str) -> str:
        """
        根据字段名生成消息类型名
        
        Args:
            field_name: 字段名
            
        Returns:
            消息类型名（PascalCase）
        """
        return field_name_processor.generate_type_name_from_field(field_name, 'message')
    
    @staticmethod
    def _to_pascal_case(snake_str: str) -> str:
        """
        将snake_case转换为PascalCase
        
        Args:
            snake_str: 蛇形命名字符串
            
        Returns:
            帕斯卡命名字符串
        """
        return naming_converter.to_pascal_case(snake_str)
    
    @staticmethod
    def _to_snake_case(camel_str: str) -> str:
        """
        将CamelCase转换为snake_case
        
        Args:
            camel_str: 驼峰命名字符串
            
        Returns:
            蛇形命名字符串
        """
        return naming_converter.to_snake_case(camel_str) 