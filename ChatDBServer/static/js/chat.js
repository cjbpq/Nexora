// Global State
let currentConversationId = null;
let currentAbortController = null;
let isGenerating = false;
let shouldAutoScroll = true; // Auto-scroll control
let uploadedFileIds = []; // Uploaded files {id, name}

// DOM Elements
const els = {
    sidebar: document.getElementById('sidebar'),
    messagesContainer: document.getElementById('messagesContainer'),
    messageInput: document.getElementById('messageInput'),
    fileInput: document.getElementById('fileInput'),
    filePreviewArea: document.getElementById('filePreviewArea'),
    sendBtn: document.getElementById('sendBtn'),
    toggleSidebar: document.getElementById('toggleSidebar'),
    // New Model Selector
    modelSelectContainer: document.getElementById('modelSelectContainer'),
    currentModelDisplay: document.getElementById('currentModelDisplay'),
    modelOptions: document.getElementById('modelOptions'),
    // ...
    conversationList: document.getElementById('conversationList'),
    newChatBtn: document.getElementById('newChatBtn'),
    conversationTitle: document.getElementById('conversationTitle'),
    knowledgePanel: document.getElementById('knowledgePanel'),
    toggleKnowledgePanel: document.getElementById('toggleKnowledgePanel'),
    btnTogglePanel: document.getElementById('btnTogglePanel'), // Close button inside panel
    refreshKnowledgeBtn: document.getElementById('refreshKnowledgeBtn'),
    panelBasisList: document.getElementById('panelBasisKnowledgeList'),
    panelShortList: document.getElementById('panelShortMemoryList'),
    panelBasisCount: document.getElementById('panelBasisCount'),
    panelShortCount: document.getElementById('panelShortCount'),
    tokenDisplay: document.getElementById('tokenDisplay'),
    modalTotalTokens: document.getElementById('modalTotalTokens'),
    modalTodayTokens: document.getElementById('modalTodayTokens'),
    tokenModal: document.getElementById('tokenModal'),
    closeModalBtn: document.getElementById('closeModalBtn'),
    totalInputTokens: document.getElementById('totalInputTokens'),
    totalOutputTokens: document.getElementById('totalOutputTokens'),
    // Options
    checkThinking: document.getElementById('enableThinking'),
    checkSearch: document.getElementById('enableWebSearch'),
    checkTools: document.getElementById('enableTools')
};

// --- Initialization ---
document.addEventListener('DOMContentLoaded', () => {
    initUI();
    loadModels();
    loadConversations();
    
    // Check URL param for conversation ID
    const urlParams = new URLSearchParams(window.location.search);
    const cid = urlParams.get('cid');
    if (cid) {
        loadConversation(cid);
    } else {
        // Init load knowledge even without conversation
        loadKnowledge(null);
    }
});

function initUI() {
    // Event Listeners
    if(els.sendBtn) els.sendBtn.addEventListener('click', sendMessage);
    
    // File Input
    if(els.fileInput) els.fileInput.addEventListener('change', handleFileUpload);
    
    if(els.messageInput) {
        els.messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });
        // Auto-resize textarea
        els.messageInput.addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = (this.scrollHeight) + 'px';
            if(this.value === '') this.style.height = 'auto'; // Reset
        });
    }

    // Auto-scroll logic
    if (els.messagesContainer) {
        // [Optimization] Immediate manual override listeners
        // This ensures that any user interaction immediately disables auto-scroll
        // providing a "crisp" detachment feeling like standard native apps.
        const breakAutoScroll = () => { shouldAutoScroll = false; };
        
        els.messagesContainer.addEventListener('wheel', (e) => {
            if (e.deltaY < 0) breakAutoScroll(); // Only on scroll up
        }, { passive: true });
        
        els.messagesContainer.addEventListener('touchmove', breakAutoScroll, { passive: true });

        els.messagesContainer.addEventListener('scroll', () => {
            const { scrollTop, scrollHeight, clientHeight } = els.messagesContainer;
            const distance = scrollHeight - scrollTop - clientHeight;
            
            // [Optimization] Ultra-tight threshold (2px)
            // Only latch if we are practically at the very bottom.
            // This prevents the "rubber band" effect when dragging slightly up.
            if (distance <= 2) {
                shouldAutoScroll = true;
            } else {
                shouldAutoScroll = false;
            }
        });
    }

    // Sidebar Toggles
    if(els.toggleSidebar) {
        els.toggleSidebar.addEventListener('click', () => {
            if (window.innerWidth <= 768) {
                els.sidebar.classList.toggle('mobile-open');
            } else {
                els.sidebar.classList.toggle('collapsed');
            }
        });
    }
    
    const mobileToggle = document.getElementById('toggleSidebarMobile');
    if (mobileToggle) {
        mobileToggle.addEventListener('click', () => {
            els.sidebar.classList.toggle('mobile-open');
        });
    }

    // Knowledge Panel
    const toggleKP = () => els.knowledgePanel.classList.toggle('visible');
    if(els.toggleKnowledgePanel) els.toggleKnowledgePanel.addEventListener('click', toggleKP);
    if(els.btnTogglePanel) els.btnTogglePanel.addEventListener('click', toggleKP);

    if(els.refreshKnowledgeBtn) {
        els.refreshKnowledgeBtn.addEventListener('click', () => loadKnowledge(currentConversationId));
    }

    // New Chat
    if(els.newChatBtn) els.newChatBtn.addEventListener('click', () => createNewConversation());

    // Token Modal
    if(els.tokenDisplay) els.tokenDisplay.addEventListener('click', openTokenModal);
    if(els.closeModalBtn) els.closeModalBtn.addEventListener('click', () => els.tokenModal.classList.remove('active'));
    if(els.tokenModal) els.tokenModal.addEventListener('click', (e) => {
        if(e.target === els.tokenModal) els.tokenModal.classList.remove('active');
    });
}

