import { promises as fs } from 'node:fs';
import path from 'node:path';

/**
 * Local-development storage: one JSON array per table under `.data/`
 * (gitignored). Writes are serialised in-process and replaced atomically.
 */

const DATA_DIR = path.join(process.cwd(), '.data');

export type FileTableName = 'leads' | 'activities' | 'messages' | 'chats' | 'push' | 'state';

let queue: Promise<unknown> = Promise.resolve();

function filePath(name: FileTableName) {
  return path.join(DATA_DIR, `${name}.json`);
}

async function readJson<T>(file: string): Promise<T[] | null> {
  try {
    return JSON.parse(await fs.readFile(file, 'utf8')) as T[];
  } catch {
    return null;
  }
}

export async function readTable<T>(name: FileTableName): Promise<T[]> {
  const rows = await readJson<T>(filePath(name));
  if (rows) return rows;
  // First run: start the lead table from a private local seed if one exists.
  if (name === 'leads') return (await readJson<T>(path.join(DATA_DIR, 'leads.seed.json'))) || [];
  return [];
}

async function writeTable<T>(name: FileTableName, rows: T[]): Promise<void> {
  await fs.mkdir(DATA_DIR, { recursive: true });
  const target = filePath(name);
  const tmp = `${target}.${process.pid}.tmp`;
  await fs.writeFile(tmp, JSON.stringify(rows, null, 2), 'utf8');
  await fs.rename(tmp, target);
}

/** Read-modify-write a table without losing concurrent updates in dev. */
export function mutateTable<T, R>(name: FileTableName, fn: (rows: T[]) => R | Promise<R>): Promise<R> {
  const run = queue.then(async () => {
    const rows = await readTable<T>(name);
    const result = await fn(rows);
    await writeTable(name, rows);
    return result;
  });
  queue = run.catch(() => undefined);
  return run;
}
