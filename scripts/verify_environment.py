"""Verify the Python, PyTorch, and CUDA runtime used by ClickVOS."""

import platform

import torch


def main() -> None:
    print("python:", platform.python_version())
    print("torch:", torch.__version__)
    print("torch_cuda_runtime:", torch.version.cuda)
    print("cuda_available:", torch.cuda.is_available())
    if not torch.cuda.is_available():
        raise SystemExit("CUDA is not available to PyTorch")

    print("gpu:", torch.cuda.get_device_name(0))
    print("compute_capability:", torch.cuda.get_device_capability(0))
    matrix = torch.randn((2048, 2048), device="cuda")
    result = matrix @ matrix
    torch.cuda.synchronize()
    print("gpu_matmul_mean:", result.mean().item())


if __name__ == "__main__":
    main()
