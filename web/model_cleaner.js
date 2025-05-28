/**
 * ComfyModelCleaner - Frontend JavaScript for ComfyUI integration
 *
 * This script provides the frontend interface for the model cleaner plugin,
 * including interactive model selection and cleanup functionality.
 */

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// Plugin configuration
const PLUGIN_NAME = "ComfyModelCleaner";
const MESSAGE_TYPES = {
    SCAN_COMPLETE: "comfy.model.cleaner.scan.complete",
    SCAN_PROGRESS: "comfy.model.cleaner.scan.progress",
    CLEANUP_COMPLETE: "comfy.model.cleaner.cleanup.complete",
    MODEL_CLEANER_DATA: "model-cleaner-data"
};

// 模型清理器状态管理
class ModelCleanerState {
    constructor() {
        this.paused = false;
        this.currentNodeId = null;
        this.models = [];
        this.selectedIndices = new Set();
    }

    setPaused(paused, nodeId = null) {
        this.paused = paused;
        this.currentNodeId = nodeId;
        if (!paused) {
            this.models = [];
            this.selectedIndices.clear();
        }
    }

    isPaused() {
        return this.paused;
    }

    getCurrentNodeId() {
        return this.currentNodeId;
    }

    setModels(models) {
        this.models = models;
        this.selectedIndices.clear();
    }

    toggleModel(index) {
        if (this.selectedIndices.has(index)) {
            this.selectedIndices.delete(index);
        } else {
            this.selectedIndices.add(index);
        }
    }

    getSelectedIndices() {
        return Array.from(this.selectedIndices);
    }

    getSelectedCount() {
        return this.selectedIndices.size;
    }
}

const modelCleanerState = new ModelCleanerState();

// Plugin state
let scanResults = null;
let isScanning = false;

// 发送消息到后端
function sendMessage(nodeId, message) {
    const body = new FormData();
    body.append('message', message);
    body.append('id', nodeId);
    api.fetchApi("/model_cleaner_message", { method: "POST", body });
}

function sendCancel() {
    api.fetchApi("/model_cleaner_cancel", { method: "POST" });
    modelCleanerState.setPaused(false);
}

function sendStart() {
    api.fetchApi("/model_cleaner_start", { method: "POST" });
}

// 发送扫描取消请求
function sendScanCancel() {
    console.log("发送扫描取消请求...");
    showNotification("正在取消扫描...", "warning");

    api.fetchApi("/model_scanner_cancel", { method: "POST" })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showNotification("扫描已取消", "warning");
                isScanning = false;

                // 更新所有扫描节点的状态
                const nodes = app.graph._nodes;
                if (nodes) {
                    nodes.forEach(node => {
                        if (node.type === "ModelScannerNode") {
                            node.scanStatus = "cancelled";
                            node.scanProgress = 0;
                            node.setDirtyCanvas(true);
                        }
                    });
                }
            } else {
                showNotification("取消扫描失败: " + (data.error || "未知错误"), "error");
            }
        })
        .catch(error => {
            console.error("取消扫描请求失败:", error);
            showNotification("取消扫描请求失败", "error");
        });
}

/**
 * Show a notification to the user
 */
