// 知识图谱 - 节点网络可视化
// 全局变量
let canvas, ctx, overlay;
let categories = {};  // 分类节点
let connections = [];  // 知识间连接
let knowledgeData = { basis: [], short: [] };
let knowledgeNodes = {};  // 知识节点位置 {title: {x, y, category}}
let currentView = 'basis';

// 交互状态
let isDraggingCanvas = false;
let isDraggingNode = false;
let draggedNode = null;
let draggedNodeType = null;
let dragOffset = { x: 0, y: 0 };
let canvasOffset = { x: 0, y: 0 };
let scale = 1;
let lastMouseX = 0, lastMouseY = 0;

// Grid Snapping Config for "Dify Mode"
const GRID_COL_WIDTH = 250;
const GRID_ROW_HEIGHT = 60;
const GRID_HEADER_HEIGHT = 100;
const GRID_GAP_X = 50;

// 连接模式
let connectMode = false;
let connectionStart = null;
let connectionStartType = null;  // 'category' or 'knowledge'

// 选中状态
let selectedNode = null;
let selectedNodeType = null;
let disconnectButtons = [];

// 右键菜单
let contextMenu = null;
let contextMenuTarget = null;
let contextMenuTargetType = null;

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    canvas = document.getElementById('graphCanvas');
    ctx = canvas.getContext('2d');
    overlay = document.getElementById('canvasOverlay');
    contextMenu = document.getElementById('contextMenu');
    
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);
    
    setupEventListeners();
    loadKnowledgeGraph();
    loadKnowledgeData();
    
    // 右键菜单点击处理
    contextMenu.addEventListener('click', (e) => {
        const editItem = e.target.closest('#ctxEditItem');
        const deleteItem = e.target.closest('#ctxDeleteItem');
        
        if (editItem) {
            console.log('点击了编辑按钮');
            handleContextMenuEdit();
            e.stopPropagation();
        } else if (deleteItem) {
            console.log('点击了删除按钮');
            handleContextMenuDelete();
            e.stopPropagation();
        }
    });
    
    // 全局点击关闭右键菜单
    document.addEventListener('click', (e) => {
        if (!e.target.closest('#contextMenu')) {
            hideContextMenu();
        }
    });
    
    document.addEventListener('contextmenu', (e) => {
        if (!e.target.closest('.category-node') && !e.target.closest('.knowledge-node')) {
            hideContextMenu();
        }
    });
});

function resizeCanvas() {
    canvas.width = canvas.offsetWidth;
    canvas.height = canvas.offsetHeight;
    draw();
}

// 设置事件监听
function setupEventListeners() {
    // 工具栏
    const addCategoryBtn = document.getElementById('addCategoryBtn');
    if (addCategoryBtn) addCategoryBtn.addEventListener('click', () => openModal('categoryModal')); // Changed ID to match new HTML
    
    const connectBtn = document.getElementById('connectModeBtn');
    if (connectBtn) connectBtn.addEventListener('click', toggleConnectMode);

    const aiBtn = document.getElementById('aiOrganizeBtn');
    if (aiBtn) aiBtn.addEventListener('click', aiOrganize);

    const autoLayoutBtn = document.getElementById('autoLayoutBtn');
    if (autoLayoutBtn) autoLayoutBtn.addEventListener('click', autoLayout);

    // Save Layout Button (New)
    const saveBtn = document.getElementById('saveLayoutBtn');
    if (saveBtn) saveBtn.addEventListener('click', () => {
         // Implement save logic call
         saveKnowledgeGraph();
    });

    // 知识库标签
    document.querySelectorAll('.knowledge-tabs .tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.knowledge-tabs .tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentView = btn.dataset.type;
            renderKnowledgeList();
        });
    });
    
    // 画布控制
    const zoomInBtn = document.getElementById('zoomInBtn');
    if (zoomInBtn) zoomInBtn.addEventListener('click', () => zoom(1.2));

    const zoomOutBtn = document.getElementById('zoomOutBtn');
    if (zoomOutBtn) zoomOutBtn.addEventListener('click', () => zoom(0.8));

    // Fix resetViewBtn ID mismatch (resetZoomBtn in HTML)
    const resetBtn = document.getElementById('resetViewBtn') || document.getElementById('resetZoomBtn');
    if (resetBtn) resetBtn.addEventListener('click', resetView);
    
    // 画布事件- 确保canvas存在
    if (canvas) {
        canvas.addEventListener('mousedown', onCanvasMouseDown);
        canvas.addEventListener('mousemove', onCanvasMouseMove);
        canvas.addEventListener('mouseup', onCanvasMouseUp);
        canvas.addEventListener('wheel', onCanvasWheel);
    }
    
    // 全局mouseup确保拖动正确结束
    document.addEventListener('mouseup', onCanvasMouseUp);
    document.addEventListener('mousemove', onCanvasMouseMove);
    
    // 搜索
    document.getElementById('searchInput').addEventListener('input', (e) => {
        filterKnowledgeList(e.target.value.toLowerCase());
    });
    
    // 颜色选择器（需要在模态框打开后初始化）
    document.addEventListener('click', (e) => {
        if (e.target.classList.contains('color-btn')) {
            document.querySelectorAll('.color-btn').forEach(b => b.classList.remove('selected'));
            e.target.classList.add('selected');
            document.getElementById('selectedColor').value = e.target.dataset.color;
        }
    });
    
    // 编辑颜色选择器
    document.addEventListener('click', (e) => {
        if (e.target.classList.contains('edit-color-btn')) {
            document.querySelectorAll('.edit-color-btn').forEach(b => b.classList.remove('selected'));
            e.target.classList.add('selected');
            document.getElementById('editSelectedColor').value = e.target.dataset.color;
        }
    });
}

