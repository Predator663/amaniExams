/**
 * Development (`npm run dev`): the web app forwards /api and /media to the Django server itself, so the browser only ever talks
 * to ONE address. No CORS, no localhost-vs-127.0.0.1 problems, and it works from a phone on the same Wi-Fi.
 *   BACKEND_URL (optional) = where Django runs, default http://127.0.0.1:8000
 * Production (`npm run build`): plain static files that can be hosted anywhere (Render Static Site, Netlify, Nginx).
 *   NEXT_PUBLIC_API_URL = address of the API, e.g. https://api.example.com
 */
const dev = process.env.NODE_ENV === "development";
const backend = (process.env.BACKEND_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

export default dev
  ? {
      reactStrictMode: true, images: { unoptimized: true },
      trailingSlash: true,  // same URLs as production, and Django keeps the slash it needs (/api/auth/login/)
      async rewrites() {
        // the trailing "/" is written out on purpose: Next drops it from the forwarded address otherwise, and Django needs it
        return [{ source: "/api/:path*/", destination: `${backend}/api/:path*/` }, { source: "/media/:path*", destination: `${backend}/media/:path*` }];
      },
    }
  : { output: "export", trailingSlash: true, reactStrictMode: true, images: { unoptimized: true } };