async function openTokenModal() {
    if(!els.tokenModal) return;
    els.tokenModal.classList.add('active');
    
    try {
        const res = await fetch('/api/tokens/stats');
        const data = await res.json();
        if(data.success) {
            if(els.modalTotalTokens) els.modalTotalTokens.textContent = data.total.toLocaleString();
            if(els.modalTodayTokens) els.modalTodayTokens.textContent = data.today.toLocaleString();
        }
    } catch(e) { console.error("Error loading token stats", e); }
}

// --- Conversations ---
async function loadConversations() {
    try {
        const res = await fetch('/api/conversations');
        const data = await res.json();
        // Assuming data is array or object with list
        // API usually returns dict keys as IDs? Or list?
        // Let's assume list for now or adapt.
        const list = Array.isArray(data) ? data : (data.conversations || []);
        renderConversationList(list);
    } catch (e) {
        console.error("Failed to load conversations", e);
    }
}

function renderConversationList(conversations) {
    if(!els.conversationList) return;
    els.conversationList.innerHTML = '';
    
    // Sort logic if needed? 
    // Assuming backend returns sorted or we just list them.
    
    conversations.forEach(c => {
        const div = document.createElement('div');
        const cid = c.conversation_id || c.id; // Handle both
        div.className = `conversation-item ${cid === currentConversationId ? 'active' : ''}`;
        
        const titleSpan = document.createElement('span');
        titleSpan.className = 'title'; // Add class for CSS styling
        titleSpan.textContent = c.title || c.preview || `Conversation ${cid}`;
        div.appendChild(titleSpan);
        
        div.onclick = () => loadConversation(cid);
        
        // Delete button
        const delBtn = document.createElement('button');
        delBtn.className = 'btn-icon-small delete-chat';
        delBtn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>';
        delBtn.onclick = (e) => {
            e.stopPropagation();
            deleteConversation(cid);
        };
        div.appendChild(delBtn);
        
        els.conversationList.appendChild(div);
    });
}

async function createNewConversation(silent = false) {
    if(!silent) {
        // Clear UI
        currentConversationId = null;
        els.messagesContainer.innerHTML = `
            <div class="welcome-screen">
                <h1>Hello.</h1>
                <p>Start a new conversation.</p>
            </div>
        `;
        els.conversationTitle.textContent = 'New Chat';
        els.totalInputTokens.textContent = '0';
        els.totalOutputTokens.textContent = '0';
        if(window.history.pushState) window.history.pushState({}, '', '/chat');
        
        // Refresh list to remove active state
        loadConversations();
    }
}

async function loadConversation(id) {
    currentConversationId = id;
    els.messagesContainer.innerHTML = ''; // Loading state
    
    // Update URL
    if(window.history.pushState) window.history.pushState({}, '', `/chat?cid=${id}`);

    try {
        // Load messages
        const res = await fetch(`/api/conversations/${id}`);
        const data = await res.json();
        
        if (data.success && data.conversation) {
            // Render
            renderMessages(data.conversation.messages);
            if(els.conversationTitle) els.conversationTitle.textContent = data.conversation.title || "Conversation " + id;
        } else {
            console.error("Failed to load conversation:", data.message);
        }
        
        // Update Token Counts (if available in stored data, otherwise calc)
        
        // Load Knowledge
        loadKnowledge(id);
        
        // Highlight in sidebar
        loadConversations(); 
        
    } catch (e) {
        console.error("Error loading chat", e);
    }
}

