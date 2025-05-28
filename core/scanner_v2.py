"""
新版扫描器 - ComfyModelCleaner V2.0

集成所有模块的主扫描流程，提供高精度的模型使用分析。
"""

import time
from pathlib import Path
from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass

from .model_discovery import ModelDiscovery, ModelInfo
from .reference_extractor import ReferenceExtractor, ModelReference
from .matcher import IntelligentMatcher, MatchResult
from .confidence_calculator import ConfidenceCalculator, ConfidenceFactors
from .github_analyzer import GitHubAnalyzer, GitHubRepoInfo
from .utils import get_custom_nodes_dir, format_file_size


@dataclass
class ScanResultV2:
    """V2扫描结果"""
    # 基础统计
    total_models: int
    single_file_models: int
    directory_models: int

    # 使用分析
    used_models: List[ModelInfo]
    unused_models: List[ModelInfo]
    uncertain_models: List[ModelInfo]

    # 详细分析
    match_results: Dict[str, MatchResult]
    confidence_analysis: Dict[str, ConfidenceFactors]
    github_analysis: Optional[Dict[str, GitHubRepoInfo]]

    # 统计信息
    total_size_bytes: int
    used_size_bytes: int
    unused_size_bytes: int
    potential_savings_bytes: int

    # 元数据
    scan_time: str
    scan_timestamp: float
    scan_config: Dict[str, Any]


class ScanCancelledException(Exception):
    """扫描被取消异常"""
    pass


class ProgressReporter:
    """进度报告器"""

    def __init__(self):
        self.current_step = 0
        self.total_steps = 5
        self.cancelled = False

    def check_cancellation(self):
        """检查是否被取消"""
        if self.cancelled:
            raise ScanCancelledException("扫描被用户取消")

    def cancel(self):
        """取消扫描"""
        self.cancelled = True
        print("⚠️ 扫描被取消")

    def report_discovery_progress(self, current: int, total: int):
        """报告模型发现进度"""
        self.check_cancellation()
        print(f"  [1/5] 模型发现: {current}/{total}")

    def report_extraction_progress(self, node_name: str, current: int, total: int):
        """报告引用提取进度"""
        self.check_cancellation()
        print(f"  [2/5] 引用提取: {node_name} ({current}/{total})")

    def report_matching_progress(self, current: int, total: int):
        """报告匹配进度"""
        self.check_cancellation()
        print(f"  [3/5] 智能匹配: {current}/{total}")

    def report_confidence_progress(self, current: int, total: int):
        """报告置信度计算进度"""
        self.check_cancellation()
        print(f"  [4/5] 置信度计算: {current}/{total}")

    def report_github_progress(self, current: int, total: int):
        """报告GitHub分析进度"""
        self.check_cancellation()
        print(f"  [5/5] GitHub分析: {current}/{total}")


