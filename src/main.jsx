import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import * as I from 'lucide-react';
import './styles.css';

const api = async (path, opts = {}) => {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10000);
  try {
    const response = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...opts, signal: controller.signal });
    let data = {};
    try { data = await response.json(); } catch {}
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    return data;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('انتهت مهلة الاتصال بالخدمة المحلية');
    throw error;
  } finally { clearTimeout(timer); }
};

const nav = [
  ['overview', 'نظرة عامة', I.LayoutDashboard], ['proxies', 'مركز البروكسي', I.Network],
  ['tasks', 'المهام الآلية', I.ListChecks], ['browser', 'المتصفح الآمن', I.Globe2],
  ['logs', 'السجل المباشر', I.ScrollText], ['settings', 'الإعدادات', I.Settings2],
];

function App() {
  const [page, setPage] = useState('overview');
  const [state, setState] = useState({ proxies: [], logs: [], tasks: [], running: false, settings: {}, stats: {} });
  const [toast, setToast] = useState('');
  const [apiError, setApiError] = useState('');
  const [busy, setBusy] = useState(false);
  const refresh = () => api('/api/state').then(data => { setState(data); setApiError(''); }).catch(error => setApiError(error.message));
  useEffect(() => { refresh(); const id = setInterval(refresh, 2500); return () => clearInterval(id); }, []);
  const action = async (path, body) => {
    setBusy(true);
    try { await api(path, { method: 'POST', body: JSON.stringify(body || {}) }); await refresh(); setToast('تم تنفيذ العملية بنجاح'); }
    catch (error) { setToast(`خطأ: ${error.message}`); }
    finally { setBusy(false); setTimeout(() => setToast(''), 3000); }
  };
  const current = nav.find(item => item[0] === page);
  return <div className="shell">
    <aside><div className="brand"><div className="logo"><I.Zap size={21} /></div><div><strong>CPA<span>•</span></strong><small>CONTROL CENTER</small></div></div>
      <div className="workspace"><div className="avatar">A</div><div><b>مساحة العمل الرئيسية</b><small>Local workspace</small></div><I.ChevronsUpDown size={15} /></div>
      <nav>{nav.map(([id, label, Icon]) => <button key={id} className={page === id ? 'active' : ''} onClick={() => setPage(id)}><Icon size={18} /><span>{label}</span>{id === 'logs' && state.logs.length > 0 && <em>{state.logs.length}</em>}</button>)}</nav>
      <div className="side-bottom"><div className="secure"><I.ShieldCheck size={18} /><div><b>وضع الخصوصية</b><small>المعالجة محلياً 100%</small></div><i /></div><small className="version">CPA Desktop v1.0.0</small></div>
    </aside>
    <main><header><div><div className="crumb">لوحة التحكم <span>/</span> {current?.[1]}</div><h1>{current?.[1]}</h1></div><div className="head-actions"><div className="system"><i /> النظام يعمل <span>•</span> {new Date().toLocaleTimeString('ar-MA', { hour: '2-digit', minute: '2-digit' })}</div><button className="icon-btn" title="التنبيهات"><I.Bell size={18} /></button><div className="profile">أ<span>عبد الرحمن</span><small>مشرف</small></div></div></header>
      <div className="content">{apiError && <div className="error-banner"><I.AlertTriangle size={17} /><span>{apiError}</span><button onClick={refresh}><I.RefreshCw size={14} /> إعادة المحاولة</button></div>}{busy && <div className="busy-bar" aria-live="polite">جار تنفيذ العملية...</div>}
        {page === 'overview' && <Overview state={state} action={action} />}{page === 'proxies' && <Proxies state={state} action={action} />}{page === 'logs' && <Logs state={state} />}{page === 'settings' && <Settings state={state} action={action} />}{page === 'tasks' && <Tasks state={state} action={action} />}{page === 'browser' && <Browser state={state} />}
      </div></main>{toast && <div className="toast"><I.CheckCircle2 size={18} />{toast}</div>}
  </div>;
}

