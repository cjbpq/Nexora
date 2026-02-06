// 全局变量
let canvas, ctx, overlay;
let categories = {};
let connections = [];
let knowledgeData = { basis: [], short: [] };
let knowledgeNodes = {};  // 知识节点位置 {title: {x, y, category}}
let currentView = 'basis';
let isDraggingCanvas = false;
let isDraggingNode = false;
let draggedNode = null;
let dragOffset = { x: 0, y: 0 };
let canvasOffset = { x: 0, y: 0 };
let scale = 1;
let connectMode = false;
let connectionStart = null;
let connectionStartType = null;  // 'category' or 'knowledge'
let selectedNode = null;
let selectedNodeType = null;  // 'category' or 'knowledge'
let hoveredConnection = null;

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    canvas = document.getElementById('graphCanvas');
    ctx = canvas.getContext('2d');
    overlay = document.getElementById('canvasOverlay');
    
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);
    
    setupEventListeners();
    loadKnowledgeGraph();
    loadKnowledgeData();
});

function resizeCanvas() {
    canvas.width = canvas.offsetWidth;
    canvas.height = canvas.offsetHeight;
    draw();
}

// 设置事件监听
function setupEventListeners() {
    // 工具栏按钮
    document.getElementById('addCategoryBtn').addEventListener('click', () => {
        openModal('addCategoryModal');
    });
    
    document.getElementById('connectModeBtn').addEventListener('click', toggleConnectMode);
    document.getElementById('aiOrganizeBtn').addEventListener('click', aiOrganize);
    document.getElementById('aiIndexBtn').addEventListener('click', aiGenerateIndex);
    
    // 知识库标签切换
    document.querySelectorAll('.knowledge-tabs .tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.knowledge-tabs .tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentView = btn.dataset.type;
            renderKnowledgeList();
        });
    });
    
    // 画布控制
    document.getElementById('zoomInBtn').addEventListener('click', () => zoom(1.2));
    document.getElementById('zoomOutBtn').addEventListener('click', () => zoom(0.8));
    document.getElementById('resetViewBtn').addEventListener('click', resetView);
    
    // 画布拖拽
    canvas.addEventListener('mousedown', onCanvasMouseDown);
    canvas.addEventListener('mousemove', onCanvasMouseMove);
    canvas.addEventListener('mouseup', onCanvasMouseUp);
    canvas.addEventListener('wheel', onCanvasWheel);
    
    // 颜色选择器
    document.querySelectorAll('.color-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.color-btn').forEach(b => b.classList.remove('selected'));
            btn.classList.add('selected');
            document.getElementById('selectedColor').value = btn.dataset.color;
        });
    });
    
    // 搜索
    document.getElementById('searchInput').addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase();
        filterKnowledgeList(query);
    });
}

// 加载知识图谱数据
async function loadKnowledgeGraph() {
    try {
        const response = await fetch('/api/knowledge/graph');
        const data = await response.json();
        
        if (data.success) {
            categories = data.graph.categories;
            connections = data.graph.connections;
            knowledgeNodes = data.graph.knowledge_nodes || {};
            
            // 为没有位置的知识节点初始化位置
            Object.entries(categories).forEach(([catName, category], catIndex) => {
                category.knowledge_ids.forEach((kid, kidIndex) => {
                    if (!knowledgeNodes[kid]) {
                        // 围绕分类节点布局
                        const angle = (kidIndex / category.knowledge_ids.length) * 2 * Math.PI;
                        const radius = 200;
                        knowledgeNodes[kid] = {
                            x: category.position.x + Math.cos(angle) * radius,
                            y: category.position.y + Math.sin(angle) * radius,
                            category: catName
                        };
                    }
                });
            });
            
            renderGraph();
        }
    } catch (error) {
        console.error('加载知识图谱失败:', error);
    }
}

