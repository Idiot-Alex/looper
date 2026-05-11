#!/bin/bash
set -e

# Start server in background
python3 src/server.py &
SERVER_PID=$!

# Wait for server to be ready
sleep 1

# Run curl and capture output
OUTPUT=$(curl -s http://localhost:8000/)
EXIT_CODE=$?

# Print output for verification
echo "Curl output: '$OUTPUT'"
echo "Exit code: $EXIT_CODE"

# Check that output is exactly 'test a'
if [ "$OUTPUT" = "test a" ]; then
    echo "Test passed: output matches 'test a'"
else
    echo "Test failed: output is '$OUTPUT'"
    kill $SERVER_PID 2>/dev/null
    exit 1
fi

# Cleanup
kill $SERVER_PID 2>/dev/null
