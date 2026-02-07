class NodeGraph {
    constructor(viewportId, containerId, edgeLayerId) {
        this.viewport = document.getElementById(viewportId);
        this.container = document.getElementById(containerId);
        this.edgeLayer = document.getElementById(edgeLayerId);
        
        this.state = {
            data: null,
            zoom: 1,
            offset: { x: 0, y: 0 },
            isPanning: false,
            isDragging: false,
            draggedElement: null,
            dragStart: { x: 0, y: 0 },
            elementStart: { x: 0, y: 0 },
            selectedNode: null
        };

        this.init();
    }

    init() {
        this.setupEventListeners();
        this.loadData();
    }

    async loadData() {
        try {
            const response = await fetch('/api/knowledge/graph');
            this.state.data = await response.json();
            this.render();
        } catch (error) {
            console.error('Failed to load knowledge graph:', error);
        }
    }

    render() {
        this.container.innerHTML = '';
        const { categories, connections } = this.state.data;

        // Render Categories
        Object.entries(categories).forEach(([name, data]) => {
            const el = this.createCategoryElement(name, data);
            this.container.appendChild(el);
        });

        this.updateEdges();
    }

    createCategoryElement(name, data) {
        const el = document.createElement('div');
        el.className = 'category-node';
        el.id = `cat-${name}`;
        el.style.left = `${data.position.x}px`;
        el.style.top = `${data.position.y}px`;
        el.dataset.name = name;

        const header = document.createElement('div');
        header.className = 'category-header';
        header.innerHTML = `
            <div class="category-title">
                <div class="category-color-dot" style="background: ${data.color || '#3b82f6'}"></div>
                ${name}
            </div>
            <div class="category-actions">
                <i class="fas fa-ellipsis-v"></i>
            </div>
        `;

        const content = document.createElement('div');
        content.className = 'category-content';
        
        data.knowledge_ids.forEach(kid => {
            const item = document.createElement('div');
            item.className = 'knowledge-item';
            item.id = `node-${kid}`;
            item.innerHTML = `
                <span>${kid}</span>
                <div class="port" data-kid="${kid}"></div>
            `;
            item.onclick = (e) => {
                e.stopPropagation();
                if (window.showNote) window.showNote(kid);
            };
            content.appendChild(item);
        });

        el.appendChild(header);
        el.appendChild(content);

        // Header movement
        header.onmousedown = (e) => this.startDragging(e, el);

        return el;
    }

    updateEdges() {
        this.edgeLayer.innerHTML = '';
        const { connections } = this.state.data;
        if (!connections) return;

        connections.forEach(conn => {
            const path = this.createEdgePath(conn);
            if (path) this.edgeLayer.appendChild(path);
        });
    }

    createEdgePath(conn) {
        const fromEl = document.getElementById(`node-${conn.from}`);
        const toEl = document.getElementById(`node-${conn.to}`);
        
        if (!fromEl || !toEl) return null;

        const fromRect = fromEl.getBoundingClientRect();
        const toRect = toEl.getBoundingClientRect();
        const containerRect = this.container.getBoundingClientRect();

        // Calculate positions relative to the container
        const startX = (fromRect.right - containerRect.left) / this.state.zoom;
        const startY = (fromRect.top + fromRect.height / 2 - containerRect.top) / this.state.zoom;
        
        const endX = (toRect.left - containerRect.left) / this.state.zoom;
        const endY = (toRect.top + toRect.height / 2 - containerRect.top) / this.state.zoom;

        const cp1x = startX + (endX - startX) / 2;
        const cp2x = startX + (endX - startX) / 2;

        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', `M ${startX} ${startY} C ${cp1x} ${startY}, ${cp2x} ${endY}, ${endX} ${endY}`);
        path.setAttribute('class', 'connector-path');
        path.dataset.from = conn.from;
        path.dataset.to = conn.to;
        
        return path;
    }

    setupEventListeners() {
        // Pan and Zoom
        this.viewport.onmousedown = (e) => {
            if (e.button === 0 && e.target === this.viewport) {
                this.state.isPanning = true;
                this.state.dragStart = { x: e.clientX, y: e.clientY };
                this.state.elementStart = { ...this.state.offset };
            }
        };

        window.onmousemove = (e) => {
            if (this.state.isPanning) {
                const dx = e.clientX - this.state.dragStart.x;
                const dy = e.clientY - this.state.dragStart.y;
                this.state.offset.x = this.state.elementStart.x + dx;
                this.state.offset.y = this.state.elementStart.y + dy;
                this.applyTransform();
            } else if (this.state.isDragging && this.state.draggedElement) {
                const dx = (e.clientX - this.state.dragStart.x) / this.state.zoom;
                const dy = (e.clientY - this.state.dragStart.y) / this.state.zoom;
                
                const newX = this.state.elementStart.x + dx;
                const newY = this.state.elementStart.y + dy;
                
                this.state.draggedElement.style.left = `${newX}px`;
                this.state.draggedElement.style.top = `${newY}px`;
                
                // Update state in data (optional, but good for saving)
                const catName = this.state.draggedElement.dataset.name;
                if (this.state.data.categories[catName]) {
                    this.state.data.categories[catName].position = { x: newX, y: newY };
                }
                
                this.updateEdges();
            }
        };

        window.onmouseup = () => {
            if (this.state.isDragging) {
                this.savePositions();
            }
            this.state.isPanning = false;
            this.state.isDragging = false;
            this.state.draggedElement = null;
        };

        this.viewport.onwheel = (e) => {
            e.preventDefault();
            const delta = e.deltaY > 0 ? 0.9 : 1.1;
            const newZoom = Math.min(Math.max(this.state.zoom * delta, 0.2), 3);
            
            // Zoom toward mouse
            const rect = this.viewport.getBoundingClientRect();
            const mouseX = e.clientX - rect.left;
            const mouseY = e.clientY - rect.top;
            
            const beforeX = (mouseX - this.state.offset.x) / this.state.zoom;
            const beforeY = (mouseY - this.state.offset.y) / this.state.zoom;
            
            this.state.zoom = newZoom;
            
            this.state.offset.x = mouseX - beforeX * this.state.zoom;
            this.state.offset.y = mouseY - beforeY * this.state.zoom;
            
            this.applyTransform();
        };
    }

    startDragging(e, el) {
        e.stopPropagation();
        this.state.isDragging = true;
        this.state.draggedElement = el;
        this.state.dragStart = { x: e.clientX, y: e.clientY };
        this.state.elementStart = {
            x: parseFloat(el.style.left),
            y: parseFloat(el.style.top)
        };
    }

    applyTransform() {
        this.container.style.transform = `translate(${this.state.offset.x}px, ${this.state.offset.y}px) scale(${this.state.zoom})`;
    }

    async savePositions() {
        // Debounced save would be better, but for now:
        const catPositions = {};
        Object.entries(this.state.data.categories).forEach(([name, data]) => {
            catPositions[name] = data.position;
        });
        
        try {
            await fetch('/api/knowledge/graph/positions', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(catPositions)
            });
        } catch (e) { console.error('Failed to save positions'); }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.graph = new NodeGraph('graph-viewport', 'graph-container', 'edge-layer');
});
