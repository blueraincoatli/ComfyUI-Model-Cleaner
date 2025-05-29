"""
ComfyModelCleaner Nodes - 清理版本

只包含必要的节点：ModelScannerNode 和 InteractiveModelCleanerNode
"""

import sys
from pathlib import Path
from server import PromptServer
import json

from .model_cleaner_server import ModelCleanerMessageHolder

# Initialize I18nManager and set language early
from .core.i18n import i18n, get_t
import os

# --- 新增的语言检测逻辑 ---
def get_comfyui_language_setting():
    default_lang = 'en'
    
    # 1. 尝试从 comfy.settings.json 读取
    try:
        # 假设 ComfyUI 根目录可以通过 __file__ 向上追溯两层 (custom_nodes -> ComfyUI)
        # 或者需要更可靠的方式确定根目录
        comfyui_root_path = Path(__file__).parent.parent.parent 
        # 如果你的插件在 ComfyUI/custom_nodes/YourPluginName/your_nodes.py
        # 则 Path(__file__).parent 是 YourPluginName
        # Path(__file__).parent.parent 是 custom_nodes
        # Path(__file__).parent.parent.parent 是 ComfyUI
        
        settings_file_path = comfyui_root_path / "user" / "default" / "comfy.settings.json"
        
        if settings_file_path.exists():
            with open(settings_file_path, 'r', encoding='utf-8') as f:
                settings_data = json.load(f)
                locale_setting = settings_data.get("Comfy.Locale")
                if locale_setting and isinstance(locale_setting, str):
                    print(f"ComfyModelCleaner I18n: Language read from comfy.settings.json: {locale_setting}")
                    # "zh" or "en" etc.
                    return locale_setting.split('-')[0].lower() # "zh-CN" -> "zh"
    except Exception as e:
        print(f"ComfyModelCleaner I18n: Error reading comfy.settings.json: {e}. Falling back.")
        
    # 2. 回退到环境变量
    env_lang = os.environ.get('COMFYUI_LANG')
    if env_lang:
        print(f"ComfyModelCleaner I18n: Language from COMFYUI_LANG env var: {env_lang}")
        return env_lang.split('-')[0].lower()
        
    # 3. 默认语言
    print(f"ComfyModelCleaner I18n: Using default language: {default_lang}")
    return default_lang

comfyui_final_lang = get_comfyui_language_setting()
i18n.set_language(comfyui_final_lang)
# --- 结束新增的语言检测逻辑 ---

# Ensure current directory in Python path
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

try:
    from .core.scanner_v2 import ModelScannerV2
    from .core.utils import format_file_size
except ImportError:
    # 如果相对导入失败，尝试绝对导入
    try:
        from core.scanner_v2 import ModelScannerV2
        from core.utils import format_file_size
    except ImportError as e:
        print(get_t("nodes.py.log_import_error", error=e))
        print(get_t("nodes.py.log_current_directory", current_dir=current_dir))
        print(get_t("nodes.py.log_python_path", python_path=sys.path[:3]))
        raise


