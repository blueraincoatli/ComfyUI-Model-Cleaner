"""
智能匹配引擎 - ComfyModelCleaner V2.0

多级匹配策略：精确匹配、部分匹配、模糊匹配、路径匹配。
"""

import re
import difflib
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from .model_discovery import ModelInfo
from .reference_extractor import ModelReference


@dataclass
class MatchResult:
    """匹配结果"""
    model_info: ModelInfo
    references: List[ModelReference]
    match_type: str  # 'exact', 'partial', 'fuzzy', 'path'
    confidence: float  # 0.0 - 1.0
    match_details: Dict[str, Any]


class IntelligentMatcher:
    """智能匹配引擎"""

    def __init__(self):
        self.match_cache = {}
        self._node_name_cache = {}  # 缓存文件路径到节点名称的映射
        self._ui_extensions = {  # UI相关扩展，不实际使用模型
            'manager', 'comfyui-manager', 'comfyui_manager',
            'frontend', 'ui', 'interface', 'web', 'browser',
            'workspace', 'settings', 'config', 'utils', 'helper'
        }

    def match_models(self, discovered_models: Dict[str, List[ModelInfo]],
                    extracted_references: Dict[str, List[ModelReference]]) -> Dict[str, MatchResult]:
        """
        多级匹配策略:
        1. 精确匹配 (confidence: 90-100%)
        2. 部分匹配 (confidence: 70-90%)
        3. 模糊匹配 (confidence: 40-60%)
        4. 路径匹配 (confidence: 50-70%)

        Args:
            discovered_models: 发现的模型
            extracted_references: 提取的引用

        Returns:
            Dict[str, MatchResult]: 匹配结果，键为模型标识符
        """
        print("🎯 开始智能匹配...")

        # 合并所有模型
        all_models = []
        for model_list in discovered_models.values():
            all_models.extend(model_list)

        # 合并所有引用并预建立节点名称缓存
        all_references = []
        for ref_list in extracted_references.values():
            all_references.extend(ref_list)

        # 预建立节点名称缓存，一次性处理所有引用
        self._build_node_name_cache(all_references)

        print(f"  模型总数: {len(all_models)}")
        print(f"  引用总数: {len(all_references)}")

        match_results = {}

        for model in all_models:
            model_id = f"{model.directory}/{model.name}"

            # 尝试各种匹配策略
            best_match = self._find_best_match(model, all_references)

            if best_match:
                match_results[model_id] = best_match
                # 转换为未使用置信度显示 (100 - 使用置信度)
                unused_confidence = 100 - (best_match.confidence * 100)

                # 提取节点名称信息（使用缓存优化）
                node_names = self._get_filtered_node_names(best_match.references)
                if node_names:
                    node_info = f"可能被 {', '.join(node_names)} 节点使用"
                else:
                    match_type_display = {
                        'exact': '精确匹配',
                        'partial': '部分匹配',
                        'fuzzy': '模糊匹配',
                        'path': '路径匹配'
                    }
                    node_info = f"{match_type_display.get(best_match.match_type, best_match.match_type)}!"

                # 格式化对齐输出
                model_name_width = 35  # 模型名称列宽度
                node_info_width = 45   # 节点信息列宽度

                # 截断过长的模型名称
                display_name = model.name[:model_name_width-3] + "..." if len(model.name) > model_name_width else model.name
                # 截断过长的节点信息
                display_node_info = node_info[:node_info_width-3] + "..." if len(node_info) > node_info_width else node_info

                print(f"  ✅ {display_name:<{model_name_width}} {display_node_info:<{node_info_width}} (未使用置信度: {unused_confidence:3.0f}%)")
            else:
                # 创建无匹配结果
                match_results[model_id] = MatchResult(
                    model_info=model,
                    references=[],
                    match_type='none',
                    confidence=0.0,
                    match_details={'reason': 'no_references_found'}
                )

        matched_count = sum(1 for result in match_results.values() if result.confidence > 0)
        print(f"✅ 匹配完成: {matched_count}/{len(all_models)} 个模型有引用")

        return match_results

    def _find_best_match(self, model: ModelInfo, references: List[ModelReference]) -> Optional[MatchResult]:
        """
        为单个模型找到最佳匹配

        Args:
            model: 模型信息
            references: 所有引用

        Returns:
            Optional[MatchResult]: 最佳匹配结果
        """
        # 尝试不同的匹配策略
        strategies = [
            ('exact', self.exact_match),
            ('partial', self.partial_match),
            ('fuzzy', self.fuzzy_match),
            ('path', self.path_match)
        ]

        best_result = None
        best_confidence = 0.0

        for _, strategy_func in strategies:
            result = strategy_func(model, references)
            if result and result.confidence > best_confidence:
                best_result = result
                best_confidence = result.confidence

        return best_result

    def exact_match(self, model: ModelInfo, references: List[ModelReference]) -> Optional[MatchResult]:
        """
        精确匹配

        Args:
            model: 模型信息
            references: 引用列表

        Returns:
            Optional[MatchResult]: 匹配结果
        """
        matched_refs = []

        for ref in references:
            # 完全匹配模型名称
            if model.name.lower() == ref.model_name.lower():
                matched_refs.append(ref)
            # 匹配带扩展名的文件名
            elif model.model_type == 'file':
                full_name = f"{model.name}{model.extension}"
                if full_name.lower() == ref.model_name.lower():
                    matched_refs.append(ref)

        if matched_refs:
            confidence = 0.95 + (len(matched_refs) * 0.01)  # 多个引用增加置信度
            confidence = min(1.0, confidence)

            return MatchResult(
                model_info=model,
                references=matched_refs,
                match_type='exact',
                confidence=confidence,
                match_details={
                    'matched_names': [ref.model_name for ref in matched_refs],
                    'reference_count': len(matched_refs)
                }
            )

        return None

    def partial_match(self, model: ModelInfo, references: List[ModelReference]) -> Optional[MatchResult]:
        """
        部分匹配 (去除版本号、前缀等)

        Args:
            model: 模型信息
            references: 引用列表

        Returns:
            Optional[MatchResult]: 匹配结果
        """
        matched_refs = []
        model_clean = self._clean_name_for_matching(model.name)

        for ref in references:
            ref_clean = self._clean_name_for_matching(ref.model_name)

            # 部分匹配策略
            if self._is_partial_match(model_clean, ref_clean):
                matched_refs.append(ref)

        if matched_refs:
            # 部分匹配的置信度较低
            base_confidence = 0.75
            confidence = base_confidence + (len(matched_refs) * 0.02)
            confidence = min(0.90, confidence)

            return MatchResult(
                model_info=model,
                references=matched_refs,
                match_type='partial',
                confidence=confidence,
                match_details={
                    'cleaned_model_name': model_clean,
                    'matched_references': [(ref.model_name, self._clean_name_for_matching(ref.model_name))
                                         for ref in matched_refs],
                    'reference_count': len(matched_refs)
                }
            )

        return None

    def fuzzy_match(self, model: ModelInfo, references: List[ModelReference]) -> Optional[MatchResult]:
        """
        模糊匹配 (编辑距离、关键词匹配)

        Args:
            model: 模型信息
            references: 引用列表

        Returns:
            Optional[MatchResult]: 匹配结果
        """
        matched_refs = []
        model_name = model.name.lower()

        for ref in references:
            ref_name = ref.model_name.lower()

            # 计算相似度
            similarity = difflib.SequenceMatcher(None, model_name, ref_name).ratio()

            # 关键词匹配
            keyword_match = self._keyword_similarity(model_name, ref_name)

            # 综合相似度
            combined_similarity = max(similarity, keyword_match)

            # 对于特定模型类型降低阈值
            threshold = 0.6
            if any(keyword in model_name for keyword in ['segformer', 'clip', 'vit', 'sam']):
                threshold = 0.4  # 降低阈值以提高匹配率

            if combined_similarity > threshold:
                matched_refs.append((ref, combined_similarity))

        if matched_refs:
            # 按相似度排序
            matched_refs.sort(key=lambda x: x[1], reverse=True)

            # 计算置信度
            best_similarity = matched_refs[0][1]
            confidence = 0.4 + (best_similarity * 0.3)  # 40-70%

            return MatchResult(
                model_info=model,
                references=[ref for ref, _ in matched_refs],
                match_type='fuzzy',
                confidence=confidence,
                match_details={
                    'similarities': [(ref.model_name, sim) for ref, sim in matched_refs],
                    'best_similarity': best_similarity,
                    'reference_count': len(matched_refs)
                }
            )

        return None

    def path_match(self, model: ModelInfo, references: List[ModelReference]) -> Optional[MatchResult]:
        """
        路径匹配 (基于目录结构)

        Args:
            model: 模型信息
            references: 引用列表

        Returns:
            Optional[MatchResult]: 匹配结果
        """
        matched_refs = []

        for ref in references:
            # 检查引用是否包含模型的目录信息
            if self._is_path_match(model, ref):
                matched_refs.append(ref)

        if matched_refs:
            confidence = 0.5 + (len(matched_refs) * 0.05)
            confidence = min(0.75, confidence)

            return MatchResult(
                model_info=model,
                references=matched_refs,
                match_type='path',
                confidence=confidence,
                match_details={
                    'model_directory': model.directory,
                    'model_path': model.relative_path,
                    'matched_paths': [ref.context for ref in matched_refs],
                    'reference_count': len(matched_refs)
                }
            )

        return None

    def _clean_name_for_matching(self, name: str) -> str:
        """
        清理名称用于匹配

        Args:
            name: 原始名称

        Returns:
            str: 清理后的名称
        """
        # 移除常见的版本号和前缀
        clean = name.lower()

        # 移除版本号模式
        version_patterns = [
            r'[-_]v?\d+(\.\d+)*',  # -v1.0, _v2.1, -1.5
            r'[-_]\d+[a-z]?$',     # -1a, _2b
            r'[-_](alpha|beta|rc)\d*',  # -alpha, -beta1, -rc2
        ]

        for pattern in version_patterns:
            clean = re.sub(pattern, '', clean)

        # 移除常见前缀和后缀
        prefixes_suffixes = [
            'comfyui_', 'comfyui-', 'sd_', 'sd-', 'xl_', 'xl-',
            '_model', '-model', '_checkpoint', '-checkpoint'
        ]

        for fix in prefixes_suffixes:
            if clean.startswith(fix):
                clean = clean[len(fix):]
            if clean.endswith(fix):
                clean = clean[:-len(fix)]

        # 移除特殊字符，只保留字母数字
        clean = re.sub(r'[^a-z0-9]', '', clean)

        return clean.strip()

    def _is_partial_match(self, name1: str, name2: str) -> bool:
        """
        判断是否是部分匹配

        Args:
            name1: 名称1
            name2: 名称2

        Returns:
            bool: 是否匹配
        """
        if not name1 or not name2:
            return False

        # 长度差异太大则不匹配
        if abs(len(name1) - len(name2)) > max(len(name1), len(name2)) * 0.5:
            return False

        # 检查包含关系
        if name1 in name2 or name2 in name1:
            return True

        # 检查公共子串
        common_length = len(self._longest_common_substring(name1, name2))
        min_length = min(len(name1), len(name2))

        return common_length >= min_length * 0.7

    def _longest_common_substring(self, s1: str, s2: str) -> str:
        """
        找到最长公共子串

        Args:
            s1: 字符串1
            s2: 字符串2

        Returns:
            str: 最长公共子串
        """
        m, n = len(s1), len(s2)
        dp = [[0] * (n + 1) for _ in range(m + 1)]

        max_length = 0
        ending_pos = 0

        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if s1[i-1] == s2[j-1]:
                    dp[i][j] = dp[i-1][j-1] + 1
                    if dp[i][j] > max_length:
                        max_length = dp[i][j]
                        ending_pos = i
                else:
                    dp[i][j] = 0

        return s1[ending_pos - max_length:ending_pos]

    def _keyword_similarity(self, name1: str, name2: str) -> float:
        """
        基于关键词的相似度计算

        Args:
            name1: 名称1
            name2: 名称2

        Returns:
            float: 相似度 (0.0 - 1.0)
        """
        # 提取关键词
        keywords1 = set(re.findall(r'[a-z]+', name1.lower()))
        keywords2 = set(re.findall(r'[a-z]+', name2.lower()))

        if not keywords1 or not keywords2:
            return 0.0

        # 计算交集和并集
        intersection = keywords1 & keywords2
        union = keywords1 | keywords2

        # 基础Jaccard相似度
        jaccard_similarity = len(intersection) / len(union) if union else 0.0

        # 增强匹配：检查重要关键词
        important_keywords = {'segformer', 'clip', 'vit', 'sam', 'controlnet', 'lora', 'vae'}

        # 如果有重要关键词匹配，给予额外加分
        important_matches = intersection & important_keywords
        if important_matches:
            # 重要关键词匹配时，提高相似度
            bonus = len(important_matches) * 0.3
            jaccard_similarity = min(1.0, jaccard_similarity + bonus)

        # 检查主要模型类型匹配（如segformer）
        for keyword in important_keywords:
            if keyword in name1.lower() and keyword in name2.lower():
                # 如果两个名称都包含相同的重要关键词，至少给0.5的相似度
                jaccard_similarity = max(jaccard_similarity, 0.5)
                break

        return jaccard_similarity

    def _is_path_match(self, model: ModelInfo, reference: ModelReference) -> bool:
        """
        判断是否是路径匹配

        Args:
            model: 模型信息
            reference: 引用信息

        Returns:
            bool: 是否匹配
        """
        # 检查引用上下文是否包含模型目录
        context_lower = reference.context.lower()

        # 检查目录名匹配
        if model.directory.lower() in context_lower:
            return True

        # 检查相对路径匹配
        path_parts = Path(model.relative_path).parts
        for part in path_parts:
            if part.lower() in context_lower:
                return True

        # 检查源文件路径是否与模型相关
        if reference.source_file:
            source_path = Path(reference.source_file)
            # 如果引用来自与模型目录相关的节点
            if model.directory.lower() in str(source_path).lower():
                return True

        return False

    def _build_node_name_cache(self, references: List[ModelReference]):
        """
        预建立节点名称缓存，一次性处理所有引用以提高性能

        Args:
            references: 所有模型引用列表
        """
        print("  🔧 建立节点名称缓存...")

        for ref in references:
            if ref.source_file and ref.source_file not in self._node_name_cache:
                node_name = self._extract_node_name_from_path(ref.source_file)
                self._node_name_cache[ref.source_file] = node_name

        print(f"  ✅ 缓存建立完成，共 {len(self._node_name_cache)} 个文件路径")

    def _extract_node_name_from_path(self, file_path: str) -> Optional[str]:
        """
        从文件路径中提取节点名称

        Args:
            file_path: 文件路径

        Returns:
            Optional[str]: 节点名称，如果无法提取则返回None
        """
        try:
            source_path = Path(file_path)
            parts = source_path.parts

            # 找到custom_nodes在路径中的位置
            custom_nodes_index = -1
            for i, part in enumerate(parts):
                if part.lower() == 'custom_nodes':
                    custom_nodes_index = i
                    break

            # 如果找到custom_nodes，下一个部分就是节点名称
            if custom_nodes_index >= 0 and custom_nodes_index + 1 < len(parts):
                node_name = parts[custom_nodes_index + 1]

                # 清理节点名称，移除常见的前缀
                if node_name.startswith('ComfyUI-'):
                    node_name = node_name[8:]  # 移除 'ComfyUI-' 前缀
                elif node_name.startswith('comfyui-'):
                    node_name = node_name[8:]  # 移除 'comfyui-' 前缀

                return node_name

        except (IndexError, AttributeError):
            pass

        return None

    def _get_filtered_node_names(self, references: List[ModelReference]) -> List[str]:
        """
        获取过滤后的节点名称列表

        Args:
            references: 模型引用列表

        Returns:
            List[str]: 过滤后的节点名称列表
        """
        node_names = set()

        for ref in references:
            if ref.source_file:
                # 从缓存中获取节点名称
                node_name = self._node_name_cache.get(ref.source_file)
                if node_name:
                    # 过滤掉UI相关扩展
                    node_name_lower = node_name.lower()
                    if not any(ui_ext in node_name_lower for ui_ext in self._ui_extensions):
                        node_names.add(node_name)

        # 返回排序后的列表，最多显示3个节点
        return sorted(list(node_names))[:3]

