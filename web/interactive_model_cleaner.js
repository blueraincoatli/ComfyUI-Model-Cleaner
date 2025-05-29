/**
 * Interactive Model Cleaner JavaScript
 * 参考image-chooser实现，在节点内部显示模型选择界面
 */

import { app } from "/scripts/app.js";
import { api } from "/scripts/api.js";

console.log("InteractiveModelCleaner: JavaScript文件开始加载");

// ===== 国际化支持 BEGIN =====
// 将 currentLang 的定义放在最前面
let currentLang = (window.COMFYUI_LANG || navigator.language || "zh").toLowerCase().startsWith("zh") ? "zh" : "en";

const I18N = {
  zh: {
    waiting_for_data: "等待模型数据...", // 保持，但会被 t() 强制英文
    run_workflow_to_get_models: "请先运行工作流以获取模型列表", // 保持，但会被 t() 强制英文
    node_will_show_ui: "此节点将在工作流运行时显示交互式模型选择界面", // 保持，但会被 t() 强制英文
    found_unused_models: "发现 {count} 个未使用模型",
    action_mode: "操作模式: {mode}",
    backup_folder: "备份文件夹: {folder}",
    select_tip: "点击模型名称选择/取消选择，然后点击确认",
    selected_count: "已选择 {count} 个模型",
    cancel: "取消", // 保持，但会被 t() 强制英文
    confirm: "确认", // 保持，但会被 t() 强制英文
    proceed: "继续", // 保持，但会被 t() 强制英文
    clean: "执行清理",
    please_select_models: "请选择要删除的模型",
    js_model_info: "{size} | {confidence_text}",
    js_unused_confidence_label: "未使用置信度: {confidence}%"
  },
  en: {
    waiting_for_data: "Waiting for model data...",
    run_workflow_to_get_models: "Run workflow to get model list",
    node_will_show_ui: "This node shows the model selection UI when running",
    found_unused_models: "Found {count} unused models",
    action_mode: "Action mode: {mode}",
    backup_folder: "Backup folder: {folder}",
    select_tip: "Click model name to select/deselect, then click confirm",
    selected_count: "{count} models selected",
    cancel: "Cancel",
    confirm: "Confirm",
    proceed: "Proceed",
    clean: "Execute Clean",
    please_select_models: "Please select models to delete",
    js_model_info: "{size} | {confidence_text}",
    js_unused_confidence_label: "Unused Confidence: {confidence}%"
  }
};

function t(key, params = {}) {
  const alwaysEnglishKeys = [
    "waiting_for_data",
    "run_workflow_to_get_models",
    "node_will_show_ui",
    "cancel",
    "confirm",
    "proceed"
  ];
  let lang_to_use = alwaysEnglishKeys.includes(key) ? "en" : currentLang;
  let str = (I18N[lang_to_use] && I18N[lang_to_use][key]) || key;
  Object.keys(params).forEach(k => {
    str = str.replace(`{${k}}`, params[k]);
  });
  return str;
}
// ===== 国际化支持 END =====

// 状态管理
class InteractiveModelCleanerState {
    constructor() {
        this.paused = false;
        this.currentNodeId = null;
        this.models = [];
        this.selectedIndices = new Set();
        this.actionMode = "dry_run";
        this.backupFolder = "model_backups";
    }