// 加载知识图谱
async function loadKnowledgeGraph() {
    try {
        const response = await fetch('/api/knowledge/graph');
        const data = await response.json();
        
        if (data.success) {
            categories = data.graph.categories;
            connections = data.graph.connections;
            knowledgeNodes = data.graph.knowledge_nodes || {};
            
            // 初始化知识节点位置
            Object.entries(categories).forEach(([catName, category]) => {
                category.knowledge_ids.forEach((kid, idx) => {
                    if (!knowledgeNodes[kid]) {
                        const angle = (idx / Math.max(category.knowledge_ids.length, 1)) * 2 * Math.PI;
                        const radius = 250;
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
        console.error('加载失败:', error);
    }
}

// 加载知识数据
async function loadKnowledgeData() {
    try {
        const [basisRes, shortRes] = await Promise.all([
            fetch('/api/knowledge/basis'),
            fetch('/api/knowledge/short')
        ]);
        
        const [basisData, shortData] = await Promise.all([
            basisRes.json(),
            shortRes.json()
        ]);
        
        if (basisData.success) knowledgeData.basis = basisData.knowledge;
        if (shortData.success) knowledgeData.short = shortData.memories;
        
        renderKnowledgeList();
    } catch (error) {
        console.error('加载知识数据失败:', error);
    }
}

// 渲染知识列表（左侧面板）
function renderKnowledgeList() {
    const container = document.getElementById('unclassifiedList');
    container.innerHTML = '';
    
    const data = currentView === 'basis' ? knowledgeData.basis : knowledgeData.short;
    
    data.forEach(item => {
        const itemEl = document.createElement('div');
        itemEl.className = 'knowledge-item';
        const displayText = item.content || item.title;
        // 只显示标题，截断长文本
        itemEl.textContent = displayText.length > 30 ? displayText.substring(0, 28) + '...' : displayText;
        itemEl.title = displayText;  // 完整内容作为tooltip
        
        itemEl.addEventListener('click', () => {
            // IMPORTANT: 对于基础知识，通常title是唯一的标识
            // 对于短期记忆，可能title和content是一样的，或者content才是唯一可见的
            // 为了查找方便，我们应该传递能够唯一标识该条目的字段
            // 基础知识有title字段，短期记忆也有title(memory)和content
            
            // 修复查找逻辑：如果currentView是basis，传title；如果是short，传content或title
            // 这里的displayText虽然是显示用的，但也通过它去反查
            
            // 为了修复无法展示详细的问题，我们直接传递原始对象的title字段（如果是基础知识）
            // 或者 item.content (如果是短期记忆)
            
            let queryKey = displayText;
            if (currentView === 'basis' && item.title) {
                queryKey = item.title;
            } else if (currentView === 'short') {
                queryKey = item.content || item.title;
            }

            showKnowledgeDetailByTitle(queryKey);
        });
        
        container.appendChild(itemEl);
    });
}

function filterKnowledgeList(query) {
    const items = document.querySelectorAll('.knowledge-item');
    items.forEach(item => {
        item.style.display = item.textContent.toLowerCase().includes(query) ? 'block' : 'none';
    });
}

// 渲染图谱
function renderGraph() {
    overlay.innerHTML = '';
    disconnectButtons = [];
    
    draw();
    
    // 创建分类节点（跳过"未分类"）
    Object.entries(categories).forEach(([name, category]) => {
        if (name !== '未分类') {
            createCategoryNode(name, category);
        }
    });
    
    // 创建知识节点
    Object.entries(knowledgeNodes).forEach(([title, node]) => {
        createKnowledgeNode(title, node);
    });
}

// 创建分类节点
function createCategoryNode(name, category) {
    const node = document.createElement('div');
    node.className = 'category-node';
    node.dataset.category = name;
    
    const x = (category.position.x + canvasOffset.x) * scale;
    const y = (category.position.y + canvasOffset.y) * scale;
    node.style.left = x + 'px';
    node.style.top = y + 'px';
    // Clean Design: Use color as border accent only
    node.style.borderTop = `3px solid ${category.color || '#333'}`;
    node.style.transform = `translate(-50%, -50%) scale(${scale})`;
    
    if (selectedNode === name && selectedNodeType === 'category') {
        node.classList.add('selected');
    }
    
    const count = (category.knowledge_ids || []).length;
    node.innerHTML = `
        <div class="node-title">${name}</div>
        <div class="node-count">${count}</div>
    `;
    
    node.addEventListener('mousedown', (e) => {
        e.stopPropagation();
        startDragNode(e, 'category', name);
    });
    
    node.addEventListener('dblclick', (e) => {
        e.stopPropagation();
        handleNodeDoubleClick('category', name);
    });
    
    node.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        e.stopPropagation();
        showContextMenu(e, 'category', name);
    });
    
    overlay.appendChild(node);
}

// 创建知识节点
function createKnowledgeNode(title, node) {
    const el = document.createElement('div');
    el.className = 'knowledge-node';
    el.dataset.knowledge = title;
    
    const x = (node.x + canvasOffset.x) * scale;
    const y = (node.y + canvasOffset.y) * scale;
    el.style.left = x + 'px';
    el.style.top = y + 'px';
    el.style.transform = `translate(-50%, -50%) scale(${scale})`;
    
    if (selectedNode === title && selectedNodeType === 'knowledge') {
        el.classList.add('selected');
    }
    
    const displayTitle = title.length > 20 ? title.substring(0, 18) + '...' : title;
    el.innerHTML = `<div class="node-title">${displayTitle}</div>`;
    el.title = title;
    
    el.addEventListener('mousedown', (e) => {
        e.stopPropagation();
        startDragNode(e, 'knowledge', title);
    });
    
    el.addEventListener('dblclick', (e) => {
        e.stopPropagation();
        handleNodeDoubleClick('knowledge', title);
    });
    
    el.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        e.stopPropagation();
        showContextMenu(e, 'knowledge', title);
    });

    // el.addEventListener('click', (e) => {
    //     // 只有非拖拽产生的点击才显示详情
    //     if (!isDraggingCanvas && !isDraggingNode) {
    //         e.stopPropagation();
    //         showKnowledgeDetailByTitle(title);
    //     }
    // });
    
    overlay.appendChild(el);
}

// 绘制所有连接
function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    disconnectButtons = [];
    
    // 1. 分类到知识的归属连接
    Object.entries(categories).forEach(([catName, category]) => {
        // 跳过"未分类"，让其中的知识点作为独立分散的节点
        if (catName === '未分类') {
            return;
        }
        
        category.knowledge_ids.forEach(kid => {
            if (knowledgeNodes[kid]) {
                const catPos = category.position;
                const kidPos = knowledgeNodes[kid];
                
                const x1 = (catPos.x + canvasOffset.x) * scale;
                const y1 = (catPos.y + canvasOffset.y) * scale;
                const x2 = (kidPos.x + canvasOffset.x) * scale;
                const y2 = (kidPos.y + canvasOffset.y) * scale;
                
                const isSelected = selectedNode === kid && selectedNodeType === 'knowledge';
                drawCategoryConnection(x1, y1, x2, y2, category.color, isSelected, kid, catName);
            }
        });
    });
    
    // 2. 知识间依赖连接
    connections.forEach(conn => {
        if (knowledgeNodes[conn.from] && knowledgeNodes[conn.to]) {
            const fromPos = knowledgeNodes[conn.from];
            const toPos = knowledgeNodes[conn.to];
            
            const x1 = (fromPos.x + canvasOffset.x) * scale;
            const y1 = (fromPos.y + canvasOffset.y) * scale;
            const x2 = (toPos.x + canvasOffset.x) * scale;
            const y2 = (toPos.y + canvasOffset.y) * scale;
            
            // 判断是否选中了相关知识节点
            const isSelected = (selectedNode === conn.from || selectedNode === conn.to) && selectedNodeType === 'knowledge';
            
            drawKnowledgeConnection(x1, y1, x2, y2, conn.type, conn.id, isSelected, conn.from, conn.to);
        }
    });
}

// 绘制分类归属连接
function drawCategoryConnection(x1, y1, x2, y2, color, isSelected, knowledgeTitle, categoryName) {
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = isSelected ? 3 : 2;
    
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();
    
    // 选中时显示断开按钮
    if (isSelected) {
        const midX = (x1 + x2) / 2;
        const midY = (y1 + y2) / 2;
        
        ctx.fillStyle = '#ef4444';
        ctx.beginPath();
        ctx.arc(midX, midY, 15, 0, 2 * Math.PI);
        ctx.fill();
        
        ctx.strokeStyle = 'white';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(midX - 6, midY - 6);
        ctx.lineTo(midX + 6, midY + 6);
        ctx.moveTo(midX + 6, midY - 6);
        ctx.lineTo(midX - 6, midY + 6);
        ctx.stroke();
        
        disconnectButtons.push({
            x: midX, y: midY, radius: 15,
            knowledge: knowledgeTitle,
            category: categoryName
        });
    }
    
    ctx.restore();
}

// 绘制知识依赖连接
function drawKnowledgeConnection(x1, y1, x2, y2, type, connId, isSelected, fromKnowledge, toKnowledge) {
    ctx.save();
    
    const styles = {
        '关联': { color: '#667eea', dash: [] },
        '依赖': { color: '#ef4444', dash: [] },
        '扩展': { color: '#10b981', dash: [] },
        '对比': { color: '#f59e0b', dash: [5, 5] },
        '补充': { color: '#8b5cf6', dash: [] }
    };
    
    const style = styles[type] || styles['关联'];
    ctx.strokeStyle = style.color;
    ctx.lineWidth = isSelected ? 3 : 2;
    ctx.setLineDash(style.dash);
    
    // 曲线
    const dx = x2 - x1;
    const dy = y2 - y1;
    const cp1x = x1 + dx / 3;
    const cp1y = y1 - 50;
    const cp2x = x2 - dx / 3;
    const cp2y = y2 - 50;
    
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, x2, y2);
    ctx.stroke();
    
    // 箭头
    const angle = Math.atan2(y2 - cp2y, x2 - cp2x);
    ctx.beginPath();
    ctx.moveTo(x2, y2);
    ctx.lineTo(x2 - 10 * Math.cos(angle - Math.PI / 6), y2 - 10 * Math.sin(angle - Math.PI / 6));
    ctx.moveTo(x2, y2);
    ctx.lineTo(x2 - 10 * Math.cos(angle + Math.PI / 6), y2 - 10 * Math.sin(angle + Math.PI / 6));
    ctx.stroke();
    
    // 如果选中，在连线中点显示断开按钮
    if (isSelected && connId) {
        const midX = (x1 + x2) / 2;
        const midY = (y1 + y2) / 2 - 25;  // 曲线中点略靠上
        
        // 绘制断开按钮背景
        ctx.fillStyle = '#f59e0b';
        ctx.beginPath();
        ctx.arc(midX, midY, 15, 0, 2 * Math.PI);
        ctx.fill();
        
        // 绘制X图标
        ctx.strokeStyle = 'white';
        ctx.lineWidth = 2;
        ctx.setLineDash([]);
        ctx.beginPath();
        ctx.moveTo(midX - 6, midY - 6);
        ctx.lineTo(midX + 6, midY + 6);
        ctx.moveTo(midX + 6, midY - 6);
        ctx.lineTo(midX - 6, midY + 6);
        ctx.stroke();
        
        disconnectButtons.push({
            x: midX, y: midY, radius: 15,
            type: 'connection',
            connectionId: connId,
            from: fromKnowledge,
            to: toKnowledge
        });
    }
    
    ctx.restore();
}

