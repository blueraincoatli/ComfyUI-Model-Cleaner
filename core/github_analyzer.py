"""
GitHub增强分析器 - ComfyModelCleaner V2.0

可选的GitHub仓库信息获取，增强模型引用检测。
"""

import re
import json
import time
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass

from .utils import safe_file_operation


@dataclass
class GitHubRepoInfo:
    """GitHub仓库信息"""
    url: str
    name: str
    description: str
    readme_content: str
    model_references: List[str]
    last_updated: float


class GitHubCache:
    """GitHub信息缓存"""

    def __init__(self, cache_duration: int = 24*3600):  # 24小时缓存
        self.cache_duration = cache_duration
        self.cache_file = Path("github_cache.json")
        self.cache_data = self._load_cache()

    def _load_cache(self) -> Dict[str, Any]:
        """加载缓存数据"""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_cache(self):
        """保存缓存数据"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存GitHub缓存失败: {e}")

    def get_cached_info(self, repo_url: str) -> Optional[GitHubRepoInfo]:
        """获取缓存的仓库信息"""
        if repo_url not in self.cache_data:
            return None

        cached = self.cache_data[repo_url]

        # 检查是否过期
        if time.time() - cached.get('timestamp', 0) > self.cache_duration:
            del self.cache_data[repo_url]
            self._save_cache()
            return None

        try:
            return GitHubRepoInfo(
                url=cached['url'],
                name=cached['name'],
                description=cached['description'],
                readme_content=cached['readme_content'],
                model_references=cached['model_references'],
                last_updated=cached['timestamp']
            )
        except KeyError:
            return None

    def cache_info(self, repo_url: str, info: GitHubRepoInfo):
        """缓存仓库信息"""
        self.cache_data[repo_url] = {
            'url': info.url,
            'name': info.name,
            'description': info.description,
            'readme_content': info.readme_content,
            'model_references': info.model_references,
            'timestamp': time.time()
        }
        self._save_cache()


class GitHubAnalyzer:
    """GitHub分析器"""

    def __init__(self, enable_cache: bool = True):
        self.cache = GitHubCache() if enable_cache else None
        self.timeout = 10  # 请求超时时间

    def analyze_node_repositories(self, node_dirs: List[Path]) -> Dict[str, GitHubRepoInfo]:
        """
        分析节点的GitHub仓库信息

        Args:
            node_dirs: 节点目录列表

        Returns:
            Dict[str, GitHubRepoInfo]: 节点名到仓库信息的映射
        """
        print("🌐 开始GitHub仓库分析...")

        repo_infos = {}

        for node_dir in node_dirs:
            try:
                repo_url = self.extract_repo_info(node_dir)
                if repo_url:
                    print(f"  分析仓库: {node_dir.name} -> {repo_url}")

                    # 检查缓存
                    if self.cache:
                        cached_info = self.cache.get_cached_info(repo_url)
                        if cached_info:
                            repo_infos[node_dir.name] = cached_info
                            print(f"    使用缓存信息")
                            continue

                    # 获取仓库信息
                    repo_info = self.fetch_repo_info(repo_url)
                    if repo_info:
                        repo_infos[node_dir.name] = repo_info

                        # 缓存信息
                        if self.cache:
                            self.cache.cache_info(repo_url, repo_info)

                        print(f"    发现 {len(repo_info.model_references)} 个模型引用")
                    else:
                        print(f"    获取仓库信息失败")
                else:
                    print(f"  {node_dir.name}: 未找到GitHub仓库")

            except Exception as e:
                print(f"  ❌ 分析 {node_dir.name} 失败: {e}")
                continue

        print(f"✅ GitHub分析完成，分析了 {len(repo_infos)} 个仓库")
        return repo_infos

    def extract_repo_info(self, node_dir: Path) -> Optional[str]:
        """
        从节点目录提取GitHub仓库信息

        Args:
            node_dir: 节点目录

        Returns:
            Optional[str]: GitHub仓库URL
        """
        # 检查.git/config文件
        git_config = node_dir / ".git" / "config"
        if git_config.exists():
            try:
                repo_url = self._extract_from_git_config(git_config)
                if repo_url:
                    return repo_url
            except Exception:
                pass

        # 检查package.json
        package_json = node_dir / "package.json"
        if package_json.exists():
            try:
                repo_url = self._extract_from_package_json(package_json)
                if repo_url:
                    return repo_url
            except Exception:
                pass

        # 检查README文件
        readme_files = list(node_dir.glob("README*")) + list(node_dir.glob("readme*"))
        for readme_file in readme_files:
            try:
                repo_url = self._extract_from_readme(readme_file)
                if repo_url:
                    return repo_url
            except Exception:
                continue

        return None

    @safe_file_operation
    def _extract_from_git_config(self, git_config: Path) -> Optional[str]:
        """从git配置文件提取仓库URL"""
        with open(git_config, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        # 查找origin remote的URL
        patterns = [
            r'url\s*=\s*https://github\.com/([^/]+/[^/\s]+)',
            r'url\s*=\s*git@github\.com:([^/]+/[^/\s]+)\.git'
        ]

        for pattern in patterns:
            match = re.search(pattern, content)
            if match:
                repo_path = match.group(1)
                return f"https://github.com/{repo_path}"

        return None

    @safe_file_operation
    def _extract_from_package_json(self, package_json: Path) -> Optional[str]:
        """从package.json提取仓库URL"""
        with open(package_json, 'r', encoding='utf-8', errors='ignore') as f:
            data = json.load(f)

        # 检查repository字段
        repo = data.get('repository', {})
        if isinstance(repo, dict):
            url = repo.get('url', '')
        elif isinstance(repo, str):
            url = repo
        else:
            return None

        # 标准化GitHub URL
        if 'github.com' in url:
            match = re.search(r'github\.com[:/]([^/]+/[^/\s]+)', url)
            if match:
                repo_path = match.group(1).rstrip('.git')
                return f"https://github.com/{repo_path}"

        return None

    @safe_file_operation
    def _extract_from_readme(self, readme_file: Path) -> Optional[str]:
        """从README文件提取GitHub URL"""
        with open(readme_file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        # 查找GitHub链接
        patterns = [
            r'https://github\.com/([^/\s]+/[^/\s]+)',
            r'\[.*?\]\(https://github\.com/([^/\s]+/[^/\s]+)\)',
        ]

        for pattern in patterns:
            match = re.search(pattern, content)
            if match:
                repo_path = match.group(1).rstrip('.git')
                return f"https://github.com/{repo_path}"

        return None

    def fetch_repo_info(self, repo_url: str) -> Optional[GitHubRepoInfo]:
        """
        获取GitHub仓库信息

        Args:
            repo_url: 仓库URL

        Returns:
            Optional[GitHubRepoInfo]: 仓库信息
        """
        try:
            # 提取仓库路径
            match = re.search(r'github\.com/([^/]+/[^/]+)', repo_url)
            if not match:
                return None

            repo_path = match.group(1)

            # 获取README内容
            readme_url = f"https://raw.githubusercontent.com/{repo_path}/main/README.md"
            readme_content = self._fetch_url_content(readme_url)

            if not readme_content:
                # 尝试master分支
                readme_url = f"https://raw.githubusercontent.com/{repo_path}/master/README.md"
                readme_content = self._fetch_url_content(readme_url)

            if not readme_content:
                readme_content = ""

            # 提取模型引用
            model_references = self.extract_model_references_from_readme(readme_content)

            return GitHubRepoInfo(
                url=repo_url,
                name=repo_path.split('/')[-1],
                description="",  # 可以通过GitHub API获取，但需要认证
                readme_content=readme_content,
                model_references=model_references,
                last_updated=time.time()
            )

        except Exception as e:
            print(f"获取GitHub仓库信息失败 {repo_url}: {e}")
            return None

    def _fetch_url_content(self, url: str) -> Optional[str]:
        """获取URL内容"""
        try:
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'ComfyModelCleaner/2.0')

            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                content = response.read().decode('utf-8', errors='ignore')
                return content

        except Exception:
            return None

    def extract_model_references_from_readme(self, readme_content: str) -> List[str]:
        """
        从README内容提取模型引用 - 增强版

        Args:
            readme_content: README内容

        Returns:
            List[str]: 模型引用列表
        """
        model_references = []

        # 基本模型文件扩展名模式
        basic_patterns = [
            r'([a-zA-Z0-9_.-]+\.(?:safetensors|ckpt|pt|pth|bin|onnx))',
            r'models/([a-zA-Z0-9_/-]+)',
            r'download.*?([a-zA-Z0-9_.-]+\.(?:safetensors|ckpt))',
            r'place.*?in.*?models/([a-zA-Z0-9_-]+)',
        ]

        # 增强的模型名称模式 - 针对GitHub页面常见格式
        enhanced_patterns = [
            # 匹配链接中的模型名 (如 [ip-adapter_sd15.safetensors](url))
            r'\[([a-zA-Z0-9_.-]+\.(?:safetensors|ckpt|pt|pth|bin|onnx))\]',
            # 匹配代码块中的模型名
            r'`([a-zA-Z0-9_.-]+\.(?:safetensors|ckpt|pt|pth|bin|onnx))`',
            # 匹配列表项中的模型名
            r'[•\-\*]\s*([a-zA-Z0-9_.-]+\.(?:safetensors|ckpt|pt|pth|bin|onnx))',
            # 匹配"download and rename"模式
            r'download\s+and\s+rename.*?([a-zA-Z0-9_.-]+\.(?:safetensors|ckpt|pt|pth|bin))',
            # 匹配HuggingFace链接中的模型名
            r'huggingface\.co/[^/]+/[^/]+/[^/]+/([a-zA-Z0-9_.-]+\.(?:safetensors|ckpt|pt|pth|bin))',
            # 匹配路径格式的模型引用
            r'/ComfyUI/models/[^/]+/([a-zA-Z0-9_.-]+\.(?:safetensors|ckpt|pt|pth|bin))',
            # 匹配不带扩展名的模型名（在特定上下文中）
            r'(?:ip-adapter|clip|vit|model)[-_]([a-zA-Z0-9_.-]+)(?:\.safetensors|\.ckpt|\.pt|\.pth|\.bin)?',
            # 匹配表格中的模型名
            r'\|\s*([a-zA-Z0-9_.-]+\.(?:safetensors|ckpt|pt|pth|bin))\s*\|',
        ]

        # 特殊的模型名称模式（不依赖扩展名）
        contextual_patterns = [
            # IP-Adapter相关模型
            r'(ip-adapter[a-zA-Z0-9_.-]*)',
            r'(clip-vit[a-zA-Z0-9_.-]*)',
            # ControlNet相关模型
            r'(control[a-zA-Z0-9_.-]*)',
            # VAE相关模型
            r'(vae[a-zA-Z0-9_.-]*)',
            # 其他常见模型前缀
            r'(sam[a-zA-Z0-9_.-]*)',
            r'(yolo[a-zA-Z0-9_.-]*)',
            r'(resnet[a-zA-Z0-9_.-]*)',
        ]

        # 应用基本模式
        for pattern in basic_patterns:
            matches = re.findall(pattern, readme_content, re.IGNORECASE)
            for match in matches:
                if match and len(match) > 3:
                    model_references.append(match)

        # 应用增强模式
        for pattern in enhanced_patterns:
            matches = re.findall(pattern, readme_content, re.IGNORECASE)
            for match in matches:
                if match and len(match) > 3:
                    # 清理匹配结果
                    clean_match = match.strip('`[]()').strip()
                    if clean_match:
                        model_references.append(clean_match)

        # 应用上下文模式（只在特定关键词附近）
        lines = readme_content.split('\n')
        for i, line in enumerate(lines):
            line_lower = line.lower()
            # 检查是否包含模型相关关键词
            if any(keyword in line_lower for keyword in ['model', 'download', 'place', 'file', 'checkpoint']):
                for pattern in contextual_patterns:
                    matches = re.findall(pattern, line, re.IGNORECASE)
                    for match in matches:
                        if match and len(match) > 3:
                            model_references.append(match)

        # 清理和去重
        cleaned_references = []
        for ref in model_references:
            # 移除常见的非模型词汇
            if not any(exclude in ref.lower() for exclude in ['http', 'www', 'github', 'readme', 'license', 'install']):
                # 移除路径前缀
                clean_ref = ref.split('/')[-1] if '/' in ref else ref
                if len(clean_ref) > 3:
                    cleaned_references.append(clean_ref)

        return list(set(cleaned_references))
