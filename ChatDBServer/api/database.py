import os
import json
import time
# 知识库

SHORT_TIME = 0
BASIS = 1


class User:
    def __init__(self, username):
        self.path = f"./data/users/{username}/"
        self.user = username
        self._ensure_knowledge_graph()

    def _ensure_knowledge_graph(self):
        """确保知识图谱文件存在"""
        graph_file = self.path + "knowledge_graph.json"
        if not os.path.exists(graph_file):
            initial_graph = {
                "categories": {
                    "未分类": {
                        "name": "未分类",
                        "color": "#9ca3af",
                        "knowledge_ids": [],
                        "position": {"x": 0, "y": 0}
                    }
                },
                "connections": [],
                "category_order": ["未分类"]
            }
            with open(graph_file, "w", encoding="utf-8") as f:
                json.dump(initial_graph, f, indent=4, ensure_ascii=False)

    def getPassword(self):
        with open("./data/user.json", "r", encoding="utf-8") as f:
            users = json.load(f)
        return users[self.user]["password"]
    
    def getKnowledgeList(self, _type=SHORT_TIME):
        with open(self.path + "database.json", "r", encoding="utf-8") as f:
            db = json.load(f)
        if _type == SHORT_TIME:
            return db["data_short"]
        elif _type == BASIS:
            return db["data_basis"]
        else:
            return {}
        
    def addShort(self, title):
        with open(self.path + "database.json", "r", encoding="utf-8") as f:
            db = json.load(f)
        
        # 找到已存在的最大ID
        max_id = -1
        for k in db["data_short"].keys():
            try:
                curr_id = int(k)
                if curr_id > max_id:
                    max_id = curr_id
            except ValueError:
                pass
        
        ID = max_id + 1
        
        db["data_short"][str(ID)] = title
        with open(self.path + "database.json", "w", encoding="utf-8") as f:
            json.dump(db, f, indent=4, ensure_ascii=False)
        return True
    
    def addBasis(self, title, context, url):
        with open(self.path + "database.json", "r", encoding="utf-8") as f:
            db = json.load(f)

        # 找到已存在的最大ID（根据文件名 xxx.txt）
        max_id = 0
        if db["data_basis"]:
            for item in db["data_basis"].values():
                src = item["src"]
                try:
                    basename = os.path.basename(src)
                    if basename.endswith('.txt'):
                        curr_id = int(basename[:-4])
                        if curr_id > max_id:
                            max_id = curr_id
                except (ValueError, IndexError):
                    pass

        ID = max_id + 1
        db["data_basis"][title] = {
            "src": f"./data/users/{self.user}/database/{ID}.txt",
            "url": url
        }
        with open(f"./data/users/{self.user}/database/{ID}.txt", "w", encoding="utf-8") as f:
            f.write(context)

        with open(self.path + "database.json", "w", encoding="utf-8") as f:
            json.dump(db, f, indent=4, ensure_ascii=False)
        
        # 自动扫描连接
        self.auto_link_knowledge(title)
        return True

    def auto_link_knowledge(self, title):
        """
        自动扫描指定知识点内容，建立与其他知识点的连接
        1. 提及链接：内容中出现了其他知识点的标题
        2. 脉络链接：内容中包含特定逻辑词汇（如"导致"、"下一步"等）
        """
        content = self.getBasisContent(title)
        db = self.getKnowledgeList(1)
        graph = self.get_knowledge_graph()
        
        all_titles = list(db.keys())
        changed = False
        
        # 1. 扫描标题匹配 (提及)
        for other_title in all_titles:
            if other_title == title: continue
            
            # 只有当内容中包含其他标题且目前尚未建立连接时
            if other_title in content:
                # 检查是否已存在
                exists = False
                for conn in graph["connections"]:
                    if (conn["from"] == title and conn["to"] == other_title) or \
                       (conn["from"] == other_title and conn["to"] == title):
                        exists = True
                        break
                
                if not exists:
                    conn_id = f"{title}-{other_title}-auto"
                    graph["connections"].append({
                        "id": conn_id,
                        "from": title,
                        "to": other_title,
                        "type": "提及",
                        "description": "内容中自动检测到关键词",
                        "created_at": time.time(),
                        "auto": True
                    })
                    changed = True
        
        # 2. 扫描逻辑词 (脉络/演化)
        # 简单的启发式：如果 B 在 A 的内容中被提及，且伴随逻辑词，标记为"脉络"
        logic_words = ["导致", "演化", "下一步", "随后", "生成", "演进", "属于", "依赖"]
        for conn in graph["connections"]:
            if conn.get("auto") and conn["from"] == title:
                target = conn["to"]
                # 查找 target 周围是否有逻辑词
                idx = content.find(target)
                if idx != -1:
                    context = content[max(0, idx-20):min(len(content), idx+len(target)+20)]
                    for word in logic_words:
                        if word in context:
                            conn["type"] = "脉络"
                            conn["description"] = f"检测到逻辑词: {word}"
                            changed = True
                            break

        if changed:
            self.save_knowledge_graph(graph)
        return changed

    def removeShort(self, ID):
        with open(self.path + "database.json", "r", encoding="utf-8") as f:
            db = json.load(f)

        del db["data_short"][str(ID)]

        with open(self.path + "database.json", "w", encoding="utf-8") as f:
            json.dump(db, f, indent=4, ensure_ascii=False)
        return True
    
    def removeBasis(self, title):
        with open(self.path + "database.json", "r", encoding="utf-8") as f:
            db = json.load(f)

        if title not in db["data_basis"]:
            return False, "Title not found"

        os.remove(db["data_basis"][title]["src"])
        del db["data_basis"][title]

        with open(self.path + "database.json", "w", encoding="utf-8") as f:
            json.dump(db, f, indent=4, ensure_ascii=False)
            
        # 清理知识图谱中的该节点及其连接
        graph = self.get_knowledge_graph()
        # 从分类中移除
        for cat in graph["categories"].values():
            if title in cat["knowledge_ids"]:
                cat["knowledge_ids"].remove(title)
        # 移除连接
        graph["connections"] = [c for c in graph["connections"] if c["from"] != title and c["to"] != title]
        # 移除节点坐标
        if "knowledge_nodes" in graph and title in graph["knowledge_nodes"]:
            del graph["knowledge_nodes"][title]
            
        self.save_knowledge_graph(graph)
        return True, "删除成功"
    
    def getBasisContent(self, title):
        with open(self.path + "database.json", "r", encoding="utf-8") as f:
            db = json.load(f)
        
        src = db["data_basis"][title]["src"]
        with open(src, "r", encoding="utf-8") as f:
            content = f.read()
        return content

    def updateBasisContent(self, title, content):
        with open(self.path + "database.json", "r", encoding="utf-8") as f:
            db = json.load(f)
        
        if title not in db["data_basis"]:
            return False, "Title not found"
            
        src = db["data_basis"][title]["src"]
        try:
            with open(src, "w", encoding="utf-8") as f:
                f.write(content)
            # 更新内容后重新扫描链接
            self.auto_link_knowledge(title)
            return True, "Success"
        except Exception as e:
            return False, str(e)
    
    def updateBasis(self, title, new_title=None, context=None, url=None):
        """更新基础知识，支持修改标题、内容和URL"""
        with open(self.path + "database.json", "r", encoding="utf-8") as f:
            db = json.load(f)
        
        if title not in db["data_basis"]:
            return False, "Title not found"
        
        # 获取旧的记录
        old_record = db["data_basis"][title]
        src = old_record["src"]
        
        # 更新内容（如果提供）
        if context is not None:
            try:
                with open(src, "w", encoding="utf-8") as f:
                    f.write(context)
            except Exception as e:
                return False, f"Failed to update content: {str(e)}"
        
        # 更新URL（如果提供）
        if url is not None:
            old_record["url"] = url
        
        # 更新标题（如果提供且不同）
        if new_title and new_title != title:
            # 检查新标题是否已存在
            if new_title in db["data_basis"]:
                return False, "New title already exists"
            
            # 移除旧标题，添加新标题
            db["data_basis"][new_title] = old_record
            del db["data_basis"][title]
            
            # 更新知识图谱中的引用
            self._update_knowledge_graph_title(title, new_title)
        
        # 保存更新
        with open(self.path + "database.json", "w", encoding="utf-8") as f:
            json.dump(db, f, indent=4, ensure_ascii=False)
        
        return True, "Success"
    
    def _update_knowledge_graph_title(self, old_title, new_title):
        """更新知识图谱中的知识标题引用"""
        graph_file = self.path + "knowledge_graph.json"
        
        try:
            with open(graph_file, "r", encoding="utf-8") as f:
                graph = json.load(f)
            
            # 更新categories中的knowledge_ids
            for category in graph.get("categories", {}).values():
                if old_title in category.get("knowledge_ids", []):
                    idx = category["knowledge_ids"].index(old_title)
                    category["knowledge_ids"][idx] = new_title
            
            # 更新connections中的引用
            for conn in graph.get("connections", []):
                if conn.get("source") == old_title:
                    conn["source"] = new_title
                if conn.get("target") == old_title:
                    conn["target"] = new_title
            
            with open(graph_file, "w", encoding="utf-8") as f:
                json.dump(graph, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Warning: Failed to update knowledge graph: {e}")
    
    # ==================== Token 统计日志 ====================
    
    def log_token_usage(self, conversation_id, conversation_title, action_type, input_tokens, output_tokens):
        """记录Token使用情况"""
        log_file = self.path + "token_usage.json"
        
        # 确保日志文件存在
        if not os.path.exists(log_file):
            with open(log_file, "w", encoding="utf-8") as f:
                json.dump([], f, indent=4, ensure_ascii=False)
        
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                logs = json.load(f)
        except:
            logs = []
        
        # 添加新日志
        log_entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "conversation_id": conversation_id,
            "conversation_title": conversation_title,
            "action": action_type,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens
        }
        
        logs.insert(0, log_entry)  # 最新的在最前
        
        # 限制日志数量（例如保留最近1000条）
        if len(logs) > 1000:
            logs = logs[:1000]
            
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=4, ensure_ascii=False)
            
    def get_token_logs(self):
        """获取Token使用日志"""
        log_file = self.path + "token_usage.json"
        if not os.path.exists(log_file):
            return []
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []

    # ==================== 知识图谱管理 ====================
    
    def set_knowledge_category(self, title, category_name):
        """设置知识的分类"""
        graph = self.get_knowledge_graph()
        
        # 检查分类是否存在
        if category_name not in graph["categories"]:
            # 如果不存在，尝试自动创建（或者报错）
            # 这里我们选择报错，要求先创建分类
            return False, f"分类 '{category_name}' 不存在，请先创建分类"
        
        # 1. 查找知识目前所在的分类并移除
        for cat_name, cat_data in graph["categories"].items():
            if title in cat_data["knowledge_ids"]:
                cat_data["knowledge_ids"].remove(title)
        
        # 2. 添加到新分类
        graph["categories"][category_name]["knowledge_ids"].append(title)
        
        self.save_knowledge_graph(graph)
        return True, f"已将 '{title}' 移动到分类 '{category_name}'"

    def get_knowledge_graph(self):
        """获取知识图谱数据"""
        with open(self.path + "knowledge_graph.json", "r", encoding="utf-8") as f:
            return json.load(f)
    
    def save_knowledge_graph(self, graph_data):
        """保存知识图谱数据"""
        with open(self.path + "knowledge_graph.json", "w", encoding="utf-8") as f:
            json.dump(graph_data, f, indent=4, ensure_ascii=False)
    
    def create_category(self, category_name, color="#667eea", position=None):
        """创建知识分类"""
        graph = self.get_knowledge_graph()
        
        if category_name in graph["categories"]:
            return False, "分类已存在"
        
        if position is None:
            position = {"x": 0, "y": len(graph["categories"]) * 150}
        
        graph["categories"][category_name] = {
            "name": category_name,
            "color": color,
            "knowledge_ids": [],
            "position": position
        }
        graph["category_order"].append(category_name)
        
        self.save_knowledge_graph(graph)
        return True, "创建成功"
    
    def delete_category(self, category_name):
        """删除分类（将知识移到未分类）"""
        graph = self.get_knowledge_graph()
        
        if category_name not in graph["categories"]:
            return False, "分类不存在"
        
        if category_name == "未分类":
            return False, "不能删除未分类"
        
        # 将该分类的知识移到未分类
        knowledge_ids = graph["categories"][category_name]["knowledge_ids"]
        graph["categories"]["未分类"]["knowledge_ids"].extend(knowledge_ids)
        
        # 删除分类
        del graph["categories"][category_name]
        graph["category_order"].remove(category_name)
        
        self.save_knowledge_graph(graph)
        return True, "删除成功"
    
    def update_category(self, old_name, new_name, color=None):
        """更新分类名称和颜色"""
        graph = self.get_knowledge_graph()
        
        if old_name not in graph["categories"]:
            return False, "分类不存在"
        
        if old_name == "未分类":
            return False, "不能修改未分类"
        
        # 如果名称改变了，检查新名称是否已存在
        if old_name != new_name and new_name in graph["categories"]:
            return False, "分类名称已存在"
        
        # 获取旧分类数据
        old_category = graph["categories"][old_name]
        
        # 如果名称改变
        if old_name != new_name:
            # 创建新分类（保留所有数据）
            graph["categories"][new_name] = old_category.copy()
            
            # 更新知识节点中的分类引用
            if "knowledge_nodes" in graph:
                for title, node in graph["knowledge_nodes"].items():
                    if node.get("category") == old_name:
                        node["category"] = new_name
            
            # 更新分类顺序
            idx = graph["category_order"].index(old_name)
            graph["category_order"][idx] = new_name
            
            # 删除旧分类
            del graph["categories"][old_name]
        
        # 更新颜色
        if color:
            graph["categories"][new_name]["color"] = color
        
        self.save_knowledge_graph(graph)
        return True, "更新成功"
    
    def move_knowledge_to_category(self, knowledge_title, category_name):
        """将知识移动到指定分类"""
        graph = self.get_knowledge_graph()
        
        if category_name not in graph["categories"]:
            return False, "分类不存在"
        
        # 从所有分类中移除该知识
        for cat in graph["categories"].values():
            if knowledge_title in cat["knowledge_ids"]:
                cat["knowledge_ids"].remove(knowledge_title)
        
        # 添加到目标分类
        if knowledge_title not in graph["categories"][category_name]["knowledge_ids"]:
            graph["categories"][category_name]["knowledge_ids"].append(knowledge_title)
        
        self.save_knowledge_graph(graph)
        return True, "移动成功"
    
    def add_connection(self, from_knowledge, to_knowledge, relation_type="关联", description=""):
        """添加知识之间的连接关系"""
        graph = self.get_knowledge_graph()
        
        connection = {
            "id": f"{from_knowledge}-{to_knowledge}-{int(time.time())}",
            "from": from_knowledge,
            "to": to_knowledge,
            "type": relation_type,
            "description": description,
            "created_at": time.time()
        }
        
        # 检查是否已存在相同连接
        for conn in graph["connections"]:
            if conn["from"] == from_knowledge and conn["to"] == to_knowledge:
                return False, "连接已存在"
        
        graph["connections"].append(connection)
        self.save_knowledge_graph(graph)
        return True, "添加成功"
    
    def remove_connection(self, connection_id):
        """删除连接"""
        graph = self.get_knowledge_graph()
        
        graph["connections"] = [c for c in graph["connections"] if c["id"] != connection_id]
        
        self.save_knowledge_graph(graph)
        return True, "删除成功"
    

    def get_knowledge_connections(self, knowledge_title=None):
        """获取某个知识的所有连接，如果不指定则返回所有"""
        graph = self.get_knowledge_graph()

        if not knowledge_title:
            return graph["connections"]

        connections = []
        for conn in graph["connections"]:
            if conn["from"] == knowledge_title or conn["to"] == knowledge_title:
                connections.append(conn)

        return connections

    def get_knowledge_graph_structure(self):
        """获取知识图谱的概览结构"""
        graph = self.get_knowledge_graph()
        structure = {
            "categories": [],
            "connections_count": len(graph.get("connections", []))
        }
        
        for name, data in graph.get("categories", {}).items():
            structure["categories"].append({
                "name": name,
                "knowledge_count": len(data.get("knowledge_ids", [])),
                "knowledge_list": data.get("knowledge_ids", [])
            })
            
        return structure

    def find_knowledge_path(self, start_title, end_title):
        """查找两个知识点之间的路径"""
        graph = self.get_knowledge_graph()
        connections = graph.get("connections", [])
        
        # 简单的BFS
        queue = [[start_title]]
        visited = {start_title}
        
        while queue:
            path = queue.pop(0)
            node = path[-1]
            
            if node == end_title:
                return path
            
            # 查找相邻节点
            for conn in connections:
                neighbor = None
                if conn["from"] == node:
                    neighbor = conn["to"]
                elif conn["to"] == node:
                    neighbor = conn["from"]
                
                if neighbor and neighbor not in visited:
                    visited.add(neighbor)
                    new_path = list(path)
                    new_path.append(neighbor)
                    queue.append(new_path)
                    
        return []

    def update_category_position(self, category_name, position):
        """更新分类位置（用于拖拽）"""
        graph = self.get_knowledge_graph()
        
        if category_name not in graph["categories"]:
            return False, "分类不存在"
        
        graph["categories"][category_name]["position"] = position
        self.save_knowledge_graph(graph)
        return True, "更新成功"
    
    def search_keyword(self, keyword, range_size=10):
        """
        在短期记忆和基础知识库中搜索关键词
        
        Args:
            keyword: 搜索关键词
            range_size: 关键词前后返回的字符数
            
        Returns:
            str: 格式化的搜索结果
        """
        with open(self.path + "database.json", "r", encoding="utf-8") as f:
            db = json.load(f)
        
        results = []
        
        # 搜索短期记忆（标题）
        for short_id, short_title in db["data_short"].items():
            if keyword in short_title:
                # 提取关键词前后的文本
                pos = short_title.find(keyword)
                context_start = max(0, pos - range_size)
                context_end = min(len(short_title), pos + len(keyword) + range_size)
                
                before = short_title[context_start:pos]
                match = keyword
                after = short_title[pos+len(keyword):context_end]
                
                results.append(f"[短期记忆 {short_id}]: ...{before}【{match}】{after}...")
        
        # 搜索基础知识库（标题和内容）
        for basis_title, basis_info in db["data_basis"].items():
            # 搜索标题
            if keyword in basis_title:
                pos = basis_title.find(keyword)
                context_start = max(0, pos - range_size)
                context_end = min(len(basis_title), pos + len(keyword) + range_size)
                
                before = basis_title[context_start:pos]
                match = keyword
                after = basis_title[pos+len(keyword):context_end]
                
                results.append(f"{basis_title}: (标题) ...{before}【{match}】{after}...")
            
            # 搜索内容
            try:
                with open(basis_info["src"], "r", encoding="utf-8") as f:
                    content = f.read()
                
                # 查找关键词的所有出现位置（最多3个）
                start = 0
                count = 0
                while count < 3:
                    pos = content.find(keyword, start)
                    if pos == -1:
                        break
                    
                    context_start = max(0, pos - range_size)
                    context_end = min(len(content), pos + len(keyword) + range_size)
                    
                    before = content[context_start:pos]
                    match = keyword
                    after = content[pos+len(keyword):context_end]
                    
                    results.append(f"{basis_title}: ...{before}【{match}】{after}...")
                    start = pos + 1
                    count += 1
                    
            except Exception as e:
                pass
        
        if not results:
            return f"未找到关键词: {keyword}"
        
        return "\n".join(results)
        
if __name__ == "__main__":
    os.chdir("../")
    user = User("test_user")