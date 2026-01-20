declare global {
  interface Window {
    ENV?: {
      VITE_API_BASE_URL?: string;
      BACKEND_URL?: string;
      [key: string]: string | undefined;
    };
  }
}

export {};
