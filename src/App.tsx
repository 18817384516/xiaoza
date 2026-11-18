import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import type { ChangeEvent, KeyboardEvent } from 'react';
import {
  ArrowDownToLine,
  ArrowRight,
  Box,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Command,
  Cuboid,
  Download,
  FileCheck2,
  FileJson,
  FolderOpen,
  Grid2X2,
  Info,
  Layers3,
  Loader2,
  Maximize,
  MessageSquareText,
  MoreHorizontal,
  MousePointer2,
  PackageCheck,
  Pencil,
  Plus,
  Printer,
  RotateCcw,
  RotateCw,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  Upload,
  WandSparkles,
  X,
} from 'lucide-react';
import Modal from './Modal';
import Sketch from './Sketch';
import { api } from './types';
import type { CatalogItem, Engine, Job, Mode, Model, Paths, Recipe, Settings } from './types';

const Viewer = lazy(() => import('./Viewer'));
const EXAMPLES = [
  {
    kind: 'bunny',
    name: '治愈系小兔',
    tag: '软萌摆件',
    prompt: '一只圆滚滚的小兔，耳朵长一点，带底座，高65毫米',
    color: 'lilac',
  },
  {
    kind: 'bracket',
    name: 'L 型安装支架',
    tag: '实用零件',
    prompt: 'L型支架，宽50毫米，深40毫米，高40毫米，厚4毫米，4个孔，孔径5毫米',
    color: 'blue',
  },
  {
    kind: 'vase',
    name: '一只桌面花瓶',
    tag: '生活灵感',
    prompt: '一个桌面花瓶，外径46毫米，高70毫米，壁厚2.4毫米',
    color: 'peach',
  },
];
const COLORS = ['#b6a0e4', '#e8c7a5', '#91b6b0', '#91aec9', '#e3a5a5', '#e9e6df'];
const FREE_EXAMPLES = [
  { kind: 'avocado-chair', name: '牛油果形状的椅子', tag: '把两种想法合在一起',
    prompt: '一把牛油果形状的椅子，圆润的椅背，果核形状的坐垫', color: 'lilac' },
  { kind: 'mushroom-house', name: '蘑菇里的小房子', tag: '童话里的新物件',
    prompt: '一个蘑菇形状的小房子，圆形小门，宽大的蘑菇帽屋顶', color: 'peach' },
  { kind: 'spaceship', name: '一艘圆润的小飞船', tag: '想象中的造型',
    prompt: '一艘圆润的小型宇宙飞船，有三个短短的着陆腿', color: 'blue' },
];
const LABELS: Record<string, string> = {
  height: '高度',
  width: '宽度 / 外径',
  depth: '深度',
  thickness: '壁厚',
  hole_diameter: '孔径',
  tolerance: '孔径补偿',
  teeth: '齿数',
  holes: '安装孔',
  ear_scale: '耳朵大小',
  head_scale: '脑袋大小',
  belly_scale: '圆润程度',
  base: '平稳底座',
};
const LIMITS: Record<string, [number, number, number]> = {
  height: [5, 250, 1],
  width: [5, 250, 1],
  depth: [5, 250, 1],
  thickness: [1.2, 20, 0.2],
  hole_diameter: [0, 100, 0.1],
  tolerance: [0, 1, 0.05],
  teeth: [8, 80, 1],
  holes: [0, 4, 2],
  ear_scale: [0.65, 1.4, 0.05],
  head_scale: [0.65, 1.4, 0.05],
  belly_scale: [0.65, 1.4, 0.05],
};
type GenerateBody = {
  prompt: string;
  mode?: Mode;
  params?: Record<string, number | boolean>;
  previous?: Recipe;
  sketch?: Paths;
  engine?: Engine;
  steps?: number;
  regenerate?: boolean;
  resume_job?: string;
  detail?: 'draft' | 'fine';
  reference?: string;
};

const engineFor = (recipe: Recipe): Engine =>
  ['blender', 'neural', 'meshy'].includes(recipe.kind) ? recipe.kind as Engine : 'parametric';