// 加载知识库数据
async function loadKnowledgeData() {
    try {
        // 加载基础知识
        const basisResponse = await fetch('/api/knowledge/basis');
        const basisData = await basisResponse.json();
        if (basisData.success) {
            knowledgeData.basis = basisData.knowledge;
        }
        
        // 加载短期记忆
        const shortResponse = await fetch('/api/knowledge/short');
        const shortData = await shortResponse.json();
        if (shortData.success) {
            knowledgeData.short = shortData.memories;
        }
        
        renderKnowledgeList();
    } catch (error) {
        console.error('加载知识库失败:', error);
    }
}

// 渲染知识列表
function renderKnowledgeList() {
    const container = document.getElementById('knowledgeList');
    container.innerHTML = '';
    
    const data = currentView === 'basis' ? knowledgeData.basis : knowledgeData.short;
    
    data.forEach(item => {
        const itemEl = document.createElement('div');
        itemEl.className = 'knowledge-item';
        // 显示完整内容，短期记忆使用content字段
        const displayText = item.content || item.title;
        itemEl.textContent = displayText;
        itemEl.draggable = true;
        itemEl.dataset.title = displayText;  // 保存完整内容作为标题
        itemEl.dataset.type = currentView;
        
        // 拖拽事件
        itemEl.addEventListener('dragstart', onKnowledgeDragStart);
        itemEl.addEventListener('dragend', onKnowledgeDragEnd);
        
        // 点击查看详情
        itemEl.addEventListener('click', () => {
            showKnowledgeDetail(item);
        });
        
        container.appendChild(itemEl);
    });
}

// 筛选知识列表
function filterKnowledgeList(query) {
    const items = document.querySelectorAll('.knowledge-item');
    items.forEach(item => {
        const title = item.textContent.toLowerCase();
        if (title.includes(query)) {
            item.style.display = 'block';
        } else {
            item.style.display = 'none';
        }
    });
}

// 渲染图谱
function renderGraph() {
    // 清空覆盖层
    overlay.innerHTML = '';
    
    // 绘制连接线和节点
    draw();
    
    // 创建分类节点
    Object.entries(categories).forEach(([name, category]) => {
        createCategoryNode(name, category);
    });
    
    // 创建知识节点
    Object.entries(knowledgeNodes).forEach(([title, node]) => {
        createKnowledgeNode(title, node);
    });
}

// 创建分类节点（圆形标题节点）
function createCategoryNode(name, category) {
    const node = document.createElement('div');
    node.className = 'category-node';
    node.dataset.category = name;
    node.style.left = (category.position.x + canvasOffset.x) * scale + 'px';
    node.style.top = (category.position.y + canvasOffset.y) * scale + 'px';
    node.style.background = category.color;
    node.style.transform = `scale(${scale})`;
    
    node.innerHTML = `
        <div class="node-title">${name}</div>
        <div class="node-count">${category.knowledge_ids.length}</div>
    `;
    
    // 选中效果
    if (selectedNode === name && selectedNodeType === 'category') {
        node.classList.add('selected');
    }
    
    // 事件监听
    node.addEventListener('mousedown', (e) => {
        e.stopPropagation();
        if (connectMode) {
            handleConnectClick('category', name);
        } else {
            startDragNode(e, 'category', name);
        }
    });
    
    node.addEventListener('click', (e) => {
        e.stopPropagation();
        if (!connectMode) {
            selectNode('category', name);
        }
    });
    
    overlay.appendChild(node);
}

