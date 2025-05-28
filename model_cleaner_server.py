"""
模型清理器服务器端消息处理
基于image chooser的消息处理机制
"""

import time

try:
    from server import PromptServer
    from aiohttp import web
    SERVER_AVAILABLE = True
except (ImportError, AttributeError) as e:
    print(f"ComfyModelCleaner: Server not available in test environment: {e}")
    SERVER_AVAILABLE = False
    PromptServer = None
    web = None

class ModelCleanerCancelled(Exception):
    """清理操作被取消"""
    pass

class ModelCleanerMessageHolder:
    """消息持有者 - 处理前端和后端之间的通信"""

    stash = {}
    messages = {}
    cancelled = False

    @classmethod
    def addMessage(cls, id, message):
        """添加消息"""
        if message == '__cancel__':
            cls.messages = {}
            cls.cancelled = True
        elif message == '__start__':
            cls.messages = {}
            cls.stash = {}
            cls.cancelled = False
        else:
            cls.messages[str(id)] = message

    @classmethod
    def waitForMessage(cls, id, period=0.1, asList=False):
        """等待消息"""
        sid = str(id)
        while not (sid in cls.messages) and not ("-1" in cls.messages):
            if cls.cancelled:
                cls.cancelled = False
                raise ModelCleanerCancelled()
            time.sleep(period)

        if cls.cancelled:
            cls.cancelled = False
            raise ModelCleanerCancelled()

        message = cls.messages.pop(str(id), None) or cls.messages.pop("-1")

        try:
            if asList:
                # 首先尝试解析JSON格式
                import json
                try:
                    parsed = json.loads(message)
                    if isinstance(parsed, list):
                        return [int(x) for x in parsed]
                    elif isinstance(parsed, (int, float)):
                        # 单个数字，转换为包含一个元素的列表
                        return [int(parsed)]
                    else:
                        print(f"ERROR IN MODEL_CLEANER - JSON parsed but unexpected type: {type(parsed)} = {parsed}")
                        return []
                except (json.JSONDecodeError, TypeError):
                    # 如果JSON解析失败，尝试逗号分隔格式
                    if message.strip() == "":
                        return []
                    return [int(x.strip()) for x in message.split(",") if x.strip()]
            else:
                return int(message.strip())
        except ValueError as e:
            print(f"ERROR IN MODEL_CLEANER - failed to parse '{message}' as {'comma separated list of ints' if asList else 'int'}: {e}")
            return [] if asList else 0

# 注册路由（仅在服务器可用时）
if SERVER_AVAILABLE and PromptServer and hasattr(PromptServer, 'instance'):
    try:
        routes = PromptServer.instance.routes

        @routes.post('/model_cleaner_message')
        async def handle_model_cleaner_message(request):
            """处理模型清理器消息"""
            post = await request.post()
            ModelCleanerMessageHolder.addMessage(post.get("id"), post.get("message"))
            return web.json_response({})

        @routes.post('/model_cleaner_cancel')
        async def handle_model_cleaner_cancel(request):
            """处理取消请求"""
            ModelCleanerMessageHolder.addMessage(-1, '__cancel__')
            return web.json_response({})

        @routes.post('/model_cleaner_start')
        async def handle_model_cleaner_start(request):
            """处理开始请求"""
            ModelCleanerMessageHolder.addMessage(-1, '__start__')
            return web.json_response({})

        @routes.post('/model_scanner_cancel')
        async def handle_model_scanner_cancel(request):
            """处理扫描取消请求"""
            try:
                from .nodes import ModelScannerNode
                success = ModelScannerNode.cancel_current_scan()
                return web.json_response({"success": success})
            except Exception as e:
                print(f"ComfyModelCleaner: 取消扫描失败: {e}")
                return web.json_response({"success": False, "error": str(e)})

        print("ComfyModelCleaner: HTTP routes registered successfully")
    except Exception as e:
        print(f"ComfyModelCleaner: Failed to register HTTP routes: {e}")
else:
    print("ComfyModelCleaner: Server not available, skipping route registration")
