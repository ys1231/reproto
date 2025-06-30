"""
类型工具类 - 统一处理类型映射和命名转换
"""

import re
from typing import Dict, Optional, Set


class TypeMapper:
    """统一的类型映射器"""
    
    # Java基础类型到Protobuf类型的映射（基于语言规范，合理的硬编码）
    _JAVA_TO_PROTO_MAPPING = {
        # Java基础类型
        'int': 'int32',
        'long': 'int64', 
        'float': 'float',
        'double': 'double',
        'boolean': 'bool',
        'byte': 'int32',
        'short': 'int32',
        'char': 'int32',
        
        # Java包装类型
        'Integer': 'int32',
        'Long': 'int64',
        'Boolean': 'bool',
        'Float': 'float',
        'Double': 'double',
        'Byte': 'int32',
        'Short': 'int32',
        'Character': 'int32',
        'String': 'string',
        
        # Java完整类名
        'java.lang.String': 'string',
        'java.lang.Integer': 'int32',
        'java.lang.Long': 'int64',
        'java.lang.Float': 'float',
        'java.lang.Double': 'double',
        'java.lang.Boolean': 'bool',
        'java.lang.Byte': 'int32',
        'java.lang.Short': 'int32',
        'java.lang.Character': 'int32',
        
        # 特殊类型
        'byte[]': 'bytes',
        'ByteString': 'bytes',
        'com.google.protobuf.ByteString': 'bytes',
        
        # Google Protobuf Well-Known Types
        'com.google.protobuf.Any': 'google.protobuf.Any',
        'com.google.protobuf.Timestamp': 'google.protobuf.Timestamp',
        'com.google.protobuf.Duration': 'google.protobuf.Duration',
        'com.google.protobuf.Empty': 'google.protobuf.Empty',
        'com.google.protobuf.Struct': 'google.protobuf.Struct',
        'com.google.protobuf.Value': 'google.protobuf.Value',
        'com.google.protobuf.ListValue': 'google.protobuf.ListValue',
        'com.google.protobuf.FieldMask': 'google.protobuf.FieldMask',
        
        # Protobuf Wrapper Types (现在已过时，但仍需支持)
        'com.google.protobuf.BoolValue': 'google.protobuf.BoolValue',
        'com.google.protobuf.Int32Value': 'google.protobuf.Int32Value',
        'com.google.protobuf.Int64Value': 'google.protobuf.Int64Value',
        'com.google.protobuf.UInt32Value': 'google.protobuf.UInt32Value',
        'com.google.protobuf.UInt64Value': 'google.protobuf.UInt64Value',
        'com.google.protobuf.FloatValue': 'google.protobuf.FloatValue',
        'com.google.protobuf.DoubleValue': 'google.protobuf.DoubleValue',
        'com.google.protobuf.StringValue': 'google.protobuf.StringValue',
        'com.google.protobuf.BytesValue': 'google.protobuf.BytesValue',
    }
    
    # Protobuf标准类型集合
    _PROTO_BASIC_TYPES = {
        'string', 'int32', 'int64', 'uint32', 'uint64', 'sint32', 'sint64',
        'fixed32', 'fixed64', 'sfixed32', 'sfixed64', 'bool', 'float', 'double', 'bytes'
    }
    
    # Java系统包前缀（用于过滤）
    _SYSTEM_PACKAGES = {
        'java.', 'javax.', 'android.', 'androidx.',
        'kotlin.', 'kotlinx.', 'com.google.common.',
        'org.apache.', 'org.junit.', 'junit.'
    }
    
    # 泛型容器类型模式（基于Protobuf实现规律，可配置）
    _GENERIC_TYPE_PATTERNS = {
        # Map类型模式
        'map_patterns': ['MapFieldLite<', 'Map<', 'java.util.Map<'],
        # List类型模式  
        'list_patterns': ['Internal.ProtobufList<', 'List<', 'ArrayList<', 
                         'java.util.List<', 'java.util.ArrayList<'],
        # 特殊列表类型
        'special_lists': {'Internal.IntList': 'int32'}
    }
    
    @classmethod
    def java_to_proto_type(cls, java_type: str) -> str:
        """
        将Java类型转换为Protobuf类型
        
        Args:
            java_type: Java类型名
            
        Returns:
            对应的Protobuf类型名
        """
        # 处理特殊列表类型（无泛型）
        if java_type in cls._GENERIC_TYPE_PATTERNS['special_lists']:
            return cls._GENERIC_TYPE_PATTERNS['special_lists'][java_type]
        
        # 处理Map类型（通用模式匹配）
        for pattern in cls._GENERIC_TYPE_PATTERNS['map_patterns']:
            if java_type.startswith(pattern) and java_type.endswith('>'):
                # 提取泛型参数
                generic_part = java_type[len(pattern):-1]
                
                # 解析键值类型，处理嵌套的尖括号
                key_type, value_type = cls._parse_map_generic_types(generic_part)
                
                # 递归转换键值类型
                proto_key_type = cls.java_to_proto_type(key_type.strip())
                proto_value_type = cls.java_to_proto_type(value_type.strip())
                
                return f"map<{proto_key_type}, {proto_value_type}>"
        
        # 处理List类型（通用模式匹配）
        for pattern in cls._GENERIC_TYPE_PATTERNS['list_patterns']:
            if java_type.startswith(pattern) and java_type.endswith('>'):
                # 提取元素类型
                start_pos = len(pattern)
                element_type = java_type[start_pos:-1]
                # 递归转换元素类型
                return cls.java_to_proto_type(element_type.strip())
        
        # 直接映射
        if java_type in cls._JAVA_TO_PROTO_MAPPING:
            return cls._JAVA_TO_PROTO_MAPPING[java_type]
        
        # 如果是完整的类名，提取简单类名
        if '.' in java_type:
            return java_type.split('.')[-1]
        
        # 默认返回原类型名
        return java_type
    
    @classmethod
    def is_basic_proto_type(cls, type_name: str) -> bool:
        """检查是否为Protobuf基础类型"""
        return type_name in cls._PROTO_BASIC_TYPES
    
    @classmethod
    def is_java_basic_type(cls, type_name: str) -> bool:
        """检查是否为Java基础类型"""
        return type_name in cls._JAVA_TO_PROTO_MAPPING
    
    @classmethod
    def is_system_package(cls, class_name: str) -> bool:
        """检查是否为系统包"""
        return any(class_name.startswith(pkg) for pkg in cls._SYSTEM_PACKAGES)
    
    @classmethod
    def is_well_known_type(cls, type_name: str) -> bool:
        """检查是否为Google Protobuf Well-Known Type"""
        return type_name.startswith('google.protobuf.')
    
    @classmethod
    def get_required_imports(cls, proto_type: str) -> list:
        """获取类型所需的导入语句"""
        imports = []
        if cls.is_well_known_type(proto_type):
            # 使用内置proto管理器获取正确的导入路径
            try:
                from utils.builtin_proto import get_builtin_manager
                builtin_manager = get_builtin_manager()
                import_path = builtin_manager.get_import_path(proto_type)
                if import_path:
                    imports.append(import_path)
            except (ImportError, ValueError):
                # 如果内置管理器不可用，使用旧逻辑作为后备
                type_name = proto_type.split('.')[-1].lower()
                imports.append(f"google/protobuf/{type_name}.proto")
        return imports
    
    @classmethod
    def add_generic_pattern(cls, category: str, pattern: str):
        """动态添加泛型类型模式（用于扩展性）"""
        if category in cls._GENERIC_TYPE_PATTERNS:
            if isinstance(cls._GENERIC_TYPE_PATTERNS[category], list):
                if pattern not in cls._GENERIC_TYPE_PATTERNS[category]:
                    cls._GENERIC_TYPE_PATTERNS[category].append(pattern)
    
    @classmethod
    def add_special_mapping(cls, java_type: str, proto_type: str):
        """动态添加特殊类型映射（用于扩展性）"""
        cls._GENERIC_TYPE_PATTERNS['special_lists'][java_type] = proto_type
    
    @classmethod
    def _parse_map_generic_types(cls, generic_part: str) -> tuple:
        """
        解析map泛型参数，处理嵌套的尖括号
        
        Args:
            generic_part: 泛型部分，如 "String, Contact" 或 "String, List<Contact>"
            
        Returns:
            (key_type, value_type) 元组
        """
        # 简单情况：没有嵌套的尖括号
        if '<' not in generic_part:
            parts = [part.strip() for part in generic_part.split(',', 1)]
            if len(parts) == 2:
                return parts[0], parts[1]
        
        # 复杂情况：处理嵌套的尖括号
        bracket_count = 0
        for i, char in enumerate(generic_part):
            if char == '<':
                bracket_count += 1
            elif char == '>':
                bracket_count -= 1
            elif char == ',' and bracket_count == 0:
                # 找到分隔符
                key_type = generic_part[:i].strip()
                value_type = generic_part[i+1:].strip()
                return key_type, value_type
        
        # 如果解析失败，返回默认值
        return 'string', 'string'