// 创建知识节点（矩形知识卡片）
function createKnowledgeNode(title, node) {
    const nodeEl = document.createElement('div');
    nodeEl.className = 'knowledge-node';
    nodeEl.dataset.knowledge = title;
    nodeEl.style.left = (node.x + canvasOffset.x) * scale + 'px';
    nodeEl.style.top = (node.y + canvasOffset.y) * scale + 'px';
    nodeEl.style.transform = `scale(${scale})`;
    
    // 显示标题（截断长文本）
    const displayTitle = title.length > 20 ? title.substring(0, 18) + '...' : title;
    nodeEl.innerHTML = `<div class="node-title">${displayTitle}</div>`;
    
    // 选中效果
    if (selectedNode === title && selectedNodeType === 'knowledge') {
        nodeEl.classList.add('selected');
    }
    
    // 事件监听
    nodeEl.addEventListener('mousedown', (e) => {
        e.stopPropagation();
        if (connectMode) {
            handleConnectClick('knowledge', title);
        } else {
            startDragNode(e, 'knowledge', title);
        }
    });
    
    nodeEl.addEventListener('click', (e) => {
        e.stopPropagation();
        if (!connectMode) {
            selectNode('knowledge', title);
            showKnowledgeDetailByTitle(title);
        }
    });
    
    overlay.appendChild(nodeEl);
}

// 绘制连接线
function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    // 1. 绘制分类到知识的归属连接
    Object.entries(categories).forEach(([catName, category]) => {
        category.knowledge_ids.forEach(kid => {
            if (knowledgeNodes[kid]) {
                const catPos = category.position;
                const kidPos = knowledgeNodes[kid];
                
                const x1 = (catPos.x + canvasOffset.x) * scale;
                const y1 = (catPos.y + canvasOffset.y) * scale;
                const x2 = (kidPos.x + canvasOffset.x) * scale;
                const y2 = (kidPos.y + canvasOffset.y) * scale;
                
                // 判断是否被选中（显示断开按钮）
                const isSelected = selectedNode === kid && selectedNodeType === 'knowledge';
                
                drawCategoryConnection(x1, y1, x2, y2, category.color, isSelected, kid, catName);
            }
        });
    });
    
    // 2. 绘制知识之间的依赖连接
    connections.forEach(conn => {
        if (knowledgeNodes[conn.from] && knowledgeNodes[conn.to]) {
            const fromPos = knowledgeNodes[conn.from];
            const toPos = knowledgeNodes[conn.to];
            
            const x1 = (fromPos.x + canvasOffset.x) * scale;
            const y1 = (fromPos.y + canvasOffset.y) * scale;
            const x2 = (toPos.x + canvasOffset.x) * scale;
            const y2 = (toPos.y + canvasOffset.y) * scale;
            
            drawKnowledgeConnection(x1, y1, x2, y2, conn.type, conn.id);
        }
    });
}

// 绘制分类归属连接（实线）
function drawCategoryConnection(x1, y1, x2, y2, color, isSelected, knowledgeTitle, categoryName) {
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = isSelected ? 3 : 2;
    ctx.setLineDash([]);
    
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();
    
    // 如果选中，在连线中点显示断开按钮
    if (isSelected) {
        const midX = (x1 + x2) / 2;
        const midY = (y1 + y2) / 2;
        
        // 绘制断开按钮背景
        ctx.fillStyle = '#ef4444';
        ctx.beginPath();
        ctx.arc(midX, midY, 15, 0, 2 * Math.PI);
        ctx.fill();
        
        // 绘制X图标
        ctx.strokeStyle = 'white';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(midX - 6, midY - 6);
        ctx.lineTo(midX + 6, midY + 6);
        ctx.moveTo(midX + 6, midY - 6);
        ctx.lineTo(midX - 6, midY + 6);
        ctx.stroke();
        
        // 保存按钮位置用于点击检测
        if (!window.disconnectButtons) window.disconnectButtons = [];
        window.disconnectButtons.push({
            x: midX,
            y: midY,
            radius: 15,
            knowledge: knowledgeTitle,
            category: categoryName
        });
    }
    
    ctx.restore();
}

