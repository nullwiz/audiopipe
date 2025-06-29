#!/bin/bash

# AudioPipe WASM Build Script
# This script builds the Go application to WebAssembly

set -e

echo "🚀 Building AudioPipe WASM..."

# Find Go installation
GO_BIN=""
if command -v go &> /dev/null; then
    GO_BIN="go"
elif [ -f "/usr/local/go/bin/go" ]; then
    GO_BIN="/usr/local/go/bin/go"
elif [ -f "/usr/lib/go-1.18/bin/go" ]; then
    GO_BIN="/usr/lib/go-1.18/bin/go"
else
    echo "❌ Go is not installed. Please install Go 1.21 or later."
    exit 1
fi

# Check Go version
GO_VERSION=$($GO_BIN version | awk '{print $3}' | sed 's/go//')
REQUIRED_VERSION="1.21"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$GO_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo "❌ Go version $REQUIRED_VERSION or later is required. Current version: $GO_VERSION"
    exit 1
fi

echo "✅ Go version: $GO_VERSION"

# Set WASM environment variables
export GOOS=js
export GOARCH=wasm

echo "📦 Building main.wasm..."

# Build the WASM binary
$GO_BIN build -o main.wasm main.go

if [ $? -eq 0 ]; then
    echo "✅ Successfully built main.wasm"
else
    echo "❌ Failed to build main.wasm"
    exit 1
fi

# Copy wasm_exec.js from Go installation
GOROOT=$($GO_BIN env GOROOT)
WASM_EXEC_JS_PATHS=(
    "$GOROOT/misc/wasm/wasm_exec.js"
    "$GOROOT/lib/wasm/wasm_exec.js"
)

WASM_EXEC_JS=""
for path in "${WASM_EXEC_JS_PATHS[@]}"; do
    if [ -f "$path" ]; then
        WASM_EXEC_JS="$path"
        break
    fi
done

if [ -n "$WASM_EXEC_JS" ]; then
    cp "$WASM_EXEC_JS" .
    echo "✅ Copied wasm_exec.js from $WASM_EXEC_JS"
else
    echo "❌ Could not find wasm_exec.js in any of the expected locations:"
    for path in "${WASM_EXEC_JS_PATHS[@]}"; do
        echo "   - $path"
    done
    echo "Please copy it manually from your Go installation"
    exit 1
fi

# Check file sizes
WASM_SIZE=$(du -h main.wasm | cut -f1)
echo "📊 WASM file size: $WASM_SIZE"

echo ""
echo "🎉 Build completed successfully!"
echo ""
echo "📁 Generated files:"
echo "   - main.wasm ($WASM_SIZE)"
echo "   - wasm_exec.js"
echo ""
echo "🌐 To serve the application:"
echo "   1. Start a local web server in this directory"
echo "   2. Open index.html in your browser"
echo ""
echo "💡 Example server commands:"
echo "   - Python: python3 -m http.server 8080"
echo "   - Node.js: npx serve ."
echo "   - Go: go run server.go"
echo ""
