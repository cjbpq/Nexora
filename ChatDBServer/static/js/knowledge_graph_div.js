/**
 * Knowledge Graph - Div Based Rendering (using D3 for simulation)
 */

class KnowledgeGraph {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.nodes = [];
        this.links = [];
        this.width = this.container.clientWidth;
        this.height = this.container.clientHeight;
        
        // Zoom/Pan State
        this.transform = { x: 0, y: 0, k: 1 };
        
        this.init();
    }

    init() {
        this.container.innerHTML = '';
        
        // Create Graph Content Wrapper
        this.content = document.createElement('div');
        this.content.className = 'graph-content';
        this.container.appendChild(this.content);
        
        // Create SVG Layer for edges
        this.svg = d3.select(this.content)
            .append('svg')
            .attr('class', 'edge-layer')
            .attr('width', 10000) // Large enough
            .attr('height', 10000)
            .style('overflow', 'visible');
        
        this.edgeGroup = this.svg.append('g').attr('class', 'edges');
        
        // Zoom behavior
        this.zoom = d3.zoom()
            .scaleExtent([0.1, 5])
            .on('zoom', (event) => {
                this.transform = event.transform;
                this.content.style.transform = `translate(${this.transform.x}px, ${this.transform.y}px) scale(${this.transform.k})`;
            });
            
        d3.select(this.container).call(this.zoom);
        
        // Simulation
        this.simulation = d3.forceSimulation()
            .force('link', d3.forceLink().id(d => d.id).distance(150))
            .force('charge', d3.forceManyBody().strength(-1500))
            .force('center', d3.forceCenter(this.width / 2, this.height / 2))
            .force('collision', d3.forceCollide().radius(100))
            .on('tick', () => this.ticked());
            
        window.addEventListener('resize', () => {
            this.width = this.container.clientWidth;
            this.height = this.container.clientHeight;
            this.simulation.force('center', d3.forceCenter(this.width / 2, this.height / 2));
            this.simulation.alpha(0.3).restart();
        });
    }

    setData(nodes, links) {
        this.nodes = nodes.map(n => ({ ...n }));
        this.links = links.map(l => ({ ...l }));
        
        this.render();
        
        this.simulation.nodes(this.nodes);
        this.simulation.force('link').links(this.links);
        this.simulation.alpha(1).restart();
    }

    render() {
        // Render Nodes as Divs
        const nodeSelection = d3.select(this.content)
            .selectAll('.node')
            .data(this.nodes, d => d.id)
            .join(
                enter => enter.append('div')
                    .attr('class', 'node')
                    .attr('id', d => `node-${d.id}`)
                    .attr('data-type', d => (d.type || 'knowledge').toLowerCase())
                    .call(d3.drag()
                        .on('start', (e, d) => this.dragStarted(e, d))
                        .on('drag', (e, d) => this.dragged(e, d))
                        .on('end', (e, d) => this.dragEnded(e, d))
                    )
                    .on('click', (e, d) => this.nodeClicked(e, d))
                    .html(d => `
                        <div class="node-type">${d.type || 'NOTE'}</div>
                        <div class="node-label">${d.label || d.id}</div>
                    `),
                update => update,
                exit => exit.remove()
            );

        // Render Edges as SVG paths
        this.edgeGroup.selectAll('.edge')
            .data(this.links, d => `${d.source.id || d.source}-${d.target.id || d.target}`)
            .join(
                enter => enter.append('path')
                    .attr('class', 'edge')
                    .attr('marker-end', 'url(#arrowhead)'),
                update => update,
                exit => exit.remove()
            );
            
        // Add Marker for Edges
        if (!this.svg.select('#arrowhead').size()) {
            this.svg.append('defs').append('marker')
                .attr('id', 'arrowhead')
                .attr('viewBox', '-0 -5 10 10')
                .attr('refX', 20)
                .attr('refY', 0)
                .attr('orient', 'auto')
                .attr('markerWidth', 6)
                .attr('markerHeight', 6)
                .attr('xoverflow', 'visible')
                .append('svg:path')
                .attr('d', 'M 0,-5 L 10 ,0 L 0,5')
                .attr('fill', '#94a3b8')
                .style('stroke', 'none');
        }
    }

    ticked() {
        // Update Node Positions
        d3.select(this.content).selectAll('.node')
            .style('left', d => `${d.x}px`)
            .style('top', d => `${d.y}px`)
            .style('transform', 'translate(-50%, -50%)');
            
        // Update Edge Positions
        this.edgeGroup.selectAll('.edge')
            .attr('d', d => {
                const dx = d.target.x - d.source.x;
                const dy = d.target.y - d.source.y;
                const dr = Math.sqrt(dx * dx + dy * dy);
                // Return a simple line or curve
                return `M${d.source.x},${d.source.y} L${d.target.x},${d.target.y}`;
            });
    }

    dragStarted(event, d) {
        if (!event.active) this.simulation.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
    }

    dragged(event, d) {
        d.fx = event.x;
        d.fy = event.y;
    }

    dragEnded(event, d) {
        if (!event.active) this.simulation.alphaTarget(0);
        d.fx = null;
        d.fy = null;
    }

    nodeClicked(event, d) {
        // Trigger generic event for the UI
        const clickEvent = new CustomEvent('nodeclick', { detail: d });
        this.container.dispatchEvent(clickEvent);
        
        // Highlight selection
        d3.select(this.content).selectAll('.node').classed('selected', false);
        d3.select(`#node-${d.id}`).classed('selected', true);
    }
    
    fit() {
        // Simple fitting - reset zoom
        d3.select(this.container).transition().call(this.zoom.transform, d3.zoomIdentity);
    }
}
