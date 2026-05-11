#!/bin/bash
# 启动服务器（后台）
python3 server.py &
sleep 1
# 发送请求
response=$(curl -s http://localhost:8000)
if [ "$response" = "test a" ]; then
    echo "Test passed: response is exactly 'test a'"
    exit 0
else
    echo "Test failed: got '$response'"
    exit 1
fi