class ModelScannerNode:
    """
    模型扫描节点 - 分析模型使用情况并生成报告
    """

    CATEGORY = "model_management"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("scan_report", "unused_models_list")
    FUNCTION = "scan_models"

    # 类级别的扫描器实例，用于取消操作
    _current_scanner = None

    @classmethod
    def INPUT_TYPES(cls):
        # Use get_t for node display names if possible, though INPUT_TYPES is class-level
        # This might be tricky for dynamic language switching of input names themselves
        # For now, keeping input names in English, but widget labels could be translated
        return {
            "required": {
                "scan_mode": (["normal", "github_enhanced"], {"default": "normal"}),
                "confidence_threshold": ("INT", {"default": 70, "min": 0, "max": 100}),
            },
            "optional": {
                "include_checkpoints": ("BOOLEAN", {"default": False}),
                "include_loras": ("BOOLEAN", {"default": False}),
                "include_embeddings": ("BOOLEAN", {"default": False}),
                "include_vae": ("BOOLEAN", {"default": False}),
                "include_controlnet": ("BOOLEAN", {"default": False}),
                "include_upscale_models": ("BOOLEAN", {"default": False}),
                "include_style_models": ("BOOLEAN", {"default": False}),
                "include_clip": ("BOOLEAN", {"default": False}),
                "custom_paths": ("STRING", {"default": "", "multiline": True}),
                "clear_cache": ("BOOLEAN", {"default": False}),
            }
        }

    def scan_models(self, scan_mode, confidence_threshold,
                   include_checkpoints=False, include_loras=False,
                   include_embeddings=False, include_vae=False, include_controlnet=False,
                   include_upscale_models=False, include_style_models=False, include_clip=False,
                   custom_paths="", clear_cache=False):
        """
        扫描模型并分析使用情况
        """
        try:
            # Update language at the beginning of the execution, in case it changed
            current_comfyui_lang = os.environ.get('COMFYUI_LANG', i18n.current_language) # Get current lang or keep existing
            i18n.set_language(current_comfyui_lang)

            print(get_t("scanner_node.scan_start_log"))

            # 清除缓存（如果用户选择）
            if clear_cache:
                print(get_t("scanner_node.clear_cache_log"))
                self._clear_all_caches()

            # 初始化V2扫描器
            print(get_t("scanner_node.init_scanner_log"))
            scanner_v2 = ModelScannerV2()

            # 保存当前扫描器实例，用于取消操作
            ModelScannerNode._current_scanner = scanner_v2

            # 配置V2扫描选项
            scan_config = {
                'checkpoints': include_checkpoints,
                'loras': include_loras,
                'embeddings': include_embeddings,
                'vae': include_vae,
                'controlnet': include_controlnet,
                'upscale_models': include_upscale_models,
                'style_models': include_style_models,
                'clip': include_clip,
                'confidence_threshold': confidence_threshold,
                'github_analysis': scan_mode == "github_enhanced",
                'clear_cache': clear_cache
            }

            # 执行V2扫描
            scan_result_v2 = scanner_v2.scan_unused_models(scan_config)

            # 生成V2报告
            print(get_t("scanner_node.report_generation_log"))
            report = self._generate_v2_report(scan_result_v2)

            # 生成未使用模型列表（JSON格式）
            unused_models_list = self._generate_unused_models_list(scan_result_v2)

            # 发送进度更新到前端
            try:
                if hasattr(PromptServer, 'instance') and PromptServer.instance:
                    PromptServer.instance.send_sync("comfy.model.cleaner.scan.complete", {
                        "total_models": scan_result_v2.total_models,
                        "unused_models": len(scan_result_v2.unused_models),
                        "potential_savings": scan_result_v2.potential_savings_bytes / (1024 * 1024)
                    })
            except Exception as e:
                print(get_t("scanner_node.error_sending_progress", error=e))

            return (report, unused_models_list)

        except Exception as e:
            error_msg = get_t("scanner_node.error_log", error=str(e))
            print(f"ModelCleaner Error: {error_msg}")
            empty_list = '{"total_unused_models": 0, "models": []}'
            return (error_msg, empty_list)
        finally:
            # 清理扫描器引用
            ModelScannerNode._current_scanner = None

    @classmethod
    def cancel_current_scan(cls):
        """取消当前正在进行的扫描"""
        if cls._current_scanner and cls._current_scanner.reporter:
            print(get_t("scanner_node.user_cancel_log"))
            cls._current_scanner.reporter.cancel()
            return True
        return False

    def _generate_v2_report(self, scan_result_v2) -> str:
        """生成V2扫描结果报告"""
        confidence_threshold = scan_result_v2.scan_config.get('confidence_threshold', 70)

        report_lines = [
            get_t("scan_report.header"),
            get_t("scan_report.scan_time", scan_time=scan_result_v2.scan_time),
            "",
            get_t("scan_report.stats_header"),
            get_t("scan_report.total_models_found", count=scan_result_v2.total_models),
            get_t("scan_report.single_file_models", count=scan_result_v2.single_file_models),
            get_t("scan_report.directory_models", count=scan_result_v2.directory_models),
            "",
            get_t("scan_report.usage_analysis_header"),
            get_t("scan_report.confirmed_used", count=len(scan_result_v2.used_models)),
            get_t("scan_report.likely_used", count=len(scan_result_v2.uncertain_models), threshold=confidence_threshold),
            get_t("scan_report.likely_unused", count=len(scan_result_v2.unused_models), threshold=confidence_threshold),
            "",
            get_t("scan_report.storage_analysis_header"),
            get_t("scan_report.total_space_occupied", size=format_file_size(scan_result_v2.total_size_bytes)),
            get_t("scan_report.used_models_space", size=format_file_size(scan_result_v2.used_size_bytes)),
            get_t("scan_report.unused_models_space", size=format_file_size(scan_result_v2.unused_size_bytes)),
            get_t("scan_report.potential_savings", size=format_file_size(scan_result_v2.potential_savings_bytes)),
            ""
        ]

        # 显示很可能未使用的模型
        if scan_result_v2.unused_models:
            report_lines.extend([
                get_t("scan_report.unused_models_header", threshold=confidence_threshold),
                ""
            ])

            # 按目录分组显示
            models_by_dir = {}
            for model in scan_result_v2.unused_models:
                dir_name = model.directory
                if dir_name not in models_by_dir:
                    models_by_dir[dir_name] = []
                models_by_dir[dir_name].append(model)

            for dir_name, models in models_by_dir.items():
                report_lines.append(get_t("scan_report.directory_group", dir_name=dir_name))
                for model in models[:10]:  # 显示前10个
                    model_id = f"{model.directory}/{model.name}"
                    confidence_info = scan_result_v2.confidence_analysis.get(model_id)
                    confidence_score = confidence_info.total_score if confidence_info else 0

                    size_str = format_file_size(model.size_bytes)
                    unused_confidence = 100 - confidence_score
                    report_lines.append(get_t("scan_report.model_item", name=model.name, size=size_str, confidence=unused_confidence))

                if len(models) > 10:
                    report_lines.append(get_t("scan_report.more_models", count=len(models) - 10))
                report_lines.append("")

        report_lines.extend([
            "",
            get_t("scan_report.notice_header"),
            get_t("scan_report.notice_text")
        ])

        return "\n".join(report_lines)

    def _generate_unused_models_list(self, scan_result_v2) -> str:
        """生成未使用模型列表的JSON格式"""
        import json

        models_list = []
        for model in scan_result_v2.unused_models:
            model_id = f"{model.directory}/{model.name}"
            confidence_info = scan_result_v2.confidence_analysis.get(model_id)
            confidence_score = confidence_info.total_score if confidence_info else 0
            unused_confidence = 100 - confidence_score

            model_dict = {
                "name": model.name,
                "path": str(model.path),
                "relative_path": model.relative_path,
                "size_bytes": model.size_bytes,
                "size_formatted": format_file_size(model.size_bytes),
                "modified_time": model.modified_time,
                "access_time": getattr(model, 'access_time', model.modified_time),
                "model_type": model.model_type,
                "directory": model.directory,
                "extension": model.extension,
                "unused_confidence": round(unused_confidence, 1)
            }
            models_list.append(model_dict)

        result = {
            "total_unused_models": len(models_list),
            "total_size_bytes": sum(m["size_bytes"] for m in models_list),
            "models": models_list
        }

        return json.dumps(result, ensure_ascii=False, indent=2)

    def _clear_all_caches(self):
        """清除所有缓存文件"""
        try:
            cache_files = [
                "model_cache.json",
                "node_analysis_cache.json",
                "github_analysis_cache.json",
                "github_cache.json",  # GitHub分析器的缓存文件
                "workflow_analysis_cache.json"
            ]

            cleared_count = 0
            for cache_file in cache_files:
                cache_path = current_dir / cache_file
                if cache_path.exists():
                    cache_path.unlink()
                    cleared_count += 1
                    print(get_t("scanner_node.caches_cleared_log", cache_file=cache_file))

            # 同时清除matcher中的内存缓存
            try:
                from .core.matcher import IntelligentMatcher
                # 创建一个新的matcher实例来清除类级别的缓存
                matcher = IntelligentMatcher()
                matcher.match_cache.clear()
                matcher._node_name_cache.clear()
                print(get_t("scanner_node.memory_cache_cleared_log"))
            except Exception as e:
                print(get_t("scanner_node.error_clearing_memory_cache", error=e))

            if cleared_count > 0:
                print(get_t("scanner_node.cleared_cache_count_log", count=cleared_count))
            else:
                print(get_t("scanner_node.no_cache_to_clear_log"))

        except Exception as e:
            print(get_t("scanner_node.error_clearing_cache_log", error=e))

        print(get_t("scanner_node.cache_clear_complete_log"))


