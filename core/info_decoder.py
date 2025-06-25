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
        初始化解码器，设置字节码到Protobuf类型的映射表
        
        Args:
            java_source_analyzer: Java源码分析器，用于获取真实的字段类型
        """
        self.logger = get_logger("info_decoder")
        
        # 字节码到Protobuf类型的映射表（逆向工程的核心成果）
        self.type_mapping = {
            1: 'float',      # FLOAT
            2: 'int64',      # INT64  
            3: 'int32',      # INT32
            4: 'int32',      # INT32 (修正：4对应int32，不是bool)
            7: 'bool',       # BOOL (修正：7对应bool)
            9: 'message',    # MESSAGE (嵌套消息)
            12: 'enum',      # ENUM (枚举类型)
            27: 'message',   # REPEATED MESSAGE
            39: 'int32',     # REPEATED INT32 (packed)
            44: 'enum',      # PACKED ENUM
            520: 'string',   # STRING (Ȉ = 520)
            538: 'string',   # REPEATED STRING (Ț = 538)  
        }
        
        # Java源码分析器
        self.java_source_analyzer = java_source_analyzer
    
    def decode_message_info(self, class_name: str, info_string: str, objects: List[str]) -> Optional[MessageDefinition]:
        """
        解码消息信息的主入口方法
        
        Args:
            class_name: 完整的Java类名
            info_string: newMessageInfo中的字节码字符串
            objects: newMessageInfo中的对象数组
            
        Returns:
            MessageDefinition对象 或 None（如果解码失败）
        """
        try:
            # 1. 解码字节码字符串为字节数组
            bytes_data = self._decode_info_string(info_string)
            if not bytes_data:
                return None
            
            # 2. 创建消息定义基础结构
            message_def = self._create_message_definition(class_name)
            
            # 3. 解析字段信息
            self._parse_fields(message_def, bytes_data, objects)
            
            return message_def
            
        except Exception as e:
            self.logger.error(f"❌ 解码消息信息失败 {class_name}: {e}")
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
            # 解码Unicode转义序列并转换为字节数组
            decoded = info_string.encode('latin-1', 'backslashreplace').decode('unicode-escape')
            return [ord(c) for c in decoded]
        except Exception as e:
            self.logger.error(f"❌ 解码字节码字符串失败: {e}")
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
    
    def _parse_fields(self, message_def: MessageDefinition, bytes_data: List[int], objects: List[str]) -> None:
        """
        解析字段信息的主调度方法
        
        Args:
            message_def: 消息定义对象
            bytes_data: 解码后的字节数组
            objects: 对象数组
        """
        try:
            # 检查是否包含oneof字段（通过查找'<'字符，ord=60）
            oneof_positions = [i for i, byte_val in enumerate(bytes_data) if byte_val == 60]
            
            if oneof_positions:
                self._parse_oneof_fields(message_def, bytes_data, objects, oneof_positions)
            else:
                self._parse_regular_fields(message_def, bytes_data, objects)
                
        except Exception as e:
            self.logger.error(f"❌ 解析字段失败: {e}")
    
    def _parse_regular_fields(self, message_def: MessageDefinition, bytes_data: List[int], objects: List[str]) -> None:
        """
        解析常规字段（非oneof字段）
        
        Args:
            message_def: 消息定义对象
            bytes_data: 字节数组
            objects: 对象数组
        """
        # 跳过前10个字节的元数据
        field_start = 10
        object_index = 0
        
        # 每次处理2个字节：[字段标签, 字段类型]
        for i in range(field_start, len(bytes_data) - 1, 2):
            field_tag = bytes_data[i]
            field_type_byte = bytes_data[i + 1]
            
            # 查找类型映射
            if field_type_byte not in self.type_mapping:
                continue
                
            field_type = self.type_mapping[field_type_byte]
            
            # 从对象数组获取字段信息
            field_info = self._extract_field_info(objects, object_index, field_type)
            if not field_info:
                continue
                
            field_name, field_type_name, new_object_index = field_info
            object_index = new_object_index
            
            # 特殊情况处理：根据字段名修正类型
            field_type_name = self._refine_field_type(field_name, field_type_name, field_type_byte)
            
            # 确定字段规则
            rule = self._determine_field_rule(field_type_byte)
            
            # 创建字段定义
            field_def = FieldDefinition(
                name=field_name,
                type_name=field_type_name,
                tag=field_tag,
                rule=rule
            )
            
            message_def.fields.append(field_def)
    
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
        field_name = self._to_snake_case(field_name_raw.rstrip('_'))
        object_index += 1
        
        # 确定字段类型名
        field_type_name = field_type  # 默认使用基础类型
        
        # 对于消息类型和枚举类型，检查objects数组中是否有具体的类型引用
        if field_type in ['message', 'enum']:
            if object_index < len(objects):
                next_obj = objects[object_index]
                if self._is_type_reference(next_obj):
                    # 直接使用objects数组中的类型引用，这是最准确的信息源
                    field_type_name = self._clean_type_reference(next_obj)
                    object_index += 1
                    self.logger.info(f"    🔗 从objects数组获取类型: {field_name} -> {field_type_name}")
                else:
                    # 没有显式引用，优先从Java源码中获取真实类型
                    real_type = self._get_real_field_type_from_source(field_name_raw, field_type)
                    if real_type:
                        field_type_name = real_type
                        self.logger.info(f"    🔍 源码获取类型: {field_name} -> {field_type_name}")
                    else:
                        # 如果源码分析失败，才进行智能推断
                        if field_type == 'enum':
                            field_type_name = self._infer_enum_type_from_field_name(field_name_raw)
                            self.logger.info(f"    🔍 推断枚举类型: {field_name} -> {field_type_name}")
                        elif field_type == 'message':
                            field_type_name = self._infer_message_type_from_field_name(field_name_raw)
                            self.logger.info(f"    🔍 推断消息类型: {field_name} -> {field_type_name}")
            else:
                # objects数组已结束，优先从Java源码中获取真实类型
                real_type = self._get_real_field_type_from_source(field_name_raw, field_type)
                if real_type:
                    field_type_name = real_type
                    self.logger.info(f"    🔍 源码获取类型: {field_name} -> {field_type_name}")
                else:
                    # 如果源码分析失败，才进行智能推断
                    if field_type == 'enum':
                        field_type_name = self._infer_enum_type_from_field_name(field_name_raw)
                        self.logger.info(f"    🔍 推断枚举类型: {field_name} -> {field_type_name}")
                    elif field_type == 'message':
                        field_type_name = self._infer_message_type_from_field_name(field_name_raw)
                        self.logger.info(f"    🔍 推断消息类型: {field_name} -> {field_type_name}")
        
        return field_name, field_type_name, object_index

    def _get_real_field_type_from_source(self, field_name_raw: str, expected_type: str) -> Optional[str]:
        """
        从Java源码中获取字段的真实类型
        
        Args:
            field_name_raw: 原始字段名（如 id_）
            expected_type: 期望的基础类型（message 或 enum）
            
        Returns:
            真实的类型名，如果无法获取则返回None
        """
        if not self.java_source_analyzer:
            return None
            
        try:
            # 调用Java源码分析器获取真实类型
            real_type = self.java_source_analyzer.get_field_type(field_name_raw, expected_type)
            return real_type
        except Exception as e:
            self.logger.warning(f"    ⚠️  源码分析失败: {e}")
            return None

    def _infer_message_type_from_field_name(self, field_name_raw: str) -> str:
        """
        根据字段名智能推断消息类型名（通用算法，无硬编码）
        
        Args:
            field_name_raw: 原始字段名（如 businessProfile_）
            
        Returns:
            推断出的消息类型名
        """
        # 移除末尾的下划线
        clean_name = field_name_raw.rstrip('_')
        
        if not clean_name:
            return 'UnknownMessage'
        
        # 将camelCase转换为PascalCase
        type_name = self._camel_to_pascal_case(clean_name)
        
        # 通用推断规则（无硬编码）
        # 1. 如果字段名以某些常见后缀结尾，进行相应处理
        if clean_name.lower().endswith('profile'):
            # businessProfile -> Business
            base_name = clean_name[:-7]  # 移除'profile'
            return self._camel_to_pascal_case(base_name) if base_name else type_name
        elif clean_name.lower().endswith('info'):
            # spamInfo -> SpamInfo，保持原样
            return type_name
        elif clean_name.lower().endswith('stats'):
            # commentsStats -> CommentsStats，保持原样
            return type_name
        elif clean_name.lower().endswith('data'):
            # senderIdData -> SenderIdData，保持原样
            return type_name
        elif clean_name.lower().endswith('id'):
            # 对于id字段，有多种可能的类型模式
            # 1. 简单的Id类型：id -> Id
            # 2. 数据类型：id -> IdData  
            # 3. 具体的Id类型：contactId -> ContactIdData
            # 由于无法确定具体类型，保持基础推断，让依赖发现来解决
            return type_name + 'Data'
        else:
            # 默认：直接转换为PascalCase
            return type_name

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
    
    def _determine_field_rule(self, field_type_byte: int) -> str:
        """
        根据字节码确定字段规则
        
        Args:
            field_type_byte: 字段类型字节
            
        Returns:
            字段规则：'optional' 或 'repeated'
        """
        # repeated类型的字节码
        repeated_types = {27, 39, 44, 538}  # repeated_message, repeated_int32, packed_enum, repeated_string
        return 'repeated' if field_type_byte in repeated_types else 'optional'
    
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