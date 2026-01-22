interface ImportMetaEnv {
  readonly BACKEND_URL?: string;
  readonly DISABLE_REGISTRATION?: string;
  readonly JUKE_RUNTIME_ENV?: string;
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