function Logo({ small = false }: { small?: boolean }) {
  return (
    <div className={'brand-mark ' + (small ? 'small' : '')}>
      <svg viewBox="0 0 32 32" fill="none" aria-hidden="true">
        <path
          d="m7 10 9-5 9 5v12l-9 5-9-5V10Z"
          stroke="currentColor"
          strokeWidth="1.9"
          strokeLinejoin="round"
        />
        <path
          d="m7 10 9 5 9-5M16 15v12"
          stroke="currentColor"
          strokeWidth="1.9"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
}

function MiniArt({ kind }: { kind: string }) {
  if (
    kind === 'bunny' ||
    ['cat', 'bear', 'dog', 'fox', 'pig', 'penguin', 'duck', 'frog', 'turtle'].includes(kind)
  )
    return (
      <svg viewBox="0 0 150 115" className="mini-art" aria-hidden="true">
        <defs>
          <linearGradient id={'b' + kind} x1="0" y1="0" x2="1" y2="1">
            <stop stopColor="#e2d6fb" />
            <stop offset="1" stopColor="#a28bd3" />
          </linearGradient>
        </defs>
        <ellipse cx="77" cy="99" rx="35" ry="7" fill="#8b75be" opacity=".12" />
        <ellipse cx="75" cy="75" rx="24" ry="25" fill={'url(#b' + kind + ')'} />
        <ellipse cx="61" cy="93" rx="13" ry="7" fill="#baa5e1" />
        <ellipse cx="89" cy="93" rx="13" ry="7" fill="#baa5e1" />
        <ellipse
          cx="61"
          cy="29"
          rx="8"
          ry="24"
          transform="rotate(-10 61 29)"
          fill={'url(#b' + kind + ')'}
        />
        <ellipse
          cx="88"
          cy="29"
          rx="8"
          ry="24"
          transform="rotate(9 88 29)"
          fill={'url(#b' + kind + ')'}
        />
        <ellipse cx="75" cy="53" rx="27" ry="22" fill={'url(#b' + kind + ')'} />
        <circle cx="66" cy="53" r="2" fill="#655278" />
        <circle cx="84" cy="53" r="2" fill="#655278" />
        <path
          d="m73 60 2 2 2-2"
          stroke="#79658c"
          strokeWidth="1.5"
          fill="none"
          strokeLinecap="round"
        />
      </svg>
    );
  if (kind === 'bracket' || kind === 'plate')
    return (
      <svg viewBox="0 0 150 115" className="mini-art" aria-hidden="true">
        <ellipse cx="78" cy="98" rx="42" ry="7" fill="#7993b7" opacity=".1" />
        <path d="m39 78 41-20 35 16-42 22Z" fill="#a8bedb" />
        <path d="M80 24 115 40v34L80 58Z" fill="#94adcf" />
        <path d="m80 24 7-4 35 16-7 4Z" fill="#d1e0ef" />
        <path d="m115 40 7-4v42L73 101v-5l42-22Z" fill="#6f8eb6" />
        <ellipse cx="95" cy="45" rx="3.7" ry="5" transform="rotate(-24 95 45)" fill="#526e98" />
        <ellipse cx="106" cy="61" rx="3.7" ry="5" transform="rotate(-24 106 61)" fill="#526e98" />
        <ellipse cx="62" cy="79" rx="5" ry="2.3" transform="rotate(-24 62 79)" fill="#6a89b3" />
        <ellipse cx="86" cy="82" rx="5" ry="2.3" transform="rotate(-24 86 82)" fill="#6a89b3" />
      </svg>
    );
  if (kind === 'vase' || kind === 'box')
    return (
      <svg viewBox="0 0 150 115" className="mini-art" aria-hidden="true">
        <defs>
          <linearGradient id="vase-gradient">
            <stop stopColor="#f0d6c3" />
            <stop offset=".45" stopColor="#e8baa0" />
            <stop offset="1" stopColor="#c79178" />
          </linearGradient>
        </defs>
        <ellipse cx="75" cy="100" rx="30" ry="6" fill="#b78063" opacity=".12" />
        <path
          d="M59 22h32c-3 26 14 31 13 52-1 24-57 24-58 0-1-21 16-26 13-52Z"
          fill="url(#vase-gradient)"
        />
        <ellipse cx="75" cy="22" rx="16" ry="5" fill="#edc7af" />
        <ellipse cx="75" cy="22" rx="12" ry="3" fill="#a87560" />
        <path
          d="M56 62c-4 15 0 22 4 25"
          stroke="#f7e0cf"
          strokeWidth="2"
          fill="none"
          opacity=".6"
        />
      </svg>
    );
  return (
    <div className="mini-generic">
      <Cuboid size={44} strokeWidth={1.1} />
    </div>
  );
}

export default function App() {
  const [page, setPage] = useState<'studio' | 'library'>('studio');
  const [model, setModel] = useState<Model | null>(null);
  const [models, setModels] = useState<Model[]>([]);
  const [prompt, setPrompt] = useState(FREE_EXAMPLES[0].prompt);
  const [engine, setEngine] = useState<Engine>('blender');
  const [quality, setQuality] = useState(32);
  const [blenderDetail, setBlenderDetail] = useState<'draft' | 'fine'>('fine');
  const [generatorReady, setGeneratorReady] = useState<boolean | null>(null);
  const [blenderReady, setBlenderReady] = useState<boolean | null>(null);
  const [mode, setMode] = useState<Mode>('auto');
  const [sketch, setSketch] = useState<Paths>([]);
  const [reference, setReference] = useState('');
  const [busy, setBusy] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState('');
  const [errorCode, setErrorCode] = useState('');
  const [online, setOnline] = useState(false);
  const [ready, setReady] = useState(false);
  const [params, setParams] = useState<Record<string, number | boolean>>({});
  const [dirty, setDirty] = useState(false);
  const [color, setColor] = useState(COLORS[0]);
  const [grid, setGrid] = useState(true);
  const [wireframe, setWireframe] = useState(false);
  const [rotate, setRotate] = useState(false);
  const [view, setView] = useState('perspective');
  const [reset, setReset] = useState(0);
  const [modal, setModal] = useState<'sketch' | 'export' | 'settings' | 'help' | 'catalog' | null>(null);
  const [settings, setSettings] = useState<Settings>({
    enabled: false,
    base_url: 'https://api.openai.com/v1',
    model: 'gpt-4.1-mini',
    has_key: false,
  });
  const [revision, setRevision] = useState('');
  const [toast, setToast] = useState('');
  const [search, setSearch] = useState('');
  const [deleteTarget, setDeleteTarget] = useState<Model | null>(null);
  const jobRef = useRef<string | null>(null);
  const token = useRef(0);
  const fileRef = useRef<HTMLInputElement>(null);
  const referenceRef = useRef<HTMLInputElement>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const promptRef = useRef<HTMLTextAreaElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const toastTimer = useRef<number | undefined>(undefined);
  const notify = useCallback((message: string) => {
    setToast(message);
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(''), 3800);
  }, []);
  const selectModel = useCallback((m: Model) => {
    setModel(m);
    setParams({ ...m.recipe.params });
    setDirty(false);
    setView('perspective');
    setReset((v) => v + 1);
    setError('');
    setBlenderDetail(m.recipe.detail || 'fine');
    setReference(m.recipe.reference || '');
  }, []);
  const saveThumbnail = useCallback(async (id: string, data: string) => {
    try {
      await api(`/models/${id}/thumbnail`, {
        method: 'POST',
        body: JSON.stringify({ image: data }),
      });
      setModels((ms) => ms.map((m) => (m.id === id ? { ...m, thumbnail: true } : m)));
    } catch {
      /* A missing thumbnail does not block editing. */
    }
  }, []);

  const generate = useCallback(
    async (body: GenerateBody, resumeId?: string) => {
      const current = ++token.current;
      setBusy(true);
      setError('');
      setErrorCode('');
      setJob({ id: '', status: 'queued', progress: 3, stage: '准备建模' });
      try {
        const result = resumeId ? { id: resumeId } : await api<{ id: string }>('/generate', {
          method: 'POST',
          body: JSON.stringify(body),
        });
        if (current !== token.current) {
          await api(`/jobs/${result.id}`, { method: 'DELETE' });
          return;
        }
        jobRef.current = result.id;
        localStorage.setItem('xiaozao.active-job', result.id);
        const start = Date.now();
        while (current === token.current) {
          const status = await api<Job>(`/jobs/${result.id}`);
          if (current !== token.current) return;
          setJob(status);
          if (status.status === 'complete' && status.model) {
            selectModel(status.model);
            setPrompt(status.model.recipe.prompt);
            setSketch(status.model.recipe.sketch || []);
            setEngine(engineFor(status.model.recipe));
            setModels((list) => [status.model!, ...list.filter((m) => m.id !== status.model!.id)]);
            setOnline(true);
            notify('模型已生成，并自动保存到作品库');
            if (window.innerWidth <= 760) {
              requestAnimationFrame(() =>
                viewportRef.current?.scrollIntoView({
                  behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches
                    ? 'auto'
                    : 'smooth',
                  block: 'start',
                }),
              );
            }
            break;
          }
          if (status.status === 'error') {
            setErrorCode(status.error_code || '');
            throw new Error(status.error || '生成未完成，请重试。');
          }
          if (status.status === 'cancelled') break;
          if (Date.now() - start > (status.engine === 'neural' ? 21_600_000 : ['blender','meshy'].includes(status.engine || '') ? 3_600_000 : 180000)) {
            await api(`/jobs/${result.id}`, { method: 'DELETE' });
            throw new Error('建模用时较长，已停止。请简化描述后重试。');
          }
          await new Promise((r) => window.setTimeout(r, 400));
        }
      } catch (e) {
        if (current === token.current)
          setError(e instanceof Error ? e.message : '生成未完成，请重试。');
      } finally {
        if (current === token.current) {
          setBusy(false);
          jobRef.current = null;
          localStorage.removeItem('xiaozao.active-job');
        }
      }
    },
    [notify, selectModel],
  );

  useEffect(() => {
    let active = true;
    Promise.all([api<Model[]>('/models'), api<Settings>('/settings'), api<{ready: boolean}>('/generator'), api<{ready: boolean}>('/blender')])
      .then(([history, config, generator, blender]) => {
        if (!active) return;
        setModels(history);
        setSettings(config);
        setGeneratorReady(generator.ready);
        setBlenderReady(blender.ready);
        setOnline(true);
        setReady(true);
        if (history.length) {
          selectModel(history[0]);
          setPrompt(history[0].recipe.prompt);
          setSketch(history[0].recipe.sketch || []);
        }
        const pending = localStorage.getItem('xiaozao.active-job');
        if (pending) void generate({ prompt: '' }, pending);
      })
      .catch((e) => {
        if (active) {
          setError(e.message);
          setReady(true);
        }
      });
    return () => {
      active = false;
    };
  }, [generate, selectModel]);
  useEffect(() => {
    const key = (e: globalThis.KeyboardEvent) => {
      if (
        (e.ctrlKey || e.metaKey) &&
        e.key === 'Enter' &&
        !document.querySelector('[role="dialog"]')
      ) {
        e.preventDefault();
        if (!busy && ready) {
          const same =
            model &&
            (engine === 'blender') === (model.recipe.kind === 'blender') &&
            (engine === 'neural') === (model.recipe.kind === 'neural') &&
            (engine === 'meshy') === (model.recipe.kind === 'meshy') &&
            prompt === model.recipe.prompt &&
            reference === (model.recipe.reference || '') &&
            ((!sketch.length && !model.recipe.sketch) || sketch === model.recipe.sketch);
          void generate({
            prompt,
            engine,
            steps: quality,
            detail: blenderDetail,
            reference: reference || undefined,
            regenerate: engine !== 'parametric',
            mode,
            sketch: sketch.length ? sketch : undefined,
            ...(same ? { previous: model.recipe, params } : {}),
          });
        }
      }
    };
    window.addEventListener('keydown', key);
    return () => window.removeEventListener('keydown', key);
  }, [busy, ready, prompt, mode, sketch, reference, generate, model, params, engine, quality, blenderDetail]);
  useEffect(() => {
    if (error) errorRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [error]);
  const cancel = async () => {
    ++token.current;
    const id = jobRef.current;
    jobRef.current = null;
    setBusy(false);
    setJob(null);
    localStorage.removeItem('xiaozao.active-job');
    if (id) {
      try {
        await api(`/jobs/${id}`, { method: 'DELETE' });
      } catch {
        /* UI already cancelled */
      }
    }
    notify('已停止生成，你可以继续修改');
  };
  const run = () => {
    if (!busy) {
      const same =
        model &&
        (engine === 'blender') === (model.recipe.kind === 'blender') &&
        (engine === 'neural') === (model.recipe.kind === 'neural') &&
        (engine === 'meshy') === (model.recipe.kind === 'meshy') &&
        prompt === model.recipe.prompt &&
        reference === (model.recipe.reference || '') &&
        ((!sketch.length && !model.recipe.sketch) || sketch === model.recipe.sketch);
      void generate({
        prompt,
        engine,
        steps: quality,
        detail: blenderDetail,
        reference: reference || undefined,
        regenerate: engine !== 'parametric',
        mode,
        sketch: sketch.length ? sketch : undefined,
        ...(same ? { previous: model.recipe, params } : {}),
      });
    }
  };
  const applyParams = () => {
    if (model && !busy)
      void generate({
        prompt: model.recipe.prompt,
        mode: 'auto',
        previous: model.recipe,
        params,
        sketch: model.recipe.sketch,
      });
  };
  const refine = (text = revision, detail = blenderDetail) => {
    if (model && text.trim() && !busy) {
      if (model.recipe.kind === 'meshy') {
        setPrompt(text);
        notify('专业形象模式修改描述会重新创造；确认描述后点击生成');
        return;
      }
      void generate({ prompt: text, previous: model.recipe, mode: 'auto', engine: engineFor(model.recipe), steps: quality, detail, reference: model.recipe.reference });
      setRevision('');
    }
  };
  const updateParam = (key: string, value: number | boolean) => {
    setParams((p) => ({ ...p, [key]: value }));
    setDirty(true);
  };
  const newProject = () => {
    if (busy) return;
    setPage('studio');
    setPrompt('');
    setSketch([]);
    setReference('');
    setMode('auto');
    setEngine('blender');
    setBlenderDetail('fine');
    setError('');
    setErrorCode('');
    setModel(null);
    setParams({});
    setDirty(false);
    setRevision('');
    window.setTimeout(() => promptRef.current?.focus(), 0);
    notify('写下新想法，已有模型可以在作品库找到');
  };
  const importProject = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    try {
      if (file.size > 10_000_000) throw new Error('项目文件过大，请选择小造导出的 JSON 项目。');
      const data = JSON.parse(await file.text());
      const recipe = data.recipe;
      if (!recipe || !recipe.kind || !recipe.params || typeof recipe.prompt !== 'string')
        throw new Error('这不是有效的小造项目，请选择导出的 JSON 文件。');
      setPage('studio');
      setPrompt(recipe.prompt);
      setSketch(recipe.sketch || []);
      await generate({
        prompt: recipe.prompt,
        previous: recipe,
        params: recipe.params,
        sketch: recipe.sketch,
        reference: recipe.reference,
      });
    } catch (e) {
      setErrorCode('');
      setError(
        e instanceof SyntaxError
          ? '这个文件不是有效的小造 JSON 项目，请重新选择。'
          : e instanceof Error
            ? e.message
            : '项目读取失败。',
      );
    }
  };
  const attachReference = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    try {
      if (!['image/png','image/jpeg','image/webp'].includes(file.type) || file.size > 10_000_000)
        throw new Error('请选择10 MB以内的 PNG、JPG 或 WebP 参考图。');
      const bitmap = await createImageBitmap(file);
      try {
        if (Math.min(bitmap.width, bitmap.height) < 32) throw new Error('参考图至少需要32×32像素。');
        const ratio = Math.min(1, 1536 / Math.max(bitmap.width, bitmap.height));
        const canvas = document.createElement('canvas');
        canvas.width = Math.round(bitmap.width * ratio);
        canvas.height = Math.round(bitmap.height * ratio);
        const context = canvas.getContext('2d');
        if (!context) throw new Error('图片无法读取，请重新选择。');
        context.fillStyle = '#ffffff';
        context.fillRect(0,0,canvas.width,canvas.height);
        context.drawImage(bitmap,0,0,canvas.width,canvas.height);
        setReference(canvas.toDataURL('image/jpeg',.92));
        notify('参考图已添加，生成时将发送至所选服务');
      } finally { bitmap.close(); }
    } catch (error) { notify((error as Error).message); }
  };
  const openModel = (m: Model) => {
    if (busy) return;
    selectModel(m);
    setPrompt(m.recipe.prompt);
    setSketch(m.recipe.sketch || []);
    setEngine(engineFor(m.recipe));
    setPage('studio');
  };
  const chooseExample = (example: (typeof EXAMPLES)[number], targetEngine: Engine = 'parametric') => {
    if (busy) return;
    setPrompt(example.prompt);
    setSketch([]);
    setReference('');
    setMode('auto');
    setEngine(targetEngine);
    setColor(
      example.kind === 'bracket' ? COLORS[3] : example.kind === 'vase' ? COLORS[1] : COLORS[0],
    );
    if (targetEngine !== 'parametric') {
      setError('');
      notify('想法已填入，可以自由修改后点击生成');
      promptRef.current?.focus();
    } else void generate({ prompt: example.prompt });
  };
  const deleteModel = async () => {
    if (!deleteTarget) return;
    try {
      await api(`/models/${deleteTarget.id}`, { method: 'DELETE' });
      setModels((ms) => ms.filter((m) => m.id !== deleteTarget.id));
      if (model?.id === deleteTarget.id) {
        setModel(null);
        setParams({});
      }
      setDeleteTarget(null);
      notify('作品已删除');
    } catch (e) {
      notify((e as Error).message);
    }
  };
  const fullscreen = async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await viewportRef.current?.requestFullscreen();
    } catch {
      notify('浏览器没有允许全屏显示');
    }
  };
  const revisions =
    model?.recipe.category === 'figurine'
      ? [
          ['ear_scale', '耳朵大一点'],
          ['head_scale', '脑袋大一点'],
          ['belly_scale', '肚子小一点'],
        ]
          .filter(([key]) => key in model.recipe.params)
          .map(([, label]) => label)
      : [];

  return (
    <div className="app-shell">
      <aside className="rail">
        <a
          href="#"
          className="logo-link"
          aria-label="小造首页"
          onClick={(e) => {
            e.preventDefault();
            setPage('studio');
          }}
        >
          <Logo />
        </a>
        <nav aria-label="主导航">
          <button
            aria-label="创作工作台"
            title="创作工作台"
            className={'rail-item ' + (page === 'studio' ? 'active' : '')}
            onClick={() => setPage('studio')}
          >
            <WandSparkles size={21} />
            <span>创作</span>
          </button>
          <button
            aria-label="我的作品"
            title="我的作品"
            className={'rail-item ' + (page === 'library' ? 'active' : '')}
            onClick={() => setPage('library')}
          >
            <Layers3 size={21} />
            <span>作品</span>
          </button>
        </nav>
        <div className="rail-bottom">
          <button
            className="rail-item"
            aria-label="使用指南"
            title="使用指南"
            onClick={() => setModal('help')}
          >
            <CircleHelp size={21} />
          </button>
          <button
            className="rail-item"
            aria-label="设置"
            title="设置"
            onClick={() => setModal('settings')}
          >
            <Settings2 size={21} />
          </button>
          <div className="avatar">我</div>
        </div>
      </aside>
      <div className="app-body">
        <header className="topbar">
          <div className="brand-text">
            小造
            <span className="brand-divider" />
            <span className="brand-sub">你的想法，值得被创造</span>
          </div>
          <div className="topbar-actions">
            <span className={'connection ' + (online ? 'connected' : '')}>
              <i />
              {online
                ? engine === 'blender'
                  ? '大模型 + 本地 Blender'
                  : engine === 'meshy'
                  ? '专业3D形象 · 云端生成'
                  : engine === 'neural'
                  ? '本地 AI · 自由创造'
                  : '本地建模 · 无需密钥'
                : '连接本地服务中'}
            </span>
            <button className="button small secondary" onClick={newProject} disabled={busy}>
              <Plus size={16} />
              新建作品
            </button>
          </div>
        </header>
        <main>
          {page === 'studio' ? (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">
                    <span className="eyebrow-line" /> A LITTLE IDEA. A REAL THING.
                  </div>
                  <h1>
                    让想法，<span>有形状。</span>
                  </h1>
                  <p>说出脑海中的样子，把下一件喜欢的东西，亲手造出来。</p>
                </div>
                <div className="workflow">
                  <span className="step current">
                    <b>1</b>描述想法
                  </span>
                  <ChevronRight size={14} />
                  <span className={'step ' + (model ? 'current' : '')}>
                    <b>2</b>调整模型
                  </span>
                  <ChevronRight size={14} />
                  <span className="step">
                    <b>3</b>打印成真
                  </span>
                </div>
              </div>
              {error && (
                <div className="error-banner recovery-banner" role="alert" ref={errorRef}>
                  <Info size={18} />
                  <div>
                    <strong>
                      {errorCode === 'unsupported_description'
                        ? '当前本地模式还做不了这个模型'
                        : '生成未完成，请检查后重试'}
                    </strong>
                    <p>{error}</p>
                    {errorCode === 'unsupported_description' && (
                      <div className="recovery-actions">
                        <button className="button primary small" onClick={() => {
                          setEngine('blender');
                          setError('');
                          setErrorCode('');
                          notify('描述已保留，可以自由补充后点击生成');
                        }}>
                          <WandSparkles size={14} />改用自由创造
                        </button>
                        <button className="button secondary small" onClick={() => setModal('catalog')}>
                          查看可生成的模型
                        </button>
                        <button className="button secondary small" onClick={() => setModal('sketch')}>
                          <Pencil size={14} />画轮廓并拉伸
                        </button>
                        <button className="button secondary small" onClick={() => setModal('settings')}>
                          <Settings2 size={14} />连接 AI
                        </button>
                      </div>
                    )}
                    {errorCode.startsWith('blender_') && (
                      <div className="recovery-actions">
                        <button className="button secondary small" disabled={busy} onClick={() => {
                          if (job?.id && ['blender_ai_connection', 'blender_ai_timeout', 'blender_ai_response', 'blender_validation_failed'].includes(errorCode))
                            void generate({ prompt: '', engine: 'blender', resume_job: job.id });
                          else run();
                        }}>{errorCode === 'blender_validation_failed' ? '继续修复' : ['blender_ai_connection', 'blender_ai_timeout', 'blender_ai_response'].includes(errorCode) ? '继续重试' : '重新生成'}</button>
                        <button className="button secondary small" onClick={() => setModal('settings')}>检查大模型连接</button>
                      </div>
                    )}
                    {errorCode.startsWith('cloud3d_') && (
                      <div className="recovery-actions">
                        {job?.id && ['cloud3d_connection','cloud3d_response'].includes(errorCode) && <button className="button secondary small" disabled={busy}
                          onClick={() => void generate({prompt:'',engine:'meshy',resume_job:job.id})}>继续查询</button>}
                        <button className="button secondary small" onClick={() => setModal('settings')}>专业3D服务设置</button>
                      </div>
                    )}
                  </div>
                  <button className="icon-button" aria-label="关闭错误提示" onClick={() => setError('')}>
                    <X size={16} />
                  </button>
                </div>
              )}
              <div className="workspace">
                <section className="create-panel panel">
                  <header className="panel-heading">
                    <span className="heading-icon">
                      <Sparkles size={17} />
                    </span>
                    <h2>从一个想法开始</h2>
                    <span className="tiny-label">CREATE</span>
                  </header>
                  <div className="input-tabs" role="tablist" aria-label="输入方式">
                    <button
                      role="tab"
                      aria-selected={!sketch.length}
                      className={!sketch.length ? 'selected' : ''}
                      onClick={() => {
                        if (!busy) setSketch([]);
                      }}
                    >
                      <MessageSquareText size={15} />
                      文字描述
                    </button>
                    <button
                      role="tab"
                      aria-selected={!!sketch.length}
                      className={sketch.length ? 'selected' : ''}
                      onClick={() => {
                        if (!busy) setModal('sketch');
                      }}
                    >
                      <Pencil size={15} />
                      文字 + 草图<span>+</span>
                    </button>
                  </div>
                  <div className="field-row creation-method">
                    <label htmlFor="creation-engine">创作方式</label>
                    <div className="select-wrap">
                      <select id="creation-engine" value={engine} disabled={busy}
                        onChange={(event) => { setEngine(event.target.value as Engine); setError(''); }}>
                        <option value="blender">自由创造 · AI + Blender</option>
                        <option value="meshy">专业形象 · 专用3D模型</option>
                        <option value="parametric">精确尺寸 · 基础部件</option>
                        {generatorReady && <option value="neural">实验模式 · 本地扩散</option>}
                      </select>
                      <ChevronDown size={13} />
                    </div>
                  </div>
                  {engine === 'blender' && (
                    <div className="neural-intro">
                      <strong>大模型设计，本地 Blender 建模</strong>
                      <p>直接描述想要的造型，或添一张草图。生成后可继续说出修改，也能打开 Blender 工程编辑。</p>
                      {blenderReady === false && <p className="generator-preparing">请运行「安装Blender建模.cmd」准备本地建模软件。</p>}
                      {!settings.enabled && <button className="text-button" onClick={() => setModal('settings')}>连接大模型服务</button>}
                    </div>
                  )}
                  {engine === 'meshy' && (
                    <div className="neural-intro">
                      <strong>面向角色、雕塑与复杂形象</strong>
                      <p>由专用3D模型生成几何。文字或参考图都可输入；参考图决定外形，文字用于作品说明与目标高度。复杂服装、甲片和五官仍需验看。</p>
                      <p>云端生成，按服务计费。彩色材质和光照不等于可打印细节，打印前会另做网格检查。</p>
                      {!settings.has_meshy_key && <button className="text-button" onClick={() => setModal('settings')}>配置独立的 Meshy 服务</button>}
                    </div>
                  )}
                  {engine === 'neural' && (
                    <div className="neural-intro">
                      <strong>写下新想法，让 AI 创造形状</strong>
                      <p>中文也可以。生成可能需要较长时间，完成后自动保存；可以刷新页面回来查看。</p>
                      {generatorReady === false && <p className="generator-preparing">本地模型尚未准备完整，请运行「安装自由生成.cmd」。</p>}
                    </div>
                  )}
                  <label className="field-label" htmlFor="idea">
                    你想做点什么？<span>越具体，越接近你的想象</span>
                  </label>
                  <div className="prompt-box">
                    <textarea
                      ref={promptRef}
                      id="idea"
                      maxLength={2000}
                      disabled={busy}
                      value={prompt}
                      onChange={(e) => setPrompt(e.target.value)}
                      placeholder={engine !== 'parametric' ? '比如：一把牛油果形状的椅子，圆润的椅背，果核形状的坐垫…' : '比如：安装板，长80宽40厚5，4个孔，孔径5…'}
                    />
                    <div className="prompt-bottom">
                      <span>
                        <Sparkles size={12} />
                        形状、尺寸、用途，都可以告诉我
                      </span>
                      <small>{prompt.length}/2000</small>
                    </div>
                  </div>
                  {(engine === 'blender' || engine === 'meshy') && (
                    <div className="reference-input">
                      <input ref={referenceRef} type="file" accept="image/png,image/jpeg,image/webp" aria-label="上传造型参考图" hidden onChange={event => void attachReference(event)} />
                      {reference ? <div className="reference-attached">
                        <img src={reference} alt="造型参考图" />
                        <span><strong>参考图已添加</strong><small>生成时发送至所选服务</small></span>
                        <button className="icon-button" aria-label="移除造型参考图" disabled={busy} onClick={() => setReference('')}><X size={14}/></button>
                      </div> : <button className="sketch-add" disabled={busy} onClick={() => referenceRef.current?.click()}>
                        <Upload size={18}/><span><strong>上传造型参考图</strong><small>角色、甲片和五官，可直接参考图片</small></span><Plus size={16}/>
                      </button>}
                    </div>
                  )}
                  {engine === 'parametric' && !sketch.length && (
                    <div className="local-scope">
                      <span>本地造型库 · 20 种基础模型，可调整尺寸与部分形状</span>
                      <button className="text-button" onClick={() => setModal('catalog')}>
                        查看全部可生成模型 <ChevronRight size={12} />
                      </button>
                    </div>
                  )}
                  {sketch.length > 0 ? (
                    <div className="sketch-attachment">
                      <div>
                        <Pencil size={18} />
                        <span>
                          <strong>草图已添加</strong>
                          <small>{sketch.length} 个轮廓 · {engine !== 'parametric' ? '作为外形参考参与生成' : '拉伸为实体'}</small>
                        </span>
                      </div>
                      <button
                        className="text-button"
                        disabled={busy}
                        onClick={() => setModal('sketch')}
                      >
                        编辑
                      </button>
                      <button
                        className="icon-button"
                        aria-label="移除草图"
                        disabled={busy}
                        onClick={() => setSketch([])}
                      >
                        <X size={14} />
                      </button>
                    </div>
                  ) : (
                    <button
                      className="sketch-add"
                      disabled={busy}
                      onClick={() => setModal('sketch')}
                    >
                      <span className="dashed-icon">
                        <Pencil size={16} />
                      </span>
                      <span>
                        <strong>有画面？添一张草图</strong>
                        <small>{engine !== 'parametric' ? '结合文字理解草图中的形状' : '随手画个轮廓，让想法更准确'}</small>
                      </span>
                      <Plus size={17} />
                    </button>
                  )}
                  <div className="field-row" hidden={engine !== 'parametric'}>
                    <label htmlFor="model-mode">建模方向</label>
                    <div className="select-wrap">
                      <select
                        id="model-mode"
                        value={mode}
                        disabled={busy || !!sketch.length}
                        onChange={(e) => setMode(e.target.value as Mode)}
                      >
                        <option value="auto">自动识别</option>
                        <option value="figurine">动物 / 创意摆件</option>
                        <option value="part">产品 / 结构零件</option>
                      </select>
                      <ChevronDown size={13} />
                    </div>
                  </div>
                  {engine === 'neural' && (
                    <div className="field-row">
                      <label htmlFor="generation-quality">生成细致程度</label>
                      <div className="select-wrap">
                        <select id="generation-quality" value={quality} disabled={busy}
                          onChange={(event) => setQuality(Number(event.target.value))}>
                          <option value={16}>快速尝试 · 16 步</option>
                          <option value={32}>标准 · 32 步</option>
                          <option value={64}>更细致 · 64 步</option>
                        </select>
                        <ChevronDown size={13} />
                      </div>
                    </div>
                  )}
                  {(engine === 'blender' || engine === 'meshy') && (
                    <div className="detail-choice">
                      <div className="field-row">
                        <label htmlFor="blender-detail">造型精细程度</label>
                        <div className="select-wrap">
                          <select id="blender-detail" value={blenderDetail} disabled={busy}
                            onChange={(event) => setBlenderDetail(event.target.value as 'draft' | 'fine')}>
                            <option value="fine">{engine === 'meshy' ? '精细 · 高细节几何生成' : '精细 · 多角度检查与精修'}</option>
                            <option value="draft">快速 · 先看整体造型</option>
                          </select>
                          <ChevronDown size={13} />
                        </div>
                      </div>
                      <p>{engine === 'meshy' ? '使用专用3D生成服务，当前大模型密钥不能替代。文字生成彩色材质会增加一个服务任务。' : blenderDetail === 'fine'
                        ? '细化轮廓与局部结构；生成预览会发给大模型复核，增加一次调用，通常需要数分钟。'
                        : '先生成整体形状与主要结构，之后可以继续精修。'}</p>
                    </div>
                  )}
                  <button
                    className="button primary generate-button"
                    disabled={busy || !ready || (!prompt.trim() && !sketch.length && !reference)}
                    onClick={run}
                  >
                    {busy ? <Loader2 className="spin" size={18} /> : <WandSparkles size={18} />}
                    <span>{busy ? '正在让想法成形…' : '生成我的模型'}</span>
                    {!busy && (
                      <span className="shortcut">
                        <Command size={11} />↵
                      </span>
                    )}
                  </button>
                  <div className="local-note">
                    <ShieldCheck size={12} />
                    {engine === 'blender'
                      ? '描述与草图发送至所设服务 · Blender 本地运行'
                      : engine === 'meshy'
                      ? '描述或参考图发送至 Meshy · 按该服务计费'
                      : engine === 'neural'
                      ? '本地 AI 生成 · 不发送描述 · 无需密钥'
                      : '本地生成 · 无需注册 · 模型自动保存'}
                  </div>
                  <div className="inspiration-heading">
                    <span>还没想好？从这里开始</span>
                    <MoreHorizontal size={17} />
                  </div>
                  <div className="example-list">
                    {(engine !== 'parametric' ? FREE_EXAMPLES : EXAMPLES).map((e) => (
                      <button
                        className={'example-card ' + e.color}
                        key={e.kind}
                        disabled={busy}
                        onClick={() => chooseExample(e, engine)}
                      >
                        <div className="example-art">
                          <MiniArt kind={e.kind} />
                        </div>
                        <div>
                          <strong>{e.name}</strong>
                          <small>{e.tag}</small>
                        </div>
                        <ArrowRight size={14} />
                      </button>
                    ))}
                  </div>
                  <button className="capability-link" onClick={() => setModal('help')}>
                    <Info size={13} />
                    我可以做哪些模型？
                    <ChevronRight size={12} />
                  </button>
                </section>
                <section className="preview-panel panel" ref={viewportRef}>
                  <div className="preview-top">
                    <span className="preview-label">
                      <span className="live-dot" />
                      3D 实时预览
                    </span>
                    <div className="view-select">
                      <select
                        aria-label="观察方向"
                        value={view}
                        onChange={(e) => setView(e.target.value)}
                      >
                        <option value="perspective">透视视图</option>
                        <option value="front">正面视图</option>
                        <option value="side">侧面视图</option>
                        <option value="top">顶部视图</option>
                      </select>
                      <ChevronDown size={12} />
                    </div>
                  </div>
                  <div className="model-name">
                    <h2>{model?.name || '你的下一件作品'}</h2>
                    <span>
                      {model ? (
                        <>
                          <Check size={11} />
                          已自动保存
                        </>
                      ) : (
                        '从左侧描述一个想法'
                      )}
                    </span>
                  </div>
                  <div className="three-viewport">
                    <Suspense
                      fallback={
                        <div className="viewer-loading">
                          <Loader2 size={24} className="spin" />
                          正在打开 3D 画布
                        </div>
                      }
                    >
                      <Viewer
                        model={model}
                        color={color}
                        wireframe={wireframe}
                        grid={grid}
                        rotate={rotate}
                        view={view}
                        reset={reset}
                        onThumbnail={saveThumbnail}
                      />
                    </Suspense>
                  </div>
                  {!model && !busy && (
                    <div className="empty-preview">
                      <Box size={44} strokeWidth={1} />
                      <h3>下一个好想法，从这里成形</h3>
                      <p>写一段描述，或试试左侧的灵感</p>
                    </div>
                  )}
                  <div className="preview-controls">
                    <div className="tool-group">
                      <button
                        className={'icon-button ' + (grid ? 'selected' : '')}
                        title="显示 / 隐藏网格"
                        aria-label="显示或隐藏网格"
                        aria-pressed={grid}
                        onClick={() => setGrid((v) => !v)}
                      >
                        <Grid2X2 size={17} />
                      </button>
                      <button
                        className={'icon-button ' + (wireframe ? 'selected' : '')}
                        title="线框模式"
                        aria-label="线框模式"
                        aria-pressed={wireframe}
                        onClick={() => setWireframe((v) => !v)}
                      >
                        <Cuboid size={18} />
                      </button>
                      <span className="tool-separator" />
                      <button
                        className={'icon-button ' + (rotate ? 'selected' : '')}
                        title="自动旋转"
                        aria-label="自动旋转"
                        aria-pressed={rotate}
                        onClick={() => setRotate((v) => !v)}
                      >
                        <RotateCw size={17} />
                      </button>
                      <button
                        className="icon-button"
                        title="重置视角"
                        aria-label="重置视角"
                        onClick={() => {
                          setView('perspective');
                          setReset((v) => v + 1);
                        }}
                      >
                        <RotateCcw size={16} />
                      </button>
                    </div>
                    <button
                      className="icon-button standalone"
                      title="全屏预览"
                      aria-label="全屏预览"
                      onClick={() => void fullscreen()}
                    >
                      <Maximize size={17} />
                    </button>
                  </div>
                  <div className="mouse-hint">
                    <MousePointer2 size={12} />
                    <span>拖动旋转</span>
                    <i />
                    滚轮缩放
                    <i />
                    右键平移
                  </div>
                  {model && (
                    <div className="model-dimensions">
                      <span>
                        X <b>{model.stats.dimensions[0]}</b>
                      </span>
                      <span>
                        Y <b>{model.stats.dimensions[1]}</b>
                      </span>
                      <span>
                        Z <b>{model.stats.dimensions[2]}</b>
                      </span>
                      <small>mm</small>
                    </div>
                  )}
                  {busy && (
                    <div className="generation-overlay" role="status">
                      <div className="generating-orb">
                        <Box size={35} strokeWidth={1.3} />
                        <span />
                      </div>
                      <h3>{job?.stage || '正在准备你的模型'}</h3>
                      <p>
                        {job?.engine === 'blender' || engine === 'blender'
                          ? '大模型设计 → Blender 建模 → 检查与自动修正'
                          : job?.engine === 'meshy' || engine === 'meshy'
                          ? '专用3D生成 → 下载原始形象 → 本地打印检查；停止等待不会撤销已提交的云端任务或费用'
                          : job?.engine === 'neural' || engine === 'neural'
                          ? `正在本机创造新形状${job?.elapsed_seconds ? ` · 已用 ${Math.floor(job.elapsed_seconds / 60)} 分 ${job.elapsed_seconds % 60} 秒` : ''}`
                          : '本地构建中，通常只需几秒'}
                      </p>
                      <div className="progress-track">
                        <span style={{ width: `${job?.progress || 3}%` }} />
                      </div>
                      <button className="text-button" onClick={() => void cancel()}>
                        停止生成
                      </button>
                    </div>
                  )}
                  <div className="refine-area">
                    <div className="refine-input">
                      <Sparkles size={16} />
                      <input
                        aria-label="继续修改模型"
                        placeholder={
                          model?.recipe.kind === 'neural' || model?.recipe.kind === 'blender'
                            ? '新的变化，比如：椅背像一片树叶…'
                            : model?.recipe.category === 'figurine'
                            ? '再说一句，比如：耳朵大一点…'
                            : '继续修改，比如：宽度80毫米…'
                        }
                        value={revision}
                        disabled={!model || busy}
                        onChange={(e) => setRevision(e.target.value)}
                        onKeyDown={(e: KeyboardEvent<HTMLInputElement>) => {
                          if (e.key === 'Enter') refine();
                        }}
                      />
                      <button
                        className="refine-send"
                        aria-label="提交修改描述"
                        disabled={!model || busy || !revision.trim()}
                        onClick={() => refine()}
                      >
                        <ArrowRight size={17} />
                      </button>
                    </div>
                    <div className="refine-suggestions">
                      <span>试着说</span>
                      {revisions.length ? (
                        revisions.map((r) => (
                          <button disabled={busy} onClick={() => refine(r)} key={r}>
                            {r}
                            <Plus size={10} />
                          </button>
                        ))
                      ) : (
                        <span className="quiet-text">{model?.recipe.kind === 'blender' ? '沿用现有建模步骤，继续修改你的作品' : model?.recipe.kind === 'neural' ? '修改描述会重新创造，形状可能一起变化' : '用右侧尺寸面板，让每一毫米刚刚好'}</span>
                      )}
                    </div>
                  </div>
                </section>
                <aside className="properties-panel panel">
                  <header className="panel-heading">
                    <SlidersHorizontal size={16} />
                    <h2>让细节刚刚好</h2>
                  </header>
                  <div className="property-scroll">
                    <div className="section-label">
                      模型尺寸<span>单位 mm</span>
                    </div>
                    {model ? (
                      <div className="parameters">
                        {Object.entries(params).map(([key, value]) => {
                          if (typeof value === 'boolean')
                            return (
                              <div className="switch-row" key={key}>
                                <label htmlFor={'param-' + key}>{LABELS[key] || key}</label>
                                <button
                                  id={'param-' + key}
                                  role="switch"
                                  aria-checked={value}
                                  aria-label={LABELS[key] || key}
                                  className={'switch ' + (value ? 'on' : '')}
                                  disabled={busy}
                                  onClick={() => updateParam(key, !value)}
                                >
                                  <i />
                                </button>
                              </div>
                            );
                          const range = LIMITS[key] || [0, 250, 1];
                          const isScale = key.endsWith('_scale');
                          const min =
                            key === 'height' &&
                            ['plate', 'washer', 'gear', 'sketch'].includes(model.recipe.kind)
                              ? 1.2
                              : range[0];
                          return (
                            <div
                              className={'parameter ' + (isScale ? 'scale-param' : '')}
                              key={key}
                            >
                              <label htmlFor={'param-' + key}>{LABELS[key] || key}</label>
                              <div className="number-field">
                                <input
                                  type="number"
                                  id={'param-' + key}
                                  aria-label={LABELS[key] || key}
                                  min={min}
                                  max={range[1]}
                                  step={range[2]}
                                  value={value}
                                  disabled={busy}
                                  onChange={(e) =>
                                    updateParam(
                                      key,
                                      e.target.value === '' ? 0 : Number(e.target.value),
                                    )
                                  }
                                />
                                <span>
                                  {isScale
                                    ? '倍'
                                    : key === 'teeth'
                                      ? '齿'
                                      : key === 'holes'
                                        ? '个'
                                        : 'mm'}
                                </span>
                              </div>
                              {isScale && (
                                <input
                                  className="range-field"
                                  aria-label={(LABELS[key] || key) + '滑块'}
                                  type="range"
                                  min={range[0]}
                                  max={range[1]}
                                  step={range[2]}
                                  value={value}
                                  disabled={busy}
                                  onChange={(e) => updateParam(key, Number(e.target.value))}
                                />
                              )}
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <p className="empty-params">生成模型后，可以在这里精确调整尺寸。</p>
                    )}
                    {model?.recipe.kind === 'neural' && (
                      <div className="neural-model-note">
                        <strong>AI 新生成的形状</strong>
                        <p>高度与底座可直接调整。修改外形会重新生成，需要等待；精密装配仍需核对。</p>
                        <button className="button secondary small" disabled={busy} onClick={() => {
                          setEngine('neural');
                          void generate({prompt: model.recipe.generation_prompt || model.recipe.prompt,
                            engine: 'neural', steps: quality, regenerate: true, params});
                        }}><Sparkles size={14} />再创造一版</button>
                      </div>
                    )}
                    {model?.recipe.kind === 'blender' && (
                      <div className="neural-model-note">
                        <strong>可继续编辑的 Blender 工程</strong>
                        <p>调高度会等比缩放全部尺寸；改变孔位、壁厚或造型，请在下方用文字提出修改。</p>
                        {model.recipe.refinement === 'refined' && <p>已结合实际模型的三个角度完成外观复核与精修。</p>}
                        {model.recipe.refinement === 'reviewed' && <p>已复核三个角度，保留当前造型。</p>}
                        {model.recipe.refinement === 'retained' && <p>本次精修未完成，当前显示已通过检查的初版。</p>}
                        {model.recipe.review && <details className="model-review"><summary>查看造型复核说明</summary><p>{model.recipe.review}</p></details>}
                        <button className="button secondary small" disabled={busy} onClick={() => refine('精修当前作品：保留原设计、姿态、底座、已有尺寸及功能接口，改善轮廓过渡和局部结构，补足原描述要求的真实几何细节；不要仅增加面数，不要添加无关装饰。', 'fine')}>
                          <Sparkles size={14} />精修当前作品
                        </button>
                        <button className="button secondary small" disabled={busy} onClick={async () => {
                          try {
                            await api(`/models/${model.id}/open-blender`, {method: 'POST'});
                            notify('正在用本机 Blender 打开工程');
                          } catch (error) { notify((error as Error).message); }
                        }}><Box size={14} />用 Blender 打开</button>
                      </div>
                    )}
                    {model?.recipe.kind === 'meshy' && <div className="neural-model-note">
                      <strong>原始形象与打印几何分开保存</strong>
                      <p>{model.stats.print_ready === false ? '形象已保留，尚需在 Blender 中修复实体。未移除服装、头发或配件。' : '几何已通过基础实体检查，仍需确认壁厚、支撑和细节尺寸。'}</p>
                      <p>高度在本地等比调整。文字修改会重新创造；原始GLB保留材质，可导入Blender。</p>
                    </div>}
                    {dirty && (
                      <div className="apply-row">
                        <button
                          className="button apply-button"
                          disabled={busy}
                          onClick={applyParams}
                        >
                          <Check size={14} />
                          应用修改
                        </button>
                        <button
                          className="icon-button"
                          title="恢复模型尺寸"
                          aria-label="恢复模型尺寸"
                          onClick={() => {
                            setParams({ ...model!.recipe.params });
                            setDirty(false);
                          }}
                        >
                          <RotateCcw size={14} />
                        </button>
                      </div>
                    )}
                    <div className="property-divider" />
                    <div className="section-label">
                      预览颜色<span>不影响打印文件</span>
                    </div>
                    <div className="color-swatches">
                      {COLORS.map((c, i) => (
                        <button
                          key={c}
                          aria-label={
                            ['丁香紫', '奶油杏', '鼠尾草绿', '雾霾蓝', '玫瑰粉', '暖白'][i]
                          }
                          aria-pressed={color === c}
                          className={'swatch ' + (color === c ? 'chosen' : '')}
                          style={{ background: c }}
                          onClick={() => setColor(c)}
                        >
                          {color === c && <Check size={13} />}
                        </button>
                      ))}
                    </div>
                    <div className="property-divider" />
                    <div className="section-label">
                      打印前检查
                      <ShieldCheck size={14} />
                    </div>
                    <div className="print-checks">
                      <div>
                        <CheckCheck size={14} />
                        <span>封闭实体</span>
                        <strong>{model ? model.stats.watertight ? '已通过' : '待修复' : '待生成'}</strong>
                      </div>
                      <div>
                        <CheckCheck size={14} />
                        <span>单个连通模型</span>
                        <strong>{model ? model.stats.components === 1 ? '已通过' : '待连接' : '待生成'}</strong>
                      </div>
                      <div>
                        <CheckCheck size={14} />
                        <span>平放到打印平台</span>
                        <strong>{model ? model.stats.print_ready === false ? '需检查' : '已完成' : '待生成'}</strong>
                      </div>
                    </div>
                    {model && (
                      <>
                        <div className="print-info">
                          <Info size={14} />
                          <p>
                            {model.stats.warnings[0] ||
                              '实体已封闭。导入切片软件，选择材料和打印参数后即可切片。'}
                          </p>
                        </div>
                        <div className="mesh-meta">
                          <span>
                            网格面数<strong>{model.stats.triangles.toLocaleString()}</strong>
                          </span>
                          <span>
                            实体体积<strong>{model.stats.volume_cm3.toFixed(1)} cm³</strong>
                          </span>
                        </div>
                      </>
                    )}
                  </div>
                  <div className="export-area">
                    <div className="export-caption">
                      <Printer size={15} />
                      <span>下一站，现实世界</span>
                    </div>
                    <button
                      className="button dark export-button"
                      disabled={!model || busy}
                      onClick={() => setModal('export')}
                    >
                      <Download size={17} />
                      导出打印文件
                      <ChevronRight size={16} />
                    </button>
                    <p>STL / 3MF / OBJ · 毫米单位</p>
                  </div>
                </aside>
              </div>
              <div className="bottom-strip">
                <div>
                  <span className="bottom-icon">
                    <PackageCheck size={21} />
                  </span>
                  <span>
                    <strong>从屏幕里的灵感，到手心里的实物</strong>
                    <small>兼容 Bambu Studio、OrcaSlicer、Cura 等常用切片软件</small>
                  </span>
                </div>
                <button onClick={() => setModal('help')}>
                  第一次 3D 打印？看这份小指南
                  <ArrowRight size={14} />
                </button>
              </div>
              <footer className="page-footer">
                <span>小造 · 为每一个想创造的人</span>
                <span>
                  <ShieldCheck size={12} />
                  本地模型留在你的电脑里
                </span>
              </footer>
            </>
          ) : (
            <>
              <div className="page-heading library-heading">
                <div>
                  <div className="eyebrow">YOUR LITTLE COLLECTION</div>
                  <h1>
                    每个想法，<span>都有迹可循。</span>
                  </h1>
                  <p>你的作品会自动保存在这台电脑。随时回来，继续打磨。</p>
                </div>
                <button
                  className="button secondary"
                  disabled={busy}
                  onClick={() => fileRef.current?.click()}
                >
                  <Upload size={16} />
                  导入项目
                </button>
              </div>
              <div className="library-tools">
                <h2>
                  我的作品 <span>{models.length}</span>
                </h2>
                <input
                  aria-label="搜索作品"
                  placeholder="搜索作品名称或描述…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
                <button className="button primary" disabled={busy} onClick={newProject}>
                  <Plus size={16} />
                  新建作品
                </button>
              </div>
              {busy && (
                <div className="library-busy" role="status">
                  <Loader2 className="spin" size={17} />
                  正在生成新模型，可回工作台查看进度
                  <button className="text-button" onClick={() => setPage('studio')}>
                    回到工作台
                    <ArrowRight size={13} />
                  </button>
                </div>
              )}
              <div className="library-grid">
                {models
                  .filter((m) =>
                    (m.name + m.recipe.prompt).toLowerCase().includes(search.toLowerCase()),
                  )
                  .map((m) => (
                    <article className="library-card" key={m.id}>
                      <button
                        className="library-card-main"
                        disabled={busy}
                        onClick={() => openModel(m)}
                      >
                        <div
                          className={
                            'library-art ' +
                            (m.recipe.category === 'figurine'
                              ? 'lilac'
                              : m.recipe.kind === 'vase'
                                ? 'peach'
                                : 'blue')
                          }
                        >
                          {m.thumbnail ? (
                            <img
                              src={`/api/models/${m.id}/thumbnail`}
                              alt={m.name}
                              loading="lazy"
                            />
                          ) : (
                            <MiniArt kind={m.recipe.kind} />
                          )}
                          <span>
                            {m.recipe.kind === 'meshy' ? '专业3D形象' : m.recipe.kind === 'blender'
                              ? 'AI + Blender'
                              : m.recipe.category === 'figurine'
                              ? '创意摆件'
                              : m.recipe.kind === 'sketch'
                                ? '草图实体'
                                : '结构模型'}
                          </span>
                        </div>
                        <div className="library-card-body">
                          <h3>{m.name}</h3>
                          <p>{m.recipe.prompt || '由草图创建'}</p>
                          <div>
                            <span>
                              {m.stats.dimensions.map((n) => Math.round(n)).join(' × ')} mm
                            </span>
                            <span>{new Date(m.created_at * 1000).toLocaleDateString('zh-CN')}</span>
                          </div>
                        </div>
                      </button>
                      <button
                        className="icon-button library-delete"
                        aria-label={'删除' + m.name}
                        disabled={busy}
                        onClick={() => setDeleteTarget(m)}
                      >
                        <Trash2 size={15} />
                      </button>
                    </article>
                  ))}
              </div>
              {!models.length && (
                <div className="library-empty">
                  <FolderOpen size={46} strokeWidth={1} />
                  <h3>第一件作品，等你来创造</h3>
                  <button className="button primary" onClick={newProject}>
                    <Plus size={16} />
                    开始创作
                  </button>
                </div>
              )}
              {models.length > 0 &&
                !models.some((m) =>
                  (m.name + m.recipe.prompt).toLowerCase().includes(search.toLowerCase()),
                ) && (
                  <div className="library-empty">
                    <p>没有找到匹配的作品，换个词试试。</p>
                  </div>
                )}
              {error && (
                <div className="error-banner" role="alert">
                  <Info size={18} />
                  <p>{error}</p>
                </div>
              )}
            </>
          )}
        </main>
      </div>
      <input
        hidden
        ref={fileRef}
        type="file"
        accept=".json,application/json"
        onChange={(e) => void importProject(e)}
      />
      {toast && (
        <div className="toast" role="status">
          <Check size={16} />
          {toast}
        </div>
      )}
      {modal === 'sketch' && (
        <Sketch
          initial={sketch}
          onClose={() => setModal(null)}
          onApply={(paths) => {
            setSketch(paths);
            setModal(null);
            notify('草图已添加，点击「生成我的模型」即可创建实体');
          }}
        />
      )}
      {modal === 'export' && model && (
        <ExportModal model={model} dirty={dirty} onClose={() => setModal(null)} notify={notify} />
      )}
      {modal === 'settings' && (
        <SettingsModal
          current={settings}
          onClose={() => setModal(null)}
          onSaved={(s) => {
            setSettings(s);
            setModal(null);
            notify(s.enabled ? 'AI 连接设置已保存' : '大模型连接已关闭，可选择基础部件模式');
          }}
        />
      )}
      {modal === 'catalog' && (
        <CatalogModal
          onClose={() => setModal(null)}
          onSelect={(item) => {
            setPrompt(item.prompt);
            setSketch([]);
            setMode('auto');
            setEngine('parametric');
            setError('');
            setErrorCode('');
            setModal(null);
            window.setTimeout(() => promptRef.current?.focus(), 0);
            notify('示例已填入，可以修改尺寸后点击生成');
          }}
        />
      )}
      {modal === 'help' && (
        <HelpModal
          onClose={() => setModal(null)}
          onExample={(e) => {
            setModal(null);
            setPage('studio');
            chooseExample(e);
          }}
        />
      )}
      {deleteTarget && (
        <Modal title="删除这件作品？" onClose={() => setDeleteTarget(null)}>
          <p className="modal-intro">
            「{deleteTarget.name}」的模型和项目文件将从本机删除。已经下载的文件不受影响。
          </p>
          <div className="modal-actions">
            <button className="button secondary" onClick={() => setDeleteTarget(null)}>
              保留作品
            </button>
            <button className="button danger" onClick={() => void deleteModel()}>
              <Trash2 size={15} />
              确认删除
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function ExportModal({
  model,
  dirty,
  onClose,
  notify,
}: {
  model: Model;
  dirty: boolean;
  onClose: () => void;
  notify: (s: string) => void;
}) {
  const [format, setFormat] = useState('3mf');
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState('');
  const download = async (fmt = format) => {
    setDownloading(true);
    setError('');
    try {
      const response = await fetch(`/api/models/${model.id}/download/${fmt}`);
      if (!response.ok) throw new Error('文件下载失败，请重试。');
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${model.name}-${fmt === 'json' || fmt === 'blend' ? '项目' : fmt === 'glb' ? '原始形象' : fmt === 'py' ? '建模步骤' : '毫米'}.${fmt}`;
      a.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 5000);
      notify(
        fmt === 'glb' ? '原始形象已下载，可导入Blender继续编辑' : ['json', 'blend', 'py'].includes(fmt) ? '工程已导出，下次可以继续修改' : '打印文件已下载，导入切片软件开始下一步',
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setDownloading(false);
    }
  };
  return (
    <Modal title="让它来到现实世界" eyebrow="READY FOR THE REAL WORLD" onClose={onClose}>
      <div className="export-summary">
        <span className="export-model-icon">
          <Box size={27} />
        </span>
        <div>
          <strong>{model.name}</strong>
          <p>{model.stats.dimensions.join(' × ')} mm · {model.stats.print_ready === false ? '形象已保留，打印待修复' : '封闭实体'}</p>
        </div>
        <span className="status-pill">
          <Check size={12} />
          {model.stats.print_ready === false ? '待修复' : '检查通过'}
        </span>
      </div>
      {dirty && (
        <p className="warning-note">尺寸面板有未应用的修改。本次导出的是预览中已生成的模型。</p>
      )}
      <p className="field-label export-format-label">选择文件格式</p>
      <div className="format-options">
        {[
          { key: '3mf', name: '3MF', desc: '保留毫米单位，推荐用于打印', tag: '推荐' },
          { key: 'stl', name: 'STL', desc: '几乎所有切片软件都能打开', tag: '' },
          { key: 'obj', name: 'OBJ', desc: '适合继续在其他建模软件中编辑', tag: '' },
        ].map((f) => (
          <button
            className={'format-option ' + (format === f.key ? 'selected' : '')}
            key={f.key}
            onClick={() => setFormat(f.key)}
          >
            <FileCheck2 size={22} />
            <span>
              <strong>
                {f.name}
                {f.tag && <em>{f.tag}</em>}
              </strong>
              <small>{f.desc}</small>
            </span>
            <span className="radio">{format === f.key && <i />}</span>
          </button>
        ))}
      </div>
      <div className="export-notes">
        <Info size={16} />
        <div>
          <strong>导入切片软件后，再确认这三件事</strong>
          <p>
            尺寸按毫米读取、需要的支撑、材料和层高。STL / OBJ 本身不存储单位；3MF 明确记录毫米单位。
          </p>
          {model.stats.warnings.map((w, i) => (
            <p key={i}>{w}</p>
          ))}
        </div>
      </div>
      {error && (
        <p role="alert" className="error-inline">
          {error}
        </p>
      )}
      <button
        className="button primary full-width"
        disabled={downloading || model.stats.print_ready === false}
        onClick={() => void download()}
      >
        {downloading ? <Loader2 className="spin" size={17} /> : <ArrowDownToLine size={17} />}下载{' '}
        {format.toUpperCase()} 文件
      </button>
      {model.recipe.kind === 'meshy' && <div className="blender-exports">
        <p className="warning-note">原始GLB保留全部几何与彩色材质，可导入Blender继续雕刻；原始文件使用服务的单位和朝向。JSON备份不包含GLB，请同时保存。</p>
        <button className="button secondary full-width" disabled={downloading} onClick={() => void download('glb')}><Box size={16}/>下载原始形象（GLB）</button>
      </div>}
      {model.recipe.kind === 'blender' && (
        <div className="blender-exports">
          <button className="button secondary full-width" disabled={downloading} onClick={() => void download('blend')}>
            <Box size={16} />下载可编辑 Blender 工程（.blend）
          </button>
          <button className="project-export" disabled={downloading} onClick={() => void download('py')}>
            <FileJson size={15} />保存建模步骤（Python）<ArrowRight size={13} />
          </button>
        </div>
      )}
      <button
        className="project-export"
        disabled={downloading}
        onClick={() => void download('json')}
      >
        <FileJson size={15} />
        同时备份可编辑项目（JSON）
        <ArrowRight size={13} />
      </button>
    </Modal>
  );
}

function SettingsModal({
  current,
  onClose,
  onSaved,
}: {
  current: Settings;
  onClose: () => void;
  onSaved: (s: Settings) => void;
}) {
  const [form, setForm] = useState({ ...current, api_key: '', meshy_api_key: '', meshy_texture: current.meshy_texture ?? true });
  const [clearKey, setClearKey] = useState(false);
  const [clearMeshyKey, setClearMeshyKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const save = async () => {
    setSaving(true);
    setError('');
    try {
      const result = await api<Settings>('/settings', {
        method: 'PUT',
        body: JSON.stringify({ ...form, clear_key: clearKey, clear_meshy_key: clearMeshyKey }),
      });
      onSaved(result);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };
  return (
    <Modal title="选择你的创作方式" eyebrow="MAKE IT YOURS" onClose={onClose}>
      <p className="modal-intro">
        大模型根据描述和草图设计建模步骤，本机 Blender 执行并保存可编辑工程。精细模式还会检查实际模型的多角度预览并精修。
      </p>
      <div className="settings-mode">
        <span>
          <strong>启用大模型建模</strong>
          <small>开启后，描述、草图、模型方案与精细模式的预览会发送至所设服务</small>
        </span>
        <button
          className={'switch ' + (form.enabled ? 'on' : '')}
          role="switch"
          aria-label="启用大模型建模"
          aria-checked={form.enabled}
          onClick={() => setForm({ ...form, enabled: !form.enabled })}
        >
          <i />
        </button>
      </div>
      <div className="settings-fields">
        <label>
          服务地址（兼容 OpenAI）
          <input
            value={form.base_url}
            onChange={(e) => setForm({ ...form, base_url: e.target.value })}
            placeholder="https://api.openai.com/v1"
          />
        </label>
        <label>
          模型名称
          <input
            value={form.model}
            onChange={(e) => setForm({ ...form, model: e.target.value })}
            placeholder="支持 JSON 输出的模型名称"
          />
        </label>
        <label>
          API 密钥
          <input
            type="password"
            autoComplete="off"
            value={form.api_key}
            onChange={(e) => {
              setForm({ ...form, api_key: e.target.value });
              setClearKey(false);
            }}
            placeholder={current.has_key && !clearKey ? '已保存密钥，留空保持不变' : 'sk-…'}
          />
        </label>
        {current.has_key && (
          <button
            className="text-button clear-key"
            onClick={() => {
              setClearKey((v) => !v);
              setForm({ ...form, api_key: '' });
            }}
          >
            {clearKey ? '撤销移除密钥' : '移除已保存的密钥'}
          </button>
        )}
      </div>
      <div className="professional-settings">
        <strong>专业形象生成 · Meshy</strong>
        <p>用于角色、雕塑和复杂服饰。专用3D服务独立计费，需要单独的API密钥。当前文字大模型的密钥不能直接使用。</p>
        <div className="settings-fields">
          <label>Meshy API 密钥
            <input type="password" autoComplete="off" value={form.meshy_api_key}
              placeholder={current.has_meshy_key && !clearMeshyKey ? '已保存，留空保持不变' : '填写从Meshy获取的API密钥'}
              onChange={event => {setForm({...form,meshy_api_key:event.target.value});setClearMeshyKey(false);}}/>
          </label>
          {current.has_meshy_key && <button className="text-button" onClick={() => {setClearMeshyKey(!clearMeshyKey);setForm({...form,meshy_api_key:''});}}>{clearMeshyKey ? '撤销移除Meshy密钥' : '移除Meshy密钥'}</button>}
          <label className="texture-setting"><input type="checkbox" checked={form.meshy_texture} onChange={event => setForm({...form,meshy_texture:event.target.checked})}/>同时生成彩色材质</label>
        </div>
        <p>精细模式使用高细节几何生成。文字生成材质会增加一个付费任务。参考图会发送至Meshy；图片未展示的背面由模型推测。停止等待不会撤销已经提交的云端任务或费用。</p>
      </div>
      <div className="print-info">
        <ShieldCheck size={15} />
        <p>
          密钥仅存于本机
          data/settings.json，不会返回到浏览器。云端服务可能产生费用；本机兼容服务可使用
          http://127.0.0.1 地址。精细模式与草图需要模型支持图像输入。Blender 在本机运行；精密装配、承载结构仍需核对和试印。
        </p>
      </div>
      {error && (
        <p role="alert" className="error-inline">
          {error}
        </p>
      )}
      <div className="modal-actions">
        <button className="button secondary" onClick={onClose}>
          返回创作
        </button>
        <button className="button primary" disabled={saving} onClick={() => void save()}>
          {saving ? <Loader2 size={16} className="spin" /> : <Check size={16} />}保存设置
        </button>
      </div>
    </Modal>
  );
}

function CatalogModal({
  onClose,
  onSelect,
}: {
  onClose: () => void;
  onSelect: (item: CatalogItem) => void;
}) {
  const [items, setItems] = useState<CatalogItem[]>([]);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setError('');
    api<CatalogItem[]>('/catalog')
      .then((data) => { if (active) setItems(data); })
      .catch((e) => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [attempt]);
  return (
    <Modal title="本地可生成的模型" onClose={onClose} wide>
      <p className="modal-intro">
        选择一种基础造型，填入示例后可以修改尺寸。浏览列表不会改动你的描述。
        本地模式使用造型库；草图可拉伸平面轮廓。任意物体和复杂结构仍需要其他建模能力。
      </p>
      {error ? (
        <div role="alert">
          <p>{error}</p>
          <button className="button secondary" onClick={() => setAttempt((n) => n + 1)}>重新加载</button>
        </div>
      ) : !items.length ? (
        <p role="status">正在读取本地造型库…</p>
      ) : (
        <div className="catalog-groups">
          {(['figurine', 'part'] as const).map((category) => (
            <section key={category}>
              <h3>{category === 'figurine' ? '小动物摆件' : '实用部件与基础形状'}</h3>
              <div className="catalog-grid">
                {items.filter((item) => item.category === category).map((item) => (
                  <button className="catalog-item" key={item.kind} onClick={() => onSelect(item)}>
                    <span>{item.name}</span><small>填入示例 <ArrowRight size={12} /></small>
                  </button>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
      <div className="modal-actions">
        <button className="button secondary" onClick={onClose}>保留描述，返回创作</button>
      </div>
    </Modal>
  );
}

function HelpModal({
  onClose,
  onExample,
}: {
  onClose: () => void;
  onExample: (e: (typeof EXAMPLES)[number]) => void;
}) {
  return (
    <Modal
      title="从第一句话，到第一件实物"
      eyebrow="A SMALL GUIDE TO MAKING"
      onClose={onClose}
      wide
    >
      <div className="help-steps">
        <div>
          <span>01</span>
          <h3>说清楚你想要什么</h3>
          <p>
            默认使用“自由创造 · AI + Blender”。写下物体名称、形状和尺寸，也可以附上草图。
            比如“牛油果形状的椅子，高70毫米”。尺寸支持 mm、毫米、cm、厘米。
          </p>
        </div>
        <div>
          <span>02</span>
          <h3>转一转，调一调</h3>
          <p>
            拖动模型查看各个方向。继续用文字提出修改，大模型会沿用已有建模程序。
            AI + Blender 会结合描述理解草图；基础部件模式则把平面轮廓拉伸成实体。
          </p>
        </div>
        <div>
          <span>03</span>
          <h3>下载，切片，然后打印</h3>
          <p>
            推荐导出带毫米单位的 3MF。用 Bambu Studio、OrcaSlicer 或 Cura
            打开，确认摆放、支撑与材料。导出 JSON 项目可保留参数，便于继续编辑。
          </p>
        </div>
      </div>
      <div className="help-capabilities">
        <h3>自由创造与精确尺寸</h3>
        <p>
          <strong>AI + Blender：</strong>大模型编写新的建模程序，本地 Blender 使用曲线、自定义网格、布尔和修改器等工具完成建模。
          执行或网格检查失败会自动尝试修正，最多三轮。可下载 .blend 工程继续编辑。
        </p>
        <p>
          <strong>基础造型库中的小动物：</strong>
          兔、猫、熊、狗、狐狸、企鹅、鸭、猪、青蛙、乌龟，均为简化的可打印造型。
        </p>
        <p>
          <strong>实用部件：</strong>L
          型支架、安装板、渐开线直齿轮、垫片、开口盒、花瓶、旋钮、隔离柱、圆球、方块。
        </p>
        <p>
          <strong>更多轮廓：</strong>
          用草图画任意平面轮廓后拉伸；草图只决定平面形状，不会还原照片中的完整三维结构。
        </p>
        <p>
          <strong>运行位置：</strong>描述、草图、当前建模程序、精细模式的网格预览及必要的错误信息发送给所设大模型服务，可能产生费用。
          Blender 建模、文件保存和打印导出在本机完成。基础部件模式不需要网络或密钥。
        </p>
        <p className="help-boundary">
          封闭性检查通过代表网格可作为切片输入；不代表已经验证全部壁厚、支撑、装配精度或承载强度。
          螺纹、精密配合和复杂雕刻需要进一步检查，不能保证任意描述都能一次准确完成。
        </p>
      </div>
      <div className="help-bottom">
        <span>
          <Sparkles size={15} />
          不知道从哪开始？试试这只小兔。
        </span>
        <button className="button primary" onClick={() => onExample(EXAMPLES[0])}>
          做一只小兔
          <ArrowRight size={15} />
        </button>
      </div>
    </Modal>
  );
}
