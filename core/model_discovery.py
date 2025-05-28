"""
模型发现引擎 - ComfyModelCleaner V2.0

实现基于模型名称匹配的精确检测，区分单文件模型和目录模型。
"""

from pathlib import Path
from typing import Dict, List, Set, Any, Tuple
from dataclasses import dataclass

from .utils import get_models_dir, is_model_file


@dataclass
class ModelInfo:
    """模型信息数据类"""
    name: str
    path: str
    relative_path: str
    size_bytes: int
    modified_time: float
    access_time: float  # 新增访问时间字段
    model_type: str  # 'file' or 'directory'
    directory: str
    extension: str
    confidence_factors: Dict[str, Any]


class ModelDirectoryFilter:
    """模型目录过滤器"""

    CORE_DIRECTORIES = {
        'checkpoints', 'loras', 'embeddings', 'vae', 'clip',
        'unet', 'controlnet', 'upscale_models', 'diffusion_models',
        'clip_vision', 'style_models', 'gligen', 'hypernetworks'
    }

    def __init__(self):
        self.excluded_dirs = set()
        self.included_dirs = set()

    def filter_directories(self, user_config: Dict[str, bool]) -> Set[str]:
        """
        根据用户配置过滤目录

        Args:
            user_config: 用户配置字典，键为目录名，值为是否包含

        Returns:
            Set[str]: 应该包含的目录名集合
        """
        included = set()

        # 处理核心目录
        for dir_name in self.CORE_DIRECTORIES:
            if user_config.get(dir_name, False):
                included.add(dir_name)

        # 总是包含自定义节点目录（非核心目录）
        # 这些目录可能包含未使用的模型文件，需要检测
        models_dir = get_models_dir()
        if models_dir.exists():
            for item in models_dir.iterdir():
                if (item.is_dir() and
                    not item.name.startswith('.') and
                    item.name not in self.CORE_DIRECTORIES):
                    included.add(item.name)

        return included


