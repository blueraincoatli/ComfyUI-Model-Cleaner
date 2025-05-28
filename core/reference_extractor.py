"""
引用提取引擎 - ComfyModelCleaner V2.0

多源引用检测：从Python文件、配置文件、示例json、README等提取模型引用。
"""

import re
import json
import yaml
from pathlib import Path
from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass

from .utils import get_custom_nodes_dir, safe_file_operation


@dataclass
class ModelReference:
    """模型引用信息"""
    model_name: str
    source_file: str
    source_type: str  # 'python', 'config', 'workflow', 'documentation'
    line_number: Optional[int]
    context: str
    confidence: float  # 0.0 - 1.0


# 引用模式定义
REFERENCE_PATTERNS = {
    'exact_file_reference': [
        r'["\']([^"\']*\.(?:safetensors|ckpt|pt|pth|bin|onnx))["\']',
        r'load_checkpoint\(["\']([^"\']+)["\']',
        r'model_path\s*=\s*["\']([^"\']+)["\']',
    ],
    'directory_reference': [
        r'["\']([^"\']*siglip[^"\']*)["\']',
        r'models[/\\]([a-zA-Z_][a-zA-Z0-9_-]+)',
        r'folder_paths\.get_folder_paths\(["\']([^"\']+)["\']',
    ],
    'model_name_patterns': [
        r'model_name\s*=\s*["\']([^"\']+)["\']',
        r'default_model["\']?\s*:\s*["\']([^"\']+)["\']',
        r'ckpt_name["\']?\s*:\s*["\']([^"\']+)["\']',
        r'checkpoint["\']?\s*:\s*["\']([^"\']+)["\']',
    ],
    'segformer_specific': [
        # 专门针对segformer模型的模式
        r'["\']([^"\']*segformer[^"\']*)["\']',
        r'segformer[_-]?([a-zA-Z0-9_-]+)',
        r'model[_-]?type["\']?\s*:\s*["\']([^"\']*segformer[^"\']*)["\']',
        r'model[_-]?id["\']?\s*:\s*["\']([^"\']*segformer[^"\']*)["\']',
    ],
    'model_identifier_patterns': [
        # 更精确的模型标识符模式 - 只匹配明确的模型相关上下文
        r'model[_-]?(?:type|id|name)["\']?\s*:\s*["\']([^"\']+)["\']',
        r'default["\']?\s*:\s*["\']([a-zA-Z][a-zA-Z0-9_-]+\.(?:safetensors|ckpt|pt|pth|bin|onnx))["\']',
        r'(?:checkpoint|ckpt|lora|vae|embedding)[_-]?(?:file|path|name)["\']?\s*:\s*["\']([^"\']+)["\']',
    ]
}