// 绘制知识依赖连接（虚线，带箭头）
function drawKnowledgeConnection(x1, y1, x2, y2, type, connId) {
    ctx.save();
    
    // 根据类型设置样式
    const styles = {
        '关联': { color: '#667eea', dash: [] },
        '依赖': { color: '#ef4444', dash: [] },
        '扩展': { color: '#10b981', dash: [] },
        '对比': { color: '#f59e0b', dash: [5, 5] },
        '补充': { color: '#8b5cf6', dash: [] }
    };
    
    const style = styles[type] || styles['关联'];
    ctx.strokeStyle = style.color;
    ctx.lineWidth = 2;
    ctx.setLineDash(style.dash);
    
    // 绘制曲线
    const cp1x = x1 + (x2 - x1) / 3;
    const cp1y = y1 - 50;
    const cp2x = x2 - (x2 - x1) / 3;
    const cp2y = y2 - 50;
    
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, x2, y2);
    ctx.stroke();
    
    // 绘制箭头
    const angle = Math.atan2(y2 - cp2y, x2 - cp2x);
    const arrowLength = 10;
    ctx.beginPath();
    ctx.moveTo(x2, y2);
    ctx.lineTo(
        x2 - arrowLength * Math.cos(angle - Math.PI / 6),
        y2 - arrowLength * Math.sin(angle - Math.PI / 6)
    );
    ctx.moveTo(x2, y2);
    ctx.lineTo(
        x2 - arrowLength * Math.cos(angle + Math.PI / 6),
        y2 - arrowLength * Math.sin(angle + Math.PI / 6)
    );
    ctx.stroke();
    
    ctx.restore();
}

// 画布交互事件
function onCanvasMouseDown(e) {
    if (e.button === 0 && !isDraggingCategory) {
        isDraggingCanvas = true;
        dragOffset.x = e.clientX - canvasOffset.x;
        dragOffset.y = e.clientY - canvasOffset.y;
        canvas.style.cursor = 'grabbing';
    }
}

function onCanvasMouseMove(e) {
    if (isDraggingCanvas) {
        canvasOffset.x = e.clientX - dragOffset.x;
        canvasOffset.y = e.clientY - dragOffset.y;
        renderGraph();
    } else if (isDraggingCategory && draggedCategory) {
        const rect = canvas.getBoundingClientRect();
        const x = (e.clientX - rect.left - canvasOffset.x) / scale;
        const y = (e.clientY - rect.top - canvasOffset.y) / scale;
        categories[draggedCategory].position = { x, y };
        renderGraph();
    }
}

function onCanvasMouseUp(e) {
    if (isDraggingCanvas) {
        isDraggingCanvas = false;
        canvas.style.cursor = 'grab';
    }
    if (isDraggingCategory) {
        isDraggingCategory = false;
        draggedCategory = null;
        // 保存位置
        saveCategoryPosition();
    }
}

function onCanvasWheel(e) {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    zoom(delta);
}

// 分类卡片拖拽
function onCategoryMouseDown(e, categoryName) {
    if (e.button === 0) {
        isDraggingCategory = true;
        draggedCategory = categoryName;
        e.stopPropagation();
    }
}

// 知识项拖拽
function onKnowledgeDragStart(e) {
    e.target.classList.add('dragging');
    e.dataTransfer.setData('knowledge', e.target.dataset.title);
    e.dataTransfer.setData('type', e.target.dataset.type);
}

function onKnowledgeDragEnd(e) {
    e.target.classList.remove('dragging');
}

function onCategoryDrop(e, categoryName) {
    e.preventDefault();
    const knowledgeTitle = e.dataTransfer.getData('knowledge');
    if (knowledgeTitle) {
        moveKnowledgeToCategory(knowledgeTitle, categoryName);
    }
}

// 缩放
function zoom(factor) {
    scale *= factor;
    scale = Math.max(0.5, Math.min(2, scale));
    renderGraph();
}

function resetView() {
    scale = 1;
    canvasOffset = { x: 0, y: 0 };
    renderGraph();
}

// 连接模式
function toggleConnectMode() {
    connectMode = !connectMode;
    connectionStart = null;
    document.getElementById('connectModeBtn').classList.toggle('active', connectMode);
    
    if (connectMode) {
        showToast('连接模式：点击【未分类】中的两个知识项创建关联');
        // 自动选中未分类
        selectedCategory = '未分类';
    } else {
        showToast('连接模式已关闭');
        selectedCategory = null;
    }
}

