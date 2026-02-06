"""
ChatDB Web Server - Flask应用
提供Web界面的聊天和知识库管理功能
"""
import os
import sys
import json
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, Response
from flask_cors import CORS
from datetime import timedelta
import time

# 添加api目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'api'))
from model import Model
from database import User
from conversation_manager import ConversationManager

app = Flask(__name__)
app.secret_key = 'chatdb-secret-key-change-in-production'
app.config['SESSION_TYPE'] = 'filesystem'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
CORS(app)

# 切换到正确的工作目录
os.chdir(os.path.dirname(os.path.abspath(__file__)))


# ==================== 认证相关 ====================

@app.route('/')
def index():
    """首页 - 重定向到聊天或登录"""
    if 'username' in session:
        return redirect(url_for('chat', **request.args))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    """登录页面"""
    if request.method == 'GET':
        return render_template('login.html')
    
    # POST - 处理登录
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'success': False, 'message': '用户名和密码不能为空'})
    
    try:
        # 验证用户
        with open('./data/user.json', 'r', encoding='utf-8') as f:
            users = json.load(f)
        
        if username not in users:
            return jsonify({'success': False, 'message': '用户不存在'})
        
        if users[username]['password'] != password:
            return jsonify({'success': False, 'message': '密码错误'})
        
        # 更新登录IP
        users[username]['last_ip'] = request.remote_addr
        with open('./data/user.json', 'w', encoding='utf-8') as f:
            json.dump(users, f, indent=4, ensure_ascii=False)
            
        # 登录成功
        session['username'] = username
        session['role'] = users[username].get('role', 'member')
        session.permanent = True
        return jsonify({'success': True, 'message': '登录成功'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'登录失败: {str(e)}'})


@app.route('/logout')
def logout():
    """登出"""
    session.clear()
    return redirect(url_for('login'))


def require_login(f):
    """登录装饰器"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return jsonify({'success': False, 'message': '请先登录'}), 401
        return f(*args, **kwargs)
    return decorated_function


def require_admin(f):
    """管理员专用装饰器"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return jsonify({'success': False, 'message': '请先登录'}), 401
        if session.get('role') != 'admin':
            return jsonify({'success': False, 'message': '权限不足，仅管理员可访问'}), 403
        return f(*args, **kwargs)
    return decorated_function


# ==================== 用户信息 API ====================

@app.route('/api/user/info', methods=['GET'])
def get_user_info():
    """获取当前登录用户的信息"""
    if 'username' not in session:
        return jsonify({'success': False, 'message': '未登录'}), 401
    return jsonify({
        'success': True,
        'username': session.get('username'),
        'role': session.get('role', 'member')
    })


# ==================== 管理后台 API ====================

@app.route('/api/admin/users', methods=['GET'])
@require_admin
def admin_get_users():
    """获取所有用户信息"""
    try:
        with open('./data/user.json', 'r', encoding='utf-8') as f:
            users = json.load(f)
        
        user_list = []
        for uname, info in users.items():
            # 计算总 token 消耗 (从 token_usage.json 读取)
            total_tokens = 0
            # 这里我们简化一下，假设存在一个全局或用户目录下的 token_usage.json
            user_token_file = os.path.join(os.path.dirname(__file__), f"data/users/{uname}/token_usage.json")
            if os.path.exists(user_token_file):
                try:
                    with open(user_token_file, 'r', encoding='utf-8') as tf:
                        tokens = json.load(tf)
                        for log in tokens:
                            total_tokens += log.get('input_tokens', 0) + log.get('output_tokens', 0)
                except:
                    pass
            
            user_list.append({
                'username': uname,
                'password': info.get('password'), # 管理员可见密码，符合用户要求
                'role': info.get('role', 'member'),
                'last_ip': info.get('last_ip', '未知'),
                'total_token_usage': total_tokens
            })
            
        return jsonify({'success': True, 'users': user_list})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/admin/user/add', methods=['POST'])
