export type Mode = 'auto' | 'figurine' | 'part' | 'sketch';
export type Engine = 'blender' | 'neural' | 'parametric' | 'meshy';
export type Paths = number[][][];
export interface Recipe {
  kind: string;
  category: string;
  name: string;
  params: Record<string, number | boolean>;
  prompt: string;
  edits?: string[];
  sketch?: Paths;
  reference?: string;
  source_job?: string;
  scene?: unknown[];
  mesh?: string;
  seed?: number;
  generator?: string;
  translated_prompt?: string;
  generation_prompt?: string;
  code?: string;
  summary?: string;
  attempts?: number;
  detail?: 'draft' | 'fine';
  refinement?: 'skipped' | 'reviewed' | 'refined' | 'retained';
  review?: string;
}
export interface Model {
  id: string;
  name: string;
  created_at: number;
  recipe: Recipe;
  thumbnail?: boolean;
  stats: {
    dimensions: number[];
    volume_cm3: number;
    triangles: number;
    watertight: boolean;
    components: number;
    warnings: string[];
    units: string;
    print_ready?: boolean;
  };
}
export interface Job {
  id: string;
  status: 'queued' | 'running' | 'complete' | 'error' | 'cancelled';
  stage: string;
  progress: number;
  model?: Model;
  error?: string;
  error_code?: string;
  engine?: Engine;
  elapsed_seconds?: number;
  remaining_seconds?: number;
}
export interface CatalogItem {
  kind: string;
  name: string;
  category: 'figurine' | 'part';
  prompt: string;
}
export interface Settings {
  enabled: boolean;
  base_url: string;
  model: string;
  has_key: boolean;
  has_meshy_key?: boolean;
  meshy_texture?: boolean;
}
export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch('/api' + path, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...options?.headers },
    });
  } catch {
    throw new Error('暂时连接不到本地建模服务。请重新运行「启动小造.cmd」后重试。');
  }
  if (!response.ok) {
    let data;
    try {
      data = await response.json();
    } catch {
      /* HTML proxy errors */
    }
    throw new Error(
      typeof data?.detail === 'string'
        ? data.detail
        : `请求没有完成（${response.status}），请稍后重试。`,
    );
  }
  return response.json();
}