function Overview({ state, action }) {
  const healthy = state.proxies.filter(proxy => proxy.status === 'healthy').length;
  const stats = state.stats || {};
  const successRate = state.requests ? Math.round(state.success / state.requests * 100) : 0;
  return <><div className="hero"><div><div className="eyebrow"><span /> CONTROL CENTER / LIVE</div><h2>أهلاً بك في مركز<br /><strong>الأتمتة الذكية.</strong></h2><p>راقب مهامك، أدر البروكسيات، وحافظ على سير العمل بكفاءة<br />من خلال لوحة تحكم موحدة وآمنة.</p><button className="primary" onClick={() => action('/api/automation/toggle')}><I.Play size={16} />{state.running ? 'إيقاف الأتمتة' : 'بدء الأتمتة'}<I.ArrowLeft size={16} /></button></div><div className="hero-art"><div className="orb o1" /><div className="orb o2" /><div className="radar"><I.Activity size={60} /></div></div></div>
    <div className="section-head"><div><h3>نظرة سريعة</h3><span>مؤشرات الأداء اللحظية</span></div><button className="link" onClick={() => action('/api/proxies/check')}>تحديث البيانات <I.RefreshCw size={14} /></button></div>
    <div className="stats"><Stat icon={I.Network} title="البروكسيات النشطة" val={healthy} meta={`${state.proxies.length} إجمالي البروكسيات`} color="cyan" /><Stat icon={I.ListChecks} title="المهام قيد التنفيذ" val={stats.active_tasks || 0} meta={`${state.tasks.length} إجمالي المهام`} color="violet" /><Stat icon={I.Gauge} title="متوسط الاستجابة" val={stats.avg_latency ?? '—'} unit={stats.avg_latency ? 'ms' : ''} meta="من آخر فحص" color="green" /><Stat icon={I.CircleCheck} title="معدل النجاح" val={state.requests ? successRate : '—'} unit="%" meta={`${state.success} نجاح / ${state.requests} تشغيل`} color="orange" /></div>
    <div className="grid2"><div className="card activity"><div className="card-title"><div><h3>نشاط الأتمتة</h3><span>إجمالي التشغيلات الحالية</span></div><span className="live-pill"><i /> LIVE</span></div><div className="chart"><div className="chart-label"><b>{state.requests}</b><small>إجراء مكتمل</small></div><div className="empty"><I.Activity size={25} /><span>سيظهر مخطط الأداء بعد تشغيل المهام</span></div></div></div><div className="card feed"><div className="card-title"><div><h3>آخر النشاطات</h3><span>تحديث تلقائي</span></div></div>{state.logs.slice(0, 5).map((log, index) => <div className="feed-row" key={`${log.time}-${index}`}><div className={`feed-icon ${log.level}`}><I.CheckCircle2 size={16} /></div><div><b>{log.message}</b><small>{log.time}</small></div></div>)}{!state.logs.length && <Empty text="لا توجد نشاطات بعد" />}</div></div></>;
}

function Stat({ icon: Icon, title, val, unit, meta, color }) { return <div className="stat"><div className={`stat-icon ${color}`}><Icon size={19} /></div><span>{title}</span><strong>{val}<small>{unit}</small></strong><em>{meta}</em></div>; }