// 节点双击处理 - 进入连接模式
function handleNodeDoubleClick(type, name) {
    if (!connectMode) {
        // 进入连接模式
        connectMode = true;
        connectionStart = name;
        connectionStartType = type;
        selectedNode = name;
        selectedNodeType = type;
        document.getElementById('connectModeBtn').classList.add('active');
        renderGraph();
        showToast(`连接模式：双击目标节点建立连接`);
    } else if (connectionStart) {
        // 已在连接模式，建立连接
        if (type === 'category' && connectionStartType === 'knowledge') {
            // 知识连接到分类（重新归属）
            moveKnowledgeToCategory(connectionStart, name);
        } else if (type === 'knowledge' && connectionStartType === 'knowledge' && name !== connectionStart) {
            // 知识连接到知识（依赖关系）
            createConnection(connectionStart, name);
        } else {
            showToast('无效的连接', 'error');
        }
        // 连接完成，退出连接模式
        exitConnectMode();
    }
}

// 拖动节点
function startDragNode(e, type, name) {
    if (connectMode) return;
    
    e.preventDefault();  // 防止文本选中
    e.stopPropagation();
    
    isDraggingNode = true;
    draggedNode = name;
    draggedNodeType = type;
    
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;
    
    if (type === 'category') {
        const pos = categories[name].position;
        const x = (pos.x + canvasOffset.x) * scale;
        const y = (pos.y + canvasOffset.y) * scale;
        dragOffset.x = mouseX - x;
        dragOffset.y = mouseY - y;
    } else {
        const pos = knowledgeNodes[name];
        const x = (pos.x + canvasOffset.x) * scale;
        const y = (pos.y + canvasOffset.y) * scale;
        dragOffset.x = mouseX - x;
        dragOffset.y = mouseY - y;
    }
}