async function deleteConversation(id) {
    if(!confirm("Delete this conversation?")) return;
    await fetch(`/api/conversations/${id}`, { method: 'DELETE' });
    if(currentConversationId === id) createNewConversation();
    loadConversations();
}

// --- Messaging ---
async function sendMessage() {
    const text = els.messageInput.value.trim();
    if (!text && !isGenerating && uploadedFileIds.length === 0) return;
    if (isGenerating) return; // or could be stop generation

    // UI Updates
    els.messageInput.value = '';
    els.messageInput.style.height = 'auto';
    
    // Configs
    const model = selectedModelId;
    const enableThinking = els.checkThinking ? els.checkThinking.checked : true;
    const enableSearch = els.checkSearch ? els.checkSearch.checked : true;
    const enableTools = els.checkTools ? els.checkTools.checked : true;

    // Prepare display content
    let displayContent = text;
    if (uploadedFileIds.length > 0) {
        displayContent += '\n\n' + uploadedFileIds.map(f => {
            return f.type === 'text' ? `[File Content: ${f.name}]` : `[Attachment: ${f.name}]`;
        }).join(' ');
    }

    // Add User Message to UI
    appendMessage({ role: 'user', content: displayContent });
    
    // Reset auto-scroll
    shouldAutoScroll = true;

    // Separate text files from Volc files
    let finalMessage = text;
    const volcFileIds = [];
    
    uploadedFileIds.forEach(f => {
        if (f.type === 'text') {
            finalMessage += `\n\n--- Start of File: ${f.name} ---\n${f.content}\n--- End of File: ${f.name} ---\n`;
        } else {
            volcFileIds.push(f.id);
        }
    });

    // Prepare API Payload
    const payload = {
        message: finalMessage,
        model_name: model,
        conversation_id: currentConversationId,
        enable_thinking: enableThinking,
        enable_web_search: enableSearch,
        enable_tools: enableTools,
        file_ids: volcFileIds
    };
    
    // Reset files
    uploadedFileIds = [];
    updateFilePreview();

    isGenerating = true;
    
    // Create Placeholder for AI Response
    const aiMsgId = Date.now().toString(); // Temporary ID
    const aiMsgDiv = appendMessage({ role: 'assistant', content: '', id: aiMsgId, pending: true });
    let currentFullContent = '';
    
    try {
        const res = await fetch('/api/chat/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) {
                // 流结束后，自动折叠思考栏（除非用户手动打开过）
                const thinkingBlock = aiMsgDiv.querySelector('.thinking-block');
                if (thinkingBlock && thinkingBlock.dataset.userToggled !== 'true') {
                    // 用户没有手动操作过，自动折叠
                    setTimeout(() => {
                        thinkingBlock.classList.add('collapsed');
                    }, 500); // 延迟500ms，让用户可以看到最后的思考内容
                }
                break;
            }
            
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop(); // Keep last incomplete line

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const jsonStr = line.slice(6);
                    if (jsonStr === '[DONE]') {
                        isGenerating = false;
                        continue;
                    }
                    try {
                        const chunk = JSON.parse(jsonStr);
                        
                        if (chunk.conversation_id) {
                            currentConversationId = chunk.conversation_id;
                        }
                        
                        if (chunk.type === 'content') {
                            currentFullContent += chunk.content;
                            const contentSpan = aiMsgDiv.querySelector('.content-body') || createContentSpan(aiMsgDiv);
                            contentSpan.innerHTML = marked.parse(currentFullContent);
                            renderMathInElement(contentSpan);
                            highlightCode(contentSpan);
                        } 
                        else if (chunk.type === 'reasoning_content') { 
                            // Handle reasoning
                           const msgContentContainer = aiMsgDiv.querySelector('.message-content');
                           let thinkingBlock = msgContentContainer.querySelector('.thinking-block');
                           
                           if(!thinkingBlock) {
                               thinkingBlock = document.createElement('div');
                               thinkingBlock.className = 'thinking-block'; // 流式输出时默认展开
                               thinkingBlock.dataset.userToggled = 'false'; // 跟踪用户是否手动操作过
                               thinkingBlock.innerHTML = `
                                <div class="thinking-header">
                                    <svg class="thinking-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                        <circle cx="12" cy="12" r="10"></circle>
                                        <path d="M12 6v6l4 2"></path>
                                    </svg>
                                    <span class="thinking-title">思考过程</span>
                                    <svg class="chevron-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                        <polyline points="6 9 12 15 18 9"></polyline>
                                    </svg>
                                </div>
                                <div class="thinking-content"></div>
                               `;
                               
                               // 添加点击事件监听，记录用户手动操作
                               const header = thinkingBlock.querySelector('.thinking-header');
                               header.addEventListener('click', function() {
                                   thinkingBlock.classList.toggle('collapsed');
                                   thinkingBlock.dataset.userToggled = 'true'; // 标记用户已手动操作
                               });
                               
                               // Prepend
                               const contentBody = msgContentContainer.querySelector('.content-body');
                               if(contentBody) msgContentContainer.insertBefore(thinkingBlock, contentBody);
                               else msgContentContainer.appendChild(thinkingBlock);
                           }
                           
                           const contentDiv = thinkingBlock.querySelector('.thinking-content');
                           contentDiv.textContent += chunk.content;
                        }
                        // --- New Chunk Types Support ---
                        else if (chunk.type === 'web_search') {
                            updateWebSearchStatus(aiMsgDiv, chunk.status, chunk.query, chunk.content);
                        }
                        else if (chunk.type === 'function_call') {
                            // Special handling for addBasis to show content
                            if (chunk.name === 'addBasis') {
                                try {
                                    const args = JSON.parse(chunk.arguments);
                                    appendAddBasisView(aiMsgDiv, args);
                                } catch(e) { console.error("Error parsing addBasis args", e); }
                            }
                            appendToolEvent(aiMsgDiv, chunk.name, chunk.arguments, true);
                        }
                        else if (chunk.type === 'function_result') {
                            updateLastToolResult(aiMsgDiv, chunk.name, chunk.result);
                        }
                        else if (chunk.type === 'token_usage') {
                            if(els.totalInputTokens) els.totalInputTokens.textContent = chunk.total_tokens || chunk.input_tokens + chunk.output_tokens;
                        }
                        else if (chunk.type === 'title') {
                            if(els.conversationTitle) els.conversationTitle.textContent = chunk.title;
                        }
                        else if (chunk.type === 'error') {
                            aiMsgDiv.innerHTML += `<div class="error" style="color:red; margin:10px;">Error: ${chunk.content}</div>`;
                        }
                        
                    } catch (e) { console.error("Parse error", e); }
                }
            }
             // Auto-scroll
             if (shouldAutoScroll) {
                // Check if we are already near bottom before forcing script scroll
                // This prevents fighting if the user is actively trying to scroll up but hasn't passed threshold yet
                // However, if we just added content, we ARE effectively scrolled up.
                // So we really just want to apply scroll if the flag says so.
                requestAnimationFrame(() => {
                    els.messagesContainer.scrollTop = els.messagesContainer.scrollHeight;
                });
             }
        }
    } catch (e) {
        aiMsgDiv.innerHTML += `<div class="error">Error: ${e.message}</div>`;
        isGenerating = false;
    } finally {
        isGenerating = false;
        aiMsgDiv.classList.remove('pending');
        loadConversations(); // Update list preview
        loadKnowledge(currentConversationId); // Refresh knowledge
    }
}

