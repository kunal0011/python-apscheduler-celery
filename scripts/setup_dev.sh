#!/bin/bash
# Setup script for development environment using tox

set -e

echo "🚀 Setting up development environment with tox + uv..."

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "📦 Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi

echo "✅ uv version: $(uv --version)"

# Install tox and tox-uv globally with uv
echo "� Installing tox and tox-uv..."
uv pip install --system tox tox-uv

# Create and setup development environment with tox
echo "� Creating development environment..."
tox -re dev

echo ""
echo "✅ Setup complete!"
echo ""
echo "The tox dev environment is ready at: .tox/dev"
echo ""
echo "To activate the dev environment:"
echo "  source .tox/dev/bin/activate"
echo ""
echo "Available tox commands:"
echo "  tox                    # Run all test environments"
echo "  tox -e py310           # Run Python 3.10 tests only"
echo "  tox -e lint            # Run linters"
echo "  tox -e format          # Auto-format code"
echo "  tox -e type            # Run type checking"
echo "  tox -e all             # All tests with coverage"
echo "  tox -re dev            # Recreate dev environment"

