实现一个 Python HTTP 服务
要求：
- 监听 9090 端口
- 访问 / 时返回 JSON: {"status": "ok", "message": "Hello OPC"}
- Content-Type 必须是 application/json
- 使用内置 http.server 模块，不引入额外依赖
