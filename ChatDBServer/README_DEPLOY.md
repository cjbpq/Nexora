# ChatDB 云端部署指南

## ✅ 项目已完全使用相对路径

本项目所有路径都已使用相对路径，**可以直接复制到任何服务器运行**。

## 📁 目录结构
```
ChatDBServer/
├── server.py           # 主服务器（启动时自动切换到项目目录）
├── config.json         # 配置文件（包含API Keys和模型配置）
├── requirements.txt    # Python依赖
├── api/               # 后端API模块
│   ├── model.py       # AI模型封装
│   ├── database.py    # 数据库管理
│   ├── conversation_manager.py
│   └── tools.py       # 工具定义
├── data/              # 数据目录（相对路径）
│   ├── user.json      # 用户认证信息
│   └── users/         # 用户数据（自动创建）
├── static/            # 静态资源（Flask自动识别）
│   ├── css/
│   └── js/
└── templates/         # HTML模板（Flask自动识别）
```

## 🚀 部署步骤

### 1. 上传项目
```bash
# 方法一：直接复制整个文件夹
scp -r ChatDBServer/ user@server:/path/to/

# 方法二：使用git
git clone <your-repo> /path/to/ChatDBServer
```

### 2. 安装依赖
```bash
cd /path/to/ChatDBServer
pip3 install -r requirements.txt
```

### 3. 配置API Key
编辑 `config.json`，填入你的火山引擎API Key：
```json
{
    "models": {
        "doubao-seed-1-6-251015": {
            "name": "Doubao Seed 1.6 (251015)",
            "api_key": "YOUR_API_KEY_HERE"
        }
    }
}
```

### 4. 启动服务

**开发环境：**
```bash
python3 server.py
```

**生产环境（推荐使用gunicorn）：**
```bash
# 安装gunicorn
pip3 install gunicorn

# 启动服务（4个worker进程）
gunicorn -w 4 -b 0.0.0.0:5000 server:app
```

## 🔒 安全配置

### 修改Secret Key
生产环境务必修改 `server.py` 中的 `secret_key`：
```python
app.secret_key = 'your-random-secret-key-here'
```

### 配置防火墙
```bash
# 仅开放必要端口
ufw allow 5000/tcp
ufw enable
```

## 📝 路径验证

所有路径都使用相对路径：
- ✅ 数据文件: `./data/users/{username}/`
- ✅ 配置文件: 相对于server.py的位置
- ✅ 用户认证: `./data/user.json`
- ✅ 静态资源: Flask自动处理
- ✅ 模板文件: Flask自动处理

**工作目录自动切换：**
```python
os.chdir(os.path.dirname(os.path.abspath(__file__)))
```
这确保无论从哪里启动，项目都能正确运行。

## 🌐 Nginx反向代理（可选）

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 🔄 systemd服务配置（推荐）

创建 `/etc/systemd/system/chatdb.service`：
```ini
[Unit]
Description=ChatDB Server
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/ChatDBServer
ExecStart=/usr/bin/python3 /path/to/ChatDBServer/server.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

启用服务：
```bash
sudo systemctl enable chatdb
sudo systemctl start chatdb
sudo systemctl status chatdb
```

## ✅ 检查清单

部署前确认：
- [ ] 已安装Python 3.8+
- [ ] 已安装requirements.txt中的依赖
- [ ] config.json中填入了有效的API Key
- [ ] data/user.json配置了用户账号
- [ ] 端口5000未被占用（或修改为其他端口）
- [ ] 防火墙已配置允许访问
- [ ] 生产环境已修改secret_key

## 🐛 常见问题

### 1. 端口被占用
修改 `server.py` 最后一行：
```python
app.run(debug=False, host='0.0.0.0', port=8080, threaded=True)
```

### 2. 权限问题
确保data目录有写权限：
```bash
chmod -R 755 data/
```

### 3. 模块找不到
确保在项目根目录运行：
```bash
cd /path/to/ChatDBServer
python3 server.py
```

## 📊 监控日志

```bash
# 查看实时日志
tail -f /var/log/chatdb.log

# 或使用systemd日志
journalctl -u chatdb -f
```