class NamingConverter:
    """统一的命名转换器"""
    
    @staticmethod
    def to_snake_case(camel_str: str) -> str:
        """
        将CamelCase转换为snake_case，同时处理$符号
        
        Args:
            camel_str: 驼峰命名字符串
            
        Returns:
            蛇形命名字符串
        """
        if not camel_str:
            return camel_str
            
        # 首先处理$符号：将$替换为_，处理内部类和匿名类
        s0 = camel_str.replace('$', '_')
        
        # 处理连续大写字母：XMLParser -> XML_Parser
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', s0)
        # 处理小写字母后跟大写字母：userId -> user_Id
        s2 = re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1)
        
        # 清理多余的下划线：将连续的下划线替换为单个下划线
        s3 = re.sub('_+', '_', s2)
        
        return s3.lower()
    
    @staticmethod
    def to_pascal_case(snake_str: str) -> str:
        """
        将snake_case转换为PascalCase
        
        Args:
            snake_str: 蛇形命名字符串
            
        Returns:
            帕斯卡命名字符串
        """
        if not snake_str:
            return snake_str
            
        components = snake_str.split('_')
        return ''.join(word.capitalize() for word in components if word)
    
    @staticmethod
    def to_camel_case(snake_str: str) -> str:
        """
        将snake_case转换为camelCase
        
        Args:
            snake_str: 蛇形命名字符串
            
        Returns:
            驼峰命名字符串
        """
        if not snake_str:
            return snake_str
            
        components = snake_str.split('_')
        if not components:
            return snake_str
            
        # 第一个单词保持小写，其余单词首字母大写
        return components[0].lower() + ''.join(word.capitalize() for word in components[1:] if word)
    
    @staticmethod
    def clean_proto_name(name: str) -> str:
        """
        清理proto名称中的$符号，用于消息和枚举名称
        
        Args:
            name: 原始名称（可能包含$符号）
            
        Returns:
            清理后的名称
        """
        if not name:
            return name
            
        # 修复：正确处理内部类的$符号
        # 不能简单删除$，这会导致Models$Device和Models$Push等内部类
        # 与其内部枚举混淆，应该转换为更明确的命名
        if '$' in name:
            # 将$替换为下划线，保持类型区分
            # Models$Device -> Models_Device
            # Models$Push -> Models_Push
            return name.replace('$', '_')
        
        return name