class ReferenceExtractor:
    """引用提取引擎"""

    def __init__(self):
        self.custom_nodes_dir = get_custom_nodes_dir()
        self.extracted_references = []

    def extract_all_references(self, node_dirs: List[Path]) -> Dict[str, List[ModelReference]]:
        """
        从所有指定节点目录提取引用

        Args:
            node_dirs: 节点目录列表

        Returns:
            Dict[str, List[ModelReference]]: 按节点名分组的引用列表
        """
        print("🔍 开始提取模型引用...")

        all_references = {}

        for node_dir in node_dirs:
            # 跳过ComfyModelCleaner自身，避免自引用
            if 'ComfyModelCleaner' in node_dir.name:
                print(f"  跳过自身节点: {node_dir.name}")
                continue

            print(f"  分析节点: {node_dir.name}")

            node_references = []

            # 从Python文件提取
            python_refs = self.extract_from_python_files(node_dir)
            node_references.extend(python_refs)

            # 从配置文件提取
            config_refs = self.extract_from_config_files(node_dir)
            node_references.extend(config_refs)

            # 从示例工作流提取
            workflow_refs = self.extract_from_example_workflows(node_dir)
            node_references.extend(workflow_refs)

            # 从文档提取
            doc_refs = self.extract_from_documentation(node_dir)
            node_references.extend(doc_refs)

            if node_references:
                all_references[node_dir.name] = node_references
                print(f"    发现 {len(node_references)} 个引用")
            else:
                print(f"    无引用发现")

        print(f"✅ 引用提取完成，共 {sum(len(refs) for refs in all_references.values())} 个引用")
        return all_references

    def extract_from_python_files(self, node_dir: Path) -> List[ModelReference]:
        """
        从Python文件提取模型引用

        Args:
            node_dir: 节点目录

        Returns:
            List[ModelReference]: 引用列表
        """
        references = []

        # 查找Python文件
        python_files = list(node_dir.rglob('*.py'))[:20]  # 限制文件数量

        for py_file in python_files:
            try:
                file_refs = self._extract_from_python_file(py_file)
                references.extend(file_refs)
            except Exception as e:
                print(f"    ❌ 分析Python文件失败 {py_file.name}: {e}")
                continue

        return references

    @safe_file_operation
    def _extract_from_python_file(self, py_file: Path) -> List[ModelReference]:
        """从单个Python文件提取引用"""
        references = []

        with open(py_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        for line_num, line in enumerate(lines, 1):
            line_refs = self._extract_references_from_line(
                line, str(py_file), 'python', line_num
            )
            references.extend(line_refs)

        return references

    def extract_from_config_files(self, node_dir: Path) -> List[ModelReference]:
        """
        从配置文件提取引用

        Args:
            node_dir: 节点目录

        Returns:
            List[ModelReference]: 引用列表
        """
        references = []

        # 配置文件模式
        config_patterns = ['*.json', '*.yaml', '*.yml', '*.toml', '*.cfg', '*.ini']

        for pattern in config_patterns:
            for config_file in node_dir.glob(pattern):
                try:
                    file_refs = self._extract_from_config_file(config_file)
                    references.extend(file_refs)
                except Exception as e:
                    print(f"    ❌ 分析配置文件失败 {config_file.name}: {e}")
                    continue

        return references

    @safe_file_operation
    def _extract_from_config_file(self, config_file: Path) -> List[ModelReference]:
        """从单个配置文件提取引用"""
        references = []

        with open(config_file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        # 尝试解析为JSON/YAML
        try:
            if config_file.suffix.lower() == '.json':
                data = json.loads(content)
                refs = self._extract_from_structured_data(data, str(config_file), 'config')
                references.extend(refs)
            elif config_file.suffix.lower() in ['.yaml', '.yml']:
                data = yaml.safe_load(content)
                refs = self._extract_from_structured_data(data, str(config_file), 'config')
                references.extend(refs)
        except Exception:
            pass

        # 文本模式提取
        lines = content.split('\n')
        for line_num, line in enumerate(lines, 1):
            line_refs = self._extract_references_from_line(
                line, str(config_file), 'config', line_num
            )
            references.extend(line_refs)

        return references

    def extract_from_example_workflows(self, node_dir: Path) -> List[ModelReference]:
        """
        从示例工作流提取引用

        Args:
            node_dir: 节点目录

        Returns:
            List[ModelReference]: 引用列表
        """
        references = []

        # 查找示例工作流文件
        workflow_patterns = ['*example*.json', '*workflow*.json', '*demo*.json']

        for pattern in workflow_patterns:
            for workflow_file in node_dir.rglob(pattern):
                try:
                    file_refs = self._extract_from_workflow_file(workflow_file)
                    references.extend(file_refs)
                except Exception as e:
                    print(f"    ❌ 分析工作流文件失败 {workflow_file.name}: {e}")
                    continue

        return references

    @safe_file_operation
    def _extract_from_workflow_file(self, workflow_file: Path) -> List[ModelReference]:
        """从工作流文件提取引用"""
        references = []

        with open(workflow_file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        try:
            data = json.loads(content)
            refs = self._extract_from_structured_data(data, str(workflow_file), 'workflow')
            references.extend(refs)
        except json.JSONDecodeError:
            # 文本模式提取
            lines = content.split('\n')
            for line_num, line in enumerate(lines, 1):
                line_refs = self._extract_references_from_line(
                    line, str(workflow_file), 'workflow', line_num
                )
                references.extend(line_refs)

        return references

    def extract_from_documentation(self, node_dir: Path) -> List[ModelReference]:
        """
        从README等文档提取引用

        Args:
            node_dir: 节点目录

        Returns:
            List[ModelReference]: 引用列表
        """
        references = []

        # 文档文件模式
        doc_patterns = ['README*', '*.md', '*.rst', '*.txt', 'INSTALL*', 'SETUP*']

        for pattern in doc_patterns:
            for doc_file in node_dir.glob(pattern):
                try:
                    file_refs = self._extract_from_doc_file(doc_file)
                    references.extend(file_refs)
                except Exception as e:
                    print(f"    ❌ 分析文档文件失败 {doc_file.name}: {e}")
                    continue

        return references

    @safe_file_operation
    def _extract_from_doc_file(self, doc_file: Path) -> List[ModelReference]:
        """从文档文件提取引用"""
        references = []

        with open(doc_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        for line_num, line in enumerate(lines, 1):
            line_refs = self._extract_references_from_line(
                line, str(doc_file), 'documentation', line_num
            )
            references.extend(line_refs)

        return references

    def _extract_references_from_line(self, line: str, source_file: str,
                                     source_type: str, line_number: int) -> List[ModelReference]:
        """
        从单行文本提取模型引用

        Args:
            line: 文本行
            source_file: 源文件路径
            source_type: 源文件类型
            line_number: 行号

        Returns:
            List[ModelReference]: 引用列表
        """
        references = []
        seen_models = set()  # 避免重复提取

        # 应用所有引用模式
        for pattern_type, patterns in REFERENCE_PATTERNS.items():
            for pattern in patterns:
                matches = re.findall(pattern, line, re.IGNORECASE)
                for match in matches:
                    if match and self._is_valid_model_reference(match):
                        clean_name = self._clean_model_name(match)

                        # 避免重复提取相同的模型名
                        if clean_name in seen_models:
                            continue
                        seen_models.add(clean_name)

                        confidence = self._calculate_reference_confidence(
                            match, pattern_type, source_type
                        )

                        ref = ModelReference(
                            model_name=clean_name,
                            source_file=source_file,
                            source_type=source_type,
                            line_number=line_number,
                            context=line.strip(),
                            confidence=confidence
                        )
                        references.append(ref)

        return references

    def _extract_from_structured_data(self, data: Any, source_file: str,
                                    source_type: str) -> List[ModelReference]:
        """
        从结构化数据（JSON/YAML）提取引用

        Args:
            data: 结构化数据
            source_file: 源文件路径
            source_type: 源文件类型

        Returns:
            List[ModelReference]: 引用列表
        """
        references = []

        def extract_recursive(obj, path=""):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    current_path = f"{path}.{key}" if path else key

                    # 检查键名是否表示模型
                    if self._is_model_key(key) and isinstance(value, str):
                        if self._is_valid_model_reference(value):
                            confidence = self._calculate_reference_confidence(
                                value, 'structured_data', source_type
                            )

                            ref = ModelReference(
                                model_name=self._clean_model_name(value),
                                source_file=source_file,
                                source_type=source_type,
                                line_number=None,
                                context=f"{current_path}: {value}",
                                confidence=confidence
                            )
                            references.append(ref)

                    # 递归处理值
                    extract_recursive(value, current_path)

            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    extract_recursive(item, f"{path}[{i}]")

            elif isinstance(obj, str):
                # 检查字符串值是否包含模型引用
                # 只有在明确的模型上下文中才提取字符串值
                if (path and any(model_key in path.lower() for model_key in
                    ['model', 'checkpoint', 'ckpt', 'lora', 'vae', 'embedding']) and
                    self._is_valid_model_reference(obj)):

                    confidence = self._calculate_reference_confidence(
                        obj, 'string_value', source_type
                    )

                    ref = ModelReference(
                        model_name=self._clean_model_name(obj),
                        source_file=source_file,
                        source_type=source_type,
                        line_number=None,
                        context=f"{path}: {obj}",
                        confidence=confidence
                    )
                    references.append(ref)

        extract_recursive(data)
        return references

    def _is_valid_model_reference(self, text: str) -> bool:
        """
        判断文本是否是有效的模型引用

        Args:
            text: 文本内容

        Returns:
            bool: 是否是有效的模型引用
        """
        if not text or len(text) < 3:
            return False

        # 排除明显的非模型引用
        invalid_patterns = [
            r'^https?://',  # URL
            r'^[a-zA-Z]:\\',  # Windows路径
            r'^/[a-zA-Z]',  # Unix绝对路径
            r'^\$\{',  # 变量引用
            r'^[0-9]+$',  # 纯数字
            r'^(true|false|null|none)$',  # 布尔值和空值
        ]

        for pattern in invalid_patterns:
            if re.match(pattern, text, re.IGNORECASE):
                return False

        text_lower = text.lower()

        # 排除ComfyUI模型目录定义（这些是目录类型，不是具体的模型引用）
        comfyui_directory_types = {
            'checkpoints', 'loras', 'embeddings', 'vae', 'controlnet',
            'clip', 'unet', 'diffusers', 'upscale_models', 'gligen',
            'style_models', 'clip_vision', 'facedetection', 'facerestore_models',
            'sams', 'mmdets', 'onnx', 'custom', 'animatediff_models',
            'photomaker', 'instantid', 'ipadapter', 'layerstyle', 'hypernetworks'
        }

        if text_lower in comfyui_directory_types:
            return False

        # 检查是否包含模型文件扩展名或模型相关关键词
        model_indicators = [
            '.safetensors', '.ckpt', '.pt', '.pth', '.bin', '.onnx',
            'checkpoint', 'model', 'lora', 'embedding', 'vae',
            'segformer', 'clip', 'vit', 'sam', 'controlnet'  # 添加特定模型类型
        ]

        # 如果包含模型指示符，则认为是有效引用
        if any(indicator in text_lower for indicator in model_indicators):
            return True

        # 对于没有明显指示符的文本，检查是否符合模型名称模式
        # 模型名称通常是字母开头，包含字母、数字、下划线、连字符
        if re.match(r'^[a-zA-Z][a-zA-Z0-9_-]*$', text) and len(text) >= 5:  # 提高最小长度要求
            # 排除常见的非模型词汇（大幅扩展排除列表）
            common_words = {
                # 基础词汇
                'default', 'none', 'auto', 'true', 'false', 'yes', 'no',
                'input', 'output', 'image', 'text', 'string', 'int', 'float',
                'width', 'height', 'size', 'scale', 'step', 'steps',
                # 编程相关
                'class', 'function', 'method', 'return', 'import', 'from',
                'self', 'super', 'init', 'main', 'test', 'debug', 'error',
                'warning', 'info', 'config', 'settings', 'options', 'params',
                # UI相关
                'button', 'label', 'title', 'description', 'tooltip', 'help',
                'menu', 'dialog', 'window', 'panel', 'tab', 'page', 'view',
                'layout', 'style', 'theme', 'color', 'font', 'icon',
                # 通用属性
                'name', 'type', 'value', 'data', 'item', 'list', 'dict',
                'array', 'object', 'element', 'node', 'path', 'file',
                'folder', 'directory', 'extension', 'format', 'version',
                # ComfyUI相关但非模型
                'comfy', 'comfyui', 'workflow', 'queue', 'prompt', 'execute',
                'preview', 'progress', 'status', 'result', 'output_dir',
                # 常见的短词
                'id', 'key', 'val', 'src', 'dst', 'tmp', 'temp', 'cache',
                'log', 'msg', 'err', 'ok', 'run', 'stop', 'start', 'end'
            }
            if text_lower not in common_words:
                # 额外检查：如果长度很短且不包含模型特征，则拒绝
                if len(text) < 8 and not any(char.isdigit() for char in text):
                    return False
                return True

        return False

    def _is_model_key(self, key: str) -> bool:
        """
        判断键名是否表示模型

        Args:
            key: 键名

        Returns:
            bool: 是否是模型键
        """
        model_keys = [
            'model', 'checkpoint', 'ckpt', 'model_name', 'checkpoint_name',
            'ckpt_name', 'lora', 'lora_name', 'vae', 'vae_name',
            'embedding', 'embedding_name', 'controlnet', 'control_net_name'
        ]

        key_lower = key.lower()
        return any(model_key in key_lower for model_key in model_keys)

    def _clean_model_name(self, name: str) -> str:
        """
        清理模型名称

        Args:
            name: 原始名称

        Returns:
            str: 清理后的名称
        """
        # 移除路径部分，只保留文件名
        clean_name = Path(name).name

        # 移除常见的前缀和后缀
        clean_name = re.sub(r'^(models?[/\\])', '', clean_name, flags=re.IGNORECASE)
        clean_name = re.sub(r'\.(safetensors|ckpt|pt|pth|bin|onnx)$', '', clean_name, flags=re.IGNORECASE)

        return clean_name.strip()

    def _calculate_reference_confidence(self, reference: str, pattern_type: str,
                                      source_type: str) -> float:
        """
        计算引用的置信度

        Args:
            reference: 引用文本
            pattern_type: 模式类型
            source_type: 源文件类型

        Returns:
            float: 置信度 (0.0 - 1.0)
        """
        confidence = 0.5  # 基础置信度

        # 根据模式类型调整
        pattern_weights = {
            'exact_file_reference': 0.9,
            'directory_reference': 0.7,
            'model_name_patterns': 0.8,
            'structured_data': 0.8,
            'string_value': 0.6
        }
        confidence = pattern_weights.get(pattern_type, 0.5)

        # 根据源文件类型调整
        source_weights = {
            'python': 1.0,
            'config': 0.9,
            'workflow': 0.8,
            'documentation': 0.6
        }
        confidence *= source_weights.get(source_type, 0.7)

        # 根据引用内容调整
        if any(ext in reference.lower() for ext in ['.safetensors', '.ckpt']):
            confidence += 0.1

        if 'default' in reference.lower() or 'example' in reference.lower():
            confidence -= 0.1

        return max(0.0, min(1.0, confidence))