// 画布事件
function onCanvasMouseDown(e) {
    e.preventDefault();  // 防止文本选中
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;
    
    // 检查断开按钮
    let clickedDisconnect = false;
    for (const btn of disconnectButtons) {
        const dist = Math.sqrt((mouseX - btn.x) ** 2 + (mouseY - btn.y) ** 2);
        if (dist <= btn.radius) {
            clickedDisconnect = true;
            if (btn.type === 'connection') {
                // 断开知识依赖连接
                removeConnection(btn.connectionId);
            } else {
                // 断开分类归属连接
                disconnectKnowledge(btn.knowledge, btn.category);
            }
            return;
        }
    }
    
    // 点击空白处退出连接模式
    // 判断是否点到了节点（点到节点会被节点事件阻止，所以这里肯定是点到了空白或按钮等非节点区域）
    // 注意：节点是HTML元素，不属于canvas内容，mousedown在canvas上触发说明没点到HTML节点(因为节点阻止了冒泡/或应该阻止)
    // 检查是否在覆盖层上的节点 - 不行，事件已经在canvas层触发了。
    // 但是节点的mousedown有 e.stopPropagation()，所以如果canvas接收到mousedown，一定没点到节点
    
    if (connectMode && !clickedDisconnect) {
        exitConnectMode();
        return; // 退出连接模式时，不进行拖动操作
    }

    // 画布拖动
    if (!isDraggingNode) {
        isDraggingCanvas = true;
        lastMouseX = e.clientX;
        lastMouseY = e.clientY;
    }
}

function onCanvasMouseMove(e) {
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;
    
    if (isDraggingNode) {
        // Raw movement
        let newX = (mouseX - dragOffset.x) / scale - canvasOffset.x;
        let newY = (mouseY - dragOffset.y) / scale - canvasOffset.y;
        
        // Dify Style: Horizontal Lock for Knowledge Nodes (Can only drag up/down within column or switch columns)
        // Actually, Dify uses Kanban, so let's check nearest column
        
        // Find nearest Category Column
        let nearestCat = null;
        let minDist = Infinity;
        
        Object.entries(categories).forEach(([name, cat]) => {
            const dist = Math.abs(newX - cat.position.x);
            if(dist < minDist) {
                minDist = dist;
                nearestCat = name;
            }
        });

        // 磁吸效果: Sticky X
        if(minDist < 100 && nearestCat) {
             // Visual feedback for dropping into this category could be added here
        }

        if (draggedNodeType === 'category') {
            // Categories sort horizontally
             categories[draggedNode].position.x = newX;
             // Lock Y for categories header
             // categories[draggedNode].position.y = newY; 
        } else {
            knowledgeNodes[draggedNode].x = newX;
            knowledgeNodes[draggedNode].y = newY;
        }
        renderGraph();
    } else if (isDraggingCanvas) {
        const dx = e.clientX - lastMouseX;
        const dy = e.clientY - lastMouseY;
        canvasOffset.x += dx / scale;
        // Lock Y axis panning if desired for strict dashboard feel, but free pan is usually better
        canvasOffset.y += dy / scale;
        
        lastMouseX = e.clientX;
        lastMouseY = e.clientY;
        renderGraph();
    }
}

