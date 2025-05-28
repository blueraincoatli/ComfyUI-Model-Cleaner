"""
置信度计算器 - ComfyModelCleaner V2.0

计算模型使用置信度，综合考虑匹配类型、引用来源、时间因素等。
支持基于模型类型的智能评分：
- 独立模型：单文件形式，>100MB，无配套配置文件
- 模型组件：多文件目录，包含配置文件，需要协同工作
"""

import time
import json
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass
from pathlib import Path

from .model_discovery import ModelInfo
from .reference_extractor import ModelReference
from .matcher import MatchResult


@dataclass
class ConfidenceFactors:
    """置信度因素"""
    match_strength: float  # 匹配强度 (0-60分)
    source_weight: float   # 引用来源权重 (0-20分)
    github_bonus: float    # GitHub增强分数 (0-10分)
    time_factor: float     # 时间因素 (0-10分)
    file_factor: float     # 文件大小和类型 (0-10分)
    total_score: float     # 总分 (0-110分，但会被限制在100分)


class ConfidenceCalculator:
    """置信度计算器"""

    def __init__(self):
        # 匹配类型权重 - 降低基础分数，提高判断标准
        self.match_type_weights = {
            'exact': 45,      # 精确匹配高分（降低15分）
            'partial': 30,    # 部分匹配中等分（降低15分）
            'fuzzy': 15,      # 模糊匹配较低分（降低15分）
            'path': 20,       # 路径匹配中低分（降低15分）
            'none': 0         # 无匹配0分
        }

        # 引用源权重 - 降低权重，更严格判断
        self.source_weights = {
            'python': 15,        # Python代码最重要（降低5分）
            'config': 10,        # 配置文件重要（降低5分）
            'workflow': 8,       # 工作流中等（降低4分）
            'documentation': 3   # 文档较低（降低5分）
        }

        # 时间阈值（天）
        self.time_thresholds = {
            'very_recent': 1,    # 1天内
            'recent': 7,         # 7天内
            'moderate': 30,      # 30天内
            'old': 90           # 90天内
        }

        # 模型类型识别的配置文件名
        self.config_file_names = {
            'config.json', 'tokenizer_config.json', 'model_index.json',
            'scheduler_config.json', 'feature_extractor_config.json',
            'preprocessor_config.json', 'generation_config.json'
        }

        # 独立模型的最小文件大小（100MB）
        self.independent_model_min_size = 100 * 1024 * 1024

    def calculate_usage_confidence(self, model_info: ModelInfo,
                                 match_result: MatchResult,
                                 github_analysis: Optional[Dict] = None) -> ConfidenceFactors:
        """
        计算模型使用置信度

        因素:
        - 匹配类型和强度 (0-60分)
        - 引用来源权重 (0-20分)
        - GitHub增强分数 (0-10分)
        - 时间因素 (0-10分)
        - 文件大小和类型 (0-10分)

        Args:
            model_info: 模型信息
            match_result: 匹配结果
            github_analysis: GitHub分析结果（可选）

        Returns:
            ConfidenceFactors: 置信度分析结果，总分0-100
        """
        # 1. 计算匹配强度分数
        match_strength = self._calculate_match_strength(match_result)

        # 2. 计算引用来源权重分数
        source_weight = self._calculate_source_weight(match_result.references)

        # 3. 计算GitHub增强分数
        github_bonus = self._calculate_github_bonus(model_info, github_analysis)

        # 4. 计算时间因素分数
        time_factor = self._calculate_time_factor(model_info)

        # 5. 计算文件因素分数
        file_factor = self._calculate_file_factor(model_info)

        # 6. 计算总分
        total_score = match_strength + source_weight + github_bonus + time_factor + file_factor
        total_score = max(0.0, min(100.0, total_score))

        return ConfidenceFactors(
            match_strength=match_strength,
            source_weight=source_weight,
            github_bonus=github_bonus,
            time_factor=time_factor,
            file_factor=file_factor,
            total_score=total_score
        )

    def _calculate_match_strength(self, match_result: MatchResult) -> float:
        """
        计算匹配强度分数 (0-60分)

        Args:
            match_result: 匹配结果

        Returns:
            float: 匹配强度分数
        """
        base_score = self.match_type_weights.get(match_result.match_type, 0)

        if match_result.match_type == 'none':
            return 0.0

        # 根据引用数量调整分数
        ref_count = len(match_result.references)
        if ref_count > 1:
            # 多个引用增加置信度
            bonus = min(10, ref_count * 2)  # 最多加10分
            base_score += bonus

        # 根据匹配详情调整分数
        if match_result.match_details:
            # 精确匹配的额外加分
            if match_result.match_type == 'exact':
                if 'reference_count' in match_result.match_details:
                    count = match_result.match_details['reference_count']
                    if count >= 3:
                        base_score += 5  # 3个以上引用额外加分

            # 模糊匹配根据相似度调整
            elif match_result.match_type == 'fuzzy':
                if 'best_similarity' in match_result.match_details:
                    similarity = match_result.match_details['best_similarity']
                    # 相似度越高分数越高
                    base_score = base_score * similarity

        return min(60.0, base_score)

    def _calculate_source_weight(self, references: List[ModelReference]) -> float:
        """
        计算引用来源权重分数 (0-20分)

        Args:
            references: 引用列表

        Returns:
            float: 来源权重分数
        """
        if not references:
            return 0.0

        # 按来源类型分组
        source_groups = {}
        for ref in references:
            source_type = ref.source_type
            if source_type not in source_groups:
                source_groups[source_type] = []
            source_groups[source_type].append(ref)

        total_score = 0.0

        # 计算每种来源类型的分数
        for source_type, refs in source_groups.items():
            base_weight = self.source_weights.get(source_type, 5)

            # 考虑该类型引用的数量
            count_factor = min(1.5, 1.0 + len(refs) * 0.1)  # 最多1.5倍

            # 考虑引用的置信度
            avg_confidence = sum(ref.confidence for ref in refs) / len(refs)
            confidence_factor = avg_confidence

            source_score = base_weight * count_factor * confidence_factor
            total_score += source_score

        return min(20.0, total_score)

    def _calculate_time_factor(self, model_info: ModelInfo) -> float:
        """
        计算时间因素分数 (0-10分)
        优先使用访问时间 (atime)，回退到修改时间 (mtime)

        Args:
            model_info: 模型信息

        Returns:
            float: 时间因素分数
        """
        model_path = Path(model_info.path)

        try:
            # 获取文件统计信息
            stat_info = model_path.stat()
            access_time = stat_info.st_atime
            modified_time = stat_info.st_mtime

            current_time = time.time()

            # 计算时间差异
            days_since_access = (current_time - access_time) / (24 * 3600) if access_time > 0 else float('inf')
            days_since_modified = (current_time - modified_time) / (24 * 3600) if modified_time > 0 else float('inf')

            # 计算各自的分数
            access_score = self._calculate_time_score(days_since_access, is_access_time=True) if access_time > 0 else 0.0
            modified_score = self._calculate_time_score(days_since_modified, is_access_time=False) if modified_time > 0 else 0.0

            # 访问时间权重更高，因为它更能反映实际使用情况
            # 但如果访问时间和修改时间差异很大，说明文件可能被意外访问
            time_diff = abs(access_time - modified_time) / (24 * 3600) if (access_time > 0 and modified_time > 0) else 0

            if time_diff < 1:  # 如果访问时间和修改时间很接近（1天内）
                # 可能是刚创建的文件，主要看修改时间
                final_score = modified_score * 0.7 + access_score * 0.3
            elif days_since_access <= 7:  # 最近7天内被访问
                # 访问时间更重要
                final_score = access_score * 0.8 + modified_score * 0.2
            else:
                # 平衡考虑两个时间
                final_score = access_score * 0.6 + modified_score * 0.4

            return min(10.0, final_score)

        except Exception as e:
            # 如果无法获取时间信息，回退到原有逻辑
            if model_info.modified_time:
                current_time = time.time()
                days_since_modified = (current_time - model_info.modified_time) / (24 * 3600)
                return self._calculate_time_score(days_since_modified, is_access_time=False)
            else:
                return 1.0  # 默认较低分数

    def _calculate_time_score(self, days_since: float, is_access_time: bool = True) -> float:
        """
        根据时间间隔计算分数

        Args:
            days_since: 距离现在的天数
            is_access_time: 是否是访问时间（访问时间的评分更严格）

        Returns:
            float: 时间分数
        """
        if is_access_time:
            # 访问时间评分 - 更严格，因为访问时间更能反映实际使用
            if days_since <= 1:
                return 9.0   # 最近1天被访问，很可能在使用
            elif days_since <= 7:
                return 7.0   # 最近1周被访问，可能在使用
            elif days_since <= 30:
                return 4.0   # 最近1月被访问，可能在使用
            elif days_since <= 90:
                return 2.0   # 最近3月被访问，可能不在使用
            else:
                return 0.5   # 很久未访问，很可能不在使用
        else:
            # 修改时间评分 - 相对宽松，因为修改时间不直接反映使用情况
            if days_since <= self.time_thresholds['very_recent']:
                return 6.0   # 最近修改，可能在使用
            elif days_since <= self.time_thresholds['recent']:
                return 4.0   # 近期修改，可能在使用
            elif days_since <= self.time_thresholds['moderate']:
                return 2.0   # 中期修改，可能在使用
            elif days_since <= self.time_thresholds['old']:
                return 1.0   # 较久未修改，可能不在使用
            else:
                return 0.0   # 很久未修改，很可能不在使用

    def _calculate_file_factor(self, model_info: ModelInfo) -> float:
        """
        计算文件大小和类型因素分数 (0-10分)
        基于模型类别进行智能评分

        Args:
            model_info: 模型信息

        Returns:
            float: 文件因素分数
        """
        # 识别模型类别
        model_category = self.identify_model_category(model_info)

        score = 2.0  # 基础分数

        # 根据模型类别调整基础分数
        if model_category == 'independent':
            score += 2.0  # 独立模型更重要
        elif model_category == 'component':
            score += 1.5  # 模型组件中等重要
        elif model_category == 'collection':
            score += 1.0  # 模型集合较低重要性

        # 根据文件大小调整
        size_mb = model_info.size_bytes / (1024 * 1024)

        if model_category == 'independent':
            # 独立模型：大文件更重要
            if size_mb > 1000:  # 大于1GB
                score += 2.0
            elif size_mb > 500:  # 大于500MB
                score += 1.5
            elif size_mb >= 100:  # 大于100MB（独立模型标准）
                score += 1.0
        else:
            # 组件模型：按传统方式评分
            if size_mb < 1:  # 小于1MB，可能是配置文件
                score += 1.0
            elif size_mb < 100:  # 小于100MB，可能是小组件
                score += 0.5
            elif size_mb > 1000:  # 大于1GB，重要组件
                score += 1.5

        # 根据文件类型调整
        if model_info.extension:
            ext = model_info.extension.lower()
            if ext == '.safetensors':
                score += 1.0  # safetensors格式更现代
            elif ext == '.ckpt':
                score += 0.5  # ckpt格式较老但常用
            elif ext in ['.pt', '.pth']:
                score += 0.5  # PyTorch格式

        # 根据模型类型调整
        if model_info.model_type == 'directory':
            if model_category == 'component':
                score += 1.5  # 组件目录通常更复杂重要
            elif model_category == 'collection':
                score += 0.5  # 集合目录重要性较低

        return min(10.0, score)

    def get_confidence_level(self, total_score: float) -> str:
        """
        根据总分获取未使用置信度等级
        注意：这里的置信度指的是"模型未使用"的置信度

        Args:
            total_score: 使用分数 (0-100)

        Returns:
            str: 未使用置信度等级描述
        """
        # 将使用分数转换为未使用置信度
        unused_confidence = 100 - total_score

        if unused_confidence >= 80:
            return "很高 - 很可能未使用"
        elif unused_confidence >= 60:
            return "高 - 可能未使用"
        elif unused_confidence >= 40:
            return "中等 - 不确定"
        elif unused_confidence >= 20:
            return "低 - 可能在使用"
        else:
            return "很低 - 很可能在使用"

    def get_unused_confidence(self, total_score: float) -> float:
        """
        获取未使用置信度百分比

        Args:
            total_score: 使用分数 (0-100)

        Returns:
            float: 未使用置信度 (0-100)
        """
        return max(0.0, min(100.0, 100 - total_score))

    def is_likely_unused(self, total_score: float, threshold: float = 70.0) -> bool:
        """
        判断模型是否可能未使用
        基于未使用置信度进行判断

        Args:
            total_score: 使用分数 (0-100)
            threshold: 未使用置信度阈值 (默认70%)

        Returns:
            bool: 是否可能未使用
        """
        unused_confidence = self.get_unused_confidence(total_score)
        return unused_confidence >= threshold

    def _calculate_github_bonus(self, model_info: ModelInfo,
                               github_analysis: Optional[Dict] = None) -> float:
        """
        计算GitHub增强分数 (0-10分)

        Args:
            model_info: 模型信息
            github_analysis: GitHub分析结果

        Returns:
            float: GitHub增强分数
        """
        if not github_analysis:
            return 0.0

        model_name = model_info.name
        bonus_score = 0.0

        # 检查所有GitHub仓库中是否提到了这个模型
        for repo_info in github_analysis.values():
            if hasattr(repo_info, 'model_references') and repo_info.model_references:
                # 检查精确匹配
                for ref in repo_info.model_references:
                    if model_name.lower() in ref.lower():
                        bonus_score += 3.0  # 在GitHub README中被提及
                        break

                # 检查部分匹配（去掉扩展名）
                model_base_name = model_name.split('.')[0]
                for ref in repo_info.model_references:
                    if model_base_name.lower() in ref.lower():
                        bonus_score += 1.5  # 部分匹配
                        break

        return min(10.0, bonus_score)

    def identify_model_category(self, model_info: ModelInfo) -> str:
        """
        识别模型类别：独立模型 vs 模型组件

        独立模型特征：
        - 直接位于模型目录下
        - 单文件形式存在且文件大小 >100MB
        - 无配套配置文件

        模型组件特征：
        - 拥有独立的子目录结构
        - 包含模型配置文件
        - 需要多个文件协同工作

        Args:
            model_info: 模型信息

        Returns:
            str: 'independent' | 'component' | 'collection'
        """
        model_path = Path(model_info.path)

        # 单文件模型的判断
        if model_info.model_type == 'file':
            # 检查文件大小是否达到独立模型标准
            if model_info.size_bytes >= self.independent_model_min_size:
                # 检查是否有配套配置文件
                parent_dir = model_path.parent
                has_config = any(
                    (parent_dir / config_name).exists()
                    for config_name in self.config_file_names
                )

                if not has_config:
                    return 'independent'  # 独立模型
                else:
                    return 'component'    # 模型组件的一部分
            else:
                return 'component'  # 小文件，可能是组件

        # 目录模型的判断
        elif model_info.model_type == 'directory':
            # 检查是否包含配置文件
            has_config = self._has_config_files(model_path)

            if has_config:
                return 'component'  # 模型组件目录
            else:
                # 检查是否是模型集合目录（如BiRefNet）
                if self._is_model_collection(model_path):
                    return 'collection'  # 模型集合
                else:
                    return 'component'   # 默认为组件

        return 'component'  # 默认分类

    def _has_config_files(self, dir_path: Path) -> bool:
        """检查目录是否包含配置文件"""
        try:
            for item in dir_path.rglob('*'):
                if item.is_file() and item.name in self.config_file_names:
                    return True
        except Exception:
            pass
        return False

    def _is_model_collection(self, dir_path: Path) -> bool:
        """
        判断是否是模型集合目录（如BiRefNet）
        特征：包含多个模型文件但没有配置文件
        """
        try:
            model_files = []
            for item in dir_path.iterdir():
                if item.is_file() and item.suffix.lower() in {'.pth', '.pt', '.ckpt', '.safetensors'}:
                    model_files.append(item)

            # 如果有多个模型文件且没有配置文件，可能是集合目录
            return len(model_files) > 1 and not self._has_config_files(dir_path)
        except Exception:
            pass
        return False

    def get_model_analysis_summary(self, model_info: ModelInfo,
                                 confidence_factors: ConfidenceFactors) -> Dict[str, Any]:
        """
        获取模型分析摘要，包括类别识别和详细信息

        Args:
            model_info: 模型信息
            confidence_factors: 置信度因素

        Returns:
            Dict: 包含模型分析的详细信息
        """
        model_category = self.identify_model_category(model_info)
        unused_confidence = self.get_unused_confidence(confidence_factors.total_score)

        return {
            'model_category': model_category,
            'model_category_description': self._get_category_description(model_category),
            'unused_confidence': unused_confidence,
            'unused_confidence_level': self.get_confidence_level(confidence_factors.total_score),
            'is_likely_unused': self.is_likely_unused(confidence_factors.total_score),
            'size_mb': round(model_info.size_bytes / (1024 * 1024), 2),
            'model_type': model_info.model_type,
            'has_config_files': self._has_config_files(Path(model_info.path)) if model_info.model_type == 'directory' else False,
            'confidence_breakdown': {
                'match_strength': confidence_factors.match_strength,
                'source_weight': confidence_factors.source_weight,
                'github_bonus': confidence_factors.github_bonus,
                'time_factor': confidence_factors.time_factor,
                'file_factor': confidence_factors.file_factor,
                'total_score': confidence_factors.total_score
            }
        }

    def _get_category_description(self, category: str) -> str:
        """获取模型类别的描述"""
        descriptions = {
            'independent': '独立模型 - 单文件形式，>100MB，无配套配置文件',
            'component': '模型组件 - 多文件目录或包含配置文件，需要协同工作',
            'collection': '模型集合 - 包含多个独立模型的集合目录'
        }
        return descriptions.get(category, '未知类别')
