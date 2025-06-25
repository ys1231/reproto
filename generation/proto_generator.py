"""
Protobuf文件生成器

根据解析出的消息定义生成标准的.proto文件
支持完整的Protobuf语法，包括包声明、导入、Java选项和消息定义

Author: AI Assistant
"""

import re
from typing import Dict, Set, List, Union
from models.message_definition import MessageDefinition, FieldDefinition, EnumDefinition, EnumValueDefinition


class ProtoGenerator:
    """
    Protobuf文件生成器
    
    功能：
    - 生成标准格式的.proto文件
    - 自动处理导入依赖
    - 智能类型推断（枚举和消息类型）
    - 符合Protobuf命名规范
    """
    
    def generate_proto_file(self, message_def: MessageDefinition, all_messages: Dict[str, MessageDefinition]) -> str:
        """
        生成完整的proto文件内容
        
        Args:
            message_def: 要生成的消息定义
            all_messages: 所有消息定义的字典，用于依赖解析
            
        Returns:
            完整的proto文件内容字符串
        """
        lines = []
        
        # 1. 文件头
        lines.extend(self._generate_file_header())
        
        # 2. 包声明
        if message_def.package_name:
            lines.extend(self._generate_package_declaration(message_def.package_name))
        
        # 3. 导入语句
        imports = self._collect_imports(message_def, all_messages)
        if imports:
            lines.extend(self._generate_imports(imports))
        
        # 4. Java选项
        if message_def.package_name:
            lines.extend(self._generate_java_options(message_def.package_name))
        
        # 5. 消息定义
        lines.extend(self._generate_message_definition(message_def))
        
        return '\n'.join(lines)
    
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
    
    def _generate_message_definition(self, message_def: MessageDefinition) -> List[str]:
        """
        生成消息定义
        
        Args:
            message_def: 消息定义对象
            
        Returns:
            消息定义的行列表
        """
        lines = [f'message {message_def.name} {{']
        
        # 生成oneof字段
        for oneof in message_def.oneofs:
            lines.extend(self._generate_oneof_definition(oneof))
        
        # 生成常规字段
        for field in message_def.fields:
            lines.append(self._generate_field_definition(field))
        
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
        lines = [f'enum {enum_def.name} {{']
        
        # 生成枚举值
        for enum_value in enum_def.values:
            lines.append(f'  {enum_value.name} = {enum_value.value};')
        
        lines.append('}')
        return lines
    
    def _generate_oneof_definition(self, oneof) -> List[str]:
        """生成oneof字段定义"""
        lines = [f'  oneof {oneof.name} {{']
        for field in oneof.fields:
            field_type = self._resolve_field_type(field)
            lines.append(f'    {field_type} {field.name} = {field.tag};')
        lines.append('  }')
        return lines
    
    def _generate_field_definition(self, field: FieldDefinition) -> str:
        """
        生成单个字段定义
        
        Args:
            field: 字段定义对象
            
        Returns:
            字段定义字符串
        """
        field_type = self._resolve_field_type(field)
        
        if field.rule == 'repeated':
            return f'  repeated {field_type} {field.name} = {field.tag};'
        else:
            return f'  {field_type} {field.name} = {field.tag};'
    
    def _collect_imports(self, message_def: MessageDefinition, all_messages: Dict[str, MessageDefinition]) -> Set[str]:
        """
        收集需要导入的proto文件
        
        Args:
            message_def: 当前消息定义
            all_messages: 所有消息定义的字典
            
        Returns:
            导入路径的集合
        """
        imports = set()
        
        # 检查常规字段依赖
        for field in message_def.fields:
            import_path = self._get_field_import_path(field, message_def.package_name, all_messages)
            if import_path:
                imports.add(import_path)
        
        # 检查oneof字段依赖
        for oneof in message_def.oneofs:
            for field in oneof.fields:
                import_path = self._get_field_import_path(field, message_def.package_name, all_messages)
                if import_path:
                    imports.add(import_path)
        
        return imports
    
    def _get_field_import_path(self, field: FieldDefinition, current_package: str, 
                              all_messages: Dict[str, MessageDefinition]) -> str:
        """
        根据字段获取导入路径
        
        Args:
            field: 字段定义
            current_package: 当前包名
            all_messages: 所有消息定义
            
        Returns:
            导入路径字符串，如果不需要导入则返回None
        """
        if not field.type_name:
            return None
            
        # 跳过基础类型
        basic_types = {'string', 'int32', 'int64', 'bool', 'float', 'double', 'bytes', 'enum', 'message'}
        if field.type_name in basic_types:
            return None
        
        # 解析完整类名
        full_class_name = self._resolve_full_class_name(field.type_name, current_package, all_messages)
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
            完整的类名
        """
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
        # com.example.Model -> com/example/model.proto
        parts = class_name.split('.')
        proto_name = self._to_snake_case(parts[-1]) + '.proto'
        package_path = '/'.join(parts[:-1])
        return f"{package_path}/{proto_name}"
    
    def _resolve_field_type(self, field: FieldDefinition) -> str:
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
        
        # 枚举类型：根据字段名生成枚举类型名
        if field.type_name == 'enum':
            return self._generate_enum_type_name(field.name)
        
        # 消息类型：根据字段名生成消息类型名  
        if field.type_name == 'message':
            return self._generate_message_type_name(field.name)
        
        # 已知的具体类型名，提取简单类型名
        if '.' in field.type_name:
            # 从完整类名中提取简单类型名
            return field.type_name.split('.')[-1]
        else:
            return field.type_name
    
    def _get_basic_proto_type(self, type_name: str) -> str:
        """
        获取基础proto类型
        
        Args:
            type_name: 类型名
            
        Returns:
            基础proto类型，如果不是基础类型则返回None
        """
        basic_type_mapping = {
            'string': 'string',
            'int32': 'int32',
            'int64': 'int64',
            'bool': 'bool',
            'float': 'float',
            'double': 'double',
            'bytes': 'bytes',
        }
        return basic_type_mapping.get(type_name)
    
    def _generate_enum_type_name(self, field_name: str) -> str:
        """
        根据字段名生成枚举类型名
        
        Args:
            field_name: 字段名
            
        Returns:
            枚举类型名（PascalCase）
        """
        name = field_name.rstrip('_')
        
        # 特殊字段名修正
        field_name_corrections = {
            'access': 'Access',  # 修正拼写
        }
        
        if name in field_name_corrections:
            return field_name_corrections[name]
        
        # 处理常见的枚举后缀
        suffix_mappings = {
            '_type': 'Type',
            '_status': 'Status',
            '_code': 'Code'
        }
        
        for suffix, replacement in suffix_mappings.items():
            if name.endswith(suffix):
                name = name[:-len(suffix)] + replacement
                break
        
        # 处理复数形式：badges -> badge
        if name.endswith('s') and len(name) > 1:
            name = name[:-1]
        
        return self._to_pascal_case(name)
    
    def _generate_message_type_name(self, field_name: str) -> str:
        """
        根据字段名生成消息类型名
        
        Args:
            field_name: 字段名
            
        Returns:
            消息类型名（PascalCase）
        """
        name = field_name.rstrip('_')
        
        # 处理常见的消息后缀
        suffix_mappings = {
            '_info': 'Info',
            '_data': 'Data',
            '_stats': 'Stats',
            '_profile': 'Profile',
            '_config': 'Config'
        }
        
        for suffix, replacement in suffix_mappings.items():
            if name.endswith(suffix):
                name = name[:-len(suffix)] + replacement
                break
        
        return self._to_pascal_case(name)
    
    @staticmethod
    def _to_pascal_case(snake_str: str) -> str:
        """
        将snake_case转换为PascalCase
        
        Args:
            snake_str: 蛇形命名字符串
            
        Returns:
            帕斯卡命名字符串
        """
        components = snake_str.split('_')
        return ''.join(word.capitalize() for word in components)
    
    @staticmethod
    def _to_snake_case(camel_str: str) -> str:
        """
        将CamelCase转换为snake_case
        
        Args:
            camel_str: 驼峰命名字符串
            
        Returns:
            蛇形命名字符串
        """
        # 处理连续大写字母：XMLParser -> XML_Parser
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', camel_str)
        # 处理小写字母后跟大写字母：userId -> user_Id
        s2 = re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1)
        return s2.lower() 