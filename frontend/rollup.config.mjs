import typescript from '@rollup/plugin-typescript';
import { readFileSync, mkdirSync, copyFileSync } from 'node:fs';
import { createHash } from 'node:crypto';

const scopedStyles = {
  name: 'scoped-workbench-styles',
  transform(_code, id) {
    if (!id.endsWith('.css')) return null;
    const css = JSON.stringify(readFileSync(id, 'utf8'));
    const styleId = JSON.stringify('autotriager-styles-' + createHash('sha256').update(id).digest('hex').slice(0, 12));
    return { code: `if (typeof document !== 'undefined' && !document.getElementById(${styleId})) { const style = document.createElement('style'); style.id = ${styleId}; style.textContent = ${css}; document.head.appendChild(style); } export default {};`, map: { mappings: '' } };
  },
  writeBundle() {
    mkdirSync('grafana-dist/img', { recursive: true });
    copyFileSync('public/plugin.json', 'grafana-dist/plugin.json');
    copyFileSync('public/img/logo.svg', 'grafana-dist/img/logo.svg');
  },
};

export default {
  input: 'src/module.tsx',
  output: { file: 'grafana-dist/module.js', format: 'system', sourcemap: true },
  external: (id) => id === 'react' || id.startsWith('react/') || id === 'react-dom' || id.startsWith('react-dom/') || id.startsWith('@grafana/'),
  plugins: [scopedStyles, typescript({ tsconfig: './tsconfig.json', noEmit: false, outDir: './grafana-dist' })],
};
