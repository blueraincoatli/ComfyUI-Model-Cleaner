"""
Workflow Analyzer - Analyzes ComfyUI workflows and model usage
"""

import json
import re
import ast
import importlib.util
from pathlib import Path
from typing import Dict, List, Set, Any, Optional

from .utils import get_comfy_dir, safe_file_operation


class WorkflowAnalyzer:
    """
    Analyzes ComfyUI workflows to identify model usage patterns.
    """

    def __init__(self):
        self.comfy_dir = get_comfy_dir()
        self.workflow_cache = {}
        self.active_nodes_cache = None

    def analyze_workflows(self) -> Dict[str, Any]:
        """
        Analyze all workflow files to identify model usage.

        Returns:
            Dict containing workflow analysis results
        """
        workflow_files = self._find_workflow_files()
        referenced_models = set()
        workflow_count = 0
        valid_workflows = 0

        for workflow_file in workflow_files:
            try:
                models_in_workflow = self._analyze_single_workflow(workflow_file)
                if models_in_workflow:  # Only count if we found models
                    valid_workflows += 1
                    referenced_models.update(models_in_workflow)
                workflow_count += 1
            except Exception as e:
                print(f"分析工作流文件失败 {workflow_file}: {e}")
                continue

        return {
            'workflow_count': workflow_count,
            'valid_workflows': valid_workflows,
            'workflow_files': [str(f) for f in workflow_files],
            'referenced_models': len(referenced_models),
            'model_references': list(referenced_models)
        }

    def analyze_workflows_safe(self, max_files: int = 100, timeout_seconds: int = 30) -> Dict[str, Any]:
        """
        安全的工作流分析，带有文件数量限制和超时控制。

        Args:
            max_files: 最大分析文件数量
            timeout_seconds: 超时时间（秒）

        Returns:
            Dict containing workflow analysis results
        """
        import time
        start_time = time.time()

        print(f"开始安全工作流分析（最多 {max_files} 个文件，超时 {timeout_seconds} 秒）...")

        workflow_files = self._find_workflow_files_safe(max_files)
        referenced_models = set()
        workflow_count = 0
        valid_workflows = 0

        for workflow_file in workflow_files:
            # 检查超时
            if time.time() - start_time > timeout_seconds:
                print(f"⚠️  工作流分析超时，已分析 {workflow_count} 个文件")
                break

            try:
                models_in_workflow = self._analyze_single_workflow(workflow_file)
                if models_in_workflow:  # Only count if we found models
                    valid_workflows += 1
                    referenced_models.update(models_in_workflow)
                workflow_count += 1

                # 每10个文件显示一次进度
                if workflow_count % 10 == 0:
                    print(f"  已分析 {workflow_count} 个工作流文件...")

            except Exception as e:
                print(f"分析工作流文件失败 {workflow_file}: {e}")
                continue

        print(f"工作流分析完成：{workflow_count} 个文件，{valid_workflows} 个有效，{len(referenced_models)} 个模型引用")

        return {
            'workflow_count': workflow_count,
            'valid_workflows': valid_workflows,
            'workflow_files': [str(f) for f in workflow_files],
            'referenced_models': len(referenced_models),
            'model_references': list(referenced_models)
        }

    def _find_workflow_files(self) -> List[Path]:
        """
        Find all workflow files in the ComfyUI directory.

        Returns:
            List of workflow file paths
        """
        workflow_files = []

        # Common locations for workflow files
        search_dirs = [
            self.comfy_dir,
            self.comfy_dir / "user",
            self.comfy_dir / "workflows",
            self.comfy_dir / "examples",
            self.comfy_dir / "input",
            self.comfy_dir / "output"
        ]

        # Add any additional directories that exist (SAFE VERSION)
        for search_dir in search_dirs:
            if search_dir.exists() and search_dir.is_dir():
                try:
                    # 只搜索直接的JSON文件，避免深度递归
                    for json_file in search_dir.glob('*.json'):
                        # Skip very large files (likely not workflows)
                        if json_file.stat().st_size > 5 * 1024 * 1024:  # 5MB limit
                            continue

                        # Quick check if it looks like a ComfyUI workflow
                        if self._is_likely_workflow(json_file):
                            workflow_files.append(json_file)

                    # 搜索一级子目录（限制深度）
                    for subdir in search_dir.glob('*/'):
                        if subdir.is_dir() and not subdir.name.startswith('.'):
                            for json_file in subdir.glob('*.json'):
                                if json_file.stat().st_size > 5 * 1024 * 1024:
                                    continue
                                if self._is_likely_workflow(json_file):
                                    workflow_files.append(json_file)

                except Exception as e:
                    print(f"搜索工作流文件时出错 {search_dir}: {e}")
                    continue

        return workflow_files

    def _find_workflow_files_safe(self, max_files: int = 100) -> List[Path]:
        """
        安全地查找工作流文件，限制数量避免卡住。

        Args:
            max_files: 最大文件数量

        Returns:
            List of workflow file paths (limited)
        """
        workflow_files = []

        # 优先搜索最可能包含工作流的目录
        priority_dirs = [
            self.comfy_dir / "user",
            self.comfy_dir / "workflows",
            self.comfy_dir / "input"
        ]

        # 次要搜索目录
        secondary_dirs = [
            self.comfy_dir / "examples",
            self.comfy_dir / "output",
            self.comfy_dir  # 根目录最后搜索
        ]

        # 先搜索优先目录
        for search_dir in priority_dirs:
            if len(workflow_files) >= max_files:
                break

            if search_dir.exists() and search_dir.is_dir():
                try:
                    # 限制搜索深度，避免递归太深
                    for json_file in search_dir.glob('*.json'):
                        if len(workflow_files) >= max_files:
                            break

                        # 跳过很大的文件
                        if json_file.stat().st_size > 5 * 1024 * 1024:  # 5MB limit
                            continue

                        if self._is_likely_workflow(json_file):
                            workflow_files.append(json_file)

                    # 如果还没达到限制，搜索一级子目录
                    if len(workflow_files) < max_files:
                        for subdir in search_dir.iterdir():
                            if len(workflow_files) >= max_files:
                                break

                            if subdir.is_dir() and not subdir.name.startswith('.'):
                                for json_file in subdir.glob('*.json'):
                                    if len(workflow_files) >= max_files:
                                        break

                                    if json_file.stat().st_size > 5 * 1024 * 1024:
                                        continue

                                    if self._is_likely_workflow(json_file):
                                        workflow_files.append(json_file)

                except Exception as e:
                    print(f"搜索工作流文件时出错 {search_dir}: {e}")
                    continue

        # 如果还没找到足够的文件，搜索次要目录
        if len(workflow_files) < max_files:
            for search_dir in secondary_dirs:
                if len(workflow_files) >= max_files:
                    break

                if search_dir.exists() and search_dir.is_dir():
                    try:
                        # 只搜索直接的json文件，不递归
                        for json_file in search_dir.glob('*.json'):
                            if len(workflow_files) >= max_files:
                                break

                            if json_file.stat().st_size > 5 * 1024 * 1024:
                                continue

                            if self._is_likely_workflow(json_file):
                                workflow_files.append(json_file)

                    except Exception as e:
                        print(f"搜索工作流文件时出错 {search_dir}: {e}")
                        continue

        print(f"找到 {len(workflow_files)} 个工作流文件（限制 {max_files} 个）")
        return workflow_files

    @safe_file_operation
    def _is_likely_workflow(self, json_file: Path) -> bool:
        """
        Quick check if a JSON file is likely a ComfyUI workflow.

        Args:
            json_file: Path to JSON file

        Returns:
            bool: True if likely a workflow file
        """
        try:
            with open(json_file, 'r', encoding='utf-8', errors='ignore') as f:
                # Read first few KB to check structure
                content = f.read(4096)

                # Look for ComfyUI workflow indicators
                workflow_indicators = [
                    '"class_type"',
                    '"inputs"',
                    '"outputs"',
                    'CheckpointLoaderSimple',
                    'LoraLoader',
                    'VAELoader',
                    'CLIPTextEncode'
                ]

                return any(indicator in content for indicator in workflow_indicators)

        except Exception:
            return False

    @safe_file_operation
    def _analyze_single_workflow(self, workflow_file: Path) -> Set[str]:
        """
        Analyze a single workflow file for model references.

        Args:
            workflow_file: Path to workflow file

        Returns:
            Set of model names/paths referenced in the workflow
        """
        referenced_models = set()

        try:
            with open(workflow_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            # First try to parse as JSON
            try:
                workflow_data = json.loads(content)
                referenced_models.update(self._extract_model_references(workflow_data))
            except json.JSONDecodeError:
                # If JSON parsing fails, try text-based extraction
                referenced_models.update(self._extract_models_from_text(content))

        except Exception as e:
            print(f"分析工作流失败 {workflow_file}: {e}")

        return referenced_models

    def _extract_models_from_text(self, content: str) -> Set[str]:
        """
        Extract model references from text content using regex patterns.

        Args:
            content: Text content to search

        Returns:
            Set of model names found
        """
        model_names = set()

        # Common model file extensions
        model_extensions = ['.ckpt', '.safetensors', '.pt', '.pth', '.bin', '.onnx']

        # Pattern to match model file references
        for ext in model_extensions:
            # Look for quoted strings containing model files
            pattern = rf'["\']([^"\']*{re.escape(ext)})["\']'
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                # Extract just the filename
                model_name = Path(match).name
                if model_name:
                    model_names.add(model_name)

        # Also look for common model field patterns
        field_patterns = [
            r'"ckpt_name":\s*"([^"]+)"',
            r'"model_name":\s*"([^"]+)"',
            r'"lora_name":\s*"([^"]+)"',
            r'"vae_name":\s*"([^"]+)"',
            r'"checkpoint_name":\s*"([^"]+)"'
        ]

        for pattern in field_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                if match.strip():
                    model_names.add(match.strip())

        return model_names

    def _extract_model_references(self, workflow_data: Any) -> Set[str]:
        """
        Extract model references from workflow data structure.

        Args:
            workflow_data: Parsed workflow JSON data

        Returns:
            Set of model references found
        """
        model_references = set()

        # Handle different workflow formats
        if isinstance(workflow_data, dict):
            # Check for node-based workflow format
            for key, value in workflow_data.items():
                if isinstance(value, dict):
                    # Look for model loader nodes
                    class_type = value.get('class_type', '')
                    inputs = value.get('inputs', {})

                    if self._is_model_loader_node(class_type):
                        models = self._extract_models_from_inputs(inputs, class_type)
                        model_references.update(models)

                    # Recursively search in nested structures
                    model_references.update(self._extract_model_references(value))

                elif isinstance(value, (list, tuple)):
                    for item in value:
                        model_references.update(self._extract_model_references(item))

        elif isinstance(workflow_data, (list, tuple)):
            for item in workflow_data:
                model_references.update(self._extract_model_references(item))

        return model_references

    def _is_model_loader_node(self, class_type: str) -> bool:
        """
        Check if a node class type is a model loader.

        Args:
            class_type: Node class type string

        Returns:
            bool: True if it's a model loader node
        """
        model_loader_types = [
            'CheckpointLoaderSimple',
            'CheckpointLoader',
            'LoraLoader',
            'LoraLoaderModelOnly',
            'VAELoader',
            'CLIPLoader',
            'UNETLoader',
            'ControlNetLoader',
            'UpscaleModelLoader',
            'StyleModelLoader',
            'DiffusersLoader'
        ]

        return class_type in model_loader_types or 'Loader' in class_type

    def _extract_models_from_inputs(self, inputs: Dict[str, Any], class_type: str) -> Set[str]:
        """
        Extract model names from node inputs.

        Args:
            inputs: Node inputs dictionary
            class_type: Node class type

        Returns:
            Set of model names found in inputs
        """
        model_names = set()

        # Common input field names for models
        model_input_fields = [
            'ckpt_name',
            'checkpoint_name',
            'model_name',
            'lora_name',
            'vae_name',
            'clip_name',
            'unet_name',
            'control_net_name',
            'upscale_model_name',
            'style_model_name'
        ]

        for field_name, field_value in inputs.items():
            if field_name in model_input_fields and isinstance(field_value, str):
                if field_value.strip():  # Non-empty string
                    model_names.add(field_value.strip())

            # Also check for model file extensions in any string field
            elif isinstance(field_value, str):
                if any(ext in field_value for ext in ['.ckpt', '.safetensors', '.pt', '.pth', '.bin']):
                    # Extract filename from path
                    model_path = Path(field_value)
                    model_names.add(model_path.name)

        return model_names

    def find_models_in_custom_nodes(self) -> Dict[str, List[str]]:
        """
        Analyze custom nodes to find model dependencies.

        Returns:
            Dict mapping custom node names to their model dependencies
        """
        custom_nodes_dir = self.comfy_dir / "custom_nodes"
        node_models = {}

        if not custom_nodes_dir.exists():
            return node_models

        for node_dir in custom_nodes_dir.iterdir():
            if node_dir.is_dir() and not node_dir.name.startswith('.'):
                try:
                    models = self._analyze_custom_node(node_dir)
                    if models:
                        node_models[node_dir.name] = models
                except Exception as e:
                    print(f"分析自定义节点失败 {node_dir.name}: {e}")
                    continue

        return node_models

    def _analyze_custom_node(self, node_dir: Path) -> List[str]:
        """
        Analyze a single custom node directory for model dependencies.

        Args:
            node_dir: Path to custom node directory

        Returns:
            List of model files this node might use
        """
        model_references = []

        # Look for Python files that might reference models
        for py_file in node_dir.rglob('*.py'):
            try:
                with open(py_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

                    # Look for model file references in code
                    model_patterns = [
                        r'["\']([^"\']*\.(?:ckpt|safetensors|pt|pth|bin))["\']',
                        r'model[_\s]*(?:path|file|name)[_\s]*=.*?["\']([^"\']+)["\']',
                        r'checkpoint[_\s]*(?:path|file|name)[_\s]*=.*?["\']([^"\']+)["\']'
                    ]

                    for pattern in model_patterns:
                        matches = re.findall(pattern, content, re.IGNORECASE)
                        for match in matches:
                            if match and not match.startswith('http'):
                                model_references.append(Path(match).name)

            except Exception:
                continue

        return list(set(model_references))  # Remove duplicates

    def get_active_custom_nodes(self) -> Set[str]:
        """
        获取激活的自定义节点列表，优先从ComfyUI Manager配置读取。

        Returns:
            Set[str]: 激活的自定义节点目录名集合
        """
        if self.active_nodes_cache is not None:
            return self.active_nodes_cache

        active_nodes = set()

        # 1. 尝试从ComfyUI Manager配置读取
        manager_config = self._read_comfyui_manager_config()
        if manager_config:
            active_nodes.update(manager_config.get('active_nodes', []))
            print(f"从ComfyUI Manager配置读取到 {len(active_nodes)} 个激活节点")

        # 2. 如果没有Manager配置，则检查所有存在的自定义节点
        if not active_nodes:
            active_nodes = self._detect_installed_custom_nodes()
            print(f"检测到 {len(active_nodes)} 个已安装的自定义节点")

        self.active_nodes_cache = active_nodes
        return active_nodes

    def _read_comfyui_manager_config(self) -> Optional[Dict]:
        """
        读取ComfyUI Manager的配置文件。

        Returns:
            Optional[Dict]: 配置数据，如果读取失败则返回None
        """
        # ComfyUI Manager可能的配置文件位置
        config_paths = [
            self.comfy_dir / "custom_nodes" / "ComfyUI-Manager" / "config.json",
            self.comfy_dir / "custom_nodes" / "ComfyUI-Manager" / "startup-scripts" / "config.json",
            self.comfy_dir / "manager_config.json",
            self.comfy_dir / "config" / "manager.json"
        ]

        for config_path in config_paths:
            if config_path.exists():
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                        print(f"找到ComfyUI Manager配置: {config_path}")
                        return config
                except Exception as e:
                    print(f"读取配置文件失败 {config_path}: {e}")
                    continue

        return None

    def _detect_installed_custom_nodes(self) -> Set[str]:
        """
        检测所有已安装的自定义节点。

        Returns:
            Set[str]: 已安装的自定义节点目录名集合
        """
        custom_nodes_dir = self.comfy_dir / "custom_nodes"
        installed_nodes = set()

        if not custom_nodes_dir.exists():
            return installed_nodes

        for node_dir in custom_nodes_dir.iterdir():
            if node_dir.is_dir() and not node_dir.name.startswith('.'):
                # 检查是否包含Python文件或__init__.py
                if self._is_valid_custom_node(node_dir):
                    installed_nodes.add(node_dir.name)

        return installed_nodes

    def _is_valid_custom_node(self, node_dir: Path) -> bool:
        """
        检查目录是否是有效的自定义节点。

        Args:
            node_dir: 节点目录路径

        Returns:
            bool: 是否是有效的自定义节点
        """
        # 检查是否有Python文件
        has_python_files = any(node_dir.glob('*.py'))

        # 检查是否有__init__.py
        has_init = (node_dir / '__init__.py').exists()

        # 检查是否有节点定义文件
        common_node_files = ['nodes.py', 'node.py', '__init__.py']
        has_node_files = any((node_dir / filename).exists() for filename in common_node_files)

        return has_python_files or has_init or has_node_files

    def find_models_in_active_nodes(self, max_nodes: int = 20, timeout_per_node: int = 10) -> Dict[str, List[str]]:
        """
        分析激活的自定义节点以找到模型依赖。

        Args:
            max_nodes: 最大分析节点数量，避免超时
            timeout_per_node: 每个节点的最大分析时间（秒）

        Returns:
            Dict[str, List[str]]: 激活节点名称到其模型依赖的映射
        """
        active_nodes = self.get_active_custom_nodes()
        custom_nodes_dir = self.comfy_dir / "custom_nodes"
        node_models = {}

        if not custom_nodes_dir.exists():
            return node_models

        # 限制分析的节点数量
        nodes_to_analyze = list(active_nodes)[:max_nodes]
        if len(active_nodes) > max_nodes:
            print(f"⚠️  限制分析前 {max_nodes} 个节点（总共 {len(active_nodes)} 个）以避免超时")

        print(f"分析 {len(nodes_to_analyze)} 个激活的自定义节点...")

        import time
        for i, node_name in enumerate(nodes_to_analyze):
            print(f"  [{i+1}/{len(nodes_to_analyze)}] 分析 {node_name}...")

            node_dir = custom_nodes_dir / node_name
            if node_dir.exists() and node_dir.is_dir():
                try:
                    start_time = time.time()
                    models = self._analyze_custom_node_enhanced(node_dir, timeout=timeout_per_node)
                    elapsed = time.time() - start_time

                    if models:
                        node_models[node_name] = models
                        print(f"    ✅ 发现 {len(models)} 个模型引用 ({elapsed:.1f}s)")
                    else:
                        print(f"    ℹ️  无模型引用 ({elapsed:.1f}s)")

                except Exception as e:
                    print(f"    ❌ 分析失败: {e}")
                    continue

        return node_models

    def _analyze_custom_node_enhanced(self, node_dir: Path, timeout: int = 10) -> List[str]:
        """
        增强的自定义节点分析，包括代码解析和配置文件检查。

        Args:
            node_dir: 节点目录路径
            timeout: 超时时间（秒），避免单个节点分析时间过长

        Returns:
            List[str]: 该节点可能使用的模型文件列表
        """
        model_references = []

        # 1. 分析Python代码中的模型引用
        model_references.extend(self._analyze_python_code_for_models(node_dir))

        # 2. 检查配置文件中的模型引用
        model_references.extend(self._analyze_config_files_for_models(node_dir))

        # 3. 检查requirements或依赖文件
        model_references.extend(self._analyze_dependency_files_for_models(node_dir))

        return list(set(model_references))  # 去重

    def _analyze_python_code_for_models(self, node_dir: Path) -> List[str]:
        """
        分析Python代码中的模型引用。

        Args:
            node_dir: 节点目录路径

        Returns:
            List[str]: 发现的模型引用
        """
        model_references = []

        for py_file in node_dir.rglob('*.py'):
            try:
                with open(py_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

                # 增强的模型文件匹配模式
                model_patterns = [
                    # 直接的模型文件引用
                    r'["\']([^"\']*\.(?:ckpt|safetensors|pt|pth|bin|onnx))["\']',
                    # 模型路径变量
                    r'(?:model|checkpoint|ckpt)[_\s]*(?:path|file|name)[_\s]*=.*?["\']([^"\']+)["\']',
                    # 模型加载函数调用
                    r'(?:load_model|load_checkpoint|from_pretrained)\([^)]*["\']([^"\']+)["\']',
                    # HuggingFace模型引用
                    r'["\']([^"\']*(?:huggingface|hf)\.co/[^"\']+)["\']',
                    # 常见的模型目录引用
                    r'["\'](?:models?/|checkpoints?/|loras?/|embeddings?/)([^"\']+)["\']'
                ]

                for pattern in model_patterns:
                    matches = re.findall(pattern, content, re.IGNORECASE)
                    for match in matches:
                        if match and not match.startswith('http') and not match.startswith('//'):
                            # 提取文件名
                            model_name = Path(match).name
                            if model_name and len(model_name) > 3:  # 过滤太短的匹配
                                model_references.append(model_name)

            except Exception:
                continue

        return model_references

    def _analyze_config_files_for_models(self, node_dir: Path) -> List[str]:
        """
        分析配置文件中的模型引用。

        Args:
            node_dir: 节点目录路径

        Returns:
            List[str]: 发现的模型引用
        """
        model_references = []

        # 常见的配置文件
        config_files = [
            '*.json', '*.yaml', '*.yml', '*.toml', '*.ini', '*.cfg'
        ]

        for pattern in config_files:
            for config_file in node_dir.rglob(pattern):
                try:
                    with open(config_file, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()

                    # 在配置文件中查找模型引用
                    model_extensions = ['.ckpt', '.safetensors', '.pt', '.pth', '.bin', '.onnx']
                    for ext in model_extensions:
                        pattern = rf'["\']([^"\']*{re.escape(ext)})["\']'
                        matches = re.findall(pattern, content, re.IGNORECASE)
                        for match in matches:
                            model_name = Path(match).name
                            if model_name:
                                model_references.append(model_name)

                except Exception:
                    continue

        return model_references

    def _analyze_dependency_files_for_models(self, node_dir: Path) -> List[str]:
        """
        分析依赖文件中的模型引用。

        Args:
            node_dir: 节点目录路径

        Returns:
            List[str]: 发现的模型引用
        """
        model_references = []

        # 检查requirements.txt等依赖文件
        dependency_files = ['requirements.txt', 'install.py', 'setup.py']

        for dep_file_name in dependency_files:
            dep_file = node_dir / dep_file_name
            if dep_file.exists():
                try:
                    with open(dep_file, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()

                    # 查找可能的模型下载URL或引用
                    url_patterns = [
                        r'https?://[^"\s]+\.(?:ckpt|safetensors|pt|pth|bin)',
                        r'huggingface\.co/[^"\s]+',
                        r'civitai\.com/[^"\s]+'
                    ]

                    for pattern in url_patterns:
                        matches = re.findall(pattern, content, re.IGNORECASE)
                        for match in matches:
                            # 从URL中提取可能的模型名
                            model_name = Path(match).name
                            if model_name and any(ext in model_name for ext in ['.ckpt', '.safetensors', '.pt', '.pth', '.bin']):
                                model_references.append(model_name)

                except Exception:
                    continue

        return model_references

    def comprehensive_model_analysis(self, max_nodes: int = 20, timeout_per_node: int = 10) -> Dict[str, Any]:
        """
        综合分析模型使用情况，结合工作流分析和激活节点分析。

        Args:
            max_nodes: 最大分析节点数量
            timeout_per_node: 每个节点的最大分析时间

        Returns:
            Dict[str, Any]: 综合分析结果
        """
        print("开始综合模型使用分析...")

        # 1. 工作流分析
        print("1. 分析工作流文件...")
        workflow_analysis = self.analyze_workflows()
        workflow_models = set(workflow_analysis.get('model_references', []))

        # 2. 激活节点分析
        print("2. 分析激活的自定义节点...")
        active_node_analysis = self.find_models_in_active_nodes(
            max_nodes=max_nodes,
            timeout_per_node=timeout_per_node
        )
        node_models = set()
        for node_name, models in active_node_analysis.items():
            node_models.update(models)

        # 3. 合并结果
        all_referenced_models = workflow_models.union(node_models)

        # 4. 分析模型来源
        model_sources = {}
        for model in all_referenced_models:
            sources = []
            if model in workflow_models:
                sources.append('workflow')
            if model in node_models:
                sources.append('active_nodes')
            model_sources[model] = sources

        print(f"综合分析完成:")
        print(f"  工作流引用的模型: {len(workflow_models)}")
        print(f"  激活节点引用的模型: {len(node_models)}")
        print(f"  总计唯一模型: {len(all_referenced_models)}")

        return {
            'workflow_analysis': workflow_analysis,
            'active_node_analysis': active_node_analysis,
            'workflow_models': list(workflow_models),
            'node_models': list(node_models),
            'all_referenced_models': list(all_referenced_models),
            'model_sources': model_sources,
            'summary': {
                'workflow_model_count': len(workflow_models),
                'node_model_count': len(node_models),
                'total_unique_models': len(all_referenced_models),
                'active_nodes_count': len(active_node_analysis)
            }
        }