function showNotification(message, type = 'info') {
    // Use ComfyUI's notification system if available
    if (app.ui && app.ui.dialog) {
        const dialog = app.ui.dialog;
        const color = type === 'error' ? '#ff6b6b' :
                     type === 'success' ? '#51cf66' :
                     type === 'warning' ? '#ffd43b' : '#339af0';

        // Create a simple notification
        const notification = document.createElement('div');
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: ${color};
            color: white;
            padding: 12px 20px;
            border-radius: 6px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            z-index: 10000;
            max-width: 400px;
            font-family: Arial, sans-serif;
            font-size: 14px;
        `;
        notification.textContent = message;

        document.body.appendChild(notification);

        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 5000);
    } else {
        // Fallback to console and alert
        console.log(`[${PLUGIN_NAME}] ${message}`);
        if (type === 'error') {
            alert(`错误: ${message}`);
        }
    }
}

// 创建模型选择UI
function createModelSelectionUI(data) {
    const { id, models, action_mode, backup_folder } = data;

    modelCleanerState.setPaused(true, id);
    modelCleanerState.setModels(models);

    // 创建模态对话框
    const modal = document.createElement('div');
    modal.className = 'model-cleaner-modal';
    modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.8);
        z-index: 10000;
        display: flex;
        justify-content: center;
        align-items: center;
    `;

    const dialog = document.createElement('div');
    dialog.className = 'model-cleaner-dialog';
    dialog.style.cssText = `
        background: #2a2a2a;
        border: 1px solid #555;
        border-radius: 8px;
        padding: 20px;
        max-width: 80%;
        max-height: 80%;
        overflow-y: auto;
        color: #fff;
        font-family: monospace;
    `;

    // 标题
    const title = document.createElement('h2');
    title.textContent = '🎯 选择要删除的模型';
    title.style.cssText = 'margin-top: 0; color: #fff; text-align: center;';

    // 信息栏
    const info = document.createElement('div');
    info.style.cssText = 'margin-bottom: 20px; padding: 10px; background: #333; border-radius: 4px;';
    info.innerHTML = `
        <div>📊 发现 ${models.length} 个可能未使用的模型</div>
        <div>⚙️ 操作模式: ${action_mode}</div>
        <div>📁 备份文件夹: ${backup_folder}</div>
    `;

    // 模型列表
    const modelList = document.createElement('div');
    modelList.style.cssText = 'margin-bottom: 20px; max-height: 400px; overflow-y: auto;';

    models.forEach((model, index) => {
        const modelItem = document.createElement('div');
        modelItem.className = 'model-item';
        modelItem.style.cssText = `
            padding: 8px;
            margin: 4px 0;
            border: 1px solid #555;
            border-radius: 4px;
            cursor: pointer;
            transition: background-color 0.2s;
        `;

        const confidence = model.unused_confidence;
        let icon = '🟢';
        if (confidence >= 90) icon = '🔴';
        else if (confidence >= 80) icon = '🟠';
        else if (confidence >= 70) icon = '🟡';

        modelItem.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <span style="margin-right: 8px;">${icon}</span>
                    <strong>${model.name}</strong>
                </div>
                <div style="font-size: 0.9em; color: #ccc;">
                    ${model.size_formatted} | ${confidence}%
                </div>
            </div>
            <div style="font-size: 0.8em; color: #999; margin-top: 4px;">
                📁 ${model.directory}
            </div>
        `;

        modelItem.addEventListener('click', () => {
            modelCleanerState.toggleModel(index);
            updateModelItemStyle(modelItem, modelCleanerState.selectedIndices.has(index));
            updateButtonStates();
        });

        modelList.appendChild(modelItem);
    });

    // 按钮区域
    const buttonArea = document.createElement('div');
    buttonArea.style.cssText = 'display: flex; justify-content: space-between; align-items: center; margin-top: 20px;';

    const selectionInfo = document.createElement('div');
    selectionInfo.id = 'selection-info';
    selectionInfo.style.cssText = 'color: #ccc;';

    const buttonGroup = document.createElement('div');
    buttonGroup.style.cssText = 'display: flex; gap: 10px;';

    const cancelButton = document.createElement('button');
    cancelButton.textContent = '取消';
    cancelButton.style.cssText = `
        padding: 8px 16px;
        background: #666;
        color: #fff;
        border: none;
        border-radius: 4px;
        cursor: pointer;
    `;
    cancelButton.addEventListener('click', () => {
        document.body.removeChild(modal);
        sendCancel();
    });

    const proceedButton = document.createElement('button');
    proceedButton.id = 'proceed-button';
    proceedButton.textContent = '执行清理';
    proceedButton.disabled = true;
    proceedButton.style.cssText = `
        padding: 8px 16px;
        background: #007acc;
        color: #fff;
        border: none;
        border-radius: 4px;
        cursor: pointer;
    `;
    proceedButton.addEventListener('click', () => {
        const selectedIndices = modelCleanerState.getSelectedIndices();
        if (selectedIndices.length > 0) {
            document.body.removeChild(modal);
            sendMessage(id, selectedIndices.join(','));
            modelCleanerState.setPaused(false);
        }
    });

    buttonGroup.appendChild(cancelButton);
    buttonGroup.appendChild(proceedButton);
    buttonArea.appendChild(selectionInfo);
    buttonArea.appendChild(buttonGroup);

    // 组装对话框
    dialog.appendChild(title);
    dialog.appendChild(info);
    dialog.appendChild(modelList);
    dialog.appendChild(buttonArea);
    modal.appendChild(dialog);

    // 添加到页面
    document.body.appendChild(modal);

    // 初始化按钮状态
    updateButtonStates();

    // 更新模型项样式
    function updateModelItemStyle(item, selected) {
        if (selected) {
            item.style.backgroundColor = '#007acc';
            item.style.borderColor = '#0099ff';
        } else {
            item.style.backgroundColor = 'transparent';
            item.style.borderColor = '#555';
        }
    }

    // 更新按钮状态
    function updateButtonStates() {
        const selectedCount = modelCleanerState.getSelectedCount();
        const selectionInfo = document.getElementById('selection-info');
        const proceedButton = document.getElementById('proceed-button');

        if (selectedCount > 0) {
            selectionInfo.textContent = `已选择 ${selectedCount} 个模型`;
            proceedButton.disabled = false;
            proceedButton.style.backgroundColor = '#007acc';
            proceedButton.style.cursor = 'pointer';
        } else {
            selectionInfo.textContent = '请选择要删除的模型';
            proceedButton.disabled = true;
            proceedButton.style.backgroundColor = '#666';
            proceedButton.style.cursor = 'not-allowed';
        }
    }
}

/**
 * Handle scan completion message
 */
function handleScanComplete(event) {
    const data = event.detail;
    isScanning = false;
    scanResults = data;

    const message = `扫描完成！发现 ${data.total_models} 个模型，其中 ${data.unused_models} 个可能未使用，潜在节省空间 ${data.potential_savings.toFixed(1)} MB`;
    showNotification(message, 'success');

    console.log(`[${PLUGIN_NAME}] 扫描结果:`, data);
}

/**
 * Handle scan progress updates
 */
function handleScanProgress(event) {
    const data = event.detail;
    console.log(`[${PLUGIN_NAME}] 扫描进度: ${data.progress}%`);

    // Update any progress indicators if they exist
    updateProgressIndicators(data);
}

/**
 * Handle cleanup completion
 */
function handleCleanupComplete(event) {
    const data = event.detail;
    const message = `清理完成！处理了 ${data.processed_files} 个文件`;
    showNotification(message, 'success');

    console.log(`[${PLUGIN_NAME}] 清理结果:`, data);
}

/**
 * Update progress indicators in the UI
 */
function updateProgressIndicators(progressData) {
    // Find any ModelScanner nodes and update their progress
    const nodes = app.graph._nodes;
    if (nodes) {
        nodes.forEach(node => {
            if (node.type === "ModelScannerNode") {
                // Add visual progress indicator if node supports it
                if (node.onProgress) {
                    node.onProgress(progressData);
                }
            }
        });
    }
}

/**
 * Add custom styling for model cleaner nodes
 */
function addCustomNodeStyling() {
    const style = document.createElement('style');
    style.textContent = `
        /* Custom styling for ModelCleaner nodes */
        .comfy-node[data-type="ModelScannerNode"] {
            border-left: 4px solid #339af0;
        }

        .comfy-node[data-type="ModelCleanerNode"] {
            border-left: 4px solid #ff6b6b;
        }

        .model-cleaner-progress {
            background: linear-gradient(90deg, #51cf66 0%, #339af0 100%);
            height: 3px;
            border-radius: 2px;
            margin: 4px 0;
            transition: width 0.3s ease;
        }

        .model-cleaner-stats {
            font-size: 11px;
            color: #666;
            margin: 2px 0;
        }
    `;
    document.head.appendChild(style);
}

/**
 * Enhance ModelScanner nodes with additional UI elements
 */
function enhanceModelScannerNodes() {
    const originalNodeCreated = app.graph.onNodeAdded;

    app.graph.onNodeAdded = function(node) {
        if (originalNodeCreated) {
            originalNodeCreated.call(this, node);
        }

        if (node.type === "ModelScannerNode") {
            // Add progress tracking
            node.scanProgress = 0;
            node.scanStatus = "ready";

            // Override the node's onExecuted method to show progress
            const originalOnExecuted = node.onExecuted;
            node.onExecuted = function(message) {
                if (originalOnExecuted) {
                    originalOnExecuted.call(this, message);
                }

                // Update node appearance based on scan results
                this.scanStatus = "completed";
                isScanning = false;
                this.setDirtyCanvas(true);
            };

            // Override onExecutionStart to track scanning state
            const originalOnExecutionStart = node.onExecutionStart;
            node.onExecutionStart = function() {
                if (originalOnExecutionStart) {
                    originalOnExecutionStart.call(this);
                }
                console.log("ModelScannerNode: 开始执行扫描");
                this.scanStatus = "scanning";
                isScanning = true;
                this.setDirtyCanvas(true);
            };

            // Add progress method
            node.onProgress = function(progressData) {
                this.scanProgress = progressData.progress || 0;
                this.scanStatus = "scanning";
                this.setDirtyCanvas(true);
            };

            // Custom drawing for progress indication
            const originalOnDrawForeground = node.onDrawForeground;
            node.onDrawForeground = function(ctx) {
                if (originalOnDrawForeground) {
                    originalOnDrawForeground.call(this, ctx);
                }

                // Draw progress bar if scanning
                if (this.scanStatus === "scanning") {
                    const width = this.size[0];
                    const height = 3;
                    const y = this.size[1] - 10;

                    // Background
                    ctx.fillStyle = "#333";
                    ctx.fillRect(0, y, width, height);

                    // Progress
                    ctx.fillStyle = "#51cf66";
                    ctx.fillRect(0, y, (width * this.scanProgress) / 100, height);

                    // Draw cancel button - 移到左边空白处，避免与输出端口重叠
                    const buttonSize = 20;
                    const buttonX = 5; // 左边边距
                    const buttonY = 5; // 顶部边距

                    // Button background
                    ctx.fillStyle = "#ff6b6b";
                    ctx.fillRect(buttonX, buttonY, buttonSize, buttonSize);

                    // Button text
                    ctx.fillStyle = "#fff";
                    ctx.font = "12px Arial";
                    ctx.textAlign = "center";
                    ctx.fillText("✕", buttonX + buttonSize/2, buttonY + buttonSize/2 + 4);

                    // Store button position for click detection
                    this.cancelButtonBounds = {
                        x: buttonX,
                        y: buttonY,
                        width: buttonSize,
                        height: buttonSize
                    };
                }

                // Draw status indicator
                if (this.scanStatus === "completed") {
                    ctx.fillStyle = "#51cf66";
                    ctx.beginPath();
                    ctx.arc(this.size[0] - 10, 10, 4, 0, Math.PI * 2);
                    ctx.fill();
                }
            };

            // Add click handler for cancel button
            const originalOnMouseDown = node.onMouseDown;
            node.onMouseDown = function(event, localPos, graphCanvas) {
                if (this.scanStatus === "scanning" && this.cancelButtonBounds) {
                    const bounds = this.cancelButtonBounds;
                    if (localPos[0] >= bounds.x && localPos[0] <= bounds.x + bounds.width &&
                        localPos[1] >= bounds.y && localPos[1] <= bounds.y + bounds.height) {
                        // Cancel button clicked
                        sendScanCancel();
                        return true; // Consume the event
                    }
                }

                if (originalOnMouseDown) {
                    return originalOnMouseDown.call(this, event, localPos, graphCanvas);
                }
                return false;
            };
        }
    };
}

/**
 * Add keyboard shortcuts for scan cancellation
 */
function addKeyboardShortcuts() {
    document.addEventListener('keydown', function(event) {
        // Ctrl+Shift+C to cancel scan
        if (event.ctrlKey && event.shiftKey && event.code === 'KeyC') {
            if (isScanning) {
                event.preventDefault();
                sendScanCancel();
                showNotification("键盘快捷键: 扫描取消请求已发送", "info");
            }
        }
        // Escape key to cancel scan (when no other UI elements are focused)
        else if (event.code === 'Escape' && isScanning && !event.target.closest('input, textarea, select')) {
            event.preventDefault();
            sendScanCancel();
            showNotification("Escape键: 扫描取消请求已发送", "info");
        }
    });
}

/**
 * Add context menu options for model cleaner nodes
 */
function addContextMenuOptions() {
    const originalGetNodeMenuOptions = app.getNodeMenuOptions;

    app.getNodeMenuOptions = function(node) {
        const options = originalGetNodeMenuOptions ? originalGetNodeMenuOptions.call(this, node) : [];

        if (node.type === "ModelScannerNode") {
            // Add cancel option if scanning
            if (isScanning || node.scanStatus === "scanning") {
                options.push({
                    content: "🛑 取消扫描",
                    callback: () => {
                        console.log("用户点击取消扫描按钮");
                        sendScanCancel();
                    }
                });
            }

            options.push({
                content: "🔍 快速扫描",
                callback: () => {
                    // Trigger a quick scan
                    const scanModeWidget = node.widgets.find(w => w.name === "scan_mode");
                    if (scanModeWidget) {
                        scanModeWidget.value = "normal";
                    }
                    app.queuePrompt(0, 1);
                }
            });

            options.push({
                content: "🔬 详细扫描",
                callback: () => {
                    // Trigger a detailed scan
                    node.widgets.find(w => w.name === "scan_mode").value = "detailed";
                    app.queuePrompt(0, 1);
                }
            });
        }

        if (node.type === "ModelCleanerNode") {
            options.push({
                content: "🧹 预览清理",
                callback: () => {
                    // Set to dry run mode
                    node.widgets.find(w => w.name === "action").value = "dry_run";
                    app.queuePrompt(0, 1);
                }
            });
        }

        return options;
    };
}

/**
 * Initialize the plugin
 */
function initializePlugin() {
    console.log(`[${PLUGIN_NAME}] 正在初始化插件...`);

    // Add custom styling
    addCustomNodeStyling();

    // Enhance node functionality
    enhanceModelScannerNodes();

    // Add context menu options
    addContextMenuOptions();

    // Add keyboard shortcuts
    addKeyboardShortcuts();

    // Register event listeners
    api.addEventListener(MESSAGE_TYPES.SCAN_COMPLETE, handleScanComplete);
    api.addEventListener(MESSAGE_TYPES.SCAN_PROGRESS, handleScanProgress);
    api.addEventListener(MESSAGE_TYPES.CLEANUP_COMPLETE, handleCleanupComplete);

    console.log(`[${PLUGIN_NAME}] 插件初始化完成`);
}

// Register the extension with ComfyUI
app.registerExtension({
    name: "comfy.model.cleaner",

    init() {
        // 监听模型清理器数据事件
        api.addEventListener(MESSAGE_TYPES.MODEL_CLEANER_DATA, (event) => {
            createModelSelectionUI(event.detail);
        });

        // 监听执行开始事件
        api.addEventListener("execution_start", () => {
            sendStart();
        });

        // 监听执行中断事件
        api.addEventListener("execution_interrupted", () => {
            if (modelCleanerState.isPaused()) {
                sendCancel();
            }
        });
    },

    async setup() {
        initializePlugin();
    },

    async nodeCreated(node) {
        if (node?.comfyClass === "Interactive Model Cleaner") {
            node.isModelCleaner = true;

            // 添加样式
            node.color = "#2a4d3a";
            node.bgcolor = "#1a2d1a";
        }
    },

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        // Additional node customization can be added here
        if (nodeData.name === "ModelScannerNode" || nodeData.name === "ModelCleanerNode" || nodeData.name === "Interactive Model Cleaner") {
            console.log(`[${PLUGIN_NAME}] 注册节点: ${nodeData.name}`);
        }
    }
});

// Export for potential use by other scripts
window.ComfyModelCleaner = {
    showNotification,
    scanResults,
    isScanning,
    modelCleanerState,
    sendScanCancel
};
