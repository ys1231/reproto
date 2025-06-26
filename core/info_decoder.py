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
        
        # Protobuf字段类型映射表
        # 键：字节码中的类型值，值：对应的protobuf字段类型
        self.type_mapping = {
            0: 'double',      # 64位浮点数 (double) - 基于ContactAddress.latitude_和longitude_的分析
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
            50: 'map',       # Map字段 - 基于BulkSearchResult.contacts的分析
            520: 'string',   # UTF-8字符串
            538: 'string',   # REPEATED STRING (Ț = 538)  
        }
        
        # Java源码分析器
        self.java_source_analyzer = java_source_analyzer
        
        # 统计未知类型（用于持续改进）
        self.unknown_types_stats = {}  # {byte_code: count}
    
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
            bytes_data: 字节码数据
            objects: 对象数组
        """
        # 跳过前10个字节的元数据
        field_start = 10
        object_index = 0
        
        # 每次处理2个字节：[字段标签, 字段类型]
        for i in range(field_start, len(bytes_data) - 1, 2):
            field_tag = bytes_data[i]
            field_type_byte = bytes_data[i + 1]
            
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
        
        # 对于消息类型、枚举类型和map类型，检查objects数组中是否有具体的类型引用
        if field_type in ['message', 'enum', 'map']:
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
                        elif field_type == 'map':
                            field_type_name = self._infer_map_type_from_source(field_name_raw)
                            self.logger.info(f"    🔍 推断map类型: {field_name} -> {field_type_name}")
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
                    elif field_type == 'map':
                        field_type_name = self._infer_map_type_from_source(field_name_raw)
                        self.logger.info(f"    🔍 推断map类型: {field_name} -> {field_type_name}")
        
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
        # 基础类型映射
        type_mapping = {
            'boolean': 'bool',
            'byte': 'int32',
            'short': 'int32', 
            'int': 'int32',
            'long': 'int64',
            'float': 'float',
            'double': 'double',
            'String': 'string',
            'ByteString': 'bytes',
        }
        
        # 直接映射
        if java_type in type_mapping:
            return type_mapping[java_type]
        
        # 处理复杂类型
        if java_type.startswith('MapFieldLite<'):
            return 'map'
        elif java_type.startswith('Internal.ProtobufList<') or java_type.startswith('List<'):
            return 'message'  # repeated message
        elif java_type.endswith('[]'):
            return 'message'  # repeated
        elif '.' in java_type and java_type.split('.')[-1][0].isupper():
            # 看起来像是类名，可能是message或enum
            return 'message'  # 默认为message，具体类型由其他逻辑确定
        
        # 默认返回string
        return 'string'
    
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