function onCanvasMouseUp(e) {
    if (isDraggingNode && draggedNode) {
        // Snap Logic on Drop
        if (draggedNodeType === 'knowledge') {
            // Find which category column we are hovering over
            let bestCat = null;
             // ... logic to find nearest column ...
            const nodeX = knowledgeNodes[draggedNode].x;
            
            let minDist = Infinity;
            Object.entries(categories).forEach(([name, cat]) => {
                const dist = Math.abs(nodeX - cat.position.x);
                if(dist < minDist) {
                    minDist = dist;
                    bestCat = name;
                }
            });
            
            // If close enough to a column, snap to it and reassign category
            if(bestCat && minDist < 150) {
                 const oldCat = knowledgeNodes[draggedNode].category;
                 if(oldCat !== bestCat) {
                     // Change Category
                     moveKnowledgeToCategory(draggedNode, bestCat);
                     // moveKnowledgeToCategory handles layout update
                 } else {
                     // Same category, just reorder?
                     // For now, just snap back to grid via autoLayout
                     autoLayout();
                 }
            }
        } else {
             // Category reordering logic could go here
             autoLayout();
        }
    }
    isDraggingCanvas = false;
    isDraggingNode = false;
    draggedNode = null;
    draggedNodeType = null;
}

function onCanvasWheel(e) {
    e.preventDefault();
    const delta = e.deltaY < 0 ? 1.1 : 0.9;
    zoom(delta);
}

function zoom(factor) {
    scale *= factor;
    scale = Math.max(0.3, Math.min(scale, 3));
    renderGraph();
}

function resetView() {
    scale = 1;
    canvasOffset = { x: 0, y: 0 };
    renderGraph();
}

// 切换连接模式
function toggleConnectMode() {
    if (connectMode) {
        exitConnectMode();
    } else {
        connectMode = true;
        document.getElementById('connectModeBtn').classList.add('active');
        showToast('连接模式：双击第一个节点开始，双击第二个节点完成连接');
    }
}

// 退出连接模式
function exitConnectMode() {
    connectMode = false;
    connectionStart = null;
    connectionStartType = null;
    selectedNode = null;
    selectedNodeType = null;
    document.getElementById('connectModeBtn').classList.remove('active');
    renderGraph();
    showToast('连接模式已关闭');
}

// API调用
function moveKnowledgeToCategory(knowledge, category) {
    // Optimistic Update
    const node = knowledgeNodes[knowledge];
    if(node) node.category = category;
    
    // Trigger Auto Layout immediately to snap into place (Dify Style)
    autoLayout(); 

    fetch('/api/knowledge/move', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ knowledge: knowledge, category })
    }).then(res => res.json()).then(data => {
        if (!data.success) {
            showToast(data.error || '移动失败', 'error');
            loadKnowledgeGraph(); // Revert on failure
        }
    });
}

async function disconnectKnowledge(knowledge, category) {
    if (!confirm(`确定断开【${knowledge}】与【${category}】的连接？`)) {
        return;
    }
    
    // 移动到未分类
    await moveKnowledgeToCategory(knowledge, '未分类');
    showToast('已断开连接');
}

async function removeConnection(connectionId) {
    if (!confirm('确定删除该依赖关系？')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/knowledge/connections/${connectionId}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        if (data.success) {
            showToast('已删除');
            loadKnowledgeGraph();
        } else {
            showToast(data.error, 'error');
        }
    } catch (error) {
        showToast('删除失败', 'error');
    }
}

async function createConnection(from, to) {
    document.getElementById('connectionInfo').textContent = `从 "${from}" 到 "${to}"`;
    document.getElementById('relationTypeSelect').value = '关联';
    document.getElementById('relationDescription').value = '';
    openModal('addConnectionModal');
    
    window.tempConnection = { from, to };
}

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
                type,
                description
            })
        });
        
        const data = await response.json();
        if (data.success) {
            showToast('连接已创建');
            closeModal('addConnectionModal');
            loadKnowledgeGraph();
        } else {
            showToast(data.error, 'error');
        }
    } catch (error) {
        showToast('创建失败', 'error');
    }
}

async function saveNodePosition(type, name) {
    if (type === 'category') {
        const pos = categories[name].position;
        await fetch('/api/knowledge/graph/positions', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ category: name, position: pos })
        });
    } else {
        const pos = knowledgeNodes[name];
        await fetch('/api/knowledge/nodes/positions', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: name, position: { x: pos.x, y: pos.y } })
        });
    }
}

// 分类管理
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
            body: JSON.stringify({
                name,
                color,
                position: { x: 100 + Object.keys(categories).length * 100, y: 100 }
            })
        });
        
        const data = await response.json();
        if (data.success) {
            showToast('分类已创建');
            closeModal('addCategoryModal');
            loadKnowledgeGraph();
        } else {
            showToast(data.error, 'error');
        }
    } catch (error) {
        showToast('创建失败', 'error');
    }
}

