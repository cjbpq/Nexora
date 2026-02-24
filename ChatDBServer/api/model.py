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
from openai import OpenAI
from tools import TOOLS
from database import User
from chroma_client import ChromaStore
from conversation_manager import ConversationManager

# 配置文件路径
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config.json')
MODELS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'models.json')
MODELS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'models.json')

# 加载配置
def load_config():
    config = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
    if os.path.exists(MODELS_PATH):
        with open(MODELS_PATH, 'r', encoding='utf-8') as f:
            models_cfg = json.load(f)
        config["models"] = models_cfg.get("models", models_cfg)
        if "providers" in models_cfg:
            config["providers"] = models_cfg.get("providers", {})
    return config

CONFIG = load_config()

# 清除代理设置
if 'HTTP_PROXY' in os.environ:
    del os.environ['HTTP_PROXY']
if 'HTTPS_PROXY' in os.environ:
    del os.environ['HTTPS_PROXY']

# 全局客户端缓存，实现连接池复用 (Keep-Alive)
_CLIENT_CACHE = {}

def _ensure_json_serializable(obj):
    """
    递归确保对象可以被 JSON 序列化
    将所有不可序列化的对象转换为字符串
    """
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    elif isinstance(obj, dict):
        return {k: _ensure_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_ensure_json_serializable(item) for item in obj]
    else:
        # 对于任何其他类型（包括 SDK 对象），转换为字符串
        return str(obj)