function updateWebSearchStatus(aiMsgDiv, status, query, fullContent) {
    const parent = aiMsgDiv.querySelector('.message-content') || aiMsgDiv;
    let badge = parent.querySelector('.tool-usage[data-tool-name="Web Search"]');
    
    // Construct display text
    let displayText = status || fullContent;
    
    if (!badge) {
        // Create new
        const div = document.createElement('div');
        div.className = 'tool-usage';
        div.dataset.toolName = 'Web Search';
        div.dataset.query = query || ''; // Store query
        
        const iconSvg = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>';
        
        div.innerHTML = `
            <div class="tool-badge">
                ${iconSvg}
                <span>Web Search</span>
                <span class="tool-status"></span>
            </div>
        `;
        
        // Insert before content body if exists
        const contentBody = parent.querySelector('.content-body');
        if(contentBody) parent.insertBefore(div, contentBody);
        else parent.appendChild(div);
        
        badge = div;
    }
    
    // Update Logic
    // If we have a new query, update stored
    if (query) badge.dataset.query = query;
    const currentQuery = badge.dataset.query;
    
    if (currentQuery) {
        displayText = `${status}: ${currentQuery}`;
    }
    
    badge.querySelector('.tool-status').textContent = displayText;
}

function appendAddBasisView(aiMsgDiv, args) {
    const parent = aiMsgDiv.querySelector('.message-content') || aiMsgDiv;
    const div = document.createElement('div');
    div.className = 'add-basis-view';
    div.innerHTML = `
        <div class="add-basis-header">
            <span>ADDED KNOWLEDGE: ${args.title || 'Untitled'}</span>
            <span style="font-weight:normal; color:#999;">${(args.context || '').length} chars</span>
        </div>
        <div class="add-basis-content">${args.context || ''}</div>
    `;
    parent.appendChild(div);
}

