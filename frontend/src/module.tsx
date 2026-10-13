import React, { useState } from 'react';
import { AppPlugin, AppPluginMeta, PluginConfigPageProps } from '@grafana/data';
import { Workbench } from './Workbench';
import { InvestigationApp } from './LiveDesk';
import './style.css';

function GrafanaInvestigationRoot() {
  const apiBase = '/api/plugin-proxy/dahe-autotriager-app/triager/api';
  return <InvestigationApp apiBase={apiBase} host="grafana" historical={<Workbench apiBase={apiBase} host="grafana" />} />;
}

interface AppOptions { apiUrl?: string; }

function ConnectionSettings({ plugin }: PluginConfigPageProps<AppPluginMeta<AppOptions>>) {
  const [lang, setLang] = useState<'en' | 'zh'>('en');
  const [url, setUrl] = useState(plugin.meta.jsonData?.apiUrl ?? 'http://127.0.0.1:8787');
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);
  const labels = lang === 'en' ? {
    title: 'Connect the investigation service', caption: 'AutoTriager · local development configuration',
    intro: 'Grafana forwards requests through its server-side plugin proxy. This address must be reachable from the Grafana server, not only from your browser.',
    address: 'Investigation service URL', save: 'Save connection', saved: 'Connection saved. Open the Investigation desk.',
    invalid: 'Enter an HTTP or HTTPS origin without credentials, path, query or fragment.',
    hint: 'Local preview only: the service has no enterprise authentication. Keep it on loopback. Docker containers have their own localhost unless host networking is explicitly configured.',
  } : {
    title: '连接故障调查服务', caption: 'AutoTriager · 本地开发配置',
    intro: 'Grafana 通过服务端插件代理转发请求。此地址必须能够从 Grafana 服务器访问，仅在浏览器中能够访问还不够。',
    address: '调查服务地址', save: '保存连接', saved: '连接已保存，可以打开故障调查工作台。',
    invalid: '请输入 HTTP 或 HTTPS 地址，不包含账号密码、路径、查询参数或片段。',
    hint: '仅供本地预览：此服务没有企业身份验证，请保留回环地址。Docker 容器有自己的 localhost，除非明确配置了主机网络。',
  };
  async function save(event: React.FormEvent) {
    event.preventDefault();
    let origin = '';
    try { const parsed = new URL(url); if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password || (parsed.pathname !== '/' && parsed.pathname !== '') || parsed.search || parsed.hash) throw new Error(); origin = parsed.origin; }
    catch { setStatus(labels.invalid); return; }
    setBusy(true); setStatus('');
    try {
      const response = await fetch('/api/plugins/dahe-autotriager-app/settings', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled: true, pinned: true, jsonData: { ...plugin.meta.jsonData, apiUrl: origin } }) });
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
      setStatus(labels.saved);
    } catch (error) { setStatus(error instanceof Error ? error.message : String(error)); }
    finally { setBusy(false); }
  }
  return <div className="at-workbench at-settings" lang={lang === 'en' ? 'en' : 'zh-CN'}><div className="at-language"><button type="button" onClick={() => setLang('en')} className={lang === 'en' ? 'active' : ''}>EN</button><button type="button" onClick={() => setLang('zh')} className={lang === 'zh' ? 'active' : ''}>中文</button></div><span className="at-eyebrow">{labels.caption}</span><h1>{labels.title}</h1><p>{labels.intro}</p><form onSubmit={save}><label htmlFor="at-api-url">{labels.address}</label><input id="at-api-url" type="url" value={url} onChange={(event) => setUrl(event.target.value)} disabled={busy} required/><button className="at-button at-button-primary" disabled={busy}>{labels.save}</button></form><p className="at-fine-print" style={{ marginTop: 20 }}>{labels.hint}</p>{status && <p role="status">{status}</p>}</div>;
}

export const plugin = new AppPlugin<AppOptions>().setRootPage(GrafanaInvestigationRoot).addConfigPage({ title: 'Connection', id: 'connection', body: ConnectionSettings });