class InteractiveModelCleanerNode:
    """
    交互式模型清理器 - 在节点内部显示模型选择界面
    """

    CATEGORY = "model_management"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("cleanup_report",)
    FUNCTION = "display_and_clean"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        # For INPUT_TYPES, widget labels might be translatable in JS later.
        # Node's own name and input/output names are harder to make dynamic per language in Python alone.
        return {
            "required": {
                "show_text_out": ("STRING", {"forceInput": True, "tooltip": "Scan report from Show Text node"}),
                "unused_models_json": ("STRING", {"forceInput": True}),
                "action_mode": (["dry_run", "move_to_backup", "move_to_recycle_bin"], {"default": "dry_run"}),
                "backup_base_folder": ("STRING", {"default": "model_backups", "tooltip": "Base path for backup folder (relative to ComfyUI root or absolute)"}),
            },
            "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO", "id": "UNIQUE_ID"},
        }

    def display_and_clean(self, show_text_out, unused_models_json, action_mode, backup_base_folder, id, **kwargs):
        """在节点内显示模型选择界面并处理清理操作"""
        try:
            import json
            # Update language at the beginning of the execution
            current_comfyui_lang = os.environ.get('COMFYUI_LANG', i18n.current_language)
            i18n.set_language(current_comfyui_lang)

            # 解析未使用模型数据
            try:
                models_data = json.loads(unused_models_json)
            except json.JSONDecodeError as e:
                return (f"❌ {get_t('error_parsing_model_data', default_text='Error: Could not parse model data')}: {str(e)}",)

            if not models_data.get('models'):
                return (get_t('interactive_cleaner.no_models_found', default_text="ℹ️ No unused models found."),)

            # 发送数据到前端用于交互
            try:
                from server import PromptServer
                # print(f"InteractiveModelCleaner: 发送数据到前端，节点ID: {id}")
                print(get_t("interactive_cleaner.log_send_data", id=id))
                # print(f"InteractiveModelCleaner: 模型数量: {len(models_data['models'])}")
                print(get_t("interactive_cleaner.log_model_count", count=len(models_data['models'])))

                data_to_send = {
                    "id": id,
                    "models": models_data['models'],
                    "action_mode": action_mode,
                    "backup_folder": backup_base_folder,
                    "lang": i18n.current_language
                }

                PromptServer.instance.send_sync("interactive-model-cleaner-data", data_to_send)
                # print(f"InteractiveModelCleaner: 数据发送完成")
                print(get_t("interactive_cleaner.log_data_sent"))

                # print(f"InteractiveModelCleaner: 等待用户选择...")
                print(get_t("interactive_cleaner.log_waiting_user_selection"))
                selected_indices = ModelCleanerMessageHolder.waitForMessage(id, asList=True)
                # print(f"InteractiveModelCleaner: 用户选择了索引: {selected_indices}")
                print(get_t("interactive_cleaner.log_user_selected_indices", indices=selected_indices))

                # 处理用户选择的模型
                cleanup_report = self._process_selected_indices(models_data, selected_indices, action_mode, backup_base_folder)

                return cleanup_report

            except ImportError:
                # 如果在测试环境中，返回模拟的交互界面
                fallback_report = self._generate_fallback_interface(models_data, action_mode, backup_base_folder)
                return fallback_report
            except Exception as e:
                # 如果消息处理失败，返回错误
                error_msg = f"❌ {get_t('error_waiting_user_selection', default_text='Error waiting for user selection')}: {str(e)}"
                return (error_msg,)

        except Exception as e:
            error_msg = f"{get_t('error_in_node_cleanup', default_text='Error during in-node cleanup')}: {str(e)}"
            print(f"InteractiveModelCleaner Error: {error_msg}")
            import traceback
            traceback.print_exc()
            return (error_msg,)

    def _process_selected_indices(self, models_data, selected_indices, action_mode, backup_folder):
        """处理用户通过索引选择的模型"""
        try:
            # 导入清理器
            from .core.model_cleaner import ModelCleaner
            from .core.model_discovery import ModelInfo

            models = models_data['models']

            if not selected_indices:
                return (get_t("interactive_cleaner.no_models_selected"),)

            # 验证索引有效性
            valid_indices = [i for i in selected_indices if 0 <= i < len(models)]
            if not valid_indices:
                return (get_t("interactive_cleaner.invalid_indices"),)

            selected_models_data = [models[i] for i in valid_indices]

            # 转换为 ModelInfo 对象
            unused_models = []
            for model_data in selected_models_data:
                model_info = ModelInfo(
                    name=model_data['name'],
                    path=model_data['path'],
                    relative_path=model_data['relative_path'],
                    size_bytes=model_data['size_bytes'],
                    modified_time=model_data['modified_time'],
                    access_time=model_data.get('access_time', model_data['modified_time']),
                    model_type=model_data['model_type'],
                    directory=model_data['directory'],
                    extension=model_data['extension'],
                    confidence_factors={}
                )
                unused_models.append(model_info)

            # 初始化清理器
            cleaner = ModelCleaner()

            # 预览模式
            if action_mode == "dry_run":
                preview_info = cleaner.preview_cleanup(unused_models, "move_to_backup")

                result_lines = [
                    get_t("interactive_cleaner.preview_header"),
                    "=" * 50,
                    "",
                    get_t("interactive_cleaner.stats_header"),
                    get_t("interactive_cleaner.selected_models_count", count=preview_info['total_models']),
                    get_t("interactive_cleaner.total_size_processed", size=preview_info['total_size_formatted']),
                    get_t("interactive_cleaner.action_mode", mode=get_t("dry_run_mode_label", default_text="Preview Mode")),
                    "",
                    get_t("interactive_cleaner.preview_info")
                ]
                return ("\n".join(result_lines),)

            # 实际清理操作
            if action_mode == "move_to_backup":
                cleaner_action_mode = "move_to_backup"
                target_folder = backup_folder
            elif action_mode == "move_to_recycle_bin":
                cleaner_action_mode = "move_to_recycle_bin"
                target_folder = None
            else:
                return (get_t("interactive_cleaner.unsupported_action"),)

            # 执行清理
            cleanup_result = cleaner.execute_cleanup(
                unused_models, cleaner_action_mode, target_folder, confirm=True
            )

            # 生成报告
            result_lines = [
                get_t("interactive_cleaner.title"),
                "=" * 50,
                "",
                get_t("interactive_cleaner.stats_header"),
                get_t("interactive_cleaner.selected_models_count", count=len(selected_models_data)),
                get_t("interactive_cleaner.success_count", count=cleanup_result.successful_operations),
                get_t("interactive_cleaner.fail_count", count=cleanup_result.failed_operations),
                get_t("interactive_cleaner.total_size_processed", size=format_file_size(cleanup_result.total_size_processed)),
                get_t("interactive_cleaner.space_freed", size=format_file_size(cleanup_result.space_freed)),
                get_t("interactive_cleaner.action_mode", mode=action_mode),
                get_t("interactive_cleaner.processing_time", seconds=cleanup_result.end_time - cleanup_result.start_time),
            ]

            # 显示备份位置
            if action_mode == "move_to_backup" and cleanup_result.successful_operations > 0:
                for op in cleanup_result.operations:
                    if op.success and op.target_path:
                        backup_path = str(Path(op.target_path).parent)
                        result_lines.append(get_t("interactive_cleaner.backup_location", path=backup_path))
                        break

            # 显示路径记录文件信息
            for op in cleanup_result.operations:
                if op.success and op.record_file_path:
                    result_lines.extend([
                        "",
                        get_t("interactive_cleaner.record_file_created", path=op.record_file_path),
                        get_t("interactive_cleaner.record_file_info")
                    ])
                    break

            # 显示失败的操作
            failed_operations = [op for op in cleanup_result.operations if not op.success]
            if failed_operations:
                result_lines.extend([
                    "",
                    get_t("interactive_cleaner.failed_ops_header"),
                ])
                for op in failed_operations[:5]:  # 显示前5个失败操作
                    result_lines.append(get_t("interactive_cleaner.failed_op_item", name=op.model_info.name, error=op.error_message))

                if len(failed_operations) > 5:
                    result_lines.append(get_t("interactive_cleaner.more_failed_ops", count=len(failed_operations) - 5))

            if cleanup_result.successful_operations > 0:
                result_lines.extend([
                    "",
                    get_t("interactive_cleaner.cleanup_complete_header"),
                    get_t("interactive_cleaner.cleanup_complete_message", 
                          count=cleanup_result.successful_operations, 
                          size=format_file_size(cleanup_result.space_freed))
                ])

            return ("\n".join(result_lines),)

        except Exception as e:
            error_msg = f"{get_t('error_in_node_cleanup', default_text='Error during in-node cleanup')}: {str(e)}"
            print(f"InteractiveModelCleaner Error: {error_msg}")
            import traceback
            traceback.print_exc()
            return (error_msg,)

    def _generate_fallback_interface(self, models_data, action_mode, backup_folder):
        """生成回退界面（用于测试环境）"""
        models = models_data['models']
        total_models = len(models)
        total_size = models_data.get('total_size_bytes', 0)

        interface_lines = [
            get_t("interactive_cleaner.test_mode_header"),
            "=" * 60,
            "",
            get_t("interactive_cleaner.stats_header"),
            get_t("interactive_cleaner.test_mode_scan_results", total_models=total_models, total_size=format_file_size(total_size)),
            get_t("interactive_cleaner.test_mode_action", action_mode=action_mode),
            get_t("interactive_cleaner.test_mode_backup_folder", backup_folder=backup_folder),
            "",
            get_t("interactive_cleaner.test_mode_info", action_mode=action_mode, backup_folder=backup_folder),
        ]

        return ("\n".join(interface_lines),)


# Node mappings for ComfyUI
NODE_CLASS_MAPPINGS = {
    "ModelScannerNode": ModelScannerNode,
    "InteractiveModelCleanerNode": InteractiveModelCleanerNode,
}

# Node display names can be translated if ComfyUI supports it directly for these mappings.
# For now, keeping them in English as a base. Front-end JS can handle dynamic title translation.
NODE_DISPLAY_NAME_MAPPINGS = {
    "ModelScannerNode": "🔍 Model Scanner",
    "InteractiveModelCleanerNode": "📋 Interactive Model Cleaner",
}
