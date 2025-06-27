"""
Protobuf信息解码器

解码Google Protobuf Lite的newMessageInfo字节码
这是项目的核心技术突破：首次成功逆向工程Protobuf Lite的字节码格式

字节码格式说明：
- 每2个字节表示一个字段：[字段标签, 字段类型]
- 特殊字符 '<' (ord=60) 标识oneof字段
- 类型映射：1=float, 2=int64, 3=int32, 4=bool, 9=message, 12=enum, 27=repeated_message, 520=string, 538=repeated_string

Author: AI Assistant
"""

import re
from typing import Optional, List

from models.message_definition import MessageDefinition, FieldDefinition, OneofDefinition
from utils.logger import get_logger


class InfoDecoder:
    """
    Protobuf信息解码器
    
    核心功能：解码Google Protobuf Lite的newMessageInfo字节码
    将字节码转换为结构化的消息定义，包括字段类型、标签和规则
    """
    
    def __init__(self, java_source_analyzer=None):
        """
        初始化信息解码器
        
        Args:
            java_source_analyzer: Java源码分析器实例（可选）
        """
        self.logger = get_logger("info_decoder")
        self.java_source_analyzer = java_source_analyzer
        
        # 导入JavaParser
        from parsing.java_parser import JavaParser
        self.java_parser = JavaParser()
        
        # Protobuf字段类型映射表
        # 键：字节码中的类型值，值：对应的protobuf字段类型
        self.type_mapping = {
            0: 'double',      # 64位浮点数 (double) - 基于ContactAddress.latitude_和longitude_的分析
            1: 'float',      # FLOAT
            2: 'int64',      # INT64  
            3: 'int32',      # INT32
            4: 'int32',      # INT32 (修正：4对应int32，不是bool)
            5: 'int64',      # INT64 - 基于Models$Onboarded.userId_和phoneNumber_的分析
            6: 'int32',      # INT32 - 基于Assistant$Payload.action_的分析
            7: 'bool',       # BOOL (修正：7对应bool)
            9: 'message',    # MESSAGE (嵌套消息)
            12: 'enum',      # ENUM (枚举类型)
            27: 'repeated_message',   # REPEATED MESSAGE (修正：27表示repeated message)
            39: 'repeated_int32',     # REPEATED INT32 (packed)
            44: 'repeated_enum',      # PACKED ENUM (修正：44表示repeated enum)
            50: 'map',       # Map字段 - 基于BulkSearchResult.contacts的分析
            92: 'string',    # STRING - 基于Assistant$Payload.title_的分析
            520: 'string',   # UTF-8字符串
            538: 'repeated_string',   # REPEATED STRING (Ț = 538)  
            4100: 'int32',   # INT32 - 基于Assistant$Payload.action_的分析
            4108: 'enum',    # ENUM - 基于Assistant$Payload.payloadType_的分析
            4616: 'string',  # STRING - 基于Assistant$Payload.summary_的分析
        }
        
        # 统计未知字节码类型
        self.unknown_types_stats = {}
    
    def decode_message_info(self, class_name: str, info_string: str, objects: List[str], java_file_path=None) -> Optional[MessageDefinition]:
        """
        解码Protobuf消息信息
        
        Args:
            class_name: 完整的Java类名
            info_string: newMessageInfo中的字节码字符串
            objects: newMessageInfo中的对象数组
            java_file_path: Java文件路径（用于提取字段标签）
            
        Returns:
            MessageDefinition对象 或 None（如果解码失败）
        """
        try:
            # 解码字节码字符串
            bytes_data = self._decode_info_string(info_string)
            if bytes_data is None:
                return None
            
            # 创建消息定义
            message_def = self._create_message_definition(class_name)
            
            # 提取字段标签（如果有Java文件路径）
            field_tags = None
            if java_file_path:
                field_tags = self.java_parser.extract_field_tags(java_file_path)
                if field_tags:
                    self.logger.info(f"    🏷️ 从Java源码提取到 {len(field_tags)} 个字段标签")
            
            # 解析字段信息
            self._parse_fields(message_def, bytes_data, objects, field_tags)
            
            return message_def
            
        except Exception as e:
            self.logger.error(f"❌ 解码消息信息失败: {e}")
            return None
    
    def _decode_info_string(self, info_string: str) -> Optional[List[int]]:
        """
        将Unicode转义序列解码为字节数组
        
        Args:
            info_string: 包含Unicode转义序列的字符串
            
        Returns:
            字节数组 或 None（如果解码失败）
        """
        try:
            # 首先解码Unicode转义序列（如\u0000）但保持Unicode字符的原始值
            # 使用raw_unicode_escape来避免将Unicode字符编码为UTF-8
            decoded_string = info_string.encode('raw_unicode_escape').decode('raw_unicode_escape')
            return [ord(c) for c in decoded_string]
        except Exception as e:
            try:
                # 如果包含转义序列，手动处理
                import re
                def replace_unicode_escape(match):
                    return chr(int(match.group(1), 16))
                
                # 替换\uXXXX格式的转义序列
                decoded_string = re.sub(r'\\u([0-9a-fA-F]{4})', replace_unicode_escape, info_string)
                return [ord(c) for c in decoded_string]
            except Exception as e2:
                try:
                    # 最后的备用方法：直接使用ord值
                    return [ord(c) for c in info_string]
                except Exception as e3:
                    self.logger.error(f"❌ 解码字节码字符串失败: {e}, 方法2: {e2}, 方法3: {e3}")
                    return None
    
    def _create_message_definition(self, class_name: str) -> MessageDefinition:
        """
        根据类名创建消息定义的基础结构
        
        Args:
            class_name: 完整的Java类名
            
        Returns:
            初始化的MessageDefinition对象
        """
        # 分离包名和消息名
        parts = class_name.split('.')
        package_name = '.'.join(parts[:-1])
        message_name = parts[-1]
        
        return MessageDefinition(
            name=message_name,
            package_name=package_name,
            full_name=class_name
        )
    
    def _parse_fields(self, message_def: MessageDefinition, bytes_data: List[int], objects: List[str], field_tags: Optional[dict] = None) -> None:
        """
        解析字段信息的主调度方法
        
        Args:
            message_def: 消息定义对象
            bytes_data: 解码后的字节数组
            objects: 对象数组
            field_tags: 字段标签映射 {field_name: tag}
        """
        try:
            # 检查是否包含oneof字段（通过查找'<'字符，ord=60）
            oneof_positions = [i for i, byte_val in enumerate(bytes_data) if byte_val == 60]
            
            if oneof_positions:
                self._parse_oneof_fields(message_def, bytes_data, objects, oneof_positions)
            else:
                self._parse_regular_fields(message_def, bytes_data, objects, field_tags)
                
        except Exception as e:
            self.logger.error(f"❌ 解析字段失败: {e}")
    
    def _parse_regular_fields(self, message_def: MessageDefinition, bytes_data: List[int], objects: List[str], field_tags: Optional[dict] = None) -> None:
        """
        解析常规字段（非oneof字段）
        
        Args:
            message_def: 消息定义对象
            bytes_data: 字节码数据
            objects: 对象数组
            field_tags: 字段标签映射 {field_name: tag}
        """
        # 跳过前10个字节的元数据
        field_start = 10
        object_index = 0
        
        self.logger.info(f"    📊 开始解析字段，字节码长度: {len(bytes_data)}, objects数组长度: {len(objects)}")
        self.logger.info(f"    📊 完整字节码数据: {[f'{b:02x}' for b in bytes_data]}")
        self.logger.info(f"    📊 Objects数组: {objects}")
        
        # 如果有字段标签，优先使用Java源码信息
        if field_tags:
            self.logger.info(f"    🏷️ 使用Java源码字段标签: {field_tags}")
            self._parse_fields_with_java_tags(message_def, bytes_data, objects, field_tags)
        else:
            # 回退到字节码解析
            self.logger.info(f"    🔍 回退到字节码解析")
            self._parse_fields_from_bytecode(message_def, bytes_data, objects, field_start)
        
        self.logger.info(f"    📊 字段解析完成，共解析 {len(message_def.fields)} 个字段")
    
    def _parse_fields_with_java_tags(self, message_def: MessageDefinition, bytes_data: List[int], objects: List[str], field_tags: dict) -> None:
        """
        使用Java源码提取的字段标签解析字段
        
        Args:
            message_def: 消息定义对象
            bytes_data: 字节码数据
            objects: 对象数组
            field_tags: Java源码提取的字段标签映射
        """
        for field_name_raw, field_tag in field_tags.items():
            # 清理字段名
            field_name = self._clean_field_name(field_name_raw)
            
            # 从Java源码获取字段类型
            # 首先尝试作为枚举类型获取
            java_type = self._get_real_field_type_from_source(field_name_raw, 'enum')
            if not java_type:
                # 如果枚举类型获取失败，再尝试作为消息类型获取
                java_type = self._get_real_field_type_from_source(field_name_raw, 'message')
            if java_type:
                # 使用Java源码类型，直接处理原始Java类型
                if java_type.startswith('Internal.ProtobufList<') and java_type.endswith('>'):
                    # Internal.ProtobufList<Contact> -> Contact (repeated)
                    element_type = java_type[len('Internal.ProtobufList<'):-1]
                    field_type_name = self._convert_java_to_proto_type(element_type)
                    rule = 'repeated'
                elif java_type.startswith('MapFieldLite<') and java_type.endswith('>'):
                    # MapFieldLite<String, Contact> -> map<string, Contact>
                    field_type_name = self._convert_java_to_proto_type(java_type)
                    rule = 'optional'
                elif java_type == 'Internal.IntList':
                    # Internal.IntList -> 需要从setter方法获取真正的枚举类型
                    if self.java_source_analyzer:
                        enum_type = self.java_source_analyzer._get_enum_type_from_list_setter(field_name_raw.rstrip('_'))
                        if enum_type:
                            # 获取到枚举类型，转换为简单类名
                            field_type_name = self._convert_java_to_proto_type(enum_type)
                            rule = 'repeated'
                        else:
                            # 如果获取不到，回退到默认处理
                            field_type_name = 'int32'
                            rule = 'repeated'
                    else:
                        field_type_name = 'int32'
                        rule = 'repeated'
                else:
                    # 普通类型 - 但需要检查是否为枚举类型
                    if java_type in ['int', 'long', 'short', 'byte'] and self.java_source_analyzer:
                        # 对于基础整数类型，检查是否有对应的枚举setter方法
                        enum_type = self.java_source_analyzer._get_type_from_setter(field_name_raw.rstrip('_'))
                        if enum_type:
                            # 找到枚举setter，使用枚举类型
                            field_type_name = self._convert_java_to_proto_type(enum_type)
                            rule = 'optional'
                        else:
                            # 没有枚举setter，使用基础类型
                            field_type_name = self._convert_java_to_proto_type(java_type)
                            rule = 'optional'
                    else:
                        # 非基础整数类型，正常处理
                        field_type_name = self._convert_java_to_proto_type(java_type)
                        # 判断是否为repeated类型
                        if (java_type.startswith('Internal.ProtobufList<') or 
                            java_type.startswith('List<') or
                            java_type.startswith('ArrayList<')):
                            rule = 'repeated'
                        else:
                            rule = 'optional'
                
                self.logger.info(f"    🔍 从Java源码获取类型: {field_name_raw} -> {java_type} -> {field_type_name} (rule: {rule})")
            else:
                # 使用默认类型
                field_type_name = 'string'
                rule = 'optional'
                self.logger.info(f"    🔍 使用默认类型: {field_name_raw} -> {field_type_name}")
            
            # 记录字段信息
            self.logger.info(f"    📝 字段信息: name={field_name}, type={field_type_name}, tag={field_tag}")
            
            # 特殊情况处理：根据字段名修正类型
            field_type_name = self._refine_field_type(field_name, field_type_name, 0)  # 使用0作为占位符
            
            # 确定字段规则（基于Java类型判断是否为repeated）
            # 已经在上面确定了rule，这里不需要重复处理
            
            # 创建字段定义
            field_def = FieldDefinition(
                name=field_name,
                type_name=field_type_name,
                tag=field_tag,
                rule=rule
            )
            
            message_def.fields.append(field_def)
            self.logger.info(f"    ✅ 添加字段: {field_name} = {field_tag} ({rule} {field_type_name})")
    
    def _determine_field_rule(self, field_type_byte: int, field_type_name: str = None, java_type: str = None) -> str:
        """
        根据字节码、字段类型和Java类型确定字段规则
        
        Args:
            field_type_byte: 字段类型字节
            field_type_name: 字段类型名（可选）
            java_type: Java源码中的类型（可选）
            
        Returns:
            字段规则：'optional' 或 'repeated'
        """
        # map类型永远不使用repeated规则，因为map本身就表示键值对集合
        if field_type_name and field_type_name.startswith('map<'):
            return 'optional'
        
        # 检查Java源码类型是否为集合类型
        if java_type:
            if (java_type.startswith('Internal.ProtobufList<') or 
                java_type.startswith('List<') or
                java_type.startswith('ArrayList<') or
                java_type.startswith('java.util.List<')):
                return 'repeated'
        
        # 检查字段类型名是否包含repeated标识
        if field_type_name and field_type_name.startswith('repeated_'):
            return 'repeated'
        
        # repeated类型的字节码
        repeated_types = {27, 39, 44, 538}  # repeated_message, repeated_int32, repeated_enum, repeated_string
        return 'repeated' if field_type_byte in repeated_types else 'optional'
    
    def _infer_field_type_from_bytecode(self, field_name_raw: str, field_type: str) -> str:
        """
        从Java源码推断字段类型
        
        Args:
            field_name_raw: 原始字段名（带下划线）
            field_type: 字节码推断的字段类型
            
        Returns:
            推断的字段类型
        """
        # 首先尝试从Java源码获取真实类型
        real_type = self._get_real_field_type_from_source(field_name_raw)
        if real_type:
            self.logger.info(f"    🔍 从Java源码获取类型: {field_name_raw} -> {real_type} -> {self._convert_java_to_proto_type(real_type)}")
            return self._convert_java_to_proto_type(real_type)
        
        # 如果源码分析失败，使用字节码类型
        self.logger.info(f"    🔍 使用字节码类型: {field_name_raw} -> {field_type}")
        return field_type
    
    def _convert_java_to_proto_type(self, java_type: str) -> str:
        """
        将Java类型转换为Protobuf类型
        
        Args:
            java_type: Java类型字符串
            
        Returns:
            转换后的Protobuf类型
        """
        if not java_type:
            return 'string'
        
        # 处理Internal.ProtobufList<T>类型
        if java_type.startswith('Internal.ProtobufList<') and java_type.endswith('>'):
            element_type = java_type[len('Internal.ProtobufList<'):-1]
            # 递归处理元素类型
            return self._convert_java_to_proto_type(element_type)
        
        # 处理MapFieldLite<K, V>类型，返回map<k, v>格式
        if java_type.startswith('MapFieldLite<') and java_type.endswith('>'):
            inner_types = java_type[len('MapFieldLite<'):-1]
            # 解析键值类型
            parts = self._parse_generic_types(inner_types)
            if len(parts) == 2:
                key_type = self._convert_java_to_proto_type(parts[0].strip())
                value_type = self._convert_java_to_proto_type(parts[1].strip())
                return f"map<{key_type}, {value_type}>"
        
        # 处理List<T>类型
        if java_type.startswith('List<') and java_type.endswith('>'):
            element_type = java_type[len('List<'):-1]
            return self._convert_java_to_proto_type(element_type)
        
        # 处理Internal.IntList类型（通常对应枚举列表）
        if java_type == 'Internal.IntList':
            # 这种情况需要从上下文获取真正的枚举类型
            # 返回特殊标记，让调用方进行进一步处理
            return 'Internal.IntList'
        
        # 基础类型映射
        basic_types = {
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
            'Float': 'float',
            'Double': 'double',
            'Boolean': 'bool',
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
        }
        
        # 检查是否为基础类型
        if java_type in basic_types:
            return basic_types[java_type]
        
        # 如果是完整的类名，提取简单类名
        if '.' in java_type:
            simple_name = java_type.split('.')[-1]
            return simple_name
        
        # 默认返回原类型名
        return java_type
    
    def _parse_fields_from_bytecode(self, message_def: MessageDefinition, bytes_data: List[int], objects: List[str], field_start: int) -> None:
        """
        从字节码解析字段（原有的解析逻辑）
        
        Args:
            message_def: 消息定义对象
            bytes_data: 字节码数据
            objects: 对象数组
            field_start: 字段数据开始位置
        """
        object_index = 0
        
        # 每次处理2个字节：[字段标签, 字段类型]
        for i in range(field_start, len(bytes_data) - 1, 2):
            field_tag = bytes_data[i]
            field_type_byte = bytes_data[i + 1]
            
            self.logger.info(f"    🔍 处理字段 #{(i-field_start)//2 + 1}: tag={field_tag}, type_byte={field_type_byte} (0x{field_type_byte:02x})")
            
            # 查找类型映射，对未知类型进行智能处理
            if field_type_byte not in self.type_mapping:
                # 统计未知类型
                self.unknown_types_stats[field_type_byte] = self.unknown_types_stats.get(field_type_byte, 0) + 1
                
                # 记录未知类型，但不跳过字段
                self.logger.warning(f"    ⚠️  发现未知字节码类型: {field_type_byte} (0x{field_type_byte:02x})")
                field_type = self._analyze_unknown_type_with_source_priority(field_type_byte, objects, object_index)
                self.logger.info(f"    🔍 推断未知类型: {field_type_byte} -> {field_type}")
            else:
                field_type = self.type_mapping[field_type_byte]
                self.logger.info(f"    ✅ 已知类型: {field_type_byte} -> {field_type}")
            
            # 从对象数组获取字段信息
            field_info = self._extract_field_info(objects, object_index, field_type)
            if not field_info:
                self.logger.warning(f"    ⚠️  无法获取字段信息，跳过字段 tag={field_tag}")
                continue
                
            field_name, field_type_name, new_object_index = field_info
            object_index = new_object_index
            
            self.logger.info(f"    📝 字段信息: name={field_name}, type={field_type_name}, tag={field_tag}")
            
            # 特殊情况处理：根据字段名修正类型
            field_type_name = self._refine_field_type(field_name, field_type_name, field_type_byte)
            
            # 确定字段规则
            rule = self._determine_field_rule(field_type_byte, field_type_name, None)
            
            # 创建字段定义
            field_def = FieldDefinition(
                name=field_name,
                type_name=field_type_name,
                tag=field_tag,
                rule=rule
            )
            
            message_def.fields.append(field_def)
            self.logger.info(f"    ✅ 添加字段: {field_name} = {field_tag} ({field_type_name})")
    
    def _extract_field_info(self, objects: List[str], object_index: int, field_type: str) -> Optional[tuple]:
        """
        从对象数组中提取字段信息
        
        混合策略：优先使用objects数组中的显式引用，对于枚举类型进行智能推断
        
        Args:
            objects: 对象数组
            object_index: 当前对象索引
            field_type: 字段类型
            
        Returns:
            (字段名, 类型名, 新的对象索引) 或 None
        """
        if object_index >= len(objects):
            return None
        
        # 获取字段名
        field_name_raw = objects[object_index]
        
        # 跳过内部状态字段（protobuf内部使用的字段，不是实际的proto字段）
        if self._is_internal_field(field_name_raw):
            self.logger.info(f"    ⏭️ 跳过内部字段: {field_name_raw}")
            object_index += 1
            # 递归调用获取下一个字段
            return self._extract_field_info(objects, object_index, field_type)
        
        field_name = self._to_snake_case(field_name_raw.rstrip('_'))
        object_index += 1
        
        # 确定字段类型名
        field_type_name = field_type  # 默认使用基础类型
        
        # 处理repeated类型：repeated_message -> message，但保留repeated信息
        if field_type.startswith('repeated_'):
            base_field_type = field_type[9:]  # 移除 'repeated_' 前缀
            field_type_name = base_field_type
        
        # 对于消息类型、枚举类型和map类型，检查objects数组中是否有具体的类型引用
        if field_type_name in ['message', 'enum', 'map'] or field_type in ['repeated_message', 'repeated_enum']:
            if object_index < len(objects):
                next_obj = objects[object_index]
                if self._is_type_reference(next_obj):
                    # 直接使用objects数组中的类型引用，这是最准确的信息源
                    if field_type == 'map':
                        # 对于map类型，从MapEntry引用中推断键值类型
                        field_type_name = self._extract_map_type_from_entry(next_obj, field_name_raw)
                        self.logger.info(f"    🗺️ 从MapEntry获取map类型: {field_name} -> {field_type_name}")
                    else:
                        field_type_name = self._clean_type_reference(next_obj)
                        self.logger.info(f"    🔗 从objects数组获取类型: {field_name} -> {field_type_name}")
                    object_index += 1
                else:
                    # 没有显式引用，优先从Java源码中获取真实类型
                    real_type = self._get_real_field_type_from_source(field_name_raw, field_type_name)
                    if real_type:
                        field_type_name = real_type
                        self.logger.info(f"    🔍 源码获取类型: {field_name} -> {field_type_name}")
                    else:
                        # 如果源码分析失败，才进行智能推断
                        if field_type_name == 'enum':
                            field_type_name = self._infer_enum_type_from_field_name(field_name_raw)
                            self.logger.info(f"    🔍 推断枚举类型: {field_name} -> {field_type_name}")
                        elif field_type_name == 'message':
                            field_type_name = self._infer_message_type_from_field_name(field_name_raw)
                            self.logger.info(f"    🔍 推断消息类型: {field_name} -> {field_type_name}")
                        elif field_type == 'map':
                            field_type_name = self._infer_map_type_from_source(field_name_raw)
                            self.logger.info(f"    🔍 推断map类型: {field_name} -> {field_type_name}")
            else:
                # objects数组已结束，优先从Java源码中获取真实类型
                real_type = self._get_real_field_type_from_source(field_name_raw, field_type_name)
                if real_type:
                    field_type_name = real_type
                    self.logger.info(f"    🔍 源码获取类型: {field_name} -> {field_type_name}")
                else:
                    # 如果源码分析失败，才进行智能推断
                    if field_type_name == 'enum':
                        field_type_name = self._infer_enum_type_from_field_name(field_name_raw)
                        self.logger.info(f"    🔍 推断枚举类型: {field_name} -> {field_type_name}")
                    elif field_type_name == 'message':
                        field_type_name = self._infer_message_type_from_field_name(field_name_raw)
                        self.logger.info(f"    🔍 推断消息类型: {field_name} -> {field_type_name}")
                    elif field_type == 'map':
                        field_type_name = self._infer_map_type_from_source(field_name_raw)
                        self.logger.info(f"    🔍 推断map类型: {field_name} -> {field_type_name}")
        
        return field_name, field_type_name, object_index

    def _get_real_field_type_from_source(self, field_name_raw: str, expected_type: str = 'message') -> Optional[str]:
        """
        从Java源码中获取字段的真实Java类型（原始类型，不转换）
        
        Args:
            field_name_raw: 原始字段名（如 contacts_）
            expected_type: 期望的基础类型（message、enum 或 map）
            
        Returns:
            原始的Java类型名，如果无法获取则返回None
        """
        if not self.java_source_analyzer:
            return None
            
        try:
            # 调用Java源码分析器获取真实Java类型（原始类型）
            real_type = self.java_source_analyzer.get_field_type(field_name_raw, expected_type)
            if real_type:
                self.logger.info(f"    🔍 源码分析成功: {field_name_raw} -> {real_type}")
                return real_type  # 返回原始Java类型
            return None
        except Exception as e:
            self.logger.warning(f"    ⚠️  源码分析失败: {e}")
            return None

    def _infer_message_type_from_field_name(self, field_name_raw: str) -> str:
        """
        根据字段名智能推断消息类型名（通用算法）
        
        Args:
            field_name_raw: 原始字段名（如 businessProfile_）
            
        Returns:
            推断出的消息类型名
        """
        # 优先从Java源码中获取真实类型
        if self.java_source_analyzer:
            real_type = self.java_source_analyzer.get_field_type(field_name_raw, 'message')
            if real_type and real_type not in ['string', 'int32', 'int64', 'bool', 'float', 'double', 'bytes']:
                return real_type
        
        # 移除末尾的下划线
        clean_name = field_name_raw.rstrip('_')
        
        if not clean_name:
            return 'UnknownMessage'
        
        # 检查是否为基础字段类型
        if self._is_likely_basic_field(clean_name):
            # 对于基础字段，返回相应的protobuf基础类型
            return self._get_basic_field_proto_type(clean_name)
        
        # 将camelCase转换为PascalCase
        type_name = self._camel_to_pascal_case(clean_name)
        
        # 通用推断规则（无硬编码）
        # 1. 处理复数形式
        if clean_name.lower().endswith('s') and len(clean_name) > 2:
            # contacts -> Contact, phones -> Phone
            singular = clean_name[:-1]
            return self._camel_to_pascal_case(singular)
        
        # 2. 处理常见后缀
        elif clean_name.lower().endswith('profile'):
            # businessProfile -> BusinessProfile，保持原样
            return type_name
        elif clean_name.lower().endswith('info'):
            # spamInfo -> SpamInfo，保持原样
            return type_name
        elif clean_name.lower().endswith('data'):
            # userData -> UserData，保持原样
            return type_name
        elif clean_name.lower().endswith('config'):
            # systemConfig -> SystemConfig，保持原样
            return type_name
        
        # 3. 默认处理
        else:
            return type_name

    def _is_likely_basic_field(self, field_name: str) -> bool:
        """
        检查字段名是否可能是基础类型字段
        
        Args:
            field_name: 清理后的字段名
            
        Returns:
            是否可能是基础类型
        """
        # 常见的基础字段模式
        basic_patterns = [
            'tags',       # 标签数组
            'ids',        # ID数组
            'values',     # 值数组
            'names',      # 名称数组
            'urls',       # URL数组
            'emails',     # 邮箱数组
            'phones',     # 电话号码数组（如果是字符串）
            'addresses',  # 地址数组（如果是字符串）
            'keywords',   # 关键词数组
            'categories', # 分类数组
            'labels',     # 标签数组
        ]
        
        field_lower = field_name.lower()
        
        # 检查是否匹配基础模式
        for pattern in basic_patterns:
            if field_lower == pattern or field_lower.endswith(pattern):
                return True
        
        return False

    def _get_basic_field_proto_type(self, field_name: str) -> str:
        """
        获取基础字段的protobuf类型
        
        Args:
            field_name: 字段名
            
        Returns:
            protobuf基础类型
        """
        field_lower = field_name.lower()
        
        # 根据字段名推断基础类型
        if field_lower in ['tags', 'names', 'urls', 'emails', 'keywords', 'categories', 'labels']:
            return 'string'  # repeated string
        elif field_lower in ['ids', 'values'] and 'id' in field_lower:
            return 'int64'   # repeated int64
        elif field_lower in ['counts', 'numbers', 'amounts']:
            return 'int32'   # repeated int32
        else:
            return 'string'  # 默认为string

    def _camel_to_pascal_case(self, camel_str: str) -> str:
        """
        将camelCase转换为PascalCase
        
        Args:
            camel_str: camelCase字符串
            
        Returns:
            PascalCase字符串
        """
        if not camel_str:
            return camel_str
        return camel_str[0].upper() + camel_str[1:]
    
    def _infer_enum_type_from_field_name(self, field_name_raw: str) -> str:
        """
        根据字段名智能推断枚举类型名（通用算法）
        
        Args:
            field_name_raw: 原始字段名（如 gender_）
            
        Returns:
            推断出的枚举类型名
        """
        # 移除末尾的下划线
        clean_name = field_name_raw.rstrip('_')
        
        if not clean_name:
            return 'UnknownEnum'
        
        # 将camelCase转换为PascalCase
        type_name = self._camel_to_pascal_case(clean_name)
        
        # 通用推断规则（无硬编码）
        # 1. 处理复数形式
        if clean_name.lower().endswith('s') and len(clean_name) > 2:
            # badges -> Badge, access -> Acces (但应该修正为Access)
            singular = clean_name[:-1]
            result = self._camel_to_pascal_case(singular)
            # 特殊处理：如果去掉s后以ss结尾，说明原词应该保留s
            if singular.lower().endswith('s'):
                result = result + 's'
            return result
        
        # 2. 处理常见后缀
        elif clean_name.lower().endswith('type'):
            # messageType -> MessageType，保持原样
            return type_name
        elif clean_name.lower().endswith('status'):
            # spamStatus -> SpamStatus，保持原样
            return type_name
        elif clean_name.lower().endswith('mode'):
            # displayMode -> DisplayMode，保持原样
            return type_name
        
        # 3. 默认处理
        else:
            return type_name
    
    def _is_type_reference(self, obj: str) -> bool:
        """
        判断对象是否是类型引用
        
        Args:
            obj: 对象字符串
            
        Returns:
            是否为类型引用
        """
        return (obj.endswith('.class') or 
                '.' in obj and not obj.endswith('_') or
                (not obj.endswith('_') and obj[0].isupper()))
    
    def _clean_type_reference(self, obj: str) -> str:
        """
        清理类型引用字符串
        
        Args:
            obj: 原始类型引用
            
        Returns:
            清理后的类型名
        """
        if obj.endswith('.class'):
            return obj[:-6]
        return obj
    
    def _refine_field_type(self, field_name: str, field_type_name: str, field_type_byte: int) -> str:
        """
        根据字段名和上下文信息修正字段类型
        
        Args:
            field_name: 字段名
            field_type_name: 当前推断的类型名
            field_type_byte: 原始字节码
            
        Returns:
            修正后的类型名
        """
        # 只进行必要的基础类型修正，不做复杂推断
        return field_type_name
    
    def _parse_oneof_fields(self, message_def: MessageDefinition, bytes_data: List[int], 
                           objects: List[str], oneof_positions: List[int]) -> None:
        """
        解析oneof字段
        
        Args:
            message_def: 消息定义对象
            bytes_data: 字节数组
            objects: 对象数组
            oneof_positions: oneof标记位置列表
        """
        if len(objects) < 2:
            return
        
        # 提取oneof信息
        oneof_field_name = objects[0]  # 如 "result_"
        oneof_name = self._to_snake_case(oneof_field_name.rstrip('_'))
        
        # 创建oneof定义
        oneof_def = OneofDefinition(name=oneof_name)
        
        # 解析oneof中的字段
        object_index = 2  # 从第3个对象开始
        
        for pos in oneof_positions:
            if pos > 0:
                field_tag = bytes_data[pos - 1]
                
                if object_index < len(objects):
                    field_type_name = objects[object_index]
                    field_name = self._to_snake_case(field_type_name)
                    
                    field_def = FieldDefinition(
                        name=field_name,
                        type_name=field_type_name,
                        tag=field_tag,
                        rule='optional'
                    )
                    
                    oneof_def.fields.append(field_def)
                    object_index += 1
        
        if oneof_def.fields:
            message_def.oneofs.append(oneof_def)
    
    def _extract_map_type_from_entry(self, entry_ref: str, field_name_raw: str) -> str:
        """
        从MapEntry引用中提取map的键值类型
        
        Args:
            entry_ref: MapEntry引用，如 "qux.f107553a"
            field_name_raw: 原始字段名，用于推断类型
            
        Returns:
            map类型字符串，如 "map<string, Contact>"
        """
        try:
            # 优先从Java源码中获取真实的map类型
            if self.java_source_analyzer:
                real_type = self.java_source_analyzer.get_field_type(field_name_raw, 'map')
                if real_type and real_type.startswith('map<'):
                    return real_type
            
            # 如果无法从源码获取，进行智能推断
            return self._infer_map_type_from_source(field_name_raw)
            
        except Exception as e:
            self.logger.warning(f"    ⚠️  从MapEntry提取类型失败: {e}")
            return self._infer_map_type_from_source(field_name_raw)
    
    def _infer_map_type_from_source(self, field_name_raw: str) -> str:
        """
        从字段名推断map类型
        
        Args:
            field_name_raw: 原始字段名（如 contacts_）
            
        Returns:
            推断的map类型字符串
        """
        # 移除末尾的下划线
        clean_name = field_name_raw.rstrip('_')
        
        # 基于字段名的通用推断规则
        if clean_name.lower().endswith('map') or clean_name.lower().endswith('mapping'):
            # xxxMap -> map<string, Xxx>
            base_name = clean_name[:-3] if clean_name.lower().endswith('map') else clean_name[:-7]
            value_type = self._camel_to_pascal_case(base_name) if base_name else 'string'
            return f"map<string, {value_type}>"
        elif clean_name.lower() in ['contacts', 'users', 'profiles']:
            # 常见的复数形式字段，推断为实体映射
            singular = clean_name[:-1] if clean_name.endswith('s') else clean_name
            value_type = self._camel_to_pascal_case(singular)
            return f"map<string, {value_type}>"
        elif clean_name.lower().endswith('tags'):
            # xxxTags -> map<string, string> (标签通常是字符串到字符串的映射)
            return "map<string, string>"
        elif clean_name.lower().endswith('ids'):
            # xxxIds -> map<string, string> (ID映射)
            return "map<string, string>"
        else:
            # 默认推断：字段名作为值类型
            value_type = self._camel_to_pascal_case(clean_name)
            return f"map<string, {value_type}>"

    def _analyze_unknown_type_with_source_priority(self, field_type_byte: int, objects: List[str], object_index: int) -> str:
        """
        分析未知字节码类型，进行智能推断，优先使用Java源码分析结果
        
        Args:
            field_type_byte: 未知的字节码类型
            objects: 对象数组
            object_index: 当前对象索引
            
        Returns:
            推断的字段类型
        """
        # 分析字节码的结构
        wire_type = field_type_byte & 7  # 低3位是wire type
        field_number = field_type_byte >> 3  # 高位是field number
        
        self.logger.debug(f"    🔬 字节码分析: byte={field_type_byte}, wire_type={wire_type}, field_number={field_number}")
        
        # 第一步：尝试从Java源码获取真实类型
        java_type = None
        if object_index < len(objects) and self.java_source_analyzer:
            field_name_raw = objects[object_index]
            try:
                java_type = self._get_java_field_type_for_unknown(field_name_raw)
                if java_type:
                    self.logger.info(f"    ✅ Java源码分析: {field_name_raw} -> {java_type}")
            except Exception as e:
                self.logger.debug(f"    ⚠️  Java源码分析失败: {e}")
        
        # 第二步：基于wire type进行字节码推断
        bytecode_type = self._analyze_unknown_type_by_wire_type(wire_type, objects, object_index, field_type_byte)
        
        # 第三步：交叉校验和最终决策
        final_type = self._cross_validate_types(java_type, bytecode_type, wire_type, field_type_byte)
        
        if java_type and java_type != final_type:
            self.logger.info(f"    🔄 类型校验: Java({java_type}) vs 字节码({bytecode_type}) -> 最终({final_type})")
        
        return final_type
    
    def _get_java_field_type_for_unknown(self, field_name_raw: str) -> Optional[str]:
        """
        从Java源码中获取未知字段的真实类型
        
        Args:
            field_name_raw: 原始字段名（如 latitude_）
            
        Returns:
            Java字段的proto类型，如果无法获取则返回None
        """
        if not self.java_source_analyzer:
            return None
            
        try:
            # 获取Java字段的原始类型
            java_raw_type = self.java_source_analyzer.get_raw_field_type(field_name_raw)
            if not java_raw_type:
                return None
            
            # 将Java类型转换为proto类型
            proto_type = self._java_type_to_proto_type(java_raw_type)
            return proto_type
            
        except Exception as e:
            self.logger.debug(f"    ⚠️  获取Java字段类型失败: {e}")
            return None
    
    def _java_type_to_proto_type(self, java_type: str) -> str:
        """
        将Java类型转换为proto类型
        
        Args:
            java_type: Java类型字符串
            
        Returns:
            对应的proto类型
        """
        # 使用内部的类型转换方法
        return self._convert_java_to_proto_type(java_type)
    
    def _analyze_unknown_type_by_wire_type(self, wire_type: int, objects: List[str], object_index: int, field_type_byte: int) -> str:
        """
        基于wire type分析未知字节码类型
        
        Args:
            wire_type: wire type (0-5)
            objects: 对象数组
            object_index: 当前对象索引
            field_type_byte: 原始字节码类型
            
        Returns:
            推断的字段类型
        """
        if wire_type == 0:
            # VARINT: int32, int64, uint32, uint64, sint32, sint64, bool, enum
            return self._infer_varint_type(objects, object_index)
        elif wire_type == 1:
            # 64-BIT: fixed64, sfixed64, double
            return 'double'  # 默认为double（比int64更常见）
        elif wire_type == 2:
            # LENGTH_DELIMITED: string, bytes, embedded messages, packed repeated fields
            return self._infer_length_delimited_type(objects, object_index, field_type_byte)
        elif wire_type == 5:
            # 32-BIT: fixed32, sfixed32, float
            return 'float'  # 默认为float
        else:
            # 其他未知wire type
            self.logger.warning(f"    ⚠️  未知wire type: {wire_type}")
            return self._fallback_type_inference(objects, object_index)
    
    def _cross_validate_types(self, java_type: Optional[str], bytecode_type: str, wire_type: int, field_type_byte: int) -> str:
        """
        交叉校验Java类型和字节码类型，返回最终类型
        
        Args:
            java_type: Java源码分析得到的类型
            bytecode_type: 字节码分析得到的类型
            wire_type: wire type
            field_type_byte: 原始字节码类型
            
        Returns:
            最终确定的字段类型
        """
        # 如果没有Java类型信息，使用字节码推断
        if not java_type:
            return bytecode_type
        
        # 如果Java类型和字节码类型一致，直接返回
        if java_type == bytecode_type:
            return java_type
        
        # 类型不一致时的校验逻辑
        if wire_type == 0:  # VARINT
            # 对于VARINT类型，Java源码更准确
            if java_type in ['bool', 'int32', 'int64', 'uint32', 'uint64', 'sint32', 'sint64']:
                return java_type
            elif java_type == 'message':  # 可能是enum
                return 'enum' if bytecode_type == 'enum' else java_type
        elif wire_type == 1:  # 64-BIT
            # 对于64位类型，Java源码更准确
            if java_type in ['double', 'fixed64', 'sfixed64']:
                return java_type
        elif wire_type == 2:  # LENGTH_DELIMITED
            # 对于长度分隔类型，Java源码更准确
            if java_type in ['string', 'bytes', 'message', 'map']:
                return java_type
        elif wire_type == 5:  # 32-BIT
            # 对于32位类型，Java源码更准确
            if java_type in ['float', 'fixed32', 'sfixed32']:
                return java_type
        
        # 默认优先使用Java类型
        self.logger.info(f"    🔧 类型冲突，优先使用Java类型: {java_type} (字节码推断: {bytecode_type})")
        return java_type

    def _infer_varint_type(self, objects: List[str], object_index: int) -> str:
        """推断VARINT类型字段"""
        # 检查objects数组中是否有类型提示
        if object_index < len(objects):
            field_name = objects[object_index].rstrip('_')
            
            # 基于字段名推断
            if any(keyword in field_name.lower() for keyword in ['type', 'status', 'mode', 'enum']):
                return 'enum'
            elif field_name.lower() in ['count', 'size', 'length', 'number']:
                return 'int32'
            elif field_name.lower().endswith('_id') or field_name.lower() == 'id':
                return 'int64'
            elif field_name.lower() in ['enabled', 'visible', 'active', 'valid']:
                return 'bool'
        
        return 'int32'  # 默认为int32
    
    def _infer_length_delimited_type(self, objects: List[str], object_index: int, field_type_byte: int) -> str:
        """推断LENGTH_DELIMITED类型字段"""
        # 检查是否可能是map类型（基于已知的map类型字节码模式）
        if field_type_byte == 50 or field_type_byte in range(48, 60):  # 扩展map类型的可能范围
            return 'map'
        
        # 检查objects数组中是否有类型提示
        if object_index < len(objects):
            field_name = objects[object_index].rstrip('_')
            
            # 基于字段名推断
            if field_name.lower().endswith('map') or field_name.lower().endswith('mapping'):
                return 'map'
            elif field_name.lower() in ['name', 'title', 'description', 'text', 'url', 'email']:
                return 'string'
            elif field_name.lower().endswith('data') or field_name.lower().endswith('bytes'):
                return 'bytes'
            elif field_name.lower().endswith('s') and len(field_name) > 2:
                # 复数形式，可能是repeated字段
                return 'message'  # repeated message
        
        return 'string'  # 默认为string
    
    def _fallback_type_inference(self, objects: List[str], object_index: int) -> str:
        """兜底类型推断"""
        if object_index < len(objects):
            field_name = objects[object_index].rstrip('_')
            
            # 基于字段名的通用推断
            if any(keyword in field_name.lower() for keyword in ['id', 'count', 'size', 'number']):
                return 'int32'
            elif any(keyword in field_name.lower() for keyword in ['name', 'title', 'text', 'url']):
                return 'string'
            elif field_name.lower().endswith('s'):
                return 'message'  # 可能是repeated字段
        
        return 'string'  # 最终兜底

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

    def _is_internal_field(self, field_name_raw: str) -> bool:
        """
        判断是否为protobuf内部字段（不是实际的proto字段）
        
        Args:
            field_name_raw: 原始字段名
            
        Returns:
            True如果是内部字段，False如果是实际字段
        """
        # 移除末尾的下划线进行判断
        clean_name = field_name_raw.rstrip('_').lower()
        
        # protobuf内部字段模式
        internal_patterns = [
            'bitfield0',    # bitField0_ - 用于标记optional字段的位掩码
            'bitfield1',    # bitField1_ - 多个位掩码字段
            'bitfield2',    # bitField2_
            'bitfield',     # 通用位字段模式
            'memoizedhashcode',  # memoizedHashCode_ - 缓存的hash值
            'memoizedsize',      # memoizedSize_ - 缓存的大小
            'unknownfields'      # unknownFields_ - 未知字段存储
        ]
        
        # 检查是否匹配内部字段模式
        for pattern in internal_patterns:
            if clean_name == pattern or clean_name.startswith(pattern):
                return True
        
        return False

    def _clean_field_name(self, field_name_raw: str) -> str:
        """
        清理字段名并转换为snake_case格式
        
        Args:
            field_name_raw: 原始字段名
            
        Returns:
            清理后的字段名
        """
        return self._to_snake_case(field_name_raw.rstrip('_'))

    def _parse_generic_types(self, type_params: str) -> List[str]:
        """
        解析泛型类型参数
        
        Args:
            type_params: 泛型参数字符串，如 "String, Contact" 或 "Map<String, Object>, List<Item>"
            
        Returns:
            解析后的类型列表
        """
        if not type_params:
            return []
        
        result = []
        current = ""
        bracket_count = 0
        
        for char in type_params:
            if char == '<':
                bracket_count += 1
                current += char
            elif char == '>':
                bracket_count -= 1
                current += char
            elif char == ',' and bracket_count == 0:
                # 只有在最外层的逗号才作为分隔符
                result.append(current.strip())
                current = ""
            else:
                current += char
        
        if current.strip():
            result.append(current.strip())
        
        return result 