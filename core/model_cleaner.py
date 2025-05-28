"""
模型清理器 - ComfyModelCleaner V2.0

实现安全的模型文件清理功能，支持多种清理模式。
"""

import os
import shutil
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime

try:
    import send2trash
    SEND2TRASH_AVAILABLE = True
except ImportError:
    SEND2TRASH_AVAILABLE = False
    print("⚠️ send2trash 库未安装，回收站功能不可用")

from .model_discovery import ModelInfo
from .utils import format_file_size


@dataclass
class CleanupOperation:
    """清理操作记录"""
    model_info: ModelInfo
    source_path: str
    target_path: Optional[str]
    operation_type: str  # 'delete', 'move', 'backup'
    timestamp: float
    success: bool
    error_message: Optional[str] = None
    record_file_path: Optional[str] = None  # 路径记录文件的位置


@dataclass
class CleanupResult:
    """清理结果"""
    total_operations: int
    successful_operations: int
    failed_operations: int
    total_size_processed: int
    space_freed: int
    operations: List[CleanupOperation]
    operation_log: List[str]
    start_time: float
    end_time: float


class ModelCleaner:
    """模型清理器"""

    def __init__(self):
        self.operations_log = []

    def preview_cleanup(self, unused_models: List[ModelInfo],
                       action_mode: str = "move_to_recycle_bin") -> Dict[str, Any]:
        """
        预览清理操作，显示将要处理的文件列表

        Args:
            unused_models: 未使用的模型列表
            action_mode: 清理模式

        Returns:
            Dict: 预览信息
        """
        total_size = sum(model.size_bytes for model in unused_models)

        # 按目录分组
        models_by_dir = {}
        for model in unused_models:
            if model.directory not in models_by_dir:
                models_by_dir[model.directory] = []
            models_by_dir[model.directory].append(model)

        preview_info = {
            'total_models': len(unused_models),
            'total_size': total_size,
            'total_size_formatted': format_file_size(total_size),
            'action_mode': action_mode,
            'models_by_directory': models_by_dir,
            'operation_description': self._get_operation_description(action_mode),
            'safety_checks': self._perform_safety_checks(unused_models)
        }

        return preview_info

    def execute_cleanup(self, unused_models: List[ModelInfo],
                       action_mode: str, target_folder: Optional[str] = None,
                       confirm: bool = False) -> CleanupResult:
        """
        执行清理操作

        Args:
            unused_models: 未使用的模型列表
            action_mode: 清理模式
            target_folder: 目标文件夹（用于移动操作）
            confirm: 是否确认执行

        Returns:
            CleanupResult: 清理结果
        """
        if not confirm:
            raise ValueError("必须确认才能执行清理操作")

        start_time = time.time()
        operations = []
        operation_log = []

        operation_log.append(f"开始清理操作: {action_mode}")
        operation_log.append(f"处理模型数量: {len(unused_models)}")
        operation_log.append(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        successful_count = 0
        failed_count = 0
        total_size_processed = 0
        space_freed = 0

        for i, model in enumerate(unused_models, 1):
            operation_log.append(f"\n[{i}/{len(unused_models)}] 处理: {model.name}")

            try:
                operation = self._execute_single_operation(
                    model, action_mode, target_folder
                )
                operations.append(operation)

                if operation.success:
                    successful_count += 1
                    total_size_processed += model.size_bytes
                    if action_mode in ['move_to_recycle_bin', 'delete']:
                        space_freed += model.size_bytes
                    operation_log.append(f"  ✅ 成功: {operation.operation_type}")
                else:
                    failed_count += 1
                    operation_log.append(f"  ❌ 失败: {operation.error_message}")

            except Exception as e:
                failed_count += 1
                error_op = CleanupOperation(
                    model_info=model,
                    source_path=model.path,
                    target_path=None,
                    operation_type=action_mode,
                    timestamp=time.time(),
                    success=False,
                    error_message=str(e)
                )
                operations.append(error_op)
                operation_log.append(f"  ❌ 异常: {str(e)}")

        end_time = time.time()
        operation_log.append(f"\n清理完成!")
        operation_log.append(f"成功: {successful_count}, 失败: {failed_count}")
        operation_log.append(f"处理大小: {format_file_size(total_size_processed)}")
        operation_log.append(f"释放空间: {format_file_size(space_freed)}")
        operation_log.append(f"耗时: {end_time - start_time:.2f} 秒")

        # 创建路径记录文件（双重备份策略）
        if successful_count > 0:
            try:
                record_files = self._create_dual_path_records(operations, action_mode, target_folder)

                if record_files['main_record']:
                    operation_log.append(f"主记录文件已创建: {record_files['main_record']}")

                if record_files['target_record']:
                    operation_log.append(f"目标记录文件已创建: {record_files['target_record']}")

                # 更新操作记录中的记录文件路径（使用主记录路径）
                main_record_path = record_files['main_record'] or record_files['target_record']
                for op in operations:
                    if op.success:
                        op.record_file_path = main_record_path

            except Exception as e:
                operation_log.append(f"⚠️ 创建路径记录文件失败: {str(e)}")

        return CleanupResult(
            total_operations=len(unused_models),
            successful_operations=successful_count,
            failed_operations=failed_count,
            total_size_processed=total_size_processed,
            space_freed=space_freed,
            operations=operations,
            operation_log=operation_log,
            start_time=start_time,
            end_time=end_time
        )

    def _execute_single_operation(self, model: ModelInfo, action_mode: str,
                                 target_folder: Optional[str]) -> CleanupOperation:
        """执行单个清理操作"""
        source_path = model.path
        timestamp = time.time()

        try:
            if action_mode == "move_to_recycle_bin":
                return self._move_to_recycle_bin(model, timestamp)
            elif action_mode == "move_to_folder":
                if not target_folder:
                    raise ValueError("移动到文件夹需要指定目标文件夹")
                return self._move_to_folder(model, target_folder, timestamp)
            elif action_mode == "move_to_backup":
                return self._move_to_backup(model, timestamp, target_folder)
            else:
                raise ValueError(f"不支持的操作模式: {action_mode}")

        except Exception as e:
            return CleanupOperation(
                model_info=model,
                source_path=source_path,
                target_path=None,
                operation_type=action_mode,
                timestamp=timestamp,
                success=False,
                error_message=str(e)
            )

    def _move_to_recycle_bin(self, model: ModelInfo, timestamp: float) -> CleanupOperation:
        """移动到回收站"""
        if not SEND2TRASH_AVAILABLE:
            raise RuntimeError("send2trash 库未安装，无法使用回收站功能")

        source_path = Path(model.path)
        if not source_path.exists():
            raise FileNotFoundError(f"文件不存在: {source_path}")

        # 使用 send2trash 安全删除
        if SEND2TRASH_AVAILABLE:
            import send2trash
            send2trash.send2trash(str(source_path))
        else:
            raise RuntimeError("send2trash 库未安装，无法使用回收站功能")

        return CleanupOperation(
            model_info=model,
            source_path=str(source_path),
            target_path="回收站",
            operation_type="move_to_recycle_bin",
            timestamp=timestamp,
            success=True
        )

    def _move_to_folder(self, model: ModelInfo, target_folder: str,
                       timestamp: float) -> CleanupOperation:
        """移动到指定文件夹"""
        source_path = Path(model.path)
        target_dir = Path(target_folder)

        if not source_path.exists():
            raise FileNotFoundError(f"文件不存在: {source_path}")

        # 创建目标目录
        target_dir.mkdir(parents=True, exist_ok=True)

        # 保持目录结构
        relative_path = source_path.relative_to(source_path.parent.parent)
        target_path = target_dir / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # 移动文件或目录
        if source_path.is_file():
            shutil.move(str(source_path), str(target_path))
        else:
            shutil.move(str(source_path), str(target_path))

        return CleanupOperation(
            model_info=model,
            source_path=str(source_path),
            target_path=str(target_path),
            operation_type="move_to_folder",
            timestamp=timestamp,
            success=True
        )

    def _move_to_backup(self, model: ModelInfo, timestamp: float,
                       base_backup_folder: Optional[str] = None) -> CleanupOperation:
        """移动到备份文件夹"""
        # 使用用户指定的备份文件夹，如果没有则使用默认值
        if base_backup_folder:
            # 在用户指定的文件夹下创建带时间戳的子文件夹
            backup_folder = f"{base_backup_folder}/model_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        else:
            # 使用默认的备份文件夹名称
            backup_folder = f"model_backups_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        return self._move_to_folder(model, backup_folder, timestamp)

    def _get_operation_description(self, action_mode: str) -> str:
        """获取操作描述"""
        descriptions = {
            'preview_only': '仅预览，不执行任何操作',
            'move_to_recycle_bin': '移动到系统回收站（可恢复）',
            'move_to_folder': '移动到指定文件夹',
            'move_to_backup': '移动到自动创建的备份文件夹'
        }
        return descriptions.get(action_mode, '未知操作')

    def _perform_safety_checks(self, unused_models: List[ModelInfo]) -> List[str]:
        """执行安全检查"""
        warnings = []

        # 检查大文件
        large_files = [m for m in unused_models if m.size_bytes > 1024 * 1024 * 1024]  # >1GB
        if large_files:
            warnings.append(f"发现 {len(large_files)} 个大文件 (>1GB)，请仔细确认")

        # 检查最近修改的文件
        recent_files = [m for m in unused_models if time.time() - m.modified_time < 7 * 24 * 3600]  # 7天内
        if recent_files:
            warnings.append(f"发现 {len(recent_files)} 个最近修改的文件 (7天内)，请仔细确认")

        # 检查回收站功能
        if not SEND2TRASH_AVAILABLE:
            warnings.append("send2trash 库未安装，无法使用回收站功能")

        return warnings

    def _create_path_record(self, operations: List[CleanupOperation],
                           target_dir: Optional[str] = None) -> str:
        """
        创建路径记录文件，记录所有模型的原始路径信息

        Args:
            operations: 清理操作列表
            target_dir: 目标目录，如果为None则保存在ComfyModelCleaner目录

        Returns:
            str: 记录文件的路径
        """
        # 确定记录文件保存位置
        if target_dir:
            record_dir = Path(target_dir)
        else:
            # 保存在ComfyModelCleaner目录下的records子目录
            current_dir = Path(__file__).parent.parent
            record_dir = current_dir / "records"

        record_dir.mkdir(parents=True, exist_ok=True)

        # 生成记录文件名
        timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        record_filename = f"model_cleanup_record_{timestamp_str}.txt"
        record_path = record_dir / record_filename

        # 写入记录文件
        with open(record_path, 'w', encoding='utf-8') as f:
            f.write("ComfyModelCleaner 模型清理路径记录\n")
            f.write("=" * 50 + "\n")
            f.write(f"清理时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"操作类型: {operations[0].operation_type if operations else 'unknown'}\n")
            f.write(f"处理模型数量: {len(operations)}\n")
            f.write("\n")

            f.write("模型路径记录:\n")
            f.write("-" * 50 + "\n")

            for i, op in enumerate(operations, 1):
                f.write(f"{i}. 模型名称: {op.model_info.name}\n")
                f.write(f"   原始路径: {op.source_path}\n")
                if op.target_path:
                    f.write(f"   目标路径: {op.target_path}\n")
                f.write(f"   操作状态: {'成功' if op.success else '失败'}\n")
                if op.error_message:
                    f.write(f"   错误信息: {op.error_message}\n")
                f.write(f"   文件大小: {format_file_size(op.model_info.size_bytes)}\n")
                f.write("\n")

            f.write("\n恢复说明:\n")
            f.write("-" * 50 + "\n")
            f.write("如需恢复模型到原始位置，请按照以下步骤操作:\n")
            f.write("1. 找到对应的模型文件（在目标路径或回收站中）\n")
            f.write("2. 将模型文件移动回原始路径\n")
            f.write("3. 确保目录结构正确\n")
            f.write("4. 重新启动ComfyUI以刷新模型列表\n")

        return str(record_path)

    def _create_dual_path_records(self, operations: List[CleanupOperation],
                                 action_mode: str, target_folder: Optional[str] = None) -> Dict[str, Optional[str]]:
        """
        创建双重路径记录文件

        Args:
            operations: 清理操作列表
            action_mode: 操作模式
            target_folder: 目标文件夹

        Returns:
            Dict: {'main_record': 主记录路径, 'target_record': 目标记录路径}
        """
        result: Dict[str, Optional[str]] = {'main_record': None, 'target_record': None}

        # 1. 总是在ComfyModelCleaner/records目录创建主记录
        try:
            main_record_path = self._create_path_record(operations, None)
            result['main_record'] = main_record_path
        except Exception as e:
            print(f"⚠️ 创建主记录文件失败: {str(e)}")

        # 2. 根据操作模式决定是否创建目标记录
        target_dir = None

        if action_mode == "move_to_folder" and target_folder:
            target_dir = target_folder
        elif action_mode == "move_to_backup":
            # 从第一个成功操作中获取备份目录
            for op in operations:
                if op.success and op.target_path and op.target_path != "回收站":
                    target_dir = str(Path(op.target_path).parent)
                    break
        # 对于move_to_recycle_bin，不创建目标记录（回收站中的文件可能被系统清理）

        # 3. 如果有目标目录，创建目标记录
        if target_dir:
            try:
                target_record_path = self._create_path_record(operations, target_dir)
                result['target_record'] = target_record_path
            except Exception as e:
                print(f"⚠️ 创建目标记录文件失败: {str(e)}")

        return result


