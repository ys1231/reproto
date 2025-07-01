# 项目开发约定

## 目录说明
- java源码目录: ../sources
- 输出目录: ../out_proto

## 测试java类
- 'com.truecaller.accountonboarding.v1.Service$SendOnboardingOtpRequest' 测试成功
- 'com.truecaller.accountonboarding.v1.Service$SendOnboardingOtpResponse' 测试成功
- 'com.truecaller.accountonboarding.v1.Service$VerifyOnboardingOtpRequest' 测试成功
- 'com.truecaller.accountonboarding.v1.Service$VerifyOnboardingOtpResponse' 测试失败

## 沟通约定
- **语言**: 始终使用中文进行沟通和交流
- **问题反馈**: 提供详细的日志文件和错误信息便于分析
- **修复方式**: 优先分析问题根因，再进行针对性修复

## 代码修改约定
- **非破坏性**: 只修复发现的问题，不进行不必要的重构
- **向后兼容**: 保持API和功能的向后兼容性
- **测试验证**: 每次修复后都要重新测试验证结果
- **日志优先**: 通过详细日志分析问题，避免盲目修改

## 通用性约定
- **避免硬编码**: 不硬编码特定应用的包名或类名
- **动态推断**: 优先从源码动态提取信息而非硬编码映射
- **错误处理**: 提供详细的错误信息和异常处理
- **工具通用**: 确保工具适用于任何Android应用，不局限于特定应用

## Protobuf约定
- **符号处理**: Java内部类的`$`符号必须替换为`_`（Protobuf不支持`$`）
- **命名规范**: 遵循Google Proto Style Guide
- **类型映射**: 正确映射Java Protobuf Lite类型到proto类型
- **依赖处理**: 自动发现和处理所有依赖的消息和枚举类型

## 逆向工程约定
- **字节码解析**: 基于Google Protobuf Lite的`newMessageInfo`字节码格式
- **源码优先**: 从Java源码直接读取信息，确保准确性
- **递归依赖**: 自动处理依赖链，避免遗漏相关类型
- **缓存机制**: 使用文件缓存避免重复解析

## 错误修复原则
1. **问题定位**: 通过日志精确定位问题所在
2. **根因分析**: 分析问题的根本原因而非表面现象
3. **最小修改**: 用最小的代码修改解决最大的问题
4. **全面测试**: 修复后验证相关功能正常工作
5. **文档更新**: 重要修复需要更新相关文档

## 项目结构约定
- **模块化**: 保持清晰的模块分离（解析、生成、核心、工具）
- **单一职责**: 每个模块只负责特定的功能
- **接口稳定**: 模块间接口保持稳定，避免频繁变动
- **文档完整**: 重要功能提供完整的文档说明

---
*此文档记录了reproto项目开发过程中建立的约定和原则，所有参与者都应遵循这些约定。* 