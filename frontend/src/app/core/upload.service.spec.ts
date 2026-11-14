import { addToPick, classifyFile, newPick } from './upload.service';

describe('classifyFile', () => {
  it('skips dependency and VCS folders', () => {
    expect(classifyFile('node_modules/react/index.js', 10)).toEqual({ kind: 'skip', dir: 'node_modules' });
  });

  it('keeps secret files private (placeholder, marked secret)', () => {
    expect(classifyFile('app/.env', 10)).toEqual({ kind: 'placeholder', secret: true });
    expect(classifyFile('keys/server.pem', 10)).toEqual({ kind: 'placeholder', secret: true });
  });

  it('still sends example env files', () => {
    expect(classifyFile('.env.example', 10)).toEqual({ kind: 'send', secret: false });
  });

  it('sends normal source files and sends binaries by name only', () => {
    expect(classifyFile('src/main.py', 10)).toEqual({ kind: 'send', secret: false });
    expect(classifyFile('static/logo.png', 10)).toEqual({ kind: 'placeholder', secret: false });
  });
});

describe('addToPick', () => {
  it('records secret file names but never queues them for sending', () => {
    const p = newPick('demo');
    addToPick(p, 'demo/.env', new File(['A=1'], '.env'));
    expect(p.secrets).toEqual(['.env']);
    expect(p.files[0].kind).toBe('placeholder');
    expect(p.bytes).toBe(0);
  });
});
