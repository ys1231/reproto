

# [reproto](https://github.com/ys1231/reproto)

🔧 **从JADX反编译的Java源码自动重构Protobuf .proto文件**

一个强大的逆向工程工具，能够从任何使用Google Protobuf Lite的Android应用中自动重构出完整的.proto文件结构。

## ✨ 特性

- 🎯 **精准解析**: 基于Google Protobuf Lite字节码的逆向工程
- 🔄 **递归依赖**: 自动发现和处理所有依赖的消息和枚举类型
- 📦 **完整支持**: 支持oneof、repeated、map、枚举等所有Protobuf特性
- 🌐 **通用性**: 适用于任何Android应用，无需硬编码映射
- 🧠 **智能推断**: 从Java源码直接读取类型信息，确保高准确性
- 📝 **标准输出**: 严格遵循Google Proto Style Guide

## 🛠️ 安装

### 方式一：拉取代码
```bash
# 克隆项目
git clone https://github.com/ys1231/reproto.git
cd reproto

# 安装依赖
poetry install
```

### 方式二：pip安装
```bash
# 从本地构建安装
pip install .

# 在线安装
pip install reproto
```

## 📖 使用

### 命令行使用
```bash
# 基本用法 python main.py or 命令 reproto
reproto <java_sources_dir> <root_class> <output_dir> [--verbose]

# 示例：重构普通类
reproto ./out_jadx/sources com.example.messaging.v1.models.MessageData ./protos_generated

# 示例：重构内部类（注意：包含$的类名需要用单引号包裹）
reproto ./out_jadx/sources 'com.example.account.v1.Models$Onboarded' ./output

# 详细输出
reproto ./out_jadx/sources com.example.Model ./output --verbose

# 编译
## 生成 pyi 方便 IDE 索引 其他正常编译
protoc --proto_path ./proto --pyi_out=./ ./proto/google/**/*.proto
```

### 代码使用
```python
# 作为包使用
from core import ProtoReconstructor
from utils.logger import setup_logger
from pathlib import Path

# 初始化
setup_logger("./logs")
sources_dir = Path("./out_jadx/sources")
output_dir = Path("./protos_generated")

# 创建重构器并执行
reconstructor = ProtoReconstructor(sources_dir, output_dir)
results = reconstructor.reconstruct_from_root("com.example.Model")

# 查看结果
for class_name, definition in results.items():
    print(f"生成: {class_name} -> {definition.proto_filename}")
```

### 参数说明
- `java_sources_dir`: JADX反编译的Java源码目录路径
- `root_class`: 要重构的根类完整类名
- `output_dir`: 生成的proto文件输出目录路径
- `--verbose`: 显示详细处理信息

## ⚠️ 注意事项

### 重要提醒
- **内部类命名**: 包含`$`符号的类名（如内部类）必须用**单引号包裹**
  ```bash
  # ✅ 正确
  reproto ./sources 'com.example.Outer$Inner' ./output
  
  # ❌ 错误
  reproto ./sources com.example.Outer$Inner ./output
  ```

### 使用建议
1. **JADX反编译**: 先使用JADX反编译APK文件
   ```bash
   jadx -d out_jadx app.apk
   ```

2. **类名查找**: 在JADX GUI中找到目标Protobuf类的完整类名

3. **输出目录**: 确保输出目录有写入权限

4. **日志查看**: 使用`--verbose`参数查看详细处理过程

## 📊 输出示例

### 输入：Java源码
```java
public final class SearchResult extends GeneratedMessageLite {
    private MapFieldLite<String, Contact> contacts_;
    private Internal.ProtobufList<String> phoneNumbers_;
    
    public static final int CONTACTS_FIELD_NUMBER = 1;
    public static final int PHONE_NUMBERS_FIELD_NUMBER = 2;
}
```

### 输出：Proto文件
```protobuf
syntax = "proto3";

package com.example.search.v1.models;

option java_package = "com.example.search.v1.models";
option java_multiple_files = true;

message SearchResult {
  map<string, Contact> contacts = 1;
  repeated string phone_numbers = 2;
}
```

## 🛠️ 支持的特性

### Protobuf类型支持
- ✅ 基础类型：`string`, `int32`, `int64`, `bool`, `float`, `double`
- ✅ 消息类型：嵌套消息和引用消息
- ✅ 枚举类型：完整的枚举值解析
- ✅ 重复字段：`repeated` 类型
- ✅ 映射字段：`map<key, value>` 类型
- ✅ Oneof字段：互斥字段组
- ✅ Google Well-Known Types

### 特殊Java类型
- `MapFieldLite<K, V>` → `map<K, V>`
- `Internal.ProtobufList<T>` → `repeated T`
- `Internal.IntList` → `repeated enum` (枚举列表)

## 📁 项目结构

```
reproto/
├── main.py                     # 主程序入口
├── core/                       # 核心组件
│   ├── reconstructor.py        # 主协调器
│   └── info_decoder.py         # 字节码解码器
├── parsing/                    # 解析模块
│   ├── java_parser.py          # Java文件解析器
│   └── enum_parser.py          # 枚举解析器
├── generation/                 # 生成模块
│   └── proto_generator.py      # Proto文件生成器
├── models/                     # 数据模型
│   └── message_definition.py   # 消息和枚举定义
├── utils/                      # 工具函数
│   ├── logger.py              # 日志系统
│   ├── file_cache.py          # 文件缓存系统
│   ├── type_utils.py          # 类型处理工具
│   └── report_utils.py        # 结果统计工具
└── include/                    # Google Protobuf标准文件
    └── google/protobuf/        # Well-Known Types
```

## 🔧 开发

```bash
# 使用Poetry管理依赖
poetry install
poetry shell

# 运行测试
reproto ../out_jadx/sources com.example.TestClass ../test_output --verbose
```

---

**🚀 立即开始重构你的Protobuf文件！**
