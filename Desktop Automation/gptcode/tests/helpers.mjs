import { cp } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// A copy gets its own unpacked-extension ID, so the native scanner registered for the
// installed extension (cai_bo_quet.py) never answers tests with the real kịch_bản folder.
export async function isolatedExtension(directory) {
  const target = path.join(directory, 'extension');
  await cp(fileURLToPath(new URL('../extension', import.meta.url)), target, { recursive: true });
  return target;
}