class ModelDiscovery:
    """模型发现引擎"""

    def __init__(self, max_depth: int = 5):
        self.models_dir = get_models_dir()
        self.max_depth = max_depth
        self.directory_filter = ModelDirectoryFilter()

    def discover_models(self, user_config: Dict[str, Any]) -> Dict[str, List[ModelInfo]]:
        """
        递归发现所有模型

        Args:
            user_config: 用户配置

        Returns:
            Dict containing:
            - 'single_file_models': List[ModelInfo] - 单文件模型列表
            - 'directory_models': List[ModelInfo] - 目录模型列表
        """
        print("🔍 开始模型发现...")

        # 过滤目录
        included_dirs = self.directory_filter.filter_directories(user_config)
        print(f"📁 将扫描 {len(included_dirs)} 个目录: {', '.join(sorted(included_dirs))}")

        single_file_models = []
        directory_models = []

        # 扫描每个包含的目录
        for dir_name in included_dirs:
            dir_path = self.models_dir / dir_name
            if dir_path.exists() and dir_path.is_dir():
                print(f"  扫描目录: {dir_name}")

                # 发现该目录中的模型
                dir_single_files, dir_directory_models = self._discover_in_directory(
                    dir_path, dir_name
                )

                single_file_models.extend(dir_single_files)
                directory_models.extend(dir_directory_models)

                print(f"    发现 {len(dir_single_files)} 个单文件模型, {len(dir_directory_models)} 个目录模型")

        print(f"✅ 模型发现完成: {len(single_file_models)} 个单文件, {len(directory_models)} 个目录")

        return {
            'single_file_models': single_file_models,
            'directory_models': directory_models
        }

    def _discover_in_directory(self, directory: Path, parent_dir: str) -> Tuple[List[ModelInfo], List[ModelInfo]]:
        """
        在指定目录中发现模型

        Args:
            directory: 要扫描的目录
            parent_dir: 父目录名称

        Returns:
            Tuple[List[ModelInfo], List[ModelInfo]]: (单文件模型, 目录模型)
        """
        single_files = []
        directory_models = []

        try:
            self._scan_directory_recursive(
                directory, parent_dir, single_files, directory_models, 0
            )
        except Exception as e:
            print(f"❌ 扫描目录 {directory} 时出错: {e}")

        return single_files, directory_models

    def _scan_directory_recursive(self,
                                 directory: Path,
                                 parent_dir: str,
                                 single_files: List[ModelInfo],
                                 directory_models: List[ModelInfo],
                                 current_depth: int):
        """
        递归扫描目录

        Args:
            directory: 当前目录
            parent_dir: 父目录名称
            single_files: 单文件模型列表（会被修改）
            directory_models: 目录模型列表（会被修改）
            current_depth: 当前递归深度
        """
        if current_depth > self.max_depth:
            return

        try:
            # 首先检查当前目录是否是模型目录
            if current_depth > 0 and self.is_model_directory(directory):
                model_name = self.extract_model_name(directory, is_directory=True)
                if model_name:
                    model_info = self._create_directory_model_info(directory, model_name, parent_dir)
                    directory_models.append(model_info)
                    return  # 如果是模型目录，不再递归其子目录

            # 扫描当前目录的文件和子目录
            for item in directory.iterdir():
                if item.is_file() and self.is_model_file(item):
                    # 单文件模型
                    model_name = self.extract_model_name(item, is_directory=False)
                    if model_name:
                        model_info = self._create_file_model_info(item, model_name, parent_dir)
                        single_files.append(model_info)

                elif item.is_dir() and not item.name.startswith('.'):
                    # 递归扫描子目录
                    self._scan_directory_recursive(
                        item, parent_dir, single_files, directory_models, current_depth + 1
                    )

        except Exception as e:
            print(f"❌ 递归扫描 {directory} 时出错: {e}")

    def is_model_file(self, file_path: Path) -> bool:
        """
        判断是否是模型文件

        Args:
            file_path: 文件路径

        Returns:
            bool: 是否是模型文件
        """
        return is_model_file(file_path)

    def is_model_directory(self, dir_path: Path) -> bool:
        """
        判断是否是模型目录

        Args:
            dir_path: 目录路径

        Returns:
            bool: 是否是模型目录
        """
        # 检查目录中是否包含模型文件
        try:
            for item in dir_path.iterdir():
                if item.is_file() and self.is_model_file(item):
                    return True
                # 检查一级子目录
                elif item.is_dir() and not item.name.startswith('.'):
                    for subitem in item.iterdir():
                        if subitem.is_file() and self.is_model_file(subitem):
                            return True
        except Exception:
            pass

        return False

    def extract_model_name(self, path: Path, is_directory: bool = False) -> str:
        """
        提取模型名称

        Args:
            path: 模型路径
            is_directory: 是否是目录模型

        Returns:
            str: 模型名称
        """
        if is_directory:
            # 对于目录模型，使用目录名作为模型名
            return path.name
        else:
            # 对于文件模型，使用不带扩展名的文件名
            return path.stem

    def _create_file_model_info(self, file_path: Path, model_name: str, parent_dir: str) -> ModelInfo:
        """
        创建单文件模型信息

        Args:
            file_path: 文件路径
            model_name: 模型名称
            parent_dir: 父目录名称

        Returns:
            ModelInfo: 模型信息对象
        """
        try:
            stat = file_path.stat()

            return ModelInfo(
                name=model_name,
                path=str(file_path),
                relative_path=str(file_path.relative_to(self.models_dir)),
                size_bytes=stat.st_size,
                modified_time=stat.st_mtime,
                access_time=stat.st_atime,
                model_type='file',
                directory=parent_dir,
                extension=file_path.suffix.lower(),
                confidence_factors={
                    'file_size': stat.st_size,
                    'last_modified': stat.st_mtime,
                    'last_accessed': stat.st_atime,
                    'extension': file_path.suffix.lower()
                }
            )
        except Exception as e:
            print(f"❌ 创建文件模型信息失败 {file_path}: {e}")
            # 返回基本信息
            return ModelInfo(
                name=model_name,
                path=str(file_path),
                relative_path=str(file_path.relative_to(self.models_dir)),
                size_bytes=0,
                modified_time=0,
                access_time=0,
                model_type='file',
                directory=parent_dir,
                extension=file_path.suffix.lower(),
                confidence_factors={}
            )

    def _create_directory_model_info(self, dir_path: Path, model_name: str, parent_dir: str) -> ModelInfo:
        """
        创建目录模型信息

        Args:
            dir_path: 目录路径
            model_name: 模型名称
            parent_dir: 父目录名称

        Returns:
            ModelInfo: 模型信息对象
        """
        try:
            # 计算目录总大小、最新修改时间和最新访问时间
            total_size = 0
            latest_mtime = 0
            latest_atime = 0
            file_count = 0

            for item in dir_path.rglob('*'):
                if item.is_file():
                    try:
                        stat = item.stat()
                        total_size += stat.st_size
                        latest_mtime = max(latest_mtime, stat.st_mtime)
                        latest_atime = max(latest_atime, stat.st_atime)
                        file_count += 1
                    except Exception:
                        continue

            return ModelInfo(
                name=model_name,
                path=str(dir_path),
                relative_path=str(dir_path.relative_to(self.models_dir)),
                size_bytes=total_size,
                modified_time=latest_mtime,
                access_time=latest_atime,
                model_type='directory',
                directory=parent_dir,
                extension='',
                confidence_factors={
                    'total_size': total_size,
                    'file_count': file_count,
                    'last_modified': latest_mtime,
                    'last_accessed': latest_atime,
                    'directory_depth': len(dir_path.relative_to(self.models_dir).parts)
                }
            )
        except Exception as e:
            print(f"❌ 创建目录模型信息失败 {dir_path}: {e}")
            # 返回基本信息
            return ModelInfo(
                name=model_name,
                path=str(dir_path),
                relative_path=str(dir_path.relative_to(self.models_dir)),
                size_bytes=0,
                modified_time=0,
                access_time=0,
                model_type='directory',
                directory=parent_dir,
                extension='',
                confidence_factors={}
            )


def identify_model_type(path: Path) -> Tuple[str, str]:
    """
    识别模型类型和名称

    Cases:
    1. models/clip/model.safetensors → ('model', 'file')
    2. models/clip/siglip-so400m/ → ('siglip-so400m', 'directory')
    3. models/checkpoints/category/model.ckpt → ('model', 'file')
    4. models/diffusers/stable-diffusion-v1-5/ → ('stable-diffusion-v1-5', 'directory')

    Args:
        path: 模型路径

    Returns:
        Tuple[str, str]: (模型名称, 模型类型)
    """
    if path.is_file() and is_model_file(path):
        return path.stem, 'file'
    elif path.is_dir():
        # 检查目录是否包含模型文件（避免循环导入）
        try:
            for item in path.iterdir():
                if item.is_file() and is_model_file(item):
                    return path.name, 'directory'
                # 检查一级子目录
                elif item.is_dir() and not item.name.startswith('.'):
                    for subitem in item.iterdir():
                        if subitem.is_file() and is_model_file(subitem):
                            return path.name, 'directory'
        except Exception:
            pass

    return '', 'unknown'
