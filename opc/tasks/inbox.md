实现一个简单的 Python HTTP 服务

要求：
- 监听 8080 端口
- 访问根路径 / 时返回 "Hello OPC"
- 不引入额外依赖（使用内置 http.server）
- 启动后可以用 curl 测试

示例：
```bash
curl http://localhost:8080/
# 应返回: Hello OPC
```
