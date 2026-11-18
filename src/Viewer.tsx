import { Component, Suspense, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { Canvas, useLoader, useThree, useFrame } from '@react-three/fiber';
import { OrbitControls, Grid } from '@react-three/drei';
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js';
import { mergeVertices } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import { Box3, Vector3, ACESFilmicToneMapping } from 'three';
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib';
import { Box, RotateCcw } from 'lucide-react';
import type { Model } from './types';

class ViewerBoundary extends Component<
  { children: ReactNode; onRetry: () => void },
  { error: boolean }
> {
  state = { error: false };
  static getDerivedStateFromError() {
    return { error: true };
  }
  render() {
    return this.state.error ? (
      <div className="viewer-fallback">
        <Box size={36} />
        <h3>预览暂时无法显示</h3>
        <p>模型文件仍可下载。请使用支持 WebGL 的浏览器。</p>
        <button className="button secondary" onClick={this.props.onRetry}>
          <RotateCcw size={15} />
          重新加载预览
        </button>
      </div>
    ) : (
      this.props.children
    );
  }
}

function Solid({
  model,
  color,
  wireframe,
  onThumbnail,
}: {
  model: Model;
  color: string;
  wireframe: boolean;
  onThumbnail: (id: string, data: string) => void;
}) {
  const raw = useLoader(STLLoader, model.stats.print_ready === false ? `/api/models/${model.id}/preview.stl` : `/api/models/${model.id}/download/stl`);
  const geometry = useMemo(() => {
    let geo = raw.clone();
    if (model.recipe.category === 'figurine' || model.recipe.kind === 'neural') {
      geo.deleteAttribute('normal');
      const merged = mergeVertices(geo, 0.0001);
      geo.dispose();
      geo = merged;
      geo.computeVertexNormals();
    }
    geo.rotateX(-Math.PI / 2);
    geo.computeBoundingBox();
    const bounds = geo.boundingBox as Box3;
    const size = bounds.getSize(new Vector3());
    const center = bounds.getCenter(new Vector3());
    geo.translate(-center.x, -bounds.min.y, -center.z);
    const scale = 3.1 / Math.max(size.x, size.y, size.z);
    geo.scale(scale, scale, scale);
    return geo;
  }, [raw, model.recipe.category]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  const frameCount = useRef(0);
  const captured = useRef('');
  useEffect(() => {
    frameCount.current = 0;
  }, [model.id]);
  useFrame(({ gl, invalidate }) => {
    if (model.thumbnail || captured.current === model.id || wireframe) return;
    if (++frameCount.current < 12) {
      invalidate();
      return;
    }
    captured.current = model.id;
    requestAnimationFrame(() => {
      try {
        const canvas = document.createElement('canvas');
        canvas.width = 320;
        canvas.height = 260;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;
        const src = gl.domElement;
        const scale = Math.min(320 / src.width, 260 / src.height);
        const w = src.width * scale,
          h = src.height * scale;
        ctx.drawImage(src, (320 - w) / 2, (260 - h) / 2, w, h);
        onThumbnail(model.id, canvas.toDataURL('image/png'));
      } catch {
        /* Downloading geometry remains available without a thumbnail. */
      }
    });
  });
  return (
    <mesh castShadow receiveShadow geometry={geometry}>
      <meshStandardMaterial
        color={color}
        roughness={0.52}
        metalness={0.025}
        wireframe={wireframe}
      />
    </mesh>
  );
}

function CameraRig({
  view,
  reset,
  rotate,
  dimensions,
}: {
  view: string;
  reset: number;
  rotate: boolean;
  dimensions: number[];
}) {
  const controls = useRef<OrbitControlsImpl>(null);
  const { camera } = useThree();
  const height = (dimensions[2] / Math.max(...dimensions)) * 3.1;
  const target = height * 0.48;
  useEffect(() => {
    const positions: Record<string, number[]> = {
      perspective: [4.2, target + (height < 1 ? 4.5 : 2.5), 6.2],
      front: [0, target, 7.5],
      side: [7.5, target, 0],
      top: [0, target + 9, 0.001],
    };
    camera.position.set(...(positions[view] as [number, number, number]));
    controls.current?.target.set(0, target, 0);
    controls.current?.update();
  }, [camera, view, reset, target, height]);
  return (
    <OrbitControls
      ref={controls}
      makeDefault
      target={[0, target, 0]}
      enableDamping
      dampingFactor={0.08}
      autoRotate={rotate}
      autoRotateSpeed={1.3}
      minDistance={2}
      maxDistance={18}
      maxPolarAngle={Math.PI * 0.49}
    />
  );
}

export default function Viewer({
  model,
  color,
  wireframe,
  grid,
  rotate,
  view,
  reset,
  onThumbnail,
}: {
  model: Model | null;
  color: string;
  wireframe: boolean;
  grid: boolean;
  rotate: boolean;
  view: string;
  reset: number;
  onThumbnail: (id: string, data: string) => void;
}) {
  const [retry, setRetry] = useState(0);
  return (
    <ViewerBoundary key={`${model?.id}-${retry}`} onRetry={() => setRetry((v) => v + 1)}>
      <Canvas
        frameloop={rotate ? 'always' : 'demand'}
        shadows
        dpr={[1, 1.8]}
        camera={{ position: [4.2, 3.2, 6.2], fov: 33, near: 0.1, far: 100 }}
        gl={{
          antialias: true,
          alpha: true,
          toneMapping: ACESFilmicToneMapping,
          preserveDrawingBuffer: true,
        }}
        onCreated={({ gl }) => {
          gl.setClearColor('#f5f4f8', 0);
        }}
      >
        <ambientLight intensity={0.8} />
        <hemisphereLight args={['#ffffff', '#a3a0b4', 1.1]} />
        <directionalLight
          position={[-3, 7, 5]}
          intensity={2.4}
          castShadow
          shadow-mapSize={[2048, 2048]}
          shadow-radius={4}
          shadow-camera-left={-6}
          shadow-camera-right={6}
          shadow-camera-top={6}
          shadow-camera-bottom={-6}
          shadow-bias={-0.0003}
        />
        <directionalLight position={[5, 3, -3]} color="#d8d6ff" intensity={1.5} />
        <directionalLight position={[-5, 2, -4]} intensity={0.8} />
        <Suspense fallback={null}>
          {model && (
            <Solid model={model} color={color} wireframe={wireframe} onThumbnail={onThumbnail} />
          )}
        </Suspense>
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.018, 0]} receiveShadow>
          <planeGeometry args={[200, 200]} />
          <shadowMaterial transparent opacity={0.11} />
        </mesh>
        {grid && (
          <Grid
            position={[0, -0.012, 0]}
            args={[16, 16]}
            cellSize={0.5}
            cellThickness={0.45}
            cellColor="#d6d3df"
            sectionSize={2.5}
            sectionThickness={0.6}
            sectionColor="#c7c3d3"
            fadeDistance={13}
            fadeStrength={1.8}
            infiniteGrid
          />
        )}
        <CameraRig
          view={view}
          reset={reset}
          rotate={rotate}
          dimensions={model?.stats.dimensions || [50, 50, 65]}
        />
      </Canvas>
    </ViewerBoundary>
  );
}
