import { useEffect, useRef, useState } from 'react';
import type { PointerEvent } from 'react';
import {
  Check,
  Circle,
  CornerDownLeft,
  MousePointer2,
  Pencil,
  RotateCcw,
  Square,
  Trash2,
  Upload,
} from 'lucide-react';
import Modal from './Modal';
import type { Paths } from './types';

export default function Sketch({
  initial,
  onApply,
  onClose,
}: {
  initial: Paths;
  onApply: (paths: Paths) => void;
  onClose: () => void;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const container = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [paths, setPaths] = useState<Paths>(initial);
  const [tool, setTool] = useState('pen');
  const [drawing, setDrawing] = useState<number[][]>([]);
  const [reference, setReference] = useState<string>();
  const [error, setError] = useState('');
  const stroke = useRef<number[][]>([]);
  const isDrawing = useRef(false);
  const redraw = () => {
    const ctx = canvas.current?.getContext('2d');
    if (!ctx) return;
    ctx.clearRect(0, 0, 640, 420);
    const render = (path: number[][], closed: boolean) => {
      if (!path.length) return;
      ctx.beginPath();
      ctx.moveTo(path[0][0], path[0][1]);
      path.slice(1).forEach(([x, y]) => ctx.lineTo(x, y));
      if (closed) {
        ctx.closePath();
        ctx.fillStyle = 'rgba(118,88,232,.13)';
        ctx.fill('evenodd');
      }
      ctx.lineWidth = 2.7;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.strokeStyle = '#7658e8';
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(path[0][0], path[0][1], 3.7, 0, Math.PI * 2);
      ctx.fillStyle = '#7658e8';
      ctx.fill();
    };
    paths.forEach((path) => render(path, true));
    render(drawing, false);
  };
  useEffect(redraw, [paths, drawing]);
  const point = (e: PointerEvent<HTMLCanvasElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    return [
      Math.max(0, Math.min(640, ((e.clientX - rect.left) / rect.width) * 640)),
      Math.max(0, Math.min(420, ((e.clientY - rect.top) / rect.height) * 420)),
    ];
  };
  const down = (e: PointerEvent<HTMLCanvasElement>) => {
    if (e.button !== 0) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    isDrawing.current = true;
    stroke.current = [point(e)];
    setDrawing(stroke.current);
    setError('');
  };
  const move = (e: PointerEvent<HTMLCanvasElement>) => {
    if (!isDrawing.current) return;
    const p = point(e),
      first = stroke.current[0];
    if (tool === 'rectangle') stroke.current = [first, [p[0], first[1]], p, [first[0], p[1]]];
    else if (tool === 'circle') {
      const cx = (p[0] + first[0]) / 2,
        cy = (p[1] + first[1]) / 2;
      stroke.current = Array.from({ length: 64 }, (_, i) => [
        cx + (Math.abs(p[0] - first[0]) / 2) * Math.cos((i / 64) * Math.PI * 2),
        cy + (Math.abs(p[1] - first[1]) / 2) * Math.sin((i / 64) * Math.PI * 2),
      ]);
      stroke.current.unshift(first);
      stroke.current.shift();
    } else {
      const last = stroke.current[stroke.current.length - 1];
      if (Math.hypot(last[0] - p[0], last[1] - p[1]) > 1.5 && stroke.current.length < 2800)
        stroke.current = [...stroke.current, p];
    }
    // Shape drag anchor remains independent of its generated path.
    if (tool !== 'pen') stroke.current = [...stroke.current];
    setDrawing([...stroke.current]);
  };
  const anchor = useRef<number[]>([]);
  const shapeDown = (e: PointerEvent<HTMLCanvasElement>) => {
    anchor.current = point(e);
    down(e);
  };
  const shapeMove = (e: PointerEvent<HTMLCanvasElement>) => {
    if (!isDrawing.current) return;
    if (tool === 'pen') {
      move(e);
      return;
    }
    const p = point(e),
      a = anchor.current;
    if (tool === 'rectangle') stroke.current = [a, [p[0], a[1]], p, [a[0], p[1]]];
    else {
      const cx = (p[0] + a[0]) / 2,
        cy = (p[1] + a[1]) / 2;
      stroke.current = Array.from({ length: 64 }, (_, i) => [
        cx + (Math.abs(p[0] - a[0]) / 2) * Math.cos((i * Math.PI) / 32),
        cy + (Math.abs(p[1] - a[1]) / 2) * Math.sin((i * Math.PI) / 32),
      ]);
    }
    setDrawing([...stroke.current]);
  };
  const up = () => {
    if (!isDrawing.current) return;
    isDrawing.current = false;
    const completed = stroke.current.map((point) => [...point]);
    if (completed.length >= 3) setPaths((p) => [...p, completed]);
    setDrawing([]);
    stroke.current = [];
  };
  return (
    <Modal title="画下来，就能做出来" eyebrow="SKETCH TO SOLID" onClose={onClose} wide>
      <p className="modal-intro">
        画一个封闭的外轮廓，我们帮你拉伸成实体。内部再画一圈，就能开孔。
      </p>
      <div className="sketch-tools">
        <div>
          {[
            { key: 'pen', icon: Pencil, label: '画笔' },
            { key: 'rectangle', icon: Square, label: '矩形' },
            { key: 'circle', icon: Circle, label: '椭圆' },
          ].map(({ key, icon: Icon, label }) => (
            <button
              key={key}
              className={'tool-button ' + (tool === key ? 'selected' : '')}
              onClick={() => setTool(key)}
            >
              <Icon size={16} />
              {label}
            </button>
          ))}
        </div>
        <div>
          <button
            className="icon-button"
            aria-label="撤销上一个轮廓"
            disabled={!paths.length}
            onClick={() => setPaths((p) => p.slice(0, -1))}
          >
            <RotateCcw size={17} />
          </button>
          <button
            className="icon-button"
            aria-label="清空草图"
            disabled={!paths.length}
            onClick={() => setPaths([])}
          >
            <Trash2 size={17} />
          </button>
          <button className="tool-button" onClick={() => fileRef.current?.click()}>
            <Upload size={15} />
            参考图
          </button>
        </div>
      </div>
      <div className="sketch-canvas" ref={container}>
        {reference && <img className="sketch-reference" src={reference} alt="描摹参考图" />}
        <canvas
          aria-label="草图画布，按住鼠标或手指绘制"
          ref={canvas}
          width={640}
          height={420}
          onPointerDown={shapeDown}
          onPointerMove={shapeMove}
          onPointerUp={up}
          onPointerCancel={() => {
            isDrawing.current = false;
            setDrawing([]);
          }}
        />
        {!paths.length && !drawing.length && (
          <div className="sketch-empty">
            <MousePointer2 size={25} />
            <strong>在这里画下你的想法</strong>
            <span>松开鼠标，轮廓会自动闭合</span>
          </div>
        )}
        <span className="sketch-count">{paths.length} 个轮廓 · 自动闭合</span>
      </div>
      <input
        hidden
        type="file"
        accept="image/png,image/jpeg,image/webp"
        ref={fileRef}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (!file) return;
          if (file.size > 8 * 1024 * 1024) {
            setError('参考图请小于 8 MB。');
            return;
          }
          const reader = new FileReader();
          reader.onload = () => setReference(String(reader.result));
          reader.readAsDataURL(file);
          e.target.value = '';
        }}
      />
      {error && (
        <p role="alert" className="error-inline">
          {error}
        </p>
      )}
      <div className="sketch-footer">
        <span>
          <CornerDownLeft size={15} />
          草图将沿厚度方向拉伸，可在生成后调整尺寸
        </span>
        <button className="button primary" disabled={!paths.length} onClick={() => onApply(paths)}>
          <Check size={17} />
          使用这张草图
        </button>
      </div>
    </Modal>
  );
}
