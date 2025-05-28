"""
Utility functions for ComfyModelCleaner
"""

import os
import sys
from pathlib import Path
from typing import Optional, List


def get_comfy_dir() -> Path:
    """
    Get the ComfyUI root directory.

    Returns:
        Path: The ComfyUI root directory
    """
    # Try to find ComfyUI directory from current working directory
    current_dir = Path.cwd()

    # Check if we're already in ComfyUI directory
    if (current_dir / "main.py").exists() and (current_dir / "models").exists():
        return current_dir

    # Check parent directories
    for parent in current_dir.parents:
        if (parent / "main.py").exists() and (parent / "models").exists():
            return parent

    # Fallback: try to find from sys.path
    for path in sys.path:
        path_obj = Path(path)
        if (path_obj / "main.py").exists() and (path_obj / "models").exists():
            return path_obj

    # Last resort: assume current directory
    return current_dir


def get_models_dir() -> Path:
    """
    Get the models directory path.

    Returns:
        Path: The models directory
    """
    comfy_dir = get_comfy_dir()
    return comfy_dir / "models"


def get_custom_nodes_dir() -> Path:
    """
    Get the custom_nodes directory path.

    Returns:
        Path: The custom_nodes directory
    """
    comfy_dir = get_comfy_dir()
    return comfy_dir / "custom_nodes"


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human readable format.

    Args:
        size_bytes: Size in bytes

    Returns:
        str: Formatted size string
    """
    if size_bytes == 0:
        return "0 B"

    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    size = float(size_bytes)

    while size >= 1024.0 and i < len(size_names) - 1:
        size /= 1024.0
        i += 1

    return f"{size:.1f} {size_names[i]}"


def is_model_file(file_path: Path) -> bool:
    """
    Check if a file is a model file based on its extension.

    Args:
        file_path: Path to the file

    Returns:
        bool: True if it's a model file
    """
    model_extensions = {
        '.ckpt', '.safetensors', '.pt', '.pth', '.bin',
        '.onnx', '.pb', '.tflite', '.h5', '.pkl'
    }

    return file_path.suffix.lower() in model_extensions


def get_model_directories() -> List[Path]:
    """
    Get all standard model directories in ComfyUI.

    Returns:
        List[Path]: List of model directory paths
    """
    models_dir = get_models_dir()

    standard_dirs = [
        "checkpoints",
        "loras",
        "embeddings",
        "vae",
        "clip",
        "unet",
        "controlnet",
        "upscale_models",
        "style_models",
        "diffusers"
    ]

    existing_dirs = []
    for dir_name in standard_dirs:
        dir_path = models_dir / dir_name
        if dir_path.exists() and dir_path.is_dir():
            existing_dirs.append(dir_path)

    return existing_dirs


def safe_file_operation(func):
    """
    Decorator for safe file operations with error handling.
    """
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except PermissionError as e:
            print(f"Permission error: {e}")
            return None
        except FileNotFoundError as e:
            print(f"File not found: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error in {func.__name__}: {e}")
            return None
    return wrapper


def find_files_by_pattern(directory: Path, pattern: str) -> List[Path]:
    """
    Find files matching a pattern in a directory.

    Args:
        directory: Directory to search in
        pattern: Glob pattern to match

    Returns:
        List[Path]: List of matching file paths
    """
    try:
        return list(directory.glob(pattern))
    except Exception as e:
        print(f"Error searching for pattern {pattern} in {directory}: {e}")
        return []


def calculate_directory_size(directory: Path) -> int:
    """
    Calculate total size of all files in a directory.

    Args:
        directory: Directory to calculate size for

    Returns:
        int: Total size in bytes
    """
    total_size = 0
    try:
        for file_path in directory.rglob('*'):
            if file_path.is_file():
                total_size += file_path.stat().st_size
    except Exception as e:
        print(f"Error calculating directory size for {directory}: {e}")

    return total_size
