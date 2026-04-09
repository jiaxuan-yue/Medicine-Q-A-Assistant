import { useEffect, useRef, useCallback } from 'react';
import { Card, Empty } from 'antd';
import type { GraphNode, GraphEdge } from '../types';

interface GraphViewerProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  width?: number;
  height?: number;
  onNodeClick?: (node: GraphNode) => void;
}

const TYPE_COLORS: Record<string, string> = {
  symptom: '#f5222d',
  herb: '#52c41a',
  formula: '#1890ff',
  syndrome: '#fa8c16',
  disease: '#722ed1',
  acupoint: '#13c2c2',
  meridian: '#eb2f96',
  default: '#8c8c8c',
};

interface SimNode extends GraphNode {
  x: number;
  y: number;
  vx: number;
  vy: number;
}

export default function GraphViewer({ nodes, edges, width = 800, height = 500, onNodeClick }: GraphViewerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const simNodesRef = useRef<SimNode[]>([]);
  const animFrameRef = useRef<number>(0);
  const hoveredRef = useRef<string | null>(null);

  const getColor = (type: string) => TYPE_COLORS[type.toLowerCase()] || TYPE_COLORS.default;

  const initSimulation = useCallback(() => {
    const simNodes: SimNode[] = nodes.map((n, i) => ({
      ...n,
      x: (width / 2) + (Math.cos(2 * Math.PI * i / nodes.length) * Math.min(width, height) * 0.35),
      y: (height / 2) + (Math.sin(2 * Math.PI * i / nodes.length) * Math.min(width, height) * 0.35),
      vx: 0,
      vy: 0,
    }));
    simNodesRef.current = simNodes;
  }, [nodes, width, height]);

  const simulate = useCallback(() => {
    const simNodes = simNodesRef.current;
    const nodeMap = new Map(simNodes.map((n) => [n.id, n]));

    // Simple force simulation
    for (let iter = 0; iter < 3; iter++) {
      // Repulsion between nodes
      for (let i = 0; i < simNodes.length; i++) {
        for (let j = i + 1; j < simNodes.length; j++) {
          const a = simNodes[i];
          const b = simNodes[j];
          let dx = a.x - b.x;
          let dy = a.y - b.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = 800 / (dist * dist);
          dx = (dx / dist) * force;
          dy = (dy / dist) * force;
          a.vx += dx;
          a.vy += dy;
          b.vx -= dx;
          b.vy -= dy;
        }
      }

      // Attraction along edges
      for (const edge of edges) {
        const a = nodeMap.get(edge.source);
        const b = nodeMap.get(edge.target);
        if (!a || !b) continue;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const force = (dist - 120) * 0.01;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        a.vx += fx;
        a.vy += fy;
        b.vx -= fx;
        b.vy -= fy;
      }

      // Center gravity
      for (const node of simNodes) {
        node.vx += (width / 2 - node.x) * 0.005;
        node.vy += (height / 2 - node.y) * 0.005;
        node.vx *= 0.8;
        node.vy *= 0.8;
        node.x += node.vx;
        node.y += node.vy;
        // Bounds
        node.x = Math.max(30, Math.min(width - 30, node.x));
        node.y = Math.max(30, Math.min(height - 30, node.y));
      }
    }
  }, [edges, width, height]);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.scale(dpr, dpr);

    ctx.clearRect(0, 0, width, height);

    const simNodes = simNodesRef.current;
    const nodeMap = new Map(simNodes.map((n) => [n.id, n]));

    // Draw edges
    ctx.strokeStyle = '#d9d9d9';
    ctx.lineWidth = 1;
    for (const edge of edges) {
      const a = nodeMap.get(edge.source);
      const b = nodeMap.get(edge.target);
      if (!a || !b) continue;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();

      // Edge label
      const mx = (a.x + b.x) / 2;
      const my = (a.y + b.y) / 2;
      ctx.fillStyle = '#8c8c8c';
      ctx.font = '10px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(edge.relation, mx, my - 4);
    }

    // Draw nodes
    for (const node of simNodes) {
      const isHovered = hoveredRef.current === node.id;
      const radius = isHovered ? 22 : 18;
      const color = getColor(node.type);

      ctx.beginPath();
      ctx.arc(node.x, node.y, radius, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.globalAlpha = 0.85;
      ctx.fill();
      ctx.globalAlpha = 1;
      ctx.strokeStyle = isHovered ? '#000' : color;
      ctx.lineWidth = isHovered ? 2 : 1;
      ctx.stroke();

      // Node label
      ctx.fillStyle = '#262626';
      ctx.font = isHovered ? 'bold 12px sans-serif' : '11px sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillText(node.name, node.x, node.y + radius + 4);
    }
  }, [edges, width, height]);

  useEffect(() => {
    if (!nodes.length) return;
    initSimulation();
    let tick = 0;
    const maxTicks = 100;

    const animate = () => {
      if (tick < maxTicks) {
        simulate();
        tick++;
      }
      draw();
      animFrameRef.current = requestAnimationFrame(animate);
    };
    animate();

    return () => cancelAnimationFrame(animFrameRef.current);
  }, [nodes, edges, initSimulation, simulate, draw]);

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    let found: string | null = null;
    for (const node of simNodesRef.current) {
      const dx = node.x - mx;
      const dy = node.y - my;
      if (dx * dx + dy * dy < 20 * 20) {
        found = node.id;
        break;
      }
    }
    hoveredRef.current = found;
    if (canvas) canvas.style.cursor = found ? 'pointer' : 'default';
  };

  const handleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!onNodeClick) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    for (const node of simNodesRef.current) {
      const dx = node.x - mx;
      const dy = node.y - my;
      if (dx * dx + dy * dy < 20 * 20) {
        onNodeClick(node);
        break;
      }
    }
  };

  if (!nodes.length) {
    return (
      <Card>
        <Empty description="暂无图谱数据" />
      </Card>
    );
  }

  // Legend
  const usedTypes = [...new Set(nodes.map((n) => n.type.toLowerCase()))];

  return (
    <div>
      <div style={{ marginBottom: 8, display: 'flex', gap: 16, flexWrap: 'wrap' }}>
        {usedTypes.map((type) => (
          <span key={type} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12 }}>
            <span
              style={{
                width: 12,
                height: 12,
                borderRadius: '50%',
                background: getColor(type),
                display: 'inline-block',
              }}
            />
            {type}
          </span>
        ))}
      </div>
      <canvas
        ref={canvasRef}
        style={{ width, height, border: '1px solid #f0f0f0', borderRadius: 8 }}
        onMouseMove={handleMouseMove}
        onClick={handleClick}
      />
    </div>
  );
}