// 创建连接
function createConnection(from, to) {
    connectionStart = null;
    connectMode = false;
    document.getElementById('connectModeBtn').classList.remove('active');
    
    // 显示连接设置模态框
    document.getElementById('connectionInfo').textContent = `从 "${from}" 到 "${to}"`;
    document.getElementById('relationTypeSelect').value = '关联';
    document.getElementById('relationDescription').value = '';
    openModal('addConnectionModal');
    
    // 临时保存连接信息
    window.tempConnection = { from, to };
}

// 保存连接
async function saveConnection() {
    const type = document.getElementById('relationTypeSelect').value;
    const description = document.getElementById('relationDescription').value;
    
    if (!window.tempConnection) return;
    
    try {
        const response = await fetch('/api/knowledge/connections', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                from: window.tempConnection.from,
                to: window.tempConnection.to,
                type: type,
                description: description
            })
        });
        
        const data = await response.json();
        if (data.success) {
            showToast('连接创建成功');
            closeModal('addConnectionModal');
            loadKnowledgeGraph();
        } else {
            showToast(data.error || '创建失败', 'error');
        }
    } catch (error) {
        showToast('创建失败', 'error');
    }
}

// 创建分类
async function createCategory() {
    const name = document.getElementById('categoryNameInput').value.trim();
    const color = document.getElementById('selectedColor').value;
    
    if (!name) {
        showToast('请输入分类名称', 'error');
        return;
    }
    
    try {
        const response = await fetch('/api/knowledge/categories', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, color })
        });
        
        const data = await response.json();
        if (data.success) {
            showToast('分类创建成功');
            closeModal('addCategoryModal');
            document.getElementById('categoryNameInput').value = '';
            loadKnowledgeGraph();
        } else {
            showToast(data.error || '创建失败', 'error');
        }
    } catch (error) {
        showToast('创建失败', 'error');
    }
}

// 删除分类
async function deleteCategory(categoryName) {
    if (!confirm(`确定要删除分类"${categoryName}"吗？其中的知识将移至"未分类"`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/knowledge/categories/${encodeURIComponent(categoryName)}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        if (data.success) {
            showToast('删除成功');
            await loadKnowledgeGraph();
            await loadKnowledgeData();  // 重新加载知识数据
        } else {
            showToast(data.error || '删除失败', 'error');
        }
    } catch (error) {
        showToast('删除失败', 'error');
    }
}

// 移动知识到分类
async function moveKnowledgeToCategory(knowledgeTitle, categoryName) {
    try {
        const response = await fetch('/api/knowledge/move', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                knowledge: knowledgeTitle,
                category: categoryName
            })
        });
        
        const data = await response.json();
        if (data.success) {
            showToast(`已移动到"${categoryName}"`);
            await loadKnowledgeGraph();
            await loadKnowledgeData();  // 重新加载知识数据
        } else {
            showToast(data.error || '移动失败', 'error');
        }
    } catch (error) {
        showToast('移动失败', 'error');
    }
}

// 保存分类位置
async function saveCategoryPosition() {
    try {
        const positions = {};
        Object.entries(categories).forEach(([name, cat]) => {
            positions[name] = cat.position;
        });
        
        await fetch('/api/knowledge/graph/positions', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ positions })
        });
    } catch (error) {
        console.error('保存位置失败:', error);
    }
}