function appendToolEvent(aiMsgDiv, name, details, isFunction = false) {
    const parent = aiMsgDiv.querySelector('.message-content') || aiMsgDiv;
    const contentBody = parent.querySelector('.content-body');
    
    const div = document.createElement('div');
    div.className = 'tool-usage';
    div.dataset.toolName = name; // Marker
    
    // Icon selection
    let iconSvg = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"></rect><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"></path></svg>'; // default toolbox
    if(name === 'Web Search' || name === 'searchKeyword' || name === 'web_search') {
        iconSvg = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>';
    }

    let detailText = typeof details === 'object' ? JSON.stringify(details) : details;
    if(isFunction && detailText) detailText = `argsStr: ${detailText.substring(0, 50)}...`;

    div.innerHTML = `
        <div class="tool-badge">
            ${iconSvg}
            <span>${name}</span>
            <span class="tool-status">${detailText || ''}</span>
        </div>
        <div class="tool-output" style="display:none;"></div>
    `;
    
    // If content exists, insert before it? Usually tools come before content or interleaved.
    // If we are strictly streaming, we append to parent. 
    // But if 'content' already started, appending to parent puts it AFTER content, which is fine for interleaved.
    parent.appendChild(div);
    return div;
}

function updateLastToolResult(aiMsgDiv, name, result) {
    // Find the last tool usage of this name that doesn't have a result yet
    const parent = aiMsgDiv.querySelector('.message-content') || aiMsgDiv;
    const tools = parent.querySelectorAll(`.tool-usage`);
    // Iterate backwards
    let target = null;
    for (let i = tools.length - 1; i >= 0; i--) {
        const t = tools[i];
        // Check if it matches name (loose check) and has hidden output (empty)
        // Just picking the last tool usage is usually safe given sequential execution
        if (t.dataset.toolName === name || (name === 'web_search' && t.dataset.toolName === 'Web Search')) {
            target = t;
            break;
        }
    }
    
    if (target) {
        const outDiv = target.querySelector('.tool-output');
        outDiv.style.display = 'block';
        outDiv.textContent = typeof result === 'object' ? JSON.stringify(result, null, 2) : result;
    }
}

function createContentSpan(parentMsgDiv) {
    const parent = parentMsgDiv.querySelector('.message-content') || parentMsgDiv;
    const span = document.createElement('div');
    span.className = 'content-body fade-in';
    parent.appendChild(span);
    return span;
}

function appendMessage(msg) {
    const div = document.createElement('div');
    div.className = `message ${msg.role}`;
    if (msg.pending) div.classList.add('pending');
    
    // Avatar for AI
    if (msg.role === 'assistant') {
        const avatar = document.createElement('div');
        avatar.className = 'avatar ai';
        avatar.textContent = 'AI';
        div.appendChild(avatar);
    }

    const content = document.createElement('div');
    content.className = 'message-content';
    
    if (msg.role === 'user') {
        // Wrap user content in bubble for alignment
        const bubble = document.createElement('div');
        bubble.className = 'message-bubble';
        bubble.textContent = msg.content;
        content.appendChild(bubble);
    } else {
        // AI Message
        
        // Render reasoning_content (thinking process) if exists
        if (msg.metadata && msg.metadata.reasoning_content) {
            const thinkingBlock = document.createElement('div');
            thinkingBlock.className = 'thinking-block collapsed'; // 默认折叠
            thinkingBlock.innerHTML = `
                <div class="thinking-header">
                    <svg class="thinking-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"></circle>
                        <path d="M12 6v6l4 2"></path>
                    </svg>
                    <span class="thinking-title">思考过程</span>
                    <svg class="chevron-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="6 9 12 15 18 9"></polyline>
                    </svg>
                </div>
                <div class="thinking-content"></div>
            `;
            
            // 添加点击事件监听
            const header = thinkingBlock.querySelector('.thinking-header');
            header.addEventListener('click', function() {
                thinkingBlock.classList.toggle('collapsed');
            });
            
            thinkingBlock.querySelector('.thinking-content').textContent = msg.metadata.reasoning_content;
            content.appendChild(thinkingBlock);
        }
        
        // Render main content
        if(msg.content) {
            const body = document.createElement('div');
            body.className = 'content-body';
            body.innerHTML = marked.parse(msg.content);
            renderMathInElement(body);
            highlightCode(body);
            content.appendChild(body);
        }
    }

    div.appendChild(content);
    
    els.messagesContainer.appendChild(div);
    
    // Remove welcome screen if exists
    const welcome = els.messagesContainer.querySelector('.welcome-screen');
    if(welcome) welcome.remove();

    // Scroll
    els.messagesContainer.scrollTop = els.messagesContainer.scrollHeight;
    
    return div; // Return main message div
}

