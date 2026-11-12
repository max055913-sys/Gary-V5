import {defineConfig} from './node_modules/vite/dist/node/index.js';
import {fileURLToPath} from 'node:url';
const here=fileURLToPath(new URL('.',import.meta.url));
export default defineConfig({root:here+'frontend',build:{outDir:here+'dist',emptyOutDir:false},server:{host:'127.0.0.1',port:5179,strictPort:true}});
