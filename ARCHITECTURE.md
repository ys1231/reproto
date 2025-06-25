# Protobuf Reconstructor 项目架构

## 🏗️ 总体架构

本项目采用模块化设计，将Protobuf逆向重构过程分解为多个独立的功能模块，确保代码的可维护性和可扩展性。

```
┌─────────────────────────────────────────────────────────────┐
│                    main.py (入口点)                          │
├─────────────────────────────────────────────────────────────┤
│                 core/reconstructor.py                      │
│                    (主协调器)                                │
├─────────────────┬─────────────────┬─────────────────────────┤
│  parsing/       │  core/          │  generation/            │
│  java_parser.py │  info_decoder.py│  proto_generator.py     │
│  (Java解析)     │  (字节码解码)    │  (Proto生成)            │
├─────────────────┼─────────────────┼─────────────────────────┤
│            models/message_definition.py                    │
│                   (数据模型)                                │
├─────────────────────────────────────────────────────────────┤
│                 utils/ (工具模块)                           │
│              logger.py + file_utils.py                     │
└─────────────────────────────────────────────────────────────┘
```

## 📦 模块详解

### 1. 入口层 (Entry Layer)

#### `main.py`
- **职责**: 命令行接口，参数解析，程序入口
- **功能**:
  - 解析命令行参数
  - 初始化日志系统
  - 创建并启动重构器
  - 错误处理和用户反馈

### 2. 核心层 (Core Layer)

#### `core/reconstructor.py` - 主协调器
- **职责**: 整个重构流程的协调和管理
- **核心功能**:
  - 类队列管理 (避免重复处理)
  - 依赖发现和递归处理
  - 模块间的协调调用
  - 结果汇总和文件生成
- **设计模式**: 协调者模式 (Coordinator Pattern)

#### `core/info_decoder.py` - 字节码解码器
- **职责**: Google Protobuf Lite字节码的逆向解析
- **核心技术**:
  - `newMessageInfo`字节码解码
  - 字节码到Protobuf类型映射
  - oneof字段识别 (通过`<`字符检测)
  - 智能类型推断算法
- **技术突破**: 首次成功逆向Protobuf Lite字节码格式

### 3. 解析层 (Parsing Layer)

#### `parsing/java_parser.py` - Java源码解析器
- **职责**: 从Java源码中提取Protobuf相关信息
- **功能**:
  - `newMessageInfo`调用提取
  - 字节码字符串和对象数组解析
  - 枚举值提取
  - 依赖类型发现

#### `parsing/java_source_analyzer.py` - Java源码分析器
- **职责**: 直接从Java源码读取真实类型信息
- **功能**:
  - 字段类型声明分析
  - setter方法分析
  - import语句解析
  - 类型名智能匹配

### 4. 生成层 (Generation Layer)

#### `generation/proto_generator.py` - Proto文件生成器
- **职责**: 根据解析结果生成标准的.proto文件
- **功能**:
  - 符合Google Style Guide的文件生成
  - import语句智能管理
  - 包结构自动推导
  - Java选项自动设置

### 5. 数据模型层 (Model Layer)

#### `models/message_definition.py`
- **包含类型**:
  - `MessageDefinition`: 消息类型定义
  - `FieldDefinition`: 字段定义
  - `OneofDefinition`: oneof字段定义
  - `EnumDefinition`: 枚举类型定义
  - `EnumValueDefinition`: 枚举值定义

### 6. 工具层 (Utility Layer)

#### `utils/logger.py`
- **职责**: 统一的日志管理
- **功能**: 基于loguru的日志系统

#### `utils/file_utils.py`
- **职责**: 文件操作工具
- **功能**: 文件读写、路径处理、目录创建

## 🔄 数据流向

```
1. Java源码输入
   ↓
2. JavaParser 提取字节码信息
   ↓  
3. InfoDecoder 解码字节码 → MessageDefinition/EnumDefinition
   ↓
4. Reconstructor 发现依赖 → 递归处理
   ↓
5. ProtoGenerator 生成.proto文件
   ↓
6. 文件输出
```