function renderMessages(messages) {
    // preserve welcome if empty
    if(!messages || messages.length === 0) return;
    
    els.messagesContainer.innerHTML = '';
    messages.forEach(appendMessage);
}


// --- Knowledge ---
async function loadKnowledge(cid) {
    // Knowledge is likely user-global, not per conversation, but we reload on chat interactions
    try {
        const [resBasis, resShort] = await Promise.all([
            fetch('/api/knowledge/basis'),
            fetch('/api/knowledge/short')
        ]);
        
        const basisData = await resBasis.json();
        const shortData = await resShort.json();

        if (basisData.success) {
            renderKnowledgeList(els.panelBasisList, basisData.knowledge || [], 'basis');
            if(els.panelBasisCount) els.panelBasisCount.textContent = (basisData.knowledge || []).length;
        }
        if (shortData.success) {
            renderKnowledgeList(els.panelShortList, shortData.knowledge || [], 'short');
            if(els.panelShortCount) els.panelShortCount.textContent = (shortData.knowledge || []).length;
        }

    } catch(e) { console.error("Error loading knowledge", e); }
}

function renderKnowledgeList(container, items, type) {
    if(!container) return;
    container.innerHTML = '';
    items.forEach(item => {
        const title = typeof item === 'string' ? item : item.title;
        const div = document.createElement('div');
        div.className = 'knowledge-item';
        div.textContent = title;
        div.style.cursor = 'pointer';
        // Add click handler to view details ONLY for basis for now
        if(type === 'basis') {
             div.onclick = () => viewKnowledge(title);
        }
        else {
            div.onclick = () => {} // Maybe view short term too?
        }
        container.appendChild(div);
    });
}


// --- Knowledge View Logic ---
let easyMDE = null;
let originalHeaderState = null;

async function viewKnowledge(title) {
    const viewer = document.getElementById('knowledgeViewer');
    const msgs = document.getElementById('messagesContainer');
    const inputWrapper = document.getElementById('inputWrapper'); // Updated ID in HTML
    const headerTitle = document.getElementById('conversationTitle');
    const headerLeft = document.querySelector('.header-left');
    const headerRight = document.querySelector('.header-right');

    if(!viewer || !msgs) return;
    
    // 1. Save Header State
    originalHeaderState = {
        title: headerTitle.textContent,
        leftHTML: headerLeft.innerHTML,
        rightHTML: headerRight.innerHTML
    };

    // 2. Fetch Content
    let content = '';
    try {
        const res = await fetch(`/api/knowledge/basis/${encodeURIComponent(title)}`);
        const data = await res.json();
        if(data.success) content = data.knowledge.content;
    } catch(e) { console.error(e); }

    // 3. UI Switch
    msgs.style.display = 'none';
    if(inputWrapper) inputWrapper.style.display = 'none';
    viewer.style.display = 'block';

    // 4. Update Header
    headerTitle.textContent = title;
    
    // Back Button (Left)
    headerLeft.innerHTML = `
        <button class="btn-icon" onclick="closeKnowledgeView()" title="Back">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="19" y1="12" x2="5" y2="12"></line><polyline points="12 19 5 12 12 5"></polyline></svg>
        </button>
    `;

    // Save Button (Right)
    headerRight.innerHTML = `
        <button class="btn-primary-outline" onclick="confirmDeleteKnowledge('${title}')" style="border:1px solid #ff4d4f; color:#ff4d4f; margin-right: 10px; background: #fff0f0;">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
            Delete
        </button>
        <button class="btn-primary-outline" onclick="saveKnowledge('${title}')" style="border:1px solid #ddd; color:#333;">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"></path><polyline points="17 21 17 13 7 13 7 21"></polyline><polyline points="7 3 7 8 15 8"></polyline></svg>
            Save
        </button>
    `;

    // 5. Initialize Editor
    if (!easyMDE) {
        easyMDE = new EasyMDE({ 
            element: document.getElementById('knowledgeEditor'),
            status: false,
            spellChecker: false,
            sideBySideFullscreen: false,
            previewRender: function(plainText) {
                return marked.parse(plainText);
            },
            toolbar: ["bold", "italic", "heading", "|", "quote", "unordered-list", "ordered-list", "|", 
                      "link", "image", "table", "|", "preview", "side-by-side", "fullscreen", "|", "guide"]
        });
        
        // Toggle to preview mode by default
        setTimeout(() => {
            const previewButton = document.querySelector('.editor-toolbar .fa-eye');
            if (previewButton && !easyMDE.isPreviewActive()) {
                EasyMDE.togglePreview(easyMDE);
            }
        }, 150);
    }
    
    // Adjust Editor Height dynamically - use fixed viewport calculation
    const viewportHeight = window.innerHeight;
    const headerHeight = 60; // chat-header height
    const editorHeight = viewportHeight - headerHeight;
    
    // Set explicit height on CodeMirror
    easyMDE.codemirror.setSize(null, `${editorHeight}px`);

    easyMDE.value(content || '');
    // Refresh to fix layout issues if hidden previously
    setTimeout(() => easyMDE.codemirror.refresh(), 100);
}