class Model:
    """大模型封装类 - 支持多供应商"""
    
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
        
        # 确定模型名称（增加黑名单过滤逻辑）
        requested_model = model_name
        
        # 加载权限配置
        blacklist = []
        try:
            perm_path = os.path.join(os.path.dirname(CONFIG_PATH), 'data', 'model_permissions.json')
            if os.path.exists(perm_path):
                with open(perm_path, 'r', encoding='utf-8') as f:
                    perm_data = json.load(f)
                    user_blacklists = perm_data.get('user_blacklists', {})
                    blacklist = user_blacklists.get(username, perm_data.get('default_blacklist', []))
        except Exception as e:
            print(f"Error loading blacklist in Model: {e}")

        if requested_model:
            # 如果请求的模型在黑名单中，或者根本不是有效的模型ID，进行处理
            if requested_model in blacklist or requested_model not in CONFIG.get('models', {}):
                # 寻找第一个真正可用的模型
                available = [m for m in CONFIG.get('models', {}).keys() if m not in blacklist]
                if not available:
                    # 如果一个可用的都没有，且请求的又非法/被禁，强制设为一个非法值以触发后续报错，或抛出异常
                    self.model_name = "NO_AVAILABLE_MODEL"
                else:
                    # 如果请求的是非法ID（如 "Select Model"），则使用第一个可用的合法模型
                    self.model_name = available[0]
            else:
                self.model_name = requested_model
        else:
            # 使用默认模型，如果默认模型被禁，寻找第一个可用的
            default_model = CONFIG.get('default_model', 'doubao-seed-1-6-251015')
            if default_model in blacklist:
                available = [m for m in CONFIG.get('models', {}).keys() if m not in blacklist]
                if available:
                    self.model_name = available[0]
                else:
                    self.model_name = "NO_AVAILABLE_MODEL"
            else:
                self.model_name = default_model
            
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
        
        # 获取模型配置和供应商信息
        model_info = CONFIG.get('models', {}).get(self.model_name, {})
        self.provider = model_info.get('provider', 'volcengine')
        provider_info = CONFIG.get('providers', {}).get(self.provider, {})
        
        api_key = provider_info.get('api_key', "")
        base_url = provider_info.get('base_url')

        # 初始化客户端 (使用全局缓存实现连接复用)
        global _CLIENT_CACHE
        cache_key = f"{self.provider}_{api_key}"
        
        if cache_key in _CLIENT_CACHE:
            self.client = _CLIENT_CACHE[cache_key]
        else:
            # 首次连接
            print(f"[INIT] 创建新的 {self.provider} 客户端连接 (Key: ...{api_key[-4:]})")
            
            if self.provider == 'volcengine':
                self.client = Ark(
                    api_key=api_key,
                    base_url=base_url,
                    timeout=120.0,
                    max_retries=2
                )
            else:
                # Stepfun 或其他 OpenAI 兼容接口
                self.client = OpenAI(
                    api_key=api_key,
                    base_url=base_url,
                    timeout=120.0
                )
            _CLIENT_CACHE[cache_key] = self.client
        
        # 工具定义
        self.tools = self._parse_tools(TOOLS)
    
    def get_embedding(self, text: str) -> List[float]:
        """获取文本向量 (OpenAI/Alibaba 兼容接口)"""
        embedding_key = CONFIG.get('default_embedding_model', "text-embedding-v3")

        embedding_model = CONFIG.get('embedding_model', {}).get(embedding_key, {}).get('name', embedding_key)
        provider_name = CONFIG.get('embedding_model', {}).get(embedding_key, {}).get('provider')
        if not provider_name:
            provider_name = 'aliyun_embedding' if 'aliyun_embedding' in CONFIG.get('providers', {}) else self.provider
        provider_info = CONFIG.get('providers', {}).get(provider_name, {})
        
        api_key = provider_info.get('api_key')
        base_url = provider_info.get('base_url')

        # 使用 OpenAI 客户端进行调用（大部分厂商均兼容此模式）
        temp_client = OpenAI(
            api_key=api_key,
            base_url=base_url
        )
        
        response = temp_client.embeddings.create(
            model=embedding_model,
            input=text
        )
        return response.data[0].embedding

    def _get_default_system_prompt(self) -> str:
        """获取极简高效的系统提示词"""
        import prompts
        # 检查是否有特定模型的自定义提示词
        if hasattr(prompts, 'others') and self.model_name in prompts.others:
            return prompts.others[self.model_name]
        return prompts.default
    
    def _get_default_web_search_prompt(self) -> str:
        """获取默认的联网搜索系统提示词"""
        import prompts
        return prompts.web_search_default

    def _estimate_token_count(self, text: str) -> int:
        """估算 token 数（当 provider 不返回 usage 时的兜底）"""
        if not text:
            return 0
        try:
            s = str(text)
            cjk = 0
            for ch in s:
                if '\u4e00' <= ch <= '\u9fff':
                    cjk += 1
            other = max(0, len(s) - cjk)
            # 经验估算：中文约 1.6 token/字，其他字符约 1 token/4字符
            est = int(cjk * 1.6 + other / 4.0)
            return max(1, est)
        except Exception:
            return max(1, len(str(text)) // 4)

    def _parse_tools(self, tools_config: List[Dict]) -> List[Dict]:
        """解析工具定义为API格式 - 兼容不同供应商"""
        parsed_tools = []
        rag_cfg = CONFIG.get("rag_database", {}) if isinstance(CONFIG, dict) else {}
        rag_enabled = bool(rag_cfg.get("rag_database_enabled", False))
        
        # 1. 火山引擎专用：内置 web_search
        provider = getattr(self, 'provider', 'volcengine')
        if provider == 'volcengine':
            parsed_tools.append({
                "type": "web_search"
            })
        
        # 2. 解析自定义 function 工具
        for tool in tools_config:
            if tool["type"] == "function":
                func_def = tool["function"]
                if func_def.get("name") == "vectorSearch" and not rag_enabled:
                                    continue
                                
                # 排除被 native web_search 替代的冗余工具
                if func_def["name"] in ["searchOnline", "web_search"] and provider == 'volcengine':
                     continue
                
                if provider == 'volcengine':
                    # 火山引擎 responses API 使用扁平结构
                    parsed_tools.append({
                        "type": "function",
                        "name": func_def["name"],
                        "description": func_def["description"],
                        "parameters": func_def.get("parameters", {})
                    })
                else:
                    # 标准 OpenAI 格式 (Stepfun 等)
                    parsed_tools.append({
                        "type": "function",
                        "function": {
                            "name": func_def["name"],
                            "description": func_def["description"],
                            "parameters": func_def.get("parameters", {})
                        }
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
            raw_result = self._execute_function_impl(function_name, args)
            
            # [TOKEN 优化] 智能脱水处理
            return self._sanitize_function_result(raw_result, function_name)
            
        except json.JSONDecodeError as e:
            return f"错误：参数JSON解析失败 - {str(e)}"
        except Exception as e:
            return f"错误：{str(e)}"

    def _sanitize_function_result(self, result: Any, func_name: str) -> str:
        """对函数输出进行'脱水'处理，防止 Context 溢出"""
        if not isinstance(result, str):
            result = str(result)
            
        # 设定阈值：2500 字符 (约 1500-2000 tokens)
        limit = 2500
        if len(result) <= limit:
            return result
            
        # 超过限制，保留头部 1200 和 尾部 800
        print(f"[TOKEN_OPT] 对工具 {func_name} 的结果进行了脱水 (原长度: {len(result)})")
        prefix = result[:1200]
        suffix = result[-800:]
        omitted_len = len(result) - 2000
        
        return f"{prefix}\n\n... [数据过长，已自动省略 {omitted_len} 字符。如果需要读取中间内容，请使用 getContext 指定范围阅读] ...\n\n{suffix}"
    
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
        elif function_name == "vectorSearch":
            query = args.get("query", "")
            top_k = int(args.get("top_k") or 5)
            if not query:
                return "missing query"
            rag_cfg = CONFIG.get("rag_database", {}) if isinstance(CONFIG, dict) else {}
            if not rag_cfg.get("rag_database_enabled", False):
                return "vector db disabled"
            try:
                store = ChromaStore(rag_cfg)
                result = store.query_text(self.username, query, top_k=top_k)
                ids = result.get("ids", [[]])[0] if isinstance(result.get("ids"), list) else []
                metas = result.get("metadatas", [[]])[0] if isinstance(result.get("metadatas"), list) else []
                dists = result.get("distances", [[]])[0] if isinstance(result.get("distances"), list) else []
                payload = []
                for i, vid in enumerate(ids):
                    meta = metas[i] if i < len(metas) else {}
                    score = None
                    if i < len(dists) and dists[i] is not None:
                        score = 1 - dists[i]
                    payload.append({
                        "id": vid,
                        "title": meta.get("title"),
                        "score": score
                    })
                return json.dumps(payload, ensure_ascii=False)
            except Exception as e:
                return f"vector search error: {str(e)}"

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
        
        elif function_name == "web_search":
            query = args.get("query", "")
            print(f"[SEARCH] 执行联网搜索: {query}")
            
            # 如果是外部模型调用此函数，我们使用一个支持搜索的火山引擎模型来中转获取结果
            try:
                # 寻找配置好的搜索模型，默认回退
                volc_provider = CONFIG.get('providers', {}).get('volcengine', {})
                volc_key = volc_provider.get('api_key')
                volc_url = volc_provider.get('base_url')
                
                # 优先使用配置中的 websearch_model
                volc_model = CONFIG.get('websearch_model')
                
                # 如果没配 websearch_model，则找第一个火山模型
                if not volc_model:
                    for m_id, m_info in CONFIG.get('models', {}).items():
                        if m_info.get('provider') == 'volcengine':
                            volc_model = m_id
                            break
                
                if not volc_key or not volc_model:
                    return f"错误：未配置火山引擎(Ark)模型或API Key，无法执行联网搜索。"
                
                print(f"[SEARCH] 使用搜索中转模型: {volc_model}")
                
                from volcenginesdkarkruntime import Ark
                search_client = Ark(api_key=volc_key, base_url=volc_url)
                
                # 调用带搜索插件的模型
                # 对于火山引擎，开启联网搜索的最佳实践是使用 extra_headers
                # 并且不一定要传入 tools (除非是必须通过 tools 触发生命周期的模型)
                response = search_client.chat.completions.create(
                    model=volc_model,
                    messages=[
                        {"role": "system", "content": self._get_default_web_search_prompt()},
                        {"role": "user", "content": query}
                    ],
                    # 提示模型立即使用搜索
                    extra_headers={"x-ark-enable-web-search": "true"}, 
                    stream=False
                )
                
                # 获取结果，同时兼容思维链和正文
                search_result = ""
                message = response.choices[0].message
                
                # 优先获取 content
                if hasattr(message, 'content') and message.content:
                    search_result = message.content
                
                # 如果正文为空，尝试获取 reasoning_content (针对推理模型如 R1)
                elif hasattr(message, 'reasoning_content') and message.reasoning_content:
                    search_result = f"[思考过程]\n{message.reasoning_content}"
                
                # 如果还是为空，由于开启了 web_search，可能结果在 tool_calls 的输出里（虽然 stream=False 通常不该这样）
                if not search_result:
                    search_result = "联网搜索成功，但模型未返回具体文本结果。可能该关键词没有找到对应的信息，或模型策略拦截了输出。"
                
                return f"联网搜索结果 for '{query}':\n\n{search_result}"
                
            except Exception as e:
                print(f"[ERROR] 联网搜索失败: {e}")
                return f"联网搜索执行失败: {str(e)}"
        
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
        file_ids: List[str] = None,
        is_regenerate: bool = False,
        regenerate_index: int = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        发送消息（支持多轮对话、流式输出、文件和Context Caching）
        """
        if self.model_name == "NO_AVAILABLE_MODEL":
            yield {
                "type": "error",
                "content": "当前账号无可用模型权限，请联系管理员分配。"
            }
            return

        try:
            # 确保对话已创建
            if not self.conversation_id:
                self.conversation_id = self.conversation_manager.create_conversation()
            
            # 发送模型信息（前端显示模型小字提示）
            yield {
                "type": "model_info", 
                "model_name": self.model_name, 
                "provider": self.provider
            }

            # 如果是重新生成，先处理版本保存
            if is_regenerate and regenerate_index is not None:
                # 注意：此时 msg 是触发重新生成的那个 user 消息
                # 我们需要在添加新消息前，先把要覆盖的那个 assistant 消息存为版本
                # 逻辑在 server.py 处理更合适，这里只负责清除 cache 强制重算
                pass

            # 暂存 file_ids 到 metadata
            metadata = {}
            if file_ids:
                metadata["file_ids"] = file_ids
            
            # 重新生成逻辑：不添加新消息，而是使用历史消息
            if not is_regenerate:
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
            
            # 如果是重新生成，必须清除 last_response_id，因为上下文已经改变（分支了）
            if is_regenerate:
                print(f"[REGENERATE] Cleared Context Cache for branching.")
                last_response_id = None

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
                        current_function_outputs=current_function_outputs
                    )
                    
                    # 关键：清除已消耗的函数输出，防止在下一轮中重复发送
                    current_function_outputs = []
                    
                    # 调用API
                    print(f"[DEBUG_API] 发送请求 (Provider: {self.provider})")
                    
                    response_iterator = None
                    try:
                        if self.provider == 'volcengine':
                            response_iterator = self.client.responses.create(**request_params)
                        else:
                            # Stepfun / OpenAI 兼容接口
                            response_iterator = self.client.chat.completions.create(**request_params)
                    except Exception as e:
                         # 统一错误处理，稍后会由 retry 逻辑捕捉或重抛
                         pass

                    # -------------------------------------------------------------
                    # Robust Retry Logic (主用于火山引擎 Context Mismatch)
                    # -------------------------------------------------------------
                    def safe_iter(iterator):
                        try:
                            for item in iterator:
                                yield item
                        except Exception as e:
                            raise e 
                    
                    is_retry_mode = False
                    try:
                         if response_iterator is None:
                             if self.provider == 'volcengine':
                                 response_iterator = self.client.responses.create(**request_params)
                             else:
                                 response_iterator = self.client.chat.completions.create(**request_params)
                         chunks = safe_iter(response_iterator)
                    except Exception as e:
                        error_str = str(e)
                        if self.provider == 'volcengine' and "previous_response_id" in error_str and "400" in error_str:
                             print(f"[ERROR] 捕获 Context Mismatch (400). Retrying with FULL context...")
                             # 关键修复：当 resumption 失败时，必须将 input 恢复为完整的 messages 历史，否则模型会丢失上下文
                             request_params["input"] = messages
                             if "previous_response_id" in request_params:
                                 del request_params["previous_response_id"]
                             previous_response_id = None
                             response_iterator = self.client.responses.create(**request_params)
                             chunks = safe_iter(response_iterator)
                             is_retry_mode = True
                        else:
                             raise e

                    # Process Stream
                    print(f"[DEBUG_API] 请求返回，开始处理流... (Round: {round_num + 1}, Retry: {is_retry_mode})")
                    
                    # 处理响应流（直接在这里处理以支持实时yield）
                    round_content = ""
                    function_calls = []
                    has_web_search = False
                    
                    # [FIX] 内部去重标志：防止某些模型同时输出 reasoning_text 和 reasoning_summary_text 导致前端重复
                    has_received_detail_reasoning = False
                    
                    # [FIX] 记录本轮最后一次出现的 usage，避免在流中多次记录导致日志爆炸
                    round_usage = None

                    try:
                        for chunk in chunks:
                            # [CHUNK_DEBUG] 每一个 chunk 的详细信息
                            if CONFIG.get('log_status', 'silent') == 'all':
                                if self.provider == 'volcengine':
                                    c_type = getattr(chunk, 'type', 'unknown')
                                    # 提取内容摘要
                                    c_content = ""
                                    if hasattr(chunk, 'delta'): 
                                        c_content = str(chunk.delta)  # 强制转换为字符串，防止 ResponseOutputText 对象
                                    elif hasattr(chunk, 'item') and chunk.item:
                                        if hasattr(chunk.item, 'content'): 
                                            c_content = str(chunk.item.content)  # 强制转换为字符串
                                        elif hasattr(chunk.item, 'type'): 
                                            c_content = f"Item({chunk.item.type})"
                                    
                                    # 统一输出格式 (Type/Content) - 直接使用字符串，不需要 json.dumps
                                    print(f"[CHUNK_DEBUG] type={c_type} content={c_content}")
                                else:
                                    # OpenAI / Stepfun 结构
                                    c_type = "openai_chunk"
                                    delta = chunk.choices[0].delta if chunk.choices else None
                                    c_content = ""
                                    if delta:
                                        if hasattr(delta, 'content') and delta.content: 
                                            c_content = str(delta.content)  # 强制转换为字符串
                                        elif hasattr(delta, 'reasoning_content') and delta.reasoning_content: 
                                            c_content = "[Reasoning] " + str(delta.reasoning_content)  # 强制转换为字符串
                                        elif hasattr(delta, 'tool_calls'): 
                                            c_content = "[ToolCalls]"
                                    
                                    # 额外检查 usage
                                    usage_str = ""
                                    if hasattr(chunk, 'usage') and chunk.usage:
                                        usage_str = f" | Usage: {chunk.usage}"
                                    
                                    print(f"[CHUNK_DEBUG] type={c_type} content={c_content}{usage_str}")

                            # --- 处理：火山引擎 (Ark Responses API 专用结构) ---
                            if self.provider == 'volcengine':
                                chunk_type = getattr(chunk, 'type', None)
                                chunk_type_str = str(chunk_type)
                                
                                # 获取 response_id
                                if hasattr(chunk, 'response'):
                                    response_obj = getattr(chunk, 'response')
                                    if hasattr(response_obj, 'id') and response_obj.id:
                                        # 更新 persistent ID 供下轮使用
                                        previous_response_id = response_obj.id
                                
                                # 文本增量 - 兼容多种可能的 chunk 类型
                                if chunk_type in ['response.output_text.delta', 'response.message.delta']:
                                    delta = getattr(chunk, 'delta', '')
                                    if delta:
                                        # 关键修复：强制转换为字符串，防止 ResponseOutputText 对象导致 JSON 序列化失败
                                        delta_str = str(delta) if not isinstance(delta, str) else delta
                                        round_content += delta_str
                                        accumulated_content += delta_str
                                        yield {"type": "content", "content": delta_str}
                            
                                # 思考过程增量 (核心修复: 重新兼容 summary 类型，并防止 detail 和 summary 同时出现时的视觉重复)
                                elif 'reasoning' in chunk_type_str and 'delta' in chunk_type_str:
                                    # 优先判断是否是详情型推理
                                    is_detail = 'reasoning_text.delta' in chunk_type_str or 'reasoning.delta' == chunk_type_str
                                    is_summary = 'reasoning_summary_text.delta' in chunk_type_str
                                    
                                    if is_detail:
                                        has_received_detail_reasoning = True
                                        
                                    # 如果已经收到过详情(Detail)，则忽略后续可能的摘要(Summary)，防止重复显示
                                    if is_summary and has_received_detail_reasoning:
                                        continue
                                        
                                    delta = getattr(chunk, 'delta', '')
                                    if delta:
                                        # 关键修复：确保思维链内容也是字符串
                                        delta_str = str(delta) if not isinstance(delta, str) else delta
                                        accumulated_reasoning += delta_str
                                        yield {"type": "reasoning_content", "content": delta_str}

                                # 核心修复: 过滤干扰并按序提取
                                elif chunk_type == 'response.output_item.done':
                                    item = getattr(chunk, 'item', None)
                                    if item:
                                        item_type = getattr(item, 'type', '')
                                        # 1. 提取 Search Keyword
                                        if 'web_search' in item_type:
                                            action = getattr(item, 'action', None)
                                            if action and hasattr(action, 'query'):
                                                query = str(action.query)  # 确保转换为字符串
                                                step = {"type": "web_search", "content": f"正在搜索: {query}", "status": "正在搜索", "query": query}
                                                yield step
                                                process_steps.append(step)
                                        
                                        # 2. 只有在没有产生任何 delta 文本的情况下才使用 done 的文本，防止重复
                                        elif item_type == 'text' and not round_content:
                                            # 关键修复：确保 content 被转换为字符串，防止 ResponseOutputText 对象导致 JSON 序列化失败
                                            text_content = getattr(item, 'content', '')
                                            if text_content:
                                                # 如果是对象类型，**立即**转换为字符串，在任何其他操作之前
                                                text_content = str(text_content) if not isinstance(text_content, str) else text_content
                                                # 现在 text_content 肯定是字符串了，可以安全地累积和 yield
                                                round_content += text_content
                                                accumulated_content += text_content
                                                yield {"type": "content", "content": text_content}
                                
                                # Web搜索实时状态
                                elif 'web_search_call.searching' in str(chunk_type) or 'web_search_call.completed' in str(chunk_type):
                                    has_web_search = True
                                    status = '正在搜索' if 'searching' in str(chunk_type) else '搜索完成'
                                    query_text = ""
                                    ws_obj = getattr(chunk, 'web_search_call', None) or getattr(chunk, 'web_search', None)
                                    if ws_obj:
                                        query_raw = getattr(ws_obj, 'query', "")
                                        query_text = str(query_raw) if query_raw else ""  # 确保转换为字符串
                                    step = {"type": "web_search", "content": f"{status}: {query_text}" if query_text else status, "status": status, "query": query_text}
                                    yield step
                                    process_steps.append(step)

                                # Token统计
                                elif chunk_type == 'response.completed':
                                    response_obj = getattr(chunk, 'response', None)
                                    if response_obj and hasattr(response_obj, 'output'):
                                        output = response_obj.output
                                        for item in output:
                                            if getattr(item, 'type', None) == 'function_call':
                                                # 确保所有值都是可序列化的基本类型
                                                func_call = {
                                                    "name": str(getattr(item, 'name', '')) if getattr(item, 'name', None) else None,
                                                    "arguments": str(getattr(item, 'arguments', '{}')),
                                                    "call_id": str(getattr(item, 'call_id', '')) if getattr(item, 'call_id', None) else None
                                                }
                                                function_calls.append(func_call)
                                    
                                    # Token统计 (暂存，等循环结束一并记录)
                                    if hasattr(response_obj, 'usage'):
                                        round_usage = response_obj.usage
                                        yield {"type": "token_usage", "input_tokens": round_usage.input_tokens, "output_tokens": round_usage.output_tokens, "total_tokens": round_usage.total_tokens}
                                
                                else:
                                    # 未知类型记录 (仅调试)
                                    # print(f"[DEBUG_CHUNK] Unknown Volc chunk type: {chunk_type}")
                                    pass
                            
                            # --- 处理：标准 OpenAI / Stepfun 结构 ---
                            else:
                                if not chunk.choices:
                                    continue
                                
                                delta = chunk.choices[0].delta
                                
                                # 文本内容
                                if hasattr(delta, 'content') and delta.content:
                                    # 关键修复：确保 OpenAI/Stepfun 的 delta.content 也是字符串
                                    content_str = str(delta.content) if not isinstance(delta.content, str) else delta.content
                                    round_content += content_str
                                    accumulated_content += content_str
                                    yield {"type": "content", "content": content_str}
                                
                                # 思维链 (Stepfun/Kimi/DeepSeek 兼容字段)
                                if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                                    # 关键修复：确保推理内容是字符串
                                    reasoning_str = str(delta.reasoning_content) if not isinstance(delta.reasoning_content, str) else delta.reasoning_content
                                    accumulated_reasoning += reasoning_str
                                    yield {"type": "reasoning_content", "content": reasoning_str}
                                
                                # 函数调用 (OpenAI 标准流式格式)
                                if hasattr(delta, 'tool_calls') and delta.tool_calls:
                                    for tc in delta.tool_calls:
                                        if tc.index >= len(function_calls):
                                            # 关键修复：确保 call_id 是字符串
                                            call_id_str = str(tc.id) if tc.id else ""
                                            function_calls.append({"name": "", "arguments": "", "call_id": call_id_str})
                                        
                                        f_info = function_calls[tc.index]
                                        if tc.id: f_info["call_id"] = str(tc.id)
                                        if tc.function:
                                            if tc.function.name: f_info["name"] += str(tc.function.name)
                                            if tc.function.arguments: f_info["arguments"] += str(tc.function.arguments)

                                # Token统计 (部分 OpenAI Provider 在最后一个 chunk 的 usage 字段)
                                if hasattr(chunk, 'usage') and chunk.usage:
                                    round_usage = chunk.usage
                                    yield {
                                        "type": "token_usage", 
                                        "input_tokens": getattr(round_usage, 'prompt_tokens', 0), 
                                        "output_tokens": getattr(round_usage, 'completion_tokens', 0), 
                                        "total_tokens": getattr(round_usage, 'total_tokens', 0)
                                    }
                    
                    except Exception as e:
                        print(f"[ERROR] Stream processing error: {e}")
                        print(f"[ERROR] Error type: {type(e).__name__}")
                        # 额外调试：尝试找出哪个变量包含不可序列化的对象
                        import traceback
                        traceback.print_exc()
                        # 如果是上下文错误，在这里其实很难直接retry，因为已经yield了部分内容
                        # 但至少我们捕获它，防止整个Server崩掉
                        if "previous response" in str(e):
                             print("[CRITICAL] Context consistency error detected.")
                        raise e

                    # [FIX] 在 chunk 循环结束后，统一记录本轮的 Token 消耗
                    if round_usage:
                        self._log_token_usage_safe(round_usage, has_web_search, function_calls, process_steps, msg)
                    else:
                        # 某些 Provider 不返回 usage，使用估算值，避免 token 全为 0
                        fallback_title = (str(msg).strip()[:30] + "...") if msg and len(str(msg).strip()) > 30 else (str(msg).strip() if msg else "新对话")
                        try:
                            prompt_snapshot = json.dumps(messages, ensure_ascii=False, default=str)
                        except Exception:
                            prompt_snapshot = str(messages)
                        est_input = self._estimate_token_count(prompt_snapshot)
                        est_output = self._estimate_token_count(round_content or accumulated_content)
                        est_total = est_input + est_output
                        self.user.log_token_usage(
                            self.conversation_id or "unknown",
                            fallback_title or "新对话",
                            "tool:web_search" if has_web_search else ("tool:" + function_calls[0].get('name', 'unknown') if function_calls else "chat"),
                            est_input,
                            est_output,
                            total_tokens=est_total,
                            metadata={
                                "provider": self.provider,
                                "model": self.model_name,
                                "token_details": {
                                    "estimated": True,
                                    "estimate_method": "cjk1.6+ascii/4",
                                    "prompt_chars": len(prompt_snapshot),
                                    "output_chars": len(round_content or accumulated_content or "")
                                },
                                "has_web_search": has_web_search,
                                "tool_call_count": len(function_calls or [])
                            }
                        )

                    # 检查 previous_response_id 获取情况 (仅针对火山引擎)
                    if self.provider == 'volcengine':
                        if previous_response_id:
                            print(f"[DEBUG] 已捕获 Response ID: {previous_response_id}")
                        else:
                            print(f"[WARNING] 本轮未能捕获 Response ID，下轮将回退到全量上下文传输 (Token开销增加)")

                    # 本轮文本内容作为步骤加入
                    if round_content:
                        process_steps.append({"type": "content", "content": round_content})
                    
                    # 处理函数调用
                    if function_calls:
                        # -------------------------------------------------------------
                        # [FIX] 核心修复: 构建 Assistant Message (Tool Calls) 并加入历史
                        # 确保多轮对话上下文完整 (User -> Assistant[Call] -> Tool[Output])
                        # 对于 OpenAI/GitHub 等模型，content 必须为 None 或省略，如果只有 tool_calls
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
                        
                        # 构建助手的工具调用消息
                        assistant_tool_msg = {
                            "role": "assistant",
                            "tool_calls": tool_calls_payload
                        }
                        # 对于标准 OpenAI 格式，如果 content 为空字符串，建议设为 None 或完全不传
                        if round_content:
                            assistant_tool_msg["content"] = round_content
                        else:
                            assistant_tool_msg["content"] = None
                            
                        messages.append(assistant_tool_msg)
                        
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
                            if self.provider == 'volcengine':
                                current_function_outputs.append({
                                    "type": "function_call_output",
                                    "call_id": call_id,
                                    "output": result
                                })
                            else:
                                # OpenAI 标准格式需要 role: tool
                                current_function_outputs.append({
                                    "role": "tool",
                                    "tool_call_id": call_id,
                                    "content": result
                                })
                        
                        # [FIX] 在工具调用结束后，添加一个隐形的引导提示，防止模型复读或卡住
                        # 仅针对火山引擎 (Ark Responses API)，帮助其更好地从工具结果切换回文本回复
                        if self.provider == 'volcengine':
                            # 提取本次调用的工具名称
                            tool_names = list(set([fc["name"] for fc in function_calls]))
                            # 使用 system 角色提供指令引导，使用中文以符合主要交互语言
                            current_function_outputs.append({
                                "role": "system",
                                "content": f"[系统指令] 你（AI助手）已完成工具调用: {', '.join(tool_names)}。请根据返回的工具结果，继续完成对用户的回答或做出最终总结。"
                            })
                        
                        # 继续下一轮（保持messages累积，但current_function_outputs已重置）
                        messages = self._append_function_outputs(messages, current_function_outputs)
                        
                        # [DEBUG] 打印更新后的历史状态
                        print(f"[DEBUG_HIST] 更新历史后消息数: {len(messages)}")
                        if len(messages) >= 2:
                            print(f"[DEBUG_HIST] 倒数第二条: {messages[-2].get('role')} (Tools: {len(messages[-2].get('tool_calls', []))})")
                            print(f"[DEBUG_HIST] 最后一条: {messages[-1].get('role')} (Type: {messages[-1].get('type', 'text')})")

                        # 继续循环下一轮
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
                    metadata = {
                        "process_steps": process_steps,
                        "model_name": self.model_name
                    }
                    
                    # 自动生成对话标题（根据配置决定是否每轮都总结）
                    if accumulated_content:
                        try:
                            # 仅在第一轮或开启 continuous_summary 时生成标题
                            should_generate = True
                            if not CONFIG.get("continuous_summary", False):
                                is_first_round = self.conversation_manager.get_message_count(self.conversation_id) <= 2 # user + assistant=2
                                should_generate = is_first_round
                            
                            if should_generate:
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
                        metadata=metadata,
                        index=regenerate_index if is_regenerate else None
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
        """安全记录Token日志（不影响主流程）"""
        try:
            def _safe_int(v, default=0):
                try:
                    if v is None:
                        return default
                    if isinstance(v, bool):
                        return int(v)
                    if isinstance(v, (int, float)):
                        return int(v)
                    s = str(v).strip()
                    if not s:
                        return default
                    if s.isdigit() or (s.startswith('-') and s[1:].isdigit()):
                        return int(s)
                    return int(float(s))
                except Exception:
                    return default

            def _uv(obj, key, default=0):
                if isinstance(obj, dict):
                    return obj.get(key, default)
                return getattr(obj, key, default)

            action_type = "chat"
            if has_web_search:
                action_type = "tool:web_search"
            elif function_calls:
                action_type = f"tool:{function_calls[0].get('name', 'unknown')}"
            elif len(process_steps) > 0:
                for step in process_steps:
                    if step.get('type') == 'function_call':
                        action_type = f"tool:{step.get('name')}"
                        break
                    elif step.get('type') == 'web_search':
                        action_type = "tool:web_search"
                        break

            action_type = action_type.lower()

            if user_message:
                clean_msg = str(user_message).strip()
                conv_title = clean_msg[:30] + "..." if len(clean_msg) > 30 else clean_msg
            else:
                conv_title = "新对话"
                if self.conversation_id:
                    try:
                        conv_data = self.conversation_manager.get_conversation(self.conversation_id)
                        conv_title = conv_data.get("title", conv_title)
                    except:
                        pass

            input_tokens = _uv(usage, 'input_tokens', _uv(usage, 'prompt_tokens', 0))
            output_tokens = _uv(usage, 'output_tokens', _uv(usage, 'completion_tokens', 0))
            usage_total = _uv(usage, 'total_tokens', 0)
            usage_total_int = _safe_int(usage_total, 0)
            input_tokens_int = _safe_int(input_tokens, 0)
            output_tokens_int = _safe_int(output_tokens, 0)
            if usage_total_int > 0:
                total_tokens = usage_total_int
            else:
                total_tokens = input_tokens_int + output_tokens_int

            prompt_details = _uv(usage, 'prompt_tokens_details', {}) or {}
            completion_details = _uv(usage, 'completion_tokens_details', {}) or {}
            token_details = {
                "cached_tokens": _safe_int(_uv(prompt_details, 'cached_tokens', 0), 0),
                "reasoning_tokens": _safe_int(_uv(completion_details, 'reasoning_tokens', 0), 0),
                "audio_input_tokens": _safe_int(_uv(prompt_details, 'audio_tokens', 0), 0),
                "audio_output_tokens": _safe_int(_uv(completion_details, 'audio_tokens', 0), 0)
            }

            log_status = CONFIG.get('log_status', 'silent')
            if log_status == 'all':
                print(f"[TOKEN_DEBUG] ==================== Token Usage Info ====================")
                print(f"[TOKEN_DEBUG] Model: {self.model_name} | Provider: {self.provider}")
                print(f"[TOKEN_DEBUG] Action: {action_type} | Input: {input_tokens_int} | Output: {output_tokens_int}")
                print(f"[TOKEN_DEBUG] Total: {total_tokens}")
                print(f"[TOKEN_DEBUG] ==========================================================")

            self.user.log_token_usage(
                self.conversation_id or "unknown",
                conv_title,
                action_type,
                input_tokens_int,
                output_tokens_int,
                total_tokens=total_tokens,
                metadata={
                    "provider": self.provider,
                    "model": self.model_name,
                    "token_details": token_details,
                    "has_web_search": has_web_search,
                    "tool_call_count": len(function_calls or [])
                }
            )
        except Exception as e:
            print(f"[WARNING] 记录 Token 日志失败: {e}")

    def _build_initial_messages(self, user_msg: str) -> List[Dict]:
        """构建初始消息列表 (优化 Prefix Caching)"""
        # 合并 System Prompt 和 历史摘要到第一条消息，以最大化 Prompt Caching 命中率
        full_system_content = self.system_prompt
        
        # 添加最近交流概览（上下文）
        if self.conversation_id:
            recent_summaries = self.conversation_manager.get_recent_exchange_summaries(
                self.conversation_id, limit=3
            )
            if recent_summaries:
                context_summary = "\n\n## 历史上下文概览 (Stable Context)\n"
                for i, exchange in enumerate(recent_summaries, 1):
                    user_text = exchange['user'][:40] + "..." if len(exchange['user']) > 40 else exchange['user']
                    context_summary += f"{i}. 用户: {user_text} | AI总结: {exchange.get('summary', '无')}\n"
                full_system_content += context_summary

        messages = [
            {"role": "system", "content": full_system_content}
        ]
        
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
            # [FIX] 增加安全性：检查 role 字段是否存在
            # 针对火山引擎 (Ark)，某些消息可能是 OutputItem (如 function_call_output)，没有 role
            if "role" not in msg:
                cleaned.append(dict(msg)) # 直接保留副本
                continue
                
            cleaned_msg = {"role": msg["role"], "content": msg.get("content", "")}
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
            provider_name = model_info.get('provider', 'volcengine')
            provider_info = CONFIG.get('providers', {}).get(provider_name, {})
            
            api_key = provider_info.get('api_key', "")
            base_url = provider_info.get('base_url')
            
            # 使用统一的缓存逻辑
            global _CLIENT_CACHE
            cache_key = f"{provider_name}_{api_key}"
            
            if cache_key in _CLIENT_CACHE:
                client = _CLIENT_CACHE[cache_key]
            else:
                if provider_name == 'volcengine':
                    client = Ark(api_key=api_key, base_url=base_url, timeout=30.0)
                else:
                    client = OpenAI(api_key=api_key, base_url=base_url, timeout=30.0)
                _CLIENT_CACHE[cache_key] = client
            
            # 构建prompt
            prompt = f"""根据以下对话内容，生成一个简洁准确的标题（10-20字）。

用户问题：{user_message[:100]}
助手回答：{assistant_response[:100]}

要求：
1. 准确概括对话核心内容
2. 简洁明了，10-20字
3. 只输出标题，不要其他内容
4. 避免使用"用户询问"、"提供信息"等冗余词汇

标题："""
            
            # 调用API
            if provider_name == 'volcengine':
                response = client.chat.completions.create(
                    model=conclusion_model,
                    messages=[{"role": "user", "content": prompt}],
                    stream=False
                )
            else:
                response = client.chat.completions.create(
                    model=conclusion_model,
                    messages=[{"role": "user", "content": prompt}],
                    stream=False
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
        """构建API请求参数 - 兼容不同供应商"""
        
        # 基础参数
        params = {
            "model": self.model_name,
            "stream": True
        }

        # 对于 OpenAI 兼容接口，开启 stream_options 以获取 Token 统计
        if self.provider != 'volcengine':
            params["stream_options"] = {"include_usage": True}

        # --- 火山引擎 (Ark Responses API) 专用逻辑 ---
        if self.provider == 'volcengine':
            # params["max_output_tokens"] = 65536
            
            if enable_thinking:
                params["thinking"] = {"type": "enabled"}
            else:
                 params["thinking"] = {"type": "disabled"}
            
            if enable_tools:
                params["tools"] = self.tools
            
            if previous_response_id is None:
                params["input"] = messages
            else:
                params["previous_response_id"] = previous_response_id
                if current_function_outputs:
                    params["input"] = current_function_outputs
                elif messages:
                    params["input"] = messages
                else:
                    params["input"] = [{"role": "user", "content": ""}]
                    
        # --- 通用 OpenAI / Stepfun 逻辑 ---
        else:
            # Stepfun / OpenAI 标准参数
            # [FIX] 对于 OpenAI o1/o3 或 GPT-5 等新模型，'max_tokens' 被替换为 'max_completion_tokens'
            is_new_reasoning_model = any(x in self.model_name.lower() for x in ["o1", "o3", "gpt-5", "gpt5", "reasoning"])
            
            # if is_new_reasoning_model:
            #     params["max_completion_tokens"] = 8192
            # else:
            #     params["max_tokens"] = 8192  # 标准模型通常限制在 4k 或 8k，除非特定长文本模型
            
            if enable_tools:
                # [FIX] GitHub Inference 的 Phi-4-reasoning 和 DeepSeek-R1 等模型不支持工具调用
                # 即使提供了 tools，后端也会报错: "auto" tool choice requires --enable-auto-tool-choice
                # 因此我们需要彻底剥离这些模型在特定 Provider 下的工具参数
                is_reasoning_only = any(x in self.model_name.lower() for x in ["-reasoning", "deepseek-r1", "qwq-32b"])
                
                # 如果是这类模型，我们强制不开启 tools
                if is_reasoning_only and self.provider in ["github", "suanli"]:
                     print(f"[DEBUG] [Phi-4-FIX] 模型 {self.model_name} 在 {self.provider} 下检测到 Reasoning，屏蔽 tools 以避免 400 错误。")
                else:
                    params["tools"] = self.tools
                    # [FIX] 针对 GitHub 上的普通 Phi-4 模型，不要传 tool_choice，否则可能 400
                    if "phi-4" in self.model_name.lower() and self.provider == "github":
                        pass
                    else:
                        # 只有非 Phi-4/Reasoning 模型才显式设置或允许 auto 行为（由 API 默认控制）
                        pass
            
            # 标准 OpenAI 格式使用 messages 数组
            # 注意：对于非火山引擎模型，messages 列表已经由 sendMessage 循环维护好了正确的 role
            # 剔除可能存在的 reasoning_content 或其他非标准字段，确保兼容性
            params["messages"] = self._strip_reasoning_content(list(messages))

            # --- 阿里云 / DashScope 专用逻辑 ---
            if self.provider == "aliyun" and enable_thinking:
                # 查阅阿里云文档可知，需要通过 extra_body 传参控制
                params["extra_body"] = {
                    "enable_thinking": True
                }
                # Qwen-Max-Latest 和部分模型支持 thinking_config
                # 但通用开启只需 enable_thinking
                print(f"[DEBUG] [Aliyun-Thinking] 已为 {self.model_name} 开启思维链模式 (extra_body)")

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