async function deleteCategory(name) {
    if (name === '未分类') {
        showToast('不能删除未分类', 'error');
        return;
    }
    
    if (!confirm(`确定删除分类【${name}】？其中的知识将移至未分类。`)) return;
    
    try {
        const response = await fetch(`/api/knowledge/categories/${encodeURIComponent(name)}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        if (data.success) {
            showToast('已删除');
            loadKnowledgeGraph();
        } else {
            showToast(data.error, 'error');
        }
    } catch (error) {
        showToast('删除失败', 'error');
    }
}

// AI功能
async function aiOrganize() {
    if (!confirm('AI将分析所有知识并提供分类建议，是否继续？')) return;
    
    showToast('AI分析中...');
    document.getElementById('aiOrganizeBtn').disabled = true;
    
    try {
        const response = await fetch('/api/knowledge/ai/organize', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            showToast('分析完成，正在刷新...');
            document.getElementById('detailContent').innerHTML = `
                <div style="padding: 20px;">
                    <h3 style="color: #667eea; margin-bottom: 16px;">AI分类建议</h3>
                    <div style="white-space: pre-wrap; line-height: 1.6;">${data.suggestion || data.message}</div>
                </div>
            `;
            // 自动刷新
            setTimeout(() => {
                loadKnowledgeGraph();
            }, 1000);
        } else {
            showToast(data.error || data.message, 'error');
        }
    } catch (error) {
        showToast('分析失败', 'error');
    } finally {
        document.getElementById('aiOrganizeBtn').disabled = false;
    }
}

async function aiOrganize() {
    // [TODO] Integration with LLM to categorize 'Unclassified' items
    showToast('AI Analyzing... (Simulation)', 'info');
    setTimeout(() => {
        showToast('AI suggestion: Move "Python Utils" to "Development"', 'success');
    }, 1500);
}

function autoLayout() {
    showToast('Applying Auto-Alignment...');
    
    const startX = 200;
    const startY = 150;
    const colWidth = 280;
    const rowGap = 70;
    const headerHeight = 100;
    
    // Sort categories (Unclassified last)
    const sortedCats = Object.keys(categories).sort((a,b) => {
        if (a === '未分类') return 1;
        if (b === '未分类') return -1;
        return a.localeCompare(b, 'zh-CN');
    });
    
    sortedCats.forEach((catName, colIndex) => {
        const catNode = categories[catName];
        
        // 1. Position Category Header
        // Arrange columns horizontally
        const catX = startX + colIndex * colWidth;
        const catY = startY;
        
        catNode.position = { x: catX, y: catY };
        
        // 2. Position Items in a Stack below header
        const knowledgeIds = catNode.knowledge_ids || [];
        
        // Sort items by name for cleaner look
        knowledgeIds.sort((a,b) => {
             const tA = (knowledgeNodes[a]?.title || "").toLowerCase();
             const tB = (knowledgeNodes[b]?.title || "").toLowerCase();
             return tA.localeCompare(tB);
        });

        knowledgeIds.forEach((kid, rowIndex) => {
            if (knowledgeNodes[kid]) {
                knowledgeNodes[kid].x = catX;
                knowledgeNodes[kid].y = catY + headerHeight + rowIndex * rowGap;
            }
        });
    });
    
    // Reset View to fit
    // resetView(); // Optional
    
    renderGraph();
    saveKnowledgeGraph();
    showToast('Layout Updated & Saved');
}

async function saveKnowledgeGraph() {
    // Prepare minimal payload for positions
    const catPositions = {};
    Object.entries(categories).forEach(([k, v]) => {
        catPositions[k] = v.position;
    });
    
    const nodePositions = {};
    Object.entries(knowledgeNodes).forEach(([k, v]) => {
        nodePositions[k] = {x: v.x, y: v.y};
    });

    try {
        // We can call the unified update or separate. 
        // Based on grep, we have /api/knowledge/graph/positions (PUT)
        const response = await fetch('/api/knowledge/graph/positions', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                categories: catPositions,
                nodes: nodePositions
            })
        });
        
        const res = await response.json();
        if(!res.success) {
            console.warn('Backend save warning:', res.message);
        }
    } catch (e) {
        console.error('Save failed:', e);
        showToast('Saving layout failed', 'error');
    }
}


// async function aiGenerateIndex() {
//     if (!selectedNode || selectedNodeType !== 'category') {
//         showToast('请先选择一个分类节点', 'error');
//         return;
//     }
    
//     showToast('AI生成中...');
//     // document.getElementById('aiIndexBtn').disabled = true;
    
//     try {
//         const response = await fetch('/api/knowledge/ai/index', {
//             method: 'POST',
//             headers: { 'Content-Type': 'application/json' },
//             body: JSON.stringify({ category: selectedNode })
//         });
        
//         const data = await response.json();
//         if (data.success) {
//             showToast('生成完成');
//             document.getElementById('detailContent').innerHTML = `
//                 <div style="padding: 20px;">
//                     <h3 style="color: #667eea; margin-bottom: 16px;">${selectedNode} - 索引</h3>
//                     <div style="white-space: pre-wrap; line-height: 1.6;">${data.index}</div>
//                 </div>
//             `;
//         } else {
//             showToast(data.error, 'error');
//         }
//     } catch (error) {
//         showToast('生成失败', 'error');
//     } finally {
//         // document.getElementById('aiIndexBtn').disabled = false;
//     }
// }

// 工具函数
function showKnowledgeDetailByTitle(title) {
    const knowledge = knowledgeData.basis.find(k => k.title === title) || 
                     knowledgeData.short.find(m => (m.content || m.title) === title);
    
    if (knowledge) {
        const content = knowledge.content || knowledge.title;
        const panel = document.getElementById('detailPanel');
        panel.style.display = 'flex';
        
        document.getElementById('detailTitle').textContent = title;
        document.getElementById('detailContent').innerHTML = `
            <div style="padding: 20px;" class="markdown-body">
                ${marked.parse(content)}
            </div>
        `;
        
        // 侧边栏弹出导致了容器宽度变化，这里需要延迟触发重新计算画布尺寸
        setTimeout(() => resizeCanvas(), 300);
    }
}

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;
    toast.style.cssText = `
        position: fixed;
        top: 80px;
        left: 50%;
        transform: translateX(-50%);
        background: ${type === 'error' ? '#ef4444' : '#667eea'};
        color: white;
        padding: 12px 24px;
        border-radius: 8px;
        z-index: 10000;
        animation: slideDown 0.3s ease;
    `;
    
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

function openModal(id) {
    const el = document.getElementById(id);
    if (el) {
        el.classList.add('active'); // Use class for transitions
        // Fallback for old style if needed, but 'active' handles visibility now
        el.style.display = 'flex'; 
    }
}

function closeModal(id) {
    const el = document.getElementById(id);
    if (el) {
        el.classList.remove('active');
        // Delay hiding display to allow transition, or keep it flex if using opacity
        setTimeout(() => el.style.display = 'none', 200);
    }
}

function closeDetailPanel() {
    const panel = document.getElementById('detailPanel');
    if (panel) {
        panel.classList.remove('active');
    }
    // No need to resize canvas usually if it's an overlay
}

// 右键菜单
function showContextMenu(e, type, name) {
    contextMenuTarget = name;
    contextMenuTargetType = type;
    
    contextMenu.style.display = 'block';
    contextMenu.style.left = e.pageX + 'px';
    contextMenu.style.top = e.pageY + 'px';
}

function hideContextMenu() {
    if (contextMenu) {
        contextMenu.style.display = 'none';
        contextMenuTarget = null;
        contextMenuTargetType = null;
    }
}

async function handleContextMenuEdit() {
    // 先保存目标信息，再隐藏菜单
    const target = contextMenuTarget;
    const targetType = contextMenuTargetType;
    
    hideContextMenu();
    
    if (!target || !targetType) return;
    
    if (targetType === 'category') {
        // 编辑分类
        openEditCategoryModal(target);
    } else if (targetType === 'knowledge') {
        // 编辑知识点
        openEditKnowledgeModal(target);
    }
}

async function handleContextMenuDelete() {
    // 先保存目标信息，再隐藏菜单
    const target = contextMenuTarget;
    const targetType = contextMenuTargetType;
    
    hideContextMenu();
    
    if (!target || !targetType) return;
    
    if (targetType === 'category') {
        // 删除分类
        await deleteCategory(target);
    } else if (targetType === 'knowledge') {
        // 删除知识点
        await deleteKnowledge(target);
    }
}

async function deleteKnowledge(title) {
    if (!confirm(`确定删除知识点【${title}】？此操作不可恢复。`)) {
        return;
    }
    
    try {
        // 先尝试从基础知识删除
        let response = await fetch(`/api/knowledge/basis/${encodeURIComponent(title)}`, {
            method: 'DELETE'
        });
        
        let data = await response.json();
        
        // 如果基础知识中没有，尝试从短期记忆删除
        if (!data.success) {
            response = await fetch(`/api/knowledge/short/${encodeURIComponent(title)}`, {
                method: 'DELETE'
            });
            data = await response.json();
        }
        
        if (data.success) {
            showToast('已删除知识点');
            loadKnowledgeGraph();
            loadKnowledgeData();
        } else {
            showToast(data.error || '删除失败', 'error');
        }
    } catch (error) {
        showToast('删除失败', 'error');
        console.error(error);
    }
}

// 编辑分类
function openEditCategoryModal(categoryName) {
    const category = categories[categoryName];
    if (!category) return;
    
    document.getElementById('editCategoryNameInput').value = categoryName;
    document.getElementById('editCategoryOldName').value = categoryName;
    document.getElementById('editSelectedColor').value = category.color;
    
    // 设置当前颜色按钮为选中状态
    document.querySelectorAll('.edit-color-btn').forEach(btn => {
        if (btn.dataset.color === category.color) {
            btn.classList.add('selected');
        } else {
            btn.classList.remove('selected');
        }
    });
    
    openModal('editCategoryModal');
}

async function updateCategory() {
    const oldName = document.getElementById('editCategoryOldName').value;
    const newName = document.getElementById('editCategoryNameInput').value.trim();
    const color = document.getElementById('editSelectedColor').value;
    
    if (!newName) {
        showToast('请输入分类名称', 'error');
        return;
    }
    
    try {
        const response = await fetch(`/api/knowledge/categories/${encodeURIComponent(oldName)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: newName, color })
        });
        
        const data = await response.json();
        if (data.success) {
            showToast('已更新分类');
            closeModal('editCategoryModal');
            loadKnowledgeGraph();
        } else {
            showToast(data.error || '更新失败', 'error');
        }
    } catch (error) {
        showToast('更新失败', 'error');
        console.error(error);
    }
}

// 编辑知识
function openEditKnowledgeModal(title) {
    // 查找知识在哪个类型中
    let knowledge = knowledgeData.basis.find(k => k.title === title);
    let type = 'basis';
    
    if (!knowledge) {
        knowledge = knowledgeData.short.find(m => {
            const displayText = m.content || m.title;
            return displayText === title;
        });
        type = 'short';
    }
    
    if (!knowledge) {
        showToast('找不到知识', 'error');
        return;
    }
    
    const displayTitle = knowledge.title || title;
    const content = knowledge.content || knowledge.title;
    
    document.getElementById('editKnowledgeTitleInput').value = displayTitle;
    document.getElementById('editKnowledgeContentInput').value = content;
    document.getElementById('editKnowledgeOldTitle').value = title;
    document.getElementById('editKnowledgeType').value = type;
    
    openModal('editKnowledgeModal');
}

async function updateKnowledge() {
    const oldTitle = document.getElementById('editKnowledgeOldTitle').value;
    const newTitle = document.getElementById('editKnowledgeTitleInput').value.trim();
    const content = document.getElementById('editKnowledgeContentInput').value.trim();
    const type = document.getElementById('editKnowledgeType').value;
    
    console.log('更新知识:', { oldTitle, newTitle, content, type });
    
    if (!newTitle || !content) {
        showToast('标题和内容不能为空', 'error');
        return;
    }
    
    try {
        const endpoint = type === 'basis' ? 'basis' : 'short';
        const url = `/api/knowledge/${endpoint}/${encodeURIComponent(oldTitle)}`;
        console.log('请求URL:', url);
        console.log('请求数据:', { title: newTitle, content });
        
        const response = await fetch(url, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: newTitle, content })
        });
        
        const data = await response.json();
        console.log('响应数据:', data);
        
        if (data.success) {
            showToast('已更新知识');
            closeModal('editKnowledgeModal');
            loadKnowledgeGraph();
            loadKnowledgeData();
        } else {
            console.error('更新失败:', data.error);
            showToast(data.error || '更新失败', 'error');
        }
    } catch (error) {
        console.error('请求异常:', error);
        showToast('更新失败: ' + error.message, 'error');
    }
}

// 全局函数（供HTML调用）
window.createCategory = createCategory;
window.saveConnection = saveConnection;
window.deleteCategory = deleteCategory;
window.closeModal = closeModal;
window.closeDetailPanel = closeDetailPanel;
window.updateCategory = updateCategory;
window.updateKnowledge = updateKnowledge;


// --- CHATDB PRO UI ADAPTER ---

document.addEventListener('DOMContentLoaded', () => {
    setupNewUI();
});

function setupNewUI() {
    // 1. Sidebar Toggle
    const toggleBtn = document.getElementById('sidebar-toggle');
    const sidebar = document.getElementById('sidebar');
    if (toggleBtn && sidebar) {
        toggleBtn.addEventListener('click', () => {
            sidebar.classList.toggle('collapsed');
            if (sidebar.classList.contains('collapsed')) {
                sidebar.style.transform = 'translateX(-100%)';
                // Also adjust main content margin if needed, but here it's flex
            } else {
                sidebar.style.transform = 'translateX(0)';
            }
        });
    }

    // 2. Tabs
    const tabs = document.querySelectorAll('.tab-btn');
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            tabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            
            const target = tab.dataset.tab;
            if (target === 'categories') {
                document.getElementById('categoryList').style.display = 'flex';
                document.getElementById('unclassifiedList').style.display = 'none';
            } else {
                document.getElementById('categoryList').style.display = 'none';
                document.getElementById('unclassifiedList').style.display = 'flex';
            }
        });
    });

    // 3. Search
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            const query = e.target.value.toLowerCase();
            filterKnowledgeList(query); // Calls original filter (needs update?)
        });
    }

    // 4. Zoom Controls
    document.getElementById('zoomInBtn').addEventListener('click', () => {
        scale *= 1.1;
        draw();
    });
    document.getElementById('zoomOutBtn').addEventListener('click', () => {
        scale *= 0.9;
        draw();
    });
    document.getElementById('resetZoomBtn').addEventListener('click', () => {
        scale = 1;
        canvasOffset = {x: 0, y: 0};
        draw();
    });
    
    // 5. Right Panel Close
    document.getElementById('closeDetailPanel').addEventListener('click', closeDetailPanel);
}

// Override filter to work on new list
function filterKnowledgeList(query) {
    const items = document.querySelectorAll('#unclassifiedList .knowledge-item, #categoryList .knowledge-item');
    items.forEach(item => {
        const text = item.textContent.toLowerCase();
        item.style.display = text.includes(query) ? 'flex' : 'none';
    });
}

// Override render call
// renderKnowledgeList is defined above (in append) or previously.
// I will append the NEW renderKnowledgeList definition here to ensure it wins.

function renderKnowledgeList() {
    const unclassifiedContainer = document.getElementById('unclassifiedList');
    const categoryContainer = document.getElementById('categoryList');
    
    if (unclassifiedContainer) unclassifiedContainer.innerHTML = '';
    if (categoryContainer) categoryContainer.innerHTML = '';
    
    // Render Knowledge Items (Use the current view data)
    const data = currentView === 'basis' ? knowledgeData.basis : knowledgeData.short;
    
    // Sort items?
    
    if (unclassifiedContainer) {
        data.forEach(item => {
            const itemEl = document.createElement('div');
            itemEl.className = 'knowledge-item';
            
            // Check if item is classified/connected (Optional optimization)
            const isClassified = false; // TODO: Check connections
            
            const displayText = item.content || item.title;
            // Truncate
             const truncateText = displayText.length > 30 ? displayText.substring(0, 28) + '...' : displayText;
            
            itemEl.innerHTML = `<span>${truncateText}</span>`;
            itemEl.title = displayText;
            itemEl.draggable = true; // Enable drag from sidebar
            
            // Add Drag Events
            itemEl.addEventListener('dragstart', (e) => {
                e.dataTransfer.setData('text/plain', JSON.stringify({
                    type: 'knowledge',
                    id: item.id || displayText, // Use title/content as ID if id missing
                    title: item.title,
                    content: item.content
                }));
                itemEl.classList.add('dragging');
            });
             itemEl.addEventListener('dragend', (e) => {
                itemEl.classList.remove('dragging');
            });

            itemEl.addEventListener('click', () => {
                let queryKey = displayText;
                if (currentView === 'basis' && item.title) {
                    queryKey = item.title;
                } else if (currentView === 'short') {
                    queryKey = item.content || item.title;
                }
                showKnowledgeDetailByTitle(queryKey);
            });
            
            unclassifiedContainer.appendChild(itemEl);
        });
    }

    // Render Categories List
    if (categoryContainer && categories) {
        Object.entries(categories).forEach(([name, cat]) => {
            const catEl = document.createElement('div');
            catEl.className = 'knowledge-item'; // Reuse style
            catEl.innerHTML = `<i class="fa-solid fa-folder" style="color:${cat.color}"></i> <span>${name}</span>`;
            
            catEl.addEventListener('click', () => {
                // Focus on category node
                // Assuming we have knowledgeNodes/categories coordinates
                const node = categories[name];
                if (node) {
                    // Pan to node
                    // canvasOffset.x = -node.position.x * scale + canvas.width / 2;
                    // canvasOffset.y = -node.position.y * scale + canvas.height / 2;
                    // draw();
                    showModal(name); // Or show details
                }
            });
            categoryContainer.appendChild(catEl);
        });
    }
}
