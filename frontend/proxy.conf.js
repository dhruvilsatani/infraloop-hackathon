// Dev server proxy: forwards API calls to the FastAPI backend.
// BACKEND_URL is set by docker-compose.yml (http://backend:8000); falls back to a local run.
const target = process.env.BACKEND_URL || 'http://127.0.0.1:8000';

const apiRoute = {
  target,
  secure: false,
  changeOrigin: true,
  // /answer can hold the connection for 1-2+ minutes while the LLM writes the report
  proxyTimeout: 600000,
  timeout: 600000,
  // A browser page load (Accept: text/html) of /scan or /answer is an app page, not an API call.
  bypass: (req) => ((req.headers.accept || '').includes('text/html') ? '/index.html' : undefined),
};

module.exports = {
  '/scan': apiRoute,
  '/answer': apiRoute,
  '/upload': apiRoute,
  '/targets': apiRoute,
  '/preview': apiRoute,
  '/generate': apiRoute,
};