    setPaused(paused, nodeId = null) {
        console.log("InteractiveModelCleaner: 设置暂停状态", {
            oldPaused: this.paused,
            newPaused: paused,
            oldNodeId: this.currentNodeId,
            newNodeId: nodeId
        });
        this.paused = paused;
        this.currentNodeId = nodeId;
        if (!paused) {
            this.models = [];
            this.selectedIndices.clear();
        }
        console.log("InteractiveModelCleaner: 暂停状态已更新", {
            paused: this.paused,
            nodeId: this.currentNodeId
        });
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
}

const interactiveModelCleanerState = new InteractiveModelCleanerState();

// 发送消息到后端
function sendMessage(nodeId, message) {
    const body = new FormData();
    body.append('message', message);
    body.append('id', nodeId);
    api.fetchApi("/model_cleaner_message", { method: "POST", body });
}

console.log("InteractiveModelCleaner: 准备注册扩展");

// 立即设置事件监听器
console.log("InteractiveModelCleaner: 立即设置事件监听器");
api.addEventListener("interactive-model-cleaner-data", (event) => {
    let languageChanged = false;
    // 自动同步后端语言
    if (event.detail && event.detail.lang) {
        const newLang = event.detail.lang.toLowerCase().startsWith("zh") ? "zh" : "en";
        if (currentLang !== newLang) {
            window.COMFYUI_LANG = event.detail.lang; // 更新全局标记 (如果其他地方用到)
            currentLang = newLang; // 更新顶层 currentLang
            languageChanged = true;
            console.log("InteractiveModelCleaner: 语言已切换到", currentLang);
        }
    }
    const data = event.detail;
    handleInteractiveModelCleanerData(data); // 这个函数内部通常会重绘

    // 如果语言真的改变了，额外确保一次重绘
    if (languageChanged) {
        const activeNode = app.graph._nodes.find(n => n.isInteractiveModelCleaner && n.id == interactiveModelCleanerState.currentNodeId);
        if (activeNode) {
            console.log("InteractiveModelCleaner: 因语言变更，强制节点重绘", activeNode.id);
            activeNode.setDirtyCanvas(true);
        }
    }
});
console.log("InteractiveModelCleaner: 事件监听器设置完成");

// 辅助函数：文本换行 (针对英文长文本)
function wrapText(ctx, text, x, y, maxWidth, lineHeight, lang) {
    if (lang === 'en' && ctx.measureText(text).width > maxWidth) {
        const words = text.split(' ');
        let line = '';
        let testLine = '';
        let currentY = y;

        for (let n = 0; n < words.length; n++) {
            testLine += words[n] + ' ';
            const metrics = ctx.measureText(testLine);
            const testWidth = metrics.width;
            if (testWidth > maxWidth && n > 0) {
                ctx.fillText(line, x, currentY);
                line = words[n] + ' ';
                testLine = words[n] + ' ';
                currentY += lineHeight;
            } else {
                line = testLine;
            }
        }
        ctx.fillText(line, x, currentY);
    } else {
        ctx.fillText(text, x, y);
    }
}

// 处理节点创建
app.registerExtension({
    name: "ComfyUI.InteractiveModelCleaner",

    async nodeCreated(node) {
        console.log("InteractiveModelCleaner: Node created:", node.comfyClass, node.type);
        if (node?.comfyClass === "InteractiveModelCleanerNode" || node?.type === "InteractiveModelCleanerNode") {
            console.log("InteractiveModelCleaner: 识别到节点，开始初始化");
            node.isInteractiveModelCleaner = true;

            // 添加自定义属性
            node.selectedModels = new Set();
            node.modelRects = [];
            node.buttonRects = {};
            node.models = []; // 初始化为空数组
            node.showBasicUI = true; // 标记显示基础UI
            node.scrollOffset = 0; // 滚动偏移量
            node.maxVisibleModels = 12; // 最大可见模型数量

            // 立即计算按钮区域（不依赖模型数据）
            updateModelRects(node);

            // 重写节点绘制
            const originalOnDrawForeground = node.onDrawForeground;
            node.onDrawForeground = function(ctx) {
                if (originalOnDrawForeground) {
                    originalOnDrawForeground.call(this, ctx);
                }
                drawInteractiveInterface(this, ctx);
            };

            // 强制初始绘制
            node.setDirtyCanvas(true);
            console.log("InteractiveModelCleaner: 节点初始化完成，显示基础UI");

            // 重写鼠标点击处理
            const originalOnMouseDown = node.onMouseDown;
            node.onMouseDown = function(e, pos, canvas) {
                console.log("InteractiveModelCleaner: onMouseDown被调用", {
                    nodeType: this.type,
                    isPrimary: e.isPrimary,
                    isInteractiveModelCleaner: this.isInteractiveModelCleaner,
                    isPaused: interactiveModelCleanerState.paused,
                    pos: pos
                });

                if (e.isPrimary && this.isInteractiveModelCleaner) {
                    console.log("InteractiveModelCleaner: 处理点击事件", {
                        paused: interactiveModelCleanerState.paused,
                        hasModels: this.models && this.models.length > 0
                    });
                    const clickResult = handleNodeClick(this, pos);
                    if (clickResult) {
                        console.log("InteractiveModelCleaner: 点击被处理，阻止默认行为");
                        return clickResult;
                    }
                }
                return originalOnMouseDown && originalOnMouseDown.apply(this, arguments);
            };

            // 添加键盘事件处理用于滚动
            const originalOnKeyDown = node.onKeyDown;
            node.onKeyDown = function(e) {
                if (this.isInteractiveModelCleaner && this.models && this.models.length > this.maxVisibleModels) {
                    // 使用上下箭头键滚动
                    if (e.key === "ArrowUp" || e.key === "ArrowDown") {
                        const maxScroll = Math.max(0, this.models.length - this.maxVisibleModels);
                        const direction = e.key === "ArrowUp" ? -1 : 1;
                        this.scrollOffset = Math.max(0, Math.min(maxScroll, this.scrollOffset + direction));

                        // 重新计算模型矩形
                        updateModelRects(this);
                        this.setDirtyCanvas(true);
                        e.preventDefault();
                        return true;
                    }
                }
                return originalOnKeyDown && originalOnKeyDown.apply(this, arguments);
            };

            // 设置节点初始大小 - 动态调整
            node.size = [300, 300]; // 减小初始高度
        }
    },

    async setup() {
        console.log("InteractiveModelCleaner: 设置事件监听器");

        // 监听来自后端的数据
        api.addEventListener("interactive-model-cleaner-data", (event) => {
            console.log("InteractiveModelCleaner: 收到事件", event);
            console.log("InteractiveModelCleaner: 事件详情", event.detail);
            const data = event.detail;
            handleInteractiveModelCleanerData(data);
        });

        // 添加调试信息
        console.log("InteractiveModelCleaner: 事件监听器设置完成");
        console.log("InteractiveModelCleaner: API对象", api);
        console.log("InteractiveModelCleaner: APP对象", app);

        // 测试事件系统是否工作
        setTimeout(() => {
            console.log("InteractiveModelCleaner: 测试事件系统");
            api.dispatchEvent(new CustomEvent("test-event", { detail: { test: "data" } }));
        }, 1000);

        // 监听测试事件
        api.addEventListener("test-event", (event) => {
            console.log("InteractiveModelCleaner: 收到测试事件", event.detail);
        });
    }
});

// 处理来自后端的数据
function handleInteractiveModelCleanerData(data) {
    console.log("收到后端数据:", data);
    const { id, models, action_mode, backup_folder } = data;

    console.log("数据中的节点ID:", id, "类型:", typeof id);

    // 更新状态
    interactiveModelCleanerState.setPaused(true, id);
    interactiveModelCleanerState.setModels(models);
    interactiveModelCleanerState.actionMode = action_mode;
    interactiveModelCleanerState.backupFolder = backup_folder;

    // 找到对应的节点 - 尝试多种方式查找
    let node = null;

    // 方式1: 直接通过ID查找
    if (id) {
        node = app.graph.getNodeById(parseInt(id));
        console.log("方式1查找节点 (parseInt):", node);

        if (!node) {
            node = app.graph.getNodeById(id);
            console.log("方式1查找节点 (原始ID):", node);
        }
    }

    // 方式2: 遍历所有节点查找InteractiveModelCleaner类型
    if (!node) {
        console.log("方式2: 遍历查找InteractiveModelCleaner节点");
        for (let i = 0; i < app.graph._nodes.length; i++) {
            const n = app.graph._nodes[i];
            console.log(`节点 ${i}: ID=${n.id}, type=${n.type}, comfyClass=${n.comfyClass}, isInteractiveModelCleaner=${n.isInteractiveModelCleaner}`);
            if (n.isInteractiveModelCleaner) {
                node = n;
                console.log("找到InteractiveModelCleaner节点:", node);
                break;
            }
        }
    }

    if (node && node.isInteractiveModelCleaner) {
        console.log("更新节点数据，模型数量:", models.length);
        // 更新节点数据
        node.models = models;
        node.selectedModels.clear();

        // 动态计算节点大小 - 根据实际模型数量调整高度
        const maxVisibleModels = Math.min(models.length, 12); // 最多显示12个，但如果模型少于12个则显示实际数量
        const actualVisibleModels = Math.min(models.length, maxVisibleModels);
        const baseHeight = 250; // 头部信息区域高度
        const modelAreaHeight = actualVisibleModels * 35; // 每个模型35px高度
        const bottomHeight = 100; // 底部按钮区域高度
        const newHeight = baseHeight + modelAreaHeight + bottomHeight;
        const newWidth = 300; // 保持300px宽度

        // 更新节点的最大可见模型数量
        node.maxVisibleModels = maxVisibleModels;
        node.size = [newWidth, Math.max(300, newHeight)]; // 最小高度300px

        // 计算模型矩形区域
        updateModelRects(node);

        // 强制重绘
        node.setDirtyCanvas(true);
        app.graph.setDirtyCanvas(true);
        console.log("节点更新完成");
    } else {
        console.log("未找到对应的节点或节点类型不匹配");
        console.log("所有节点:", app.graph._nodes.map(n => ({id: n.id, type: n.type, isInteractiveModelCleaner: n.isInteractiveModelCleaner})));
    }
}

// 更新模型矩形区域
function updateModelRects(node) {
    node.modelRects = [];
    node.buttonRects = {};

    // 如果有模型数据，计算模型矩形（支持滚动）
    if (node.models && node.models.length > 0) {
        const startY = 230;  // 与绘制函数保持一致
        const rowHeight = 35;  // 与绘制函数保持一致
        const maxVisibleModels = node.maxVisibleModels || 12;
        const scrollOffset = node.scrollOffset || 0;

        // 计算可见模型的矩形
        const visibleModels = Math.min(node.models.length - scrollOffset, maxVisibleModels);
        for (let i = 0; i < visibleModels; i++) {
            const modelIndex = scrollOffset + i; // 实际模型索引
            const y = startY + (i * rowHeight); // 显示位置
            node.modelRects.push({
                x: 10,
                y: y,
                width: node.size[0] - 20,
                height: rowHeight - 2,
                index: modelIndex // 使用实际模型索引
            });
        }
    }

    // 计算滚动按钮（如果需要滚动）- 移到上方空白区域
    if (node.models && node.models.length > node.maxVisibleModels) {
        const scrollButtonSize = 20;
        const scrollButtonX = node.size[0] - scrollButtonSize - 5;
        const scrollButtonY = 180; // 移到上方空白区域

        // 向上滚动按钮
        node.buttonRects.scrollUp = {
            x: scrollButtonX,
            y: scrollButtonY,
            width: scrollButtonSize,
            height: scrollButtonSize
        };

        // 向下滚动按钮
        node.buttonRects.scrollDown = {
            x: scrollButtonX,
            y: scrollButtonY + scrollButtonSize + 5,
            width: scrollButtonSize,
            height: scrollButtonSize
        };
    }

    // 始终计算按钮矩形（不依赖模型数据）
    const buttonY = node.size[1] - 60;
    const buttonWidth = 80;  // 调整按钮宽度以适应300px宽度
    const buttonHeight = 30;
    const buttonSpacing = 10;  // 减少按钮间距

    node.buttonRects.cancel = {
        x: node.size[0] / 2 - buttonWidth - buttonSpacing / 2,
        y: buttonY,
        width: buttonWidth,
        height: buttonHeight
    };

    node.buttonRects.confirm = {
        x: node.size[0] / 2 + buttonSpacing / 2,
        y: buttonY,
        width: buttonWidth,
        height: buttonHeight
    };
}

// 绘制节点内界面
function drawInteractiveInterface(node, ctx) {
    if (!node.isInteractiveModelCleaner) {
        return;
    }

    // console.log("绘制界面 - 暂停状态:", interactiveModelCleanerState.paused, "节点ID:", interactiveModelCleanerState.currentNodeId, "当前节点ID:", node.id, "模型数据:", node.models);

    // 绘制背景
    ctx.fillStyle = "#2b2b2b";
    ctx.fillRect(0, 0, node.size[0], node.size[1]);

    // 移除标题和图标

    // 检查是否有模型数据
    const hasModelData = node.models && node.models.length > 0;

    if (!hasModelData) {
        // 如果没有数据，绘制等待界面 - 减少上方空间
        const initialPromptX = 10;
        const initialPromptYBase = 130; // 向上移动10像素
        const lineHeight = 16; // 更紧凑的行高

        ctx.fillStyle = "#cccccc";
        ctx.font = "12px Arial";
        wrapText(ctx, t("waiting_for_data"), initialPromptX, initialPromptYBase, node.size[0] - 20, lineHeight, currentLang);

        ctx.fillStyle = "#888888";
        ctx.font = "12px Arial";
        wrapText(ctx, t("run_workflow_to_get_models"), initialPromptX, initialPromptYBase + lineHeight * 1.5, node.size[0] - 20, lineHeight, currentLang);
    }

    // 如果有模型数据，绘制详细信息
    if (hasModelData) {
        const models = node.models;

        // 绘制模型数量信息 - 适应300px宽度，减少上方空间
        ctx.fillStyle = "#ffffff";
        ctx.font = "14px Arial";
        ctx.fillText(t("found_unused_models", {count: models.length}), 10, 140);

        // 绘制操作信息 - 适应300px宽度
        ctx.fillStyle = "#cccccc";
        ctx.font = "12px Arial";
        ctx.fillText(t("action_mode", {mode: interactiveModelCleanerState.actionMode}), 10, 160);

        // 备份路径显示，300px宽度需要截断更多内容
        let backupText = t("backup_folder", {folder: interactiveModelCleanerState.backupFolder});
        if (backupText.length > 30) {
            backupText = backupText.substring(0, 27) + "...";
        }
        ctx.fillText(backupText, 10, 180);

        // 绘制说明 - 适应300px宽度
        ctx.fillStyle = "#ffff88";
        ctx.font = "10px Arial";  // 减小字体以适应300px宽度
        ctx.fillText(t("select_tip"), 10, 200);
        ctx.strokeStyle = "#555555";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(5, 215);
        ctx.lineTo(node.size[0] - 5, 215);
        ctx.stroke();
    }

    // 绘制模型列表（只在有数据时，支持滚动）
    if (hasModelData) {
        const models = node.models;
        const startY = 230;  // 减少起始位置，减少上方空间
        const rowHeight = 35;  // 保持行高
        const maxVisibleModels = node.maxVisibleModels || 12;
        const scrollOffset = node.scrollOffset || 0;
        const visibleModels = Math.min(models.length - scrollOffset, maxVisibleModels);

        for (let i = 0; i < visibleModels; i++) {
            const modelIndex = scrollOffset + i; // 实际模型索引
            const model = models[modelIndex];
            const y = startY + (i * rowHeight);
            const isSelected = node.selectedModels.has(modelIndex);

            // 绘制背景
            const confidence = model.unused_confidence;
            let bgColor, textColor;

            if (confidence >= 90) {
                bgColor = isSelected ? "#6a2a2a" : "#4a1a1a";
                textColor = "#ff6666";
            } else if (confidence >= 80) {
                bgColor = isSelected ? "#6a4a2a" : "#4a3a1a";
                textColor = "#ffaa66";
            } else if (confidence >= 70) {
                bgColor = isSelected ? "#6a6a2a" : "#4a4a1a";
                textColor = "#ffff66";
            } else {
                bgColor = isSelected ? "#2a6a2a" : "#1a4a1a";
                textColor = "#66ff66";
            }

            ctx.fillStyle = bgColor;
            ctx.fillRect(10, y, node.size[0] - 20, rowHeight - 2);

            // 绘制边框
            if (isSelected) {
                ctx.strokeStyle = "#ffffff";
                ctx.lineWidth = 2;
                ctx.strokeRect(10, y, node.size[0] - 20, rowHeight - 2);
            }

            // 绘制模型名称 - 向右移动20像素
            ctx.fillStyle = textColor;
            ctx.font = "11px Arial";
            const modelName = model.name.length > 25 ? model.name.substring(0, 22) + "..." : model.name;
            ctx.fillText(modelName, 28, y + 12);  // 从8改为28，向右移动20像素

            // 绘制大小和置信度 - 向右移动20像素
            ctx.fillStyle = "#cccccc";
            ctx.font = "9px Arial";
            const confidenceText = t('js_unused_confidence_label', { confidence: model.unused_confidence.toFixed(1) });
            const modelInfoText = t('js_model_info', { size: model.size_formatted, confidence_text: confidenceText });
            ctx.fillText(modelInfoText, 28, y + 25);  // 从8改为28

            // 绘制选择框 - 向左移动10像素
            const checkboxX = node.size[0] - 35;  // 从25改为35，向左移动10像素
            const checkboxY = y + 8;
            ctx.strokeStyle = "#ffffff";
            ctx.lineWidth = 1;
            ctx.strokeRect(checkboxX, checkboxY, 12, 12);

            if (isSelected) {
                ctx.fillStyle = "#ffffff";
                ctx.fillRect(checkboxX + 2, checkboxY + 2, 8, 8);
            }
        }

        // 显示选择统计 - 调整位置避免与按钮重叠
        const selectedCount = node.selectedModels.size;
        if (selectedCount > 0) {
            ctx.fillStyle = "#ffff88";
            ctx.font = "11px Arial";
            ctx.fillText(t("selected_count", {count: selectedCount}), 10, node.size[1] - 90);  // 从-20改为-90，避免与按钮重叠
        }

        // 显示滚动信息和绘制滚动按钮
        if (models.length > node.maxVisibleModels) {
            ctx.fillStyle = "#888888";
            ctx.font = "10px Arial";
            const totalPages = Math.ceil(models.length / node.maxVisibleModels);
            const currentPage = Math.floor(scrollOffset / node.maxVisibleModels) + 1;
            ctx.fillText(`第 ${currentPage}/${totalPages} 页 (${scrollOffset + 1}-${Math.min(scrollOffset + node.maxVisibleModels, models.length)}/${models.length})`, 10, node.size[1] - 80);

            // 绘制滚动按钮 - 移到上方空白区域
            const scrollButtonSize = 20;
            const scrollButtonX = node.size[0] - scrollButtonSize - 5;
            const scrollButtonY = 180; // 移到上方空白区域

            // 向上滚动按钮
            const canScrollUp = scrollOffset > 0;
            ctx.fillStyle = canScrollUp ? "#4a7c59" : "#333333";
            ctx.fillRect(scrollButtonX, scrollButtonY, scrollButtonSize, scrollButtonSize);
            ctx.strokeStyle = canScrollUp ? "#6a9c79" : "#555555";
            ctx.strokeRect(scrollButtonX, scrollButtonY, scrollButtonSize, scrollButtonSize);
            ctx.fillStyle = canScrollUp ? "#ffffff" : "#888888";
            ctx.font = "12px Arial";
            ctx.textAlign = "center";
            ctx.fillText("▲", scrollButtonX + scrollButtonSize/2, scrollButtonY + scrollButtonSize/2 + 4);

            // 向下滚动按钮
            const canScrollDown = scrollOffset + node.maxVisibleModels < models.length;
            const downButtonY = scrollButtonY + scrollButtonSize + 5;
            ctx.fillStyle = canScrollDown ? "#4a7c59" : "#333333";
            ctx.fillRect(scrollButtonX, downButtonY, scrollButtonSize, scrollButtonSize);
            ctx.strokeStyle = canScrollDown ? "#6a9c79" : "#555555";
            ctx.strokeRect(scrollButtonX, downButtonY, scrollButtonSize, scrollButtonSize);
            ctx.fillStyle = canScrollDown ? "#ffffff" : "#888888";
            ctx.fillText("▼", scrollButtonX + scrollButtonSize/2, downButtonY + scrollButtonSize/2 + 4);

            // 重置文本对齐
            ctx.textAlign = "left";

            // 绘制滚动提示
            ctx.fillStyle = "#ffff88";
            ctx.font = "9px Arial";
            ctx.fillText("点击箭头按钮或使用上下键滚动", 10, node.size[1] - 65);
        }
    }

    // 始终绘制底部按钮
    const buttonY = node.size[1] - 50;
    const buttonWidth = 80;  // 调整按钮宽度以适应300px宽度
    const buttonHeight = 30;
    const buttonSpacing = 10;  // 减少按钮间距以适应300px宽度

    // 确保按钮矩形已初始化
    if (!node.buttonRects) {
        node.buttonRects = {};
    }

    // 设置文本对齐方式为居中
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";

    // 取消按钮
    const cancelX = node.size[0] / 2 - buttonWidth - buttonSpacing / 2;
    ctx.fillStyle = "#666666";
    ctx.fillRect(cancelX, buttonY, buttonWidth, buttonHeight);
    ctx.strokeStyle = "#888888";
    ctx.strokeRect(cancelX, buttonY, buttonWidth, buttonHeight);
    ctx.fillStyle = "#ffffff";
    ctx.font = "13px Arial";
    // 使用居中对齐
    ctx.fillText(t("cancel"), cancelX + buttonWidth / 2, buttonY + buttonHeight / 2);

    // 设置取消按钮矩形
    node.buttonRects.cancel = {
        x: cancelX,
        y: buttonY,
        width: buttonWidth,
        height: buttonHeight
    };

    // 确认按钮 - 根据是否有数据调整文本和颜色
    const confirmX = node.size[0] / 2 + buttonSpacing / 2;
    if (hasModelData) {
        ctx.fillStyle = "#4a7c59";
        ctx.strokeStyle = "#6a9c79";
    } else {
        ctx.fillStyle = "#555555";
        ctx.strokeStyle = "#777777";
    }
    ctx.fillRect(confirmX, buttonY, buttonWidth, buttonHeight);
    ctx.strokeRect(confirmX, buttonY, buttonWidth, buttonHeight);
    ctx.fillStyle = "#ffffff";
    ctx.font = "13px Arial";
    const confirmText = hasModelData ? t("confirm") : t("proceed");
    // 使用居中对齐
    ctx.fillText(confirmText, confirmX + buttonWidth / 2, buttonY + buttonHeight / 2);

    // 设置确认按钮矩形
    node.buttonRects.confirm = {
        x: confirmX,
        y: buttonY,
        width: buttonWidth,
        height: buttonHeight
    };

    // 重置文本对齐方式，以防影响其他绘制
    ctx.textAlign = "left";
    ctx.textBaseline = "alphabetic"; // 或者 "ideographic" 取决于默认
}

// 处理节点点击
function handleNodeClick(node, pos) {
    console.log("InteractiveModelCleaner: 点击检测", {
        pos: pos,
        buttonRects: node.buttonRects,
        nodeSize: node.size,
        paused: interactiveModelCleanerState.paused,
        hasModels: node.models && node.models.length > 0
    });

    // 检查模型点击（只在有模型数据且暂停状态时）
    if (interactiveModelCleanerState.paused && node.models && node.models.length > 0 && node.modelRects) {
        for (let i = 0; i < node.modelRects.length; i++) {
            const rect = node.modelRects[i];
            if (pos[0] >= rect.x && pos[0] <= rect.x + rect.width &&
                pos[1] >= rect.y && pos[1] <= rect.y + rect.height) {

                console.log("InteractiveModelCleaner: 点击模型", i);
                // 切换选择状态
                if (node.selectedModels.has(rect.index)) {
                    node.selectedModels.delete(rect.index);
                } else {
                    node.selectedModels.add(rect.index);
                }

                node.setDirtyCanvas(true);
                return true;
            }
        }
    }

    // 检查滚动按钮点击
    if (node.buttonRects && node.buttonRects.scrollUp) {
        const scrollUpRect = node.buttonRects.scrollUp;
        if (pos[0] >= scrollUpRect.x && pos[0] <= scrollUpRect.x + scrollUpRect.width &&
            pos[1] >= scrollUpRect.y && pos[1] <= scrollUpRect.y + scrollUpRect.height) {

            // 向上滚动
            if (node.scrollOffset > 0) {
                node.scrollOffset = Math.max(0, node.scrollOffset - 1);
                updateModelRects(node);
                node.setDirtyCanvas(true);
            }
            return true;
        }
    }

    if (node.buttonRects && node.buttonRects.scrollDown) {
        const scrollDownRect = node.buttonRects.scrollDown;
        if (pos[0] >= scrollDownRect.x && pos[0] <= scrollDownRect.x + scrollDownRect.width &&
            pos[1] >= scrollDownRect.y && pos[1] <= scrollDownRect.y + scrollDownRect.height) {

            // 向下滚动
            const maxScroll = Math.max(0, node.models.length - node.maxVisibleModels);
            if (node.scrollOffset < maxScroll) {
                node.scrollOffset = Math.min(maxScroll, node.scrollOffset + 1);
                updateModelRects(node);
                node.setDirtyCanvas(true);
            }
            return true;
        }
    }

    // 始终检查按钮点击
    if (node.buttonRects && node.buttonRects.cancel) {
        const cancelRect = node.buttonRects.cancel;
        console.log("InteractiveModelCleaner: 检查取消按钮", {
            pos: pos,
            cancelRect: cancelRect,
            inBounds: pos[0] >= cancelRect.x && pos[0] <= cancelRect.x + cancelRect.width &&
                     pos[1] >= cancelRect.y && pos[1] <= cancelRect.y + cancelRect.height
        });

        if (pos[0] >= cancelRect.x && pos[0] <= cancelRect.x + cancelRect.width &&
            pos[1] >= cancelRect.y && pos[1] <= cancelRect.y + cancelRect.height) {

            // 取消操作
            console.log("InteractiveModelCleaner: 点击取消按钮");
            sendMessage(node.id, JSON.stringify([]));
            interactiveModelCleanerState.setPaused(false);
            // 清理节点数据
            node.models = [];
            node.selectedModels.clear();
            node.setDirtyCanvas(true);
            return true;
        }
    }

    if (node.buttonRects && node.buttonRects.confirm) {
        const confirmRect = node.buttonRects.confirm;
        console.log("InteractiveModelCleaner: 检查确认按钮", {
            pos: pos,
            confirmRect: confirmRect,
            inBounds: pos[0] >= confirmRect.x && pos[0] <= confirmRect.x + confirmRect.width &&
                     pos[1] >= confirmRect.y && pos[1] <= confirmRect.y + confirmRect.height
        });

        if (pos[0] >= confirmRect.x && pos[0] <= confirmRect.x + confirmRect.width &&
            pos[1] >= confirmRect.y && pos[1] <= confirmRect.y + confirmRect.height) {

            // 确认操作
            console.log("InteractiveModelCleaner: 点击确认按钮");

            // 如果有模型数据且处于暂停状态，发送选择的模型
            if (interactiveModelCleanerState.paused && node.models && node.models.length > 0) {
                const selectedIndices = Array.from(node.selectedModels);
                console.log("InteractiveModelCleaner: 发送选择的模型索引", selectedIndices);
                sendMessage(node.id, JSON.stringify(selectedIndices));
            } else {
                // 如果没有模型数据，发送空数组继续执行
                console.log("InteractiveModelCleaner: 没有模型数据，继续执行");
                sendMessage(node.id, JSON.stringify([]));
            }

            interactiveModelCleanerState.setPaused(false);
            // 清理节点数据
            node.models = [];
            node.selectedModels.clear();
            node.setDirtyCanvas(true);
            return true;
        }
    }

    console.log("InteractiveModelCleaner: 没有点击到任何按钮");
    return false;
}

console.log("InteractiveModelCleaner: JavaScript文件加载完成");
