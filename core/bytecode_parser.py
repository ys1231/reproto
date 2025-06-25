from typing import List, Dict, Tuple
import re
from ..models import FieldDefinition, OneofDefinition

class BytecodeParser:
    """
    重新设计的 Protobuf info_string 解析器，基于对 Google Protobuf Lite 格式的深入理解。
    
    info_string 格式分析：
    - 前面是头部信息（版本、字段数量等）
    - 后面是字段描述符，每个字段用特定格式编码
    - '<' 字符表示 oneof 字段
    - 数字表示字段标签
    """

    def __init__(self, info_bytes: bytes, objects: List[str]):
        """
        初始化解析器。

        参数:
            info_bytes (bytes): 从 info_string 编码而来的字节数组。
            objects (List[str]): 作为符号表的 objects 数组。
        """
        self.info_string = info_bytes.decode('utf-8')
        self.objects = objects
        # print(f"  > 原始 info_string: {repr(self.info_string)}")
        # print(f"  > 对象数组: {self.objects}")

    def parse(self) -> Tuple[List[FieldDefinition], Dict[str, OneofDefinition]]:
        """
        解析 info_string 并返回字段定义。
        
        基于观察到的模式：
        - SearchResult: "\\u0000\\u0002\\u0001\\u0000\\u0001\\u0002\\u0002\\u0000\\u0000\\u0000\\u0001<\\u0000\\u0002<\\u0000"
        - ContactPhone: "\\u0000\\u0003\\u0001\\u0000\\u0001\\u0003\\u0003\\u0000\\u0000\\u0000\\u0001<\\u0000\\u0002<\\u0000\\u0003<\\u0000"
        """
        fields: List[FieldDefinition] = []
        oneofs: Dict[str, OneofDefinition] = {}
        
        # 尝试解析字段描述符部分
        # 寻找 '<' 字符，它们标识 oneof 字段
        field_descriptors = self._extract_field_descriptors()
        
        if not field_descriptors:
            return fields, oneofs
            
        # 确定 oneof 名称（从 objects 数组中）
        oneof_name = self._determine_oneof_name()
        
        if oneof_name:
            # 这是一个 oneof 结构
            oneof_def = OneofDefinition(name=oneof_name)
            
            for i, desc in enumerate(field_descriptors):
                if desc.get('is_oneof'):
                    field_tag = desc['tag']
                    field_type = self._determine_field_type(i + 2)  # objects[2], objects[3], etc.
                    field_name = self._generate_field_name(field_type, field_tag)
                    
                    field = FieldDefinition(
                        name=field_name,
                        type=field_type,
                        tag=field_tag,
                        rule="optional"
                    )
                    oneof_def.fields.append(field)
            
            oneofs[oneof_name] = oneof_def
        else:
            # 常规字段结构
            for i, desc in enumerate(field_descriptors):
                field_tag = desc['tag']
                # 对于常规字段，从 objects 数组中获取字段名
                if field_tag - 1 < len(self.objects):
                    raw_field_name = self.objects[field_tag - 1]  # tag 从 1 开始，数组从 0 开始
                    field_name = self._clean_field_name(raw_field_name)
                else:
                    field_name = f"field_{field_tag}"
                
                # 尝试推断字段类型
                field_type = self._infer_field_type(desc, field_tag)
                
                # 检查是否是 repeated 字段
                if field_type.startswith("repeated "):
                    rule = "repeated"
                    field_type = field_type[9:]  # 移除 "repeated " 前缀
                else:
                    rule = "optional"
                
                field = FieldDefinition(
                    name=field_name,
                    type=field_type,
                    tag=field_tag,
                    rule=rule
                )
                fields.append(field)
        
        return fields, oneofs

    def _extract_field_descriptors(self) -> List[Dict]:
        """
        从 info_string 中提取字段描述符。
        
        基于观察：
        - 字段描述符通常在字符串的后半部分
        - '<' 字符标识 oneof 字段
        - 数字字符表示字段标签
        """
        descriptors = []
        
        # 先打印原始字符串的字符分析
        # print(f"  > 字符串分析:")
        # for i, char in enumerate(self.info_string):
        #     if ord(char) > 32:  # 可打印字符
        #         print(f"    位置 {i}: '{char}' (ord={ord(char)})")
        #     else:
        #         print(f"    位置 {i}: \\x{ord(char):02x}")
        
        # 寻找 '<' 字符的位置
        oneof_positions = []
        for i, char in enumerate(self.info_string):
            if char == '<':
                oneof_positions.append(i)
                
        # print(f"  > 找到 oneof 标记位置: {oneof_positions}")
        
        # 对于每个 '<' 字符，查找前面的数字作为字段标签
        for pos in oneof_positions:
            # 查找 '<' 前面的字符
            if pos > 0:
                prev_char = self.info_string[pos - 1]
                prev_byte = ord(prev_char)
                # print(f"    '<' 前面的字节: \\x{prev_byte:02x} (值={prev_byte})")
                
                # 检查是否是有效的字段标签（1-15 是常见范围）
                if 1 <= prev_byte <= 15:
                    tag = prev_byte
                    descriptors.append({
                        'tag': tag,
                        'is_oneof': True,
                        'position': pos
                    })
                    # print(f"    发现 oneof 字段: tag={tag}, 位置={pos}")
        
        # 如果没有找到 oneof 字段，尝试寻找普通字段
        if not descriptors:
            # 寻找可能的字段标签模式
            # 对于非 oneof 字段，我们需要查找其他模式
            # print(f"  > 没有找到 oneof 字段，尝试寻找常规字段...")
            
            # 查找特殊字符 'Ȉ' (ord=520) 这似乎是字段标记
            for i, char in enumerate(self.info_string):
                if ord(char) == 520:  # 'Ȉ' 字符
                    # 查找前面的字节作为字段标签
                    if i > 0:
                        prev_byte = ord(self.info_string[i - 1])
                        if 1 <= prev_byte <= 50:  # 扩大范围以捕获更多字段
                            descriptors.append({
                                'tag': prev_byte,
                                'is_oneof': False,
                                'position': i
                            })
                            # print(f"    发现常规字段: tag={prev_byte}, 位置={i}")
            
            # 如果还是没有找到，尝试其他数字模式
            if not descriptors:
                for i, char in enumerate(self.info_string):
                    byte_val = ord(char)
                    if 1 <= byte_val <= 20 and byte_val <= len(self.objects):  # 可能的字段标签
                        # 检查前后上下文以确认这是字段标签
                        if i < len(self.info_string) - 1:
                            next_char = self.info_string[i + 1]
                            # 如果下一个字符是特殊标记，这可能是字段标签
                            if ord(next_char) in [50, 60, 520, 27]:  # 各种字段类型标记
                                descriptors.append({
                                    'tag': byte_val,
                                    'is_oneof': False,
                                    'position': i
                                })
                                # print(f"    发现可能的字段: tag={byte_val}, 位置={i}")
        
        return descriptors

    def _determine_oneof_name(self) -> str:
        """
        从 objects 数组确定 oneof 的名称。
        
        观察：
        - objects[0] 通常是 oneof 字段名（如 "result_", "sealedValue_"）
        - objects[1] 通常是 case 字段名（如 "resultCase_", "sealedValueCase_"）
        """
        if len(self.objects) >= 2:
            field_name = self.objects[0]
            case_name = self.objects[1]
            
            # 检查是否符合 oneof 模式
            if (field_name.endswith('_') and 
                case_name.endswith('Case_') and 
                case_name.startswith(field_name[:-1])):
                
                # 从字段名生成 oneof 名称
                base_name = field_name[:-1]  # 移除末尾的 '_'
                return self._to_snake_case(base_name)
        
        return ""

    def _determine_field_type(self, object_index: int) -> str:
        """
        从 objects 数组确定字段类型。
        """
        if object_index < len(self.objects):
            obj = self.objects[object_index]
            if obj.endswith('.class'):
                # 移除 '.class' 后缀，提取类名
                class_name = obj[:-6]
                # 提取最后一部分作为类型名
                return class_name.split('.')[-1]
            else:
                return obj
        return "unknown"

    def _generate_field_name(self, field_type: str, field_tag: int) -> str:
        """
        根据字段类型和标签生成字段名称。
        """
        # 将类型名转换为 snake_case
        name = self._to_snake_case(field_type)
        return name

    def _to_snake_case(self, name: str) -> str:
        """
        将 CamelCase 转换为 snake_case。
        """
        # 处理连续的大写字母
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        # 处理小写字母后跟大写字母的情况
        s2 = re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1)
        return s2.lower()

    def _clean_field_name(self, name: str) -> str:
        """
        清理字段名称，去除不必要的后缀或前缀。
        """
        # 去除末尾的下划线
        if name.endswith('_'):
            name = name[:-1]
        # 转换为 snake_case
        return self._to_snake_case(name)

    def _infer_field_type(self, desc: Dict, field_tag: int) -> str:
        """
        根据字段描述符推断字段类型。
        """
        # 检查 info_string 中字段标签后面的字节来推断类型
        position = desc.get('position', -1)
        if position > 0 and position < len(self.info_string) - 1:
            # 查看字段标签后面的字节
            next_byte = ord(self.info_string[position + 1])
            
            # 根据字节值推断类型
            if next_byte == 27:  # 0x1B - repeated message
                # 查找对应的类类型
                if field_tag < len(self.objects):
                    class_obj = self.objects[field_tag]  # objects[1] 对应 tag=1
                    if class_obj.endswith('.class'):
                        class_name = class_obj[:-6].split('.')[-1]
                        return f"repeated {class_name}"
                return "repeated message"
            elif next_byte == 520:  # 'Ȉ' - string field
                return "string"
            elif next_byte == 12:  # 0x0C - enum
                return "int32"  # 枚举通常映射为 int32
            elif next_byte == 50:  # '2' - 可能是某种数字类型
                return "int32"
            
        # 默认返回 string
        return "string" 