class ModelScannerV2:
    """新版模型扫描器"""

    def __init__(self):
        self.discovery = ModelDiscovery()
        self.extractor = ReferenceExtractor()
        self.matcher = IntelligentMatcher()
        self.calculator = ConfidenceCalculator()
        self.github = None  # 将在scan_unused_models中根据配置初始化
        self.reporter = ProgressReporter()

    def scan_unused_models(self, config: Dict[str, Any]) -> ScanResultV2:
        """
        主扫描流程:
        1. 发现所有模型
        2. 提取所有引用
        3. GitHub增强分析（可选，在智能匹配前进行）
        4. 智能匹配
        5. 计算置信度
        6. 生成报告

        Args:
            config: 扫描配置

        Returns:
            ScanResultV2: 扫描结果
        """
        start_time = time.time()
        try:
            print("🚀 开始ComfyModelCleaner V2.0 扫描...")

            # 根据配置初始化GitHub分析器
            clear_cache = config.get('clear_cache', False)
            if config.get('github_analysis', False):
                # 如果需要清除缓存，则禁用GitHub分析器的缓存
                enable_github_cache = not clear_cache
                self.github = GitHubAnalyzer(enable_cache=enable_github_cache)
                if clear_cache:
                    print("🧹 GitHub分析器缓存已禁用")

            # 1. 发现所有模型
            print("\n📁 阶段1: 模型发现")
            self.reporter.check_cancellation()
            discovered_models = self.discovery.discover_models(config)
            self.reporter.check_cancellation()  # 发现完成后再次检查

            all_models = []
            all_models.extend(discovered_models['single_file_models'])
            all_models.extend(discovered_models['directory_models'])

            print(f"✅ 发现 {len(all_models)} 个模型")

            # 2. 提取所有引用
            print("\n🔍 阶段2: 引用提取")
            self.reporter.check_cancellation()
            node_dirs = self._get_active_node_directories()
            self.reporter.check_cancellation()
            extracted_references = self.extractor.extract_all_references(node_dirs)
            self.reporter.check_cancellation()  # 提取完成后再次检查

            total_references = sum(len(refs) for refs in extracted_references.values())
            print(f"✅ 提取 {total_references} 个引用")

            # 3. GitHub增强分析（可选，在智能匹配前进行）
            github_analysis = None
            if config.get('github_analysis', False) and self.github is not None:
                print("\n🌐 阶段3: GitHub增强分析")
                self.reporter.check_cancellation()
                github_analysis = self.github.analyze_node_repositories(node_dirs)
                self.reporter.check_cancellation()  # GitHub分析完成后再次检查
                print(f"✅ 分析 {len(github_analysis)} 个GitHub仓库")
            else:
                print("\n⏭️  跳过GitHub分析")

            # 4. 智能匹配（结合GitHub分析结果）
            print("\n🎯 阶段4: 智能匹配")
            self.reporter.check_cancellation()
            match_results = self.matcher.match_models(discovered_models, extracted_references)
            self.reporter.check_cancellation()  # 匹配完成后再次检查

            matched_count = sum(1 for result in match_results.values() if result.confidence > 0)
            print(f"✅ 匹配 {matched_count}/{len(all_models)} 个模型")

            # 5. 计算置信度（结合GitHub分析结果）
            print("\n📊 阶段5: 置信度计算")
            self.reporter.check_cancellation()
            confidence_analysis = {}

            total_models = len(match_results)
            for i, (model_id, match_result) in enumerate(match_results.items()):
                self.reporter.check_cancellation()  # 每个模型都检查取消
                confidence_factors = self.calculator.calculate_usage_confidence(
                    match_result.model_info, match_result, github_analysis
                )
                confidence_analysis[model_id] = confidence_factors

                # 每10个模型报告一次进度
                if (i + 1) % 10 == 0 or (i + 1) == total_models:
                    print(f"  置信度计算进度: {i + 1}/{total_models}")

            print(f"✅ 完成 {len(confidence_analysis)} 个模型的置信度分析")

            # 6. 生成结果
            print("\n📋 生成扫描结果...")
            self.reporter.check_cancellation()
            scan_result = self._generate_scan_result(
                discovered_models, match_results, confidence_analysis,
                github_analysis, config, start_time
            )

            scan_time = time.time() - start_time
            print(f"\n✅ 扫描完成！耗时 {scan_time:.2f} 秒")
            print(f"📊 结果摘要:")
            print(f"  - 总模型: {scan_result.total_models}")
            print(f"  - 正在使用: {len(scan_result.used_models)}")
            print(f"  - 可能未使用: {len(scan_result.unused_models)}")
            print(f"  - 不确定: {len(scan_result.uncertain_models)}")
            print(f"  - 潜在节省: {format_file_size(scan_result.potential_savings_bytes)}")

            return scan_result

        except ScanCancelledException as e:
            print(f"❌ {str(e)}")
            # 返回空的扫描结果
            scan_time = time.time() - start_time
            return self._create_empty_scan_result(config, scan_time)
        except Exception as e:
            print(f"❌ 扫描过程中发生错误: {str(e)}")
            # 检查是否是取消导致的错误
            if self.reporter.cancelled:
                print("❌ 扫描被取消")
                scan_time = time.time() - start_time
                return self._create_empty_scan_result(config, scan_time)
            else:
                raise

    def _get_active_node_directories(self) -> List[Path]:
        """获取激活的节点目录"""
        custom_nodes_dir = get_custom_nodes_dir()
        active_dirs = []

        if custom_nodes_dir.exists():
            for node_dir in custom_nodes_dir.iterdir():
                if (node_dir.is_dir() and
                    not node_dir.name.startswith('.') and
                    self._is_active_node_directory(node_dir)):
                    active_dirs.append(node_dir)

        return active_dirs

    def _is_active_node_directory(self, node_dir: Path) -> bool:
        """判断是否是激活的节点目录"""
        # 检查是否有Python文件
        has_python_files = any(node_dir.glob('*.py'))

        # 检查是否被禁用
        is_disabled = (
            (node_dir / '.disabled').exists() or
            node_dir.name.endswith('.disabled') or
            node_dir.name.startswith('disabled_')
        )

        return has_python_files and not is_disabled

    def _generate_scan_result(self, discovered_models: Dict[str, List[ModelInfo]],
                            match_results: Dict[str, MatchResult],
                            confidence_analysis: Dict[str, ConfidenceFactors],
                            github_analysis: Optional[Dict[str, GitHubRepoInfo]],
                            config: Dict[str, Any],
                            start_time: float) -> ScanResultV2:
        """生成扫描结果"""

        # 合并所有模型
        all_models = []
        all_models.extend(discovered_models['single_file_models'])
        all_models.extend(discovered_models['directory_models'])

        # 分类模型
        used_models = []
        unused_models = []
        uncertain_models = []

        confidence_threshold = config.get('confidence_threshold', 70)

        for model in all_models:
            model_id = f"{model.directory}/{model.name}"

            if model_id in confidence_analysis:
                # 使用置信度分数，需要转换为未使用置信度
                usage_confidence = confidence_analysis[model_id].total_score
                unused_confidence = 100 - usage_confidence  # 转换为未使用置信度

                # 根据未使用置信度分类 - 调整阈值使其更合理
                if unused_confidence < 50:
                    # 未使用置信度 < 50% = 很可能在使用
                    used_models.append(model)
                elif unused_confidence > confidence_threshold:
                    # 未使用置信度 > 阈值 = 很可能未使用
                    unused_models.append(model)
                else:
                    # 50% <= 未使用置信度 <= 阈值 = 不确定状态
                    uncertain_models.append(model)
            else:
                # 没有置信度分析的模型视为未使用（未使用置信度100%）
                unused_models.append(model)

        # 计算大小统计
        total_size = sum(model.size_bytes for model in all_models)
        used_size = sum(model.size_bytes for model in used_models)
        unused_size = sum(model.size_bytes for model in unused_models)

        scan_time = time.time() - start_time

        return ScanResultV2(
            # 基础统计
            total_models=len(all_models),
            single_file_models=len(discovered_models['single_file_models']),
            directory_models=len(discovered_models['directory_models']),

            # 使用分析
            used_models=used_models,
            unused_models=unused_models,
            uncertain_models=uncertain_models,

            # 详细分析
            match_results=match_results,
            confidence_analysis=confidence_analysis,
            github_analysis=github_analysis,

            # 统计信息
            total_size_bytes=total_size,
            used_size_bytes=used_size,
            unused_size_bytes=unused_size,
            potential_savings_bytes=unused_size,

            # 元数据
            scan_time=f"{scan_time:.2f}秒",
            scan_timestamp=time.time(),
            scan_config=config.copy()
        )

    def _create_empty_scan_result(self, config: Dict[str, Any], scan_time: float) -> ScanResultV2:
        """创建空的扫描结果（用于取消时）"""
        return ScanResultV2(
            # 基础统计
            total_models=0,
            single_file_models=0,
            directory_models=0,

            # 使用分析
            used_models=[],
            unused_models=[],
            uncertain_models=[],

            # 详细分析
            match_results={},
            confidence_analysis={},
            github_analysis=None,

            # 统计信息
            total_size_bytes=0,
            used_size_bytes=0,
            unused_size_bytes=0,
            potential_savings_bytes=0,

            # 元数据
            scan_time=f"{scan_time:.2f}秒 (已取消)",
            scan_timestamp=time.time(),
            scan_config=config.copy()
        )
