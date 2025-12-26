#!/bin/bash
# Install git hooks for DataPlatform

set -e

echo "📦 Installing git hooks..."

# Create .git/hooks directory if it doesn't exist
mkdir -p .git/hooks

# Copy pre-push hook
cp scripts/hooks/pre-push .git/hooks/pre-push
chmod +x .git/hooks/pre-push

echo "✅ Pre-push hook installed at .git/hooks/pre-push"
echo ""
echo "Hook will run before each push to:"
echo "  🔒 Check for API keys/secrets"
echo "  🧹 Lint code with ruff"
echo "  🎨 Check code formatting"
echo "  🧪 Run unit tests"
echo ""
echo "To bypass hook (not recommended):"
echo "  git push --no-verify"