function closeKnowledgeView() {
    const viewer = document.getElementById('knowledgeViewer');
    const msgs = document.getElementById('messagesContainer');
    const inputWrapper = document.getElementById('inputWrapper');
    const headerTitle = document.getElementById('conversationTitle');
    const headerLeft = document.querySelector('.header-left');
    const headerRight = document.querySelector('.header-right');

    // UI Switch
    viewer.style.display = 'none';
    msgs.style.display = 'flex'; // flex for messages center alignment
    if(inputWrapper) inputWrapper.style.display = 'block';

    // Restore Header
    if (originalHeaderState) {
        headerTitle.textContent = originalHeaderState.title;
        headerLeft.innerHTML = originalHeaderState.leftHTML;
        headerRight.innerHTML = originalHeaderState.rightHTML;
        
        // Re-attach event listeners (innerHTML destroys them)
        // Sidebar Toggle
        const toggleSidebar = document.getElementById('toggleSidebar');
        if(toggleSidebar) {
             toggleSidebar.addEventListener('click', () => {
                if (window.innerWidth <= 768) els.sidebar.classList.toggle('mobile-open');
                else els.sidebar.classList.toggle('collapsed');
            });
        }
        // Model Selector Logic (Need to re-bind because elements were destroyed)
        els.currentModelDisplay = document.getElementById('currentModelDisplay');
        els.modelOptions = document.getElementById('modelOptions');
        // Re-init model selector events if needed or just re-render
        // Ideally we shouldn't destroy the whole headerLeft, but just hide stuff. 
        // For now, let's call loadModels() again or manually re-bind to be safe.
        loadModels(); 

        // Knowledge Panel Toggle
        const toggleKP = document.getElementById('toggleKnowledgePanel');
        if(toggleKP) toggleKP.onclick = () => els.knowledgePanel.classList.toggle('visible');
    }
}

async function saveKnowledge(title) {
    if(!easyMDE) return;
    const content = easyMDE.value();
    
    try {
        const res = await fetch('/api/knowledge/basis/update', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ title, content })
        });
        const data = await res.json();
        if(data.success) {
            showToast('Saved successfully');
        } else {
            showToast('Error saving: ' + data.message);
        }
    } catch(e) {
        showToast('Error saving: ' + e.message);
    }
}

function confirmDeleteKnowledge(title) {
    const backdrop = document.getElementById('confirmBackdrop');
    const msg = document.getElementById('confirmMessage');
    const okBtn = document.getElementById('confirmOkBtn');
    
    msg.textContent = `Are you sure you want to delete "${title}"? This cannot be undone.`;
    okBtn.onclick = () => deleteKnowledge(title);
    
    if(backdrop) {
        backdrop.style.display = 'flex'; // Or add class 'active' if you used the CSS from style.css
        backdrop.classList.add('active');
    }
}

function closeConfirmModal() {
    const backdrop = document.getElementById('confirmBackdrop');
    if(backdrop) {
        backdrop.style.display = 'none';
        backdrop.classList.remove('active');
    }
}

async function deleteKnowledge(title) {
    try {
        const res = await fetch(`/api/knowledge/basis/${encodeURIComponent(title)}`, {
            method: 'DELETE'
        });
        
        const data = await res.json();
        closeConfirmModal();
        
        if(data.success) {
            showToast('Deleted successfully');
            closeKnowledgeView();
            loadKnowledge(); // Refresh the list
        } else {
            showToast('Error deleting: ' + (data.message || data.error));
        }
    } catch(e) {
        closeConfirmModal();
        showToast('Error deleting: ' + e.message);
    }
}

function showToast(msg) {
    let toast = document.querySelector('.toast-notification');
    if(!toast) {
        toast = document.createElement('div');
        toast.className = 'toast-notification';
        document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 3000);
}

// --- Models ---
let selectedModelId = null;