function Proxies({ state, action }) {
  const [text, setText] = useState('');
  const healthy = state.proxies.filter(proxy => proxy.status === 'healthy').length;
  const latency = state.stats?.avg_latency;
  return <><div className="proxy-hero"><div><div className="eyebrow"><span /> PROXY ENGINE / SMART ROTATION</div><h2>مركز إدارة البروكسي</h2><p>فحص متوازٍ، تدوير ذكي، وقاطع دائرة لحماية استقرار كل جلسة.</p></div><div className="health-ring"><b>{state.proxies.length ? Math.round(healthy / state.proxies.length * 100) : 0}<small>%</small></b><span>جاهزية الشبكة</span></div></div>
    <div className="proxy-toolbar"><div className="proxy-input"><I.Link size={17} /><input value={text} onChange={event => setText(event.target.value)} placeholder="أدخل Proxy أو قائمة (host:port)" /><button disabled={!text.trim()} onClick={() => { action('/api/proxies/import', { text }); setText(''); }}>إضافة</button></div><button className="secondary" onClick={() => action('/api/proxies/check')}><I.Activity size={16} /> فحص شامل</button><button className="secondary danger" onClick={() => action('/api/proxies/clear')}><I.Trash2 size={16} /> مسح الكل</button></div>
    <div className="proxy-summary"><Stat icon={I.CircleCheck} title="متصل" val={healthy} meta="جاهز للاستخدام" color="green" /><Stat icon={I.Clock3} title="متوسط الكمون" val={latency ?? '—'} unit={latency ? 'ms' : ''} meta="من آخر فحص" color="cyan" /><Stat icon={I.ShieldAlert} title="في فترة انتظار" val={state.proxies.filter(proxy => proxy.cooldown > Date.now() / 1000).length} meta="حماية تلقائية" color="orange" /></div>
    <div className="card table-card"><div className="card-title"><div><h3>قائمة البروكسيات</h3><span>يتم ترتيبها تلقائياً حسب الصحة والسرعة</span></div><div className="card-actions"><button className="secondary" onClick={() => window.open('/api/export', '_blank')}><I.Download size={15} /> تصدير</button><span className="live-pill"><i /> LIVE</span></div></div><div className="table"><div className="tr th"><span>العنوان</span><span>النوع</span><span>الحالة</span><span>الاستجابة</span><span>النقاط</span><span>النجاح</span><span /></div>{state.proxies.map(proxy => <div className="tr" key={proxy.id || proxy.raw}><span className="mono">{proxy.host}:{proxy.port}</span><span className="tag">{proxy.scheme.toUpperCase()}</span><span><b className={`status ${proxy.status}`}><i />{proxy.status === 'healthy' ? 'متصل' : proxy.status === 'offline' ? 'غير متاح' : 'لم يفحص'}</b></span><span>{proxy.latency ? `${proxy.latency} ms` : '—'}</span><span className="score">{proxy.score || 0}</span><span>{proxy.successes || 0}/{(proxy.successes || 0) + (proxy.failures || 0)}</span><button className="dots danger" title="حذف البروكسي" onClick={() => window.confirm('حذف هذا البروكسي؟') && action('/api/proxies/delete', { id: proxy.id })}><I.Trash2 size={13} /></button></div>)}</div>{!state.proxies.length && <Empty text="لم تتم إضافة أي بروكسي. ابدأ بإضافة عنوان واحد أو قائمة كاملة." />}</div></>;
}

function Logs({ state }) { return <div className="card log-card"><div className="card-title"><div><h3>السجل المباشر</h3><span>كل أحداث النظام والأتمتة</span></div><span className="live-pill"><i /> LIVE</span></div>{state.logs.map((log, index) => <div className="log-row" key={`${log.time}-${index}`}><time>{log.time}</time><span className={`level ${log.level}`}>{log.level}</span><p>{log.message}</p></div>)}{!state.logs.length && <Empty text="السجل فارغ حالياً" />}</div>; }

function Settings({ state, action }) {
  const settings = state.settings || {};
  return <div className="settings-grid"><div className="card setting-card"><div className="card-title"><div><h3>محرك البروكسي</h3><span>تحكم دقيق في سياسة الاتصال</span></div><I.SlidersHorizontal size={20} /></div><label>استراتيجية التدوير<select value={settings.rotation || 'smart'} onChange={event => action('/api/settings', { rotation: event.target.value })}><option value="smart">ذكي — الأفضل أداءً</option><option value="round_robin">Round robin</option><option value="random">عشوائي</option></select></label><label>مهلة الاتصال<input type="number" min="1" max="120" value={settings.timeout ?? 8} onChange={event => action('/api/settings', { timeout: Number(event.target.value) })} /><small>بالثواني</small></label><label>عدد المحاولات<input type="number" min="0" max="10" value={settings.retries ?? 2} onChange={event => action('/api/settings', { retries: Number(event.target.value) })} /></label></div><div className="card setting-card"><div className="card-title"><div><h3>الأمان والخصوصية</h3><span>إعدادات حماية البيانات</span></div><I.ShieldCheck size={20} /></div><div className="toggle-row"><div><b>التحقق من شهادات TLS</b><small>رفض الاتصالات غير الآمنة</small></div><button className={`toggle ${settings.verify !== false ? 'on' : ''}`} onClick={() => action('/api/settings', { verify: settings.verify === false })} aria-pressed={settings.verify !== false}><i /></button></div><label>وضع WebRTC<select value={settings.webrtc_mode || 'blocked'} onChange={event => action('/api/settings', { webrtc_mode: event.target.value })}><option value="blocked">محظور — أقصى خصوصية</option><option value="proxy_only">عبر البروكسي فقط</option></select><small>لا يتم إنشاء عنوان IP أو بصمة WebRTC وهمية.</small></label><div className="toggle-row"><div><b>المعالجة المحلية</b><small>الخدمة تعمل على هذا الجهاز فقط</small></div><span className="status healthy"><i /> مفعلة</span></div></div></div>;
}

