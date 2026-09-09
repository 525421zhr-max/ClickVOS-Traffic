#!/usr/bin/env bash
set -euo pipefail

# Prerequisite system packages are installed as root from PowerShell:
# wsl -d Ubuntu-24.04 -u root -- apt-get install -y \
#   build-essential ffmpeg git python3 python3-pip python3-venv

venv_dir="${HOME}/.venvs/clickvos"
mkdir -p "$(dirname "${venv_dir}")"
python3 -m venv "${venv_dir}"
"${venv_dir}/bin/python" -m pip install --upgrade pip setuptools wheel
"${venv_dir}/bin/python" -m pip install \
  torch \
  torchvision \
  --index-url https://download.pytorch.org/whl/cu128

"${venv_dir}/bin/python" - <<'PY'
import torch

print("torch:", torch.__version__)
print("torch CUDA runtime:", torch.version.cuda)
print("CUDA available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("GPU:", torch.cuda.get_device_name(0))
    x = torch.rand((1024, 1024), device="cuda")
    print("GPU tensor mean:", x.mean().item())
PY

ffmpeg -version | head -n 1
python3 --version
