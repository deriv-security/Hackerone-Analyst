#!/bin/bash

echo "Cleaning Python cache files..."

echo "Finding and removing __pycache__ directories..."
find . -type d -name "__pycache__" -exec rm -rf {} +

echo "Finding and removing .pyc files..."
find . -name "*.pyc" -delete

echo "Removing .pytest_cache directory..."
rm -rf .pytest_cache

echo "Cleanup complete!"