function Tasks({ state, action }) {
  const [name, setName] = useState(''); const [url, setUrl] = useState('');
  const create = () => { if (name.trim() && url.trim()) { action('/api/tasks/create', { name, url }); setName(''); setUrl(''); } };
  return <div><div className="proxy-hero"><div><div className="eyebrow"><span /> WORKFLOW ENGINE</div><h2>المهام الآلية</h2><p>أنشئ تدفقات عمل محفوظة محلياً وأدر تشغيلها من مكان واحد.</p></div><I.ListChecks size={62} color="#7b70ff" /></div><div className="card task-form"><div className="card-title"><div><h3>إنشاء مهمة جديدة</h3><span>سيتم حفظها في قاعدة البيانات المحلية</span></div><button className="secondary" onClick={() => action('/api/tasks/create-ip-check')}><I.Network size={16} /> إضافة فحص BrowserLeaks</button></div><div className="task-fields"><input value={name} onChange={event => setName(event.target.value)} placeholder="اسم المهمة" /><input value={url} onChange={event => setUrl(event.target.value)} placeholder="الرابط المستهدف https://..." dir="ltr" /><button className="primary" disabled={!name.trim() || !url.trim()} onClick={create}><I.Plus size={16} /> إضافة المهمة</button></div></div><div className="card task-list"><div className="card-title"><div><h3>المهام المحفوظة</h3><span>{state.tasks.length} مهام محلية</span></div></div>{state.tasks.map(task => <div className="task-row" key={task.id}><div className="task-state"><I.ListChecks size={16} /></div><div><b>{task.name}</b><small dir="ltr">{task.url}</small></div><span className={`status ${task.enabled ? 'healthy' : 'offline'}`}><i />{task.status === 'running' ? 'قيد التنفيذ' : task.enabled ? 'مفعلة' : 'متوقفة'}</span><div className="task-actions"><button className="dots" title="تشغيل" disabled={!task.enabled || task.status === 'running'} onClick={() => action('/api/tasks/run', { id: task.id })}><I.Play size={13} /></button><button className="dots" title="تفعيل أو إيقاف" disabled={task.status === 'running'} onClick={() => action('/api/tasks/toggle', { id: task.id })}><I.Power size={14} /></button><button className="dots danger" title="حذف" disabled={task.status === 'running'} onClick={() => action('/api/tasks/delete', { id: task.id })}><I.Trash2 size={13} /></button></div></div>)}{!state.tasks.length && <Empty text="لم تتم إضافة مهام بعد" />}</div></div>;
}

function Browser({ state }) {
  const [url, setUrl] = useState('https://example.com');
  const [message, setMessage] = useState('');
  const open = async () => {
    try {
      if (!window.desktop?.openBrowser) throw new Error('هذه الميزة متاحة داخل تطبيق Electron فقط');
      await window.desktop.openBrowser(url, { webrtcMode: state.settings?.webrtc_mode || 'blocked' });
      setMessage('تم فتح جلسة المتصفح المعزولة');
    } catch (error) { setMessage(error.message); }
  };
  const webrtcMode = state.settings?.webrtc_mode || 'blocked';
  return <div className="empty-page"><I.Globe2 size={48} /><h2>المتصفح الآمن</h2><p>جلسة Electron معزولة بإعدادات أمان مستقلة ومنع صلاحيات المواقع.</p><small>{webrtcMode === 'proxy_only' ? 'WebRTC مسموح عبر مسار البروكسي فقط؛ UDP المباشر محظور.' : 'WebRTC محظور: لا وسائط أو UDP مباشر خارج البروكسي.'}</small><div className="browser-launch"><input value={url} onChange={event => setUrl(event.target.value)} dir="ltr" placeholder="https://example.com" /><button className="primary" onClick={open}><I.ExternalLink size={16} /> فتح الجلسة</button></div>{message && <small>{message}</small>}</div>;
}
function Empty({ text }) { return <div className="empty"><I.Inbox size={25} /><span>{text}</span></div>; }

createRoot(document.getElementById('root')).render(<App />);