@require_admin
def admin_add_user():
    """添加用户"""
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    role = data.get('role', 'member')
    
    if not username or not password:
        return jsonify({'success': False, 'message': '用户名和密码不能为空'})
        
    try:
        with open('./data/user.json', 'r', encoding='utf-8') as f:
            users = json.load(f)
            
        if username in users:
            return jsonify({'success': False, 'message': '用户已存在'})
            
        # 初始化用户目录
        user_path = f"./data/users/{username}/"
        os.makedirs(user_path, exist_ok=True)
        os.makedirs(user_path + "database/", exist_ok=True)
        os.makedirs(user_path + "conversations/", exist_ok=True)
        
        # 初始化 database.json
        db_file = user_path + "database.json"
        if not os.path.exists(db_file):
            with open(db_file, 'w', encoding='utf-8') as f:
                json.dump({"data_short": {}, "data_basis": {}}, f, indent=4, ensure_ascii=False)
        
        users[username] = {
            "username": username,
            "password": password,
            "path": user_path,
            "role": role,
            "last_ip": "从未登录"
        }
        
        with open('./data/user.json', 'w', encoding='utf-8') as f:
            json.dump(users, f, indent=4, ensure_ascii=False)
            
        return jsonify({'success': True, 'message': '用户添加成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/admin/user/delete', methods=['POST'])
@require_admin
def admin_delete_user():
    """删除用户"""
    data = request.get_json()
    username = data.get('target_username')
    
    if username == session['username']:
        return jsonify({'success': False, 'message': '不能删除自己'})
        
    try:
        with open('./data/user.json', 'r', encoding='utf-8') as f:
            users = json.load(f)
            
        if username not in users:
            return jsonify({'success': False, 'message': '用户不存在'})
            
        del users[username]
        
        with open('./data/user.json', 'w', encoding='utf-8') as f:
            json.dump(users, f, indent=4, ensure_ascii=False)
            
        # 注意：此处不主动删除磁盘文件，以防操作失误（数据无价）
        return jsonify({'success': True, 'message': '用户账号已注销'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/admin/user/role', methods=['POST'])
@require_admin
def admin_set_role():
    """修改用户权限"""
    data = request.get_json()
    username = data.get('username') or data.get('target_username')
    new_role = data.get('role') # 'admin' or 'member'
    
    if not username or not new_role:
        return jsonify({'success': False, 'message': '参数不完整'})
        
    if username == session.get('username'):
        return jsonify({'success': False, 'message': '管理员不能修改自己的权限'})
        
    try:
        with open('./data/user.json', 'r', encoding='utf-8') as f:
            users = json.load(f)
            
        if username not in users:
            return jsonify({'success': False, 'message': '用户不存在'})
            
        users[username]['role'] = new_role
        
        with open('./data/user.json', 'w', encoding='utf-8') as f:
            json.dump(users, f, indent=4, ensure_ascii=False)
            
        return jsonify({'success': True, 'message': f'用户 {username} 已设为 {new_role}'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/admin/user/password', methods=['POST'])
@require_admin
def admin_set_password():
    """修改用户密码"""
    data = request.get_json()
    username = data.get('target_username')
    new_password = data.get('password')
    
    if not username or not new_password:
        return jsonify({'success': False, 'message': '参数不完整'})
        
    try:
        with open('./data/user.json', 'r', encoding='utf-8') as f:
            users = json.load(f)
            
        if username not in users:
            return jsonify({'success': False, 'message': '用户不存在'})
            
        users[username]['password'] = new_password
        
        with open('./data/user.json', 'w', encoding='utf-8') as f:
            json.dump(users, f, indent=4, ensure_ascii=False)
            
        return jsonify({'success': True, 'message': '密码重置成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/admin/tokens/stats', methods=['GET'])
@require_admin
def admin_token_stats():
    """获取所有用户的总 token 消耗"""
    try:
        total_tokens = 0
        user_dir = os.path.join(os.path.dirname(__file__), "data/users")
        for username in os.listdir(user_dir):
            token_file = os.path.join(user_dir, username, "token_usage.json")
            if os.path.exists(token_file):
                try:
                    with open(token_file, 'r', encoding='utf-8') as f:
                        logs = json.load(f)
                        for log in logs:
                            total_tokens += log.get('input_tokens', 0) + log.get('output_tokens', 0)
                except:
                    pass
        return jsonify({'success': True, 'total': total_tokens})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


# ==================== 聊天相关 ====================

@app.route('/chat')
def chat():
    """聊天页面"""
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('chat.html', username=session['username'])


@app.route('/api/upload', methods=['POST'])
@require_login
def upload_file():
    """上传文件"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '没有文件'}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': '未选择文件'}), 400
        
    try:
        filename = file.filename
        suffix = os.path.splitext(filename)[1].lower()
        
        # VolcEngine File API 支持的格式 (图像, 视频, PDF)
        # 遇到 JSON/TXT 等纯文本文件，File API 会报错，因此我们在服务端转为文本内容返回
        VOLC_SUPPORTED_EXTS = {
            '.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tiff',
            '.pdf',
            '.mp4', '.mov', '.avi', '.webm', '.mkv', '.flv'
        }
        
        # 1. 如果是不支持直接上传的格式，尝试读取为文本
        if suffix not in VOLC_SUPPORTED_EXTS:
            try:
                content = file.read().decode('utf-8')
                return jsonify({
                    'success': True,
                    'type': 'text',
                    'content': content,
                    'filename': filename,
                    'message': '已解析为文本内容'
                })
            except UnicodeDecodeError:
                return jsonify({'success': False, 'message': '不支持的二进制文件格式'}), 400
            except Exception as e:
                return jsonify({'success': False, 'message': f'文件解析失败: {str(e)}'}), 500

        # 2. 支持的格式，上传到 VolcEngine
        # 保存到临时文件
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name
            
        try:
            # 初始化模型并上传
            model = Model(session['username'], auto_create=False)
            file_obj = model.upload_file(tmp_path)
            
            # 返回文件ID和名称
            return jsonify({
                'success': True,
                'type': 'file', 
                'file_id': file_obj.id,
                'filename': filename,
                'message': '上传成功'
            })
        finally:
            # 清理临时文件
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except:
                    pass
                
    except Exception as e:
        print(f"[ERROR] Upload failed: {e}")
        return jsonify({'success': False, 'message': f'上传失败: {str(e)}'}), 500


@app.route('/api/conversations', methods=['GET'])
@require_login
def list_conversations():
    """获取对话列表"""
    username = session['username']
    manager = ConversationManager(username)
    conversations = manager.list_conversations()
    return jsonify({'success': True, 'conversations': conversations})


@app.route('/api/conversations/<conv_id>', methods=['GET'])
@require_login
def get_conversation(conv_id):
    """获取对话详情"""
    username = session['username']
    manager = ConversationManager(username)
    try:
        conversation = manager.get_conversation(conv_id)
        return jsonify({'success': True, 'conversation': conversation})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/conversations/<conv_id>', methods=['DELETE'])
@require_login
def delete_conversation(conv_id):
    """删除对话"""
    username = session['username']
    manager = ConversationManager(username)
    success = manager.delete_conversation(conv_id)
    return jsonify({'success': success})



@app.route('/api/config', methods=['GET'])
@require_login
def get_config():
    """获取系统配置（模型列表等）"""
    try:
        CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                config = json.load(f)
                
            # 只返回前端需要的信息，不返回API Key
            models_info = []
            for model_id, info in config.get('models', {}).items():
                models_info.append({
                    'id': model_id,
                    'name': info['name'],
                    'provider': info.get('provider', 'volcengine'),
                    'status': info.get('status', 'normal')
                })
                
            return jsonify({
                'success': True,
                'models': models_info,
                'default_model': config.get('default_model')
            })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})
    
    return jsonify({'success': False, 'message': '配置加载失败'})


@app.route('/api/chat/stream', methods=['POST'])
@require_login
def chat_stream():
    """流式聊天接口"""
    data = request.get_json()
    message = data.get('message')
    conversation_id = data.get('conversation_id')
    model_name = data.get('model_name')
    enable_thinking = data.get('enable_thinking', False)
    enable_web_search = data.get('enable_web_search', True)
    enable_tools = data.get('enable_tools', True)
    show_token_usage = data.get('show_token_usage', False)
    
    if not message:
        return jsonify({'success': False, 'message': '消息不能为空'})
    
    username = session['username']
    
    def generate():
        """生成流式响应"""
        try:
            # 创建模型实例
            model = Model(
                username, 
                model_name=model_name,
                conversation_id=conversation_id,
                auto_create=(conversation_id is None)
            )
            
            # 发送对话ID
            if not conversation_id:
                yield f"data: {json.dumps({'type': 'conversation_id', 'conversation_id': model.conversation_id})}\n\n"
            
            # 流式处理消息
            for chunk in model.sendMessage(
                message, 
                stream=True,
                enable_thinking=enable_thinking,
                enable_web_search=enable_web_search,
                enable_tools=enable_tools,
                show_token_usage=show_token_usage
            ):
                chunk_data = json.dumps(chunk, ensure_ascii=False)
                yield f"data: {chunk_data}\n\n"
                time.sleep(0.01)  # 小延迟避免过快
            
        except Exception as e:
            error_data = json.dumps({
                'type': 'error',
                'content': f'处理消息时出错: {str(e)}'
            }, ensure_ascii=False)
            yield f"data: {error_data}\n\n"
    
    return Response(generate(), mimetype='text/event-stream')


@app.route('/api/tokens/stats', methods=['GET'])
@require_login
def get_token_stats():
    """获取Token使用统计"""
    username = session['username']
    user = User(username)
    
    try:
        logs = user.get_token_logs()
        
        total_tokens = 0
        today_tokens = 0
        
        # Calculate stats
        today_str = time.strftime("%Y-%m-%d", time.localtime())
        
        for log in logs:
            total_tokens += log.get('total_tokens', 0)
            if log.get('timestamp', '').startswith(today_str):
                today_tokens += log.get('total_tokens', 0)
                
        return jsonify({
            'success': True,
            'total': total_tokens,
            'today': today_tokens,
            'history': logs[:20]  # Optional: return recent logs if needed
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


# ==================== 知识库相关 ====================

@app.route('/knowledge')
def knowledge():
    """知识库页面"""
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('knowledge.html', username=session['username'])


@app.route('/api/knowledge/list', methods=['GET'])
@require_login
def list_knowledge():
    """获取知识库列表"""
    username = session['username']
    user = User(username)
    
    try:
        # 获取短期记忆和基础知识
        short_memory = user.getKnowledgeList(0)  # 短期记忆
        basis_knowledge = user.getKnowledgeList(1)  # 基础知识
        
        return jsonify({
            'success': True,
            'short_memory': short_memory,
            'basis_knowledge': basis_knowledge
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/knowledge/basis', methods=['GET'])
@require_login
def get_all_basis():
    """获取所有基础知识"""
    username = session['username']
    user = User(username)
    
    try:
        knowledge_list = user.getKnowledgeList(1)  # 1表示基础知识
        result = []
        for title in knowledge_list:
            content = user.getBasisContent(title)
            result.append({
                'title': title,
                'content': content
            })
        return jsonify({'success': True, 'knowledge': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/knowledge/basis/update', methods=['POST'])
@require_login
def update_basis_content():
    """更新基础知识内容"""
    username = session['username']
    user = User(username)
    data = request.get_json()
    
    title = data.get('title')
    content = data.get('content')
    
    if not title:
        return jsonify({'success': False, 'message': '标题不能为空'})
        
    try:
        success, msg = user.updateBasisContent(title, content)
        return jsonify({'success': success, 'message': msg})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/knowledge/basis/<title>', methods=['GET'])
@require_login
def get_basis_content(title):
    """获取单个基础知识内容"""
    username = session['username']
    user = User(username)
    
    try:
        content = user.getBasisContent(title)
        return jsonify({
            'success': True, 
            'knowledge': {
                'title': title,
                'content': content
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/knowledge/basis', methods=['POST'])
@require_login
def add_basis():
    """添加基础知识"""
    username = session['username']
    user = User(username)
    data = request.get_json()
    
    title = data.get('title')
    content = data.get('content')
    url = data.get('url', '')
    
    if not title or not content:
        return jsonify({'success': False, 'message': '标题和内容不能为空'})
    
    try:
        user.addBasis(title, content, url)
        return jsonify({'success': True, 'message': '添加成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/knowledge/basis/<title>', methods=['PUT'])
@require_login
def update_basis(title):
    """更新基础知识"""
    username = session['username']
    user = User(username)
    data = request.get_json()
    
    new_title = data.get('title')
    content = data.get('content')
    url = data.get('url', '')
    
    if not new_title or not content:
        return jsonify({'success': False, 'error': '标题和内容不能为空'})
    
    try:
        # 如果标题改变了，先删除旧的
        if title != new_title:
            user.removeBasis(title)
        user.addBasis(new_title, content, url)
        return jsonify({'success': True, 'message': '更新成功'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/knowledge/basis/<title>', methods=['DELETE'])
@require_login
def delete_basis(title):
    """删除基础知识"""
    username = session['username']
    user = User(username)
    
    try:
        user.removeBasis(title)
        return jsonify({'success': True, 'message': '删除成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/knowledge/short', methods=['GET'])
@require_login
def get_all_short():
    """获取所有短期记忆"""
    username = session['username']
    user = User(username)
    
    try:
        short_dict = user.getKnowledgeList(0)  # 0表示短期记忆，返回{ID: title}
        result = []
        for mem_id, title in short_dict.items():
            result.append({
                'id': mem_id,
                'title': title[:30] + '...' if len(title) > 30 else title,
                'content': title  # 完整内容
            })
        return jsonify({'success': True, 'memories': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/knowledge/short/<title>', methods=['GET'])
@require_login
def get_short_content(title):
    """获取单个短期记忆"""
    username = session['username']
    user = User(username)
    
    try:
        short_list = user.getKnowledgeList(0)
        if title in short_list:
            return jsonify({
                'success': True,
                'memory': {
                    'title': title,
                    'content': title
                }
            })
        else:
            return jsonify({'success': False, 'error': '未找到该记忆'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/knowledge/short', methods=['POST'])
@require_login
def add_short():
    """添加短期记忆"""
    username = session['username']
    user = User(username)
    data = request.get_json()
    
    title = data.get('title')
    content = data.get('content', title)  # 使用content字段，如果没有则使用title
    
    if not title:
        return jsonify({'success': False, 'error': '标题不能为空'})
    
    try:
        user.addShort(content if content else title)
        return jsonify({'success': True, 'message': '添加成功'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/knowledge/short/<title>', methods=['PUT'])
@require_login
def update_short(title):
    """更新短期记忆"""
    username = session['username']
    user = User(username)
    data = request.get_json()
    
    new_title = data.get('title')
    content = data.get('content', new_title)
    
    print(f"[DEBUG] 更新短期记忆: {title} -> {new_title}, content: {content}")
    
    if not new_title:
        return jsonify({'success': False, 'error': '标题不能为空'})
    
    try:
        # 短期记忆存储为 {ID: title} 字典
        short_dict = user.getKnowledgeList(0)  # 返回字典
        print(f"[DEBUG] 当前短期记忆: {short_dict}")
        
        # 查找要更新的记忆ID
        mem_id = None
        for mid, mtitle in short_dict.items():
            if mtitle == title:
                mem_id = mid
                break
        
        if mem_id is None:
            print(f"[ERROR] 找不到短期记忆: {title}")
            return jsonify({'success': False, 'error': f'找不到短期记忆: {title}'})
        
        print(f"[DEBUG] 找到记忆ID: {mem_id}")
        
        # 删除旧记忆（通过索引）
        short_list = list(short_dict.keys())
        idx = short_list.index(mem_id)
        user.removeShort(idx)
        print(f"[DEBUG] 已删除旧记忆，索引: {idx}")
        
        # 添加新记忆
        user.addShort(content if content else new_title)
        print(f"[DEBUG] 已添加新记忆: {content if content else new_title}")
        
        return jsonify({'success': True, 'message': '更新成功'})
    except Exception as e:
        print(f"[ERROR] 更新短期记忆失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/knowledge/short/<title>', methods=['DELETE'])
@require_login
def delete_short(title):
    """删除短期记忆"""
    username = session['username']
    user = User(username)
    
    try:
        # 通过title找到索引
        short_list = user.getKnowledgeList(0)
        if title in short_list:
            idx = short_list.index(title)
            user.removeShort(idx)
            return jsonify({'success': True, 'message': '删除成功'})
        else:
            return jsonify({'success': False, 'error': '未找到该记忆'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ==================== 知识图谱相关 ====================

@app.route('/knowledge_graph')
@require_login
def knowledge_graph():
    """知识图谱页面"""
    return render_template('knowledge_graph.html', username=session['username'])


@app.route('/token_logs')
@require_login
def token_logs():
    """Token记录页面"""
    return render_template('token_logs.html', username=session['username'])


@app.route('/api/knowledge/graph', methods=['GET'])
@require_login
def get_knowledge_graph():
    """获取知识图谱数据"""
    username = session['username']
    user = User(username)
    
    try:
        graph = user.get_knowledge_graph()
        
        # 获取所有基础知识
        all_basis = user.getKnowledgeList(1)  # 1表示基础知识
        
        # 收集所有已分类的知识ID
        categorized = set()
        for category in graph['categories'].values():
            categorized.update(category['knowledge_ids'])
        
        # 将未分类的知识添加到"未分类"分类中
        uncategorized = [k for k in all_basis.keys() if k not in categorized]
        if uncategorized:
            if '未分类' not in graph['categories']:
                graph['categories']['未分类'] = {
                    'name': '未分类',
                    'color': '#9ca3af',
                    'knowledge_ids': [],
                    'position': {'x': 100, 'y': 100}
                }
            graph['categories']['未分类']['knowledge_ids'].extend(uncategorized)
        
        return jsonify({'success': True, 'graph': graph})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/knowledge/categories', methods=['POST'])
@require_login
def create_category():
    """创建知识分类"""
    username = session['username']
    user = User(username)
    data = request.get_json()
    
    name = data.get('name')
    color = data.get('color', '#667eea')
    
    if not name:
        return jsonify({'success': False, 'error': '分类名称不能为空'})
    
    try:
        success, message = user.create_category(name, color)
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/knowledge/categories/<category_name>', methods=['DELETE'])
@require_login
def delete_category_route(category_name):
    """删除分类"""
    username = session['username']
    user = User(username)
    
    try:
        success, message = user.delete_category(category_name)
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/knowledge/categories/<category_name>', methods=['PUT'])
@require_login
def update_category_route(category_name):
    """更新分类"""
    username = session['username']
    user = User(username)
    data = request.get_json()
    
    new_name = data.get('name')
    color = data.get('color')
    
    if not new_name:
        return jsonify({'success': False, 'error': '分类名称不能为空'})
    
    try:
        success, message = user.update_category(category_name, new_name, color)
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/knowledge/move', methods=['POST'])
@require_login
def move_knowledge():
    """移动知识到分类"""
    username = session['username']
    user = User(username)
    data = request.get_json()
    
    knowledge = data.get('knowledge')
    category = data.get('category')
    
    if not knowledge or not category:
        return jsonify({'success': False, 'error': '参数错误'})
    
    try:
        success, message = user.move_knowledge_to_category(knowledge, category)
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/knowledge/connections', methods=['POST'])
@require_login
def add_connection():
    """添加知识连接"""
    username = session['username']
    user = User(username)
    data = request.get_json()
    
    from_knowledge = data.get('from')
    to_knowledge = data.get('to')
    relation_type = data.get('type', '关联')
    description = data.get('description', '')
    
    if not from_knowledge or not to_knowledge:
        return jsonify({'success': False, 'error': '参数错误'})
    
    try:
        success, message = user.add_connection(from_knowledge, to_knowledge, relation_type, description)
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/knowledge/connections/<connection_id>', methods=['DELETE'])
@require_login
def delete_connection(connection_id):
    """删除知识连接"""
    username = session['username']
    user = User(username)
    
    try:
        success, message = user.remove_connection(connection_id)
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/knowledge/graph/positions', methods=['PUT'])
@require_login
def update_positions():
    """更新分类位置"""
    username = session['username']
    user = User(username)
    data = request.get_json()
    
    category = data.get('category')
    position = data.get('position')
    
    if not category or not position:
        return jsonify({'success': False, 'error': '参数不完整'})
    
    try:
        graph = user.get_knowledge_graph()
        if category in graph['categories']:
            graph['categories'][category]['position'] = position
        user.save_knowledge_graph(graph)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/knowledge/nodes/positions', methods=['PUT'])
@require_login
def update_knowledge_position():
    """更新知识节点位置"""
    username = session['username']
    user = User(username)
    data = request.get_json()
    
    title = data.get('title')
    position = data.get('position')
    
    if not title or not position:
        return jsonify({'success': False, 'error': '参数不完整'})
    
    try:
        graph = user.get_knowledge_graph()
        if 'knowledge_nodes' not in graph:
            graph['knowledge_nodes'] = {}
        
        # 保留category信息
        if title in graph['knowledge_nodes']:
            graph['knowledge_nodes'][title]['x'] = position['x']
            graph['knowledge_nodes'][title]['y'] = position['y']
        else:
            # 查找知识所属分类
            category = None
            for cat_name, cat_data in graph['categories'].items():
                if title in cat_data['knowledge_ids']:
                    category = cat_name
                    break
            graph['knowledge_nodes'][title] = {
                'x': position['x'],
                'y': position['y'],
                'category': category
            }
        
        user.save_knowledge_graph(graph)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/knowledge/ai/organize', methods=['POST'])
@require_login
def ai_organize():
    """AI自动整理知识库"""
    username = session['username']
    model = Model(username, auto_create=False)
    user = User(username)
    
    try:
        # 获取所有知识
        basis_list = user.getKnowledgeList(1)
        short_list = user.getKnowledgeList(0)
        
        # 构建提示词让AI分析
        all_knowledge = []
        for title in basis_list.keys():
            content = user.getBasisContent(title)
            all_knowledge.append(f"【{title}】\n{content[:300]}...")
        
        prompt = f"""分析以下知识库内容，构建更符合人类认知脉络的知识图谱。
1. 分类方案：将知识点归纳到3-5个主要领域。
2. 关系脉络：识别知识点之间的演化、推导、依赖或提及关系。

知识列表：
{chr(10).join(all_knowledge)}

请以JSON格式返回：
{{
    "categories": [
        {{"name": "分类名", "color": "#颜色代码", "knowledge": ["知识标题1", "知识标题2"]}}
    ],
    "nodes": [
        {{"title": "知识标题", "summary": "一句话核心脉络"}}
    ],
    "connections": [
        {{"from": "知识标题A", "to": "知识标题B", "type": "脉络/提及/依赖/属于", "description": "简短描述关系"}}
    ]
}}"""
        

        # 调用AI模型
        response_content = ""
        # 使用流式接口同步获取
        for chunk in model.sendMessage(prompt, stream=False, enable_tools=False):
            if isinstance(chunk, dict):
                 if chunk.get('type') == 'content_delta':
                     response_content += chunk.get('content', '')
                 elif chunk.get('type') == 'done':
                     if not response_content and chunk.get('content'):
                         response_content = chunk.get('content')
            elif hasattr(chunk, 'content'):
                response_content += chunk.content
        
        print(f"[DEBUG] AI整理响应: {response_content[:100]}...")

        # 尝试解析JSON
        try:
            # 找到JSON部分
            start = response_content.find('{')
            end = response_content.rfind('}') + 1
            if start != -1 and end != -1:
                json_str = response_content[start:end]
                result = json.loads(json_str)
                
                # 更新分类
                if 'categories' in result:
                    # 获取当前图谱
                    graph = user.get_knowledge_graph()
                    
                    # 记录旧的分类和位置，以便保留
                    old_categories = graph.get('categories', {})
                    
                    # 清空当前分类（除了未分类）
                    graph['categories'] = {}
                    if '未分类' in old_categories:
                        graph['categories']['未分类'] = old_categories['未分类']
                        graph['categories']['未分类']['knowledge_ids'] = [] # 清空内容，重新分配

                    # 重新构建分类
                    for i, cat in enumerate(result['categories']):
                        name = cat['name']
                        color = cat.get('color', '#667eea')
                        knowledge = cat.get('knowledge', [])
                        
                        # 先给个默认位置，稍后统一布局
                        graph['categories'][name] = {
                            'name': name,
                            'color': color,
                            'knowledge_ids': knowledge,
                            'position': {'x': 0, 'y': 0} 
                        }
                    
                    # 3. 处理知识连接
                    if 'connections' in result:
                        for conn in result['connections']:
                            from_k = conn.get('from')
                            to_k = conn.get('to')
                            # 验证知识点是否存在
                            if from_k in basis_list and to_k in basis_list:
                                # 检查是否重复
                                exists = False
                                for old_conn in graph['connections']:
                                    if old_conn['from'] == from_k and old_conn['to'] == to_k:
                                        exists = True
                                        break
                                if not exists:
                                    graph['connections'].append({
                                        "id": f"{from_k}-{to_k}-{int(time.time())}",
                                        "from": from_k,
                                        "to": to_k,
                                        "type": conn.get('type', '脉络'),
                                        "description": conn.get('description', 'AI自动脉络识别'),
                                        "created_at": time.time()
                                    })

                    # 应用自动布局
                    _apply_auto_layout(graph)
                    
                    user.save_knowledge_graph(graph)
                    return jsonify({'success': True, 'message': '整理完成'})
                    
        except Exception as e:
            print(f"[ERROR] 解析AI响应失败: {e}")
                
    except Exception as e:
        print(f"[ERROR] AI整理失败: {e}")
        return jsonify({'success': False, 'message': str(e)})
        
    return jsonify({'success': True, 'message': 'AI整理完成'})

@app.route('/api/knowledge/ai/scan', methods=['POST'])
@require_login
def ai_scan_links():
    """批量扫描所有知识点并建立自动连接"""
    username = session['username']
    user = User(username)
    
    try:
        basis_list = user.getKnowledgeList(1)
        count = 0
        for title in basis_list.keys():
            if user.auto_link_knowledge(title):
                count += 1
        return jsonify({'success': True, 'message': f'扫描完成，更新了 {count} 个连接'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/knowledge/layout', methods=['POST'])
@require_login
def auto_layout():
    """纯自动布局接口"""
    username = session['username']
    user = User(username)
    
    try:
        graph = user.get_knowledge_graph()
        _apply_auto_layout(graph)
        user.save_knowledge_graph(graph)
        return jsonify({'success': True, 'message': '布局完成'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

def _apply_auto_layout(graph):
    """应用圆形布局算法"""
    import math
    import random
    
    center_x, center_y = 600, 400
    radius = 360 # 增大分类圆环半径
    
    categories = graph.get('categories', {})
    cat_names = list(categories.keys())
    cat_count = len(cat_names)
    
    for i, name in enumerate(cat_names):
        cat = categories[name]
        
        # 计算分类位置
        if cat_count > 0:
            angle = (2 * math.pi / cat_count) * i
            x = center_x + radius * math.cos(angle)
            y = center_y + radius * math.sin(angle)
        else:
            x, y = center_x, center_y
            
        cat['position'] = {'x': x, 'y': y}
        
        # 计算子节点位置
        knowledge_ids = cat.get('knowledge_ids', [])
        node_radius = 160 # 增大节点分散半径
        node_count = len(knowledge_ids)
        
        if 'knowledge_nodes' not in graph:
            graph['knowledge_nodes'] = {}
            
        for j, k_title in enumerate(knowledge_ids):
            # 改进：按照行列式排列，体现脉络感
            col = j % 4
            row = j // 4
            n_x = x + (col * 200) - 300
            n_y = y + (row * 150) - 100
            
            graph['knowledge_nodes'][k_title] = {
                'x': n_x, 
                'y': n_y,
                'category': name
            }



@app.route('/api/knowledge/ai/index', methods=['POST'])
@require_login
def ai_generate_index():
    """AI生成分类索引"""
    username = session['username']
    user = User(username)
    data = request.get_json()
    
    category = data.get('category')
    
    if not category:
        return jsonify({'success': False, 'error': '未指定分类'})
    
    try:
        from api.model import Model
        
        graph = user.get_knowledge_graph()
        if category not in graph['categories']:
            return jsonify({'success': False, 'error': '分类不存在'})
        
        knowledge_ids = graph['categories'][category]['knowledge_ids']
        
        if not knowledge_ids:
            return jsonify({'success': False, 'error': '该分类下没有知识'})
        
        # 构建知识标题列表
        titles_text = "\n".join([f"- {title}" for title in knowledge_ids])
        
        prompt = f"""请为【{category}】分类生成一个简洁的知识索引。

该分类包含以下知识：
{titles_text}

请生成：
1. 该分类的整体概述（1-2句话）
2. 知识点之间的关联和主题分布
3. 使用Markdown格式输出，简洁明了"""
        
        # 调用AI模型
        model = Model(username, auto_create=False)
        index_content = ""
        for chunk in model.sendMessage(prompt, stream=False):
            if chunk.get('type') == 'text':
                index_content += chunk.get('content', '')
        
        return jsonify({'success': True, 'index': index_content})
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/token_logs', methods=['GET'])
@require_login
def get_token_logs():
    """获取Token统计日志"""
    username = session['username']
    user = User(username)
    
    logs = user.get_token_logs()
    return jsonify({'success': True, 'logs': logs})


# ==================== 启动服务器 ====================

if __name__ == '__main__':
    # 确保必要的目录存在
    os.makedirs('./templates', exist_ok=True)
    os.makedirs('./static/css', exist_ok=True)
    os.makedirs('./static/js', exist_ok=True)
    
    print("🚀 ChatDB Web Server Starting...")
    print("📍 访问地址: http://localhost:5000")
    print("💡 使用 Ctrl+C 停止服务器")
    
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)
