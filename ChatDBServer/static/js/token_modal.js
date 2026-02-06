// Token模态窗口相关函数

// 打开模态窗口
function openTokenModal() {
    const modal = document.getElementById('tokenModal');
    if (modal) {
        modal.classList.add('active');
        loadTokenLogs();
    }
}

// 关闭模态窗口
function closeTokenModal() {
    const modal = document.getElementById('tokenModal');
    if (modal) {
        modal.classList.remove('active');
    }
}

// 加载Token日志
async function loadTokenLogs() {
    const tbody = document.getElementById('modalLogsBody');
    if (!tbody) return;
    
    tbody.innerHTML = '<tr><td colspan="6" style="text-align: center;"><div class="loading-spinner"></div> 加载中...</td></tr>';
    
    try {
        const response = await fetch('/api/token_logs');
        const data = await response.json();
        
        if (data.success) {
            renderTokenLogs(data.logs);
            calculateTokenStats(data.logs);
        } else {
            tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: red;">${data.error || '加载失败'}</td></tr>`;
        }
    } catch (error) {
        console.error('加载日志失败:', error);
        tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: red;">网络错误: ${error.message}</td></tr>`;
    }
}

// 渲染Token日志表格
function renderTokenLogs(logs) {
    const tbody = document.getElementById('modalLogsBody');
    if (!tbody) return;
    
    tbody.innerHTML = '';
    
    if (!logs || logs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align: center;">暂无记录</td></tr>';
        return;
    }
    
    logs.forEach(log => {
        const tr = document.createElement('tr');
        
        // 确定动作类型样式
        let actionClass = 'action-badge';
        if (log.action.includes('tool')) actionClass += ' tool';
        else if (log.action.includes('web')) actionClass += ' search';
        else actionClass += ' chat';
        
        tr.innerHTML = `
            <td>${log.timestamp.split(' ').join('<br>')}</td>
            <td>
                <div style="font-weight: 500;">${escapeHtml(log.conversation_title || '未命名对话')}</div>
                <div style="font-size: 11px; color: #9ca3af; font-family: monospace;">${log.conversation_id}</div>
            </td>
            <td><span class="${actionClass}">${log.action}</span></td>
            <td>${log.input_tokens.toLocaleString()}</td>
            <td>${log.output_tokens.toLocaleString()}</td>
            <td style="font-weight: bold;">${log.total_tokens.toLocaleString()}</td>
        `;
        tbody.appendChild(tr);
    });
}

// 计算并显示统计数据
function calculateTokenStats(logs) {
    let total = 0;
    let today = 0;
    
    // 获取当前本地日期 YYYY-MM-DD
    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    const todayStr = `${year}-${month}-${day}`;
    
    if (logs && logs.length > 0) {
        logs.forEach(log => {
            const tokenCount = log.total_tokens || 0;
            total += tokenCount;
            // 匹配日志中的日期部分
            if (log.timestamp && log.timestamp.startsWith(todayStr)) {
                today += tokenCount;
            }
        });
    }
    
    const elTotal = document.getElementById('modalTotalTokens');
    const elToday = document.getElementById('modalTodayTokens');
    const elRounds = document.getElementById('modalTotalRounds');
    
    if (elTotal) elTotal.textContent = total.toLocaleString();
    if (elToday) elToday.textContent = today.toLocaleString();
    if (elRounds) elRounds.textContent = (logs ? logs.length : 0).toLocaleString();
}