async function loadModels() {
    try {
        const res = await fetch('/api/config');
        const data = await res.json();
        if(data.models) {
            renderCustomModelSelect(data.models, data.default_model);
        }
    } catch(e) { console.error("Error loading models", e); }
}

function renderCustomModelSelect(models, defaultModel) {
    if(!els.modelOptions) return;
    
    // Clear
    els.modelOptions.innerHTML = '';
    
    // Setup initial
    const stored = localStorage.getItem('selectedModel');
    selectedModelId = (models.find(m => m.id === stored) ? stored : defaultModel) || models[0].id;
    
    // Render Options
    models.forEach(m => {
        const div = document.createElement('div');
        div.textContent = m.name;
        div.onclick = () => selectModel(m.id, m.name);
        if(m.id === selectedModelId) div.classList.add('same-as-selected');
        els.modelOptions.appendChild(div);
    });
    
    // Set initial display
    const currentList = models.find(m => m.id === selectedModelId);
    if(currentList) els.currentModelDisplay.textContent = currentList.name;

    // Toggle logic
    els.currentModelDisplay.onclick = (e) => {
        e.stopPropagation();
        const isClosed = els.modelOptions.classList.contains('select-hide');
        closeAllSelects(); // Close any potential others or self cleanup
        
        if (isClosed) {
            els.modelOptions.classList.remove('select-hide');
            els.currentModelDisplay.classList.add('select-arrow-active');
        }
    };
    
    document.addEventListener('click', closeAllSelects);
}

function selectModel(id, name) {
    selectedModelId = id;
    localStorage.setItem('selectedModel', id);
    els.currentModelDisplay.textContent = name;
    
    // Visual update
    Array.from(els.modelOptions.children).forEach(c => {
         if(c.textContent === name) c.classList.add('same-as-selected');
         else c.classList.remove('same-as-selected');
    });
    
    els.modelOptions.classList.add('select-hide');
    els.currentModelDisplay.classList.remove('select-arrow-active');
}

function closeAllSelects(e) {
    if(els.modelOptions && !els.modelOptions.classList.contains('select-hide')) {
        // If click was outside container
         els.modelOptions.classList.add('select-hide');
         els.currentModelDisplay.classList.remove('select-arrow-active');
    }
}


// --- Utils ---
function highlightCode(element) {
    if(window.hljs) {
        element.querySelectorAll('pre code').forEach((block) => {
            hljs.highlightElement(block);
        });
    }
}


// --- File Upload ---
async function handleFileUpload(e) {
    const files = e.target.files;
    if (!files.length) return;

    for (let file of files) {
        const formData = new FormData();
        formData.append('file', file);
        
        try {
            const loadingBadge = document.createElement('div');
            loadingBadge.textContent = 'Uploading ' + file.name + '...';
            loadingBadge.className = 'file-badge loading';
            loadingBadge.style.cssText = 'background:#eee; padding:2px 8px; border-radius:12px; font-size:12px;';
            if(els.filePreviewArea) {
                els.filePreviewArea.appendChild(loadingBadge);
                els.filePreviewArea.style.display = 'flex';
            }

            const res = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();
            
            loadingBadge.remove();

            if (data.success) {
                // Store based on type
                if (data.type === 'text') {
                    uploadedFileIds.push({
                        type: 'text', // local marker
                        content: data.content,
                        name: data.filename
                    });
                } else {
                    uploadedFileIds.push({
                        type: 'file',
                        id: data.file_id,
                        name: data.filename
                    });
                }
                updateFilePreview();
            } else {
                alert('Upload failed: ' + data.message);
            }
        } catch (err) {
            console.error(err);
            alert('Upload error');
        }
    }
    e.target.value = '';
}

function updateFilePreview() {
    if(!els.filePreviewArea) return;
    els.filePreviewArea.innerHTML = '';
    
    if (uploadedFileIds.length === 0) {
        els.filePreviewArea.style.display = 'none';
        return;
    }
    
    els.filePreviewArea.style.display = 'flex';
    
    uploadedFileIds.forEach((file, index) => {
        const badge = document.createElement('div');
        badge.className = 'file-badge';
        badge.style.cssText = 'background:#e1e4e8; padding:2px 8px; border-radius:12px; font-size:12px; display:flex; align-items:center; gap:5px;';
        
        badge.innerHTML = `
            <span>${file.name}</span>
            <span style="cursor:pointer; font-weight:bold; color:#666;" onclick="removeUploadedFile(${index})">×</span>
        `;
        els.filePreviewArea.appendChild(badge);
    });
}

window.removeUploadedFile = function(index) {
    uploadedFileIds.splice(index, 1);
    updateFilePreview();
}