// AI整理
async function aiOrganize() {
    if (!confirm('AI将根据知识内容自动创建分类并整理知识，是否继续？')) {
        return;
    }
    
    showToast('AI正在分析中，请稍候...');
    document.getElementById('aiOrganizeBtn').disabled = true;
    
    try {
        const response = await fetch('/api/knowledge/ai/organize', {
            method: 'POST'
        });
        
        const data = await response.json();
        if (data.success) {
            showToast('AI分析完成！');
            // 显示AI建议结果
            const detailContent = document.getElementById('detailContent');
            detailContent.innerHTML = `
                <div style="padding: 20px;">
                    <h3 style="margin-bottom: 16px; color: #667eea;">AI整理建议</h3>
                    <div style="white-space: pre-wrap; line-height: 1.6;">${data.suggestion || data.message}</div>
                </div>
            `;
        } else {
            showToast(data.error || 'AI整理失败', 'error');
        }
    } catch (error) {
        showToast('AI整理失败', 'error');
    } finally {
        document.getElementById('aiOrganizeBtn').disabled = false;
    }
}

// AI生成索引
async function aiGenerateIndex() {
    const selected = selectedCategory;
    if (!selected) {
        showToast('请先选择一个分类', 'error');
        return;
    }
    
    showToast('AI正在生成索引，请稍候...');
    document.getElementById('aiIndexBtn').disabled = true;
    
    try {
        const response = await fetch('/api/knowledge/ai/index', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ category: selected })
        });
        
        const data = await response.json();
        if (data.success) {
            showToast('索引生成完成！');
            // 显示索引内容
            const detailContent = document.getElementById('detailContent');
            detailContent.innerHTML = `
                <div style="padding: 20px;">
                    <h3 style="margin-bottom: 16px; color: #667eea;">${selected} - 分类索引</h3>
                    <div style="white-space: pre-wrap; line-height: 1.6;">${data.index}</div>
                </div>
            `;
        } else {
            showToast(data.error || '生成失败', 'error');
        }
    } catch (error) {
        showToast('生成失败', 'error');
    } finally {
        document.getElementById('aiIndexBtn').disabled = false;
    }
}

// 辅助函数
function findKnowledge(title) {
    let found = knowledgeData.basis.find(k => k.title === title);
    if (!found) {
        found = knowledgeData.short.find(k => k.title === title);
    }
    return found;
}

function findCategoryByKnowledge(knowledgeTitle) {
    for (const [name, category] of Object.entries(categories)) {
        if (category.knowledge_ids.includes(knowledgeTitle)) {
            return name;
        }
    }
    return null;
}

function selectCategory(categoryName) {
    selectedCategory = categoryName;
    document.querySelectorAll('.category-card').forEach(card => {
        card.classList.remove('selected');
    });
    document.querySelector(`[data-category="${categoryName}"]`).classList.add('selected');
    showCategoryDetail(categoryName);
}

function showKnowledgeDetail(knowledge) {
    document.getElementById('detailTitle').textContent = knowledge.title;
    document.getElementById('detailContent').innerHTML = marked.parse(knowledge.content);
}

function showCategoryDetail(categoryName, indexContent = null) {
    const category = categories[categoryName];
    let html = `
        <h4 style="margin-bottom: 16px;">${categoryName}</h4>
        <p style="color: #6b7280; margin-bottom: 16px;">包含 ${category.knowledge_ids.length} 个知识</p>
    `;
    
    if (indexContent) {
        html += `<div style="margin-top: 20px; padding: 16px; background: #f9fafb; border-radius: 8px;">
            ${marked.parse(indexContent)}
        </div>`;
    }
    
    document.getElementById('detailTitle').textContent = '分类详情';
    document.getElementById('detailContent').innerHTML = html;
}

function closeDetailPanel() {
    document.getElementById('detailPanel').style.display = 'none';
}

function openModal(modalId) {
    document.getElementById(modalId).classList.add('active');
}

function closeModal(modalId) {
    document.getElementById(modalId).classList.remove('active');
}

function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.style.cssText = `
        position: fixed;
        top: 80px;
        right: 20px;
        background: ${type === 'error' ? '#ef4444' : '#10b981'};
        color: white;
        padding: 12px 20px;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        z-index: 10000;
        animation: slideIn 0.3s ease;
    `;
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