class FieldNameProcessor:
    """字段名处理器 - 基于规律的智能处理"""
    
    @staticmethod
    def generate_type_name_from_field(field_name: str, target_type: str = 'message') -> str:
        """
        基于字段名生成类型名（使用规律而非硬编码）
        
        Args:
            field_name: 字段名
            target_type: 目标类型 ('enum' 或 'message')
            
        Returns:
            生成的类型名
        """
        # 清理字段名
        name = field_name.rstrip('_')
        
        # 应用智能后缀转换（基于英语语言规律）
        name = FieldNameProcessor._apply_suffix_transformation(name, target_type)
        
        # 处理复数形式（仅对枚举类型）
        if target_type == 'enum' and FieldNameProcessor._is_plural(name):
            name = FieldNameProcessor._to_singular(name)
        
        return NamingConverter.to_pascal_case(name)
    
    @staticmethod
    def _apply_suffix_transformation(name: str, target_type: str) -> str:
        """
        应用后缀转换（基于英语语言规律，无硬编码）
        
        Args:
            name: 原始名称
            target_type: 目标类型
            
        Returns:
            转换后的名称
        """
        # 检查是否以下划线+单词结尾的模式
        suffix_pattern = re.search(r'_([a-z]+)$', name)
        if suffix_pattern:
            suffix = suffix_pattern.group(1)
            prefix = name[:suffix_pattern.start()]
            
            # 特殊情况：如果后缀本身就是有意义的类型名，进行转换
            if FieldNameProcessor._is_meaningful_type_suffix(suffix, target_type):
                # 应用英语首字母大写规律（这是语言规律，不是硬编码）
                capitalized_suffix = suffix.capitalize()
                return prefix + capitalized_suffix
        
        return name
    
    @staticmethod
    def _is_meaningful_type_suffix(suffix: str, target_type: str) -> bool:
        """
        判断后缀是否为有意义的类型后缀（基于语义分析）
        
        Args:
            suffix: 后缀
            target_type: 目标类型
            
        Returns:
            是否为有意义的类型后缀
        """
        # 常见的类型相关词汇（基于英语语义，不是应用特定的）
        enum_words = {'type', 'status', 'state', 'mode', 'level', 'kind', 'category', 'code'}
        message_words = {'info', 'data', 'details', 'config', 'setting', 'metadata', 'stats', 'profile'}
        
        if target_type == 'enum':
            return suffix in enum_words
        else:  # message
            return suffix in message_words
    
    @staticmethod
    def _is_plural(name: str) -> bool:
        """
        判断名称是否为复数形式（基于英语语法规律）
        
        Args:
            name: 名称
            
        Returns:
            是否为复数
        """
        if len(name) <= 1:
            return False
        
        # 简单的英语复数规则检查
        if name.endswith('s') and not name.endswith('ss'):
            # 排除一些明显不是复数的情况
            non_plural_endings = {'class', 'pass', 'address', 'access', 'process', 'status'}
            return name not in non_plural_endings
        
        return False
    
    @staticmethod
    def _to_singular(name: str) -> str:
        """
        将复数转换为单数（基于英语语法规律）
        
        Args:
            name: 复数名称
            
        Returns:
            单数名称
        """
        if not name.endswith('s') or len(name) <= 1:
            return name
        
        # 简单的英语单数转换规则
        if name.endswith('ies') and len(name) > 3:
            # categories -> category
            return name[:-3] + 'y'
        elif name.endswith('es') and len(name) > 2:
            # boxes -> box, but not "types" -> "typ"
            if name.endswith(('ches', 'shes', 'xes', 'zes')):
                return name[:-2]
            else:
                return name[:-1]
        else:
            # 一般情况：直接去掉s
            return name[:-1]


# 全局实例，方便使用
type_mapper = TypeMapper()
naming_converter = NamingConverter()
field_name_processor = FieldNameProcessor() 