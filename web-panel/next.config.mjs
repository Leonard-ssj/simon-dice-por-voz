/** @type {import('next').NextConfig} */
const nextConfig = {
  webpack: (config) => {
    // @huggingface/transformers depende de onnxruntime-node (binario nativo de Node.js)
    // y de sharp. En el browser solo se necesita onnxruntime-web (WASM).
    // Poner false hace que webpack los ignore y use el fallback WASM.
    // Referencia: https://huggingface.co/docs/transformers.js/guides/nextjs
    config.resolve.alias = {
      ...config.resolve.alias,
      "sharp$":            false,
      "onnxruntime-node$": false,
    };

    // Permite que Web Workers con TypeScript funcionen en Next.js 14 App Router
    config.resolve.extensionAlias = {
      ".js": [".ts", ".tsx", ".js", ".jsx"],
    };

    return config;
  },
};

export default nextConfig;
