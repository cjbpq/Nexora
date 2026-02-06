"""
火山引擎大模型封装类 - 重构版
基于 Responses API 最佳实践
参考文档：
- https://www.volcengine.com/docs/82379/1569618 (Responses API)
- https://www.volcengine.com/docs/82379/1262342 (Function Calling)
"""
import os
import json
import time
from datetime import datetime
from typing import List, Dict, Any, Optional, Generator
from volcenginesdkarkruntime import Ark
from tools import TOOLS
from database import User
from conversation_manager import ConversationManager

# 配置文件路径
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config.json')

# 加载配置
def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "models": {
            "doubao-seed-1-6-251015": {
                "name": "Doubao Seed 1.6 (251015)",
                "api_key": ""
            }
        },
        "default_model": "doubao-seed-1-6-251015"
    }

CONFIG = load_config()

# 清除代理设置
if 'HTTP_PROXY' in os.environ:
    del os.environ['HTTP_PROXY']
if 'HTTPS_PROXY' in os.environ:
    del os.environ['HTTPS_PROXY']

# 全局客户端缓存，实现连接池复用 (Keep-Alive)
_ARK_CLIENT_CACHE = {}

class Model:
    """火山引擎大模型封装类"""
    
    def __init__(
        self,
        username: str,
        model_name: str = None,
        system_prompt: Optional[str] = None,
        conversation_id: Optional[str] = None,
        auto_create: bool = True
    ):
        """
        初始化Model
        
        Args:
            username: 用户名
            model_name: 模型名称 (None使用配置文件默认值)
            system_prompt: 自定义系统提示词
            conversation_id: 对话ID（None时根据auto_create决定是否创建）
            auto_create: 是否自动创建新对话
        """
        self.username = username
        self.user = User(username)
        
        # 加载配置
        global CONFIG
        CONFIG = load_config()
        
        # 确定模型名称
        if model_name:
            self.model_name = model_name
        else:
            self.model_name = CONFIG.get('default_model', 'doubao-seed-1-6-251015')
            
        self.conversation_manager = ConversationManager(username)
        
        # 对话ID管理
        if conversation_id:
            self.conversation_id = conversation_id
        elif auto_create:
            self.conversation_id = self.conversation_manager.create_conversation()
        else:
            self.conversation_id = None
        
        # 系统提示词
        self.system_prompt = system_prompt or self._get_default_system_prompt()
        
        # 获取API Key
        model_info = CONFIG.get('models', {}).get(self.model_name, {})
        api_key = model_info.get('api_key', "")

        # 初始化Ark客户端 (使用全局缓存实现连接复用)
        # 这可以节省TCP握手和SSL协商的时间 (每次请求约减少 200ms - 500ms)
        global _ARK_CLIENT_CACHE
        if api_key in _ARK_CLIENT_CACHE:
            self.client = _ARK_CLIENT_CACHE[api_key]
        else:
            # 首次连接
            print(f"[INIT] 创建新的Ark客户端连接 (Key: ...{api_key[-4:]})")
            # 可以在这里通过 base_url 或 timeout 进行更细致的配置
            self.client = Ark(
                api_key=api_key,
                timeout=120.0, # 增加默认超时以应对长时间思考
                max_retries=2  # 网络抖动自动重试
            )
            _ARK_CLIENT_CACHE[api_key] = self.client
        
        # 工具定义
        self.tools = self._parse_tools(TOOLS)
    
    def _get_default_system_prompt(self) -> str:
        """获取默认系统提示词"""
        return """你是智能助手，可以管理知识库并回答问题。

**核心原则：**
1. 理解用户的真实意图，主动完成任务而不是反问
2. 禁止编造或臆测用户没有问过的内容

**知识库查询流程：**
1. 优先使用 searchKeyword 快速搜索
2. 如需完整内容，使用 getKnowledgeList + getBasisContent
3. 历史对话查询：getContext / getContext_findKeyword / getMainTitle

**工具使用规范：**
- 当用户要求"添加XXX到知识库"或"丰富XXX资料"时，主动使用web_search联网搜索
- 完成工具调用后必须给用户确认消息（如"已成功保存XXX"）
- 禁止重复调用相同工具和参数
- 失败后应调整参数或更换工具，多次失败直接告知用户

**联网搜索规则：**
- 用户要求查询最新信息、添加知识、丰富资料时，直接使用web_search
- 不要问用户"需要搜索吗"，直接执行搜索
- 搜索完成后立即整理结果并保存到知识库（使用addBasis）

**内容质量要求：**
- 用户要求攥写长篇文章的时候自动保存到知识库
- 总结内容到知识库的时候必须详细表示引用和引用连接到文章末尾，包括连接和资料精确位置
- 总结内容的时候特殊数据例如百分比信息、统计数据、时间节点等必须精确无误和引用来源

**字数要求**
- 用户要求简介输出的时候自行控制字数
- 用户要求添加内容到知识库的时候必须详细精确、至少回复一段内容，但越详细越好
- 用户要求总结知识库的时候或你自行总结知识库的时候需要区分短期记忆和长期记忆
- 长期记忆即知识库
- 短期记忆用于记录用户的喜好偏向、最近在做的事，这个需要频繁主动记录

**基础知识（长期记忆）写作标准 - 核心要求：**
使用 addBasis 保存长期记忆时，必须按照以下学术报告级别的标准执行：

1. **内容深度与广度：**
   - 最低要求：3000字以上，优秀标准：5000-10000字
   - 必须包含：背景介绍、核心概念、详细分析、数据支撑、对比总结、展望结论
   - 横向对比时：逐项对比所有关键参数，制作完整对比表格
   - 技术说明时：原理、实现、优缺点、应用场景、最佳实践全面覆盖

2. **数据与引用要求：**
   - 所有数据必须精确标注来源（含页码/章节/时间戳）
   - 引用格式：`[来源名称](链接) - 第X页/第X章节 - 发布时间`
   - 统计数据必须包含：数值、单位、统计时间、样本量、数据源
   - 文末必须有完整的「参考资料」章节，列出所有引用来源

3. **结构化组织：**
   - 使用清晰的Markdown层级标题（# ## ### ####）
   - 复杂信息必须使用表格对比（| 参数 | 型号A | 型号B | 说明 |）
   - 关键概念用列表展开（- 要点1: 详细说明...）
   - 技术参数用代码块标注

4. **质量检查清单：**
   ✓ 是否包含至少3个主要章节？
   ✓ 每个关键论点是否有数据/案例支撑？
   ✓ 是否提供了至少3个有效引用链接？
   ✓ 对比分析是否覆盖所有核心维度？
   ✓ 结论是否有前瞻性观点？

**错误示例（禁止）：**
❌ "索尼A7 IV是一款全画幅相机，3300万像素，性能不错。"

**正确示例（参考）：**
✅ 完整报告包含：
- 产品背景与市场定位（500字+）
- 核心技术参数详解（1000字+，含表格对比）
- 性能测试数据分析（800字+，引用专业评测）
- 与竞品横向对比（1000字+，多维度表格）
- 使用场景与最佳实践（500字+）
- 总结与选购建议（300字+）
- 参考资料（完整链接列表）

使用 Markdown 格式回复。"""
    
    def _parse_tools(self, tools_config: List[Dict]) -> List[Dict]:
        """解析工具定义为API格式"""
        parsed_tools = []
        
        # 添加内置web_search工具
        # 注意: 某些新版模型可能更倾向于使用 "web_search" type 显式声明
        parsed_tools.append({
            "type": "web_search"
            # 移除 "limit": 10，使用默认值，避免 invalid parameter error
        })
        
        # 解析自定义function工具
        for tool in tools_config:
            if tool["type"] == "function":
                func_def = tool["function"]
                # 不要排除 searchOnline。如果模型习惯调用它，我们应该允许。
                # 并在 _execute_function 中将其映射到 web_search 逻辑，或者提示模型改用 web_search。
                # 但更简单的做法是：仍然排除它，但在System Prompt里强调 "Use web_search tool".
                
                # 之前代码排除 searchOnline 是为了强制模型使用 native web_search
                if func_def["name"] == "searchOnline":
                     continue
                
                parsed_tools.append({
                    "type": "function",
                    "name": func_def["name"],
                    "description": func_def["description"],
                    "parameters": func_def.get("parameters", {})
                })
        return parsed_tools
    
    def _execute_function(self, function_name: str, arguments: str) -> str:
        """
        执行函数调用
        
        Args:
            function_name: 函数名
            arguments: 参数JSON字符串或字典
            
        Returns:
            函数执行结果字符串
        """
        try:
            # 解析参数
            if isinstance(arguments, str):
                args = json.loads(arguments)
            else:
                args = arguments
            
            # 参数幻觉检测（Deepseek R1问题）
            # 检测类似 city: get_location() 的嵌套函数调用模式
            # 但要排除正常文本中的括号（如中文全角括号、Markdown等）
            for key, value in args.items():
                if isinstance(value, str):
                    # 更精确的检测：函数调用通常是 functionName(...) 的形式
                    # 且前面没有其他字符，后面紧跟括号
                    import re
                    # 匹配函数调用模式：字母开头，后跟字母数字下划线，然后是括号
                    if re.search(r'\b[a-zA-Z_][a-zA-Z0-9_]*\s*\(', value):
                        # 进一步检查：如果包含中文或大量文本，很可能是正常内容
                        if len(value) < 100 and not re.search(r'[\u4e00-\u9fff]', value):
                            return f"错误：参数 '{key}' 的值似乎是嵌套函数调用 '{value[:50]}'。请先单独调用该函数获取结果。"
            
            # 执行函数
            return self._execute_function_impl(function_name, args)
            
        except json.JSONDecodeError as e:
            return f"错误：参数JSON解析失败 - {str(e)}"
        except Exception as e:
            return f"错误：{str(e)}"
    
    def _execute_function_impl(self, function_name: str, args: Dict) -> str:
        """函数执行实现"""
        
        # 知识库管理
        if function_name == "getKnowledgeList":
            result = self.user.getKnowledgeList(args.get("_type", 0))
            if isinstance(result, dict):
                if args.get("_type", 0) == 0:  # 短期记忆
                    return "\n".join([f"{k}: {v}" for k, v in result.items()]) or "(空)"
                else:  # 基础知识库
                    return "\n".join(result.keys()) or "(空)"
            return str(result)
        
        elif function_name == "addShort":
            self.user.addShort(args.get("title", ""))
            return "已添加到短期记忆"
        
        elif function_name == "addBasis":
            self.user.addBasis(
                args.get("title", ""),
                args.get("context", ""),
                args.get("url", "")
            )
            return "已添加到基础知识库"
        
        elif function_name == "removeShort":
            self.user.removeShort(args.get("ID"))
            return "已删除短期记忆"
        
        elif function_name == "removeBasis":
            self.user.removeBasis(args.get("title", ""))
            return "已删除基础知识"
        
        elif function_name == "updateBasis":
            success, message = self.user.updateBasis(
                title=args.get("title", ""),
                new_title=args.get("new_title"),
                context=args.get("context"),
                url=args.get("url")
            )
            if success:
                updates = []
                if args.get("new_title"):
                    updates.append(f"标题已更新为'{args.get('new_title')}'")
                if args.get("context"):
                    updates.append("内容已更新")
                if args.get("url"):
                    updates.append("来源链接已更新")
                return f"已成功更新基础知识。{', '.join(updates) if updates else ''}"
            else:
                return f"更新失败: {message}"
        
        elif function_name == "getBasisContent":
            return self.user.getBasisContent(args.get("title", ""))
        
        elif function_name == "searchKeyword":
            result = self.user.search_keyword(
                args.get("keyword", ""),
                args.get("range", 10)
            )
            # 智能反馈：如果找不到结果，明确告知模型应该使用 web_search
            if result.startswith("未找到关键词"):
                return f"{result}。建议：本地知识库中没有此信息。请立即调用 `web_search` 工具联网搜索: '{args.get('keyword', '')}'"
            return result
        
        # 知识图谱功能 - 新增
        elif function_name == "linkKnowledge":
            success, msg = self.user.add_connection(
                args.get("source"),
                args.get("target"),
                args.get("relation"),
                args.get("description", "")
            )
            return f"{'成功' if success else '失败'}: {msg}"
            
        elif function_name == "categorizeKnowledge":
            # 如果分类名不存在，默认先创建或由User内部处理
            success, msg = self.user.move_knowledge_to_category(
                args.get("title"),
                args.get("category")
            )
            return f"{'成功' if success else '失败'}: {msg}"
            
        elif function_name == "createCategory":
            success, msg = self.user.create_category(
                args.get("name"),
                args.get("description", "") # 注意create_category参数可能只有name和color，需要检查
            )
            return f"{'成功' if success else '失败'}: {msg}"

        elif function_name == "analyzeConnections":
            # 这是一个分析工具，不是动作工具，应该返回相关知识
            # 现在改为 getKnowledgeConnections 
            return self.user.get_knowledge_connections(args.get("title"))

        elif function_name == "getKnowledgeGraphStructure":
            return json.dumps(self.user.get_knowledge_graph_structure(), ensure_ascii=False)

        elif function_name == "getKnowledgeConnections":
            return json.dumps(self.user.get_knowledge_connections(args.get("title")), ensure_ascii=False)

        elif function_name == "findPathBetweenKnowledge":
            return json.dumps(self.user.find_knowledge_path(args.get("start"), args.get("end")), ensure_ascii=False)
            
        # 对话历史管理
        elif function_name == "getContextLength":
            length = self.conversation_manager.get_context_length(
                args.get("offset", 0),
                conversation_id=self.conversation_id
            )
            return f"对话长度: {length} 字符"
        
        elif function_name == "getContext":
            content = self.conversation_manager.get_context(
                args.get("offset", 0),
                args.get("from_pos", 0),
                args.get("to_pos", None),
                conversation_id=self.conversation_id
            )
            return content if content else "无内容"
        
        elif function_name == "getContext_findKeyword":
            return self.conversation_manager.get_context_find_keyword(
                args.get("offset", 0),
                args.get("keyword", ""),
                args.get("range", 10),
                conversation_id=self.conversation_id
            )
        
        elif function_name == "getMainTitle":
            return self.conversation_manager.get_main_title(
                self.conversation_id,
                args.get("offset", 0)
            )
        
        # 知识图谱
        elif function_name == "analyzeConnections":
            connections = self.user.get_knowledge_connections(args.get("title", ""))
            return json.dumps(connections, ensure_ascii=False) if connections else "无关联连接"
            
        elif function_name == "linkKnowledge":
            success, msg = self.user.add_connection(
                args.get("source"),
                args.get("target"),
                args.get("relation"),
                args.get("description", "")
            )
            return msg
            
        elif function_name == "categorizeKnowledge":
            success, msg = self.user.set_knowledge_category(
                args.get("title"),
                args.get("category")
            )
            return msg
            
        elif function_name == "createCategory":
            success, msg = self.user.create_category(args.get("name"))
            return msg
        
        else:
            return f"错误：未知函数 {function_name}"
    
    def upload_file(self, file_path: str):
        """
        上传文件到火山引擎
        """
        try:
            print(f"[FILE] 上传文件: {file_path}")
            # 指定 purpose 为 assistants 以支持上下文缓存等高级功能
            with open(file_path, "rb") as f:
                file_obj = self.client.files.create(
                    file=f,
                    purpose="user_data"
                )
            print(f"[FILE] 上传成功 ID: {file_obj.id}")
            return file_obj
        except Exception as e:
            print(f"[ERROR] 文件上传失败: {e}")
            raise e

    def sendMessage(
        self,
        msg: str,
        stream: bool = True,
        max_rounds: int = 10,
        enable_thinking: bool = True,
        enable_web_search: bool = True,
        enable_tools: bool = True,
        show_token_usage: bool = False,
        file_ids: List[str] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        发送消息（支持多轮对话、流式输出、文件和Context Caching）
        """
        try:
            # 确保对话已创建
            if not self.conversation_id:
                self.conversation_id = self.conversation_manager.create_conversation()
            
            # 保存用户消息
            # 暂存 file_ids 到 metadata
            metadata = {}
            if file_ids:
                metadata["file_ids"] = file_ids
            self.conversation_manager.add_message(self.conversation_id, "user", msg, metadata=metadata)
            
            # 构造本次用户消息内容 (多模态)
            # 如果没有文件，直接使用字符串，避免API兼容性问题 (Error: unknown type: text)
            if not file_ids:
                user_content = msg
            else:
                user_content = []
                user_content.append({"type": "text", "text": msg})
                for fid in file_ids:
                    user_content.append({
                        "type": "image_url",
                        "image_url": {
                             "url": fid
                        }
                    })

            # Check Context Cache
            last_response_id = self.conversation_manager.get_last_volc_response_id(
                self.conversation_id, 
                current_model_name=self.model_name
            )
            previous_response_id = None
            messages = []

            if last_response_id:
                # Cache Hit: 仅发送新消息
                print(f"[CACHE] Hit! Resuming from: {last_response_id}")
                previous_response_id = last_response_id
                messages = [{"role": "user", "content": user_content}]
            else:
                # Cache Miss: 全量构建
                print(f"[CACHE] Miss. Building full context.")
                # _build_initial_messages 默认只加了文本，我们需要替换最后一条
                messages = self._build_initial_messages(msg)
                if file_ids:
                    messages.pop() # 移除默认纯文本user消息
                    messages.append({"role": "user", "content": user_content})
            
            # 多轮对话循环
            accumulated_content = ""
            accumulated_reasoning = ""  # 累积思维链内容
            process_steps = []  # 记录完整的工具调用过程
            
            # previous_response_id 已在上面初始化
            current_function_outputs = []  # 当前轮的function输出
            
            try:
                for round_num in range(max_rounds):
                    # [FIX] 增加短暂延迟以提高多轮对话稳定性 (官方建议 100ms)
                    if round_num > 0:
                        time.sleep(0.1)
                        
                    print(f"\n[DEBUG] ===== 第 {round_num + 1} 轮 =====")
                    print(f"[DEBUG] Messages数量: {len(messages)} | Function消息: {len([m for m in messages if m.get('role')=='function'])}")
                    
                    # 构建请求
                    print(f"[DEBUG_REQ] Pkg_ID: {previous_response_id} | Func_Outs: {len(current_function_outputs) if current_function_outputs else 0}")
                    if not previous_response_id and messages:
                        last_msg = messages[-1]
                        print(f"[DEBUG_REQ] Last Msg Role: {last_msg.get('role')} | Content: {str(last_msg.get('content'))[:50]}...")
                        if last_msg.get('role') == 'assistant' and 'tool_calls' in last_msg:
                            print(f"[DEBUG_REQ] Last Msg ToolCalls: {len(last_msg['tool_calls'])}")

                    request_params = self._build_request_params(
                        messages=messages,
                        previous_response_id=previous_response_id,
                        enable_thinking=enable_thinking,
                        enable_tools=enable_tools,
                        current_function_outputs=current_function_outputs  # 传递当前轮的function结果
                    )
                    
                    # 调用API
                    print(f"[DEBUG_API] 发送请求 (Input Type: {'Messages' if 'messages' in str(request_params.get('input')) else 'Other'})")
                    
                    # -------------------------------------------------------------
                    # Robust Retry Logic for Context Mismatch (400)
                    # -------------------------------------------------------------
                    response_iterator = None
                    try:
                        response_iterator = self.client.responses.create(**request_params)
                        # Test iterator initialization by peeking (optional, but iteration triggers validation)
                    except Exception as e:
                         pass # Handle below

                    # We need to wrap the iteration in a way that catches the error 
                    # which might happen during the First yield of the stream
                    
                    def safe_iter(iterator):
                        try:
                            for item in iterator:
                                yield item
                        except Exception as e:
                            raise e 
                    
                    # Manual Retry Loop
                    # We use a flag to indicate if we are in the "Retry" phase
                    is_retry_mode = False
                    
                    try:
                         # Attempt 1
                         if response_iterator is None: # Creation failed
                             # Re-create inside try to catch creation errors
                             response_iterator = self.client.responses.create(**request_params)
                         
                         chunks = safe_iter(response_iterator)
                    except Exception as e:
                        error_str = str(e)
                        if "previous_response_id" in error_str and "400" in error_str and "previous_response_id" in request_params:
                             print(f"[ERROR] 捕获 Context Mismatch (400) on Init. Retrying without ID...")
                             del request_params["previous_response_id"]
                             previous_response_id = None
                             response_iterator = self.client.responses.create(**request_params)
                             chunks = safe_iter(response_iterator)
                             is_retry_mode = True
                        else:
                             raise e

                    # Process Stream
                    print(f"[DEBUG_API] 请求返回，开始处理流... (Retry Mode: {is_retry_mode})")
                    
                    # 处理响应流（直接在这里处理以支持实时yield）
                    round_content = ""
                    function_calls = []
                    has_web_search = False
                    current_function_outputs = []  # 重置当前轮的function输出
                    if not is_retry_mode:
                         # implied previous_response_id logic... but we reset it for the loop
                         pass 
                    previous_response_id = None # Will be updated from stream
                    
                    # 记录本轮的事件
                    current_round_steps = []
                    
                    try:
                        for chunk in chunks:
                            chunk_type = getattr(chunk, 'type', None)
                            
                            # 获取 response_id
                            if hasattr(chunk, 'response'):
                                response_obj = getattr(chunk, 'response')
                                if hasattr(response_obj, 'id'):
                                    previous_response_id = response_obj.id
                            
                            # 文本增量 - 立即yield给前端
                            if chunk_type == 'response.output_text.delta':
                                delta = getattr(chunk, 'delta', '')
                                round_content += delta
                                accumulated_content += delta
                                yield {"type": "content", "content": delta}
                        
                            # 思考过程增量 (如果模型支持)
                            elif chunk_type in ['response.reasoning_text.delta', 'response.reasoning_summary_text.delta']:
                                delta = getattr(chunk, 'delta', '')
                                accumulated_reasoning += delta  # 累积思维链
                                yield {"type": "reasoning_content", "content": delta}

                            # 函数参数增量 - 静默处理
                            elif chunk_type == 'response.function_call_arguments.delta':
                                pass
                        
                            # -------------------------------------------------------------
                            # 核心修复: 过滤掉云端自动注入的"Current time"类系统干扰
                            # -------------------------------------------------------------
                            elif chunk_type == 'response.output_item.done':
                                item = getattr(chunk, 'item', None)
                                if item:
                                    # 1. 提取 Search Keyword
                                    item_type = getattr(item, 'type', '')
                                    if 'web_search_call' in item_type:
                                        action = getattr(item, 'action', None)
                                        if action:
                                            query = getattr(action, 'query', None)
                                            if query:
                                                print(f"[WEB_SEARCH] 捕捉到关键词: {query}")
                                                # 前端即使收到中间状态，只要 query 字段有值就会更新UI
                                                step = {
                                                    "type": "web_search", 
                                                    "content": f"正在搜索: {query}",
                                                    "status": "正在搜索",
                                                    "query": query
                                                }
                                                yield step
                                                process_steps.append(step)
                            
                            # Web搜索事件
                            elif chunk_type in ['response.web_search_call.in_progress',
                                            'response.web_search_call.searching', 
                                            'response.web_search_call.completed']:
                                has_web_search = True
                                status_map = {
                                    'response.web_search_call.in_progress': '准备搜索',
                                    'response.web_search_call.searching': '正在搜索',
                                    'response.web_search_call.completed': '搜索完成'
                                }
                                status = status_map.get(chunk_type, chunk_type)
                                
                                # 注意: 搜索关键词通常在 response.output_item.done 事件中，这里可能拿不到
                                # 但保留此处的逻辑以防万一
                                query_text = ""
                                ws_obj = getattr(chunk, 'web_search_call', None) or getattr(chunk, 'web_search', None)
                                if ws_obj:
                                    query_text = getattr(ws_obj, 'query', "")
                                
                                step_content = f"{status}: {query_text}" if query_text else status
                                print(f"[WEB_SEARCH] {status}")

                                # 避免重复发送"搜索完成"且无内容的消息，防止前端闪烁或重复
                                if chunk_type == 'response.web_search_call.completed':
                                    pass
                                else:
                                    step = {
                                        "type": "web_search", 
                                        "content": step_content,
                                        "status": status,
                                        "query": query_text
                                    }
                                    yield step
                                    process_steps.append(step)


                            # 响应完成 - 提取函数调用
                            elif chunk_type == 'response.completed':
                                response_obj = getattr(chunk, 'response', None)
                                if response_obj and hasattr(response_obj, 'output'):
                                    output = response_obj.output
                                    for item in output:
                                        item_type = getattr(item, 'type', None)
                                        if item_type == 'function_call':
                                            function_calls.append({
                                                "name": getattr(item, 'name', None),
                                                "arguments": getattr(item, 'arguments', '{}'),
                                                "call_id": getattr(item, 'call_id', None)
                                            })
                                
                                # Token统计
                                if hasattr(response_obj, 'usage'):
                                    usage = response_obj.usage
                                    print(f"[TOKEN] Input: {usage.input_tokens}, Output: {usage.output_tokens}, Total: {usage.total_tokens}")
                                    yield {
                                        "type": "token_usage",
                                        "input_tokens": usage.input_tokens,
                                        "output_tokens": usage.output_tokens,
                                        "total_tokens": usage.total_tokens
                                    }
                                    # 记录日志到文件
                                    self._log_token_usage_safe(usage, has_web_search, function_calls, process_steps, msg)
                    
                    
                    except Exception as e:
                        print(f"[ERROR] Stream processing error: {e}")
                        # 如果是上下文错误，在这里其实很难直接retry，因为已经yield了部分内容
                        # 但至少我们捕获它，防止整个Server崩掉
                        if "previous response" in str(e):
                             print("[CRITICAL] Context consistency error detected.")
                        raise e

                    # 检查 previous_response_id 获取情况
                    if previous_response_id:
                        print(f"[DEBUG] 已捕获 Response ID: {previous_response_id}")
                    else:
                        print(f"[WARNING] 本轮未能捕获 Response ID，下轮将回退到全量上下文传输 (Token开销增加)")

                    # 本轮文本内容作为步骤加入
                    if round_content:
                        # 注意：这里我们加入的是本轮产生的content，方便前端按顺序渲染
                        process_steps.append({"type": "content", "content": round_content})
                        # yield {"type": "content", "content": round_content} # 之前已经yield了delta
                    
                    # 处理函数调用
                    if function_calls:
                        # -------------------------------------------------------------
                        # [FIX] 核心修复: 构建 Assistant Message (Tool Calls) 并加入历史
                        # 确保多轮对话上下文完整 (User -> Assistant[Call] -> Tool[Output])
                        # 否则在 Context Cache 失效回退时，Tool Output 会成为无头消息，导致模型死循环
                        # -------------------------------------------------------------
                        tool_calls_payload = []
                        for fc in function_calls:
                            tool_calls_payload.append({
                                "id": fc["call_id"],
                                "type": "function",
                                "function": {
                                    "name": fc["name"],
                                    "arguments": fc["arguments"]
                                }
                            })
                        
                        # 只有当messages不为空时才追加(理论上肯定不为空)
                        messages.append({
                            "role": "assistant",
                            "content": round_content or "",
                            "tool_calls": tool_calls_payload
                        })
                        
                        function_outputs = []
                        
                        for func_call in function_calls:
                            func_name = func_call["name"]
                            func_args = func_call["arguments"]
                            call_id = func_call["call_id"]
                            
                            print(f"\n[FUNCTION] 调用: {func_name}")
                            print(f"[FUNCTION] 参数: {func_args}")
                            
                            # 记录调用步骤
                            step_call = {
                                "type": "function_call",
                                "name": func_name,
                                "arguments": func_args
                            }
                            process_steps.append(step_call)
                            yield step_call
                            
                            # 执行函数
                            result = self._execute_function(func_name, func_args)
                            
                            print(f"[FUNCTION] 结果: {result[:100]}..." if len(result) > 100 else f"[FUNCTION] 结果: {result}")
                            
                            # 记录结果步骤
                            step_result = {
                                "type": "function_result",
                                "name": func_name,
                                "result": result
                            }
                            process_steps.append(step_result)
                            yield step_result
                            
                            # 收集函数输出
                            current_function_outputs.append({
                                "type": "function_call_output",
                                "call_id": call_id,
                                "output": result
                            })
                        
                        # 继续下一轮（保持messages累积，但current_function_outputs已重置）
                        messages = self._append_function_outputs(messages, current_function_outputs)
                        
                        # [DEBUG] 打印更新后的历史状态
                        print(f"[DEBUG_HIST] 更新历史后消息数: {len(messages)}")
                        if len(messages) >= 2:
                            print(f"[DEBUG_HIST] 倒数第二条: {messages[-2].get('role')} (Tools: {len(messages[-2].get('tool_calls', []))})")
                            print(f"[DEBUG_HIST] 最后一条: {messages[-1].get('role')} (Type: {messages[-1].get('type', 'text')})")

                        # 通知前端清除上一轮的临时content显示（如果需要清空以便重新生成解释）
                        # 但这里我们希望保留历史content，所以不需要 clear_round_content
                        continue
                    
                    # 没有函数调用，对话结束
                    yield {"type": "done", "content": accumulated_content}
                    return
                
                # 达到最大轮次
                print(f"[WARNING] 达到最大轮次 {max_rounds}")
                yield {"type": "done", "content": accumulated_content}
            
            finally:
                # 统一保存消息（无论正常结束、Function调用中断、Client中断）
                # 只有当有内容或有步骤时才保存
                if accumulated_content or process_steps:
                    print(f"[DEBUG] 保存助手消息，Steps: {len(process_steps)}")
                    metadata = {"process_steps": process_steps}
                    
                    # 自动生成对话标题（使用conclusion_model）
                    if accumulated_content:
                        try:
                            title = self._generate_conversation_title(msg, accumulated_content)
                            metadata["exchange_summary"] = title
                            # 更新对话标题
                            self.conversation_manager.update_conversation_title(self.conversation_id, title)
                        except Exception as e:
                            print(f"[ERROR] 自动生成标题失败: {e}")
                    
                    # 保存思维链内容（如果有）
                    if accumulated_reasoning:
                        metadata["reasoning_content"] = accumulated_reasoning
                    
                    self.conversation_manager.add_message(
                        self.conversation_id,
                        "assistant",
                        accumulated_content,
                        metadata=metadata
                    )
                
                # 保存 Context Cache ID
                if previous_response_id:
                    self.conversation_manager.update_volc_response_id(
                        self.conversation_id, 
                        previous_response_id,
                        model_name=self.model_name
                    )
                    print(f"[CACHE] Saved Response ID: {previous_response_id}")
                else: 
                     # Case: 模型可能在最后一轮 function execution 后，返回空内容结束了
                     # 此时应该检查是否有未保存的 process_steps，但通常 accumulated_content 会为空
                     # 如果 accumulated_content 为空，但有 steps，上面已经保存了
                     # 唯一的问题是：如果模型在最后一次响应里只输出了 function_call 却没有 text content
                     # 并且 tool loop 结束了（例如 max rounds），那么 accumulated_content 为空
                     # 已经在上面保存了。
                     
                     # 但用户遇到的情况是： json里 content: ""，但是有 process_steps。
                     # 这说明前端如果不显示 process_steps，就什么都看不到。
                     # 或者 accumulated_content 本来就是空的。
                     
                     # 修正：当流式输出结束后，如果 accumulated_content 为空，尝试给一个默认值
                     # 或者前端应该渲染 process_steps。
                     
                     # 实际上，如果 content 为空，前端可能就什么都不显示，只显示了一个空白的气泡？
                     # 或者前端根本没渲染？
                     
                     # 如果是 function_call 导致的中断，那么此时 content 确实可能为空，等待下一轮
                     # 但这里是 finally 块，意味着 sendMessage 彻底结束
                     
                     pass
            
        except Exception as e:
            error_msg = f"错误: {str(e)}"
            print(f"[ERROR] {error_msg}")
            yield {"type": "error", "content": error_msg}
    
    def _log_token_usage_safe(self, usage, has_web_search, function_calls, process_steps, user_message=None):
        """安全地记录Token日志（不影响主流程）"""
        try:
            # 推断动作类型
            action_type = "chat"
            if has_web_search:
                action_type = "web_search"
            elif function_calls:
                # 如果有函数调用，取第一个函数名作为动作类型
                action_type = f"tool:{function_calls[0].get('name', 'unknown')}"
            elif len(process_steps) > 0:
                # 检查之前的步骤是否有tool
                for step in process_steps:
                    if step.get('type') == 'function_call':
                        action_type = f"tool:{step.get('name')}"
                        break
                    elif step.get('type') == 'web_search':
                        action_type = "web_search"
                        break
            
            # 获取当前对话标题
            # 优先使用当前用户消息作为本轮对话的标题（截取前30个字符）
            if user_message:
                clean_msg = user_message.strip()
                conv_title = clean_msg[:30] + "..." if len(clean_msg) > 30 else clean_msg
            else:
                conv_title = "新对话"
                if self.conversation_id:
                    try:
                        conv_data = self.conversation_manager.get_conversation(self.conversation_id)
                        conv_title = conv_data.get("title", conv_title)
                    except:
                        pass
                
            self.user.log_token_usage(
                self.conversation_id or "unknown", 
                conv_title, 
                action_type, 
                usage.input_tokens, 
                usage.output_tokens
            )
        except Exception as e:
            print(f"[WARNING] 记录Token日志失败: {e}")

    def _build_initial_messages(self, user_msg: str) -> List[Dict]:
        """构建初始消息列表"""
        messages = [
            {"role": "system", "content": self.system_prompt}
        ]
        
        # 添加最近交流概览（上下文）
        if self.conversation_id:
            recent_summaries = self.conversation_manager.get_recent_exchange_summaries(
                self.conversation_id, limit=2  # 优化：从3减少到2，减少Token使用和上下文处理时间
            )
            if recent_summaries:
                context_summary = "## 最近交流概览\n"
                for i, exchange in enumerate(recent_summaries, 1):
                    # 截断过长的用户输入
                    user_text = exchange['user']
                    if len(user_text) > 50:
                        user_text = user_text[:50] + "..."
                    
                    context_summary += f"{i}. 用户: {user_text}\n"
                    if 'summary' in exchange:
                         context_summary += f"   AI总结: {exchange['summary']}\n"
                
                messages.append({
                    "role": "system",
                    "content": context_summary + "\n(历史摘要已简化，如需精确历史请调用 getContext)"
                })
        
        # 添加用户消息
        messages.append({"role": "user", "content": user_msg})
        
        # 重要：剔除历史对话中的 reasoning_content 字段
        # 根据文档：模型版本在251228之前需要剔除，避免影响推理逻辑
        messages = self._strip_reasoning_content(messages)
        
        return messages
    
    def _strip_reasoning_content(self, messages: List[Dict]) -> List[Dict]:
        """剔除消息中的reasoning_content字段（符合文档要求）"""
        cleaned = []
        for msg in messages:
            cleaned_msg = {"role": msg["role"], "content": msg["content"]}
            # 保留其他必要字段（如tool_calls等），但排除reasoning_content
            for key in msg:
                if key not in ["role", "content", "reasoning_content", "metadata"]:
                    cleaned_msg[key] = msg[key]
            cleaned.append(cleaned_msg)
        return cleaned
    
    def _generate_conversation_title(self, user_message: str, assistant_response: str) -> str:
        """使用conclusion_model生成对话标题"""
        try:
            conclusion_model = CONFIG.get('conclusion_model', 'doubao-seed-1-6-flash-250828')
            model_info = CONFIG.get('models', {}).get(conclusion_model, {})
            api_key = model_info.get('api_key', "")
            
            # 创建临时客户端用于生成标题
            global _ARK_CLIENT_CACHE
            if api_key in _ARK_CLIENT_CACHE:
                client = _ARK_CLIENT_CACHE[api_key]
            else:
                client = Ark(api_key=api_key, timeout=30.0)
                _ARK_CLIENT_CACHE[api_key] = client
            
            # 构建prompt
            prompt = f"""根据以下对话内容，生成一个简洁准确的标题（10-20字）。

用户问题：{user_message[:200]}
助手回答：{assistant_response[:500]}

要求：
1. 准确概括对话核心内容
2. 简洁明了，10-20字
3. 只输出标题，不要其他内容
4. 避免使用"用户询问"、"提供信息"等冗余词汇

标题："""
            
            # 调用API
            response = client.chat.completions.create(
                model=conclusion_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=50
            )
            
            title = response.choices[0].message.content.strip()
            # 清理可能的引号
            title = title.strip('"').strip("'").strip()
            
            print(f"[TITLE] 生成标题: {title}")
            return title[:50]  # 限制最大长度
            
        except Exception as e:
            print(f"[ERROR] 生成标题失败: {e}")
            # 降级方案：使用用户消息前30字
            return user_message[:30] + ("..." if len(user_message) > 30 else "")
    
    def _build_request_params(
        self,
        messages: List[Dict],
        previous_response_id: Optional[str],
        enable_thinking: bool,
        enable_tools: bool,
        current_function_outputs: List[Dict] = None
    ) -> Dict:
        """构建API请求参数"""
        params = {
            "model": self.model_name,
            "stream": True,
            # 设置最大输出长度，支持详尽的报告级内容（回答+思维链总长度）
            # doubao-seed-1-6-251015的上下文窗口为96k，思维链窗口32k
            # 设置16k可支持5000-10000字的详细报告（约15000-30000 tokens）
            "max_output_tokens": 65536   # 16k tokens，足够支持详尽的学术报告
        }
        
        # 启用深度思考（新版模型支持与Tools同时使用）
        if enable_thinking:
            params["thinking"] = {"type": "enabled"}
        else:
             params["thinking"] = {"type": "disabled"}
        
        if enable_tools:
            params["tools"] = self.tools
            # 注意：max_tool_calls 仅支持内置工具，自定义function不支持
        
        # 核心逻辑修改：支持 Context Caching
        if previous_response_id is None:
            # 场景1：无缓存，发送完整历史
            params["input"] = messages
            print(f"[DEBUG_REQ] Round 1 (No Cache) Input Messages Count: {len(messages)}")
        else:
            params["previous_response_id"] = previous_response_id
            
            # 场景2：函数调用中间轮（有 Function Outputs）
            if current_function_outputs:
                params["input"] = current_function_outputs
                print(f"[DEBUG_REQ] Continuing Round - Func Outputs: {len(current_function_outputs)}")
            
            # 场景3：Context Caching 命中（首轮，但有之前的ID）
            # 此时 messages 应该只包含新的用户消息
            elif messages:
                params["input"] = messages
                print(f"[DEBUG_REQ] Round 1 (Cache Hit) Input Messages Count: {len(messages)}")
            
            else:
                # 场景4：异常空输入
                print("[WARNING] 发送了空User消息！")
                params["input"] = [{"role": "user", "content": ""}]
        
        return params
    
    def _append_function_outputs(
        self,
        messages: List[Dict],
        function_outputs: List[Dict]
    ) -> List[Dict]:
        """追加函数输出到消息列表"""
        return messages + function_outputs
    
    def _process_response_stream(
        self,
        response,
        round_num: int,
        show_token_usage: bool
    ) -> Dict:
        """
        处理响应流
        
        Returns:
            {
                "content": str,
                "function_calls": List[Dict],
                "has_web_search": bool,
                "response_id": str
            }
        """
        content = ""
        function_calls = []
        has_web_search = False
        response_id = None
        
        for chunk in response:
            chunk_type = getattr(chunk, 'type', None)
            
            # 获取 response_id
            if hasattr(chunk, 'response'):
                response_obj = getattr(chunk, 'response')
                if hasattr(response_obj, 'id'):
                    response_id = response_obj.id
            
            # 处理不同事件类型
            if chunk_type == 'response.output_text.delta':
                # 文本增量
                delta = getattr(chunk, 'delta', '')
                content += delta
                # 只在控制台显示调试信息，不输出完整文本
                # print(delta, end='', flush=True)
            
            elif chunk_type == 'response.function_call_arguments.delta':
                # 函数参数增量（静默处理，done时才处理完整参数）
                pass
            
            elif chunk_type in ['response.web_search_call.in_progress',
                               'response.web_search_call.searching',
                               'response.web_search_call.completed']:
                # Web搜索事件
                has_web_search = True
                status_map = {
                    'response.web_search_call.in_progress': '准备搜索',
                    'response.web_search_call.searching': '正在搜索',
                    'response.web_search_call.completed': '搜索完成'
                }
                print(f"[WEB_SEARCH] {status_map.get(chunk_type, chunk_type)}")
            
            elif chunk_type == 'response.completed':
                # 响应完成，提取函数调用
                response_obj = getattr(chunk, 'response', None)
                if response_obj and hasattr(response_obj, 'output'):
                    output = response_obj.output
                    for item in output:
                        item_type = getattr(item, 'type', None)
                        if item_type == 'function_call':
                            function_calls.append({
                                "name": getattr(item, 'name', None),
                                "arguments": getattr(item, 'arguments', '{}'),
                                "call_id": getattr(item, 'call_id', None)
                            })
                
                # Token统计
                if show_token_usage and hasattr(response_obj, 'usage'):
                    usage = response_obj.usage
                    print(f"[TOKEN] Input: {usage.input_tokens}, Output: {usage.output_tokens}, Total: {usage.total_tokens}")
        
        return {
            "content": content,
            "function_calls": function_calls,
            "has_web_search": has_web_search,
            "response_id": response_id
        }
    
    def reset_conversation(self):
        """重置对话"""
        self.conversation_id = self.conversation_manager.create_conversation()
    
    def get_conversation_history(self):
        """获取对话历史"""
        if not self.conversation_id:
            return []
        return self.conversation_manager.get_messages(self.conversation_id)
    
    def analyzeConnections(self, title: str) -> str:
        """分析知识连接（简化实现）"""
        return f"知识 '{title}' 的连接分析功能尚未完整实现"