## 🧠 核心算法

### 1. 字节码解码算法
```python
# 字节码格式: [字段标签, 字段类型] 对
# 特殊字符 '<' (ord=60) 标识oneof字段
def decode_message_info(info_string, objects):
    bytes_data = decode_unicode_escapes(info_string)
    for i in range(10, len(bytes_data)-1, 2):  # 跳过元数据
        field_tag = bytes_data[i]
        field_type = type_mapping[bytes_data[i+1]]
        # 处理字段...
```

### 2. 依赖发现算法
```python
# 递归依赖发现
def discover_dependencies(message_def):
    for field in message_def.fields:
        if field.type_name in custom_types:
            full_class_name = resolve_type_name(field.type_name)
            if full_class_name not in processed:
                queue.append(full_class_name)
```

### 3. 智能类型推断算法
```python
# 无硬编码的通用推断
def infer_type_from_field_name(field_name):
    clean_name = field_name.rstrip('_')
    if clean_name.endswith('info'):
        return to_pascal_case(clean_name)
    elif clean_name.endswith('data'):
        return to_pascal_case(clean_name)
    # ... 更多通用规则
```

## 🎯 设计原则

### 1. 单一职责原则 (SRP)
- 每个模块只负责一个特定的功能
- InfoDecoder只负责字节码解码
- ProtoGenerator只负责文件生成

### 2. 开放封闭原则 (OCP)
- 通过接口扩展功能，不修改现有代码
- 类型推断算法可以轻松添加新规则

### 3. 依赖倒置原则 (DIP)
- 高层模块不依赖低层模块的具体实现
- 通过抽象接口进行交互

### 4. 无硬编码原则
- 所有类型推断都基于通用算法
- 避免特定应用的硬编码映射

## 🔧 可扩展性

### 1. 新增字节码类型支持
在`InfoDecoder.type_mapping`中添加新的映射：
```python
self.type_mapping[new_type_code] = 'new_protobuf_type'
```

### 2. 新增类型推断规则
在推断方法中添加新的模式匹配：
```python
def infer_type_from_field_name(self, field_name):
    # 添加新的推断规则
    if field_name.endswith('new_pattern'):
        return handle_new_pattern(field_name)
```

### 3. 新增输出格式
继承`ProtoGenerator`并实现新的生成方法：
```python
class CustomProtoGenerator(ProtoGenerator):
    def generate_custom_format(self, message_def):
        # 实现自定义格式生成
```

## 🚀 性能优化

### 1. 队列去重
使用set进行O(1)的重复检查：
```python
processed_classes = set()
pending_classes = set()
```

### 2. 懒加载
只在需要时才解析Java文件和生成proto文件

### 3. 缓存机制
缓存已解析的类型定义，避免重复解析

## 🧪 测试策略

### 1. 单元测试
- 每个模块独立测试
- 模拟输入数据进行测试

### 2. 集成测试
- 端到端的完整流程测试
- 真实Android应用的测试用例

### 3. 回归测试
- 对比生成结果与预期输出
- 确保修改不破坏现有功能

## 📈 监控和日志

### 1. 结构化日志
```python
logger.info("开始处理类", class_name=class_name, field_count=len(fields))
logger.success("生成proto文件", file_path=output_path, size=file_size)
```

### 2. 性能监控
- 处理时间统计
- 内存使用监控
- 文件生成统计

### 3. 错误追踪
- 详细的错误堆栈
- 上下文信息记录
- 失败重试机制

## 🔮 未来扩展

### 1. 多语言支持
- 支持生成其他语言的绑定代码
- 扩展到其他序列化格式

### 2. GUI界面
- 可视化的操作界面
- 拖拽式的配置管理

### 3. 云端处理
- 支持大规模批量处理
- 分布式解析能力

### 4. AI增强
- 机器学习辅助类型推断
- 智能错误修复建议 