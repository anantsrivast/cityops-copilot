#!/bin/bash
set -e

echo "============================================"
echo "  CityOps Copilot Workshop - Build"
echo "============================================"

echo ""
echo "[1/2] Installing Python dependencies..."
# Install CPU-only PyTorch first to prevent sentence-transformers
# from pulling CUDA libs (~5GB) that blow out Codespaces disk.
pip install -q --no-cache-dir \
  torch --index-url https://download.pytorch.org/whl/cpu

pip install -q --no-cache-dir \
  oracleagentmemory \
  sentence-transformers \
  oracledb \
  openai \
  jupyter \
  ipykernel \
  ipywidgets \
  matplotlib \
  pydantic

echo ""
echo "[2/2] Registering Jupyter kernel..."
python -m ipykernel install --user --name workshop --display-name "CityOps Copilot"

echo ""
echo "Build complete. Oracle will start when the Codespace opens."
echo "============================================"
